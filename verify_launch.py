"""Exercise the local launch page and dashboard against the real desktop application."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8766"
ROOT = Path(__file__).resolve().parent


def server_alive():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return json.load(response).get("service") == "deskpal-launcher"
    except (OSError, ValueError):
        return False


def buddy_alive():
    try:
        with socket.create_connection(("127.0.0.1", 50577), timeout=1):
            return True
    except OSError:
        return False


def quit_app():
    """Shut down whatever DeskPal is already running so the verifier always
    exercises a freshly launched app.  The buddy gets the same `quit` action
    the app's Quit button sends; the launcher is a stateless proxy that the
    buddy respawns via ensure_launcher(), so it is stopped afterwards by
    process name and never merely `terminate()`d."""
    if server_alive() and buddy_alive():
        request = urllib.request.Request(
            URL + "/api/action", data=json.dumps({"action": "quit"}).encode("utf-8"),
            headers={"X-DeskPal-Launch": "1", "Origin": URL, "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=5).read()
        except (OSError, ValueError):
            pass
    for _ in range(50):
        if not buddy_alive():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("A previous DeskPal instance would not quit")
    if os.name == "nt":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
                        "'*deskpal_launch_server.py*' } | ForEach-Object { Stop-Process -Id "
                        "$_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                       capture_output=True, timeout=30)
    for _ in range(50):
        if not server_alive():
            return
        time.sleep(0.2)
    raise RuntimeError("A previous DeskPal launcher would not stop")


def ensure_server_running():
    # Always verify a freshly launched app, never whatever happens to be running.
    quit_app()
    executable = sys.executable
    windowless = Path(executable).with_name("pythonw.exe")
    if os.name == "nt" and windowless.exists():
        executable = str(windowless)

    proc = subprocess.Popen([executable, str(ROOT / "deskpal_launch_server.py")], cwd=ROOT)
    for _ in range(30):
        time.sleep(0.2)
        try:
            with urllib.request.urlopen(URL + "/api/health", timeout=1) as resp:
                if json.load(resp).get("service") == "deskpal-launcher":
                    return proc
        except (OSError, ValueError):
            pass
    raise RuntimeError("Launch server failed to start")


def status():
    with urllib.request.urlopen(URL + "/api/status") as response:
        return json.load(response)


def wait_state(expected, timeout=6.0):
    """Poll /api/status until the engine reports `expected` (animations are
    acknowledged over a socket before the state machine flips, and a freshly
    launched Ganesh plays an intro first)."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = status()
        if last["state"] == expected:
            return last
        time.sleep(0.15)
    raise AssertionError((expected, last))


def wait_setting(key, expected, timeout=6.0):
    """Poll /api/settings until the engine reports key == expected."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = settings_get()
        if last.get(key) == expected:
            return last
        time.sleep(0.15)
    raise AssertionError(("setting %s never became %r" % (key, expected), last))


def settings_get():
    with urllib.request.urlopen(URL + "/api/settings") as response:
        return json.load(response)


def main():
    server_proc = ensure_server_running()
    try:
        output = ROOT / "verification"
        output.mkdir(exist_ok=True)
        log = Path(os.environ["APPDATA"]) / "DeskPal" / "log.txt"
        offset = log.stat().st_size if log.exists() else 0

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            # 1. Test Launcher Page & Emotes
            page.goto(URL)
            page.wait_for_function("document.getElementById('connection-label').textContent !== 'Connecting'")
            assert page.locator("#preview-character").evaluate("image => image.complete && image.naturalWidth > 0")
            page.screenshot(path=str(output / "deskpal-launch-desktop.png"))

            page.get_by_role("button", name="Launch DeskPal").click()
            page.locator("#running-panel").wait_for(state="visible", timeout=20000)
            assert status()["character"] == "custom"
            assert status()["visible"]
            wait_state("idle", timeout=15)   # let the launch intro finish

            for name, state, seconds in (("Walk", "walk", 4.2), ("Run", "run_cycle", 3.2),
                                         ("Hungry", "hungry_cycle", 3.2), ("Laddu toss", "eat_laddu", 5.2),
                                         ("Wave", "wave", 2.6), ("Celebrate", "celebrate", 3.2)):
                page.get_by_role("button", name=name, exact=True).click()
                page.wait_for_function("document.getElementById('emote-status').textContent === "
                                       + json.dumps(name + " is playing on your desktop."))
                wait_state(state)
                page.wait_for_timeout(seconds * 1000)
                print(name + ": desktop acknowledged and completed", flush=True)

            page.screenshot(path=str(output / "deskpal-running.png"))

            # 2. The app: every page, every control bound to the real engine
            dashboard_url = URL + "/dashboard"
            api_headers = {"X-DeskPal-Launch": "1", "Origin": URL, "Content-Type": "application/json"}

            def goto_view(name):
                page.click('#nav a[data-view="%s"]' % name)
                page.wait_for_function("document.body.dataset.view === %s" % json.dumps(name))

            page.goto(dashboard_url)
            page.wait_for_selector("#livePill")
            page.wait_for_selector("#activityChart svg")
            page.wait_for_function("document.getElementById('sideVersion').textContent !== ''")

            # 2a. Today: tiles, rings, week chart, heatmap and log come from /api/stats
            stats = page.request.get(URL + "/api/stats").json()
            assert "today" in stats and "history" in stats and len(stats["history"]) == 7, stats
            assert "targets" in stats and stats["targets"].get("water"), stats["targets"]
            assert "heatmap" in stats and len(stats["heatmap"]) == 7 and len(stats["heatmap"][0]["hours"]) == 24, stats.get("heatmap")
            assert page.locator("#rings svg circle.fill").count() == 4
            assert not page.locator("#rings").evaluate("e => e.classList.contains('skeleton')")
            assert page.locator("#weekChart svg").count() == 1
            assert not page.locator("#weekChart").evaluate("e => e.classList.contains('skeleton')")
            assert page.locator("#todayLog div").count() >= 6
            assert page.locator("#tActive").text_content().strip() != ""
            # weekly heatmap: a real 7x24 grid, bound to real per-hour history
            page.wait_for_function("document.querySelectorAll('#heatmapGrid .heatmap-cell').length === 168")
            assert not page.locator("#heatmapGrid").evaluate("e => e.classList.contains('skeleton')")
            page.locator("#heatmapGrid .heatmap-cell").first.hover()
            page.wait_for_selector("#tooltip:not([hidden])")
            page.mouse.move(5, 5)
            # sparklines: SVG trend line inside each tile that has 7-day history
            assert page.locator("#tActiveSpark svg, #tActiveSpark.empty").count() == 1
            assert page.locator("#tFocusSpark svg, #tFocusSpark.empty").count() == 1
            assert page.locator("#tHealthSpark svg, #tHealthSpark.empty").count() == 1
            print("heatmap, sparklines and skeleton-removal verified", flush=True)
            page.screenshot(path=str(output / "deskpal-today.png"))

            # 2b. Health page: reminder cards mirror the engine live
            goto_view("health")
            page.locator("#reminderCards .rcard").first.wait_for()
            assert page.locator("#reminderCards .rcard").count() == 7
            assert page.locator("#healthChart svg rect.bar").count() >= 1
            full = settings_get()
            water_every = page.locator("#h-water_every")
            assert water_every.input_value() == str(full["water_every"])
            # interval typed on the card reaches the engine (debounced save)
            water_every.fill("30")
            wait_setting("water_every", 30)
            water_every.fill(str(full["water_every"]))
            wait_setting("water_every", full["water_every"])
            # daily target
            page.locator("#h-water_target").fill("11")
            wait_setting("water_target", 11)
            assert page.request.get(URL + "/api/stats").json()["targets"]["water"] == 11
            page.locator("#h-water_target").fill(str(full["water_target"]))
            wait_setting("water_target", full["water_target"])
            # the message Ganesh shows on the desktop card
            page.locator("#h-water_msg").fill("Sip sip - hydrate!")
            wait_setting("water_msg", "Sip sip - hydrate!")
            assert [r["msg"] for r in status()["reminders"] if r["key"] == "water"] == ["Sip sip - hydrate!"]
            page.locator("#h-water_msg").fill("")
            wait_setting("water_msg", "")
            # on/off switch on the card
            was_on = bool(full["water_on"])
            page.locator("#h-water_on").click(force=True)
            wait_setting("water_on", not was_on)
            page.locator("#h-water_on").click(force=True)
            wait_setting("water_on", was_on)
            # live countdown text comes from the engine's timers
            page.wait_for_function("/Next in|every|Paused|Quiet|Outside/.test(document.querySelector('[data-reminder=eye] .next').textContent)")
            eye_info = [r for r in status()["reminders"] if r["key"] == "eye"][0]
            assert eye_info["on"] == settings_get()["eye_on"] and eye_info["every"] == settings_get()["eye_every"], eye_info
            # logging a glass of water counts it and restarts the timer
            before_water = page.request.get(URL + "/api/stats").json()["today"]["water"]
            page.locator('[data-log="water"]').click()
            page.wait_for_function("document.querySelector('[data-reminder=water] .count b').textContent === %s" % json.dumps(str(before_water + 1)))
            assert page.request.get(URL + "/api/stats").json()["today"]["water"] == before_water + 1
            # schedule panel: work hours only
            page.locator("label[for=sch-work_hours_only]").click()
            wait_setting("work_hours_only", not bool(full["work_hours_only"]))
            page.locator("label[for=sch-work_hours_only]").click()
            wait_setting("work_hours_only", bool(full["work_hours_only"]))
            print("health page: intervals, targets, messages, switches, logging and schedule verified", flush=True)

            # 2c. Custom reminders round-trip through the engine
            for r in page.request.get(URL + "/api/stats").json()["custom_reminders"]:
                if r["name"].startswith("Verify reminder"):
                    page.request.post(URL + "/api/reminders", data=json.dumps({"action": "delete", "id": r["id"]}), headers=api_headers)
            rem_name = "Verify reminder %d" % int(time.time())
            rem_row = page.locator("#customList .item", has_text=rem_name)
            page.fill("#customName", rem_name)
            page.select_option("#customEvery", "30")
            page.fill("#customMsg", "Stand up and shake it out")
            page.click("#customForm button[type=submit]")
            rem_row.wait_for()
            rem = [r for r in page.request.get(URL + "/api/stats").json()["custom_reminders"] if r["name"] == rem_name]
            assert rem and rem[0]["every"] == 30 and rem[0]["msg"] == "Stand up and shake it out", rem
            assert any(r["key"] == rem[0]["id"] and r["custom"] for r in status()["reminders"]), status()["reminders"]
            rem_row.locator("button", has_text="Done").click()
            page.wait_for_function("document.querySelector('#customList .item.done') !== null")
            assert [r for r in page.request.get(URL + "/api/stats").json()["custom_reminders"] if r["name"] == rem_name][0]["today"] == 1
            rem_row.locator("select.mini").select_option("60")
            deadline = time.time() + 6
            got = []
            while time.time() < deadline:
                got = [r for r in page.request.get(URL + "/api/stats").json()["custom_reminders"] if r["name"] == rem_name]
                if got and got[0]["every"] == 60:
                    break
                time.sleep(0.2)
            assert got and got[0]["every"] == 60, got
            rem_row.locator(".btn.del").click()
            rem_row.wait_for(state="detached")
            assert not any(r["name"] == rem_name for r in page.request.get(URL + "/api/stats").json()["custom_reminders"])
            print("custom reminders: add, fire schedule, done, edit, delete verified", flush=True)
            page.screenshot(path=str(output / "deskpal-health.png"))

            # 2d. Goals round-trip through the desktop engine (with 7-day dots)
            goto_view("goals")
            for g in page.request.get(URL + "/api/stats").json()["goals"]:
                if g["name"].startswith("Verify goal"):   # leftovers from an aborted run
                    page.request.post(URL + "/api/goals", data=json.dumps({"action": "delete", "id": g["id"]}),
                                      headers=api_headers)
            goal_name = "Verify goal %d" % int(time.time())
            row = page.locator("#goalList .item", has_text=goal_name)
            page.fill("#goalName", goal_name)
            page.click("#goalForm button[type=submit]")
            row.wait_for()
            goals = page.request.get(URL + "/api/stats").json()["goals"]
            assert any(g["name"] == goal_name and len(g["week"]) == 7 for g in goals), goals
            row.locator(".btn").first.click()
            page.wait_for_function("document.querySelector('#goalList .item.done') !== null")
            goals = page.request.get(URL + "/api/stats").json()["goals"]
            assert any(g["name"] == goal_name and g["done_today"] and g["week"][-1] == 1 for g in goals), goals
            assert row.locator(".week-dots i.on").count() >= 1
            row.locator(".btn.del").click()
            row.wait_for(state="detached")
            goals = page.request.get(URL + "/api/stats").json()["goals"]
            assert not any(g["name"] == goal_name for g in goals), goals

            # 2e. Focus page: presets save the engine defaults
            goto_view("focus")
            old_focus, old_break = int(full.get("focus_len", 25)), int(full.get("focus_break", 5))
            page.locator('#focusPresets .preset[data-focus="50"]').click()
            wait_setting("focus_len", 50)
            wait_setting("focus_break", 10)
            assert page.locator("#focusMinutes").input_value() == "50"
            page.request.post(URL + "/api/settings", data=json.dumps({"focus_len": old_focus, "focus_break": old_break}), headers=api_headers)
            wait_setting("focus_len", old_focus)
            assert page.locator("#focusStats div").count() >= 4
            assert page.locator("#focusChart svg").count() == 1

            # 2f. Settings page: every control type, search, appearance
            goto_view("settings")
            assert "fps" in full and "quiet_from" in full and "data_dir" in full, full
            page.locator("#settingsGrid .panel").first.wait_for()
            assert page.locator("#settingsGrid .panel").count() == 4
            assert page.locator("#aboutPath").text_content() == full["data_dir"]
            # toggle: speech bubbles
            speech = page.locator("#set-speech")
            before = bool(full.get("speech", True))
            assert speech.is_checked() == before
            page.locator("label[for=set-speech]").click()
            wait_setting("speech", (not before))
            page.locator("label[for=set-speech]").click()
            wait_setting("speech", before)
            # number: focus length (debounced save)
            page.fill("#set-focus_len", "40")
            wait_setting("focus_len", 40)
            page.fill("#set-focus_len", str(old_focus))
            wait_setting("focus_len", old_focus)
            # select: quiet hours "from"
            old_qf = int(full.get("quiet_from", 22))
            page.select_option("#set-quiet_from", "21")
            wait_setting("quiet_from", 21)
            assert page.locator("#sch-quiet_from").input_value() == "21"   # Health page mirrors it
            page.select_option("#set-quiet_from", str(old_qf))
            wait_setting("quiet_from", old_qf)
            # choice: character stays Ganesh after a round trip
            page.locator("#set-character button[data-value=custom]").click()
            wait_setting("character", "custom")
            # out-of-range numbers are clamped by the engine, never accepted raw
            assert page.request.post(URL + "/api/settings", data=json.dumps({"fps": 9999}),
                                     headers=api_headers).json()["fps"] == 60
            page.request.post(URL + "/api/settings", data=json.dumps({"fps": full.get("fps", 30)}), headers=api_headers)
            assert page.request.post(URL + "/api/settings", data=json.dumps({"water_target": 999}),
                                     headers=api_headers).json()["water_target"] == 30
            page.request.post(URL + "/api/settings", data=json.dumps({"water_target": full["water_target"]}), headers=api_headers)
            # search narrows the settings list
            page.fill("#settingsSearch", "battery")
            page.wait_for_function("document.querySelectorAll('#settingsGrid .srow:not(.hidden)').length === 2")
            page.fill("#settingsSearch", "")
            page.wait_for_function("document.querySelectorAll('#settingsGrid .srow.hidden').length === 0")
            # appearance: accent + theme are remembered on this device
            page.locator('#accentSwatches button[data-value="forest"]').click()
            assert page.evaluate("document.documentElement.dataset.accent") == "forest"
            page.locator('#themeSeg button[data-value="dark"]').click()
            assert page.evaluate("document.documentElement.dataset.theme") == "dark"
            page.screenshot(path=str(output / "deskpal-settings-dark.png"))
            page.locator('#themeSeg button[data-value="system"]').click()
            page.locator('#accentSwatches button[data-value="indigo"]').click()
            print("settings page: toggle, number, select, choice, clamping, search and appearance verified", flush=True)

            # 2g. Ganesh page: emotes, actions and live presence
            goto_view("companion")
            page.locator('[data-emote="bless_cycle"]').click()
            wait_state("bless_cycle")
            page.locator('[data-emote="stop"]').click()
            wait_state("idle")
            page.locator('[data-action="snooze"][data-minutes="30"]').click()
            page.wait_for_timeout(600)
            assert status()["quiet_mode"] and status()["snooze_seconds"] > 1700, status()
            page.locator('[data-action="snooze_off"]').click()
            page.wait_for_timeout(600)
            assert status()["snooze_seconds"] == 0, status()
            page.wait_for_function("document.getElementById('lsState').classList.contains('on') || document.getElementById('lsState').classList.contains('idle')")
            assert "Ganesh" in page.locator("#presenceState").text_content()
            assert "Ganesh" in page.locator("#presenceMiniState").text_content()
            assert page.request.post(URL + "/api/action", data=json.dumps({"action": "format_disk"}),
                                     headers=api_headers).status == 400
            assert page.request.post(URL + "/api/log", data=json.dumps({"what": "rm -rf"}),
                                     headers=api_headers).status == 400
            goto_view("settings")
            page.locator('[data-action="reset_timers"]').click()
            page.wait_for_timeout(500)
            assert page.locator("#toast").is_visible()
            # keyboard: 1..6 switch pages
            page.keyboard.press("3")
            page.wait_for_function("document.body.dataset.view === 'health'")
            print("emotes, actions, live presence and keyboard navigation verified", flush=True)

            # 3. Test Daily Exercise Reset & Corrupt LocalStorage Recovery
            page.evaluate("localStorage.setItem('deskpal-exercises', 'not-valid-json')")
            page.reload()
            page.wait_for_function("document.body.dataset.view === 'health'")   # hash keeps the page
            page.wait_for_selector("#exerciseList")
            assert not errors, "Corrupt localStorage crashed dashboard"

            # Exercise daily reset test
            yesterday_exercise = [
                {"name": "Old Stretch", "minutes": 2, "done": True, "doneDate": "2000-01-01"}
            ]
            page.evaluate(f"localStorage.setItem('deskpal-exercises', '{json.dumps(yesterday_exercise)}')")
            page.reload()
            page.wait_for_function("document.body.dataset.view === 'health'")
            page.wait_for_selector("#exerciseList")
            done_count = page.locator("#exerciseList .item.done").count()
            assert done_count == 0, f"Exercise done state did not reset for new day, got {done_count}"

            page.screenshot(path=str(output / "deskpal-dashboard.png"))

            # Security check
            assert page.request.post(URL + "/api/launch").status == 403
            assert page.request.get(URL + "/deskpal.py").status == 404
            assert not errors, errors
            browser.close()

        if log.exists():
            with log.open("rb") as handle:
                handle.seek(offset)
                recent = handle.read().decode("utf-8", errors="replace")
            assert "Traceback" not in recent and "TK CALLBACK ERROR" not in recent, recent
        print("PASS: launch, emotes, today, health (targets, messages, logging, schedule), custom reminders, goals, focus presets, settings (search, appearance), actions, live presence, keyboard nav, exercise daily reset, security, zero tracebacks")
    finally:
        quit_app()
        if server_proc:
            try:
                server_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
