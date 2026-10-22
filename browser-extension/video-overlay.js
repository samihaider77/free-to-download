(() => {
  if (window.__openDownloadVideoOverlay) return;
  window.__openDownloadVideoOverlay = true;

  const host = document.createElement('div');
  host.style.cssText = 'all:initial;position:fixed;z-index:2147483647;display:none;';
  const shadow = host.attachShadow({mode: 'closed'});
  shadow.innerHTML = `
    <style>
      * { box-sizing: border-box; font-family: "Segoe UI", system-ui, sans-serif; }
      .bar { display: flex; align-items: stretch; height: 30px; border-radius: 4px; overflow: hidden;
             box-shadow: 0 2px 10px rgba(0,0,0,.45); border: 1px solid #1e3a8a; user-select: none; }
      .bar button { all: unset; cursor: pointer; color: #fff; display: flex; align-items: center;
                    background: linear-gradient(#4f8ff7, #2563eb 55%, #1d4ed8); }
      .bar button:hover { background: linear-gradient(#60a5fa, #3b82f6 55%, #2563eb); }
      .bar .main { gap: 7px; padding: 0 10px 0 8px; font: 600 12.5px/1 "Segoe UI", system-ui, sans-serif; white-space: nowrap; }
      .bar .main svg { flex: none; }
      .bar .caret, .bar .close { width: 22px; justify-content: center; border-left: 1px solid rgba(255,255,255,.28);
                                 font-size: 11px; }
      .bar.sent button { background: linear-gradient(#22c55e, #16a34a 55%, #15803d); }
      .menu { position: absolute; top: 34px; right: 0; min-width: 300px; max-width: 420px; display: none;
              background: #fff; color: #111827; border: 1px solid #9ca3af; border-radius: 4px;
              box-shadow: 0 6px 22px rgba(0,0,0,.35); padding: 4px 0; font-size: 13px; }
      .menu.open { display: block; }
      .head { padding: 6px 12px 5px; font-size: 11px; font-weight: 600; letter-spacing: .04em;
              text-transform: uppercase; color: #6b7280; }
      .item { all: unset; display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 12px;
              cursor: pointer; box-sizing: border-box; }
      .item:hover, .item:focus-visible { background: #dbeafe; }
      .item[disabled] { cursor: default; color: #6b7280; background: none; }
      .q { min-width: 52px; font-weight: 700; color: #1d4ed8; }
      .what { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .sub { color: #6b7280; font-size: 11.5px; }
      .note { padding: 7px 12px; color: #374151; }
      .note.error { color: #b91c1c; }
      .foot { border-top: 1px solid #e5e7eb; margin-top: 4px; padding: 5px 12px 3px; font-size: 11px; color: #9ca3af; }
    </style>
    <div class="bar" part="bar">
      <button class="main" type="button" title="Download this video with Free-to-Download">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 1.5v8.2M4.6 6.6 8 10l3.4-3.4" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M2.5 11.5v2h11v-2" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="label">Download this video</span>
      </button>
      <button class="caret" type="button" title="Choose quality" aria-label="Choose quality">▾</button>
      <button class="close" type="button" title="Hide for this video" aria-label="Hide">✕</button>
    </div>
    <div class="menu" role="menu"></div>`;
  const bar = shadow.querySelector('.bar');
  const label = shadow.querySelector('.label');
  const menu = shadow.querySelector('.menu');
  (document.documentElement || document.body).append(host);

  let activeVideo = null;
  let resetTimer = 0;
  const watched = new WeakSet();
  const dismissed = new WeakSet();
  const playedAt = new WeakMap();  // when each video first started loading or playing
  const starts = [];               // [WeakRef(video), time] for every video seen starting

  function noteStart(video) {
    if (playedAt.has(video)) return;
    const time = Date.now();
    playedAt.set(video, time);
    starts.push([new WeakRef(video), time]);
  }

  // Streams that arrived within a few seconds of this video starting, trusted only when no other
  // video started in the same window (otherwise the streams could be theirs).
  function streamsNearStart(video, items, window = 8000) {
    const started = playedAt.get(video);
    const crowded = starts.some(([ref, time]) => ref.deref() !== video && Math.abs(time - started) < window);
    return crowded ? [] : items.filter(item => item.time && Math.abs(item.time - started) < window);
  }

  function directUrl(video) {
    if (video.currentSrc && !/^https?:\/\//i.test(video.currentSrc)) return '';
    const candidates = [video.currentSrc, video.src,
      ...[...video.querySelectorAll('source[src]')].map(source => source.src)];
    return candidates.find(url => /^https?:\/\//i.test(url || '') && !/\.(m3u8|mpd)(?:[?#]|$)/i.test(url)) || '';
  }

  // Turn a raw media URL into a menu entry: quality first, then format.
  function megabytes(bytes) {
    return bytes >= 1073741824 ? (bytes / 1073741824).toFixed(2) + ' GB' : (bytes / 1048576).toFixed(1) + ' MB';
  }

  function describe(url, kind, bytes = 0) {
    const parsed = new URL(url);
    const text = decodeURIComponent(parsed.pathname + parsed.search);
    const height = +((text.match(/(?:^|[^0-9])(4320|2160|1440|1080|720|540|480|360|240|144)p/i)
      || text.match(/[_\-/=](4320|2160|1440|1080|720|540|480|360|240|144)(?=[_\-./&]|$)/) || [])[1] || 0);
    const audio = /audio|[_\-/]aac[_\-./]|mp4a/i.test(text) && !height;
    const codec = (text.match(/\b(av1|h264|avc1?|hevc|h265|vp9)\b/i) || [])[1] || '';
    const ext = (parsed.pathname.match(/\.([a-z0-9]{2,4})$/i) || [])[1]?.toLowerCase() || '';
    // Only a detected playlist is a stream; a URL merely containing "hls" may be one piece of it.
    const format = kind === 'Stream' ? (ext === 'mpd' || /dash/i.test(text) ? 'DASH' : 'HLS')
      : ext && ext !== 'm3u8' && ext !== 'mpd' ? ext.toUpperCase() : 'file';
    return {
      url, height, audio, stream: kind === 'Stream',
      quality: audio ? 'Audio' : height ? height + 'p' : kind === 'Stream' ? 'Best' : '—',
      what: [audio ? 'Audio only' : 'Full video', format, codec.toUpperCase(), bytes ? megabytes(bytes) : ''].filter(Boolean).join(' · '),
      sub: parsed.hostname,
    };
  }

  // Sites whose players stream in chunks; the downloader extracts them best from the page link.
  const PAGE_SITES = /(^|\.)(youtube\.com|youtu\.be|linkedin\.com|vimeo\.com|x\.com|twitter\.com|facebook\.com|instagram\.com|tiktok\.com|dailymotion\.com|reddit\.com|twitch\.tv)$/i;

  // The link the downloader should open for this video: the post on LinkedIn, the watch page on
  // YouTube (also when embedded), otherwise the page itself.
  function pageLink(video) {
    if (/linkedin\.com$/i.test(location.hostname)) {
      if (/^\/(feed\/update\/urn:li:activity:\d+|posts\/)/.test(location.pathname)) return location.href;
      return linkedInPost(video);
    }
    const embed = location.pathname.match(/^\/(?:embed|shorts)\/([\w-]{11})/);
    if (/youtube(-nocookie)?\.com$/i.test(location.hostname) && embed) return `https://www.youtube.com/watch?v=${embed[1]}`;
    return location.href;
  }

  // Find the LinkedIn post that holds this video. Climb from the video only while the container
  // still holds this one video: once it holds others we have left the post and reached the feed.
  // In each container look for the post's ID in attributes, then for the post's own permalink.
  function linkedInPost(video) {
    const postUrl = (kind, id) => `https://www.linkedin.com/feed/update/urn:li:${kind}:${id}/`;
    let fallback = '';
    for (let el = video; el && el !== document.documentElement; el = el.parentElement || el.getRootNode()?.host) {
      if (el !== video && el.querySelectorAll?.('video').length > 1) break;
      for (const attr of el.attributes || []) {
        const activity = attr.value.match(/urn:li:activity:(\d{8,})/);
        if (activity) return postUrl('activity', activity[1]);
        const other = attr.value.match(/urn:li:(ugcPost|share):(\d{8,})/);
        if (other && !fallback) fallback = postUrl(other[1], other[2]);
      }
      for (const anchor of el.querySelectorAll?.('a[href]') || []) {
        const href = anchor.href;
        const activity = href.match(/urn(?::|%3A)li(?::|%3A)activity(?::|%3A)(\d{8,})/i);
        if (activity) return postUrl('activity', activity[1]);
        if (/linkedin\.com\/posts\/[^/?#]+-\d{8,}/i.test(href)) return href.split('?')[0];
      }
    }
    return fallback;
  }

  // Media asset ID from the video's cover image: the poster, or a cover image inside the same post.
  function videoAsset(video) {
    const cover = /\/dms\/image\/(?:v2\/)?([A-Za-z0-9_-]{12,})\/videocover/;
    const sources = [video.poster];
    const attributesOf = node => [...(node.attributes || [])].map(attr => attr.value).filter(value => value.includes('videocover'));
    sources.push(...attributesOf(video));
    for (let el = video.parentElement, depth = 0; el && depth < 8; el = el.parentElement, depth++) {
      if (el.querySelectorAll('video').length > 1) break;
      sources.push(...attributesOf(el));  // e.g. data-poster-url on the player wrapper
      for (const node of el.querySelectorAll('img[src*="videocover"], [style*="videocover"], [data-poster-url]')) {
        sources.push(node.currentSrc || node.src, ...attributesOf(node));
      }
    }
    for (const source of sources) {
      const id = (source || '').match(cover)?.[1];
      if (id) return id;
    }
    return '';
  }

  // Page structure around the video, without query strings (they hold access tokens), for bug reports.
  function diagnostics(video, items) {
    const strip = value => String(value || '').split('?')[0].slice(0, 160);
    const chain = [];
    for (let el = video, depth = 0; el && el !== document.documentElement && depth < 12; el = el.parentElement, depth++) {
      chain.push([el.tagName.toLowerCase(), el.id ? '#' + el.id : '', strip(el.className),
        [...el.attributes].filter(a => !['class', 'id', 'style'].includes(a.name)).map(a => `${a.name}=${strip(a.value)}`).join(' '),
        `videos:${el.querySelectorAll?.('video').length ?? 0}`].filter(Boolean).join(' '));
    }
    // Times in ms relative to when this video started loading, to show which streams arrived with it.
    const started = playedAt.get(video);
    const relative = time => (started && time ? time - started : null);
    return JSON.stringify({extension: chrome.runtime.getManifest().version, host: location.hostname,
      poster: strip(video?.poster), src: strip(video?.currentSrc), asset: video ? videoAsset(video) : '',
      started: Boolean(started), otherVideoStarts: starts.filter(([ref]) => ref.deref() !== video).map(([, time]) => relative(time)),
      streams: items.map(item => `${strip(item.url)} @${relative(item.time)}`), chain}, null, 1);
  }

  function pageTitle() {
    const raw = (document.title || '').replace(/^\(\d+\)\s*/, '').trim();
    const parts = raw.match(/^(.*?)\s+[|\-–—]\s+([^|\-–—]{2,40})$/);
    let title = (parts ? parts[1] : raw).trim();
    // Titles like "Post" or "Video" say nothing on their own; prefix the site name.
    if (title.length < 12) title = `${parts ? parts[2].trim() : location.hostname} ${title}`.trim();
    return title;
  }

  function place() {
    if (!activeVideo || !activeVideo.isConnected) return hide();
    const rect = activeVideo.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 70 || rect.bottom < 0 || rect.top > innerHeight) return hide();
    host.style.top = `${Math.max(8, rect.top + 10)}px`;
    host.style.left = `${Math.max(8, Math.min(innerWidth - bar.offsetWidth - 8, rect.right - bar.offsetWidth - 10))}px`;
  }

  function show(video) {
    if (dismissed.has(video)) return;
    if (activeVideo === video && host.style.display === 'block') { place(); return; }
    activeVideo = video;
    closeMenu();
    host.style.display = 'block';
    requestAnimationFrame(place);
  }

  function hide() {
    host.style.display = 'none';
    activeVideo = null;
    closeMenu();
  }

  function closeMenu() { menu.classList.remove('open'); }

  function note(text, error = false) {
    const div = document.createElement('div');
    div.className = error ? 'note error' : 'note';
    div.textContent = text;
    return div;
  }

  async function openMenu() {
    const video = activeVideo;
    menu.replaceChildren(note('Looking for video streams…'));
    menu.classList.add('open');
    let items = [];
    try {
      const found = await chrome.runtime.sendMessage({type: 'media-list'});
      // Streams that loaded after this video started playing most likely belong to it; other
      // videos on the page (feed autoplay) load streams too.
      const since = (video && playedAt.get(video)) || 0;
      items = (found?.items || []).map(item => ({...describe(item.url, item.kind, item.size), time: item.time,
                                                 mine: !since || item.time >= since - 3000}));
    } catch (error) {
      menu.replaceChildren(note(error.message || 'Extension is not responding. Reload the page.', true));
      return;
    }
    const direct = video && directUrl(video);
    if (direct && !items.some(item => item.url === direct)) items.unshift(describe(direct, 'Media'));
    const seen = new Set();
    items = items.filter(item => !seen.has(item.url) && seen.add(item.url))
      // Audio last; a master playlist ("Best") first, then highest quality, streams before loose files.
      .sort((a, b) => ((b.mine ?? true) - (a.mine ?? true)) || (a.audio - b.audio)
        || ((b.stream && !b.height) - (a.stream && !a.height)) || (b.height - a.height) || (b.stream - a.stream));
    // A site's media ID in the video's cover image (LinkedIn: /dms/image/v2/<asset>/videocover…) also
    // appears in every stream address of that video, so it singles out this video's streams.
    const all = items;
    const asset = video ? videoAsset(video) : '';
    let matched = asset ? items.filter(item => item.url.includes(asset)) : [];
    // Second signal: streams that arrived within a few seconds of this video starting to load, when no
    // other video started in that window (covers posts whose cover image has a different ID).
    if (!matched.length && video && playedAt.has(video)) matched = streamsNearStart(video, items);
    // Known video but none of its streams seen yet: never offer other videos' streams instead.
    const waitForPlay = Boolean(asset) && !matched.length && !pageLink(video);
    if (matched.length || waitForPlay) items = matched;
    items = items.slice(0, 12);
    let link = video && pageLink(video);
    // No page link, but this video's own stream manifest is known: offer the quality choices on it.
    const manifest = !link && matched.find(item => item.stream);
    if (manifest) {
      link = manifest.url;
      items = items.filter(item => item !== manifest);
    }
    const unsure = !link && !matched.length && PAGE_SITES.test(location.hostname) && items.length > 0;
    if (link) {
      const sub = location.hostname.replace(/^www\./, '');
      if (PAGE_SITES.test(location.hostname)) {
        // These sites offer several renditions; the downloader takes the closest one at or below the choice.
        items.unshift(...[['best', 'Best', 'Highest quality available'], ['1080', '1080p', 'Full HD'], ['720', '720p', 'HD'],
          ['480', '480p', 'Smaller file'], ['360', '360p', 'Smallest video'], ['audio', 'Audio', 'Audio only · MP3']]
          .map(([choice, quality, what]) => ({url: link, choice, quality, what, sub})));
      } else {
        const page = {url: link, choice: 'best', quality: 'Best', what: 'Full video · from page link', sub};
        items.length ? items.push(page) : items.unshift(page);
      }
    }
    const head = document.createElement('div');
    head.className = 'head';
    head.textContent = items.length ? 'Download with Free-to-Download' : 'No video detected yet';
    menu.replaceChildren(head);
    if (!items.length) menu.append(note(waitForPlay ? 'Play this video for a few seconds, then click again.'
                                                     : 'Play the video for a few seconds, then click again.'));
    if (unsure) menu.append(note('Couldn’t identify this video for sure. These streams were seen on the page; the top one most likely belongs to it.'));
    if ((unsure || !items.length) && video) {
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'item';
      copy.textContent = 'Copy diagnostic info (for a bug report)';
      copy.addEventListener('click', async event => {
        event.stopPropagation();
        await navigator.clipboard.writeText(diagnostics(video, all)).catch(() => {});
        copy.textContent = 'Copied ✓ — paste it into an issue on GitHub';
      });
      menu.append(copy);
    }
    for (const item of items) {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'item';
      row.setAttribute('role', 'menuitem');
      row.title = item.url;
      const q = document.createElement('span'); q.className = 'q'; q.textContent = item.quality;
      const what = document.createElement('span'); what.className = 'what'; what.textContent = item.what;
      const sub = document.createElement('span'); sub.className = 'sub'; sub.textContent = item.sub;
      row.append(q, what, sub);
      row.addEventListener('click', event => { event.stopPropagation(); send(item.url, row, item.choice || 'best'); });
      menu.append(row);
    }
    const foot = document.createElement('div');
    foot.className = 'foot';
    foot.textContent = 'Separate audio and video streams are combined automatically.';
    menu.append(foot);
  }

  async function send(url, row, quality) {
    const what = row.querySelector('.what');
    const original = what.textContent;
    row.disabled = true;
    if (row.nextElementSibling?.classList.contains('error')) row.nextElementSibling.remove();
    what.textContent = 'Sending to Free-to-Download…';
    // If the app is closed the browser starts it, which can take a few seconds.
    const slow = setTimeout(() => { what.textContent = 'Starting Free-to-Download…'; }, 1500);
    try {
      const response = await chrome.runtime.sendMessage({type: 'download', urls: [url], media: true,
        referer: location.href, title: pageTitle(), quality});
      if (!response || response.error) throw new Error(response?.error || 'Desktop app did not respond.');
      closeMenu();
      label.textContent = 'Sent to Free-to-Download ✓';
      bar.classList.add('sent');
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => { label.textContent = 'Download this video'; bar.classList.remove('sent'); place(); }, 3000);
      place();
    } catch (error) {
      row.after(note(error.message || 'Unable to send video', true));
    } finally {
      clearTimeout(slow);
      what.textContent = original;
      row.disabled = false;
    }
  }

  function watch(video) {
    if (watched.has(video)) return;
    watched.add(video);
    for (const type of ['loadstart', 'playing']) video.addEventListener(type, () => noteStart(video), {passive: true});
    video.addEventListener('mouseenter', () => show(video), {passive: true});
    video.addEventListener('mousemove', () => show(video), {passive: true});
  }

  function scan(root = document) {
    if (root instanceof HTMLVideoElement) watch(root);
    root.querySelectorAll?.('video').forEach(watch);
  }

  for (const target of [shadow.querySelector('.main'), shadow.querySelector('.caret')]) {
    target.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      menu.classList.contains('open') ? closeMenu() : openMenu();
    });
  }
  shadow.querySelector('.close').addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    if (activeVideo) dismissed.add(activeVideo);
    hide();
  });
  // Sites often listen for clicks on the player; keep ours from toggling playback.
  for (const type of ['mousedown', 'mouseup', 'pointerdown', 'pointerup', 'dblclick']) {
    host.addEventListener(type, event => event.stopPropagation());
  }
  addEventListener('click', event => { if (!event.composedPath().includes(host)) closeMenu(); }, true);
  addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); }, true);

  scan();
  function visiblePlayer() {
    const videos = [];
    function collect(root) {
      root.querySelectorAll('video').forEach(video => videos.push(video));
      root.querySelectorAll('*').forEach(el => { if (el.shadowRoot) collect(el.shadowRoot); });
    }
    collect(document);
    const visible = videos.filter(video => {
      const r = video.getBoundingClientRect();
      return !dismissed.has(video) && r.width >= 120 && r.height >= 70 && r.bottom > 40 && r.top < innerHeight - 40 && r.right > 0 && r.left < innerWidth;
    });
    const video = visible.includes(activeVideo) ? activeVideo : visible[0];
    if (video) show(video); else hide();
  }
  setInterval(visiblePlayer, 1000);
  document.addEventListener('fullscreenchange', () => {
    const target = document.fullscreenElement || document.documentElement;
    if (!(target instanceof HTMLVideoElement)) target.append(host);
    visiblePlayer();
  });
  new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) scan(node);
    }
  }).observe(document.documentElement, {childList: true, subtree: true});
  addEventListener('scroll', place, {passive: true, capture: true});
  addEventListener('resize', place, {passive: true});
})();
