const status = document.getElementById('status');
const links = document.getElementById('links');
const selected = document.getElementById('selected');
const mediaButton = document.createElement('button');
mediaButton.textContent = 'Find detected videos / streams';
document.getElementById('scan').parentElement.after(mediaButton);
const pageButton = document.createElement('button');
pageButton.textContent = 'Download video from this page';
mediaButton.after(pageButton);
const pastedVideo = document.createElement('button');
pastedVideo.textContent = 'Download pasted video URLs';
pageButton.after(pastedVideo);
pastedVideo.addEventListener('click', () => {
  mediaMode = true; pageUrl = '';
  send(document.getElementById('urls').value.split(/\r?\n/).map(s => s.trim()).filter(Boolean));
});
let mediaMode = false;
let pageUrl = '';
pageButton.addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    mediaMode = true; pageUrl = tab.url;
    await send([tab.url]);
  } catch (error) { status.textContent = error.message; }
});
mediaButton.addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    pageUrl = tab.url; mediaMode = true;
    const result = await chrome.runtime.sendMessage({type: 'media-list', tabId: tab.id});
    links.replaceChildren();
    for (const item of result.items || []) {
      const label = document.createElement('label'); label.className = 'link';
      const input = document.createElement('input'); input.type = 'checkbox'; input.value = item.url;
      const text = document.createElement('span');
      const parsed = new URL(item.url);
      text.textContent = `${item.kind}: ${parsed.hostname}${parsed.pathname}`;
      label.append(input, text); links.append(label);
    }
    selected.hidden = !links.childElementCount;
    status.textContent = links.childElementCount ? 'Choose the media to download. Streams may include separate audio and video variants.' : 'No media detected. Refresh this page, play the video, and try again.';
  } catch (error) { status.textContent = error.message; }
});
async function send(urls) {
  if (!urls.length) {status.textContent = 'Choose at least one link.'; return;}
  try {
    const response = await chrome.runtime.sendMessage({type: 'download', urls: urls.slice(0, 50), media: mediaMode, referer: mediaMode ? pageUrl : ''});
    status.textContent = response.error || `Sent ${response.accepted} link(s) to the desktop app.`;
    if (!response.error) await chrome.action.setBadgeText({text: ''});
  } catch (error) {status.textContent = error.message;}
}
document.getElementById('send').addEventListener('click', () => {
  mediaMode = false;
  send(document.getElementById('urls').value.split(/\r?\n/).map(s => s.trim()).filter(Boolean));
});
document.getElementById('settings').addEventListener('click', () => chrome.runtime.openOptionsPage());
document.getElementById('scan').addEventListener('click', async () => {
  mediaMode = false;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const [result] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: () => {
      const urls = [...document.querySelectorAll('a[href], video[src], audio[src], source[src]')].map(el => el.href || el.src);
      return [...new Set(urls)].filter(url => /^https?:\/\//i.test(url)).slice(0, 200);
    }});
    links.replaceChildren();
    for (const url of result.result) {
      const label = document.createElement('label'); label.className = 'link';
      const input = document.createElement('input'); input.type = 'checkbox'; input.value = url;
      const text = document.createElement('span'); text.textContent = url;
      label.append(input, text); links.append(label);
    }
    selected.hidden = !result.result.length;
    status.textContent = `Found ${result.result.length} links. Select up to 50 to download.`;
  } catch (error) {status.textContent = 'This page cannot be scanned: ' + error.message;}
});
selected.addEventListener('click', () => send([...links.querySelectorAll('input:checked')].map(input => input.value)));
chrome.storage.local.get('lastError').then(({lastError}) => {if (lastError) status.textContent = lastError;});
