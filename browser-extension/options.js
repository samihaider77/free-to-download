const state = document.getElementById('state');
const tokenInput = document.getElementById('token');
const portInput = document.getElementById('port');
const status = document.getElementById('status');

async function check() {
  state.textContent = 'Checking the connection…';
  const result = await chrome.runtime.sendMessage({type: 'status'});
  state.textContent = result?.connected
    ? `✓ Connected to Free-to-Download ${result.version}. Play a video and click “Download this video”.`
    : `✗ ${result?.error || 'Could not reach the app.'}`;
  state.className = result?.connected ? 'ok' : 'error';
}

chrome.storage.local.get(['token', 'port']).then(value => {
  tokenInput.value = value.token || '';
  portInput.value = value.port || 17863;
});
document.getElementById('check').addEventListener('click', check);
document.getElementById('save').addEventListener('click', async () => {
  const token = tokenInput.value.trim(), port = Number(portInput.value);
  if (!token || !Number.isInteger(port) || port < 1024 || port > 65535) {status.textContent = 'Enter a token and a valid local port.'; return;}
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {headers: {Authorization: `Bearer ${token}`}, signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Pairing failed. Check the token and keep Free-to-Download running.');
    await chrome.storage.local.set({token, port});
    status.textContent = 'Saved.';
    check();
  } catch (error) {status.textContent = error.message;}
});
check();
