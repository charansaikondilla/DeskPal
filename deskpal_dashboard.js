'use strict';

// --------------------------------------------------------------------------
// DeskPal Dashboard — live productivity + health hub (no external libraries)
// --------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const SVG_NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (text !== undefined) node.textContent = text;
  return node;
}
function series(n) { return getComputedStyle(document.documentElement).getPropertyValue('--s' + n).trim(); }
function fmtMin(m) {
  m = Math.max(0, Math.round(m));
  if (m < 60) return m + 'm';
  return Math.floor(m / 60) + 'h ' + String(m % 60).padStart(2, '0') + 'm';
}
function fmtClock(sec) {
  sec = Math.max(0, Math.round(sec));
  return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
}
function todayISO() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

// ─── API ─────────────────────────────────────────────────────────────────
async function api(path, method = 'GET', body = null) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const headers = {};
    if (method !== 'GET') headers['X-DeskPal-Launch'] = '1';
    if (body !== null) headers['Content-Type'] = 'application/json';
    const opts = { method, headers, signal: controller.signal };
    if (body !== null) opts.body = JSON.stringify(body);
    const response = await fetch(path, opts);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

// ─── theme ───────────────────────────────────────────────────────────────
(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('deskpal-theme'); } catch (e) { /* private mode */ }
  if (saved === 'dark' || saved === 'light') document.documentElement.dataset.theme = saved;
  const btn = $('#themeToggle');
  if (!btn) return;
  btn.onclick = () => {
    const root = document.documentElement;
    const osDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = root.dataset.theme === 'dark' || (!root.dataset.theme && osDark);
    root.dataset.theme = isDark ? 'light' : 'dark';
    try { localStorage.setItem('deskpal-theme', root.dataset.theme); } catch (e) { /* ignore */ }
    renderAll();
  };
})();

// ─── greeting ────────────────────────────────────────────────────────────
(function initGreeting() {
  const h = new Date().getHours();
  const word = h < 5 ? 'Still up?' : h < 12 ? 'Good morning.' : h < 17 ? 'Good afternoon.' : h < 21 ? 'Good evening.' : 'Winding down.';
  $('#greeting').textContent = word;
  $('#dateLine').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
})();

// ─── tooltip ─────────────────────────────────────────────────────────────
const tooltip = $('#tooltip');
function showTip(html, x, y) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const pad = 12;
  const w = tooltip.offsetWidth;
  const left = Math.min(Math.max(x, w / 2 + pad), window.innerWidth - w / 2 - pad);
  tooltip.style.left = left + 'px';
  tooltip.style.top = y + 'px';
}
function hideTip() { tooltip.hidden = true; }

// ─── chart: active vs idle line/area ─────────────────────────────────────
function drawActivity(container, hours) {
  container.innerHTML = '';
  const W = container.clientWidth || 800, H = container.clientHeight || 240;
  const pad = { l: 34, r: 12, t: 12, b: 26 };
  const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H });
  const x = (h) => pad.l + (h / 23) * (W - pad.l - pad.r);
  const y = (m) => pad.t + (1 - Math.min(60, m) / 60) * (H - pad.t - pad.b);

  [0, 15, 30, 45, 60].forEach((m) => {
    svg.appendChild(el('line', { class: m === 0 ? 'axis' : 'grid', x1: pad.l, x2: W - pad.r, y1: y(m), y2: y(m) }));
    svg.appendChild(el('text', { x: pad.l - 8, y: y(m) + 4, 'text-anchor': 'end' }, String(m)));
  });
  for (let h = 0; h <= 23; h += 3) {
    svg.appendChild(el('text', { x: x(h), y: H - 8, 'text-anchor': 'middle' }, h === 0 ? '12am' : h < 12 ? h + 'am' : h === 12 ? '12pm' : (h - 12) + 'pm'));
  }

  const data = (hours || []).filter((d) => typeof d.h === 'number');
  if (!data.length) {
    svg.appendChild(el('text', { class: 'empty', x: W / 2, y: H / 2 }, 'No activity recorded yet — keep DeskPal running.'));
    container.appendChild(svg);
    return;
  }

  const build = (key, color, cls) => {
    const pts = data.map((d) => x(d.h) + ',' + y(d[key] || 0));
    const last = data[data.length - 1];
    svg.appendChild(el('polygon', { class: 'area', fill: color,
      points: pts.join(' ') + ' ' + x(last.h) + ',' + y(0) + ' ' + x(data[0].h) + ',' + y(0) }));
    svg.appendChild(el('polyline', { class: 'line', stroke: color, points: pts.join(' ') }));
    if (data.length === 1) svg.appendChild(el('circle', { class: 'marker', cx: x(last.h), cy: y(last[key] || 0), r: 4, fill: color }));
  };
  build('idle', series(2));
  build('active', series(1));

  const cross = el('line', { class: 'crosshair', y1: pad.t, y2: H - pad.b, x1: 0, x2: 0, visibility: 'hidden' });
  const dotA = el('circle', { class: 'marker', r: 4.5, fill: series(1), visibility: 'hidden' });
  const dotI = el('circle', { class: 'marker', r: 4.5, fill: series(2), visibility: 'hidden' });
  svg.appendChild(cross); svg.appendChild(dotI); svg.appendChild(dotA);
  const hideHover = () => { hideTip(); [cross, dotA, dotI].forEach((n) => n.setAttribute('visibility', 'hidden')); };

  const hit = el('rect', { class: 'hit', x: pad.l, y: pad.t, width: W - pad.l - pad.r, height: H - pad.t - pad.b });
  hit.addEventListener('mousemove', (ev) => {
    const rect = container.getBoundingClientRect();
    const h = Math.round(((ev.clientX - rect.left) * (W / rect.width) - pad.l) / (W - pad.l - pad.r) * 23);
    const d = data.find((p) => p.h === h);
    if (!d) { hideHover(); return; }
    cross.setAttribute('x1', x(h)); cross.setAttribute('x2', x(h));
    dotA.setAttribute('cx', x(h)); dotA.setAttribute('cy', y(d.active || 0));
    dotI.setAttribute('cx', x(h)); dotI.setAttribute('cy', y(d.idle || 0));
    [cross, dotA, dotI].forEach((n) => n.setAttribute('visibility', 'visible'));
    const label = h === 0 ? '12 am' : h < 12 ? h + ' am' : h === 12 ? '12 pm' : (h - 12) + ' pm';
    showTip('<b>' + label + '</b><br>Active ' + (d.active || 0) + ' min · Idle ' + (d.idle || 0) + ' min',
      rect.left + x(h) * (rect.width / W), rect.top + y(Math.max(d.active || 0, d.idle || 0)) * (rect.height / H));
  });
  hit.addEventListener('mouseleave', hideHover);
  svg.appendChild(hit);
  container.appendChild(svg);
}

// ─── chart: grouped bars ─────────────────────────────────────────────────
function drawBars(container, days, keys, colors, names) {
  container.innerHTML = '';
  const W = container.clientWidth || 800, H = container.clientHeight || 220;
  const pad = { l: 30, r: 8, t: 12, b: 26 };
  const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H });
  const max = Math.max(4, ...days.flatMap((d) => keys.map((k) => d[k] || 0)));
  const step = max <= 8 ? 2 : max <= 20 ? 5 : 10;
  const top = Math.ceil(max / step) * step;
  const y = (v) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  for (let v = 0; v <= top; v += step) {
    svg.appendChild(el('line', { class: v === 0 ? 'axis' : 'grid', x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
    svg.appendChild(el('text', { x: pad.l - 8, y: y(v) + 4, 'text-anchor': 'end' }, String(v)));
  }
  const groupW = (W - pad.l - pad.r) / days.length;
  const inner = groupW * 0.68;
  const barW = inner / keys.length;
  days.forEach((d, i) => {
    const gx = pad.l + i * groupW + (groupW - inner) / 2;
    svg.appendChild(el('text', { x: pad.l + i * groupW + groupW / 2, y: H - 8, 'text-anchor': 'middle' }, d.label));
    keys.forEach((k, j) => {
      const v = d[k] || 0;
      const bx = gx + j * barW + 1;
      const bh = Math.max(0, y(0) - y(v));
      const bar = el('rect', { class: 'bar', x: bx, y: y(v), width: Math.max(1, barW - 2), height: v ? Math.max(3, bh) : 0, fill: colors[j] });
      const hit = el('rect', { class: 'hit', x: bx - 1, y: pad.t, width: barW, height: H - pad.t - pad.b });
      const onMove = (ev) => {
        const rect = container.getBoundingClientRect();
        showTip('<b>' + d.label + '</b><br>' + names[j] + ': ' + v, rect.left + (bx + barW / 2) * (rect.width / W), rect.top + y(v) * (rect.height / H));
        bar.style.opacity = '0.8';
      };
      hit.addEventListener('mousemove', onMove);
      hit.addEventListener('mouseleave', () => { hideTip(); bar.style.opacity = ''; });
      svg.appendChild(bar); svg.appendChild(hit);
    });
  });
  container.appendChild(svg);
}

// ─── state ───────────────────────────────────────────────────────────────
let stats = null;
let status = null;
let focusLocal = null;   // { end: epoch ms, total: sec, kind, label }
let desktopOnline = false;
let isStarting = false;

// ─── tiles ───────────────────────────────────────────────────────────────
function renderTiles() {
  const t = (stats && stats.today) || {};
  const active = t.active_min || 0, idle = t.idle_min || 0;
  $('#tActive').textContent = fmtMin(active);
  $('#tActiveFoot').textContent = active + idle ? 'of ' + fmtMin(active + idle) + ' at the desk · ' + Math.round(active / (active + idle) * 100) + '% active' : 'nothing recorded yet';
  $('#tFocus').textContent = String(t.focus || 0);
  $('#tFocusFoot').textContent = (t.breaks || 0) + (t.breaks === 1 ? ' break taken today' : ' breaks taken today');
  $('#tStreak').textContent = String((stats && stats.streak) || 0);
  const counts = $('#todayCounts');
  counts.innerHTML = '';
  [['Water', t.water], ['Eye rest', t.eye], ['Stretch', t.stretch], ['Exercise', t.exercise], ['Breaks', t.breaks]].forEach(([n, v]) => {
    const s = document.createElement('span');
    s.innerHTML = n + ' today <b>' + (v || 0) + '</b>';
    counts.appendChild(s);
  });
}

function renderNextReminder() {
  const next = $('#tNext'), foot = $('#tNextFoot');
  if (!status || !status.running) { next.textContent = '—'; foot.textContent = desktopOnline ? 'DeskPal is hidden' : 'launch Ganesh to start reminders'; return; }
  if (status.quiet_mode) { next.textContent = 'Quiet'; foot.textContent = 'reminders snoozed'; return; }
  if (status.paused_reason === 'idle') { next.textContent = 'Paused'; foot.textContent = 'you are away from the PC'; return; }
  if (status.next_reminder && status.next_reminder_in_seconds != null) {
    next.textContent = status.next_reminder;
    const s = status.next_reminder_in_seconds, m = Math.floor(s / 60);
    foot.textContent = m > 0 ? 'in ' + m + ' min' : 'in under a minute';
    return;
  }
  next.textContent = '—'; foot.textContent = 'no reminders scheduled';
}

// ─── focus ring ──────────────────────────────────────────────────────────
const RING = 540.35;
function renderFocus() {
  const fill = $('#ringFill'), time = $('#ringTime'), label = $('#ringLabel'), chip = $('#focusStatus');
  const start = $('#focusStart'), stop = $('#focusStop'), brk = $('#breakStart');
  const canControl = desktopOnline && status && status.running;
  start.disabled = !canControl || !!focusLocal; stop.disabled = !canControl || !focusLocal; brk.disabled = !canControl || !!focusLocal;
  if (!focusLocal) {
    fill.style.strokeDashoffset = RING; fill.classList.remove('break');
    time.textContent = fmtClock((parseInt($('#focusMinutes').value, 10) || 25) * 60);
    label.textContent = canControl ? 'ready' : 'offline';
    chip.textContent = canControl ? 'Idle' : 'Launch Ganesh first'; chip.className = 'status-chip';
    return;
  }
  const left = Math.max(0, (focusLocal.end - Date.now()) / 1000);
  const pct = focusLocal.total ? Math.min(1, 1 - left / focusLocal.total) : 0;
  fill.style.strokeDashoffset = RING * (1 - pct);
  fill.classList.toggle('break', focusLocal.kind !== 'focus');
  time.textContent = fmtClock(left);
  label.textContent = (focusLocal.kind === 'focus' ? 'focusing' : focusLocal.kind === 'break' ? 'on a break' : focusLocal.label || 'timer');
  chip.textContent = focusLocal.kind === 'focus' ? 'In session' : 'Break'; chip.className = 'status-chip on';
  if (left <= 0) { focusLocal = null; setTimeout(loadStats, 1200); }
}
setInterval(renderFocus, 1000);

$('#focusStart').onclick = async () => {
  const minutes = Math.max(5, Math.min(120, parseInt($('#focusMinutes').value, 10) || 25));
  $('#focusMinutes').value = minutes;
  try { applyStats(await api('/api/focus', 'POST', { action: 'start', minutes })); $('#focusHint').textContent = 'Focus started — Ganesh will stay quiet for ' + minutes + ' minutes.'; }
  catch (e) { $('#focusHint').textContent = 'Could not start the session. Is Ganesh running?'; }
};
$('#focusStop').onclick = async () => {
  try { applyStats(await api('/api/focus', 'POST', { action: 'stop' })); $('#focusHint').textContent = 'Session stopped.'; }
  catch (e) { $('#focusHint').textContent = 'Could not reach DeskPal.'; }
};
$('#breakStart').onclick = async () => {
  try { applyStats(await api('/api/focus', 'POST', { action: 'break' })); $('#focusHint').textContent = 'Break started — step away from the screen.'; }
  catch (e) { $('#focusHint').textContent = 'Could not reach DeskPal.'; }
};

// ─── goals ───────────────────────────────────────────────────────────────
let goalsSig = '';
function renderGoals() {
  const goals = (stats && stats.goals) || [];
  // renderStatus() calls this every second; only touch the DOM when the
  // goals really changed so an in-flight click never lands on a dead row.
  const sig = JSON.stringify([desktopOnline, goals]);
  if (sig === goalsSig) return;
  goalsSig = sig;
  const list = $('#goalList');
  if (!desktopOnline) { list.innerHTML = '<div class="empty-list">Launch Ganesh to load and save your goals.</div>'; return; }
  if (!goals.length) { list.innerHTML = '<div class="empty-list">No goals yet. Add one above — it will show up here every day.</div>'; return; }
  const fragment = document.createDocumentFragment();   // swapped in atomically below
  goals.forEach((g) => {
    const row = document.createElement('div');
    row.className = 'item' + (g.done_today ? ' done' : '');
    const text = document.createElement('div');
    const name = document.createElement('strong'); name.textContent = g.name;
    if (g.streak > 0) { const b = document.createElement('span'); b.className = 'streak-badge'; b.textContent = g.streak + (g.streak === 1 ? ' day' : ' days'); name.appendChild(b); }
    const sub = document.createElement('small'); sub.textContent = g.done_today ? 'Done today' : 'Not done yet today';
    text.appendChild(name); text.appendChild(sub);
    const actions = document.createElement('div'); actions.className = 'item-actions';
    const toggle = document.createElement('button'); toggle.className = 'btn ' + (g.done_today ? 'done-btn' : 'ghost'); toggle.textContent = g.done_today ? 'Done ✓' : 'Mark done';
    toggle.onclick = async () => { try { applyStats(await api('/api/goals', 'POST', { action: 'toggle', id: g.id })); } catch (e) { flash('#goalStatus', 'Could not save', 'warn'); } };
    const del = document.createElement('button'); del.className = 'btn ghost del'; del.textContent = '×'; del.title = 'Remove goal';
    del.onclick = async () => { try { applyStats(await api('/api/goals', 'POST', { action: 'delete', id: g.id })); } catch (e) { flash('#goalStatus', 'Could not remove', 'warn'); } };
    actions.appendChild(toggle); actions.appendChild(del);
    row.appendChild(text); row.appendChild(actions);
    fragment.appendChild(row);
  });
  list.replaceChildren(fragment);
}
$('#goalForm').onsubmit = async (ev) => {
  ev.preventDefault();
  const input = $('#goalName');
  const name = input.value.trim();
  if (!name) return;
  try { applyStats(await api('/api/goals', 'POST', { action: 'add', name })); input.value = ''; flash('#goalStatus', 'Saved', 'on'); }
  catch (e) { flash('#goalStatus', 'Launch Ganesh first', 'warn'); }
};
function flash(sel, text, cls) {
  const chip = $(sel); chip.textContent = text; chip.className = 'status-chip ' + (cls || '');
  setTimeout(() => { if (chip.textContent === text) { chip.textContent = ''; chip.className = 'status-chip'; } }, 2500);
}

// ─── exercises (local list, completions counted by DeskPal) ──────────────
const defaultExercises = [
  { name: 'Desk stretch', minutes: 2 }, { name: 'Shoulder rolls', minutes: 2 }, { name: 'Short walk', minutes: 5 }
];
function loadExercises() {
  const today = todayISO();
  try {
    const parsed = JSON.parse(localStorage.getItem('deskpal-exercises') || 'null');
    if (!Array.isArray(parsed) || !parsed.length) throw new Error('empty');
    return parsed.map((x) => ({
      name: typeof x.name === 'string' && x.name.trim() ? x.name.trim().slice(0, 40) : 'Exercise',
      minutes: Number.isFinite(x.minutes) && x.minutes > 0 ? Math.min(120, Math.round(x.minutes)) : 2,
      doneDate: x.doneDate === today ? today : ''
    }));
  } catch (e) { return defaultExercises.map((x) => ({ ...x, doneDate: '' })); }
}
let exercises = loadExercises();
function saveExercises() { try { localStorage.setItem('deskpal-exercises', JSON.stringify(exercises)); } catch (e) { /* ignore */ } }
function renderExercises() {
  const list = $('#exerciseList');
  list.innerHTML = '';
  const today = todayISO();
  exercises.forEach((x, i) => {
    const done = x.doneDate === today;
    const row = document.createElement('div'); row.className = 'item' + (done ? ' done' : '');
    const text = document.createElement('div');
    const name = document.createElement('strong'); name.textContent = x.name;
    const sub = document.createElement('small'); sub.textContent = x.minutes + ' min' + (done ? ' · done today' : '');
    text.appendChild(name); text.appendChild(sub);
    const actions = document.createElement('div'); actions.className = 'item-actions';
    const btn = document.createElement('button'); btn.className = 'btn ' + (done ? 'done-btn' : 'ghost'); btn.textContent = done ? 'Done ✓' : 'Mark done';
    btn.onclick = async () => {
      x.doneDate = done ? '' : today;
      saveExercises(); renderExercises();
      if (!done && desktopOnline) { try { applyStats(await api('/api/exercise_done', 'POST')); } catch (e) { /* counted locally only */ } }
    };
    const del = document.createElement('button'); del.className = 'btn ghost del'; del.textContent = '×'; del.title = 'Remove exercise';
    del.onclick = () => { exercises.splice(i, 1); saveExercises(); renderExercises(); };
    actions.appendChild(btn); actions.appendChild(del);
    row.appendChild(text); row.appendChild(actions);
    list.appendChild(row);
  });
  if (!exercises.length) list.innerHTML = '<div class="empty-list">No exercises. Add one to build a routine.</div>';
}
const dialog = $('#dialog');
$('#addExercise').onclick = () => { dialog.showModal(); $('#name').focus(); };
$('#save').onclick = (e) => {
  const name = $('#name').value.trim(), minutes = parseInt($('#minutes').value, 10);
  if (!name || !Number.isFinite(minutes) || minutes < 1 || minutes > 120) { e.preventDefault(); return; }
  exercises.push({ name: name.slice(0, 40), minutes, doneDate: '' });
  saveExercises(); renderExercises();
  $('#name').value = ''; $('#minutes').value = '2';
};

// ─── reminders ───────────────────────────────────────────────────────────
const reminderKey = { 'Water': 'water_every', 'Eye rest': 'eye_every', 'Stretch': 'stretch_every', 'Posture': 'posture_every', 'Break': 'break_every' };
function applySettings(settings) {
  if (!settings) return;
  $$('[data-reminder]').forEach((sel) => {
    const key = reminderKey[sel.dataset.reminder];
    if (key && settings[key] !== undefined) {
      const v = String(settings[key]);
      if (!Array.from(sel.options).some((o) => o.value === v)) { const o = document.createElement('option'); o.value = v; o.textContent = 'Every ' + v + ' min'; sel.appendChild(o); }
      sel.value = v;
    }
  });
}
$$('[data-reminder]').forEach((sel) => {
  sel.onchange = async () => {
    const key = reminderKey[sel.dataset.reminder], minutes = parseInt(sel.value, 10);
    try { await api('/api/settings', 'POST', { [key]: minutes }); flash('#reminderStatus', sel.dataset.reminder + ' → every ' + minutes + ' min', 'on'); }
    catch (e) { flash('#reminderStatus', 'Launch Ganesh to save', 'warn'); }
  };
});

// ─── toast & confirm ─────────────────────────────────────────────────────
let toastTimer = null;
function toast(text) {
  const t = $('#toast'); t.textContent = text; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}
function confirmDialog(title, text, okLabel) {
  return new Promise((resolve) => {
    const d = $('#confirm');
    $('#confirmTitle').textContent = title; $('#confirmText').textContent = text; $('#confirmOk').textContent = okLabel || 'Yes';
    const done = () => { d.removeEventListener('close', done); resolve(d.returnValue === 'ok'); };
    d.addEventListener('close', done);
    d.returnValue = 'cancel';
    d.showModal();
  });
}

// ─── companion: emotes & actions ─────────────────────────────────────────
const EMOTE_STATE = { wave: 'wave', walk: 'walk', run: 'run_cycle', laddu: 'eat_laddu', hungry: 'hungry_cycle', celebrate: 'celebrate' };
$$('[data-emote]').forEach((btn) => {
  btn.onclick = async () => {
    try {
      await api('/api/emote/' + btn.dataset.emote, 'POST');
      flash('#actionStatus', btn.textContent + (btn.dataset.emote === 'stop' ? '' : ' playing'), 'on');
      loadStatus();
    } catch (e) { flash('#actionStatus', 'Launch Ganesh first', 'warn'); }
  };
});
async function runAction(action, minutes) {
  const body = { action };
  if (minutes) body.minutes = minutes;
  return api('/api/action', 'POST', body);
}
$$('[data-action]').forEach((btn) => {
  btn.onclick = async () => {
    const action = btn.dataset.action;
    const chip = btn.closest('#settings') ? '#aboutStatus' : btn.closest('.panel') && btn.closest('.panel').querySelector('#presenceStatus') ? '#presenceStatus' : '#actionStatus';
    try {
      const res = await runAction(action, parseInt(btn.dataset.minutes || '0', 10) || 0);
      if (res && res.app) { status = res; desktopOnline = !!res.running; renderStatus(); }
      const label = btn.textContent.trim();
      flash(chip, action === 'scene' ? 'Scene starting on the desktop' : label + ' ✓', 'on');
      if (action === 'reset_timers') toast('Reminder timers reset — every reminder starts counting from now.');
      if (action === 'scene' && res && res.scene_error) toast(res.scene_error);
    } catch (e) { flash(chip, 'Launch Ganesh first', 'warn'); }
  };
});
$('#resetAll').onclick = async () => {
  if (!await confirmDialog('Reset everything?', 'Every setting goes back to its default. Your goals and daily history are kept.', 'Reset')) return;
  try { const res = await runAction('reset_all'); await loadSettings(); flash('#aboutStatus', 'Defaults restored', 'on'); toast('All settings are back to their defaults.'); if (res && res.app) { status = res; renderStatus(); } }
  catch (e) { flash('#aboutStatus', 'Launch Ganesh first', 'warn'); }
};
$('#quitApp').onclick = async () => {
  if (!await confirmDialog('Quit DeskPal?', 'Ganesh leaves the desktop and reminders stop until you start DeskPal again.', 'Quit')) return;
  try { await runAction('quit'); toast('DeskPal is closing. Double-click Start DeskPal.bat to come back.'); setTimeout(loadStatus, 1500); }
  catch (e) { flash('#aboutStatus', 'DeskPal is not running', 'warn'); }
};

$('#launch').onclick = async () => {
  if (isStarting) return;
  isStarting = true; renderLive();
  try { await api('/api/launch', 'POST'); await loadStatus(); await loadStats(); await loadSettings(); }
  catch (e) { flash('#actionStatus', 'Could not launch DeskPal', 'warn'); }
  finally { isStarting = false; renderLive(); }
};

// ─── presence: live animation state, mirrored from the desktop ───────────
const STATE_WORDS = {
  idle: 'Standing idle', ganesh_rest: 'Resting', walk: 'Walking', run_cycle: 'Running', run: 'Running', wave: 'Waving',
  breathe_cycle: 'Breathing', meditation_peek: 'Meditation peek', eat_laddu: 'Modak jump & catch', window_peek: 'Peeking from the edge',
  water_slump: 'Thirsty slump', drink_water: 'Drinking water', bless_cycle: 'Blessing', study_cycle: 'Studying', mouse_play: 'Playing with the rat',
  mouse_ride: 'Riding the mouse', happy_jump: 'Happy jump', celebrate: 'Celebrating', hungry_cycle: 'Getting hungry', dance: 'Dancing',
  stretch: 'Stretching', jumping_jacks: 'Jumping jacks', sit: 'Sitting quietly', sleep: 'Napping', happy: 'Happy', watching: 'Watching you'
};
const FRAMES = {
  walk: ['ganesh_walk1', 'ganesh_walk2', 'ganesh_walk3', 'ganesh_walk4', 'ganesh_walk5', 'ganesh_walk6', 'ganesh_walk7', 'ganesh_walk8', 'ganesh_walk9'],
  run_cycle: ['ganesh_run1', 'ganesh_run2', 'ganesh_run3', 'ganesh_run4', 'ganesh_run5', 'ganesh_run6', 'ganesh_run7', 'ganesh_run8'],
  run: ['ganesh_run1', 'ganesh_run2', 'ganesh_run3', 'ganesh_run4', 'ganesh_run5', 'ganesh_run6', 'ganesh_run7', 'ganesh_run8'],
  hungry_cycle: ['ganesh_hungry1', 'ganesh_hungry2'],
  eat_laddu: ['ganesh_laddu_raise', 'ganesh_laddu_toss1', 'ganesh_laddu_toss2', 'ganesh_laddu_toss3', 'ganesh_laddu_catch', 'ganesh_laddu_bite', 'ganesh_laddu_chew', 'ganesh_satisfied'],
  watching: ['ganesh_watch1', 'ganesh_watch2', 'ganesh_watch3', 'ganesh_watch4']
};
const avatarImg = document.createElement('img');
avatarImg.alt = '';
avatarImg.onerror = () => { avatarImg.src = 'assets/ganesh/ganesh_stand.png'; };
$('#presenceAvatar').appendChild(avatarImg);
let frameTick = 0;
function renderPresence() {
  const box = $('#presence'), state = $('#presenceState'), foot = $('#presenceFoot');
  const online = desktopOnline && status && status.running;
  box.classList.toggle('on', !!online);
  if (!online) {
    state.textContent = 'Offline'; foot.textContent = 'Launch Ganesh to see the live state.';
    avatarImg.src = 'assets/ganesh/ganesh_stand.png';
    return;
  }
  const name = status.character === 'custom' ? 'Ganesh' : (status.pet_name || 'Buddy');
  const word = STATE_WORDS[status.state] || (status.state || 'idle').replace(/_/g, ' ');
  state.textContent = status.visible ? name + ' · ' + word : name + ' is hidden';
  const bits = [];
  if (status.scene) bits.push('Scene: ' + status.scene.replace(/_/g, ' '));
  if (status.hidden_seconds) bits.push('back in ' + fmtClock(status.hidden_seconds));
  if (status.snooze_seconds) bits.push('quiet for ' + fmtClock(status.snooze_seconds));
  if (status.idle_seconds >= 60) bits.push('you have been away ' + fmtMin(status.idle_seconds / 60));
  if (status.uptime_seconds != null) bits.push('running for ' + fmtMin(status.uptime_seconds / 60));
  foot.textContent = bits.join(' · ') || 'Live on your desktop right now.';
  const frames = status.visible ? FRAMES[status.state] : null;
  const wanted = 'assets/ganesh/' + (frames ? frames[frameTick % frames.length] : 'ganesh_stand') + '.png';
  if (!avatarImg.src.endsWith(wanted)) avatarImg.src = wanted;
  $$('.emote-grid .btn').forEach((b) => b.classList.toggle('playing', status.visible && EMOTE_STATE[b.dataset.emote] === status.state || b.dataset.emote === status.state));
}
setInterval(() => { frameTick++; if (status && FRAMES[status.state]) renderPresence(); }, 140);

// ─── live strip (header) ─────────────────────────────────────────────────
let statusAt = 0;
function renderLiveStrip() {
  const st = $('#lsState'), next = $('#lsNext'), idle = $('#lsIdle'), foc = $('#lsFocus');
  const text = st.querySelector('span');
  st.className = 'live-item';
  if (!status) { text.textContent = 'DeskPal service offline'; st.classList.add('off'); next.hidden = idle.hidden = foc.hidden = true; return; }
  if (!status.running) { text.textContent = 'Ganesh is not on the desktop'; st.classList.add('off'); next.hidden = idle.hidden = foc.hidden = true; return; }
  const drift = Math.floor((Date.now() - statusAt) / 1000);
  const word = STATE_WORDS[status.state] || (status.state || 'idle').replace(/_/g, ' ');
  if (status.paused_reason === 'idle') { st.classList.add('idle'); text.innerHTML = 'Away · <b>' + fmtMin(((status.idle_seconds || 0) + drift) / 60) + '</b> without input'; }
  else { st.classList.add('on'); text.innerHTML = 'Live · <b>' + (status.visible ? word : 'hidden') + '</b>'; }
  if (status.quiet_mode) { next.hidden = false; next.innerHTML = 'Reminders <b>quiet</b>' + (status.snooze_seconds ? ' for ' + fmtClock(Math.max(0, status.snooze_seconds - drift)) : ''); }
  else if (status.next_reminder && status.next_reminder_in_seconds != null) { next.hidden = false; next.innerHTML = 'Next: <b>' + status.next_reminder + '</b> in ' + fmtClock(Math.max(0, status.next_reminder_in_seconds - drift)); }
  else next.hidden = true;
  idle.hidden = !(status.idle_seconds >= 10 && status.paused_reason !== 'idle');
  if (!idle.hidden) idle.innerHTML = 'No input for <b>' + fmtClock((status.idle_seconds || 0) + drift) + '</b>';
  foc.hidden = !status.focus_kind;
  if (!foc.hidden) foc.innerHTML = (status.focus_kind === 'focus' ? 'Focus' : 'Break') + ' · <b>' + fmtClock(Math.max(0, status.focus_left - drift)) + '</b> left';
}
setInterval(renderLiveStrip, 1000);

// ─── settings (schema-driven, saved live to the engine) ──────────────────
let settings = null;
const HOURS = Array.from({ length: 24 }, (_, h) => [h, h === 0 ? '12 am' : h < 12 ? h + ' am' : h === 12 ? '12 pm' : (h - 12) + ' pm']);
const SETTINGS_SCHEMA = [
  { title: 'Companion', eyebrow: 'BUDDY', rows: [
    { key: 'character', type: 'choice', label: 'Who sits on your desktop', options: [['custom', 'Ganesh'], ['dog', 'Puppy'], ['cat', 'Kitty'], ['human', 'Buddy']] },
    { key: 'pet_name', type: 'text', label: 'Name', hint: 'Used by Puppy, Kitty and Buddy', max: 18 },
    { key: 'scale', type: 'range', label: 'Size', min: 0.6, max: 1.8, step: 0.05, fmt: (v) => Math.round(v * 100) + '%' },
    { key: 'fps', type: 'number', label: 'Animation smoothness', min: 12, max: 60, unit: 'fps' },
    { key: 'speech', type: 'toggle', label: 'Speech bubbles' },
    { key: 'sounds', type: 'toggle', label: 'Gentle sounds' },
    { key: 'wander', type: 'toggle', label: 'Wander around the screen' },
    { key: 'wander_every', type: 'number', label: 'Wander every', min: 1, max: 60, unit: 'min', sub: 'wander' },
    { key: 'always_on_top', type: 'toggle', label: 'Always stay on top of other windows' },
    { key: 'autostart', type: 'toggle', label: 'Start automatically with Windows', hint: 'Adds DeskPal to your Startup folder' }
  ] },
  { title: 'Reminders', eyebrow: 'HEALTHY RHYTHM', rows: [
    { key: 'break_on', type: 'toggle', label: 'Remind me to take a break' },
    { key: 'break_every', type: 'number', label: 'After', min: 5, max: 240, unit: 'min of active work', sub: 'break_on' },
    { key: 'break_len', type: 'number', label: 'Break length', min: 1, max: 60, unit: 'min', sub: 'break_on' },
    { key: 'eye_on', type: 'toggle', label: 'Blink & eye rest', hint: '20-20-20 rule' },
    { key: 'eye_every', type: 'number', label: 'Every', min: 5, max: 180, unit: 'min', sub: 'eye_on' },
    { key: 'water_on', type: 'toggle', label: 'Drink a glass of water' },
    { key: 'water_every', type: 'number', label: 'Every', min: 10, max: 360, unit: 'min', sub: 'water_on' },
    { key: 'stretch_on', type: 'toggle', label: 'Stretch' },
    { key: 'stretch_every', type: 'number', label: 'Every', min: 10, max: 360, unit: 'min', sub: 'stretch_on' },
    { key: 'posture_on', type: 'toggle', label: 'Posture check' },
    { key: 'posture_every', type: 'number', label: 'Every', min: 5, max: 240, unit: 'min', sub: 'posture_on' },
    { key: 'hunger_on', type: 'toggle', label: 'Snack / food reminder' },
    { key: 'hunger_every', type: 'number', label: 'Every', min: 30, max: 480, unit: 'min', sub: 'hunger_on' },
    { key: 'meditate_on', type: 'toggle', label: 'Offer a breathing session' },
    { key: 'meditate_every', type: 'number', label: 'Every', min: 15, max: 720, unit: 'min', sub: 'meditate_on' },
    { key: 'breath_pattern', type: 'select', label: 'Breathing pattern', options: [['box', 'Box breathing 4-4-4-4'], ['478', 'Relaxing 4-7-8'], ['calm', 'Calm 5-5']], sub: 'meditate_on' },
    { key: 'breath_cycles', type: 'number', label: 'Cycles', min: 2, max: 30, unit: 'rounds', sub: 'meditate_on' },
    { key: 'dim_on_breathe', type: 'toggle', label: 'Dim the screen while breathing', sub: 'meditate_on' }
  ] },
  { title: 'Focus & quiet hours', eyebrow: 'POMODORO', rows: [
    { key: 'focus_len', type: 'number', label: 'Focus length', min: 5, max: 120, unit: 'min', hint: '25 / 5 is the classic Pomodoro split' },
    { key: 'focus_break', type: 'number', label: 'Break after focus', min: 1, max: 60, unit: 'min' },
    { key: 'quiet_on', type: 'toggle', label: 'Stay completely quiet during these hours' },
    { key: 'quiet_from', type: 'select', label: 'From', options: HOURS, sub: 'quiet_on' },
    { key: 'quiet_to', type: 'select', label: 'To', options: HOURS, sub: 'quiet_on' },
    { key: 'idle_pause', type: 'number', label: 'Pause reminders after', min: 1, max: 60, unit: 'min away', hint: 'Break timers count only real keyboard and mouse time' },
    { key: 'skip_fullscreen', type: 'toggle', label: 'Stay quiet during full-screen apps and games' },
    { key: 'greet_on', type: 'toggle', label: 'Say hello when I come back' }
  ] },
  { title: 'System & routine', eyebrow: 'MY DAY', rows: [
    { key: 'battery_on', type: 'toggle', label: 'Warn me about low battery' },
    { key: 'battery_low', type: 'number', label: 'Warn below', min: 5, max: 50, unit: '%', sub: 'battery_on' },
    { key: 'night_on', type: 'toggle', label: 'Nudge me when it gets late' },
    { key: 'night_hour', type: 'select', label: 'After', options: HOURS.filter(([h]) => h >= 18), sub: 'night_on' },
    { key: 'same_app_on', type: 'toggle', label: 'Notice when I stay in one app too long' },
    { key: 'same_app_mins', type: 'number', label: 'After', min: 15, max: 300, unit: 'min', sub: 'same_app_on' },
    { key: 'work_start_hour', type: 'select', label: 'Start work / wake up around', options: HOURS },
    { key: 'breakfast_on', type: 'toggle', label: 'Remind me about breakfast' },
    { key: 'breakfast_hour', type: 'select', label: 'Around', options: HOURS, sub: 'breakfast_on' },
    { key: 'lunch_on', type: 'toggle', label: 'Remind me about lunch' },
    { key: 'lunch_hour', type: 'select', label: 'Around', options: HOURS, sub: 'lunch_on' },
    { key: 'dinner_on', type: 'toggle', label: 'Remind me about dinner' },
    { key: 'dinner_hour', type: 'select', label: 'Around', options: HOURS, sub: 'dinner_on' },
    { key: 'work_end_hour', type: 'select', label: 'Finish work around', options: HOURS }
  ] }
];
const settingCtl = {};   // key -> { input, row, def, chip }
const saveTimers = {};
function buildSettings() {
  const grid = $('#settingsGrid');
  grid.innerHTML = '';
  SETTINGS_SCHEMA.forEach((group) => {
    const panel = document.createElement('article'); panel.className = 'panel';
    const head = document.createElement('div'); head.className = 'panel-head';
    head.innerHTML = '<div><p class="eyebrow"></p><h2></h2></div><span class="status-chip"></span>';
    head.querySelector('.eyebrow').textContent = group.eyebrow; head.querySelector('h2').textContent = group.title;
    const chip = head.querySelector('.status-chip');
    panel.appendChild(head);
    const rows = document.createElement('div'); rows.className = 'srows';
    group.rows.forEach((def) => {
      const row = document.createElement('div'); row.className = 'srow' + (def.sub ? ' sub' : '');
      const label = document.createElement('label'); label.textContent = def.label;
      if (def.hint) { const h = document.createElement('small'); h.textContent = def.hint; label.appendChild(h); }
      const ctl = document.createElement('div'); ctl.className = 'sctl';
      let input;
      const id = 'set-' + def.key;
      label.htmlFor = id;
      if (def.type === 'toggle') {
        const sw = document.createElement('span'); sw.className = 'switch';
        input = document.createElement('input'); input.type = 'checkbox'; input.id = id; input.setAttribute('role', 'switch');
        sw.appendChild(input); sw.appendChild(document.createElement('i')); ctl.appendChild(sw);
        input.onchange = () => saveSetting(def, input.checked, chip, panel);
      } else if (def.type === 'number') {
        input = document.createElement('input'); input.type = 'number'; input.id = id; input.min = def.min; input.max = def.max; input.step = 1;
        ctl.appendChild(input);
        if (def.unit) { const u = document.createElement('span'); u.className = 'unit'; u.textContent = def.unit; ctl.appendChild(u); }
        input.oninput = () => { const v = clampNum(input.value, def); if (v !== null) saveSetting(def, v, chip, panel, 500); };
        input.onblur = () => { const v = clampNum(input.value, def); if (v === null) input.value = settings ? settings[def.key] : def.min; else input.value = v; };
      } else if (def.type === 'range') {
        input = document.createElement('input'); input.type = 'range'; input.id = id; input.min = def.min; input.max = def.max; input.step = def.step;
        const val = document.createElement('span'); val.className = 'val';
        ctl.appendChild(input); ctl.appendChild(val);
        input.oninput = () => { val.textContent = def.fmt(parseFloat(input.value)); saveSetting(def, parseFloat(input.value), chip, panel, 250); };
        input._val = val;
      } else if (def.type === 'text') {
        input = document.createElement('input'); input.type = 'text'; input.id = id; input.maxLength = def.max || 40;
        ctl.appendChild(input);
        input.oninput = () => saveSetting(def, input.value.trim().slice(0, def.max || 40), chip, panel, 500);
      } else if (def.type === 'select') {
        input = document.createElement('select'); input.id = id;
        def.options.forEach(([v, t]) => { const o = document.createElement('option'); o.value = String(v); o.textContent = t; input.appendChild(o); });
        ctl.appendChild(input);
        input.onchange = () => saveSetting(def, /^\d+$/.test(input.value) ? parseInt(input.value, 10) : input.value, chip, panel);
      } else if (def.type === 'choice') {
        input = document.createElement('div'); input.className = 'seg'; input.id = id; input.setAttribute('role', 'radiogroup');
        def.options.forEach(([v, t]) => {
          const b = document.createElement('button'); b.type = 'button'; b.textContent = t; b.dataset.value = String(v); b.setAttribute('role', 'radio');
          b.onclick = () => { setChoice(input, String(v)); saveSetting(def, v, chip, panel); };
          input.appendChild(b);
        });
        ctl.appendChild(input);
      }
      row.appendChild(label); row.appendChild(ctl); rows.appendChild(row);
      settingCtl[def.key] = { input, row, def, chip };
    });
    panel.appendChild(rows);
    grid.appendChild(panel);
  });
}
function clampNum(raw, def) {
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return null;
  return Math.max(def.min, Math.min(def.max, n));
}
function setChoice(seg, value) {
  seg.querySelectorAll('button').forEach((b) => { const on = b.dataset.value === value; b.classList.toggle('active', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); });
}
function applyFullSettings(data) {
  if (!data || typeof data !== 'object') return;
  settings = data;
  const active = document.activeElement;
  Object.keys(settingCtl).forEach((key) => {
    const { input, def } = settingCtl[key];
    if (!(key in data)) return;
    if (input === active || (input.tagName === 'INPUT' && input.type === 'range' && input.matches(':active'))) return;
    const v = data[key];
    if (def.type === 'toggle') input.checked = !!v;
    else if (def.type === 'number') input.value = v;
    else if (def.type === 'range') { input.value = v; input._val.textContent = def.fmt(parseFloat(v)); }
    else if (def.type === 'text') input.value = v;
    else if (def.type === 'select') input.value = String(v);
    else if (def.type === 'choice') setChoice(input, String(v));
  });
  Object.keys(settingCtl).forEach((key) => {
    const { row, def } = settingCtl[key];
    if (def.sub) row.classList.toggle('disabled', !data[def.sub]);
  });
  if (data.version) {
    $('#aboutVersion').textContent = data.version;
    $('#sideVersion').textContent = data.version;
  }
  if (data.data_dir) $('#aboutPath').textContent = data.data_dir;
  applySettings(data);   // keeps the Health-page interval selects in sync
}
function saveSetting(def, value, chip, panel, delay) {
  clearTimeout(saveTimers[def.key]);
  const go = async () => {
    try {
      const res = await api('/api/settings', 'POST', { [def.key]: value });
      if (res && res.note) toast(res.note);
      applyFullSettings(res);
      chip.textContent = 'Saved ✓'; chip.className = 'status-chip on';
      panel.classList.add('saved');
      setTimeout(() => { if (chip.textContent === 'Saved ✓') { chip.textContent = ''; chip.className = 'status-chip'; } panel.classList.remove('saved'); }, 1800);
      flash('#settingsStatus', 'Live on the desktop', 'on');
    } catch (e) {
      chip.textContent = 'Launch Ganesh to save'; chip.className = 'status-chip warn';
    }
  };
  if (delay) saveTimers[def.key] = setTimeout(go, delay); else go();
}
async function loadSettings() {
  try { applyFullSettings(await api('/api/settings')); }
  catch (e) { /* engine offline — controls keep their last values */ }
}
buildSettings();

// ─── live pill ───────────────────────────────────────────────────────────
function renderLive() {
  const pill = $('#livePill'), text = $('#liveText'), launch = $('#launch');
  pill.className = 'live-pill';
  launch.disabled = isStarting;
  if (isStarting) { text.textContent = 'Starting Ganesh…'; return; }
  if (!status) { text.textContent = 'Launcher offline'; launch.textContent = 'Launch Ganesh'; return; }
  if (!status.running) { text.textContent = 'Ganesh not running'; launch.textContent = 'Launch Ganesh'; return; }
  launch.textContent = status.visible ? 'Ganesh is running' : 'Show Ganesh';
  if (status.paused_reason === 'idle') { pill.classList.add('idle'); text.textContent = 'Away · tracking idle'; return; }
  pill.classList.add('on'); text.textContent = 'Live · tracking active';
}

// ─── data loading ────────────────────────────────────────────────────────
function applyStats(data) {
  if (!data || typeof data !== 'object' || !data.today) return;
  stats = data;
  const f = data.focus_session;
  focusLocal = f ? { end: Date.now() + f.left * 1000, total: f.total, kind: f.kind, label: f.label } : null;
  renderAll();
}
async function loadStats() {
  try { applyStats(await api('/api/stats')); }
  catch (e) { /* desktop offline — status loop reports it */ }
}
async function loadStatus() {
  try {
    const data = await api('/api/status');
    status = data;
    desktopOnline = !!data.running;
    if (data.settings) applySettings(data.settings);
  } catch (e) { status = null; desktopOnline = false; focusLocal = null; }
  statusAt = Date.now();
  renderStatus();
}
function renderStatus() {
  renderLive(); renderNextReminder(); renderFocus(); renderGoals(); renderPresence(); renderLiveStrip();
}
function renderAll() {
  renderTiles(); renderNextReminder(); renderFocus(); renderGoals();
  const hist = (stats && stats.history) || [];
  drawActivity($('#activityChart'), (stats && stats.today && stats.today.hours) || []);
  drawBars($('#healthChart'), hist.length ? hist : emptyWeek(), ['water', 'eye', 'stretch', 'exercise'], [series(1), series(2), series(3), series(4)], ['Water', 'Eye rest', 'Stretch', 'Exercise']);
  drawBars($('#focusChart'), hist.length ? hist : emptyWeek(), ['focus'], [series(1)], ['Focus sessions']);
}
function emptyWeek() {
  const out = [];
  for (let i = 6; i >= 0; i--) { const d = new Date(); d.setDate(d.getDate() - i); out.push({ label: d.toLocaleDateString(undefined, { weekday: 'short' }) }); }
  return out;
}

// ─── scrollspy ───────────────────────────────────────────────────────────
(function initSpy() {
  const links = $$('#nav a');
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((en) => { if (en.isIntersecting) links.forEach((a) => a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id)); });
  }, { rootMargin: '-30% 0px -60% 0px' });
  $$('.section').forEach((s) => obs.observe(s));
})();

let resizeTimer = null;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 150); });

// ─── boot ────────────────────────────────────────────────────────────────
renderExercises();
renderAll();
loadStatus();
loadStats();
loadSettings();
setInterval(loadStatus, 1000);        // real-time: state, countdowns, idle
setInterval(loadStats, 5000);
setInterval(loadSettings, 10000);     // picks up changes made from the desktop menu
document.addEventListener('visibilitychange', () => { if (!document.hidden) { loadStatus(); loadStats(); loadSettings(); } });
if (location.hash) { const target = document.querySelector(location.hash); if (target) setTimeout(() => target.scrollIntoView({ block: 'start' }), 60); }
