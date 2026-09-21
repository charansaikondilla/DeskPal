'use strict';

// --------------------------------------------------------------------------
// DeskPal app — live productivity + health hub (no external libraries)
//
// Data flow: the desktop engine (deskpal.py) is the single source of truth.
//   /api/status   every second  → live state, per-reminder countdowns
//   /api/stats    every 5 s     → today's counters, 7-day history, targets,
//                                 goals, custom reminders
//   /api/settings every 10 s    → every user setting (also on each save)
// Nothing shown here is mocked; when the engine is offline the UI says so.
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
function h(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
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
function fmtEvery(min) {
  min = Number(min) || 0;
  if (min < 60) return 'every ' + min + ' min';
  if (min % 60 === 0) return 'every ' + (min / 60) + (min === 60 ? ' hour' : ' hours');
  return 'every ' + (min / 60).toFixed(1).replace(/\.0$/, '') + ' hours';
}
function todayISO() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function hourLabel(hh) { return hh === 0 ? '12 am' : hh < 12 ? hh + ' am' : hh === 12 ? '12 pm' : (hh - 12) + ' pm'; }

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

// ─── state ───────────────────────────────────────────────────────────────
let stats = null;
let status = null;
let settings = null;
let focusLocal = null;   // { end: epoch ms, total: sec, kind, label }
let desktopOnline = false;
let isStarting = false;
let statusAt = 0;        // when `status` was fetched — countdowns drift from it

// ─── theme & accent (per-device conveniences, kept in localStorage) ──────
const ACCENTS = [['indigo', '#4f5bd5'], ['ocean', '#2a78d6'], ['forest', '#158f66'], ['sunset', '#e0653a'], ['plum', '#8b4fd6'], ['graphite', '#344054']];
function storageGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function storageSet(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } }
function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === 'light' || mode === 'dark') root.dataset.theme = mode; else delete root.dataset.theme;
  storageSet('deskpal-theme', mode || 'system');
  setChoice($('#themeSeg'), mode || 'system');
  renderAll();
}
function applyAccent(name) {
  if (!ACCENTS.some(([n]) => n === name)) name = 'indigo';
  document.documentElement.dataset.accent = name;
  storageSet('deskpal-accent', name);
  $$('#accentSwatches button').forEach((b) => b.classList.toggle('active', b.dataset.value === name));
  renderAll();
}
(function initTheme() {
  const saved = storageGet('deskpal-theme');
  const root = document.documentElement;
  if (saved === 'dark' || saved === 'light') root.dataset.theme = saved;
  const accent = storageGet('deskpal-accent') || 'indigo';
  root.dataset.accent = ACCENTS.some(([n]) => n === accent) ? accent : 'indigo';
  const sw = $('#accentSwatches');
  ACCENTS.forEach(([name, color]) => {
    const b = h('button'); b.type = 'button'; b.dataset.value = name; b.title = name[0].toUpperCase() + name.slice(1);
    b.style.setProperty('--c', color); b.setAttribute('role', 'radio');
    b.classList.toggle('active', name === root.dataset.accent);
    b.onclick = () => applyAccent(name);
    sw.appendChild(b);
  });
  $$('#themeSeg button').forEach((b) => { b.onclick = () => applyTheme(b.dataset.value); });
  setChoice($('#themeSeg'), (saved === 'dark' || saved === 'light') ? saved : 'system');
  $('#themeToggle').onclick = () => {
    const osDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = root.dataset.theme === 'dark' || (!root.dataset.theme && osDark);
    applyTheme(isDark ? 'light' : 'dark');
  };
})();

// ─── greeting ────────────────────────────────────────────────────────────
(function initGreeting() {
  const hr = new Date().getHours();
  const word = hr < 5 ? 'Still up?' : hr < 12 ? 'Good morning.' : hr < 17 ? 'Good afternoon.' : hr < 21 ? 'Good evening.' : 'Winding down.';
  $('#greeting').textContent = word;
  $('#dateLine').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
})();

// ─── router: one page at a time, hash-addressable, keys 1-6 ─────────────
const VIEWS = ['today', 'focus', 'health', 'goals', 'companion', 'settings'];
const VIEW_SUBS = {
  today: 'Live focus, movement and reminders — everything DeskPal tracks for you, in one place.',
  focus: 'Run a focus session on the desktop. Ganesh keeps quiet until the timer ends.',
  health: 'Every reminder, target and message is yours to change — and it goes live on the desktop instantly.',
  goals: 'Small daily promises to yourself, with streaks that only count real ticks.',
  companion: 'Play with Ganesh, move him around, or ask for some quiet.',
  settings: 'Companion, reminders, focus, quiet hours and your routine — all saved live to DeskPal.'
};
function showView(name, push) {
  if (!VIEWS.includes(name)) name = 'today';
  document.body.dataset.view = name;
  $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === name));
  $$('#nav a').forEach((a) => { const on = a.dataset.view === name; a.classList.toggle('active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  $('#pageSub').textContent = VIEW_SUBS[name];
  if (push !== false && location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
  window.scrollTo({ top: 0, behavior: 'auto' });
  renderAll();   // charts size to their (now visible) containers
}
$$('#nav a').forEach((a) => { a.onclick = (ev) => { ev.preventDefault(); showView(a.dataset.view); }; });
$$('[data-goto]').forEach((t) => { t.onclick = () => showView(t.dataset.goto); });
window.addEventListener('hashchange', () => showView(location.hash.slice(1), false));
document.addEventListener('keydown', (ev) => {
  if (ev.target.matches('input, select, textarea') || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const n = parseInt(ev.key, 10);
  if (n >= 1 && n <= VIEWS.length) showView(VIEWS[n - 1]);
});

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
  if (!container.clientWidth) return;                       // page not visible
  const pad = { l: 34, r: 12, t: 12, b: 26 };
  const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H });
  const x = (hh) => pad.l + (hh / 23) * (W - pad.l - pad.r);
  const y = (m) => pad.t + (1 - Math.min(60, m) / 60) * (H - pad.t - pad.b);

  [0, 15, 30, 45, 60].forEach((m) => {
    svg.appendChild(el('line', { class: m === 0 ? 'axis' : 'grid', x1: pad.l, x2: W - pad.r, y1: y(m), y2: y(m) }));
    svg.appendChild(el('text', { x: pad.l - 8, y: y(m) + 4, 'text-anchor': 'end' }, String(m)));
  });
  for (let hh = 0; hh <= 23; hh += 3) {
    svg.appendChild(el('text', { x: x(hh), y: H - 8, 'text-anchor': 'middle' }, hh === 0 ? '12am' : hh < 12 ? hh + 'am' : hh === 12 ? '12pm' : (hh - 12) + 'pm'));
  }

  const data = (hours || []).filter((d) => typeof d.h === 'number');
  if (!data.length) {
    svg.appendChild(el('text', { class: 'empty', x: W / 2, y: H / 2 }, 'No activity recorded yet — keep DeskPal running.'));
    container.appendChild(svg);
    return;
  }

  const build = (key, color) => {
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
    const hh = Math.round(((ev.clientX - rect.left) * (W / rect.width) - pad.l) / (W - pad.l - pad.r) * 23);
    const d = data.find((p) => p.h === hh);
    if (!d) { hideHover(); return; }
    cross.setAttribute('x1', x(hh)); cross.setAttribute('x2', x(hh));
    dotA.setAttribute('cx', x(hh)); dotA.setAttribute('cy', y(d.active || 0));
    dotI.setAttribute('cx', x(hh)); dotI.setAttribute('cy', y(d.idle || 0));
    [cross, dotA, dotI].forEach((n) => n.setAttribute('visibility', 'visible'));
    showTip('<b>' + hourLabel(hh) + '</b><br>Active ' + (d.active || 0) + ' min · Idle ' + (d.idle || 0) + ' min',
      rect.left + x(hh) * (rect.width / W), rect.top + y(Math.max(d.active || 0, d.idle || 0)) * (rect.height / H));
  });
  hit.addEventListener('mouseleave', hideHover);
  svg.appendChild(hit);
  container.appendChild(svg);
}

// ─── chart: grouped bars ─────────────────────────────────────────────────
function drawBars(container, days, keys, colors, names, opts) {
  container.innerHTML = '';
  const W = container.clientWidth || 800, H = container.clientHeight || 220;
  if (!container.clientWidth) return;
  opts = opts || {};
  const pad = { l: 34, r: 8, t: 12, b: 26 };
  const svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H });
  const max = Math.max(opts.min || 4, ...days.flatMap((d) => keys.map((k) => d[k] || 0)));
  const step = max <= 8 ? 2 : max <= 20 ? 5 : max <= 60 ? 10 : max <= 240 ? 60 : 120;
  const top = Math.ceil(max / step) * step;
  const y = (v) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  const fmt = opts.fmt || ((v) => String(v));
  for (let v = 0; v <= top; v += step) {
    svg.appendChild(el('line', { class: v === 0 ? 'axis' : 'grid', x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
    svg.appendChild(el('text', { x: pad.l - 8, y: y(v) + 4, 'text-anchor': 'end' }, fmt(v)));
  }
  if (opts.target && opts.target <= top) {   // only when it fits on the scale
    svg.appendChild(el('line', { class: 'today-bar', x1: pad.l, x2: W - pad.r, y1: y(Math.min(top, opts.target)), y2: y(Math.min(top, opts.target)), 'stroke-dasharray': '4 4' }));
  }
  const groupW = (W - pad.l - pad.r) / days.length;
  const inner = groupW * 0.68;
  const barW = inner / keys.length;
  days.forEach((d, i) => {
    const gx = pad.l + i * groupW + (groupW - inner) / 2;
    svg.appendChild(el('text', { x: pad.l + i * groupW + groupW / 2, y: H - 8, 'text-anchor': 'middle', 'font-weight': i === days.length - 1 ? '600' : '400' }, d.label));
    keys.forEach((k, j) => {
      const v = d[k] || 0;
      const bx = gx + j * barW + 1;
      const bh = Math.max(0, y(0) - y(v));
      const bar = el('rect', { class: 'bar', x: bx, y: y(v), width: Math.max(1, barW - 2), height: v ? Math.max(3, bh) : 0, fill: colors[j] });
      const hit = el('rect', { class: 'hit', x: bx - 1, y: pad.t, width: barW, height: H - pad.t - pad.b });
      hit.addEventListener('mousemove', () => {
        const rect = container.getBoundingClientRect();
        showTip('<b>' + d.label + '</b><br>' + names[j] + ': ' + fmt(v), rect.left + (bx + barW / 2) * (rect.width / W), rect.top + y(v) * (rect.height / H));
        bar.style.opacity = '0.8';
      });
      hit.addEventListener('mouseleave', () => { hideTip(); bar.style.opacity = ''; });
      svg.appendChild(bar); svg.appendChild(hit);
    });
  });
  container.appendChild(svg);
}

// ─── health rings (Today) ────────────────────────────────────────────────
const RING_ITEMS = [
  { key: 'water', label: 'Water', color: 1 }, { key: 'eye', label: 'Eye rest', color: 2 },
  { key: 'stretch', label: 'Stretch', color: 3 }, { key: 'posture', label: 'Posture', color: 5 }
];
function drawRings() {
  const box = $('#rings'), legend = $('#ringsLegend');
  const t = (stats && stats.today) || {}, targets = (stats && stats.targets) || {};
  box.innerHTML = ''; legend.innerHTML = '';
  const size = 168, stroke = 13, gap = 4;
  const svg = el('svg', { viewBox: '0 0 ' + size + ' ' + size });
  RING_ITEMS.forEach((item, i) => {
    const r = size / 2 - stroke / 2 - i * (stroke + gap) - 2;
    const circ = 2 * Math.PI * r;
    const target = targets[item.key] || 0, value = t[item.key] || 0;
    const pct = target ? Math.min(1, value / target) : 0;
    const color = series(item.color);
    svg.appendChild(el('circle', { class: 'track', cx: size / 2, cy: size / 2, r, 'stroke-width': stroke }));
    svg.appendChild(el('circle', { class: 'fill', cx: size / 2, cy: size / 2, r, 'stroke-width': stroke, stroke: color,
      'stroke-dasharray': circ.toFixed(2), 'stroke-dashoffset': (circ * (1 - pct)).toFixed(2), opacity: pct ? 1 : 0.35 }));
    const row = h('div');
    const dot = h('i'); dot.style.setProperty('--c', color);
    row.appendChild(dot);
    row.appendChild(h('span', '', item.label));
    const b = h('b', '', value + ' / ' + (target || '–'));
    row.appendChild(b);
    if (pct >= 1) { const ok = h('small', '', ' ✓'); ok.style.color = 'var(--good-text)'; row.appendChild(ok); }
    legend.appendChild(row);
  });
  box.appendChild(svg);
  const closed = RING_ITEMS.filter((it) => targets[it.key] && (t[it.key] || 0) >= targets[it.key]).length;
  $('#ringsHint').textContent = !desktopOnline ? 'Launch Ganesh to start counting today\'s check-ins.'
    : closed === RING_ITEMS.length ? 'All four rings closed. That is a properly looked-after day.'
    : closed ? closed + ' of 4 rings closed so far — keep going.' : 'Targets live on the Health page — set them to match your day.';
}

// ─── tiles (Today) ───────────────────────────────────────────────────────
function setBar(id, pct) {
  const bar = $(id); bar.style.setProperty('--p', Math.max(0, Math.min(1, pct)).toFixed(3)); bar.classList.toggle('done', pct >= 1);
}
function renderTiles() {
  const t = (stats && stats.today) || {}, targets = (stats && stats.targets) || {};
  const active = t.active_min || 0, idle = t.idle_min || 0;
  $('#tActive').textContent = fmtMin(active);
  const aT = targets.active || 0;
  setBar('#tActiveBar', aT ? active / aT : 0);
  $('#tActiveFoot').textContent = aT ? (active >= aT ? 'daily goal of ' + fmtMin(aT) + ' reached' : fmtMin(aT - active) + ' to your ' + fmtMin(aT) + ' goal')
    + (active + idle ? ' · ' + Math.round(active / (active + idle) * 100) + '% active' : '') : 'nothing recorded yet';
  const focus = t.focus || 0, fT = targets.focus || 0;
  $('#tFocus').textContent = String(focus);
  setBar('#tFocusBar', fT ? focus / fT : 0);
  $('#tFocusFoot').textContent = (fT ? 'of ' + fT + ' planned · ' : '') + (t.breaks || 0) + (t.breaks === 1 ? ' break taken' : ' breaks taken');
  const hv = RING_ITEMS.reduce((n, it) => n + (t[it.key] || 0), 0), hT = RING_ITEMS.reduce((n, it) => n + (targets[it.key] || 0), 0);
  $('#tHealth').textContent = String(hv);
  setBar('#tHealthBar', hT ? hv / hT : 0);
  $('#tHealthFoot').textContent = hT ? 'of ' + hT + ' today · water, eyes, stretch, posture' : 'water · eyes · stretch · posture';
  renderNextReminder();
  // today's log
  const log = $('#todayLog'); log.innerHTML = '';
  [['Breaks', t.breaks, 'breaks'], ['Water', t.water, 'glasses'], ['Eye rests', t.eye, 'done'], ['Stretches', t.stretch, 'done'],
   ['Posture fixes', t.posture, 'done'], ['Exercises', t.exercise, 'done'], ['Breathing', t.breath, (t.breath_min || 0) + ' min'], ['Snacks', t.hunger, 'logged'], ['Pets', t.pets, 'for Ganesh']]
    .forEach(([name, v, unit]) => { const d = h('div'); d.appendChild(h('b', '', String(v || 0))); d.appendChild(h('span', '', name + ' · ' + unit)); log.appendChild(d); });
  const tot = (stats && stats.totals) || {};
  $('#allTimeLine').textContent = stats && stats.days_tracked ? 'All time: ' + fmtMin(tot.active_min || 0) + ' active over ' + stats.days_tracked + (stats.days_tracked === 1 ? ' day' : ' days') + ' · '
    + (tot.focus || 0) + ' focus sessions · ' + (tot.water || 0) + ' glasses of water · ' + (tot.breaks || 0) + ' breaks.' : '';
}
function renderNextReminder() {
  const next = $('#tNext'), foot = $('#tNextFoot');
  const drift = Math.floor((Date.now() - statusAt) / 1000);
  if (!status || !status.running) { next.textContent = '—'; foot.textContent = desktopOnline ? 'DeskPal is hidden' : 'launch Ganesh to start reminders'; setBar('#tNextBar', 0); return; }
  if (status.quiet_mode) { next.textContent = 'Quiet'; foot.textContent = 'reminders snoozed'; setBar('#tNextBar', 0); return; }
  if (status.paused_reason === 'idle') { next.textContent = 'Paused'; foot.textContent = 'you are away from the PC'; setBar('#tNextBar', 0); return; }
  if (status.work_hours === false && settings && settings.work_hours_only) { next.textContent = 'Off hours'; foot.textContent = 'outside your work hours'; setBar('#tNextBar', 0); return; }
  if (status.next_reminder && status.next_reminder_in_seconds != null) {
    next.textContent = status.next_reminder;
    const s = Math.max(0, status.next_reminder_in_seconds - drift);
    foot.textContent = s >= 60 ? 'in ' + fmtClock(s) : 'in under a minute';
    const rem = (status.reminders || []).find((r) => r.name === status.next_reminder);
    setBar('#tNextBar', rem && rem.every ? 1 - s / (rem.every * 60) : 0);
    return;
  }
  next.textContent = '—'; foot.textContent = 'no reminders scheduled'; setBar('#tNextBar', 0);
}

// ─── focus ───────────────────────────────────────────────────────────────
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
function renderFocusStats() {
  const t = (stats && stats.today) || {}, hist = (stats && stats.history) || [], tot = (stats && stats.totals) || {};
  const week = hist.reduce((n, d) => n + (d.focus || 0), 0);
  const best = hist.reduce((b, d) => (d.focus || 0) > (b.focus || 0) ? d : b, { focus: 0 });
  const box = $('#focusStats'); box.innerHTML = '';
  [[String(t.focus || 0), 'sessions today'], [String(week), 'this week'], [best.focus ? best.focus + ' · ' + best.label : '—', 'best day this week'],
   [String(tot.focus || 0), 'all time'], [String(stats && stats.streaks ? stats.streaks.focus || 0 : 0), 'day streak'], [fmtMin(t.active_min || 0), 'active today']]
    .forEach(([v, name]) => { const d = h('div'); d.appendChild(h('b', '', v)); d.appendChild(h('span', '', name)); box.appendChild(d); });
  $$('#focusPresets .preset').forEach((b) => b.classList.toggle('active', settings && String(settings.focus_len) === b.dataset.focus && String(settings.focus_break) === b.dataset.break));
}
$$('#focusPresets .preset').forEach((b) => {
  b.onclick = async () => {
    $('#focusMinutes').value = b.dataset.focus;
    renderFocus();
    try { applyFullSettings(await api('/api/settings', 'POST', { focus_len: parseInt(b.dataset.focus, 10), focus_break: parseInt(b.dataset.break, 10) })); toast(b.dataset.focus + ' minutes of focus, then a ' + b.dataset.break + ' minute break — saved as your default.'); }
    catch (e) { $('#focusHint').textContent = 'Launch Ganesh to save presets.'; }
    renderFocusStats();
  };
});
$('#focusMinutes').oninput = renderFocus;
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
  const fragment = document.createDocumentFragment();
  goals.forEach((g) => {
    const row = h('div', 'item' + (g.done_today ? ' done' : ''));
    const text = h('div');
    const name = h('strong', '', g.name);
    if (g.streak > 0) name.appendChild(h('span', 'streak-badge', g.streak + (g.streak === 1 ? ' day' : ' days')));
    if (Array.isArray(g.week)) {
      const dots = h('span', 'week-dots'); dots.title = 'Last 7 days';
      g.week.forEach((v, i) => dots.appendChild(h('i', (v ? 'on' : '') + (i === g.week.length - 1 ? ' today' : ''))));
      name.appendChild(dots);
    }
    text.appendChild(name); text.appendChild(h('small', '', g.done_today ? 'Done today' : 'Not done yet today'));
    const actions = h('div', 'item-actions');
    const toggle = h('button', 'btn ' + (g.done_today ? 'done-btn' : 'ghost'), g.done_today ? 'Done ✓' : 'Mark done');
    toggle.onclick = async () => { try { applyStats(await api('/api/goals', 'POST', { action: 'toggle', id: g.id })); } catch (e) { flash('#goalStatus', 'Could not save', 'warn'); } };
    const del = h('button', 'btn ghost del', '×'); del.title = 'Remove goal';
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
  const chip = $(sel); if (!chip) return;
  chip.textContent = text; chip.className = 'status-chip ' + (cls || '');
  setTimeout(() => { if (chip.textContent === text) { chip.textContent = ''; chip.className = 'status-chip'; } }, 2500);
}

// ─── exercises (local list, completions counted by DeskPal) ──────────────
const defaultExercises = [
  { name: 'Desk stretch', minutes: 2 }, { name: 'Shoulder rolls', minutes: 2 }, { name: 'Short walk', minutes: 5 }
];
function loadExercises() {
  const today = todayISO();
  try {
    const parsed = JSON.parse(storageGet('deskpal-exercises') || 'null');
    if (!Array.isArray(parsed) || !parsed.length) throw new Error('empty');
    return parsed.map((x) => ({
      name: typeof x.name === 'string' && x.name.trim() ? x.name.trim().slice(0, 40) : 'Exercise',
      minutes: Number.isFinite(x.minutes) && x.minutes > 0 ? Math.min(120, Math.round(x.minutes)) : 2,
      doneDate: x.doneDate === today ? today : ''
    }));
  } catch (e) { return defaultExercises.map((x) => ({ ...x, doneDate: '' })); }
}
let exercises = loadExercises();
function saveExercises() { storageSet('deskpal-exercises', JSON.stringify(exercises)); }
function renderExercises() {
  const list = $('#exerciseList');
  list.innerHTML = '';
  const today = todayISO();
  exercises.forEach((x, i) => {
    const done = x.doneDate === today;
    const row = h('div', 'item' + (done ? ' done' : ''));
    const text = h('div');
    text.appendChild(h('strong', '', x.name)); text.appendChild(h('small', '', x.minutes + ' min' + (done ? ' · done today' : '')));
    const actions = h('div', 'item-actions');
    const btn = h('button', 'btn ' + (done ? 'done-btn' : 'ghost'), done ? 'Done ✓' : 'Mark done');
    btn.onclick = async () => {
      x.doneDate = done ? '' : today;
      saveExercises(); renderExercises();
      if (!done && desktopOnline) { try { applyStats(await api('/api/exercise_done', 'POST')); } catch (e) { /* counted locally only */ } }
    };
    const del = h('button', 'btn ghost del', '×'); del.title = 'Remove exercise';
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
      if (res && res.app) { status = res; statusAt = Date.now(); desktopOnline = !!res.running; renderStatus(); }
      const label = btn.textContent.trim();
      flash(chip, action === 'scene' ? 'Scene starting on the desktop' : label + ' ✓', 'on');
      if (action === 'reset_timers') toast('Reminder timers reset — every reminder starts counting from now.');
      if (action === 'scene' && res && res.scene_error) toast(res.scene_error);
    } catch (e) { flash(chip, 'Launch Ganesh first', 'warn'); }
  };
});
$('#resetAll').onclick = async () => {
  if (!await confirmDialog('Reset everything?', 'Every setting goes back to its default. Your goals, custom reminders and daily history are kept.', 'Reset')) return;
  try { const res = await runAction('reset_all'); await loadSettings(); flash('#aboutStatus', 'Defaults restored', 'on'); toast('All settings are back to their defaults.'); if (res && res.app) { status = res; statusAt = Date.now(); renderStatus(); } }
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
const miniImg = document.createElement('img');
miniImg.alt = '';
miniImg.onerror = () => { miniImg.src = 'assets/ganesh/ganesh_stand.png'; };
$('#presenceMiniAvatar').appendChild(miniImg);
let frameTick = 0;
function renderPresence() {
  const box = $('#presence'), state = $('#presenceState'), foot = $('#presenceFoot');
  const mini = $('#presenceMini'), miniState = $('#presenceMiniState'), miniFoot = $('#presenceMiniFoot');
  const online = desktopOnline && status && status.running;
  box.classList.toggle('on', !!online); mini.classList.toggle('on', !!online);
  if (!online) {
    state.textContent = 'Offline'; foot.textContent = 'Launch Ganesh to see the live state.';
    miniState.textContent = 'Offline'; miniFoot.textContent = 'Launch Ganesh';
    avatarImg.src = miniImg.src = 'assets/ganesh/ganesh_stand.png';
    return;
  }
  const name = status.character === 'custom' ? 'Ganesh' : (status.pet_name || 'Buddy');
  const word = STATE_WORDS[status.state] || (status.state || 'idle').replace(/_/g, ' ');
  state.textContent = status.visible ? name + ' · ' + word : name + ' is hidden';
  miniState.textContent = name; miniFoot.textContent = status.visible ? word : 'hidden';
  const bits = [];
  if (status.scene) bits.push('Scene: ' + status.scene.replace(/_/g, ' '));
  if (status.hidden_seconds) bits.push('back in ' + fmtClock(status.hidden_seconds));
  if (status.snooze_seconds) bits.push('quiet for ' + fmtClock(status.snooze_seconds));
  if (status.idle_seconds >= 60) bits.push('you have been away ' + fmtMin(status.idle_seconds / 60));
  if (status.uptime_seconds != null) bits.push('running for ' + fmtMin(status.uptime_seconds / 60));
  foot.textContent = bits.join(' · ') || 'Live on your desktop right now.';
  const frames = status.visible ? FRAMES[status.state] : null;
  const wanted = 'assets/ganesh/' + (frames ? frames[frameTick % frames.length] : 'ganesh_stand') + '.png';
  if (!avatarImg.src.endsWith(wanted)) avatarImg.src = miniImg.src = wanted;
  $$('.emote-grid .btn').forEach((b) => b.classList.toggle('playing', status.visible && EMOTE_STATE[b.dataset.emote] === status.state || b.dataset.emote === status.state));
}
setInterval(() => { frameTick++; if (status && FRAMES[status.state]) renderPresence(); }, 140);

// ─── live strip (header) ─────────────────────────────────────────────────
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
setInterval(() => { renderLiveStrip(); renderNextReminder(); renderReminderLive(); }, 1000);

// ─── settings engine: schema-driven controls, saved live to the engine ───
// Several controls may bind to one key (Health cards + Settings page), so
// the registry keeps a list per key and every control follows the engine.
const HOURS = Array.from({ length: 24 }, (_, hh) => [hh, hourLabel(hh)]);
const settingCtl = {};   // key -> [{ input, row, def, chip, panel }]
const saveTimers = {};
function registerCtl(def, entry) { (settingCtl[def.key] = settingCtl[def.key] || []).push(entry); }
function createControl(def, chip, panel, idPrefix) {
  const ctl = h('div', 'sctl');
  const id = (idPrefix || 'set-') + def.key;
  let input;
  if (def.type === 'toggle') {
    const sw = h('label', 'switch');
    input = h('input'); input.type = 'checkbox'; input.id = id; input.setAttribute('role', 'switch');
    sw.appendChild(input); sw.appendChild(h('i')); ctl.appendChild(sw);
    input.onchange = () => saveSetting(def, input.checked, chip, panel);
  } else if (def.type === 'number') {
    input = h('input'); input.type = 'number'; input.id = id; input.min = def.min; input.max = def.max; input.step = 1;
    ctl.appendChild(input);
    if (def.unit) ctl.appendChild(h('span', 'unit', def.unit));
    input.oninput = () => { const v = clampNum(input.value, def); if (v !== null) saveSetting(def, v, chip, panel, 500); };
    input.onblur = () => { const v = clampNum(input.value, def); if (v === null) input.value = settings ? settings[def.key] : def.min; else input.value = v; };
  } else if (def.type === 'range') {
    input = h('input'); input.type = 'range'; input.id = id; input.min = def.min; input.max = def.max; input.step = def.step;
    const val = h('span', 'val');
    ctl.appendChild(input); ctl.appendChild(val);
    input.oninput = () => { val.textContent = def.fmt(parseFloat(input.value)); saveSetting(def, parseFloat(input.value), chip, panel, 250); };
    input._val = val;
  } else if (def.type === 'text') {
    input = h('input'); input.type = 'text'; input.id = id; input.maxLength = def.max || 40;
    if (def.placeholder) input.placeholder = def.placeholder;
    ctl.appendChild(input);
    input.oninput = () => saveSetting(def, input.value.trim().slice(0, def.max || 40), chip, panel, 600);
  } else if (def.type === 'select') {
    input = h('select'); input.id = id;
    def.options.forEach(([v, t]) => { const o = h('option', '', t); o.value = String(v); input.appendChild(o); });
    ctl.appendChild(input);
    input.onchange = () => saveSetting(def, /^\d+$/.test(input.value) ? parseInt(input.value, 10) : input.value, chip, panel);
  } else if (def.type === 'choice') {
    input = h('div', 'seg'); input.id = id; input.setAttribute('role', 'radiogroup');
    def.options.forEach(([v, t]) => {
      const b = h('button', '', t); b.type = 'button'; b.dataset.value = String(v); b.setAttribute('role', 'radio');
      b.onclick = () => { setChoice(input, String(v)); saveSetting(def, v, chip, panel); };
      input.appendChild(b);
    });
    ctl.appendChild(input);
  }
  return { input, ctl };
}
function buildRows(container, defs, chip, panel, idPrefix) {
  defs.forEach((def) => {
    const row = h('div', 'srow' + (def.sub ? ' sub' : ''));
    const label = h('label', '', def.label);
    if (def.hint) label.appendChild(h('small', '', def.hint));
    const { input, ctl } = createControl(def, chip, panel, idPrefix);
    label.htmlFor = input.id;
    row.appendChild(label); row.appendChild(ctl); container.appendChild(row);
    row.dataset.search = (def.label + ' ' + (def.hint || '') + ' ' + def.key.replace(/_/g, ' ')).toLowerCase();
    registerCtl(def, { input, row, def, chip, panel });
  });
}
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
    { key: 'focus_target', type: 'number', label: 'Focus sessions per day', min: 1, max: 20, unit: 'sessions', hint: 'Shown as progress on the Today page' },
    { key: 'active_target', type: 'number', label: 'Active desk time per day', min: 30, max: 900, unit: 'min' },
    { key: 'quiet_on', type: 'toggle', label: 'Stay completely quiet during these hours' },
    { key: 'quiet_from', type: 'select', label: 'From', options: HOURS, sub: 'quiet_on' },
    { key: 'quiet_to', type: 'select', label: 'To', options: HOURS, sub: 'quiet_on' },
    { key: 'work_hours_only', type: 'toggle', label: 'Only remind me during work hours', hint: 'Uses the start and finish times below' },
    { key: 'idle_pause', type: 'number', label: 'Pause reminders after', min: 1, max: 60, unit: 'min away', hint: 'Break timers count only real keyboard and mouse time' },
    { key: 'skip_fullscreen', type: 'toggle', label: 'Stay quiet during full-screen apps and games' },
    { key: 'greet_on', type: 'toggle', label: 'Say hello when I come back' }
  ] },
  { title: 'System & routine', eyebrow: 'MY DAY', rows: [
    { key: 'battery_on', type: 'toggle', label: 'Warn me about low battery' },
    { key: 'battery_low', type: 'number', label: 'Warn below', min: 5, max: 50, unit: '%', sub: 'battery_on' },
    { key: 'night_on', type: 'toggle', label: 'Nudge me when it gets late' },
    { key: 'night_hour', type: 'select', label: 'After', options: HOURS.filter(([hh]) => hh >= 18), sub: 'night_on' },
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
function buildSettings() {
  const grid = $('#settingsGrid');
  grid.innerHTML = '';
  SETTINGS_SCHEMA.forEach((group) => {
    const panel = h('article', 'panel');
    const head = h('div', 'panel-head');
    head.innerHTML = '<div><p class="eyebrow"></p><h2></h2></div><span class="status-chip"></span>';
    head.querySelector('.eyebrow').textContent = group.eyebrow; head.querySelector('h2').textContent = group.title;
    const chip = head.querySelector('.status-chip');
    panel.appendChild(head);
    const rows = h('div', 'srows');
    buildRows(rows, group.rows, chip, panel, 'set-');
    panel.appendChild(rows);
    grid.appendChild(panel);
  });
}
$('#settingsSearch').oninput = () => {
  const q = $('#settingsSearch').value.trim().toLowerCase();
  $$('#settingsGrid .panel').forEach((panel) => {
    let any = false;
    panel.querySelectorAll('.srow').forEach((row) => { const hit = !q || row.dataset.search.includes(q); row.classList.toggle('hidden', !hit); if (hit) any = true; });
    panel.classList.toggle('hidden', !any);
  });
};
function clampNum(raw, def) {
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return null;
  return Math.max(def.min, Math.min(def.max, n));
}
function setChoice(seg, value) {
  if (!seg) return;
  seg.querySelectorAll('button').forEach((b) => { const on = b.dataset.value === value; b.classList.toggle('active', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); });
}
function applyFullSettings(data) {
  if (!data || typeof data !== 'object') return;
  settings = data;
  const active = document.activeElement;
  Object.keys(settingCtl).forEach((key) => {
    if (!(key in data)) return;
    settingCtl[key].forEach(({ input, def }) => {
      if (input === active || (input.tagName === 'INPUT' && input.type === 'range' && input.matches(':active'))) return;
      const v = data[key];
      if (def.type === 'toggle') input.checked = !!v;
      else if (def.type === 'number') input.value = v;
      else if (def.type === 'range') { input.value = v; input._val.textContent = def.fmt(parseFloat(v)); }
      else if (def.type === 'text') input.value = v;
      else if (def.type === 'select') input.value = String(v);
      else if (def.type === 'choice') setChoice(input, String(v));
    });
  });
  Object.keys(settingCtl).forEach((key) => {
    settingCtl[key].forEach(({ row, def }) => { if (def.sub && row) row.classList.toggle('disabled', !data[def.sub]); });
  });
  if (data.version) { $('#aboutVersion').textContent = data.version; $('#sideVersion').textContent = data.version; }
  if (data.data_dir) $('#aboutPath').textContent = data.data_dir;
  renderReminderCards();
  renderFocusStats();
}
function saveSetting(def, value, chip, panel, delay) {
  clearTimeout(saveTimers[def.key]);
  const go = async () => {
    try {
      const res = await api('/api/settings', 'POST', { [def.key]: value });
      if (res && res.note) toast(res.note);
      applyFullSettings(res);
      if (chip) { chip.textContent = 'Saved ✓'; chip.className = 'status-chip on'; }
      if (panel) panel.classList.add('saved');
      setTimeout(() => { if (chip && chip.textContent === 'Saved ✓') { chip.textContent = ''; chip.className = 'status-chip'; } if (panel) panel.classList.remove('saved'); }, 1800);
      flash('#settingsStatus', 'Live on the desktop', 'on');
      flash('#healthStatus', 'Live on the desktop', 'on');
    } catch (e) {
      if (chip) { chip.textContent = 'Launch Ganesh to save'; chip.className = 'status-chip warn'; }
    }
  };
  if (delay) saveTimers[def.key] = setTimeout(go, delay); else go();
}
async function loadSettings() {
  try { applyFullSettings(await api('/api/settings')); }
  catch (e) { /* engine offline — controls keep their last values */ }
}

// ─── health: one card per reminder, bound live to the engine ─────────────
const ICONS = {
  break: '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4z"/><path d="M6 2v2M10 2v2M14 2v2"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  water: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  stretch: '<circle cx="12" cy="4" r="1.6"/><path d="M12 7v6"/><path d="M8 10l4-3 4 3"/><path d="M9 21l3-8 3 8"/>',
  posture: '<circle cx="12" cy="4.5" r="1.6"/><path d="M12 7v7"/><path d="M7 11h10"/><path d="M12 14l-3 7M12 14l3 7"/>',
  hunger: '<path d="M4 3v7a3 3 0 0 0 6 0V3"/><path d="M7 3v18"/><path d="M17 3c-2 2-3 5-3 8h3v10"/>',
  meditate: '<path d="M12 4c2 3 6 4 6 8a6 6 0 0 1-12 0c0-4 4-5 6-8z"/><path d="M12 12v8"/>'
};
function svgIcon(name) {
  const svg = el('svg', { viewBox: '0 0 24 24' });
  svg.innerHTML = ICONS[name] || ICONS.break;
  return svg;
}
const EVERY_OPTIONS = [10, 15, 20, 30, 45, 60, 90, 120, 150, 180, 240, 360, 480];
const REMINDERS = [
  { key: 'break', name: 'Break', blurb: 'After a stretch of real work, step away for a few minutes.', color: 1, on: 'break_on', every: 'break_every', everyLabel: 'After', everyUnit: 'min of active work', min: 5, max: 240, target: 'break_target', counter: 'breaks', msg: 'break_msg',
    extra: [{ key: 'break_len', type: 'number', label: 'Break length', min: 1, max: 60, unit: 'min' }] },
  { key: 'eye', name: 'Eye rest', blurb: '20-20-20: every 20 minutes, look 20 feet away for 20 seconds.', color: 2, on: 'eye_on', every: 'eye_every', min: 5, max: 180, target: 'eye_target', counter: 'eye', msg: 'eye_msg', log: 'eye', logLabel: 'Rested my eyes' },
  { key: 'water', name: 'Water', blurb: 'A glass at a time. Ganesh gets thirsty too.', color: 1, on: 'water_on', every: 'water_every', min: 10, max: 360, target: 'water_target', counter: 'water', msg: 'water_msg', log: 'water', logLabel: 'Drank a glass' },
  { key: 'stretch', name: 'Stretch', blurb: 'Shoulders, neck, wrists — Ganesh suggests a different one each time.', color: 3, on: 'stretch_on', every: 'stretch_every', min: 10, max: 360, target: 'stretch_target', counter: 'stretch', msg: 'stretch_msg', log: 'stretch', logLabel: 'Stretched' },
  { key: 'posture', name: 'Posture', blurb: 'Sit back, screen at eye level, shoulders down.', color: 5, on: 'posture_on', every: 'posture_every', min: 5, max: 240, target: 'posture_target', counter: 'posture', msg: 'posture_msg', log: 'posture', logLabel: 'Fixed my posture' },
  { key: 'hunger', name: 'Snack', blurb: 'A modak for Ganesh, something real for you.', color: 4, on: 'hunger_on', every: 'hunger_every', min: 30, max: 480, counter: 'hunger', msg: 'hunger_msg', log: 'hunger', logLabel: 'Had a snack' },
  { key: 'meditate', name: 'Breathing', blurb: 'A short guided breathing session, right on the desktop.', color: 5, on: 'meditate_on', every: 'meditate_every', min: 15, max: 720, counter: 'breath', msg: 'meditate_msg',
    extra: [{ key: 'breath_pattern', type: 'select', label: 'Pattern', options: [['box', 'Box 4-4-4-4'], ['478', 'Relaxing 4-7-8'], ['calm', 'Calm 5-5']] },
            { key: 'breath_cycles', type: 'number', label: 'Cycles', min: 2, max: 30, unit: 'rounds' },
            { key: 'dim_on_breathe', type: 'toggle', label: 'Dim the screen' }] }
];
const reminderCards = {};   // key -> { card, next, count, bar, chip }
function buildReminderCards() {
  const grid = $('#reminderCards');
  grid.innerHTML = '';
  REMINDERS.forEach((r) => {
    const card = h('article', 'panel rcard'); card.dataset.reminder = r.key;
    const chip = h('span', 'status-chip');
    // head: icon, name, switch
    const head = h('div', 'rcard-head');
    const icon = h('span', 'rcard-icon'); icon.style.setProperty('--c', 'var(--s' + r.color + ')'); icon.appendChild(svgIcon(r.key));
    const title = h('div', 'rcard-title'); title.appendChild(h('h2', '', r.name)); title.appendChild(h('small', '', r.blurb));
    const onDef = { key: r.on, type: 'toggle', label: r.name + ' on' };
    const { input: onInput, ctl: onCtl } = createControl(onDef, chip, card, 'h-');
    onInput.setAttribute('aria-label', r.name + ' reminder on or off');
    registerCtl(onDef, { input: onInput, row: null, def: onDef, chip, panel: card });
    head.appendChild(icon); head.appendChild(title); head.appendChild(onCtl);
    // live row
    const live = h('div', 'rcard-live');
    const next = h('div', 'next'); const count = h('div', 'count');
    live.appendChild(next); live.appendChild(count);
    const progress = h('div', 'rcard-progress');
    const bar = h('div', 'bar'); const barFill = h('i'); bar.appendChild(barFill); progress.appendChild(bar);
    // body: interval, target, extras, message
    const body = h('div', 'rcard-body');
    const everyDef = { key: r.every, type: 'number', label: r.everyLabel || 'Every', min: r.min, max: r.max, unit: r.everyUnit || 'min', sub: r.on };
    body.appendChild(rcardRow(everyDef, chip, card, r));
    if (r.target) body.appendChild(rcardRow({ key: r.target, type: 'number', label: 'Daily target', min: 1, max: 40, unit: r.key === 'water' ? 'glasses' : 'times', sub: r.on }, chip, card, r));
    (r.extra || []).forEach((def) => body.appendChild(rcardRow({ ...def, sub: r.on }, chip, card, r)));
    const msgWrap = h('div', 'rcard-msg');
    const msgDef = { key: r.msg, type: 'text', label: 'What Ganesh says', max: 140, placeholder: 'Leave empty for Ganesh\'s own words' };
    const { input: msgInput, ctl: msgCtl } = createControl(msgDef, chip, card, 'h-');
    const msgLabel = h('label', '', 'What Ganesh says on the card'); msgLabel.htmlFor = msgInput.id;
    msgWrap.appendChild(msgLabel); msgWrap.appendChild(msgCtl);
    registerCtl(msgDef, { input: msgInput, row: null, def: msgDef, chip, panel: card });
    body.appendChild(msgWrap);
    // actions
    const actions = h('div', 'rcard-actions');
    if (r.log) {
      const logBtn = h('button', 'btn soft sm', '+ ' + r.logLabel); logBtn.dataset.log = r.log;
      logBtn.onclick = async () => {
        logBtn.disabled = true;
        try { applyStats(await api('/api/log', 'POST', { what: r.log })); flash('#healthStatus', r.logLabel + ' — counted', 'on'); toast(r.logLabel + '. Ganesh is pleased; the ' + r.name.toLowerCase() + ' timer starts again from now.'); }
        catch (e) { flash('#healthStatus', 'Launch Ganesh first', 'warn'); }
        finally { logBtn.disabled = false; }
      };
      actions.appendChild(logBtn);
    }
    actions.appendChild(h('span', 'spacer'));
    actions.appendChild(chip);
    card.appendChild(head); card.appendChild(live); card.appendChild(progress); card.appendChild(body); card.appendChild(actions);
    grid.appendChild(card);
    reminderCards[r.key] = { card, next, count, bar: barFill, chip, def: r };
  });
}
function rcardRow(def, chip, card, r) {
  const row = h('div', 'rcard-row');
  const { input, ctl } = createControl(def, chip, card, 'h-');
  const label = h('label', '', def.label); label.htmlFor = input.id;
  row.appendChild(label); row.appendChild(ctl);
  registerCtl(def, { input, row, def, chip, panel: card });
  return row;
}
function renderReminderCards() {
  if (!settings) return;
  REMINDERS.forEach((r) => {
    const c = reminderCards[r.key]; if (!c) return;
    c.card.classList.toggle('off', !settings[r.on]);
  });
  renderReminderLive();
}
function renderReminderLive() {
  const drift = Math.floor((Date.now() - statusAt) / 1000);
  const live = status && status.running ? (status.reminders || []) : [];
  const t = (stats && stats.today) || {};
  REMINDERS.forEach((r) => {
    const c = reminderCards[r.key]; if (!c) return;
    const info = live.find((x) => x.key === r.key);
    const on = settings ? !!settings[r.on] : true;
    if (!status || !status.running) c.next.innerHTML = 'Launch Ganesh to start the timer';
    else if (!on) c.next.innerHTML = 'Switched off';
    else if (status.quiet_mode) c.next.innerHTML = 'Quiet — reminders snoozed';
    else if (status.paused_reason === 'idle') c.next.innerHTML = 'Paused while you are away';
    else if (status.work_hours === false && settings && settings.work_hours_only) c.next.innerHTML = 'Outside work hours';
    else if (info && info.left != null) { const s = Math.max(0, info.left - drift); c.next.innerHTML = 'Next in <b>' + fmtClock(s) + '</b>' + (settings ? ' · ' + fmtEvery(settings[r.every]) : ''); }
    else c.next.innerHTML = settings ? fmtEvery(settings[r.every]) : '';
    const today = t[r.counter] || 0;
    const target = r.target && settings ? settings[r.target] : 0;
    c.count.innerHTML = '<b>' + today + '</b>' + (target ? ' / ' + target : '') + ' today';
    const pct = target ? Math.min(1, today / target) : (info && info.left != null && settings && settings[r.every] ? 1 - Math.max(0, info.left - drift) / (settings[r.every] * 60) : 0);
    c.bar.style.width = (pct * 100).toFixed(1) + '%';
    c.bar.classList.toggle('done', !!target && today >= target);
    c.bar.style.background = target ? '' : 'var(--s' + r.color + ')';
  });
  renderCustomLive();
}
buildReminderCards();
buildSettings();
buildRows($('#scheduleRows'), [
  { key: 'work_hours_only', type: 'toggle', label: 'Only remind me during work hours', hint: 'Outside these hours Ganesh stays quiet' },
  { key: 'work_start_hour', type: 'select', label: 'Work starts', options: HOURS, sub: 'work_hours_only' },
  { key: 'work_end_hour', type: 'select', label: 'Work ends', options: HOURS, sub: 'work_hours_only' },
  { key: 'quiet_on', type: 'toggle', label: 'Quiet hours', hint: 'No reminders at all during these hours' },
  { key: 'quiet_from', type: 'select', label: 'From', options: HOURS, sub: 'quiet_on' },
  { key: 'quiet_to', type: 'select', label: 'To', options: HOURS, sub: 'quiet_on' },
  { key: 'idle_pause', type: 'number', label: 'Pause after', min: 1, max: 60, unit: 'min away', hint: 'Timers only count real keyboard and mouse time' },
  { key: 'skip_fullscreen', type: 'toggle', label: 'Stay quiet during full-screen apps and games' }
], $('#scheduleStatus'), $('#scheduleRows').closest('.panel'), 'sch-');

// ─── custom reminders (stored by the engine, fired on the desktop) ───────
let customSig = '';
const customRows = {};   // id -> { next }
function renderCustom() {
  const items = (stats && stats.custom_reminders) || [];
  const sig = JSON.stringify([desktopOnline, items.map((r) => [r.id, r.name, r.every, r.on, r.msg, r.today, r.streak])]);
  if (sig === customSig) return;
  customSig = sig;
  const list = $('#customList');
  Object.keys(customRows).forEach((k) => delete customRows[k]);
  if (!desktopOnline) { list.innerHTML = '<div class="empty-list">Launch Ganesh to load and save your reminders.</div>'; return; }
  if (!items.length) { list.innerHTML = '<div class="empty-list">Nothing custom yet. Add a reminder above — medication, standing up, checking in with someone.</div>'; return; }
  const fragment = document.createDocumentFragment();
  items.forEach((r) => {
    const row = h('div', 'item' + (r.today ? ' done' : '') + (r.on ? '' : ' off'));
    const text = h('div');
    const name = h('strong', '', r.name);
    if (r.streak > 0) name.appendChild(h('span', 'streak-badge', r.streak + (r.streak === 1 ? ' day' : ' days')));
    const sub = h('small');
    text.appendChild(name); text.appendChild(sub);
    const actions = h('div', 'item-actions');
    const every = h('select', 'mini'); every.title = 'How often';
    const opts = EVERY_OPTIONS.includes(r.every) ? EVERY_OPTIONS : EVERY_OPTIONS.concat([r.every]).sort((a, b) => a - b);
    opts.forEach((m) => { const o = h('option', '', fmtEvery(m).replace('every ', '')); o.value = String(m); every.appendChild(o); });
    every.value = String(r.every);
    every.onchange = async () => { try { applyStats(await api('/api/reminders', 'POST', { action: 'update', id: r.id, every: parseInt(every.value, 10) })); flash('#customStatus', 'Saved', 'on'); } catch (e) { flash('#customStatus', 'Could not save', 'warn'); } };
    const sw = h('label', 'switch'); const swInput = h('input'); swInput.type = 'checkbox'; swInput.checked = !!r.on; swInput.setAttribute('aria-label', r.name + ' on or off');
    swInput.onchange = async () => { try { applyStats(await api('/api/reminders', 'POST', { action: 'update', id: r.id, on: swInput.checked })); } catch (e) { flash('#customStatus', 'Could not save', 'warn'); } };
    sw.appendChild(swInput); sw.appendChild(h('i'));
    const done = h('button', 'btn ' + (r.today ? 'done-btn' : 'ghost'), r.today ? 'Done ×' + r.today : 'Done');
    done.title = 'Count one now and restart the timer';
    done.onclick = async () => { try { applyStats(await api('/api/reminders', 'POST', { action: 'done', id: r.id })); flash('#customStatus', r.name + ' — counted', 'on'); } catch (e) { flash('#customStatus', 'Could not save', 'warn'); } };
    const del = h('button', 'btn ghost del', '×'); del.title = 'Remove reminder';
    del.onclick = async () => { try { applyStats(await api('/api/reminders', 'POST', { action: 'delete', id: r.id })); } catch (e) { flash('#customStatus', 'Could not remove', 'warn'); } };
    actions.appendChild(every); actions.appendChild(sw); actions.appendChild(done); actions.appendChild(del);
    row.appendChild(text); row.appendChild(actions);
    fragment.appendChild(row);
    customRows[r.id] = { sub, r };
  });
  list.replaceChildren(fragment);
  renderCustomLive();
}
function renderCustomLive() {
  const drift = Math.floor((Date.now() - statusAt) / 1000);
  const live = status && status.running ? (status.reminders || []) : [];
  Object.keys(customRows).forEach((id) => {
    const { sub, r } = customRows[id];
    const info = live.find((x) => x.key === id);
    const bits = [];
    if (!r.on) bits.push('off');
    else if (status && status.running && info && info.left != null) bits.push('next in ' + fmtClock(Math.max(0, info.left - drift)));
    else bits.push(fmtEvery(r.every));
    if (r.msg) bits.push('“' + r.msg + '”');
    bits.push(r.today ? 'done ' + r.today + (r.today === 1 ? ' time today' : ' times today') : 'not yet today');
    sub.textContent = bits.join(' · ');
  });
}
$('#customForm').onsubmit = async (ev) => {
  ev.preventDefault();
  const name = $('#customName').value.trim();
  if (!name) return;
  try {
    applyStats(await api('/api/reminders', 'POST', { action: 'add', name, every: parseInt($('#customEvery').value, 10), msg: $('#customMsg').value.trim() }));
    $('#customName').value = ''; $('#customMsg').value = '';
    flash('#customStatus', 'Saved — live on the desktop', 'on');
  } catch (e) { flash('#customStatus', 'Launch Ganesh first', 'warn'); }
};

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
  } catch (e) { status = null; desktopOnline = false; focusLocal = null; }
  statusAt = Date.now();
  renderStatus();
}
function renderStatus() {
  renderLive(); renderNextReminder(); renderFocus(); renderGoals(); renderCustom(); renderPresence(); renderLiveStrip(); renderReminderLive();
}
function renderAll() {
  renderTiles(); renderFocus(); renderFocusStats(); renderGoals(); renderCustom(); drawRings(); renderReminderCards();
  const hist = (stats && stats.history) || [];
  const week = hist.length ? hist : emptyWeek();
  drawActivity($('#activityChart'), (stats && stats.today && stats.today.hours) || []);
  drawBars($('#weekChart'), week, ['active_min'], [series(1)], ['Active'], { fmt: fmtMin, min: 60, target: stats && stats.targets ? stats.targets.active : 0 });
  $('#weekChip').textContent = hist.length ? fmtMin(hist.reduce((n, d) => n + (d.active_min || 0), 0)) + ' this week' : '';
  drawBars($('#healthChart'), week, ['water', 'eye', 'stretch', 'posture', 'exercise'], [series(1), series(2), series(3), series(5), series(4)], ['Water', 'Eye rest', 'Stretch', 'Posture', 'Exercise']);
  drawBars($('#focusChart'), week, ['focus'], [series(1)], ['Focus sessions'], { target: stats && stats.targets ? stats.targets.focus : 0 });
}
function emptyWeek() {
  const out = [];
  for (let i = 6; i >= 0; i--) { const d = new Date(); d.setDate(d.getDate() - i); out.push({ label: d.toLocaleDateString(undefined, { weekday: 'short' }) }); }
  return out;
}

let resizeTimer = null;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 150); });

// ─── boot ────────────────────────────────────────────────────────────────
renderExercises();
showView(location.hash ? location.hash.slice(1) : 'today', false);
setTimeout(() => window.scrollTo(0, 0), 0);   // undo the browser's own #hash jump
loadStatus();
loadStats();
loadSettings();
setInterval(loadStatus, 1000);        // real-time: state, countdowns, idle
setInterval(loadStats, 5000);
setInterval(loadSettings, 10000);     // picks up changes made from the desktop menu
document.addEventListener('visibilitychange', () => { if (!document.hidden) { loadStatus(); loadStats(); loadSettings(); } });
