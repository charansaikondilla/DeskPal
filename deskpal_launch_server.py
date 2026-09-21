"""Loopback-only desktop launcher; Python standard library only."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
PORT = 8766
URL = f"http://127.0.0.1:{PORT}"
LAUNCH_LOCK = threading.Lock()

# Emotes the dashboard may trigger: name -> desktop command.
EMOTES = {
    # short names the launch page used from day one
    "walk": "walk", "run": "run", "hungry": "hungry", "laddu": "laddu",
    "wave": "wave", "celebrate": "celebrate",
    # every Ganesh clip from the old Settings > Emotes tab
    "idle": 'emote:{"state": "idle"}',
    "run_cycle": 'emote:{"state": "run_cycle"}',
    "breathe_cycle": 'emote:{"state": "breathe_cycle"}',
    "meditation_peek": 'emote:{"state": "meditation_peek"}',
    "eat_laddu": 'emote:{"state": "eat_laddu"}',
    "window_peek": 'emote:{"state": "window_peek"}',
    "water_slump": 'emote:{"state": "water_slump"}',
    "drink_water": 'emote:{"state": "drink_water"}',
    "bless_cycle": 'emote:{"state": "bless_cycle"}',
    "study_cycle": 'emote:{"state": "study_cycle"}',
    "mouse_play": 'emote:{"state": "mouse_play"}',
    "mouse_ride": 'emote:{"state": "mouse_ride"}',
    "happy_jump": 'emote:{"state": "happy_jump"}',
    "hungry_cycle": 'emote:{"state": "hungry_cycle"}',
    "dance": 'emote:{"state": "dance"}',
    "stretch": 'emote:{"state": "stretch"}',
    "jumping_jacks": 'emote:{"state": "jumping_jacks"}',
    "play_all": "play_all",
    "stop": "emote_stop",
}

# Maintenance / companion actions: name -> (desktop command, takes minutes?)
ACTIONS = {
    "reset_timers": ("reset_timers", False),
    "reset_all": ("reset_all", False),
    "open_folder": ("open_folder", False),
    "breathe": ("breathe", False),
    "eye_rest": ("eye_rest", False),
    "snooze": ("snooze", True),
    "snooze_off": ("snooze_off", False),
    "hide": ("hide", True),
    "show": ("show", False),
    "come_here": ("come_here", False),
    "go_home": ("go_home", False),
    "scene": ("scene", False),
    "scene_stop": ("scene_stop", False),
    "quit": ("quit", False),
}


def desktop(command="status"):
    with socket.create_connection(("127.0.0.1", 50577), timeout=3) as connection:
        connection.settimeout(1)
        connection.sendall(command.encode("utf-8"))
        chunks = []
        while True:  # the engine closes the socket after its reply
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if len(chunks) > 64:
                break
        raw = b"".join(chunks)
        if not raw:
            raise RuntimeError("DeskPal could not run that command (details in log.txt).")
        result = json.loads(raw.decode("utf-8"))
        if result.get("app") != "DeskPal":
            raise ValueError("Unexpected desktop response")
        return result


def launcher_alive():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return json.load(response).get("service") == "deskpal-launcher"
    except (OSError, ValueError, RuntimeError):
        return False


def _python_windowless():
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    if os.name == "nt" and windowless.exists():
        return str(windowless)
    return str(executable)


def ensure_launcher():
    """Make sure this loopback server is running; returns its base URL."""
    if launcher_alive():
        return URL
    subprocess.Popen([_python_windowless(), str(ROOT / "deskpal_launch_server.py")],
                     cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):
        time.sleep(0.15)
        if launcher_alive():
            return URL
    raise RuntimeError("The DeskPal launcher did not start.")


def _browser_candidates():
    """Chromium browsers that support --app (a chromeless desktop window)."""
    found = []
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("LocalAppData", "")]
        rel = [r"Microsoft\Edge\Application\msedge.exe",
               r"Google\Chrome\Application\chrome.exe",
               r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        for base in roots:
            for r in rel:
                p = os.path.join(base, r)
                if base and os.path.exists(p):
                    found.append(p)
    for name in ("msedge", "chrome", "google-chrome", "chromium", "brave"):
        p = shutil.which(name)
        if p:
            found.append(p)
    seen, out = set(), []
    for p in found:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def open_app_window(url):
    """Open URL as its own desktop window (no tabs / address bar).
    Returns True when something opened."""
    profile = Path(os.environ.get("APPDATA") or Path.home()) / "DeskPal" / "app-window"
    for exe in _browser_candidates():
        try:
            profile.mkdir(parents=True, exist_ok=True)
            subprocess.Popen([exe, "--app=" + url, "--window-size=1320,880",
                              "--user-data-dir=" + str(profile),
                              "--no-first-run", "--no-default-browser-check",
                              "--disable-features=Translate,msEdgeShoppingIntegration"],
                             cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return webbrowser.open(url)


def launch():
    with LAUNCH_LOCK:
        try:
            return desktop("launch")
        except ConnectionRefusedError:
            pass
        except (OSError, ValueError, RuntimeError):
            raise RuntimeError("Quit the older DeskPal from its right-click menu, then launch again.")
        subprocess.Popen([_python_windowless(), str(ROOT / "deskpal.py"), "--desktop-launch"],
                         cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(60):
            time.sleep(0.15)
            try:
                state = desktop()
                if state.get("visible") and state.get("character") == "custom":
                    return state
            except (OSError, ValueError, RuntimeError):
                pass
        raise RuntimeError("DeskPal did not finish starting. Try the troubleshooting launcher in this folder.")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass

    def send_json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        body = json.loads(raw_body)
        return body if isinstance(body, dict) else {}

    def valid_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        if not self.valid_host():
            return self.send_error(403)
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            return self.send_json(200, {"service": "deskpal-launcher", "version": 2,
                                        "dashboard": URL + "/dashboard"})
        if path == "/api/status":
            try:
                return self.send_json(200, desktop())
            except (OSError, ValueError, RuntimeError):
                return self.send_json(200, {"running": False})
        if path == "/api/settings":
            try:
                res = desktop("settings_get")
                return self.send_json(200, res.get("settings", {}))
            except (OSError, ValueError, RuntimeError):
                return self.send_json(503, {"error": "Desktop app offline"})
        if path == "/api/stats":
            try:
                res = desktop("stats")
                return self.send_json(200, res.get("stats", {}))
            except (OSError, ValueError, RuntimeError):
                return self.send_json(503, {"error": "Desktop app offline"})
        if path == "/":
            self.path = "/ganesh_showcase.html"
        elif path in ("/dashboard", "/settings", "/app"):
            self.path = "/deskpal_dashboard.html"
        elif path not in ("/ganesh_showcase.html", "/ganesh_showcase.css", "/ganesh_showcase.js",
                          "/deskpal_dashboard.html", "/deskpal_dashboard.css", "/deskpal_dashboard.js"):
            if not (path.startswith("/assets/ganesh/") and path.endswith(".png")
                    and Path(path).name == path.removeprefix("/assets/ganesh/")):
                return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if (not self.valid_host() or self.headers.get("X-DeskPal-Launch") != "1"
                or self.headers.get("Origin") not in (URL, f"http://localhost:{PORT}")):
            return self.send_error(403)
        try:
            if self.path == "/api/launch":
                return self.send_json(200, launch())
            if self.path == "/api/settings":
                body = self.read_body()
                res = desktop(f"settings_set:{json.dumps(body)}")
                out = res.get("settings", {})
                if res.get("note"):
                    out["note"] = res["note"]
                return self.send_json(200, out)
            if self.path == "/api/exercise_done":
                res = desktop("exercise_done")
                return self.send_json(200, res.get("stats", {}))
            if self.path == "/api/focus":
                body = self.read_body()
                action = body.get("action")
                if action == "start":
                    minutes = body.get("minutes", 25)
                    res = desktop(f"focus_start:{json.dumps({'minutes': minutes})}")
                elif action == "stop":
                    res = desktop("focus_stop")
                elif action == "break":
                    res = desktop("break_start")
                else:
                    return self.send_error(400)
                return self.send_json(200, res.get("stats", {}))
            if self.path == "/api/goals":
                body = self.read_body()
                action = body.get("action")
                if action == "add":
                    res = desktop(f"goals_add:{json.dumps({'name': body.get('name', '')})}")
                elif action == "toggle":
                    res = desktop(f"goals_toggle:{json.dumps({'id': body.get('id', '')})}")
                elif action == "delete":
                    res = desktop(f"goals_delete:{json.dumps({'id': body.get('id', '')})}")
                else:
                    return self.send_error(400)
                return self.send_json(200, res.get("stats", {}))
            if self.path == "/api/action":
                body = self.read_body()
                action = body.get("action")
                if action not in ACTIONS:
                    return self.send_error(400)
                command, takes_minutes = ACTIONS[action]
                if takes_minutes:
                    try:
                        minutes = max(1, min(720, int(body.get("minutes", 30))))
                    except (TypeError, ValueError):
                        minutes = 30
                    command = f"{command}:{json.dumps({'minutes': minutes})}"
                return self.send_json(200, desktop(command))
            mode = self.path.removeprefix("/api/emote/")
            if self.path.startswith("/api/emote/") and mode in EMOTES:
                return self.send_json(200, desktop(EMOTES[mode]))
            return self.send_error(404)
        except (OSError, ValueError, RuntimeError) as error:
            return self.send_json(503, {"error": str(error) or "Please launch DeskPal again."})


def _open_ui():
    """--app starts the buddy and opens the dashboard as a desktop window;
    --open opens the classic launch page in the default browser."""
    if "--app" in sys.argv:
        def start_buddy():
            try:
                launch()
            except (OSError, ValueError, RuntimeError):
                pass  # the dashboard shows a Launch button when this fails
        threading.Thread(target=start_buddy, daemon=True).start()
        open_app_window(URL + "/dashboard")
    elif "--open" in sys.argv:
        webbrowser.open(URL)


def main():
    if launcher_alive():
        _open_ui()
        return
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if getattr(e, "errno", None) == 10048 or "10048" in str(e):
            print(f"Port {PORT} is already in use by another application.")
            _open_ui()
            return
        raise
    _open_ui()
    server.serve_forever()



if __name__ == "__main__":
    main()
