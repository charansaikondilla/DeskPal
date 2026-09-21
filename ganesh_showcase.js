'use strict';
const landing = document.getElementById('landing');
const runningPanel = document.getElementById('running-panel');
const launchButton = document.getElementById('launch-button');
const launchLabel = document.getElementById('launch-label');
const statusLabel = document.getElementById('launch-status');
const emoteStatus = document.getElementById('emote-status');
let launching = false;
let wasRunning = false;

async function request(path, method = 'GET') {
  const response = await fetch(path, {
    method, cache: 'no-store', signal: AbortSignal.timeout(15000),
    headers: method === 'POST' ? { 'X-DeskPal-Launch': '1' } : {}
  });
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('Open Start-DeskPal-Launch.bat to connect the desktop launcher.');
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not connect. Please try again.');
  return result;
}

async function refreshStatus() {
  try {
    const health = await request('/api/health');
    if (health.service !== 'deskpal-launcher') throw new Error('Wrong service');
    const state = await request('/api/status');
    document.getElementById('connection-dot').classList.add('ready');
    document.getElementById('connection-label').textContent = state.running ? 'DeskPal is running' : 'Ready to launch';
    if (wasRunning && !state.running && !launching) {
      landing.hidden = false;
      runningPanel.hidden = true;
      statusLabel.textContent = 'DeskPal is closed. Launch whenever you’re ready.';
    }
    wasRunning = Boolean(state.running);
  } catch {
    document.getElementById('connection-dot').classList.remove('ready');
    document.getElementById('connection-label').textContent = 'Launcher offline';
  }
}

launchButton.addEventListener('click', async () => {
  if (launching) return;
  launching = true;
  launchButton.disabled = true;
  launchLabel.textContent = 'Starting DeskPal…';
  statusLabel.textContent = 'Bringing your companion to the desktop…';
  try {
    const state = await request('/api/launch', 'POST');
    if (!state.running || !state.visible || state.character !== 'custom') throw new Error('The desktop companion is not ready yet. Try again.');
    wasRunning = true;
    landing.hidden = true;
    runningPanel.hidden = false;
    document.getElementById('back-button').focus();
    statusLabel.textContent = '';
    await refreshStatus();
  } catch (error) {
    statusLabel.textContent = error.message || 'Launch failed. Please try again.';
  } finally {
    launching = false;
    launchButton.disabled = false;
    launchLabel.textContent = 'Launch DeskPal';
  }
});

document.querySelectorAll('[data-emote]').forEach(button => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await request('/api/emote/' + button.dataset.emote, 'POST');
      document.querySelectorAll('[data-emote]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
      emoteStatus.textContent = button.textContent + ' is playing on your desktop.';
    } catch (error) {
      emoteStatus.textContent = error.message;
    } finally { button.disabled = false; }
  });
});
document.getElementById('back-button').addEventListener('click', () => {
  runningPanel.hidden = true;
  landing.hidden = false;
  launchButton.focus();
});
refreshStatus();
setInterval(() => { if (!document.hidden && !launching) refreshStatus(); }, 4000);
