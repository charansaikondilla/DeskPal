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

            # 2. Test Settings Endpoint & Dashboard Integration
            dashboard_url = URL + "/dashboard"
            page.goto(dashboard_url)
            page.wait_for_selector("#livePill")
            page.wait_for_selector("#activityChart svg")

            # Test: live stats endpoint feeds the charts and tiles
            stats = page.request.get(URL + "/api/stats").json()
            assert "today" in stats and "history" in stats and len(stats["history"]) == 7, stats
            assert page.locator("#healthChart svg rect.bar").count() >= 1
            assert page.locator("#tStreak").text_content() == str(stats["streak"])

            # Test: custom goals round-trip through the desktop engine
            api_headers = {"X-DeskPal-Launch": "1", "Origin": URL, "Content-Type": "application/json"}
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
            assert any(g["name"] == goal_name for g in goals), goals
            row.locator(".btn").first.click()
            page.wait_for_function("document.querySelector('#goalList .item.done') !== null")
            goals = page.request.get(URL + "/api/stats").json()["goals"]
            assert any(g["name"] == goal_name and g["done_today"] for g in goals), goals
            row.locator(".btn.del").click()
            row.wait_for(state="detached")
            goals = page.request.get(URL + "/api/stats").json()["goals"]
            assert not any(g["name"] == goal_name for g in goals), goals
            
            # Test: Dashboard reflects real engine settings
            water_select = page.locator('[data-reminder="Water"]')
            current_water = settings_get().get("water_every", 60)
            assert water_select.input_value() == str(current_water)

            # Test: Changing dropdown posts settings to desktop engine (valid options for Water: "30", "60", "90")
            water_select.select_option("30")
            wait_setting("water_every", 30)

            # Reset back to 60 for consistency
            water_select.select_option("60")
            wait_setting("water_every", 60)

            # 2b. Full settings page: every control is bound to the engine
            full = settings_get()
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
            old_focus = int(full.get("focus_len", 25))
            page.fill("#set-focus_len", "40")
            wait_setting("focus_len", 40)
            page.fill("#set-focus_len", str(old_focus))
            wait_setting("focus_len", old_focus)
            # select: quiet hours "from"
            old_qf = int(full.get("quiet_from", 22))
            page.select_option("#set-quiet_from", "21")
            wait_setting("quiet_from", 21)
            page.select_option("#set-quiet_from", str(old_qf))
            wait_setting("quiet_from", old_qf)
            # choice: character stays Ganesh after a round trip
            page.locator("#set-character button[data-value=custom]").click()
            wait_setting("character", "custom")
            # out-of-range numbers are clamped by the engine, never accepted raw
            assert page.request.post(URL + "/api/settings", data=json.dumps({"fps": 9999}),
                                     headers={"X-DeskPal-Launch": "1", "Origin": URL,
                                              "Content-Type": "application/json"}).json()["fps"] == 60
            page.request.post(URL + "/api/settings", data=json.dumps({"fps": full.get("fps", 30)}),
                              headers={"X-DeskPal-Launch": "1", "Origin": URL, "Content-Type": "application/json"})
            print("settings page: toggle, number, select, choice and clamping verified", flush=True)

            # 2c. Every emote button and the maintenance actions reach the engine
            page.locator('[data-emote="bless_cycle"]').click()
            wait_state("bless_cycle")
            page.locator('[data-emote="stop"]').click()
            wait_state("idle")
            page.locator('[data-action="reset_timers"]').click()
            page.wait_for_timeout(500)
            assert page.locator("#toast").is_visible()
            page.locator('[data-action="snooze"][data-minutes="30"]').click()
            page.wait_for_timeout(600)
            assert status()["quiet_mode"] and status()["snooze_seconds"] > 1700, status()
            page.locator('[data-action="snooze_off"]').click()
            page.wait_for_timeout(600)
            assert status()["snooze_seconds"] == 0, status()
            # live strip reflects the engine in real time
            page.wait_for_function("document.getElementById('lsState').classList.contains('on') || document.getElementById('lsState').classList.contains('idle')")
            assert "Ganesh" in page.locator("#presenceState").text_content()
            assert page.request.post(URL + "/api/action", data=json.dumps({"action": "format_disk"}),
                                     headers={"X-DeskPal-Launch": "1", "Origin": URL,
                                              "Content-Type": "application/json"}).status == 400
            print("emotes, actions and live presence verified", flush=True)

            # 3. Test Daily Exercise Reset & Corrupt LocalStorage Recovery
            page.evaluate("localStorage.setItem('deskpal-exercises', 'not-valid-json')")
            page.reload()
            page.wait_for_selector("#exerciseList")
            assert not errors, "Corrupt localStorage crashed dashboard"

            # Exercise daily reset test
            yesterday_exercise = [
                {"name": "Old Stretch", "minutes": 2, "done": True, "doneDate": "2000-01-01"}
            ]
            page.evaluate(f"localStorage.setItem('deskpal-exercises', '{json.dumps(yesterday_exercise)}')")
            page.reload()
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
        print("PASS: launch, emotes, settings page, actions, live presence, dashboard integration, exercise daily reset, security, zero tracebacks")
    finally:
        quit_app()
        if server_proc:
            try:
                server_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
