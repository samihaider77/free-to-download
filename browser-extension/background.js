const QUALITIES = ['best', '2160', '1440', '1080', '720', '480', '360', 'audio'];
const NOT_RUNNING = 'Free-to-Download is not running. Start the app, then try again.';
const LAUNCHER = 'com.free_to_download.launcher';

class NotRunning extends Error {
  constructor() { super(NOT_RUNNING); }
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// Ask the desktop app for its token. The app answers only this extension (it checks the
// browser-set Origin header against our fixed ID), so no manual pairing is needed.
async function pair(port) {
  let response;
  try {
    response = await fetch(`http://127.0.0.1:${port}/pair`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(3000)
    });
  } catch {
    throw new NotRunning();
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.token) throw new Error(result.error || 'Could not connect to Free-to-Download.');
  await chrome.storage.local.set({token: result.token});
  return result;
}

// The app is closed: ask the browser to start it through its registered launcher (native messaging),
// then wait for it to open. The launcher exists once the app has been run on this computer.
async function startApp(port) {
  try {
    await chrome.runtime.sendNativeMessage(LAUNCHER, {action: 'start'});
  } catch {
    throw new NotRunning();
  }
  for (let attempt = 0; attempt < 40; attempt++) {
    await sleep(500);
    try {
      return await pair(port);
    } catch (error) {
      if (!(error instanceof NotRunning)) throw error;
    }
  }
  throw new NotRunning();
}

async function pairOrStart(port) {
  try {
    return await pair(port);
  } catch (error) {
    if (!(error instanceof NotRunning)) throw error;
    return startApp(port);
  }
}

async function connection() {
  const {token = '', port = 17863} = await chrome.storage.local.get(['token', 'port']);
  return {token: token || (await pairOrStart(port)).token, port};
}

async function sendUrls(urls, media = false, referer = '', title = '', quality = 'best') {
  const body = {urls, media, referer};
  if (media && title) body.title = title.slice(0, 200);
  if (media && QUALITIES.includes(quality) && quality !== 'best') body.quality = quality;
  let {token, port} = await connection();
  const post = auth => fetch(`http://127.0.0.1:${port}/downloads`, {
    method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${auth}`},
    body: JSON.stringify(body), signal: AbortSignal.timeout(5000)
  }).catch(() => { throw new NotRunning(); });
  let response;
  try {
    response = await post(token);
  } catch (error) {
    if (!(error instanceof NotRunning)) throw error;
    // The app was closed after pairing: start it, then send.
    token = (await startApp(port)).token;
    response = await post(token);
  }
  if (response.status === 401) {
    // The app was reinstalled or its data reset: fetch the new token once and retry.
    token = (await pair(port)).token;
    response = await post(token);
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Desktop app rejected this request.');
  return result;
}

async function status() {
  try {
    const {port = 17863} = await chrome.storage.local.get('port');
    const result = await pair(port);
    return {connected: true, version: result.version};
  } catch (error) {
    return error instanceof NotRunning
      ? {connected: false, error: 'Free-to-Download is closed. It starts by itself when you download something.'}
      : {connected: false, error: error.message};
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: 'send', title: 'Download with Free-to-Download', contexts: ['link', 'image', 'video', 'audio']});
  });
  status();
});
chrome.runtime.onStartup.addListener(() => { status(); });
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
  if (message.type === 'status') {
    status().then(respond);
    return true;
  }
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
