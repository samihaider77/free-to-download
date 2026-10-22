const QUALITIES = ['best', '2160', '1440', '1080', '720', '480', '360', 'audio'];
async function sendUrls(urls, media = false, referer = '', title = '', quality = 'best') {
  const { token = '', port = 17863 } = await chrome.storage.local.get(['token', 'port']);
  if (!token) throw new Error('Open extension Settings and pair with the desktop app.');
  const body = {urls, media, referer};
  if (media && title) body.title = title.slice(0, 200);
  if (media && QUALITIES.includes(quality) && quality !== 'best') body.quality = quality;
  const response = await fetch(`http://127.0.0.1:${port}/downloads`, {
    method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
    body: JSON.stringify(body), signal: AbortSignal.timeout(5000)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Desktop app rejected this request.');
  return result;
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: 'send', title: 'Download with Free-to-Download', contexts: ['link', 'image', 'video', 'audio']});
  });
});
chrome.contextMenus.onClicked.addListener(async info => {
  if (info.menuItemId !== 'send') return;
  try {
    const url = info.linkUrl || info.srcUrl;
    if (!/^https?:\/\//i.test(url || '')) throw new Error('This media does not expose a direct HTTP download URL.');
    await sendUrls([url]);
    await chrome.action.setBadgeText({text: 'OK'});
    await chrome.action.setBadgeBackgroundColor({color: '#0f766e'});
    await chrome.storage.local.set({lastError: ''});
  } catch (error) {
    await chrome.action.setBadgeText({text: '!'});
    await chrome.action.setBadgeBackgroundColor({color: '#b91c1c'});
    await chrome.storage.local.set({lastError: error.message});
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message.type === 'media-list') {
    const tabId = sender.tab?.id ?? message.tabId;
    chrome.storage.session.get('media-' + tabId).then(data => {
      const items = (data['media-' + tabId] || []).filter(item => Date.now() - item.time < 1800000);
      // The top page sees everything in its tab (players often fetch from workers or child frames);
      // an embedded frame only sees its own requests.
      respond({items: sender.tab && sender.frameId ? items.filter(item => item.frameId === sender.frameId) : items});
    });
    return true;
  }
  if (message.type !== 'download') return;
  sendUrls(message.urls, message.media === true, message.referer || '', typeof message.title === 'string' ? message.title : '',
    typeof message.quality === 'string' ? message.quality : 'best').then(respond).catch(error => respond({error: error.message}));
  return true;
});

// Store only media candidates, temporarily and per tab. Never copy cookies or
// authorization headers. A request is sent to the app only after a user click.
let storageQueue = Promise.resolve();
// onResponseStarted also fires for responses served from the browser cache, unlike onHeadersReceived,
// so a video watched (or downloaded) before is still detected.
chrome.webRequest.onResponseStarted.addListener(details => {
  if (details.tabId < 0 || details.statusCode < 200 || details.statusCode >= 300) return;
  const header = name => details.responseHeaders?.find(h => h.name.toLowerCase() === name)?.value || '';
  const type = header('content-type').split(';')[0].toLowerCase();
  const parsed = new URL(details.url);
  const path = parsed.pathname;
  // Byte-range chunks (YouTube's /videoplayback and similar) are never whole videos; the page link handles those sites.
  if (/\/videoplayback$/.test(path) || /[?&](range|byterange|bytestart)=/i.test(parsed.search)) return;
  const playlist = /mpegurl|dash\+xml/.test(type) || /\.(m3u8|mpd)$/i.test(path);
  const file = /^(video|audio)\//.test(type) || /\.(mp4|webm|m4a|mp3|mov)$/i.test(path);
  if (!playlist && !file) return;
  if (/\.(ts|m4s|cmfv|cmfa)$/i.test(path) || type === 'video/mp2t') return;
  // Streams such as LinkedIn's serve each HLS piece (header-only init file, numbered fragments) as
  // video/mp4. Those are not whole videos; only the playlist is worth offering.
  const total = +(header('content-range').match(/\/(\d+)$/)?.[1] || (details.statusCode === 200 ? header('content-length') : 0)) || 0;
  const disposition = (header('content-disposition').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1] || '');
  if (!playlist && (/(^|[_\-./])(init|seg(ment)?|frag(ment)?|chunk)([_\-.\d]|$)/i.test(disposition + ' ' + path)
      || (total && total < 300 * 1024))) return;
  const key = 'media-' + details.tabId;
  storageQueue = storageQueue.then(async () => {
    const old = (await chrome.storage.session.get(key))[key] || [];
    const items = old.filter(item => item.url !== details.url && Date.now() - item.time < 1800000);
    items.push({url: details.url, kind: playlist ? 'Stream' : 'Media', size: total, frameId: details.frameId, referer: details.initiator || '', time: Date.now()});
    await chrome.storage.session.set({[key]: items.slice(-60)});
  }).catch(() => {});
}, {urls: ['http://*/*', 'https://*/*']}, ['responseHeaders']);
chrome.tabs.onRemoved.addListener(tabId => { storageQueue = storageQueue.then(() => chrome.storage.session.remove('media-' + tabId)).catch(() => {}); });
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.status === 'loading') storageQueue = storageQueue.then(() => chrome.storage.session.remove('media-' + tabId)).catch(() => {});
});
