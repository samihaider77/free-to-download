const tokenInput = document.getElementById('token');
const portInput = document.getElementById('port');
const status = document.getElementById('status');
chrome.storage.local.get(['token', 'port']).then(value => {tokenInput.value = value.token || ''; portInput.value = value.port || 17863;});
document.getElementById('save').addEventListener('click', async () => {
  const token = tokenInput.value.trim(), port = Number(portInput.value);
  if (!token || !Number.isInteger(port) || port < 1024 || port > 65535) {status.textContent = 'Enter a token and a valid local port.'; return;}
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {headers: {Authorization: `Bearer ${token}`}, signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Pairing failed. Check the token and keep Free-to-Download running.');
    await chrome.storage.local.set({token, port});
    status.textContent = 'Connected. Right-click a link and choose Download with Free-to-Download.';
  } catch (error) {status.textContent = error.message;}
});
