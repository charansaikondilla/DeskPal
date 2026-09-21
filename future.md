# 🐘 DeskPal — Future Roadmap & Improvement Plan

> **Your tiny desktop companion deserves to be bulletproof, polished, and delightful.**
> This document is the honest, detailed plan for getting there — written directly from the source code.

---

## 📋 Table of Contents

1. [🔴 Priority 1 — Fix Broken Connections (Dashboard ↔ App)](#-priority-1--fix-broken-connections)
2. [🟠 Priority 2 — Real Reminder Data](#-priority-2--real-reminder-data)
3. [🟡 Priority 3 — Exercise Storage & Daily Reset](#-priority-3--exercise-storage--daily-reset)
4. [🟢 Priority 4 — Better Launch & Status Feedback](#-priority-4--better-launch--status-feedback)
5. [🔵 Priority 5 — One-Click Startup & Packaging](#-priority-5--one-click-startup--packaging)
6. [🟣 Priority 6 — UI/UX Polish](#-priority-6--uiux-polish)
7. [⚙️ Priority 7 — Reliability & Error Recovery](#️-priority-7--reliability--error-recovery)
8. [🧪 Priority 8 — Testing & Quality Gates](#-priority-8--testing--quality-gates)
9. [🚀 Priority 9 — Desktop App Power Features](#-priority-9--desktop-app-power-features)
10. [📦 Priority 10 — Distribution & Release](#-priority-10--distribution--release)
11. [🛣️ Timeline Summary](#️-timeline-summary)

---

## 🔴 Priority 1 — Fix Broken Connections

> **The single most important fix.** Right now the dashboard writes reminder settings to `localStorage` only — they never reach the desktop app.

### 🔧 Problem: Dashboard Reminders Go Nowhere

**Where the bug lives:** `deskpal_dashboard.js` line 1 — the `[data-reminder]` `onchange` handler:

```javascript
// CURRENT (broken): only writes to browser storage, never sends to app
s.onchange = () => {
  localStorage.setItem('deskpal-reminders', JSON.stringify(...));
  document.querySelector('#next').textContent = s.dataset.reminder;
  document.querySelector('#nextDetail').textContent = 'in ' + s.value + ' minutes';
}
```

The desktop engine in `deskpal.py` already has settings like `water_every`, `eye_every`, `stretch_every` stored in its own `settings.json` at `%APPDATA%\DeskPal\settings.json`. These two systems never talk.

### ✅ Fix: Add `/api/settings` Endpoint

**In `deskpal_launch_server.py`** — add two new routes:

```
GET  /api/settings         → read current reminder intervals from desktop app
POST /api/settings         → send updated intervals to desktop app
```

**In `deskpal.py`** — the socket command handler already supports commands like `"walk"`, `"wave"`, etc. — extend it to handle `"settings_get"` and `"settings_set:{"water_every":45}"`.

**In the dashboard JS** — after a reminder dropdown changes:
1. POST to `/api/settings` with the new value
2. Wait for `{"ok": true}` response
3. Only update the UI label after success — not before
4. Show an inline error if the POST fails ("Couldn't save — is Ganesh running?")

### ✅ Fix: Load Real Settings on Dashboard Open

```javascript
// SHOULD DO: on page load, read the real values
async function loadSettings() {
  try {
    const settings = await api('/api/settings');
    // set each <select> to the real value from the desktop engine
    document.querySelectorAll('[data-reminder]').forEach(select => {
      const key = reminderKeyMap[select.dataset.reminder]; // e.g. "Water" → "water_every"
      if (settings[key]) select.value = String(settings[key]);
    });
  } catch {
    // dashboard works in read-only mode if app is offline
  }
}
```

**Why this matters:** Right now opening the dashboard and changing "Water" to "30 min" does nothing. After this fix, Ganesh on your desktop will actually remind you every 30 minutes.

---

## 🟠 Priority 2 — Real Reminder Data

> **The "Next reminder: Water / in 60 minutes" card is hardcoded fiction.**

### 🔧 Problem: Status Shows Fake Numbers

**Current code** in `deskpal_dashboard.html`:
```html
<b id="next">Water</b>
<small id="nextDetail">in 60 minutes</small>
```

These are static strings. They don't change unless you touch a dropdown.

### ✅ Fix: Add Next-Reminder Info to the Socket Status Response

The desktop engine in `deskpal.py` already tracks the scheduled times for each reminder. The socket status response needs to include:

```json
{
  "app": "DeskPal",
  "running": true,
  "visible": true,
  "state": "idle",
  "next_reminder": "Water",
  "next_reminder_in_seconds": 1823,
  "quiet_mode": false,
  "paused_reason": null
}
```

**In the dashboard** — update the "Next reminder" card every 30 seconds from this real data:

```javascript
// Show: "Water · in 30m 23s"
const minutes = Math.floor(seconds / 60);
const secs = seconds % 60;
nextDetail.textContent = `in ${minutes}m ${secs}s`;
```

### ✅ Fix: Show Quiet Mode and Paused State

If `quiet_mode: true` or `paused_reason: "idle"`, the dashboard should say so clearly:
- 🔕 "Quiet mode until 8:00 AM"
- ⏸️ "Paused — you've been idle for 7 minutes"
- ✅ "Water · in 30m"

---

## 🟡 Priority 3 — Exercise Storage & Daily Reset

> **The exercise list has two bugs that could confuse or corrupt user data.**

### 🔧 Bug 1: XSS-Vulnerable Rendering

**Current code** in `deskpal_dashboard.js`:
```javascript
row.innerHTML = `<div><strong>${x.name}</strong>...`; // ← DANGER
```

If an exercise name contains `<script>` or `</div>`, this breaks the layout. Fix:

```javascript
const nameEl = document.createElement('strong');
nameEl.textContent = x.name;  // safe, no injection possible
```

### 🔧 Bug 2: No Error Handling on localStorage Parse

```javascript
// CURRENT (crashes if stored JSON is invalid):
let exercises = JSON.parse(localStorage.getItem('deskpal-exercises') || 'null') || defaults...

// SHOULD BE:
function loadExercises() {
  try {
    const raw = localStorage.getItem('deskpal-exercises');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // validate: must be array, each item must have name (string) and minutes (number 1-120)
    if (!Array.isArray(parsed)) return null;
    return parsed.filter(x =>
      typeof x.name === 'string' && x.name.trim().length > 0 &&
      typeof x.minutes === 'number' && x.minutes >= 1 && x.minutes <= 120
    );
  } catch {
    return null; // corrupt data: fall back to defaults silently
  }
}
```

### 🔧 Bug 3: "Today's Movement" Never Resets

The dashboard says **"Today's movement"** but the `done` flag is never cleared by date. If you mark "Desk stretch" as done on Monday, it still shows as done on Tuesday.

**Fix:** Store exercises with a `doneDate` field:
```json
{"name": "Desk stretch", "minutes": 2, "doneDate": "2026-09-20"}
```

On render, consider an exercise done for today only if `doneDate === today's ISO date`. Otherwise render it as undone automatically.

---

## 🟢 Priority 4 — Better Launch & Status Feedback

> **"Checking…" tells the user nothing. Good status feedback prevents repeat clicks and confusion.**

### 🔧 Current Problems

| State | Current label | What user sees |
|-------|--------------|----------------|
| Launcher not running | "Offline / Launcher unavailable" | Same as "app stopped" |
| Launcher running, app not started | "Offline" | No actionable info |
| App starting (takes up to 9 seconds) | Nothing changes | User clicks again → two instances race |
| App running, character hidden | "Running" | Character may not be visible |

### ✅ Fix: Four Distinct States

```javascript
// State machine: UNAVAILABLE → OFFLINE → STARTING → RUNNING
const States = {
  UNAVAILABLE: { label: '⚠️ Launcher offline', detail: 'Start DeskPal from the folder first', color: '#ff6b6b' },
  OFFLINE:     { label: '⭕ Not running',      detail: 'Click "Launch Ganesh" to start',       color: '#ffa94d' },
  STARTING:    { label: '⏳ Starting…',         detail: 'Ganesh is waking up (~8 seconds)',     color: '#74c0fc' },
  RUNNING:     { label: '✅ Running',            detail: 'Ganesh is on your desktop',            color: '#69db7c' },
};
```

**Prevent double-launch:** Disable the launch button while in STARTING state. Re-enable after timeout or on confirmed RUNNING.

**Timeout on requests:** All `fetch()` calls should have a 5-second `AbortController` timeout. The showcase page (`ganesh_showcase.js`) already does this — copy that pattern to the dashboard.

### ✅ Fix: Confirm Visibility Before Saying "Running"

The API status already returns `"visible": true/false`. The dashboard should only say "Ganesh is on your desktop" when `visible === true`. If `visible === false`, say "Running (hidden)" instead.

---

## 🔵 Priority 5 — One-Click Startup & Packaging

> **If someone needs to read a README to start your app, the startup is broken.**

### 🔧 Current Startup Situation

There are **5 different .bat files** plus a long README.txt:
- `Start-DeskPal.bat`
- `Start-DeskPal-Launch.bat`
- `Start-Buddy.bat`
- `Start-Ganesh-Experience.bat`
- `Start-Vinayaka-Scene.bat`
- `If-Something-Goes-Wrong.bat`

This is confusing. A new user does not know which one to click.

### ✅ Fix: Single Entry Point

Create **one** obvious launcher: `Start DeskPal.bat` (the only thing users need):

```batch
@echo off
title DeskPal — Starting...
cd /d "%~dp0"

:: Start the launcher service (silently, idempotent)
start "" /B pythonw deskpal_launch_server.py --open 2>nul

:: Brief wait, then open dashboard in browser
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8766/dashboard

exit /b 0
```

Keep `If-Something-Goes-Wrong.bat` — just rename and clean it up. Archive the others.

### ✅ Fix: Port Already in Use — Better Error

**Current behaviour:** `deskpal_launch_server.py` silently exits if port 8766 is taken. The user sees a blank browser page with no explanation.

**Fix in `deskpal_launch_server.py`**:
```python
try:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
except OSError as e:
    if e.errno == 10048:  # WSAEADDRINUSE on Windows
        print(f"Port {PORT} is already in use by another program.")
        print("Either DeskPal is already running, or another app took that port.")
        print("Try: close DeskPal from the taskbar, then restart.")
        input("Press Enter to exit...")
    sys.exit(1)
```

### ✅ Fix: Verify DeskPal-Windows Build Before Distributing

The `DeskPal-Windows/` folder exists but **has not been verified** to match the current `deskpal.py` source. Before giving this to anyone:

1. Note the version string in source: `APP_VERSION = "1.1"`
2. Confirm the `.exe` in `DeskPal-Windows/` reports the same version
3. Verify `assets/ganesh/` folder is complete in the bundled distribution
4. Run `verify_launch.py` against the bundled version, not just source

---

## 🟣 Priority 6 — UI/UX Polish

> **After the connections work, the dashboard needs to feel as good as the companion.**

### ✅ Fix: Group Dashboard Into Clear Sections

Proposed tab structure:

```
┌─────────────────────────────────┐
│ 🐘 DeskPal Dashboard            │
│━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│ [🌅 Today]  [🔔 Reminders]      │
│ [🤸 Moves]  [🎛️ Settings]       │
└─────────────────────────────────┘
```

- **Today tab:** Real stats from `%APPDATA%\DeskPal\stats.json` — breaks taken, water reminders, streak
- **Reminders tab:** Dropdowns that save to the app + toggle switches for enable/disable
- **Moves tab:** Exercise list with correct daily reset
- **Settings tab:** Character selector, scale slider, quiet hours, autostart toggle

### ✅ Fix: Consistent Naming

| What you say now | What it should be |
|-----------------|------------------|
| "Ganesh" in dashboard, "Pal" in app | Pick one: **Ganesh** as the character name, **DeskPal** as the app name |
| "Modak / laddu" button | "Laddu Toss 🪔" — one clear name |
| "Your wellbeing hub" | "Your companion dashboard" — matches the actual product |

### ✅ Fix: Keyboard Access

Every button and dropdown needs to be reachable by Tab and activated by Enter/Space. The add-exercise dialog should trap focus:

```javascript
dialog.addEventListener('keydown', e => {
  if (e.key === 'Escape') dialog.close();
});
```

### ✅ Fix: Smaller Window Support

The dashboard should work in a window as small as **400px wide** — many users snap it to a side panel. Test and fix the sidebar layout below 800px.

---

## ⚙️ Priority 7 — Reliability & Error Recovery

> **An app people depend on daily must handle every real-world failure gracefully.**

### 🔧 Scenario Checklist

| Scenario | Current behaviour | Should be |
|----------|-----------------|-----------|
| Close dashboard → reminder still fires | ✅ Works (reminders are in desktop app) | Keep this working |
| Change reminder in dashboard → close → reopen | ❌ Dashboard resets to hardcoded defaults | ✅ Load from app on open |
| Dashboard open, app crashes mid-session | ❌ Dashboard stays in "Running" state forever | ✅ Status poll detects change within 5s |
| `settings.json` is corrupt | ✅ App uses defaults (already handled in Config.load) | Also log a user-visible warning |
| `assets/ganesh/` folder is missing | ❌ Character invisible, no user message | ✅ Show "Asset folder missing" in right-click menu |
| Display scaling changes while app runs | 🔶 May mis-position character | ✅ Detect and re-snap to screen |
| Character on disconnected monitor | 🔶 Character becomes invisible | ✅ Re-home character to primary monitor |
| Launch while app already running | ✅ `LOCK_PORT = 50577` prevents double instance | Keep + confirm in distributed build |
| Launcher crashes mid-session | ❌ Dashboard gets "Launcher unavailable" with no recovery | ✅ Auto-restart launcher in the .bat watchdog |

### ✅ Fix: Add a Watchdog Launcher

```batch
:: In start bat — restart the launcher if it ever dies unexpectedly
:loop
pythonw deskpal_launch_server.py
timeout /t 2 /nobreak >nul
goto loop
```

### ✅ Fix: Add Monitor Change Detection in deskpal.py

Windows sends `WM_DISPLAYCHANGE` when monitors connect/disconnect. Subscribe to this via the existing `WIN` wrapper and move the character onto the primary monitor if its current position is out of bounds.

---

## 🧪 Priority 8 — Testing & Quality Gates

> **The existing `verify_launch.py` is a great foundation — expand it before every release.**

### Current Test Coverage ✅

`verify_launch.py` covers:
- ✅ Launch page loads correctly
- ✅ Character image loads (non-zero pixels)
- ✅ Launch button starts the desktop app
- ✅ All 6 emotes reach the desktop engine
- ✅ Repeated launch doesn't crash
- ✅ Mobile layout fits viewport
- ✅ Unauthenticated POST → 403
- ✅ Source code not exposed via HTTP
- ✅ No JS errors on page
- ✅ No Python tracebacks in log

### ❌ Missing Tests — Add These

```python
# Test: reminder settings round-trip
def test_settings_roundtrip():
    """Set water interval via API, restart app, confirm value persists."""
    api_post('/api/settings', {'water_every': 45})
    restart_app()
    state = desktop('settings_get')
    assert state['water_every'] == 45, "Setting didn't survive restart"

# Test: dashboard loads real settings on open
def test_dashboard_loads_real_settings():
    page.goto(URL + '/dashboard')
    water_select = page.locator('[data-reminder="Water"]')
    actual = desktop()['water_every']
    assert water_select.input_value() == str(actual)

# Test: corrupt localStorage doesn't crash dashboard
def test_corrupt_localstorage():
    page.evaluate("localStorage.setItem('deskpal-exercises', 'not-json')")
    page.reload()
    assert not errors  # no JS error thrown

# Test: dashboard works with launcher offline
def test_launcher_offline():
    # Kill launcher, open dashboard
    page.goto(URL + '/dashboard')
    # Should show "Launcher unavailable", not a blank/crashed page
    assert page.locator('#deskpal').text_content() != ''

# Test: exercise daily reset
def test_exercise_daily_reset():
    page.evaluate("""
        const exercises = [{name: 'Test', minutes: 2, done: true, doneDate: '2000-01-01'}];
        localStorage.setItem('deskpal-exercises', JSON.stringify(exercises));
    """)
    page.reload()
    # Exercise should render as NOT done today
    assert 'done' not in (page.locator('.exercise').get_attribute('class') or '')
```

### ✅ Gate: Run Tests Before Every Distribution

Create `run_tests.bat`. Only zip and ship `DeskPal-Windows.zip` **after all tests pass**.

---

## 🚀 Priority 9 — Desktop App Power Features

> **These are things that make DeskPal genuinely better than any website can be.**

### 💡 Feature: Smarter Idle Detection

**Currently:** Reminders pause after `idle_pause` minutes of no keyboard/mouse input (via `idle_seconds()` in `deskpal.py`).

**Better:** Distinguish *idle* from *deeply focused*:
- 😴 Idle 5+ min → pause reminders, stop animation
- ⌨️ Active typing burst → defer non-urgent reminders by 5 min
- 🎯 Focus mode active → only show urgent reminders (battery, time)

### 💡 Feature: Streak Heatmap in Dashboard

`%APPDATA%\DeskPal\stats.json` already tracks `breaks`, `waters`, `eyes` per day for 120 days. Add a calendar heatmap to the Today tab:

```
Sep 2026
M  T  W  T  F
■  ■  □  ■  ■   ← darker square = more reminders acknowledged that day
```

This is ~20 lines of JavaScript on top of existing data. No new collection needed.

### 💡 Feature: Quiet Hours Configurator

The app already has `quiet_from` / `quiet_to` in `settings.json`. The dashboard should show a time range control, not just a dropdown. Changes save via `/api/settings`.

### 💡 Feature: Right-Click "Open Dashboard"

In `deskpal.py`, the right-click menu already has many options. Add one:

```python
menu.add_command(
    label="📊 Open dashboard",
    command=lambda: webbrowser.open("http://127.0.0.1:8766/dashboard")
)
```

This makes the dashboard discoverable without hunting for a URL.

### 💡 Feature: Ganesh Reacts to Focus Mode

When the user starts a Pomodoro focus session, Ganesh could:
- Show a focused/serious pose 🎯
- Stop wandering for the duration
- Show a "Focus ending soon" wave at 22 minutes

This plugs into the existing animation state machine — no new infrastructure needed.

### 💡 Feature: Document the Notify File

The app already watches `%APPDATA%\DeskPal\notify.txt` for external messages. Document this in the dashboard Settings tab so any script or tool can trigger Ganesh:

```batch
echo "Your build finished! 🎉" >> %APPDATA%\DeskPal\notify.txt
```

---

## 📦 Priority 10 — Distribution & Release

> **The final 20% that makes the difference between a personal project and something you give to people.**

### ✅ Checklist Before Giving DeskPal to Others

- [ ] `APP_VERSION` in `deskpal.py` is current (currently `"1.1"`)
- [ ] `DeskPal-Windows/` executable version matches source
- [ ] `assets/ganesh/` folder is complete in the zip (every `.png` referenced in code exists)
- [ ] All 5 old `.bat` files replaced with one clear `Start DeskPal.bat`
- [ ] `verify_launch.py` passes with zero failures against the distributed build
- [ ] New settings tests pass (see Priority 8)
- [ ] `README.txt` updated to match current launcher name and dashboard URL
- [ ] `If-Something-Goes-Wrong.bat` has clear, readable instructions (not technical jargon)

### ✅ What the Final Zip Should Contain

```
DeskPal/
├── Start DeskPal.bat          ← the ONLY thing users need to click
├── If-Something-Goes-Wrong.bat
├── DeskPal.exe                ← compiled from deskpal.py via PyInstaller
├── deskpal_launch_server.exe  ← compiled launcher
├── assets/
│   └── ganesh/
│       ├── ganesh_stand.png
│       └── ... (all sprites)
├── deskpal_dashboard.html
├── deskpal_dashboard.css
├── deskpal_dashboard.js
├── ganesh_showcase.html
├── ganesh_showcase.css
└── ganesh_showcase.js
```

### ✅ For Python Source Distribution (Power Users)

Keep the source version working:
```
Python 3.9+  (no pip installs needed for the app itself)
Run: python deskpal_launch_server.py --open
```

Add `requirements.txt` noting that `playwright` is only needed to run the test suite — not to run the app.

---

## 🛣️ Timeline Summary

| Phase | What | Effort | Impact |
|-------|------|--------|--------|
| **Week 1** | Priority 1: Settings endpoint + dashboard wiring | 1–2 days | 🔴 Critical — app/dashboard actually connected |
| **Week 1** | Priority 2: Real reminder status in dashboard | 0.5 day | 🟠 High — no more fake "Water / in 60 min" |
| **Week 1** | Priority 3: Exercise safety fixes + daily reset | 0.5 day | 🟡 Medium — prevents data bugs |
| **Week 2** | Priority 4: Launch state machine + timeouts | 1 day | 🟢 High — no more confused double-clicks |
| **Week 2** | Priority 5: Single start bat + port error message | 0.5 day | 🔵 High — critical for giving to others |
| **Week 2** | Priority 8: New tests + run_tests.bat | 1 day | 🧪 Safety net for everything else |
| **Week 3** | Priority 6: Dashboard layout + keyboard access | 2 days | 🟣 Polish |
| **Week 3** | Priority 7: Monitor change + watchdog | 1 day | ⚙️ Reliability |
| **Week 4** | Priority 9: Power features (heatmap, quiet hours UI, right-click dashboard) | 3 days | 🚀 Delight |
| **Week 4** | Priority 10: Distribution build + full test pass | 1 day | 📦 Release-ready |

---

## 🏁 Definition of "Done"

DeskPal is ready to give to people when:

1. ✅ **One click starts everything** — `Start DeskPal.bat` → browser opens → Ganesh appears
2. ✅ **Dashboard settings reach the desktop engine** — change "Water" to 30 min → Ganesh actually reminds at 30 min, survives restart
3. ✅ **Dashboard shows real data** — next reminder countdown is live, not hardcoded
4. ✅ **No silent failures** — every error state has a readable, actionable message
5. ✅ **Exercises reset daily** — "Today's movement" means today, not since last click
6. ✅ **All tests pass** — `verify_launch.py` + new test suite, zero failures
7. ✅ **Distribution verified** — `.exe` version = source version, all assets present

---

> 🐘 *DeskPal is already doing the hard thing — it's alive on your desktop, caring about your health. This roadmap just makes sure it's as solid as the care it represents.*

*Last updated: September 2026 — based on source inspection of `deskpal.py` (v1.1, 6373 lines), `deskpal_launch_server.py`, `deskpal_dashboard.js`, `ganesh_showcase.js`, and `verify_launch.py`.*
