# -*- coding: utf-8 -*-
"""
==========================================================================
  DeskPal  -  your kawaii desktop buddy
==========================================================================
  A friendly animated companion that lives on top of every window on your
  Windows desktop.  It walks around, reacts to you, keeps an eye on your
  battery and your working time, and nudges you to take breaks, drink
  water, rest your eyes, stretch and breathe.

  * Pure Python standard library.  No pip installs, no internet, nothing
    to configure.  Just Python + this file.
  * Runs on Windows 10 / 11 (also starts on macOS / Linux with reduced
    transparency support, which is only used for development).

  Right-click the buddy for the menu.  Left-click to pet it.  Drag to move.

  Written to be sturdy: every optional feature is wrapped so that a
  failure degrades quietly instead of crashing your buddy.
==========================================================================
"""

import ctypes
import json
import math
import os
import random
import shutil
from collections import deque
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog

APP_NAME = "DeskPal"
APP_VERSION = "1.4"
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# The colour that becomes 100% see-through (and click-through) on Windows.
# Nothing in the artwork is allowed to use this exact colour.
KEY_COLOR = "#FF00FE"

# Single-instance guard port (loopback only, nothing is exposed).
LOCK_PORT = 50577

# Display scaling factor (1.0 at 96 dpi, 1.5 on a 150% laptop screen).
# Filled in at startup by main(); everything the buddy draws is multiplied
# by it so the artwork keeps its real-world size on high resolution screens.
UI_K = 1.0


# --------------------------------------------------------------------------
#  Paths & logging
# --------------------------------------------------------------------------
def app_dir():
    """Folder where settings/stats/log live.  Created on demand."""
    try:
        if IS_WIN:
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
        elif IS_MAC:
            base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        d = os.path.join(base, APP_NAME)
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d


DATA_DIR = app_dir()
PROJECT_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ganesh")
GANESH_BUNDLED_IDLE = os.path.join(PROJECT_ASSET_DIR, "ganesh_stand.png")
CONFIG_PATH = os.path.join(DATA_DIR, "settings.json")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")
LOG_PATH = os.path.join(DATA_DIR, "log.txt")
NOTIFY_PATH = os.path.join(DATA_DIR, "notify.txt")   # other tools (e.g. Claude Code) drop lines here
CUSTOM_IDLE_PATH = os.path.join(DATA_DIR, "custom_idle.png")     # everyday pose
CUSTOM_URGENT_PATH = os.path.join(DATA_DIR, "custom_urgent.png")  # optional second pose for urgent moments


def log(msg):
    """Append a line to the log file.  Never raises."""
    try:
        line = "[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
        # keep the log small
        try:
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 400000:
                os.remove(LOG_PATH)
        except Exception:
            pass
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(line)
    except Exception:
        pass


def log_exc(where):
    try:
        log("ERROR in %s\n%s" % (where, traceback.format_exc()))
    except Exception:
        pass


def safe(fn, *a, **kw):
    """Call fn, swallow (and log) any exception.  Returns None on failure."""
    try:
        return fn(*a, **kw)
    except Exception:
        log_exc(getattr(fn, "__name__", "call"))
        return None


# --------------------------------------------------------------------------
#  Windows plumbing (all optional - every call degrades to a safe default)
# --------------------------------------------------------------------------
class Win:
    """Thin ctypes wrapper around the few Win32 calls the buddy uses."""

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080      # keep out of Alt-Tab and the taskbar
    WS_EX_NOACTIVATE = 0x08000000      # never steal keyboard focus
    WS_EX_TOPMOST = 0x00000008
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040

    def __init__(self):
        self.ok = False
        self.user32 = None
        self.kernel32 = None
        if not IS_WIN:
            return
        try:
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.ok = True
        except Exception:
            log_exc("Win.__init__")
            self.ok = False

    # ---- DPI -------------------------------------------------------------
    def make_dpi_aware(self):
        """Crisp rendering + real pixel coordinates on scaled displays."""
        if not IS_WIN:
            return
        try:
            # Per-monitor-v2 if available, else system DPI aware.
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                return
            except Exception:
                pass
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                return
            except Exception:
                pass
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            log_exc("make_dpi_aware")

    def system_dpi(self):
        """Dots per inch of the main display (96 = 100% scaling)."""
        if not self.ok:
            return 96.0
        try:
            try:
                d = float(self.user32.GetDpiForSystem())
                if d > 0:
                    return d
            except Exception:
                pass
            hdc = self.user32.GetDC(0)
            try:
                d = float(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
            finally:
                self.user32.ReleaseDC(0, hdc)
            return d if d > 0 else 96.0
        except Exception:
            return 96.0

    # ---- window handles --------------------------------------------------
    def hwnd_of(self, widget):
        """Top-level HWND for a Tk window."""
        if not self.ok:
            return None
        try:
            wid = widget.winfo_id()
            parent = self.user32.GetParent(wid)
            return parent if parent else wid
        except Exception:
            return None

    def set_tool_window(self, widget, no_activate=True):
        """Hide from Alt-Tab / taskbar, and optionally never take focus."""
        if not self.ok:
            return
        try:
            hwnd = self.hwnd_of(widget)
            if not hwnd:
                return
            try:
                get_l = self.user32.GetWindowLongPtrW
                set_l = self.user32.SetWindowLongPtrW
            except AttributeError:
                get_l = self.user32.GetWindowLongW
                set_l = self.user32.SetWindowLongW
            style = get_l(hwnd, self.GWL_EXSTYLE)
            style |= self.WS_EX_TOOLWINDOW
            if no_activate:
                style |= self.WS_EX_NOACTIVATE
            set_l(hwnd, self.GWL_EXSTYLE, style)
        except Exception:
            log_exc("set_tool_window")

    def push_topmost(self, widget):
        """Re-assert 'above everything' without stealing focus."""
        if not self.ok:
            return
        try:
            hwnd = self.hwnd_of(widget)
            if not hwnd:
                return
            self.user32.SetWindowPos(
                hwnd, self.HWND_TOPMOST, 0, 0, 0, 0,
                self.SWP_NOSIZE | self.SWP_NOMOVE | self.SWP_NOACTIVATE)
        except Exception:
            pass

    # ---- user activity ---------------------------------------------------
    def idle_seconds(self):
        """Seconds since the last real keyboard/mouse input.  0.0 if unknown."""
        if not self.ok:
            return 0.0
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not self.user32.GetLastInputInfo(ctypes.byref(lii)):
                return 0.0
            now = self.kernel32.GetTickCount() & 0xFFFFFFFF
            delta = (now - (lii.dwTime & 0xFFFFFFFF)) & 0xFFFFFFFF
            return delta / 1000.0
        except Exception:
            return 0.0

    # ---- battery ---------------------------------------------------------
    def battery(self):
        """(percent or None, plugged_in bool or None)."""
        if not self.ok:
            return (None, None)
        try:
            class SPS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_ubyte),
                            ("BatteryFlag", ctypes.c_ubyte),
                            ("BatteryLifePercent", ctypes.c_ubyte),
                            ("SystemStatusFlag", ctypes.c_ubyte),
                            ("BatteryLifeTime", ctypes.c_ulong),
                            ("BatteryFullLifeTime", ctypes.c_ulong)]
            sps = SPS()
            if not self.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                return (None, None)
            pct = int(sps.BatteryLifePercent)
            if pct == 255:
                pct = None
            ac = int(sps.ACLineStatus)
            plugged = True if ac == 1 else (False if ac == 0 else None)
            return (pct, plugged)
        except Exception:
            return (None, None)

    # ---- foreground app --------------------------------------------------
    def active_window_title(self):
        if not self.ok:
            return ""
        try:
            hwnd = self.user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = self.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(min(max(length + 1, 2), 1024))
            self.user32.GetWindowTextW(hwnd, buf, len(buf))
            return buf.value or ""
        except Exception:
            return ""

    def foreground_is_fullscreen(self):
        """True when a game/video/presentation is covering a whole monitor."""
        if not self.ok:
            return False
        try:
            hwnd = self.user32.GetForegroundWindow()
            if not hwnd:
                return False
            shell = self.user32.GetShellWindow()
            desktop = self.user32.GetDesktopWindow()
            if hwnd in (shell, desktop):
                return False

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            r = RECT()
            if not self.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                return False
            sw = self.user32.GetSystemMetrics(0)
            sh = self.user32.GetSystemMetrics(1)
            return (r.right - r.left) >= sw and (r.bottom - r.top) >= sh
        except Exception:
            return False

    # ---- monitors --------------------------------------------------------
    def virtual_screen(self):
        """(x, y, w, h) covering every monitor, or None."""
        if not self.ok:
            return None
        try:
            x = self.user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
            y = self.user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
            w = self.user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
            h = self.user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
            if w <= 0 or h <= 0:
                return None
            return (x, y, w, h)
        except Exception:
            return None

    def work_area_at(self, px, py):
        """Usable rect (minus taskbar) of the monitor containing a point."""
        if not self.ok:
            return None
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT(int(px), int(py))
            hmon = self.user32.MonitorFromPoint(pt, 2)  # NEAREST
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if not self.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return None
            w = mi.rcWork
            return (w.left, w.top, w.right - w.left, w.bottom - w.top)
        except Exception:
            return None


WIN = Win()


# --------------------------------------------------------------------------
#  Gentle sounds (Windows only, non-blocking, never fatal)
# --------------------------------------------------------------------------
_winsound = None
if IS_WIN:
    try:
        import winsound as _winsound
    except Exception:
        _winsound = None


def play_chime(kind="soft"):
    """Short pleasant tone sequence on a background thread."""
    if not _winsound:
        return
    patterns = {
        "soft":   [(659, 90), (784, 130)],
        "up":     [(587, 80), (740, 80), (880, 150)],
        "down":   [(740, 90), (587, 150)],
        "happy":  [(784, 70), (988, 70), (1175, 160)],
        "calm":   [(523, 180), (659, 260)],
        "alert":  [(880, 100), (0, 60), (880, 100)],
    }
    seq = patterns.get(kind, patterns["soft"])

    def run():
        try:
            for freq, dur in seq:
                if freq <= 0:
                    time.sleep(dur / 1000.0)
                else:
                    _winsound.Beep(int(freq), int(dur))
        except Exception:
            pass

    try:
        threading.Thread(target=run, daemon=True).start()
    except Exception:
        pass


# --------------------------------------------------------------------------
#  Settings
# --------------------------------------------------------------------------
DEFAULTS = {
    "character": "dog",            # dog | cat | human | custom
    "pet_name": "Mochi",
    "scale": 1.0,                  # 0.6 .. 1.6
    "pos_x": None,
    "pos_y": None,

    # reminders -----------------------------------------------------------
    "break_on": True,
    "break_every": 45,             # minutes of ACTIVE work
    "break_len": 5,                # minutes suggested
    "eye_on": True,
    "eye_every": 20,
    "water_on": True,
    "water_every": 60,
    "stretch_on": True,
    "stretch_every": 90,
    "posture_on": True,
    "posture_every": 30,
    "hunger_on": True,
    "hunger_every": 150,
    "meditate_on": True,
    "meditate_every": 180,
    "breath_pattern": "box",       # box | 478 | calm
    "breath_cycles": 6,
    "dim_on_breathe": True,

    # focus ---------------------------------------------------------------
    "focus_len": 25,
    "focus_break": 5,

    # system --------------------------------------------------------------
    "battery_on": True,
    "battery_low": 20,
    "night_on": True,
    "night_hour": 23,
    "greet_on": True,
    "same_app_on": True,
    "same_app_mins": 90,

    # routine (set during onboarding) --------------------------------------
    "work_start_hour": 9,
    "work_end_hour": 18,
    "breakfast_on": True,
    "breakfast_hour": 8,
    "lunch_on": True,
    "lunch_hour": 13,
    "dinner_on": True,
    "dinner_hour": 20,
    "onboarded": False,

    # behaviour -----------------------------------------------------------
    "sounds": True,
    "speech": True,
    "wander": True,
    "wander_every": 3,             # minutes
    "idle_pause": 5,               # pause reminders after N idle minutes
    "quiet_on": False,
    "quiet_from": 22,
    "quiet_to": 8,
    "skip_fullscreen": True,
    "always_on_top": True,
    "autostart": False,
    "fps": 30,
    "first_run": True,

    # daily health targets shown as rings in the app ---------------------
    "water_target": 8,             # glasses
    "eye_target": 10,              # eye rests
    "stretch_target": 6,
    "posture_target": 8,
    "break_target": 6,
    "focus_target": 4,             # completed focus sessions
    "active_target": 360,          # minutes of active desk time

    # what the companion says on each card ("" = built-in phrases) -------
    "break_msg": "",
    "eye_msg": "",
    "water_msg": "",
    "stretch_msg": "",
    "posture_msg": "",
    "hunger_msg": "",
    "meditate_msg": "",

    # only remind between work_start_hour and work_end_hour ---------------
    "work_hours_only": False,

    # custom productivity goals (list of {id, name, target, created}) -----
    "goals": [],

    # user-defined reminders (list of {id, name, every, on, msg}) ---------
    "custom_reminders": [],
}

TARGET_LIMITS = {
    "water_target": (1, 30), "eye_target": (1, 40), "stretch_target": (1, 30),
    "posture_target": (1, 40), "break_target": (1, 30), "focus_target": (1, 20),
    "active_target": (30, 900),
}
REMINDER_MSG_KEYS = ("break_msg", "eye_msg", "water_msg", "stretch_msg",
                     "posture_msg", "hunger_msg", "meditate_msg")


class Config(dict):
    """Settings dict that knows how to load/save itself.  Never raises."""

    def __init__(self):
        super().__init__()
        self.update(DEFAULTS)
        self.load()

    def load(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k in DEFAULTS:
                            # keep the declared type where we can
                            want = DEFAULTS[k]
                            if isinstance(want, bool):
                                self[k] = bool(v)
                            elif isinstance(want, int) and not isinstance(want, bool) and v is not None:
                                try:
                                    self[k] = int(v)
                                except Exception:
                                    pass
                            elif isinstance(want, float) and v is not None:
                                try:
                                    self[k] = float(v)
                                except Exception:
                                    pass
                            else:
                                self[k] = v
        except Exception:
            log_exc("Config.load")

    def save(self):
        try:
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self), fh, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            log_exc("Config.save")

    def clamp(self):
        """Keep every value inside a sane range."""
        try:
            self["scale"] = max(0.5, min(2.0, float(self.get("scale", 1.0) or 1.0)))
            for key, lo, hi in (("break_every", 5, 240), ("break_len", 1, 60),
                                ("eye_every", 5, 180), ("water_every", 10, 360),
                                ("stretch_every", 10, 360), ("posture_every", 5, 240),
                                ("meditate_every", 15, 720), ("hunger_every", 30, 480),
                                ("focus_len", 5, 120),
                                ("focus_break", 1, 60), ("battery_low", 5, 50),
                                ("night_hour", 18, 23), ("wander_every", 1, 60),
                                ("idle_pause", 1, 60), ("breath_cycles", 2, 30),
                                ("same_app_mins", 15, 300), ("fps", 12, 60),
                                ("quiet_from", 0, 23), ("quiet_to", 0, 23),
                                ("work_start_hour", 0, 23), ("work_end_hour", 0, 23),
                                ("breakfast_hour", 0, 23), ("lunch_hour", 0, 23),
                                ("dinner_hour", 0, 23)):
                try:
                    self[key] = max(lo, min(hi, int(self.get(key, DEFAULTS[key]))))
                except Exception:
                    self[key] = DEFAULTS[key]
            for key, (lo, hi) in TARGET_LIMITS.items():
                try:
                    self[key] = max(lo, min(hi, int(self.get(key, DEFAULTS[key]))))
                except Exception:
                    self[key] = DEFAULTS[key]
            for key in REMINDER_MSG_KEYS:
                self[key] = str(self.get(key) or "").strip()[:140]
            self["custom_reminders"] = self._clean_custom(self.get("custom_reminders"))
            if self.get("character") not in ("dog", "cat", "human", "custom"):
                self["character"] = "dog"
            if self.get("breath_pattern") not in ("box", "478", "calm"):
                self["breath_pattern"] = "box"
            name = str(self.get("pet_name") or "").strip()
            self["pet_name"] = (name[:18] or "Mochi")
        except Exception:
            log_exc("Config.clamp")

    @staticmethod
    def _clean_custom(items):
        """Custom reminders: at most 12, every entry well-formed."""
        out = []
        seen = set()
        for it in (items or []) if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            rid = str(it.get("id") or "").strip()[:12]
            name = str(it.get("name") or "").strip()[:40]
            if not rid or not name or rid in seen:
                continue
            seen.add(rid)
            try:
                every = max(5, min(720, int(it.get("every", 60))))
            except Exception:
                every = 60
            out.append({"id": rid, "name": name, "every": every,
                        "on": bool(it.get("on", True)),
                        "msg": str(it.get("msg") or "").strip()[:140]})
            if len(out) >= 12:
                break
        return out


# --------------------------------------------------------------------------
#  Stats  (streaks + counters, one row per day)
# --------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.data = {"days": {}, "totals": {}}
        self.load()

    def load(self):
        try:
            if os.path.exists(STATS_PATH):
                with open(STATS_PATH, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                if isinstance(d, dict) and isinstance(d.get("days"), dict):
                    self.data = d
                    self.data.setdefault("totals", {})
        except Exception:
            log_exc("Stats.load")

    def save(self):
        try:
            # keep 120 days at most
            days = self.data.get("days", {})
            if len(days) > 120:
                for k in sorted(days.keys())[:-120]:
                    days.pop(k, None)
            tmp = STATS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, STATS_PATH)
        except Exception:
            log_exc("Stats.save")

    @staticmethod
    def today_key():
        return datetime.now().strftime("%Y-%m-%d")

    def bump(self, key, amount=1):
        try:
            day = self.data.setdefault("days", {}).setdefault(self.today_key(), {})
            day[key] = day.get(key, 0) + amount
            tot = self.data.setdefault("totals", {})
            tot[key] = tot.get(key, 0) + amount
            self.save()
        except Exception:
            log_exc("Stats.bump")

    def today(self, key):
        try:
            return self.data.get("days", {}).get(self.today_key(), {}).get(key, 0)
        except Exception:
            return 0

    def total(self, key):
        try:
            return self.data.get("totals", {}).get(key, 0)
        except Exception:
            return 0

    def last_days(self, n=7):
        """[(label, {counters}), ...] oldest first, including empty days."""
        out = []
        try:
            for i in range(n - 1, -1, -1):
                d = datetime.now() - timedelta(days=i)
                key = d.strftime("%Y-%m-%d")
                out.append((d.strftime("%a"), self.data.get("days", {}).get(key, {})))
        except Exception:
            log_exc("Stats.last_days")
        return out

    def streak(self):
        """Consecutive days (up to today) with at least one break taken."""
        return self.streak_for("breaks")

    def streak_for(self, key):
        """Consecutive days (up to today) with at least one count on `key`."""
        try:
            n = 0
            for i in range(0, 120):
                d = datetime.now() - timedelta(days=i)
                rec = self.data.get("days", {}).get(d.strftime("%Y-%m-%d"), {})
                if rec.get(key, 0) > 0:
                    n += 1
                elif i == 0:
                    continue          # today may not have happened yet
                else:
                    break
            return n
        except Exception:
            return 0


# --------------------------------------------------------------------------
#  Palette  (soft kawaii pastels + a strong readable ink outline)
# --------------------------------------------------------------------------
INK = "#5A4740"
INK_SOFT = "#8A7166"
WHITE = "#FFFFFF"
CREAM = "#FFF8EE"

BLUSH = "#FF9FB6"
PINK = "#FF8FB1"
MINT = "#6FD6BE"
LAV = "#A99BF0"
SUN = "#FFD05C"
SKY = "#7FC8F0"
PEACH = "#FFB088"
LEAF = "#8FD48A"

CHAR_COLORS = {
    "dog": {
        "body": "#F7C77F", "body_dark": "#E8AC5E", "light": "#FFF3DF",
        "ear": "#E09A50", "accent": "#FFD9A0", "collar": PINK,
    },
    "cat": {
        "body": "#DCD6F7", "body_dark": "#C3BAEA", "light": "#FFFFFF",
        "ear": "#F3B7CE", "accent": "#EFEAFF", "collar": MINT,
    },
    "human": {
        "body": "#FFCFA8", "body_dark": "#F0B489", "light": "#FFF0E2",
        "ear": "#FFCFA8", "accent": "#7FC8F0", "collar": LAV,
        "hair": "#6E4B63", "shirt": "#7FC8F0", "shirt_dark": "#5FA9D6",
    },
    "custom": {
        "body": "#DCD6F7", "body_dark": "#C3BAEA", "light": "#FFFFFF",
        "ear": "#DCD6F7", "accent": "#7FC8F0", "collar": LAV,
    },
}

# reminder card accents
ACCENTS = {
    "break": MINT, "eye": SKY, "water": SKY, "stretch": PEACH,
    "posture": LAV, "meditate": LAV, "focus": PINK, "battery": SUN,
    "night": LAV, "hello": SUN, "info": MINT, "cheer": PINK,
}


def shade(hex_color, factor):
    """Lighten (factor>1) or darken (factor<1) a #rrggbb colour."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if factor >= 1:
            r = r + (255 - r) * (factor - 1)
            g = g + (255 - g) * (factor - 1)
            b = b + (255 - b) * (factor - 1)
        else:
            r, g, b = r * factor, g * factor, b * factor
        return "#%02x%02x%02x" % (max(0, min(255, int(r))),
                                  max(0, min(255, int(g))),
                                  max(0, min(255, int(b))))
    except Exception:
        return hex_color


def mix(c1, c2, t):
    """Blend two #rrggbb colours, t=0 -> c1, t=1 -> c2."""
    try:
        t = max(0.0, min(1.0, t))
        a = c1.lstrip("#")
        b = c2.lstrip("#")
        out = []
        for i in (0, 2, 4):
            x = int(a[i:i + 2], 16)
            y = int(b[i:i + 2], 16)
            out.append(int(x + (y - x) * t))
        return "#%02x%02x%02x" % tuple(out)
    except Exception:
        return c1


# --------------------------------------------------------------------------
#  Fonts
# --------------------------------------------------------------------------
_FONT_FAMILY = None


def ui_font(size=10, bold=False, italic=False):
    """A font tuple that exists on this machine."""
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        fam = "Helvetica"
        try:
            families = set(tkfont.families())
            for cand in ("Segoe UI Variable Text", "Segoe UI", "Nirmala UI",
                         "Calibri", "DejaVu Sans", "Helvetica", "Arial"):
                if cand in families:
                    fam = cand
                    break
        except Exception:
            pass
        _FONT_FAMILY = fam
    style = ""
    if bold:
        style += " bold"
    if italic:
        style += " italic"
    return (_FONT_FAMILY, int(size), style.strip()) if style else (_FONT_FAMILY, int(size))


def sfont(size=10, bold=False, italic=False):
    """Font for the ordinary windows, scaled for the screen's DPI."""
    return ui_font(max(6, round(size * UI_K)), bold, italic)


# --------------------------------------------------------------------------
#  Easing helpers
# --------------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_in_out(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) * (1 - t)


def ease_out_back(t):
    t = clamp(t, 0.0, 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


def ease_out_elastic(t):
    t = clamp(t, 0.0, 1.0)
    if t in (0.0, 1.0):
        return t
    p = 0.35
    return pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p) + 1


def bounce(t):
    """0 -> 1 -> 0 hump."""
    return math.sin(clamp(t, 0.0, 1.0) * math.pi)


def rot(x, y, deg):
    """Rotate a point about the origin."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca)


# --------------------------------------------------------------------------
#  Painter - draws in "character units" and maps to canvas pixels
# --------------------------------------------------------------------------
class Painter:
    """
    Unit space: x grows right, y grows UP, origin at the character's feet.
    A character is about 100 units tall, so 1 unit ~= 1% of its height.
    """

    def __init__(self, canvas):
        self.c = canvas
        self.ox = 0.0
        self.oy = 0.0
        self.s = 1.0
        self.flip = 1          # -1 mirrors horizontally
        self.sx = 1.0          # squash / stretch
        self.sy = 1.0

    def setup(self, ox, oy, scale, flip=1, sx=1.0, sy=1.0):
        self.ox, self.oy, self.s = ox, oy, scale
        self.flip = -1 if flip < 0 else 1
        self.sx, self.sy = sx, sy

    # -- coordinate mapping ------------------------------------------------
    def p(self, x, y):
        return (self.ox + x * self.flip * self.sx * self.s,
                self.oy - y * self.sy * self.s)

    def w(self, units):
        return max(1, int(round(units * self.s)))

    # -- primitives --------------------------------------------------------
    def oval(self, cx, cy, rx, ry, fill=None, outline="", width=0, stipple=None, tags=None):
        x0, y0 = self.p(cx - rx, cy + ry)
        x1, y1 = self.p(cx + rx, cy - ry)
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        kw = {"fill": fill or "", "outline": outline or "",
              "width": self.w(width) if width else 0}
        if stipple:
            kw["stipple"] = stipple
        if tags:
            kw["tags"] = tags
        return self.c.create_oval(x0, y0, x1, y1, **kw)

    def poly(self, pts, fill=None, outline="", width=0, smooth=False, stipple=None):
        flat = []
        for (x, y) in pts:
            px, py = self.p(x, y)
            flat.extend((px, py))
        if len(flat) < 6:
            return None
        kw = {"fill": fill or "", "outline": outline or "",
              "width": self.w(width) if width else 0, "smooth": bool(smooth)}
        if smooth:
            kw["splinesteps"] = 16
        if stipple:
            kw["stipple"] = stipple
        return self.c.create_polygon(*flat, **kw)

    def line(self, pts, fill=INK, width=2, smooth=False, cap="round", joint="round"):
        flat = []
        for (x, y) in pts:
            px, py = self.p(x, y)
            flat.extend((px, py))
        if len(flat) < 4:
            return None
        return self.c.create_line(*flat, fill=fill, width=self.w(width),
                                  smooth=bool(smooth), splinesteps=16,
                                  capstyle=cap, joinstyle=joint)

    def arc(self, cx, cy, rx, ry, start, extent, outline=INK, width=2,
            style=tk.ARC, fill=None):
        x0, y0 = self.p(cx - rx, cy + ry)
        x1, y1 = self.p(cx + rx, cy - ry)
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        st = start if self.flip > 0 else 180 - start - extent
        return self.c.create_arc(x0, y0, x1, y1, start=st, extent=extent,
                                 style=style, outline=outline or "",
                                 fill=fill or "", width=self.w(width))

    def text(self, x, y, txt, fill=INK, size=10, bold=False, anchor="center"):
        px, py = self.p(x, y)
        return self.c.create_text(px, py, text=txt, fill=fill, anchor=anchor,
                                  font=ui_font(max(6, int(size * self.s)), bold))

    def image(self, cx, cy, photo, anchor="center"):
        """Place a pre-loaded tk.PhotoImage - used by the custom-photo character."""
        px, py = self.p(cx, cy)
        return self.c.create_image(px, py, image=photo, anchor=anchor)

    def star(self, cx, cy, r, fill=SUN, outline="", points=5, rotation=0, width=0):
        pts = []
        for i in range(points * 2):
            rad = r if i % 2 == 0 else r * 0.45
            ang = rotation + i * (180.0 / points)
            a = math.radians(ang - 90)
            pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
        return self.poly(pts, fill=fill, outline=outline, width=width)

    def heart(self, cx, cy, r, fill=PINK, outline="", width=0, rotation=0):
        pts = []
        for i in range(0, 361, 12):
            t = math.radians(i)
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            x, y = x / 16.0 * r, y / 16.0 * r
            if rotation:
                x, y = rot(x, y, rotation)
            pts.append((cx + x, cy + y))
        return self.poly(pts, fill=fill, outline=outline, width=width, smooth=True)

    def sparkle(self, cx, cy, r, fill=WHITE, rotation=0):
        pts = []
        for i in range(8):
            rad = r if i % 2 == 0 else r * 0.22
            a = math.radians(rotation + i * 45 - 90)
            pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
        return self.poly(pts, fill=fill, smooth=False)

    def round_rect(self, x0, y0, x1, y1, r, fill=WHITE, outline=INK, width=2, smooth=True):
        """Rounded rectangle in unit space (y0 is the BOTTOM edge)."""
        r = min(r, abs(x1 - x0) / 2.0, abs(y1 - y0) / 2.0)
        pts = [
            (x0 + r, y0), (x1 - r, y0), (x1, y0), (x1, y0 + r),
            (x1, y1 - r), (x1, y1), (x1 - r, y1), (x0 + r, y1),
            (x0, y1), (x0, y1 - r), (x0, y0 + r), (x0, y0),
        ]
        return self.poly(pts, fill=fill, outline=outline, width=width, smooth=smooth)


def px_round_rect(canvas, x0, y0, x1, y1, r, **kw):
    """Rounded rectangle directly in canvas pixels (used by panels/cards)."""
    r = max(0, min(r, abs(x1 - x0) / 2.0, abs(y1 - y0) / 2.0))
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    kw.setdefault("smooth", True)
    kw.setdefault("splinesteps", 16)
    return canvas.create_polygon(*pts, **kw)


# --------------------------------------------------------------------------
#  Particles  (hearts, sparkles, confetti, Zzz, music notes, water drops...)
# --------------------------------------------------------------------------
class Particles:
    MAX = 160

    def __init__(self):
        self.items = []

    def clear(self):
        self.items = []

    def emit(self, kind, x, y, n=8, spread=1.0, power=1.0, color=None):
        try:
            for _ in range(int(n)):
                if len(self.items) >= self.MAX:
                    return
                ang = random.uniform(40, 140)
                spd = random.uniform(18, 46) * power
                self.items.append({
                    "k": kind,
                    "x": x + random.uniform(-10, 10) * spread,
                    "y": y + random.uniform(-6, 6) * spread,
                    "vx": math.cos(math.radians(ang)) * spd * random.uniform(0.4, 1.2),
                    "vy": math.sin(math.radians(ang)) * spd,
                    "life": random.uniform(0.8, 1.7),
                    "age": 0.0,
                    "r": random.uniform(3.2, 6.4),
                    "rot": random.uniform(0, 360),
                    "spin": random.uniform(-260, 260),
                    "col": color or random.choice([PINK, SUN, MINT, LAV, SKY, PEACH]),
                })
        except Exception:
            log_exc("Particles.emit")

    def burst_ring(self, kind, x, y, n=10, radius=14, color=None):
        try:
            for i in range(int(n)):
                if len(self.items) >= self.MAX:
                    return
                a = math.radians(i * (360.0 / max(1, n)))
                self.items.append({
                    "k": kind, "x": x + math.cos(a) * radius * 0.2,
                    "y": y + math.sin(a) * radius * 0.2,
                    "vx": math.cos(a) * 34, "vy": math.sin(a) * 34,
                    "life": 0.9, "age": 0.0, "r": random.uniform(3.0, 5.0),
                    "rot": random.uniform(0, 360), "spin": random.uniform(-200, 200),
                    "col": color or random.choice([PINK, SUN, MINT, LAV]),
                })
        except Exception:
            log_exc("Particles.burst_ring")

    def update(self, dt):
        try:
            alive = []
            for p in self.items:
                p["age"] += dt
                if p["age"] >= p["life"]:
                    continue
                k = p["k"]
                if k == "zzz":
                    p["x"] += (p["vx"] * 0.25) * dt
                    p["y"] += 22 * dt
                elif k == "drop":
                    p["vy"] -= 120 * dt
                    p["x"] += p["vx"] * dt
                    p["y"] += p["vy"] * dt
                elif k in ("confetti", "leaf"):
                    p["vy"] -= 70 * dt
                    p["x"] += (p["vx"] + math.sin(p["age"] * 6) * 16) * dt
                    p["y"] += p["vy"] * dt
                else:
                    p["vy"] -= 26 * dt
                    p["x"] += p["vx"] * dt
                    p["y"] += p["vy"] * dt
                p["rot"] += p["spin"] * dt
                alive.append(p)
            self.items = alive
        except Exception:
            log_exc("Particles.update")
            self.items = []

    def draw(self, pn):
        try:
            for p in self.items:
                t = p["age"] / max(0.001, p["life"])
                fade = 1.0 - t
                r = p["r"] * (0.5 + 0.9 * (1 - abs(0.5 - t) * 2) + 0.3)
                k, x, y, col = p["k"], p["x"], p["y"], p["col"]
                stip = None
                if fade < 0.35:
                    stip = "gray50"
                elif fade < 0.6:
                    stip = "gray75"
                if k == "heart":
                    pn.heart(x, y, r * 1.15, fill=col, rotation=p["rot"] * 0.15)
                elif k == "star":
                    pn.star(x, y, r * 1.2, fill=col, rotation=p["rot"])
                elif k == "sparkle":
                    pn.sparkle(x, y, r * 1.3, fill=col, rotation=p["rot"])
                elif k == "confetti":
                    hw, hh = r * 0.9, r * 0.5
                    pts = [rot(-hw, -hh, p["rot"]), rot(hw, -hh, p["rot"]),
                           rot(hw, hh, p["rot"]), rot(-hw, hh, p["rot"])]
                    pn.poly([(x + a, y + b) for a, b in pts], fill=col)
                elif k == "zzz":
                    pn.text(x, y, "z", fill=col, size=int(6 + r), bold=True)
                elif k == "question":
                    pn.text(x, y, "?", fill=col, size=int(8 + r), bold=True)
                elif k == "exclaim":
                    pn.text(x, y, "!", fill=col, size=int(8 + r), bold=True)
                elif k == "drop":
                    pn.oval(x, y, r * 0.65, r * 0.85, fill=SKY)
                    pn.oval(x - r * 0.2, y + r * 0.25, r * 0.18, r * 0.22, fill=WHITE)
                elif k == "note":
                    pn.oval(x, y, r * 0.6, r * 0.45, fill=col)
                    pn.line([(x + r * 0.55, y), (x + r * 0.55, y + r * 1.6)], fill=col, width=1.6)
                elif k == "leaf":
                    pn.oval(x, y, r * 0.9, r * 0.45, fill=LEAF, stipple=stip)
                elif k == "bubble":
                    pn.oval(x, y, r, r, fill="", outline=col, width=1.6)
                elif k == "rat":
                    pn.oval(x, y, r * 0.85, r * 0.55, fill=col)
                    pn.oval(x - r * 0.6, y - r * 0.15, r * 0.28, r * 0.28, fill=col)
                    pn.line([(x + r * 0.75, y + r * 0.1), (x + r * 1.3, y - r * 0.15)],
                            fill=col, width=1.2, smooth=True)
                elif k == "modak":
                    pn.oval(x, y, r * 0.72, r * 0.62, fill="#FFE9B8", outline="#E8B23D", width=1)
                    pn.poly([(x - r * 0.3, y - r * 0.3), (x, y - r * 0.85), (x + r * 0.3, y - r * 0.3)],
                            fill="#FFE9B8", outline="#E8B23D", width=1)
                else:
                    pn.oval(x, y, r * 0.6, r * 0.6, fill=col, stipple=stip)
        except Exception:
            log_exc("Particles.draw")


# --------------------------------------------------------------------------
#  Shared face parts
# --------------------------------------------------------------------------
def draw_shadow(pn, w=30, alpha="gray50"):
    pn.oval(0, 1.5, w, w * 0.22, fill=INK_SOFT, stipple=alpha)


def draw_eye(pn, x, y, r, style="normal", open_amt=1.0, dx=0.0, dy=0.0, ink=INK):
    """One big shiny kawaii eye."""
    try:
        if style == "closed" or open_amt <= 0.06:
            pn.line([(x - r * 1.05, y), (x - r * 0.4, y + r * 0.42),
                     (x + r * 0.4, y + r * 0.42), (x + r * 1.05, y)],
                    fill=ink, width=2.1, smooth=True)
            return
        if style == "happy":          # ^ ^
            pn.line([(x - r * 1.1, y - r * 0.25), (x, y + r * 0.75),
                     (x + r * 1.1, y - r * 0.25)], fill=ink, width=2.3, smooth=True)
            return
        if style == "sleep":          # gentle downward curve
            pn.arc(x, y + r * 0.1, r * 1.15, r * 0.9, 200, 140, outline=ink, width=2.1)
            return
        if style == "heart":
            pn.heart(x, y, r * 1.25, fill=PINK)
            pn.oval(x - r * 0.35, y + r * 0.35, r * 0.16, r * 0.2, fill=WHITE)
            return
        if style == "dizzy":
            pts = []
            for i in range(0, 540, 20):
                a = math.radians(i)
                rr = r * 1.15 * (i / 540.0)
                pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
            pn.line(pts, fill=ink, width=1.8, smooth=True)
            return

        oy = r * (1.0 - open_amt) * 0.5
        ry = max(r * 0.12, r * open_amt)
        pn.oval(x, y, r, ry, fill=ink)                             # eyeball
        if open_amt > 0.45:
            pn.oval(x + dx * r * 0.28 - r * 0.3, y + dy * r * 0.2 + ry * 0.35,
                    r * 0.3, ry * 0.3, fill=WHITE)                 # big highlight
            pn.oval(x + dx * r * 0.28 + r * 0.35, y + dy * r * 0.2 - ry * 0.3,
                    r * 0.15, ry * 0.16, fill=WHITE)               # small highlight
        del oy
    except Exception:
        log_exc("draw_eye")


def draw_blush(pn, x, y, r, amount=1.0):
    if amount <= 0.02:
        return
    st = "gray50" if amount < 0.75 else None
    pn.oval(x, y, r, r * 0.62, fill=BLUSH, stipple=st)


def draw_mouth(pn, x, y, style="smile", w=7.0, open_amt=0.0, ink=INK):
    try:
        if style == "cat":            # the classic w
            pn.line([(x - w, y + w * 0.45), (x - w * 0.5, y - w * 0.15),
                     (x, y + w * 0.3), (x + w * 0.5, y - w * 0.15),
                     (x + w, y + w * 0.45)], fill=ink, width=2.0, smooth=True)
        elif style == "smile":
            pn.arc(x, y + w * 0.5, w, w * 0.75, 200, 140, outline=ink, width=2.1)
        elif style == "wide":
            pn.arc(x, y + w * 0.8, w * 1.25, w * 1.1, 195, 150, outline=ink, width=2.2)
        elif style == "flat":
            pn.line([(x - w * 0.6, y), (x + w * 0.6, y)], fill=ink, width=2.0)
        elif style == "sad":
            pn.arc(x, y - w * 0.5, w, w * 0.7, 20, 140, outline=ink, width=2.1)
        elif style in ("open", "yawn", "o"):
            h = w * (0.55 + open_amt * 1.15) if style != "o" else w * 0.55
            pn.oval(x, y - h * 0.35, w * 0.62, h, fill="#7A4A52", outline=ink, width=1.6)
            pn.oval(x, y - h * 0.95, w * 0.42, h * 0.38, fill=PINK)   # tongue
    except Exception:
        log_exc("draw_mouth")


def draw_zzz_tag(pn, x, y, t):
    """Little floating Z near a sleeping head (drawn, not a particle)."""
    for i in range(3):
        ph = (t * 0.6 + i * 0.33) % 1.0
        pn.text(x + 6 * i + ph * 6, y + 6 * i + ph * 10, "z",
                fill=LAV, size=int(7 + i * 2), bold=True)



def draw_curl_tail(pn, base, shape, angle, color, width, tip_r, tip_color):
    """A tail drawn as a curved stroke that swings around its base."""
    pts = []
    for (dx, dy) in shape:
        rx, ry = rot(dx, dy, angle)
        pts.append((base[0] + rx, base[1] + ry))
    pn.line(pts, fill=color, width=width, smooth=True)
    pn.oval(pts[-1][0], pts[-1][1], tip_r, tip_r, fill=tip_color)


# --------------------------------------------------------------------------
#  DOG
# --------------------------------------------------------------------------
def draw_dog(pn, P, col):
    body, dark, light = col["body"], col["body_dark"], col["light"]
    ear_c, collar = col["ear"], col["collar"]
    pose = P.get("pose", "stand")
    legp = P.get("leg_phase", 0.0)
    walk = P.get("walk", 0.0)
    tail_a = P.get("tail", 0.0)
    ear_a = P.get("ear", 0.0)
    arm = P.get("arm", 0.0)
    hy = P.get("head_y", 0.0)
    hx = P.get("head_x", 0.0)

    draw_shadow(pn, 27 if pose == "stand" else 30)

    # ---- curly tail (behind the body) ------------------------------------
    t_base = (-22, 26) if pose != "lie" else (-25, 13)
    draw_curl_tail(pn, t_base,
                   [(0, 0), (-14, 7), (-18, 21), (-8, 30), (2, 25)],
                   tail_a * 0.9, dark, 8.0, 5.0, light)

    # ---- legs ------------------------------------------------------------
    if pose == "stand":
        for i, lx in enumerate((-15, 15)):
            sw = math.sin(legp + i * math.pi) * 7 * walk
            pn.line([(lx, 20), (lx + sw, 4)], fill=dark, width=9, smooth=True)
            pn.oval(lx + sw, 3.5, 6.2, 4.2, fill=light)
        for i, lx in enumerate((-9, 9)):
            sw = math.sin(legp + math.pi + i * math.pi) * 6 * walk
            pn.line([(lx, 26), (lx + sw, 5)], fill=body, width=9, smooth=True)
            pn.oval(lx + sw, 4.2, 5.8, 4.0, fill=light)
    elif pose in ("sit", "lotus"):
        pn.oval(-19, 12, 11, 11, fill=dark)
        pn.oval(19, 12, 11, 11, fill=dark)
        for lx in (-10, 10):
            pn.line([(lx, 22), (lx, 6)], fill=body, width=9, smooth=True)
            pn.oval(lx, 5, 6.0, 4.0, fill=light)
    else:  # lie
        pn.oval(-20, 9, 13, 8, fill=dark)
        pn.oval(20, 9, 13, 8, fill=dark)
        for lx in (-13, 13):
            pn.oval(lx, 7, 7.5, 4.6, fill=light)

    # ---- body ------------------------------------------------------------
    if pose == "lie":
        pn.oval(0, 17, 30, 15, fill=body, outline=dark, width=1.4)
        pn.oval(2, 14, 20, 10, fill=light)
    elif pose in ("sit", "lotus"):
        pn.oval(0, 30, 24, 25, fill=body, outline=dark, width=1.4)
        pn.oval(0, 25, 15, 17, fill=light)
    else:
        pn.oval(0, 34, 25, 23, fill=body, outline=dark, width=1.4)
        pn.oval(0, 30, 16, 16, fill=light)

    # ---- front paws / arms (only when actually raised) -------------------
    if abs(arm) > 0.01:
        ax, ay = 22, 32
        a = -20 - arm * 95
        ex = ax + math.cos(math.radians(a)) * 17
        ey = ay + math.sin(math.radians(a)) * 17
        pn.line([(ax * 0.75, ay + 3), (ex, ey)], fill=body, width=8.5, smooth=True)
        pn.oval(ex, ey, 5.6, 5.0, fill=light)
        if P.get("both_arms"):
            arm2 = P.get("arm2", arm)
            a2 = 200 + arm2 * 95
            ex2 = -ax + math.cos(math.radians(a2)) * 17
            ey2 = ay + math.sin(math.radians(a2)) * 17
            pn.line([(-ax * 0.75, ay + 3), (ex2, ey2)], fill=body, width=8.5, smooth=True)
            pn.oval(ex2, ey2, 5.6, 5.0, fill=light)

    # ---- head ------------------------------------------------------------
    hcx = hx
    hcy = (52 if pose == "lie" else (62 if pose in ("sit", "lotus") else 66)) + hy

    # ears
    for side in (-1, 1):
        bx = hcx + side * 18
        by = hcy + 15
        tipa = (60 if side > 0 else 120) + (-ear_a if side > 0 else ear_a)
        tx = bx + math.cos(math.radians(tipa)) * 20
        ty = by + math.sin(math.radians(tipa)) * 20
        pn.poly([(bx - side * 8, by - 3), (tx, ty), (bx + side * 7, by - 7)],
                fill=dark, outline=col["ear"], width=0, smooth=True)
        pn.poly([(bx - side * 4, by - 4), (tx * 0.92 + bx * 0.08, ty * 0.9 + by * 0.1),
                 (bx + side * 4, by - 7)], fill=ear_c, smooth=True)

    pn.oval(hcx, hcy, 25, 22.5, fill=body, outline=dark, width=1.4)       # skull
    pn.oval(hcx, hcy + 12, 17, 11, fill=light)                            # forehead blaze
    pn.oval(hcx, hcy - 6, 15.5, 12.5, fill=light)                         # muzzle

    eye_s = P.get("eye_style", "normal")
    eo = P.get("eye_open", 1.0)
    edx, edy = P.get("eye_dx", 0.0), P.get("eye_dy", 0.0)
    draw_eye(pn, hcx - 10, hcy + 5, 5.6, eye_s, eo, edx, edy)
    draw_eye(pn, hcx + 10, hcy + 5, 5.6, eye_s, eo, edx, edy)

    if P.get("brow", 0) > 0.05:
        b = P["brow"]
        pn.line([(hcx - 15, hcy + 12 + b * 2), (hcx - 6, hcy + 14)], fill=INK, width=1.8)
        pn.line([(hcx + 6, hcy + 14), (hcx + 15, hcy + 12 + b * 2)], fill=INK, width=1.8)

    draw_blush(pn, hcx - 18, hcy - 1, 5.6, P.get("blush", 0.85))
    draw_blush(pn, hcx + 18, hcy - 1, 5.6, P.get("blush", 0.85))

    pn.oval(hcx, hcy - 3, 4.6, 3.4, fill=INK)                             # nose
    pn.oval(hcx - 1.4, hcy - 2.2, 1.5, 1.0, fill=shade(INK, 1.9))
    draw_mouth(pn, hcx, hcy - 9, P.get("mouth", "cat"), 7.0, P.get("mouth_open", 0.0))
    if P.get("tongue", 0) > 0.1:
        pn.oval(hcx, hcy - 13 - P["tongue"] * 3, 4.2, 3.4 + P["tongue"] * 2.2, fill=PINK)

    # collar
    if pose != "lie":
        pn.line([(hcx - 16, hcy - 20), (hcx, hcy - 23), (hcx + 16, hcy - 20)],
                fill=collar, width=5.5, smooth=True)
        pn.oval(hcx, hcy - 24, 3.6, 3.6, fill=SUN)


# --------------------------------------------------------------------------
#  CAT
# --------------------------------------------------------------------------
def draw_cat(pn, P, col):
    body, dark, light = col["body"], col["body_dark"], col["light"]
    ear_c, collar = col["ear"], col["collar"]
    pose = P.get("pose", "stand")
    legp = P.get("leg_phase", 0.0)
    walk = P.get("walk", 0.0)
    tail_a = P.get("tail", 0.0)
    ear_a = P.get("ear", 0.0)
    arm = P.get("arm", 0.0)
    hy = P.get("head_y", 0.0)
    hx = P.get("head_x", 0.0)

    draw_shadow(pn, 27 if pose == "stand" else 30)

    # ---- long curvy tail -------------------------------------------------
    t_base = (-19, 28) if pose != "lie" else (-22, 13)
    draw_curl_tail(pn, t_base,
                   [(0, 0), (-12, 6), (-20, 18), (-19, 32), (-11, 40)],
                   tail_a * 0.8, dark, 7.0, 4.6, light)

    # ---- legs ------------------------------------------------------------
    if pose == "stand":
        for i, lx in enumerate((-14, 14)):
            sw = math.sin(legp + i * math.pi) * 7 * walk
            pn.line([(lx, 19), (lx + sw, 4)], fill=dark, width=8, smooth=True)
            pn.oval(lx + sw, 3.4, 5.8, 3.9, fill=light)
        for i, lx in enumerate((-8, 9)):
            sw = math.sin(legp + math.pi + i * math.pi) * 6 * walk
            pn.line([(lx, 25), (lx + sw, 5)], fill=body, width=8, smooth=True)
            pn.oval(lx + sw, 4.0, 5.4, 3.8, fill=light)
    elif pose in ("sit", "lotus"):
        pn.oval(-18, 11, 10.5, 10, fill=dark)
        pn.oval(18, 11, 10.5, 10, fill=dark)
        for lx in (-9, 9):
            pn.line([(lx, 21), (lx, 6)], fill=body, width=8, smooth=True)
            pn.oval(lx, 5, 5.6, 3.8, fill=light)
    else:
        pn.oval(-19, 9, 12.5, 7.6, fill=dark)
        pn.oval(19, 9, 12.5, 7.6, fill=dark)
        for lx in (-12, 12):
            pn.oval(lx, 7, 7.0, 4.4, fill=light)

    # ---- body ------------------------------------------------------------
    if pose == "lie":
        pn.oval(0, 16, 29, 14, fill=body, outline=dark, width=1.4)
        pn.oval(2, 13, 19, 9, fill=light)
    elif pose in ("sit", "lotus"):
        pn.oval(0, 29, 23, 24, fill=body, outline=dark, width=1.4)
        pn.oval(0, 24, 14, 16, fill=light)
    else:
        pn.oval(0, 33, 24, 22, fill=body, outline=dark, width=1.4)
        pn.oval(0, 29, 15, 15, fill=light)

    # ---- paws / arms (only when actually raised) -------------------------
    if abs(arm) > 0.01:
        ax, ay = 21, 31
        a = -20 - arm * 95
        ex = ax + math.cos(math.radians(a)) * 16
        ey = ay + math.sin(math.radians(a)) * 16
        pn.line([(ax * 0.75, ay + 3), (ex, ey)], fill=body, width=8, smooth=True)
        pn.oval(ex, ey, 5.2, 4.6, fill=light)
        if P.get("both_arms"):
            arm2 = P.get("arm2", arm)
            a2 = 200 + arm2 * 95
            ex2 = -ax + math.cos(math.radians(a2)) * 16
            ey2 = ay + math.sin(math.radians(a2)) * 16
            pn.line([(-ax * 0.75, ay + 3), (ex2, ey2)], fill=body, width=8, smooth=True)
            pn.oval(ex2, ey2, 5.2, 4.6, fill=light)

    # ---- head ------------------------------------------------------------
    hcx = hx
    hcy = (50 if pose == "lie" else (60 if pose in ("sit", "lotus") else 64)) + hy

    for side in (-1, 1):
        bx = hcx + side * 15
        by = hcy + 16
        lean = (-ear_a if side > 0 else ear_a)
        tip = (bx + side * 6 + lean * 0.35, by + 17)
        pn.poly([(bx - side * 9, by - 2), tip, (bx + side * 9, by - 1)],
                fill=body, outline=dark, width=1.2)
        pn.poly([(bx - side * 5, by + 1), (tip[0], tip[1] - 4), (bx + side * 5, by + 1)],
                fill=ear_c)

    pn.oval(hcx, hcy, 24, 21, fill=body, outline=dark, width=1.4)
    pn.oval(hcx, hcy - 6, 13.5, 9, fill=light)

    eye_s = P.get("eye_style", "normal")
    eo = P.get("eye_open", 1.0)
    edx, edy = P.get("eye_dx", 0.0), P.get("eye_dy", 0.0)
    draw_eye(pn, hcx - 9.5, hcy + 5, 5.8, eye_s, eo, edx, edy)
    draw_eye(pn, hcx + 9.5, hcy + 5, 5.8, eye_s, eo, edx, edy)

    if P.get("brow", 0) > 0.05:
        b = P["brow"]
        pn.line([(hcx - 15, hcy + 12 + b * 2), (hcx - 6, hcy + 14)], fill=INK, width=1.8)
        pn.line([(hcx + 6, hcy + 14), (hcx + 15, hcy + 12 + b * 2)], fill=INK, width=1.8)

    # whiskers start at the edge of the muzzle and sweep outside the head
    for side in (-1, 1):
        for k, yy in enumerate((-2.0, -5.0, -8.0)):
            x0 = hcx + side * 13.5
            pn.line([(x0, hcy + yy), (x0 + side * 9, hcy + yy + (1.0 - k) * 1.1),
                     (x0 + side * 21, hcy + yy + (1.0 - k) * 3.0)],
                    fill=INK_SOFT, width=1.3, smooth=True)

    draw_blush(pn, hcx - 16.5, hcy + 1.5, 5.2, P.get("blush", 0.85))
    draw_blush(pn, hcx + 16.5, hcy + 1.5, 5.2, P.get("blush", 0.85))

    pn.poly([(hcx - 3.4, hcy - 2.4), (hcx + 3.4, hcy - 2.4), (hcx, hcy - 6)],
            fill=PINK, outline=shade(PINK, 0.8), width=1.0, smooth=True)
    draw_mouth(pn, hcx, hcy - 8, P.get("mouth", "cat"), 6.4, P.get("mouth_open", 0.0))

    if pose != "lie":
        pn.line([(hcx - 15, hcy - 19), (hcx, hcy - 22), (hcx + 15, hcy - 19)],
                fill=collar, width=5.2, smooth=True)
        pn.oval(hcx, hcy - 23, 3.4, 3.4, fill=SUN)


# --------------------------------------------------------------------------
#  HUMAN  (tiny chibi buddy)
# --------------------------------------------------------------------------
def draw_human(pn, P, col):
    skin, skin_d = col["body"], col["body_dark"]
    hair = col.get("hair", "#6E4B63")
    shirt, shirt_d = col.get("shirt", SKY), col.get("shirt_dark", "#5FA9D6")
    pose = P.get("pose", "stand")
    legp = P.get("leg_phase", 0.0)
    walk = P.get("walk", 0.0)
    arm = P.get("arm", 0.0)
    hy = P.get("head_y", 0.0)
    hx = P.get("head_x", 0.0)

    draw_shadow(pn, 24 if pose == "stand" else 29)

    # ---- legs ------------------------------------------------------------
    if pose == "stand":
        for i, lx in enumerate((-8, 8)):
            sw = math.sin(legp + i * math.pi) * 8 * walk
            pn.line([(lx, 24), (lx + sw, 5)], fill=shirt_d, width=8.5, smooth=True)
            pn.oval(lx + sw, 3.6, 5.6, 3.6, fill=INK_SOFT)
    elif pose == "lotus":
        pn.line([(-20, 10), (0, 4), (20, 10)], fill=shirt_d, width=11, smooth=True)
        pn.oval(-13, 7, 6.4, 4.4, fill=skin)
        pn.oval(13, 7, 6.4, 4.4, fill=skin)
    elif pose == "sit":
        pn.line([(-7, 20), (-14, 8), (-20, 6)], fill=shirt_d, width=8.5, smooth=True)
        pn.line([(7, 20), (14, 8), (20, 6)], fill=shirt_d, width=8.5, smooth=True)
        pn.oval(-21, 4.5, 5.6, 3.6, fill=INK_SOFT)
        pn.oval(21, 4.5, 5.6, 3.6, fill=INK_SOFT)
    else:
        pn.line([(-14, 8), (14, 6)], fill=shirt_d, width=9, smooth=True)
        pn.oval(18, 6, 5.6, 3.6, fill=INK_SOFT)

    # ---- torso -----------------------------------------------------------
    if pose == "lie":
        pn.round_rect(-20, 10, 12, 24, 8, fill=shirt, outline=shirt_d, width=1.4)
    else:
        top = 52 if pose == "stand" else 46
        bot = 22 if pose == "stand" else 14
        pn.round_rect(-16, bot, 16, top, 11, fill=shirt, outline=shirt_d, width=1.4)
        pn.oval(0, bot + 6, 9, 5, fill=shade(shirt, 1.12))

    # ---- arms ------------------------------------------------------------
    sh_y = 44 if pose == "stand" else 38
    if pose == "lotus":
        for side in (-1, 1):
            pn.line([(side * 14, sh_y), (side * 23, sh_y - 14), (side * 20, 12)],
                    fill=shirt, width=7.5, smooth=True)
            pn.oval(side * 20, 11, 5.0, 4.4, fill=skin)
            pn.oval(side * 20, 11, 2.0, 2.0, fill="", outline=LAV, width=1.4)
    else:
        a_r = -70 - arm * 110
        er = (15 + math.cos(math.radians(a_r)) * 18, sh_y + math.sin(math.radians(a_r)) * 18)
        pn.line([(14, sh_y), er], fill=shirt, width=7.5, smooth=True)
        pn.oval(er[0], er[1], 5.2, 4.8, fill=skin)
        a_l = -110 + (P.get("arm2", arm) * 110 if P.get("both_arms") else 0)
        el = (-15 + math.cos(math.radians(a_l)) * 18, sh_y + math.sin(math.radians(a_l)) * 18)
        pn.line([(-14, sh_y), el], fill=shirt, width=7.5, smooth=True)
        pn.oval(el[0], el[1], 5.2, 4.8, fill=skin)

    # ---- head ------------------------------------------------------------
    hcx = hx
    hcy = (46 if pose == "lie" else (68 if pose == "stand" else 62)) + hy

    pn.oval(hcx, hcy, 22, 22, fill=skin, outline=skin_d, width=1.4)        # face
    # hair: rounded cap that sits well above the eyes, plus soft bangs
    pn.arc(hcx, hcy + 8, 22.2, 19, 0, 180, outline=hair, width=0,
           style=tk.PIESLICE, fill=hair)
    pn.oval(hcx, hcy + 13, 21, 11, fill=hair)
    pn.oval(hcx - 18.5, hcy + 5, 5.2, 9.5, fill=hair)
    pn.oval(hcx + 18.5, hcy + 5, 5.2, 9.5, fill=hair)
    pn.oval(hcx - 9, hcy + 11, 9.5, 5.4, fill=hair)
    pn.oval(hcx + 9.5, hcy + 10.5, 8, 4.8, fill=hair)

    eye_s = P.get("eye_style", "normal")
    eo = P.get("eye_open", 1.0)
    edx, edy = P.get("eye_dx", 0.0), P.get("eye_dy", 0.0)
    draw_eye(pn, hcx - 8.5, hcy + 1, 5.2, eye_s, eo, edx, edy)
    draw_eye(pn, hcx + 8.5, hcy + 1, 5.2, eye_s, eo, edx, edy)

    if P.get("brow", 0) > 0.05:
        b = P["brow"]
        pn.line([(hcx - 13, hcy + 9 + b * 2.5), (hcx - 4, hcy + 11)], fill=INK, width=1.8)
        pn.line([(hcx + 4, hcy + 11), (hcx + 13, hcy + 9 + b * 2.5)], fill=INK, width=1.8)

    draw_blush(pn, hcx - 14, hcy - 5, 5.2, P.get("blush", 0.9))
    draw_blush(pn, hcx + 14, hcy - 5, 5.2, P.get("blush", 0.9))
    m = P.get("mouth", "smile")
    draw_mouth(pn, hcx, hcy - 9, "smile" if m == "cat" else m, 6.2,
               P.get("mouth_open", 0.0))


# --------------------------------------------------------------------------
#  Background removal - pure tkinter, no Pillow, no installs
#
#  Flood-fills inward from every edge pixel of the photo, cutting anything
#  close in colour to the border (the backdrop) while stopping the instant
#  it hits a real edge - so it never has to guess where a limb ends, it
#  just never gets there because the colour changes too much to cross.
#  Runs on a small working copy for speed, so it stays quick even on a
#  large photo, then that becomes the saved image (already about the size
#  DeskPal displays it at, so nothing is lost).
# --------------------------------------------------------------------------
def remove_background_tk(img, thresh=34, max_side=260):
    """Return a new tk.PhotoImage with the backdrop cut to transparent.

    Never raises - on any problem it just returns the original image
    untouched, so a background-removal hiccup never breaks a photo upload.
    """
    try:
        w, h = img.width(), img.height()
        if w <= 1 or h <= 1:
            return img
        factor = max(1, int(round(max(w, h) / float(max_side))))
        work = img.subsample(factor, factor) if factor > 1 else img.copy()
        ww, wh = work.width(), work.height()
        if ww <= 1 or wh <= 1:
            return work
        get = work.get

        # a fixed reference colour (average of the border pixels) - safer
        # than comparing pixel-to-neighbour, which can slowly drift across
        # a soft shadow all the way into the subject
        border = []
        for x in range(0, ww, max(1, ww // 40) or 1):
            border.append(get(x, 0)); border.append(get(x, wh - 1))
        for y in range(0, wh, max(1, wh // 40) or 1):
            border.append(get(0, y)); border.append(get(ww - 1, y))
        if not border:
            return work
        rr = sum(p[0] for p in border) / len(border)
        rg = sum(p[1] for p in border) / len(border)
        rb = sum(p[2] for p in border) / len(border)

        def near_bg(px):
            return abs(px[0] - rr) + abs(px[1] - rg) + abs(px[2] - rb) <= thresh * 3

        visited = bytearray(ww * wh)
        dq = deque()

        def seed(x, y):
            idx = y * ww + x
            if not visited[idx] and near_bg(get(x, y)):
                visited[idx] = 1
                dq.append((x, y))

        for x in range(ww):
            seed(x, 0)
            seed(x, wh - 1)
        for y in range(wh):
            seed(0, y)
            seed(ww - 1, y)

        while dq:
            x, y = dq.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < ww and 0 <= ny < wh:
                    nidx = ny * ww + nx
                    if not visited[nidx]:
                        px = get(nx, ny)
                        if near_bg(px):
                            visited[nidx] = 1
                            dq.append((nx, ny))

        # binary transparency only - DeskPal's window uses exact-colour-key
        # transparency (one magic colour = invisible, everything else is
        # fully solid), so a soft/partial alpha edge - which some source
        # photos already carry, e.g. an AI-generated sprite sheet - would
        # get alpha-blended against the canvas and leave a faint tinted
        # halo that Windows can't key out. Forcing every kept pixel fully
        # opaque (and every cut pixel fully transparent) avoids that no
        # matter what alpha the original photo came in with.
        for y in range(wh):
            for x in range(ww):
                work.transparency_set(x, y, bool(visited[y * ww + x]))
        return work
    except Exception:
        log_exc("remove_background_tk")
        return img


# --------------------------------------------------------------------------
#  CUSTOM PHOTO  (a small named set of pictures used as the character)
#
#  DeskPal draws everything else as live vector shapes, so every limb, eye
#  and blush can move independently. A flat photo has none of that - there
#  are no separate parts to rig - so each pose here is a single rigid image
#  that still bounces, walks, wanders and reacts to reminders using the
#  exact same bob/sway values every other character gets. Real movement
#  (an arm actually swinging, a blink) comes from SWAPPING between a few
#  whole-body photos at the right moment instead of rotating one part -
#  classic sprite-frame animation, only every "frame" is optional: drop in
#  as many or as few of these named files as you like into DeskPal's data
#  folder (Settings -> About -> Open that folder) and each unlocks one more
#  moment of real movement. Missing ones just fall back to the idle photo.
#
#    custom_idle.png       required - the everyday look
#    custom_blink.png      optional - the SAME pose as idle, eyes closed -
#                           shown for a fraction of a second on the normal
#                           blink timer every character already has, for a
#                           real blink made of real photo pixels
#    custom_urgent.png     optional - shown for low battery / urgent events
#    custom_happy.png      optional - shown when praised or celebrating
#    custom_wave.png       optional - shown when greeting / waving
#    custom_walk1.png      optional - shown while walking
#    custom_meditate.png   optional - shown during a breathing session
#    custom_sleep.png      optional - shown when resting / late at night
#    custom_run_left.png   optional - shown dashing, facing left
#    custom_run_right.png  optional - shown dashing, facing right
#                           (run_left/run_right are picked by actual facing
#                           direction, not a timer - safe to use two really
#                           different photos here, unlike walk, because
#                           they're genuinely two different drawings, not
#                           one photo mirrored)
#
#  Only PNG/GIF/PPM/PGM load (Tk's own image reader - no extra installs);
#  a missing or bad file always falls back rather than breaking anything.
# --------------------------------------------------------------------------
_CUSTOM_IMG_CACHE = {}     # path -> (mtime, target_h, PhotoImage) - one slot per path


def clean_ganesh_sprite_tk(img):
    """Remove detached generator debris from a bundled Ganesh PNG.

    The desktop window uses colour-key transparency, so a single stray pixel,
    a cut-off tile edge, or a baked grey floor shadow is much more noticeable
    than it would be on a normal web page.  Some supplied source frames came
    from sprite/reference sheets and contain exactly that kind of debris.

    Keep the principal connected artwork and substantial secondary actors
    (the mouse and props), but discard small detached marks, edge-attached
    sheet remnants, and detached neutral floor shadows.  This is deliberately
    conservative: a problem while cleaning simply returns the original frame.
    """
    try:
        w, h = img.width(), img.height()
        if w < 8 or h < 8:
            return img
        opaque = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                if not img.transparency_get(x, y):
                    opaque[y * w + x] = 1

        seen = bytearray(w * h)
        components = []
        for start in range(w * h):
            if not opaque[start] or seen[start]:
                continue
            stack = [start]
            seen[start] = 1
            pixels = []
            min_x = max_x = start % w
            min_y = max_y = start // w
            touches_edge = False
            while stack:
                index = stack.pop()
                pixels.append(index)
                x, y = index % w, index // w
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                touches_edge = touches_edge or x == 0 or y == 0 or x == w - 1 or y == h - 1
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if opaque[ni] and not seen[ni]:
                            seen[ni] = 1
                            stack.append(ni)
            components.append((pixels, min_x, max_x, min_y, max_y, touches_edge))

        if not components:
            return img
        largest = max(len(part[0]) for part in components)
        actor_min = max(120, int(largest * 0.015))
        for pixels, min_x, max_x, min_y, max_y, touches_edge in components:
            area = len(pixels)
            keep = area >= actor_min and not (touches_edge and area < largest)
            # A separate, low-saturation component below the character is a
            # baked floor shadow, never a required Ganesh feature.
            if keep and min_y >= int(h * 0.60) and area < int(largest * 0.45):
                sample = pixels[::max(1, len(pixels) // 80)]
                chroma = 0.0
                for index in sample:
                    r, g, b = img.get(index % w, index // w)
                    chroma += max(r, g, b) - min(r, g, b)
                if sample and chroma / len(sample) < 28:
                    keep = False
            if not keep:
                for index in pixels:
                    img.transparency_set(index % w, index // w, True)
        return img
    except Exception:
        log_exc("clean_ganesh_sprite_tk")
        return img

CUSTOM_POSE_PATHS = {
    "blink":     os.path.join(DATA_DIR, "custom_blink.png"),
    "urgent":    CUSTOM_URGENT_PATH,
    "happy":     os.path.join(DATA_DIR, "custom_happy.png"),
    "wave":      os.path.join(DATA_DIR, "custom_wave.png"),
    "stand":     os.path.join(DATA_DIR, "custom_stand.png"),
    "walk1":     os.path.join(DATA_DIR, "custom_walk1.png"),
    "meditate":  os.path.join(DATA_DIR, "custom_meditate.png"),
    "sleep":     os.path.join(DATA_DIR, "custom_sleep.png"),
    "run_left":  os.path.join(DATA_DIR, "custom_run_left.png"),
    "run_right": os.path.join(DATA_DIR, "custom_run_right.png"),
    # 4-frame cycles - a real running stride and a real blessing gesture,
    # unfolding across frames instead of one static picture
    "run1": os.path.join(DATA_DIR, "custom_run1.png"),
    "run2": os.path.join(DATA_DIR, "custom_run2.png"),
    "run3": os.path.join(DATA_DIR, "custom_run3.png"),
    "run4": os.path.join(DATA_DIR, "custom_run4.png"),
    # mirrored copies of the same 4 frames, facing left - picked by actual
    # facing direction during run_cycle, never alternated on a timer, so
    # there is no flicker, just a correctly-facing dash either way
    "run1_left": os.path.join(DATA_DIR, "custom_run1_left.png"),
    "run2_left": os.path.join(DATA_DIR, "custom_run2_left.png"),
    "run3_left": os.path.join(DATA_DIR, "custom_run3_left.png"),
    "run4_left": os.path.join(DATA_DIR, "custom_run4_left.png"),
    "bless1": os.path.join(DATA_DIR, "custom_bless1.png"),
    "bless2": os.path.join(DATA_DIR, "custom_bless2.png"),
    "bless3": os.path.join(DATA_DIR, "custom_bless3.png"),
    "bless4": os.path.join(DATA_DIR, "custom_bless4.png"),
    # Bundled Ganesh story frames. These are used when a matching user pose
    # is not present in %APPDATA%\DeskPal, so the shipped project works on a
    # clean machine without a manual asset-copy step.
    "hungry1": os.path.join(PROJECT_ASSET_DIR, "custom_hungry1.png"),
    "hungry2": os.path.join(PROJECT_ASSET_DIR, "custom_hungry2.png"),
    "laddu1": os.path.join(PROJECT_ASSET_DIR, "custom_laddu1.png"),
    "laddu2": os.path.join(PROJECT_ASSET_DIR, "custom_laddu2.png"),
    "eat1": os.path.join(PROJECT_ASSET_DIR, "custom_eat1.png"),
    "eat2": os.path.join(PROJECT_ASSET_DIR, "custom_eat2.png"),
    "satisfied": os.path.join(PROJECT_ASSET_DIR, "custom_satisfied.png"),
    "ganesh_celebrate": os.path.join(PROJECT_ASSET_DIR, "custom_celebrate.png"),
}

# Optional production-frame names for the expanded Ganesh Emotes panel.
# A missing frame is deliberately harmless: resolve_custom_path() falls back
# to the approved idle pose, so testers can exercise every button before the
# art batch for that emote is installed.  Drop matching custom_*.png frames
# into DeskPal's data folder to replace the preview one frame at a time.
GANESH_EMOTE_FRAME_SETS = {
    "breathe_cycle": ("breathe1", "breathe2", "breathe3", "breathe4"),
    # Clean production sequence: both eyes closed, left-eye wink, both
    # closed, right-eye wink.  It deliberately does not use the older
    # custom_peek source frames, which contained sheet-edge artifacts.
    "meditation_peek": ("ganesh_watch1", "ganesh_watch2", "ganesh_watch3", "ganesh_watch4"),
    "window_peek": ("window_peek1", "window_peek2", "window_peek3", "window_peek4"),
    "water_slump": ("water_slump1", "water_slump2", "water_slump3", "water_slump4"),
    "drink_water": ("water_drink1", "water_drink2", "water_drink3", "water_drink4"),
    "study_cycle": ("study1", "study2", "study3", "study4"),
    "mouse_play": ("mouse_play1", "mouse_play2", "mouse_play3", "mouse_play4"),
    "mouse_ride": ("mouse_ride1", "mouse_ride2", "mouse_ride3", "mouse_ride4"),
    "happy_jump": ("happy_jump1", "happy_jump2", "happy_jump3", "happy_jump4"),
}
for _frames in GANESH_EMOTE_FRAME_SETS.values():
    for _frame in _frames:
        CUSTOM_POSE_PATHS.setdefault(_frame, os.path.join(DATA_DIR, "custom_%s.png" % _frame))

_BUNDLED_GANESH_POSES = {
    "run_left": os.path.join(PROJECT_ASSET_DIR, "custom_run_left.png"),
    "run_right": os.path.join(PROJECT_ASSET_DIR, "custom_run_right.png"),
    "run1": os.path.join(PROJECT_ASSET_DIR, "custom_run1.png"),
    "run2": os.path.join(PROJECT_ASSET_DIR, "custom_run2.png"),
    "run3": os.path.join(PROJECT_ASSET_DIR, "custom_run3.png"),
    "run4": os.path.join(PROJECT_ASSET_DIR, "custom_run4.png"),
    "run1_left": os.path.join(PROJECT_ASSET_DIR, "custom_run1_left.png"),
    "run2_left": os.path.join(PROJECT_ASSET_DIR, "custom_run2_left.png"),
    "run3_left": os.path.join(PROJECT_ASSET_DIR, "custom_run3_left.png"),
    "run4_left": os.path.join(PROJECT_ASSET_DIR, "custom_run4_left.png"),
    "stand": GANESH_BUNDLED_IDLE,
    "wave": os.path.join(PROJECT_ASSET_DIR, "custom_wave.png"),
    "happy": os.path.join(PROJECT_ASSET_DIR, "custom_celebrate.png"),
}
for _i in range(1, 5):
    _BUNDLED_GANESH_POSES["bless%d" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "custom_bless%d.png" % _i)
    _BUNDLED_GANESH_POSES["ganesh_watch%d" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_watch%d.png" % _i)

# The v2 sheet uses unique names so older AppData photos cannot silently
# replace the smoother bundled cycle.
for _i in range(1, 10):
    _BUNDLED_GANESH_POSES["ganesh_walk%d" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_walk%d.png" % _i)
    _BUNDLED_GANESH_POSES["ganesh_walk%d_left" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_walk%d_left.png" % _i)
for _i in range(1, 9):
    _BUNDLED_GANESH_POSES["ganesh_run%d" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_run%d.png" % _i)
    _BUNDLED_GANESH_POSES["ganesh_run%d_left" % _i] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_run%d_left.png" % _i)
for _name in ("hungry1", "hungry2", "laddu_toss1", "laddu_toss2",
              "laddu_toss3", "laddu_catch", "laddu_raise", "laddu_bite",
              "laddu_chew", "satisfied"):
    _BUNDLED_GANESH_POSES["ganesh_" + _name] = os.path.join(
        PROJECT_ASSET_DIR, "ganesh_" + _name + ".png")
for _frames in GANESH_EMOTE_FRAME_SETS.values():
    for _frame in _frames:
        _BUNDLED_GANESH_POSES.setdefault(_frame, os.path.join(
            PROJECT_ASSET_DIR, "custom_%s.png" % _frame))

# Visible previews used until an emote's dedicated production frames arrive.
# Mouse play and riding use the already shipped directional run cycle, so the
# controls always show real movement rather than a motionless idle fallback.
GANESH_EMOTE_PREVIEW_FRAMES = {
    "mouse_play": tuple("ganesh_run%d" % _i for _i in range(1, 9)),
    "mouse_ride": tuple("ganesh_run%d" % _i for _i in range(1, 9)),
    "water_slump": ("ganesh_hungry1", "ganesh_hungry2"),
    "drink_water": ("ganesh_laddu_raise", "ganesh_laddu_bite",
                    "ganesh_satisfied"),
    "happy_jump": ("ganesh_celebrate",),
}


def resolve_custom_path(pose_name):
    """Pick the file for a named pose, falling back to the idle photo."""
    path = CUSTOM_POSE_PATHS.get(pose_name)
    if path and os.path.exists(path):
        return path
    bundled = _BUNDLED_GANESH_POSES.get(pose_name)
    if bundled and os.path.exists(bundled):
        return bundled
    if os.path.exists(CUSTOM_IDLE_PATH):
        return CUSTOM_IDLE_PATH
    return GANESH_BUNDLED_IDLE


def get_custom_image(path, target_h):
    """Load + cache one of the user's photos, downscaled to ~target_h px tall.

    tk.PhotoImage only supports whole-number subsample factors (no smooth
    resize without Pillow), so the size is approximate, not exact. Cached
    per path so different poses never evict each other.
    """
    try:
        if not path or not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        target_h = int(target_h)
        cached = _CUSTOM_IMG_CACHE.get(path)
        if cached and cached[0] == mtime and cached[1] == target_h:
            return cached[2]
        img = tk.PhotoImage(file=path)
        ih = img.height()
        if ih <= 0:
            return None
        factor = max(1, int(round(ih / float(max(8, target_h)))))
        if factor > 1:
            img = img.subsample(factor, factor)
        # Only clean the app's bundled Ganesh art.  A person's own uploaded
        # photo must never be altered by an automatic sprite-sheet heuristic.
        try:
            asset_root = os.path.normcase(os.path.abspath(PROJECT_ASSET_DIR))
            image_path = os.path.normcase(os.path.abspath(path))
            if image_path.startswith(asset_root + os.sep):
                img = clean_ganesh_sprite_tk(img)
        except Exception:
            log_exc("get_custom_image.clean_ganesh")
        _CUSTOM_IMG_CACHE[path] = (mtime, target_h, img)
        return img
    except Exception:
        log_exc("get_custom_image")
        return None


def draw_custom(pn, P, col):
    # no synthetic vector shadow here - it's a flat dithered oval meant for
    # the flat-shaded drawn characters, and it looks like a stray grey patch
    # under a glossy photo instead of a ground shadow. The photo already
    # reads as fully grounded on its own.
    path = resolve_custom_path(P.get("custom_pose", "idle"))
    img = get_custom_image(path, 130)
    if img is None and path != CUSTOM_IDLE_PATH:
        img = get_custom_image(CUSTOM_IDLE_PATH, 130)   # graceful fallback
    if img is not None:
        try:
            pn.image(0, 60, img)
            return
        except Exception:
            log_exc("draw_custom.image")
    # no photo chosen yet, or it failed to load - a friendly placeholder
    pn.oval(0, 58, 26, 26, fill=col.get("body", "#DCD6F7"),
            outline=col.get("body_dark", "#C3BAEA"), width=1.4)
    pn.text(0, 58, "?", fill=INK, size=24, bold=True)



CHAR_DRAWERS = {"dog": draw_dog, "cat": draw_cat, "human": draw_human,
                "custom": draw_custom}
CHAR_LABELS = {"dog": "Puppy", "cat": "Kitty", "human": "Buddy",
               "custom": "Ganesh"}


# --------------------------------------------------------------------------
#  Animator - turns a state name + elapsed time into a pose
# --------------------------------------------------------------------------
IDLE_SPECIALS = ("look", "earflick", "yawn", "stretch", "sit", "tailspin", "hop",
                  "shiver", "confused", "hiccup", "sneeze")


class Animator:
    def __init__(self, particles):
        self.fx = particles
        self.state = "idle"
        self.t = 0.0                # seconds inside the current state
        self.clock = 0.0            # global seconds
        self.duration = None        # None = stay until told otherwise
        self.after_state = "idle"
        self.facing = 1
        self.walking = 0.0          # 0..1 blend for leg swing
        self.speed = 0.0            # units/sec of horizontal travel
        self.blink_in = random.uniform(1.5, 4.0)
        self.blink_t = 0.0
        self.look = [0.0, 0.0]
        self.look_target = [0.0, 0.0]
        self.look_in = 2.0
        self.cursor_dir = None       # set each frame by Buddy; None = no cursor info
        self.special_in = random.uniform(6.0, 14.0)
        self.mood = "normal"        # normal | happy | sleepy | worried | love
        self.breath_scale = 0.0     # driven by the breathing overlay
        self.on_done = None
        self.drag_tilt = 0.0
        self.character = "dog"      # kept in sync by Buddy each frame

    # ---------------------------------------------------------------- state
    def set(self, state, duration=None, after="idle", on_done=None, force=True):
        if not force and self.state == state:
            return
        self.state = state
        self.t = 0.0
        self.duration = duration
        self.after_state = after
        self.on_done = on_done
        if state in ("walk",):
            self.walking = 1.0
        elif state not in ("walk",):
            self.speed = 0.0

    def is_busy(self):
        return self.state not in ("idle", "sit", "sleep")

    # --------------------------------------------------------------- update
    def update(self, dt):
        try:
            self.clock += dt
            self.t += dt

            # blink ---------------------------------------------------------
            if self.blink_t > 0:
                self.blink_t = max(0.0, self.blink_t - dt)
            else:
                self.blink_in -= dt
                if self.blink_in <= 0:
                    self.blink_t = 0.16
                    self.blink_in = random.uniform(2.2, 6.5)

            # eye wander / cursor tracking -----------------------------------
            follow_cursor = self.cursor_dir is not None and self.state in ("idle", "sit", "walk")
            if follow_cursor:
                self.look_target = self.cursor_dir
                self.look_in = random.uniform(1.4, 4.0)   # stay fresh for when cursor info drops
            else:
                self.look_in -= dt
                if self.look_in <= 0:
                    self.look_in = random.uniform(1.4, 4.0)
                    self.look_target = [random.uniform(-1, 1), random.uniform(-0.5, 0.7)]
            for i in (0, 1):
                self.look[i] += (self.look_target[i] - self.look[i]) * min(1.0, dt * (8.0 if follow_cursor else 4.0))

            # idle fidgets --------------------------------------------------
            if self.state in ("idle", "sit") and self.character != "custom":
                self.special_in -= dt
                if self.special_in <= 0:
                    self.special_in = random.uniform(7.0, 16.0)
                    self.play_special()

            # state timeout -------------------------------------------------
            if self.duration is not None and self.t >= self.duration:
                cb, self.on_done = self.on_done, None
                nxt = self.after_state
                self.set(nxt, None, "idle")
                if cb:
                    safe(cb)

            # walking blend -------------------------------------------------
            target = 1.0 if self.state == "walk" else 0.0
            self.walking += (target - self.walking) * min(1.0, dt * 6.0)
            self.drag_tilt *= max(0.0, 1.0 - dt * 4.0)
        except Exception:
            log_exc("Animator.update")

    def play_special(self):
        try:
            if self.mood == "sleepy":
                self.set(random.choice(("yawn", "sit", "look")), 2.4)
                return
            pick = random.choice(IDLE_SPECIALS)
            dur = {"look": 2.2, "earflick": 0.9, "yawn": 2.4, "stretch": 2.2,
                   "sit": 4.5, "tailspin": 1.6, "hop": 1.0, "shiver": 1.4,
                   "confused": 2.6, "hiccup": 2.0, "sneeze": 1.0}.get(pick, 1.5)
            self.set(pick, dur)
        except Exception:
            log_exc("play_special")

    # ----------------------------------------------------------------- pose
    def pose(self):
        """Build the parameter dict the character drawers consume."""
        p = {}
        try:
            t, st = self.t, self.state
            c = self.clock
            breathe = math.sin(c * 1.9) * 1.4
            p["pose"] = "stand"
            p["bob"] = breathe
            p["dx"] = 0.0
            p["sx"] = 1.0
            p["sy"] = 1.0
            p["face"] = self.facing
            p["tail"] = math.sin(c * 2.2) * 9
            p["ear"] = math.sin(c * 1.1) * 3
            p["arm"] = 0.0
            p["head_y"] = math.sin(c * 1.9 + 0.6) * 0.8
            p["head_x"] = 0.0
            p["leg_phase"] = 0.0
            p["walk"] = self.walking
            p["eye_open"] = 1.0
            p["eye_style"] = "normal"
            p["eye_dx"] = self.look[0]
            p["eye_dy"] = self.look[1]
            p["mouth"] = "cat"
            p["mouth_open"] = 0.0
            p["blush"] = 0.85
            p["brow"] = 0.0
            p["tongue"] = 0.0
            p["both_arms"] = False
            p["custom_pose"] = "idle"

            if self.mood == "happy":
                p["blush"] = 1.0
            elif self.mood == "sleepy":
                p["eye_open"] = 0.55
                p["mouth"] = "flat"
            elif self.mood == "worried":
                p["brow"] = 1.0
                p["mouth"] = "sad"
                p["blush"] = 0.4
            elif self.mood == "love":
                p["eye_style"] = "heart"
                p["blush"] = 1.0

            # ---- per-state overrides ------------------------------------
            if st == "walk":
                wk = 0.6 if self.character == "custom" else 1.0
                p["leg_phase"] = c * 10.0 * wk
                p["bob"] = abs(math.sin(c * 10.0 * wk)) * 2.6
                p["tail"] = math.sin(c * 9.0) * 16
                p["ear"] = math.sin(c * 9.0 + 1) * 6
                p["mouth"] = "smile"
                walk_frames = tuple(
                    "ganesh_walk%d%s" % (i, "" if self.facing >= 0 else "_left")
                    for i in range(1, 9))
                p["custom_pose"] = walk_frames[int(t * 10.0 * wk) % len(walk_frames)]
                sq = 1.0 + math.sin(c * 17.0 * wk) * 0.02
                p["sx"], p["sy"] = 2.0 - sq, sq

            elif st == "run":
                p["leg_phase"] = c * 14.0
                p["bob"] = abs(math.sin(c * 14.0)) * 4.2
                p["walk"] = 1.0
                p["tail"] = math.sin(c * 11.0) * 22
                p["mouth"] = "open"
                p["tongue"] = 0.8
                p["custom_pose"] = "urgent"
                if self.character == "custom" and random.random() < 0.35:
                    self.fx.emit("rat", -14 * self.facing, 4, 1, power=0.3,
                                  color="#9C8F8A")

            elif st == "sit":
                p["pose"] = "sit"
                p["bob"] = math.sin(c * 1.7) * 1.0
                p["tail"] = math.sin(c * 1.6) * 14

            elif st == "sleep":
                if self.character == "custom":
                    # calm meditative rest instead of lying down asleep
                    p["pose"] = "lotus"
                    p["eye_style"] = "closed"
                    p["mouth"] = "smile"
                    p["bob"] = 2 + math.sin(c * 1.1) * 3
                    p["sy"] = 1.0 + math.sin(c * 1.1) * 0.03
                    p["sx"] = 1.0 - math.sin(c * 1.1) * 0.02
                    p["blush"] = 0.6
                    p["both_arms"] = True
                    p["arm"] = 0.35
                    p["custom_pose"] = "sleep"
                else:
                    p["pose"] = "lie"
                    p["eye_style"] = "sleep"
                    p["mouth"] = "flat"
                    p["bob"] = math.sin(c * 0.9) * 1.6
                    p["sy"] = 1.0 + math.sin(c * 0.9) * 0.02
                    p["sx"] = 2.0 - p["sy"]
                    p["tail"] = math.sin(c * 0.7) * 5
                    p["blush"] = 0.6
                    if random.random() < 0.012:
                        self.fx.emit("zzz", 14, 62, 1, power=0.4, color=LAV)

            elif st == "happy":
                k = bounce(t / max(0.001, self.duration or 1.2))
                p["bob"] = 4 + k * 12
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["sy"] = 1.0 + k * 0.10
                p["sx"] = 1.0 - k * 0.07
                p["tail"] = math.sin(c * 16) * 26
                p["ear"] = math.sin(c * 14) * 9
                p["blush"] = 1.0
                p["custom_pose"] = "happy"

            elif st == "love":
                p["eye_style"] = "heart"
                p["mouth"] = "wide"
                p["bob"] = 2 + bounce(t / max(0.001, self.duration or 1.6)) * 6
                p["blush"] = 1.0
                p["custom_pose"] = "happy"
                if random.random() < 0.25:
                    self.fx.emit("heart", random.uniform(-14, 14), 74, 1, power=0.5, color=PINK)

            elif st == "dance":
                beat = c * 5.4
                p["bob"] = abs(math.sin(beat)) * 8
                p["dx"] = math.sin(beat * 0.5) * 7
                p["sx"] = 1.0 + math.sin(beat) * 0.07
                p["sy"] = 1.0 - math.sin(beat) * 0.05
                p["arm"] = (math.sin(beat) + 1) / 2
                p["both_arms"] = True
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["tail"] = math.sin(beat * 1.5) * 28
                p["ear"] = math.sin(beat) * 12
                if random.random() < 0.16:
                    self.fx.emit(random.choice(("note", "star", "confetti")),
                                 random.uniform(-20, 20), 70, 1, power=0.7)

            elif st == "wave":
                p["arm"] = (math.sin(t * 11.0) + 1) / 2
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["bob"] = 1.5 + math.sin(t * 5.5) * 1.5
                p["head_x"] = math.sin(t * 5.5) * 1.2
                p["custom_pose"] = "wave"

            elif st == "stretch":
                k = bounce(t / max(0.001, self.duration or 2.2))
                p["sy"] = 1.0 + k * 0.22
                p["sx"] = 1.0 - k * 0.12
                p["bob"] = k * 4
                p["arm"] = k
                p["both_arms"] = True
                p["eye_style"] = "closed" if k > 0.35 else "normal"
                p["mouth"] = "open" if k > 0.5 else "smile"
                p["mouth_open"] = k * 0.5

            elif st == "yawn":
                k = bounce(t / max(0.001, self.duration or 2.4))
                p["mouth"] = "yawn"
                p["mouth_open"] = k
                p["eye_style"] = "closed" if k > 0.25 else "normal"
                p["head_y"] = k * 3
                p["bob"] = k * 2
                p["sy"] = 1.0 + k * 0.05
                if k > 0.8 and random.random() < 0.08:
                    self.fx.emit("zzz", 10, 70, 1, power=0.3, color=LAV)

            elif st == "look":
                sway = math.sin(t * 2.6)
                p["head_x"] = sway * 4.5
                p["eye_dx"] = sway
                p["ear"] = sway * 8
                p["tail"] = math.sin(c * 2.6) * 12

            elif st == "earflick":
                k = bounce(t / max(0.001, self.duration or 0.9))
                p["ear"] = k * 26
                p["head_x"] = k * 1.5

            elif st == "tailspin":
                p["tail"] = math.sin(c * 15) * 34
                p["bob"] = math.sin(c * 7) * 2
                p["eye_style"] = "happy"

            elif st == "hop":
                k = bounce(t / max(0.001, self.duration or 1.0))
                p["bob"] = k * 16
                p["sy"] = 1.0 + k * 0.08
                p["sx"] = 1.0 - k * 0.06
                p["ear"] = k * 14

            elif st == "meditate":
                p["pose"] = "lotus"
                br = self.breath_scale
                p["bob"] = 2 + br * 6
                p["sy"] = 1.0 + br * 0.045
                p["sx"] = 1.0 - br * 0.03
                p["eye_style"] = "closed"
                p["mouth"] = "smile"
                p["blush"] = 0.7
                p["tail"] = math.sin(c * 0.8) * 4
                p["both_arms"] = True
                p["arm"] = 0.35
                p["custom_pose"] = "meditate"

            elif st == "ganesh_rest":
                p["custom_pose"] = "breathe1"
                p["mouth"] = "smile"
                p["blush"] = 0.7

            elif st == "drag":
                p["bob"] = -4
                p["arm"] = 0.9
                p["both_arms"] = True
                p["eye_style"] = "normal"
                p["eye_open"] = 1.0
                p["mouth"] = "o"
                p["dx"] = clamp(self.drag_tilt, -8, 8)
                p["sy"] = 1.04
                p["sx"] = 0.97
                p["tail"] = math.sin(c * 9) * 20
                p["ear"] = math.sin(c * 8) * 10

            elif st == "dizzy":
                p["eye_style"] = "dizzy"
                p["mouth"] = "flat"
                p["dx"] = math.sin(c * 9) * 3
                p["bob"] = math.sin(c * 12) * 1.5
                if random.random() < 0.08:
                    self.fx.emit("star", random.uniform(-8, 8), 82, 1, power=0.3, color=SUN)

            elif st == "celebrate":
                k = (t * 2.2) % 1.0
                p["bob"] = bounce(k) * 16
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["arm"] = 1.0
                p["both_arms"] = True
                p["tail"] = math.sin(c * 14) * 28
                p["custom_pose"] = "happy"
                if random.random() < 0.3:
                    self.fx.emit("confetti", random.uniform(-26, 26), 86, 2, power=1.1)

            elif st == "worried":
                p["brow"] = 1.0
                p["mouth"] = "sad"
                p["eye_open"] = 0.85
                p["dx"] = math.sin(c * 12) * 1.4
                p["blush"] = 0.35

            elif st == "run_cycle":
                # the 8 real running frames, played in order on a proper
                # animation timer (not a picture swap) - loops while the
                # trick is active. Picked by actual facing direction (set
                # once when the dash starts, not alternated), using a real
                # mirrored set for left so it never runs backwards
                side = "" if self.facing >= 0 else "_left"
                frames = tuple("ganesh_run%d%s" % (i, side) for i in range(1, 9))
                fps = 10.0
                p["custom_pose"] = frames[int(t * fps) % len(frames)]
                p["leg_phase"] = c * 12.0
                p["bob"] = abs(math.sin(c * 12.0)) * 4.0
                p["walk"] = 1.0
                p["mouth"] = "open"
                p["tongue"] = 0.6
                p["tail"] = math.sin(c * 10) * 20

            elif st == "bless_cycle":
                # plays the 4 blessing frames forward once, then holds on
                # the peak (eyes closed, hand raised) until the trick ends
                frames = ("bless1", "bless2", "bless3", "bless4")
                dur = self.duration or 2.4
                frac = clamp(t / max(0.001, dur), 0.0, 0.999)
                idx = min(3, int(frac * 4))
                p["custom_pose"] = frames[idx]
                p["eye_style"] = "closed" if idx >= 2 else "happy"
                p["mouth"] = "smile"
                p["blush"] = 1.0
                p["bob"] = 1.0 + math.sin(c * 2.0) * 1.0
                if idx == 3 and random.random() < 0.1:
                    self.fx.emit("sparkle", 14, 74, 1, power=0.4, color=SUN)

            elif st == "hungry_cycle":
                # A short readable story: tummy ache, then hopeful searching.
                frames = ("ganesh_hungry1", "ganesh_hungry2",
                          "ganesh_hungry1", "ganesh_hungry2")
                p["custom_pose"] = frames[int(t * 2.4) % len(frames)]
                p["brow"] = 1.0
                p["mouth"] = "sad"
                p["bob"] = math.sin(c * 3.0) * 1.5

            elif st == "eat_laddu":
                # Cinematic story: toss, track, catch, bring to mouth, bite,
                # chew, and finish satisfied.
                frames = ("ganesh_laddu_toss1", "ganesh_laddu_toss2",
                          "ganesh_laddu_toss3", "ganesh_laddu_catch",
                          "ganesh_laddu_raise", "ganesh_laddu_bite",
                          "ganesh_laddu_chew", "ganesh_satisfied")
                dur = self.duration or 5.0
                idx = min(len(frames) - 1, int(clamp(t / max(0.001, dur), 0.0, 0.999) * len(frames)))
                p["custom_pose"] = frames[idx]
                p["eye_style"] = "happy" if idx >= 2 else "normal"
                p["mouth"] = "wide" if idx >= 2 else "smile"
                p["blush"] = 1.0
                p["bob"] = math.sin(c * 2.4) * 1.5

            elif st in GANESH_EMOTE_FRAME_SETS:
                # These named clips have a stable, documented frame contract.
                # They play even before optional production art is installed:
                # each missing frame simply resolves to the safe idle image.
                frames = GANESH_EMOTE_FRAME_SETS[st]
                dur = self.duration or 2.4
                idx = min(len(frames) - 1, int(
                    clamp(t / max(0.001, dur), 0.0, 0.999) * len(frames)))
                p["custom_pose"] = frames[idx]
                has_production_frames = any(
                    os.path.exists(CUSTOM_POSE_PATHS.get(frame, "")) or
                    os.path.exists(_BUNDLED_GANESH_POSES.get(frame, ""))
                    for frame in frames)
                if not has_production_frames and st in GANESH_EMOTE_PREVIEW_FRAMES:
                    preview = GANESH_EMOTE_PREVIEW_FRAMES[st]
                    p["custom_pose"] = preview[int(t * 10.0) % len(preview)]
                p["blush"] = 1.0 if st in ("happy_jump", "mouse_play") else 0.8
                p["mouth"] = "wide" if st in ("happy_jump", "mouse_play") else "smile"
                p["eye_style"] = "happy" if st in ("happy_jump", "mouse_play", "mouse_ride") else "normal"

                if st == "breathe_cycle":
                    p["bob"] = math.sin(t * math.pi * 2.0) * 1.5
                elif st == "meditation_peek":
                    p["eye_style"] = "closed" if idx in (0, 3) else "happy"
                elif st == "window_peek":
                    # The artwork itself supplies the crop; no white card or
                    # fake window is drawn over the desktop companion.
                    p["dx"] = -5 + idx * 3
                elif st == "water_slump":
                    p["bob"] = -1.5
                    p["mouth"] = "sad"
                    p["eye_style"] = "closed" if idx >= 2 else "normal"
                elif st == "drink_water":
                    p["bob"] = math.sin(t * 3.0) * 1.0
                    if idx == 2 and random.random() < 0.08:
                        self.fx.emit("drop", 12, 72, 1, power=0.25, color=SKY)
                elif st == "study_cycle":
                    p["eye_style"] = "closed" if idx == 3 else "normal"
                elif st == "mouse_play":
                    if random.random() < 0.20:
                        self.fx.emit("rat", -16 * self.facing, 4, 1, power=0.25,
                                     color="#9C8F8A")
                elif st == "mouse_ride":
                    p["bob"] = abs(math.sin(t * 7.0)) * 2.0
                elif st == "happy_jump":
                    k = bounce(t / max(0.001, dur))
                    p["bob"] = k * 15
                    p["ear"] = k * 8
                    if idx == 2 and random.random() < 0.12:
                        self.fx.emit("sparkle", random.uniform(-16, 16), 76,
                                     1, power=0.45, color=SUN)

            elif st == "hold_laddu":
                p["custom_pose"] = "ganesh_laddu_catch"
                p["mouth"] = "smile"
                p["blush"] = 1.0

            elif st == "satisfied_laddu":
                p["custom_pose"] = "ganesh_satisfied"
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["blush"] = 1.0

            elif st == "think":
                p["head_x"] = 2.5
                p["eye_dx"] = 0.8
                p["eye_dy"] = 0.6
                p["mouth"] = "flat"
                p["arm"] = 0.55

            # ---- big showy tricks (menu-triggered) -----------------------
            elif st == "spin":
                D = self.duration or 1.2
                ang = (t / D) * 720.0
                k = abs(math.cos(math.radians(ang)))
                p["sx"] = 0.25 + 0.75 * k
                p["face"] = 1 if (int(ang // 180) % 2 == 0) else -1
                p["bob"] = 3 + bounce(t / D) * 7
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["tail"] = math.sin(c * 20) * 30
                p["ear"] = math.sin(c * 18) * 14
                p["arm"] = 0.7
                p["both_arms"] = True
                p["blush"] = 1.0
                if random.random() < 0.3:
                    self.fx.emit("sparkle", random.uniform(-10, 10), 60, 1,
                                 power=0.5, color=SUN)

            elif st == "bow":
                D = self.duration or 1.8
                k = bounce(t / D)
                p["sy"] = 1.0 - k * 0.28
                p["sx"] = 1.0 + k * 0.10
                p["head_y"] = -k * 14
                p["bob"] = -k * 3
                p["arm"] = 0.4 + k * 0.3
                p["both_arms"] = True
                p["eye_style"] = "closed" if k > 0.3 else "normal"
                p["mouth"] = "smile"
                if k > 0.85 and random.random() < 0.25:
                    self.fx.emit("sparkle", 0, 50, 1, power=0.3, color=SUN)

            elif st == "jumping_jacks":
                legp = c * 6.0
                p["leg_phase"] = legp
                p["walk"] = 1.0
                o = (math.sin(legp) + 1) / 2.0
                p["arm"] = o
                p["both_arms"] = True
                p["bob"] = o * 5
                p["sy"] = 1.0 + o * 0.05
                p["mouth"] = "open"
                p["mouth_open"] = 0.3
                p["eye_style"] = "happy" if o > 0.5 else "normal"
                p["tail"] = math.sin(c * 10) * 20
                p["ear"] = math.sin(c * 10 + 1) * 10
                if random.random() < 0.02:
                    self.fx.emit("drop", random.uniform(-6, 6), 78, 1,
                                 power=0.3, color=SKY)

            elif st == "shimmy":
                beat = c * 9.0
                p["dx"] = math.sin(beat) * 6
                p["sx"] = 1.0 + math.sin(beat * 2) * 0.05
                p["sy"] = 1.0 - math.sin(beat * 2) * 0.03
                p["tail"] = math.sin(beat * 1.3) * 30
                p["ear"] = math.sin(beat * 1.6) * 14
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["head_x"] = math.sin(beat) * 3
                p["blush"] = 1.0
                if random.random() < 0.1:
                    self.fx.emit("note", random.uniform(-14, 14), 70, 1,
                                 power=0.4, color=LAV)

            elif st == "applause":
                beat = c * 14.0
                p["arm"] = (math.sin(beat) + 1) / 2.0
                p["both_arms"] = True
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["bob"] = 1.5 + math.sin(beat * 0.5) * 1.0
                p["blush"] = 1.0
                if random.random() < 0.22:
                    self.fx.emit("sparkle", random.uniform(-16, 16), 72, 1,
                                 power=0.5, color=SUN)

            elif st == "peekaboo":
                D = self.duration or 1.6
                half = D * 0.5
                if t < half:
                    k = t / max(0.001, half)
                    p["arm"] = k
                    p["eye_style"] = "closed"
                    p["mouth"] = "smile"
                else:
                    k2 = (t - half) / max(0.001, D - half)
                    p["arm"] = max(0.0, 1.0 - k2 * 3)
                    p["eye_open"] = 1.25
                    p["eye_style"] = "normal"
                    p["mouth"] = "wide"
                    p["blush"] = 1.0
                    if half <= t < half + 0.12:
                        self.fx.emit("star", 0, 74, 6, power=0.7, color=SUN)

            elif st == "tada":
                D = self.duration or 1.4
                k = ease_out_back(min(1.0, t / max(0.001, D * 0.4)))
                p["arm"] = k
                p["both_arms"] = True
                p["sy"] = 1.0 + k * 0.08
                p["sx"] = 1.0 - k * 0.05
                p["bob"] = k * 6
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["blush"] = 1.0

            elif st == "moonwalk":
                D = self.duration or 2.4
                k = t / D
                p["dx"] = -k * 18
                p["leg_phase"] = c * 10.0
                p["walk"] = 1.0
                p["bob"] = abs(math.sin(c * 10.0)) * 1.6
                p["eye_style"] = "happy"
                p["mouth"] = "smile"
                p["arm"] = 0.25
                p["tail"] = math.sin(c * 6) * 14
                if random.random() < 0.08:
                    self.fx.emit("note", random.uniform(-10, 10), 68, 1,
                                 power=0.4, color=LAV)

            elif st == "robot":
                step = int(math.floor(c * 3.0)) % 4
                arm_a = (0.05, 1.0, 1.0, 0.05)[step]
                arm_b = (1.0, 1.0, 0.05, 0.05)[step]
                p["arm"] = arm_a
                p["arm2"] = arm_b
                p["both_arms"] = True
                p["head_x"] = (-3, 0, 3, 0)[step]
                p["bob"] = (0, 1.5, 0, 1.5)[step]
                p["mouth"] = "flat"
                p["eye_style"] = "normal"
                p["blush"] = 0.0
                p["tail"] = 0.0
                p["ear"] = 0.0
                if random.random() < 0.05:
                    self.fx.emit("sparkle", random.uniform(-4, 4), 86, 1,
                                 power=0.2, color=SKY)

            elif st == "fly":
                k = ease_out(min(1.0, t / 0.6))
                p["bob"] = 6 + k * 10 + math.sin(c * 5) * 1.5
                p["arm"] = 0.9
                p["both_arms"] = True
                p["head_x"] = 2.0
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["blush"] = 1.0
                p["sy"] = 1.0 + k * 0.04
                p["tail"] = math.sin(c * 9) * 16
                if random.random() < 0.35:
                    self.fx.emit("star", random.uniform(-4, 4), 22, 1,
                                 power=0.9, color=SUN)
                    self.fx.emit("sparkle", random.uniform(-4, 4), 18, 1,
                                 power=0.7, color=SKY)

            elif st == "karate":
                beat = (t * 4.0) % 1.0
                chop = bounce(beat)
                p["arm"] = chop
                p["dx"] = (chop - 0.4) * 6
                p["brow"] = 1.0
                p["mouth"] = "flat"
                p["sx"] = 1.0 + chop * 0.06
                p["sy"] = 1.0 - chop * 0.04
                p["tail"] = math.sin(c * 20) * 14
                if chop > 0.9 and random.random() < 0.5:
                    self.fx.emit("sparkle", 14, 40, 2, power=0.6, color=SKY)

            elif st == "magic":
                D = self.duration or 1.8
                half = D * 0.55
                if t < half:
                    k = t / max(0.001, half)
                    p["arm"] = k
                    p["eye_style"] = "closed"
                    p["mouth"] = "smile"
                else:
                    p["arm"] = 1.0
                    p["eye_style"] = "happy"
                    p["mouth"] = "wide"
                    p["blush"] = 1.0
                    if half <= t < half + 0.12:
                        self.fx.burst_ring("sparkle", 0, 78, 12, color=LAV)
                        self.fx.burst_ring("star", 0, 78, 6, color=SUN)

            # ---- little reflex reactions (also used as idle fidgets) ------
            elif st == "shiver":
                j = math.sin(c * 30.0)
                p["dx"] = j * 2.4
                p["head_x"] = -j * 1.6
                p["sy"] = 1.0 - abs(j) * 0.02
                p["mouth"] = "o" if int(c * 14) % 2 == 0 else "flat"
                p["eye_open"] = 0.7
                p["tail"] = j * 10
                p["ear"] = -j * 10

            elif st == "sneeze":
                D = self.duration or 1.0
                peak = D * 0.65
                if t < peak:
                    k = t / max(0.001, peak)
                    p["eye_style"] = "closed"
                    p["head_y"] = -k * 2
                    p["sy"] = 1.0 + k * 0.04
                    p["mouth"] = "o"
                else:
                    k2 = (t - peak) / max(0.001, D - peak)
                    p["head_x"] = (1 - k2) * 6
                    p["head_y"] = -3 * (1 - k2)
                    p["eye_style"] = "closed" if k2 < 0.2 else "normal"
                    p["mouth"] = "open"
                    p["mouth_open"] = max(0.0, 1 - k2 * 2)
                    if peak <= t < peak + 0.1:
                        self.fx.emit("sparkle", 0, 66, 5, power=0.6, color=WHITE)

            elif st == "hiccup":
                beat = t * 2.2
                spike = max(0.0, math.sin(beat * math.pi)) ** 6
                p["bob"] = spike * 7
                p["eye_open"] = 1.0 + spike * 0.3
                p["mouth"] = "o" if spike > 0.3 else "flat"
                p["head_y"] = spike * 3
                if spike > 0.85 and random.random() < 0.4:
                    self.fx.emit("bubble", 0, 70, 1, power=0.3, color=SKY)

            elif st == "confused":
                sway = math.sin(t * 3.0)
                p["head_x"] = sway * 5
                p["arm"] = 0.35 + math.sin(t * 6.0) * 0.08
                p["eye_dx"] = sway * 0.6
                p["mouth"] = "flat"
                p["brow"] = 0.6
                if random.random() < 0.05:
                    self.fx.emit("question", random.uniform(-6, 6), 82, 1,
                                 power=0.3, color=INK_SOFT)

            elif st == "surprised":
                k = math.exp(-t * 6.0)
                p["dx"] = -k * 10
                p["eye_open"] = 1.0 + k * 0.35
                p["mouth"] = "o"
                p["head_x"] = -k * 3
                p["sy"] = 1.0 + k * 0.05
                if t < 0.1:
                    self.fx.emit("exclaim", 0, 86, 1, power=0.5, color=SUN)

            elif st == "disco":
                beat = c * 3.0
                on = int(beat) % 2
                p["arm"] = 1.0 if on == 0 else 0.1
                p["arm2"] = 0.1 if on == 0 else 1.0
                p["both_arms"] = True
                p["eye_style"] = "happy"
                p["mouth"] = "wide"
                p["sx"] = 1.0 + math.sin(beat * math.pi) * 0.03
                p["tail"] = math.sin(c * 8) * 22
                p["blush"] = 1.0
                if random.random() < 0.12:
                    self.fx.emit("note", random.uniform(-16, 16), 74, 1,
                                 power=0.5, color=random.choice((PINK, LAV, SKY)))

            # blink wins over most eye styles
            if self.blink_t > 0 and p["eye_style"] in ("normal", "happy"):
                p["eye_style"] = "closed"

            # real blink for the photo character - same idle pose, eyes
            # closed, swapped in for the same fraction of a second every
            # other character blinks for. Only during plain idle/sit, so
            # it never fights a more specific pose like meditating or sad.
            if (self.character == "custom" and self.blink_t > 0
                    and p.get("custom_pose") == "idle"):
                p["custom_pose"] = "blink"

            p["bob"] += 0.0
        except Exception:
            log_exc("Animator.pose")
        return p


# --------------------------------------------------------------------------
#  The buddy window  (transparent, always on top, click-through background)
# --------------------------------------------------------------------------
UNIT_PX = 1.45          # pixels per character unit at scale 1.0
WIN_W_UNITS = 240       # window width in units
WIN_H_UNITS = 230       # window height in units
FOOT_PAD_UNITS = 18     # gap between the feet and the window bottom


class Buddy:
    """Owns the Tk root window, the drawing surface and all pet behaviour."""

    def __init__(self, app, root, cfg):
        self.app = app
        self.root = root
        self.cfg = cfg
        self.fx = Particles()
        self.anim = Animator(self.fx)

        self.transparent_ok = False
        self.alive = True
        self.hidden = False

        # geometry -------------------------------------------------------
        self.s = UNIT_PX * float(cfg.get("scale", 1.0)) * UI_K
        self.cw = int(WIN_W_UNITS * self.s)
        self.ch = int(WIN_H_UNITS * self.s)
        self.x = 0.0
        self.y = 0.0
        self.target_x = None
        self.floor_y = None

        # speech ---------------------------------------------------------
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.bubble_start = 0.0
        self.bubble_typed = 0

        # interaction ----------------------------------------------------
        self._drag = None
        self._drag_last_x = None
        self._press_xy = None
        self.pet_count = 0
        self.last_pet = 0.0
        self.last_ganesh_interaction = time.time()

        # timing ---------------------------------------------------------
        self._last_frame = time.time()
        self._frame_budget = 1.0 / max(12, int(cfg.get("fps", 30)))
        self._slow_frames = 0
        self._topmost_tick = 0.0

        self._build_window()
        self._place_initial()
        self._bind()

    # ------------------------------------------------------------------ UI
    def _build_window(self):
        r = self.root
        r.title(APP_NAME)
        try:
            r.overrideredirect(True)
        except Exception:
            log_exc("overrideredirect")
        try:
            r.attributes("-topmost", True)
        except Exception:
            pass
        try:
            r.configure(bg=KEY_COLOR)
            r.attributes("-transparentcolor", KEY_COLOR)
            self.transparent_ok = True
        except Exception:
            # macOS / Linux: no colour keying - use a plain soft background
            self.transparent_ok = False
            try:
                r.configure(bg=CREAM)
            except Exception:
                pass

        bg = KEY_COLOR if self.transparent_ok else CREAM
        self.canvas = tk.Canvas(r, width=self.cw, height=self.ch, bg=bg,
                                highlightthickness=0, bd=0, takefocus=0)
        self.canvas.pack(fill="both", expand=True)
        self.pn = Painter(self.canvas)

        r.geometry("%dx%d" % (self.cw, self.ch))
        try:
            r.update_idletasks()
        except Exception:
            pass
        WIN.set_tool_window(r, no_activate=True)

    def _screen_rect(self):
        """Work area of the monitor the buddy currently sits on."""
        rect = WIN.work_area_at(self.x + self.cw / 2, self.y + self.ch / 2)
        if rect:
            return rect
        try:
            return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        except Exception:
            return (0, 0, 1280, 720)

    def _place_initial(self):
        sx, sy, sw, sh = self._screen_rect()
        px, py = self.cfg.get("pos_x"), self.cfg.get("pos_y")
        if px is None or py is None:
            self.x = sx + sw - self.cw - int(30 * self.s)
            self.y = sy + sh - self.ch + int(6 * self.s)
        else:
            self.x, self.y = float(px), float(py)
        self._clamp_into_screen()
        self.floor_y = self.y
        self._apply_geometry()

    def _clamp_into_screen(self):
        vs = WIN.virtual_screen()
        if vs:
            vx, vy, vw, vh = vs
        else:
            try:
                vx, vy = 0, 0
                vw, vh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            except Exception:
                vx, vy, vw, vh = 0, 0, 1280, 720
        self.x = clamp(self.x, vx - self.cw * 0.25, vx + vw - self.cw * 0.75)
        self.y = clamp(self.y, vy - self.ch * 0.1, vy + vh - self.ch * 0.55)

    def _apply_geometry(self):
        try:
            self.root.geometry("+%d+%d" % (int(self.x), int(self.y)))
        except Exception:
            pass

    def _bind(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Button-3>", self.on_menu)
        c.bind("<Double-Button-1>", self.on_double)
        c.bind("<Triple-Button-1>", self.on_triple)
        c.bind("<Enter>", self.on_enter)
        c.bind("<Leave>", self.on_leave)
        try:
            self.root.protocol("WM_DELETE_WINDOW", self.app.quit_app)
        except Exception:
            pass

    # -------------------------------------------------------- interaction
    def on_press(self, ev):
        self.app.stop_modak_scene()
        try:
            self.last_ganesh_interaction = time.time()
            if self.cfg.get("character") == "custom" and self.anim.state == "ganesh_rest":
                self.anim.set("idle")
            self._press_xy = (ev.x_root, ev.y_root, time.time())
            self._drag = (ev.x_root - self.x, ev.y_root - self.y)
            self._drag_last_x = ev.x_root
        except Exception:
            log_exc("on_press")

    def on_drag(self, ev):
        try:
            if not self._drag:
                return
            nx = ev.x_root - self._drag[0]
            ny = ev.y_root - self._drag[1]
            last_x = self._drag_last_x if self._drag_last_x is not None else ev.x_root
            move_dx = ev.x_root - last_x
            self._drag_last_x = ev.x_root
            self.anim.drag_tilt = clamp((nx - self.x) * 0.55, -10, 10)
            self.x, self.y = nx, ny
            self._clamp_into_screen()
            self._apply_geometry()
            if self.cfg.get("character") == "custom":
                # While the user drags Ganesh, choose the sprite direction
                # from the actual cursor travel so left and right walking
                # never face the wrong way or flicker between frames.
                if abs(move_dx) >= 1:
                    self.anim.facing = 1 if move_dx > 0 else -1
                if self.anim.state != "walk":
                    self.anim.set("walk")
            elif self.anim.state != "drag":
                self.anim.set("drag")
                self.say_random(("wheee!", "hey!", "flying!", "woo!"), 1.2)
        except Exception:
            log_exc("on_drag")

    def on_release(self, ev):
        try:
            moved = 0
            if self._press_xy:
                moved = abs(ev.x_root - self._press_xy[0]) + abs(ev.y_root - self._press_xy[1])
            self._drag = None
            self._drag_last_x = None
            self.floor_y = self.y
            self.cfg["pos_x"], self.cfg["pos_y"] = int(self.x), int(self.y)
            self.cfg.save()
            if moved < 5:
                self.pet_me()
            else:
                self.anim.set("dizzy", 1.1, after="idle")
                self.say_random(("okay... woah", "put me down (:", "again!"), 1.6)
        except Exception:
            log_exc("on_release")

    def on_double(self, ev):
        try:
            if self.cfg.get("character") == "custom":
                sx, sy, sw, sh = self._screen_rect()
                dash = random.uniform(220, 380) * random.choice((-1, 1))
                tx = clamp(self.x + dash, sx + 20, sx + sw - self.cw - 20)
                self.target_x = tx
                self.anim.facing = 1 if tx > self.x else -1
                self.anim.set("run_cycle", 2.0, after="idle")
                self.say_random(("catch me!", "watch this!"), 1.6)
                return
        except Exception:
            log_exc("on_double.custom")
        safe(self.app.open_settings)

    def on_triple(self, ev):
        try:
            if self.cfg.get("character") == "custom":
                self.app.play_all_ganesh_emotes()
                self.say("Ganesh animation showcase", 2.4)
        except Exception:
            log_exc("on_triple")

    def on_enter(self, ev):
        try:
            if self.anim.state in ("idle", "sit") and time.time() > self.bubble_until:
                self.say(self.app.status_line(), 3.2)
        except Exception:
            log_exc("on_enter")

    def on_leave(self, ev):
        pass

    def on_menu(self, ev):
        safe(self.app.show_menu, ev.x_root, ev.y_root)

    def pet_me(self):
        """Left-click reaction - gets happier the more you pet."""
        try:
            now = time.time()
            if now - self.last_pet < 2.5:
                self.pet_count += 1
            else:
                self.pet_count = 1
            self.last_pet = now
            self.app.stats.bump("pets")
            is_ganesh = self.cfg.get("character") == "custom"
            if self.pet_count >= 4:
                if is_ganesh:
                    # no hearts or romantic lines for this one - warm
                    # gratitude instead, sparkles instead of hearts
                    self.anim.set("happy", 2.0, after="idle")
                    self.fx.burst_ring("sparkle", 0, 72, 9, color=SUN)
                    self.say_random(("thank you!", "bless you!", "so happy",
                                     "you're very kind"), 2.4)
                else:
                    self.anim.set("love", 2.0, after="idle")
                    self.fx.burst_ring("heart", 0, 72, 9, color=PINK)
                    self.say_random(("i love you too!", "best friend!", "you are the best",
                                     "happy happy happy"), 2.4)
                if self.cfg.get("sounds"):
                    play_chime("happy")
            elif self.pet_count >= 2:
                self.anim.set("dance", 2.2, after="idle")
                self.say_random(("dance party!", "wooo!", "yeah!"), 2.0)
            else:
                self.anim.set("happy", 1.1, after="idle")
                if is_ganesh:
                    self.fx.emit("sparkle", 0, 74, 5, power=0.7, color=SUN)
                else:
                    self.fx.emit("heart", 0, 74, 5, power=0.7, color=PINK)
                self.say_random(("hehe!", "hi!", "that tickles", "pat pat", "yay!",
                                 self.app.tiny_tip()), 2.2)
                if self.cfg.get("sounds"):
                    play_chime("soft")
        except Exception:
            log_exc("pet_me")

    # -------------------------------------------------------------- speech
    def say(self, text, seconds=3.5):
        if not text:
            return
        if not self.cfg.get("speech", True):
            return
        try:
            self.bubble_text = str(text)[:160]
            self.bubble_start = time.time()
            self.bubble_until = self.bubble_start + max(1.2, float(seconds))
        except Exception:
            log_exc("say")

    def say_random(self, options, seconds=3.0):
        try:
            self.say(random.choice(list(options)), seconds)
        except Exception:
            pass

    def shut_up(self):
        self.bubble_text = ""
        self.bubble_until = 0.0

    # ------------------------------------------------------------ movement
    def wander(self):
        """Stroll to a random spot on the current monitor."""
        try:
            if self.hidden or self._drag or self.anim.is_busy():
                return
            sx, sy, sw, sh = self._screen_rect()
            span = max(120, sw - self.cw - 60)
            tx = sx + 30 + random.random() * span
            if abs(tx - self.x) < 80:
                return
            self.target_x = tx
            self.anim.facing = 1 if tx > self.x else -1
            self.anim.set("walk")
            if random.random() < 0.25:
                self.say_random(("just stretching my legs", "wandering...", "la la la",
                                 "exploring!"), 2.2)
        except Exception:
            log_exc("wander")

    def go_home(self):
        try:
            sx, sy, sw, sh = self._screen_rect()
            self.x = sx + sw - self.cw - int(30 * self.s)
            self.y = sy + sh - self.ch + int(6 * self.s)
            self.floor_y = self.y
            self._clamp_into_screen()
            self._apply_geometry()
            self.cfg["pos_x"], self.cfg["pos_y"] = int(self.x), int(self.y)
            self.cfg.save()
        except Exception:
            log_exc("go_home")

    def _step_movement(self, dt):
        if self.target_x is None:
            return
        if self.anim.state not in ("walk", "run_cycle"):   # something more interesting happened
            self.target_x = None
            return
        try:
            if self.anim.state == "run_cycle":
                speed = 190.0 * self.s * dt        # a real dash, much faster than walking
            else:
                walk_scale = 0.6 if self.cfg.get("character") == "custom" else 1.0
                speed = 62.0 * self.s * walk_scale * dt
            dx = self.target_x - self.x
            if abs(dx) <= speed:
                self.x = self.target_x
                self.target_x = None
                if self.anim.state != "run_cycle":     # let the run trick finish its own timing
                    self.anim.set("idle")
                self.cfg["pos_x"], self.cfg["pos_y"] = int(self.x), int(self.y)
                self.cfg.save()
            else:
                self.x += speed * (1 if dx > 0 else -1)
            self._clamp_into_screen()
            self._apply_geometry()
        except Exception:
            log_exc("_step_movement")
            self.target_x = None

    def _update_cursor_look(self):
        """Make the eyes track the real mouse cursor, wherever it is on screen."""
        if self._drag or self.hidden:
            self.anim.cursor_dir = None
            return
        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()
            if px < -32000 or py < -32000:   # Windows returns this off-screen
                self.anim.cursor_dir = None
                return
            head_x = self.x + self.cw / 2.0
            head_y = self.y + self.ch - FOOT_PAD_UNITS * self.s - 62.0 * self.s
            dx, dy = px - head_x, py - head_y
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                self.anim.cursor_dir = [0.0, 0.0]
                return
            reach = clamp(dist / 260.0, 0.15, 1.0)   # subtle glance when far, fuller look when close
            self.anim.cursor_dir = [clamp((dx / dist) * reach, -1.0, 1.0),
                                     clamp((dy / dist) * reach, -0.6, 0.75)]
        except Exception:
            self.anim.cursor_dir = None

    # -------------------------------------------------------------- render
    def tick(self):
        """One animation frame.  Reschedules itself.  Never raises."""
        if not self.alive:
            return
        try:
            now = time.time()
            dt = now - self._last_frame
            self._last_frame = now
            dt = clamp(dt, 0.001, 0.12)

            self._update_cursor_look()
            self.anim.character = self.cfg.get("character", "dog")
            self.anim.update(dt)
            self.fx.update(dt)
            if getattr(self.app, "modak_scene", None) is None:
                self._step_movement(dt)
            if (self.cfg.get("character") == "custom" and not self._drag
                    and self.anim.state == "idle"
                    and now - self.last_ganesh_interaction >= 60.0):
                self.anim.set("ganesh_rest")

            if not self.hidden:
                self.draw()

            # keep ourselves above full-screen apps that grab the top spot
            self._topmost_tick += dt
            if self._topmost_tick > 3.0:
                self._topmost_tick = 0.0
                if self.cfg.get("always_on_top", True) and not self.hidden:
                    try:
                        self.root.attributes("-topmost", True)
                    except Exception:
                        pass
                    WIN.push_topmost(self.root)
        except Exception:
            log_exc("Buddy.tick")

        try:
            delay = int(1000 * self._frame_budget)
            self.root.after(max(10, delay), self.tick)
        except Exception:
            log_exc("tick.reschedule")

    def draw(self):
        scene = getattr(self.app, "modak_scene", None)
        if scene is not None and not scene.closed:
            scene.draw_ganesh()
            return
        c = self.canvas
        try:
            c.delete("all")
        except Exception:
            return
        try:
            p = self.anim.pose()
            ax = self.cw / 2.0 + p.get("dx", 0.0) * self.s
            ay = self.ch - FOOT_PAD_UNITS * self.s - p.get("bob", 0.0) * self.s
            self.pn.setup(ax, ay, self.s, flip=p.get("face", self.anim.facing),
                          sx=p.get("sx", 1.0), sy=p.get("sy", 1.0))

            drawer = CHAR_DRAWERS.get(self.cfg.get("character", "dog"), draw_dog)
            colors = CHAR_COLORS.get(self.cfg.get("character", "dog"), CHAR_COLORS["dog"])
            drawer(self.pn, p, colors)

            # particles live in the same unit space but never mirror
            self.pn.setup(self.cw / 2.0, self.ch - FOOT_PAD_UNITS * self.s, self.s,
                          flip=1, sx=1.0, sy=1.0)
            self.fx.draw(self.pn)

            self._draw_bubble()
        except Exception:
            log_exc("Buddy.draw")

    def _draw_bubble(self):
        if not self.bubble_text:
            return
        try:
            now = time.time()
            if now > self.bubble_until:
                self.bubble_text = ""
                return
            # typewriter reveal
            elapsed = now - self.bubble_start
            n = int(elapsed / 0.022)
            shown = self.bubble_text[:max(1, n)]

            c = self.canvas
            max_w = int(self.cw - 26)
            font = ui_font(max(8, int(9.4 * self.s)), bold=False)
            head_px = self.ch - FOOT_PAD_UNITS * self.s - 96 * self.s
            tx = self.cw / 2.0
            ty = max(16, head_px - 22 * self.s)

            tid = c.create_text(tx, ty, text=shown, width=max_w, fill=INK,
                                font=font, anchor="s", justify="center")
            bb = c.bbox(tid)
            if not bb:
                return
            pad = max(7, int(7 * self.s))
            x0, y0, x1, y1 = bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad
            # keep it inside the window
            if x0 < 3:
                shift = 3 - x0
                c.move(tid, shift, 0)
                x0, x1 = x0 + shift, x1 + shift
            if x1 > self.cw - 3:
                shift = x1 - (self.cw - 3)
                c.move(tid, -shift, 0)
                x0, x1 = x0 - shift, x1 - shift
            if y0 < 3:
                shift = 3 - y0
                c.move(tid, 0, shift)
                y0, y1 = y0 + shift, y1 + shift

            # pop-in animation
            age = now - self.bubble_start
            k = ease_out_back(clamp(age / 0.22, 0, 1))
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            hw, hh = (x1 - x0) / 2.0 * k, (y1 - y0) / 2.0 * k

            tail_x = clamp(self.cw / 2.0, x0 + 14, x1 - 14)
            body = px_round_rect(c, cx - hw, cy - hh, cx + hw, cy + hh,
                                 max(8, 10 * self.s), fill=WHITE,
                                 outline=INK, width=max(1, int(1.6 * self.s)))
            tail = c.create_polygon(
                tail_x - 7 * self.s, cy + hh - 1,
                tail_x + 7 * self.s, cy + hh - 1,
                tail_x + 1 * self.s, cy + hh + 11 * self.s,
                fill=WHITE, outline=INK, width=max(1, int(1.6 * self.s)))
            c.tag_lower(tail, tid)
            c.tag_lower(body, tail)
            # hide the seam where the tail meets the bubble
            seam = c.create_line(tail_x - 6 * self.s, cy + hh - 1,
                                 tail_x + 6 * self.s, cy + hh - 1,
                                 fill=WHITE, width=max(2, int(2.6 * self.s)))
            c.tag_lower(seam, tid)
            c.tag_raise(seam, tail)
        except Exception:
            log_exc("_draw_bubble")

    # ------------------------------------------------------------ lifecycle
    def rebuild_scale(self):
        """Apply a new size without restarting."""
        self.app.stop_modak_scene()
        try:
            self.s = UNIT_PX * float(self.cfg.get("scale", 1.0)) * UI_K
            self.cw = int(WIN_W_UNITS * self.s)
            self.ch = int(WIN_H_UNITS * self.s)
            self.canvas.config(width=self.cw, height=self.ch)
            self.root.geometry("%dx%d+%d+%d" % (self.cw, self.ch, int(self.x), int(self.y)))
            self._clamp_into_screen()
            self._apply_geometry()
            self._frame_budget = 1.0 / max(12, int(self.cfg.get("fps", 30)))
        except Exception:
            log_exc("rebuild_scale")

    def hide(self, yes=True):
        if yes:
            self.app.stop_modak_scene()
        try:
            self.hidden = bool(yes)
            if yes:
                self.root.withdraw()
            else:
                self.root.deiconify()
                self.root.after(60, lambda: WIN.set_tool_window(self.root))
                try:
                    self.root.attributes("-topmost", True)
                except Exception:
                    pass
                self._apply_geometry()
        except Exception:
            log_exc("hide")


# --------------------------------------------------------------------------
#  Floating window helpers
# --------------------------------------------------------------------------
def make_float(parent, w, h, key=True, alpha=None, click_through_bg=True):
    """A borderless always-on-top Toplevel with a transparent background."""
    win = tk.Toplevel(parent)
    try:
        win.overrideredirect(True)
    except Exception:
        pass
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    transparent = False
    if key:
        try:
            win.configure(bg=KEY_COLOR)
            win.attributes("-transparentcolor", KEY_COLOR)
            transparent = True
        except Exception:
            transparent = False
    if not transparent:
        try:
            win.configure(bg=CREAM)
        except Exception:
            pass
    if alpha is not None:
        try:
            win.attributes("-alpha", alpha)
        except Exception:
            pass
    bg = KEY_COLOR if transparent else CREAM
    cv = tk.Canvas(win, width=w, height=h, bg=bg, highlightthickness=0, bd=0,
                   takefocus=0)
    cv.pack(fill="both", expand=True)
    win.geometry("%dx%d" % (int(w), int(h)))
    del click_through_bg
    return win, cv, transparent


class CanvasButton:
    """A rounded button drawn on a canvas (no ttk theming surprises)."""

    def __init__(self, canvas, x, y, w, h, text, command,
                 fill=MINT, text_color="#20343A", font_size=10, radius=None):
        self.c = canvas
        self.command = command
        self.fill = fill
        self.x, self.y, self.w, self.h = x, y, w, h
        r = radius if radius is not None else h / 2.0
        self.bg = px_round_rect(canvas, x, y, x + w, y + h, r,
                                fill=fill, outline=shade(fill, 0.82), width=1)
        self.tx = canvas.create_text(x + w / 2.0, y + h / 2.0, text=text,
                                     fill=text_color, font=ui_font(font_size, True))
        for item in (self.bg, self.tx):
            canvas.tag_bind(item, "<Button-1>", self._click)
            canvas.tag_bind(item, "<Enter>", self._enter)
            canvas.tag_bind(item, "<Leave>", self._leave)

    def _click(self, _ev=None):
        safe(self.command)

    def _enter(self, _ev=None):
        try:
            self.c.itemconfig(self.bg, fill=shade(self.fill, 1.12))
            self.c.config(cursor="hand2")
        except Exception:
            pass

    def _leave(self, _ev=None):
        try:
            self.c.itemconfig(self.bg, fill=self.fill)
            self.c.config(cursor="")
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Reminder card  (the animated notification)
# --------------------------------------------------------------------------
class ReminderCard:
    WIDTH = 340
    HEIGHT = 168

    def __init__(self, app, title, message, buttons=None, accent=MINT,
                 seconds=30, icon="bell"):
        self.app = app
        self.root = app.root
        self.title = title
        self.message = message
        self.accent = accent
        self.icon = icon
        self.buttons = buttons or [("Got it", None)]
        self.seconds = max(6, int(seconds))
        self.born = time.time()
        self.paused = False
        self.closed = False
        self.alpha = 0.0
        self.slide = 0.0
        self.win = None
        self.cv = None
        self.s = clamp(float(app.cfg.get("scale", 1.0)), 0.85, 1.35) * UI_K
        safe(self._build)

    # ---------------------------------------------------------------- build
    def _build(self):
        w = int(self.WIDTH * self.s)
        h = int(self.HEIGHT * self.s)
        self.w, self.h = w, h
        self.win, self.cv, self.transparent = make_float(self.root, w, h, key=True, alpha=0.0)
        WIN.set_tool_window(self.win, no_activate=True)
        self._last_anim = time.time()
        self._position()
        self._render()
        self.cv.bind("<Enter>", lambda e: setattr(self, "paused", True))
        self.cv.bind("<Leave>", lambda e: setattr(self, "paused", False))
        self._animate()

    def _position(self):
        try:
            b = self.app.buddy
            sx, sy, sw, sh = b._screen_rect()
            cx = b.x + b.cw / 2.0 - self.w / 2.0
            cy = b.y - self.h - 6
            if cy < sy + 8:
                cy = b.y + b.ch - 10
            cx = clamp(cx, sx + 8, sx + sw - self.w - 8)
            cy = clamp(cy, sy + 8, sy + sh - self.h - 8)
            self.px, self.py = cx, cy
            self.win.geometry("+%d+%d" % (int(cx), int(cy + 18)))
        except Exception:
            log_exc("card._position")
            self.px, self.py = 80, 80

    # --------------------------------------------------------------- render
    def _render(self, progress=1.0):
        c = self.cv
        try:
            c.delete("all")
        except Exception:
            return
        w, h, s = self.w, self.h, self.s
        pad = 6 * s

        # soft outer glow
        px_round_rect(c, pad - 3 * s, pad - 3 * s, w - pad + 3 * s, h - pad + 3 * s,
                      18 * s, fill=shade(self.accent, 1.25), outline="", stipple="gray25")
        # card
        px_round_rect(c, pad, pad, w - pad, h - pad, 16 * s,
                      fill=CREAM, outline=INK, width=max(1, int(1.8 * s)))
        # accent header
        px_round_rect(c, pad, pad, w - pad, pad + 44 * s, 16 * s,
                      fill=self.accent, outline="")
        c.create_rectangle(pad, pad + 30 * s, w - pad, pad + 44 * s,
                           fill=self.accent, outline="")
        c.create_line(pad, pad + 44 * s, w - pad, pad + 44 * s,
                      fill=INK, width=max(1, int(1.8 * s)))

        self._draw_icon(pad + 24 * s, pad + 22 * s, 13 * s)

        c.create_text(pad + 46 * s, pad + 22 * s, text=self.title, anchor="w",
                      fill="#2E2320", font=ui_font(int(11 * s) + 1, True))

        c.create_text(w / 2.0, pad + 74 * s, text=self.message, anchor="center",
                      width=w - 34 * s, justify="center", fill=INK,
                      font=ui_font(int(10 * s)))

        # buttons
        n = len(self.buttons)
        bw = (w - 2 * pad - 16 * s - (n - 1) * 8 * s) / max(1, n)
        bh = 30 * s
        by = h - pad - bh - 10 * s
        bx = pad + 8 * s
        self._btn_objs = []
        for i, (label, cb) in enumerate(self.buttons):
            fill = self.accent if i == 0 else "#ECE4DA"
            self._btn_objs.append(CanvasButton(
                c, bx, by, bw, bh, label,
                (lambda f=cb: self._do(f)), fill=fill,
                text_color="#2E2320", font_size=max(8, int(9.4 * s))))
            bx += bw + 8 * s

        # countdown bar (only this gets updated while the card is on screen)
        self._bar_y = h - pad - 5 * s
        self._bar_x0 = pad + 12 * s
        self._bar_x1 = w - pad - 12 * s
        c.create_line(self._bar_x0, self._bar_y, self._bar_x1, self._bar_y,
                      fill="#E3D9CD", width=max(2, int(3 * s)), capstyle="round")
        self.bar_fg = c.create_line(self._bar_x0, self._bar_y, self._bar_x1, self._bar_y,
                                    fill=shade(self.accent, 0.9),
                                    width=max(2, int(3 * s)), capstyle="round")
        self._set_progress(progress)

        # close x
        cxx, cyy = w - pad - 16 * s, pad + 22 * s
        xid = c.create_text(cxx, cyy, text="x", fill="#2E2320",
                            font=ui_font(int(12 * s), True))
        c.tag_bind(xid, "<Button-1>", lambda e: self.close())

    def _set_progress(self, p):
        try:
            p = clamp(p, 0.0, 1.0)
            if p <= 0.005:
                self.cv.itemconfigure(self.bar_fg, state="hidden")
                return
            self.cv.itemconfigure(self.bar_fg, state="normal")
            self.cv.coords(self.bar_fg, self._bar_x0, self._bar_y,
                           self._bar_x0 + (self._bar_x1 - self._bar_x0) * p, self._bar_y)
        except Exception:
            pass

    def _draw_icon(self, cx, cy, r):
        c = self.cv
        try:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CREAM, outline=INK,
                          width=max(1, int(1.4 * self.s)))
            k = self.icon
            col = INK
            if k == "cup":
                c.create_rectangle(cx - r * 0.45, cy - r * 0.35, cx + r * 0.35, cy + r * 0.5,
                                   fill=SKY, outline=col, width=1)
                c.create_arc(cx + r * 0.2, cy - r * 0.3, cx + r * 0.8, cy + r * 0.2,
                             start=270, extent=180, style=tk.ARC, outline=col, width=1)
            elif k == "eye":
                c.create_oval(cx - r * 0.7, cy - r * 0.35, cx + r * 0.7, cy + r * 0.35,
                              fill=WHITE, outline=col, width=1)
                c.create_oval(cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22,
                              fill=col, outline="")
            elif k == "leaf":
                c.create_oval(cx - r * 0.6, cy - r * 0.3, cx + r * 0.6, cy + r * 0.45,
                              fill=LEAF, outline=col, width=1)
                c.create_line(cx - r * 0.5, cy + r * 0.35, cx + r * 0.5, cy - r * 0.2,
                              fill=col, width=1)
            elif k == "bolt":
                c.create_polygon(cx - r * 0.2, cy - r * 0.6, cx + r * 0.35, cy - r * 0.05,
                                 cx + r * 0.02, cy - r * 0.02, cx + r * 0.22, cy + r * 0.62,
                                 cx - r * 0.38, cy + r * 0.02, cx - r * 0.02, cy + r * 0.02,
                                 fill=SUN, outline=col, width=1)
            elif k == "moon":
                c.create_arc(cx - r * 0.65, cy - r * 0.65, cx + r * 0.65, cy + r * 0.65,
                             start=40, extent=280, style=tk.CHORD, fill=LAV, outline=col, width=1)
            elif k == "clock":
                c.create_oval(cx - r * 0.65, cy - r * 0.65, cx + r * 0.65, cy + r * 0.65,
                              fill=WHITE, outline=col, width=1)
                c.create_line(cx, cy, cx, cy - r * 0.42, fill=col, width=1)
                c.create_line(cx, cy, cx + r * 0.32, cy, fill=col, width=1)
            elif k == "star":
                pts = []
                for i in range(10):
                    rad = r * 0.72 if i % 2 == 0 else r * 0.3
                    a = math.radians(i * 36 - 90)
                    pts.extend((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
                c.create_polygon(*pts, fill=SUN, outline=col, width=1)
            elif k == "food":
                c.create_oval(cx - r * 0.55, cy - r * 0.05, cx + r * 0.55, cy + r * 0.55,
                              fill="#FFE9B8", outline=col, width=1)
                c.create_polygon(cx - r * 0.28, cy - r * 0.02, cx, cy - r * 0.55,
                                 cx + r * 0.28, cy - r * 0.02,
                                 fill="#FFE9B8", outline=col, width=1)
            elif k == "body":
                c.create_oval(cx - r * 0.18, cy - r * 0.62, cx + r * 0.18, cy - r * 0.26,
                              fill=PEACH, outline=col, width=1)
                c.create_line(cx, cy - r * 0.26, cx, cy + r * 0.2, fill=col, width=2)
                c.create_line(cx - r * 0.42, cy - r * 0.05, cx + r * 0.42, cy - r * 0.05,
                              fill=col, width=2)
                c.create_line(cx, cy + r * 0.2, cx - r * 0.3, cy + r * 0.62, fill=col, width=2)
                c.create_line(cx, cy + r * 0.2, cx + r * 0.3, cy + r * 0.62, fill=col, width=2)
            else:  # bell
                c.create_arc(cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.45,
                             start=0, extent=180, style=tk.CHORD, fill=SUN,
                             outline=col, width=1)
                c.create_line(cx - r * 0.62, cy + r * 0.42, cx + r * 0.62, cy + r * 0.42,
                              fill=col, width=1)
                c.create_oval(cx - r * 0.13, cy + r * 0.42, cx + r * 0.13, cy + r * 0.68,
                              fill=SUN, outline=col, width=1)
        except Exception:
            log_exc("card._draw_icon")

    # -------------------------------------------------------------- animate
    def _animate(self):
        if self.closed:
            return
        try:
            now = time.time()
            if self.paused:
                self.born += (now - self._last_anim)      # hovering pauses the timer
            self._last_anim = now
            age = now - self.born
            # slide + fade in
            k = ease_out_back(clamp(age / 0.42, 0, 1))
            self.alpha = clamp(age / 0.28, 0, 1) * 0.98
            try:
                self.win.attributes("-alpha", self.alpha)
            except Exception:
                pass
            try:
                self.win.geometry("+%d+%d" % (int(self.px), int(self.py + (1 - k) * 26)))
            except Exception:
                pass

            left = self.seconds - age
            if left <= 0:
                self.close()
                return
            self._set_progress(clamp(left / float(self.seconds), 0, 1))
            WIN.push_topmost(self.win)
            self.root.after(60, self._animate)
        except Exception:
            log_exc("card._animate")
            self.close()

    def _do(self, cb):
        self.close()
        if cb:
            safe(cb)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.app.card is self:
                self.app.card = None
        except Exception:
            pass

        def fade(step=0):
            try:
                a = max(0.0, 0.98 - step * 0.18)
                self.win.attributes("-alpha", a)
                if a <= 0.02:
                    self.win.destroy()
                else:
                    self.root.after(22, lambda: fade(step + 1))
            except Exception:
                try:
                    self.win.destroy()
                except Exception:
                    pass
        safe(fade)


# --------------------------------------------------------------------------
#  Guided breathing / meditation overlay
# --------------------------------------------------------------------------
BREATH_PATTERNS = {
    "box":  [("Breathe in", 4.0), ("Hold", 4.0), ("Breathe out", 4.0), ("Hold", 4.0)],
    "478":  [("Breathe in", 4.0), ("Hold", 7.0), ("Breathe out", 8.0)],
    "calm": [("Breathe in", 4.0), ("Breathe out", 6.0)],
}
BREATH_LABEL = {"box": "Box breathing 4-4-4-4",
                "478": "Relaxing 4-7-8",
                "calm": "Calm 4-6"}


class BreathOverlay:
    SIZE = 460

    def __init__(self, app, pattern=None, cycles=None, on_done=None):
        self.app = app
        self.root = app.root
        self.cfg = app.cfg
        self.pattern_key = pattern or self.cfg.get("breath_pattern", "box")
        self.steps = BREATH_PATTERNS.get(self.pattern_key, BREATH_PATTERNS["box"])
        self.cycles = int(cycles or self.cfg.get("breath_cycles", 6))
        self.on_done = on_done
        self.closed = False
        self.cycle = 0
        self.step_i = 0
        self.step_t = 0.0
        self.finished = False
        self.finish_t = 0.0
        self.last = time.time()
        self.dim = None
        self.s = clamp(float(self.cfg.get("scale", 1.0)), 0.9, 1.4) * UI_K
        safe(self._build)

    def _build(self):
        size = int(self.SIZE * self.s)
        self.size = size

        if self.cfg.get("dim_on_breathe", True):
            try:
                self.dim = tk.Toplevel(self.root)
                self.dim.overrideredirect(True)
                self.dim.configure(bg="#10131A")
                self.dim.attributes("-topmost", True)
                self.dim.attributes("-alpha", 0.0)
                vs = WIN.virtual_screen() or (0, 0, self.root.winfo_screenwidth(),
                                              self.root.winfo_screenheight())
                self.dim.geometry("%dx%d+%d+%d" % (vs[2], vs[3], vs[0], vs[1]))
                self.dim.bind("<Button-1>", lambda e: self.close())
                self.dim.bind("<Escape>", lambda e: self.close())
            except Exception:
                log_exc("breath.dim")
                self.dim = None

        self.win, self.cv, self.transparent = make_float(self.root, size, size,
                                                         key=True, alpha=0.0)
        try:
            sx, sy, sw, sh = self.app.buddy._screen_rect()
            self.win.geometry("+%d+%d" % (int(sx + (sw - size) / 2), int(sy + (sh - size) / 2)))
        except Exception:
            pass
        for w in (self.win, self.cv):
            try:
                w.bind("<Escape>", lambda e: self.close())
                w.bind("<Return>", lambda e: self.close())
                w.bind("<space>", lambda e: self.close())
                w.bind("<Button-1>", lambda e: self.close())
            except Exception:
                pass
        try:
            self.win.focus_force()
        except Exception:
            pass

        self.app.buddy.anim.set("meditate")
        self.app.buddy.shut_up()
        if self.cfg.get("sounds"):
            play_chime("calm")
        self._tick()

    # ------------------------------------------------------------ mechanics
    def _phase_amount(self):
        """0 = fully exhaled, 1 = fully inhaled."""
        label, dur = self.steps[self.step_i]
        t = clamp(self.step_t / max(0.1, dur), 0, 1)
        if label == "Breathe in":
            return ease_in_out(t)
        if label == "Breathe out":
            return 1.0 - ease_in_out(t)
        # a hold keeps whatever the previous step ended on
        prev = self.steps[(self.step_i - 1) % len(self.steps)][0]
        return 1.0 if prev == "Breathe in" else 0.0

    def _tick(self):
        if self.closed:
            return
        try:
            now = time.time()
            dt = clamp(now - self.last, 0.001, 0.15)
            self.last = now

            if not self.finished:
                self.step_t += dt
                label, dur = self.steps[self.step_i]
                if self.step_t >= dur:
                    self.step_t = 0.0
                    self.step_i += 1
                    if self.step_i >= len(self.steps):
                        self.step_i = 0
                        self.cycle += 1
                        if self.cfg.get("sounds") and self.cycle < self.cycles:
                            play_chime("soft")
                        if self.cycle >= self.cycles:
                            self.finished = True
                            self.finish_t = now
                            self.app.on_breath_complete(self.cycles)
            else:
                if now - self.finish_t > 2.6:
                    self.close()
                    return

            amt = self._phase_amount() if not self.finished else 1.0
            self.app.buddy.anim.breath_scale = amt
            self._render(amt)

            # fade the layers in
            try:
                cur = float(self.win.attributes("-alpha") or 0)
                self.win.attributes("-alpha", min(0.985, cur + 0.09))
            except Exception:
                pass
            if self.dim is not None:
                try:
                    cur = float(self.dim.attributes("-alpha") or 0)
                    self.dim.attributes("-alpha", min(0.5, cur + 0.045))
                except Exception:
                    pass
            WIN.push_topmost(self.win)
            self.root.after(33, self._tick)
        except Exception:
            log_exc("breath._tick")
            self.close()

    # --------------------------------------------------------------- render
    def _render(self, amt):
        c = self.cv
        try:
            c.delete("all")
        except Exception:
            return
        size = self.size
        cx = cy = size / 2.0
        s = self.s

        px_round_rect(c, 8 * s, 8 * s, size - 8 * s, size - 8 * s, 30 * s,
                      fill="#1D2230", outline="#39405A", width=max(1, int(2 * s)))

        label, dur = self.steps[self.step_i]
        if self.finished:
            label = "Beautifully done"

        base = size * 0.125
        span = size * 0.135
        r = base + span * amt

        # aura rings
        for i, mult in enumerate((1.78, 1.46, 1.21)):
            rr = r * mult * (0.92 + 0.08 * amt)
            col = mix("#2B3350", LAV, 0.25 + 0.2 * i)
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=col,
                          width=max(1, int(1.6 * s)))
        glow = r * 1.22
        c.create_oval(cx - glow, cy - glow, cx + glow, cy + glow,
                      fill=mix("#232A42", LAV, 0.35), outline="", stipple="gray25")

        # the breathing orb
        top = mix(LAV, "#FFFFFF", 0.25)
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill=mix(LAV, MINT, 0.35 * amt), outline=top,
                      width=max(1, int(2 * s)))
        c.create_oval(cx - r * 0.55, cy - r * 0.62, cx - r * 0.02, cy - r * 0.18,
                      fill=mix("#FFFFFF", LAV, 0.35), outline="", stipple="gray50")

        # orbiting dot marks the phase
        if not self.finished:
            ang = -90 + 360 * clamp(self.step_t / max(0.1, dur), 0, 1)
            ox = cx + math.cos(math.radians(ang)) * (r * 1.42)
            oy = cy + math.sin(math.radians(ang)) * (r * 1.42)
            c.create_oval(ox - 5 * s, oy - 5 * s, ox + 5 * s, oy + 5 * s,
                          fill=WHITE, outline="")

        c.create_text(cx, cy - 10 * s, text=label, fill=WHITE,
                      font=ui_font(int(17 * s), True))
        if not self.finished:
            left = max(0, int(math.ceil(dur - self.step_t)))
            c.create_text(cx, cy + 18 * s, text=str(left), fill=mix(WHITE, LAV, 0.5),
                          font=ui_font(int(26 * s), True))
        else:
            c.create_text(cx, cy + 20 * s, text="%d cycles" % self.cycles,
                          fill=mix(WHITE, LAV, 0.5), font=ui_font(int(13 * s)))

        c.create_text(cx, 44 * s, text=BREATH_LABEL.get(self.pattern_key, "Breathing"),
                      fill=mix(WHITE, "#8890B5", 0.5), font=ui_font(int(11 * s), True))

        # cycle dots
        n = self.cycles
        dot_r = 5.0 * s
        gap = 16 * s
        total = (n - 1) * gap
        for i in range(n):
            x = cx - total / 2.0 + i * gap
            y = size - 76 * s
            done = i < self.cycle
            c.create_oval(x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                          fill=(MINT if done else "#39405A"), outline="")

        bw, bh = 132 * s, 30 * s
        bx, by = cx - bw / 2.0, size - 52 * s
        px_round_rect(c, bx, by, bx + bw, by + bh, bh / 2.0,
                      fill="#2B3350", outline="#4A5478", width=max(1, int(1.4 * s)))
        c.create_text(cx, by + bh / 2.0, text="Finish  (or click)", fill="#C9CFE8",
                      font=ui_font(int(9.5 * s), True))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.app.buddy.anim.breath_scale = 0.0
            if self.app.buddy.anim.state == "meditate":
                self.app.buddy.anim.set("idle")
        except Exception:
            pass
        try:
            if self.app.breath is self:
                self.app.breath = None
        except Exception:
            pass

        def fade(step=0):
            try:
                a = max(0.0, 1.0 - step * 0.16)
                for w, mx in ((self.win, 0.985), (self.dim, 0.5)):
                    if w is not None:
                        try:
                            w.attributes("-alpha", min(mx, a * mx))
                        except Exception:
                            pass
                if a <= 0.02:
                    for w in (self.win, self.dim):
                        if w is not None:
                            try:
                                w.destroy()
                            except Exception:
                                pass
                else:
                    self.root.after(24, lambda: fade(step + 1))
            except Exception:
                for w in (self.win, self.dim):
                    if w is not None:
                        try:
                            w.destroy()
                        except Exception:
                            pass
        safe(fade)
        if self.on_done:
            safe(self.on_done)


# --------------------------------------------------------------------------
#  Focus timer chip  (small pill that floats above the buddy)
# --------------------------------------------------------------------------
class TimerChip:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.s = clamp(float(app.cfg.get("scale", 1.0)), 0.85, 1.3) * UI_K
        self.w = int(128 * self.s)
        self.h = int(38 * self.s)
        self.closed = False
        self.win, self.cv, self.transparent = make_float(self.root, self.w, self.h,
                                                         key=True, alpha=0.96)
        WIN.set_tool_window(self.win, no_activate=True)
        self.cv.bind("<Button-1>", lambda e: safe(self.app.stop_focus, True))
        self._tick()

    def _tick(self):
        if self.closed:
            return
        try:
            f = self.app.focus
            if not f:
                self.close()
                return
            left = max(0, f["end"] - time.time())
            total = max(1.0, f["total"])
            frac = clamp(1.0 - left / total, 0, 1)
            mm, ss = int(left // 60), int(left % 60)

            b = self.app.buddy
            x = b.x + b.cw / 2.0 - self.w / 2.0
            sx, sy, sw, sh = b._screen_rect()
            y = b.y + b.ch - 6 * self.s
            if y + self.h > sy + sh - 4:          # no room under the feet
                y = b.y + 2 * self.s              # ... so sit above the head
            x = clamp(x, sx + 4, sx + sw - self.w - 4)
            y = clamp(y, sy + 4, sy + sh - self.h - 4)
            self.win.geometry("+%d+%d" % (int(x), int(y)))

            c = self.cv
            c.delete("all")
            accent = PINK if f["kind"] == "focus" else MINT
            px_round_rect(c, 2, 2, self.w - 2, self.h - 2, (self.h - 4) / 2.0,
                          fill=CREAM, outline=INK, width=max(1, int(1.6 * self.s)))
            px_round_rect(c, 4, self.h - 10 * self.s, self.w - 4, self.h - 5 * self.s,
                          3 * self.s, fill="#E3D9CD", outline="")
            if frac > 0.01:
                px_round_rect(c, 4, self.h - 10 * self.s,
                              4 + (self.w - 8) * frac, self.h - 5 * self.s,
                              3 * self.s, fill=accent, outline="")
            r = 8 * self.s
            cx0 = 16 * self.s
            cy0 = self.h / 2.0 - 2 * self.s
            c.create_oval(cx0 - r, cy0 - r, cx0 + r, cy0 + r, fill=accent,
                          outline=INK, width=1)
            c.create_line(cx0, cy0, cx0, cy0 - r * 0.55, fill=INK, width=max(1, int(1.4 * self.s)))
            c.create_line(cx0, cy0, cx0 + r * 0.45, cy0, fill=INK, width=max(1, int(1.4 * self.s)))
            c.create_text(self.w / 2.0 + 10 * self.s, cy0,
                          text="%02d:%02d" % (mm, ss), fill=INK,
                          font=ui_font(int(12 * self.s), True))
            WIN.push_topmost(self.win)
            self.root.after(250, self._tick)
        except Exception:
            log_exc("TimerChip._tick")
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except Exception:
            pass
        try:
            if self.app.chip is self:
                self.app.chip = None
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Things the buddy says
# --------------------------------------------------------------------------
MSG = {
    "break": [
        "You've been at it for {mins} minutes straight - take {len} min to move however feels good to you?",
        "{mins} minutes of solid work, nice. Your body would love a change of position now.",
        "Time for a proper break. Stretch, look away from the screen, step away if you can.",
        "{mins} minutes without stopping. Let's pause for {len} minutes together, okay?",
        "Great focus for {mins} minutes! Now give yourself {len} minutes to just not work.",
    ],
    "eye": [
        "Quick eye break: find something about 20 feet away and look at it for 20 seconds.",
        "Your eyes have been locked on this screen a while - look far away for 20 seconds and blink a few times, slowly.",
        "20-20-20 time. Every 20 minutes, 20 feet away, 20 seconds - and don't forget to blink, screens make us forget to.",
        "Give your eyes a moment. Look at something distant, and blink properly a few times - it re-wets them.",
    ],
    "water": [
        "Water check! Go grab a glass of water and take a few good sips.",
        "Hydration break - your brain is about 75% water, so top the glass up.",
        "Have some water. Even half a glass right now genuinely helps your focus.",
        "When did you last fill your glass? Now's a good moment for a proper drink of water.",
        "Small nudge: a glass of water nearby helps more than another cup of coffee.",
    ],
    "stretch": [
        "Stretch time: {idea}",
        "Let's loosen up a little. {idea}",
        "Quick body check: {idea}",
        "Your muscles have been sitting still too long - {idea}",
    ],
    "hunger": [
        "Getting a little hungry over here. Have you eaten something today?",
        "Snack check - a proper bite of food helps more than another coffee.",
        "When did you last eat? Might be worth a small break for food.",
    ],
    "breakfast": [
        "Morning! This is around your usual breakfast time - don't skip it.",
        "Breakfast time, by your own schedule. Worth fueling up before the day gets going.",
    ],
    "lunch": [
        "It's about your usual lunch time - a proper break helps more than working through it.",
        "Lunch time, based on what you told me. Step away and eat something.",
    ],
    "dinner": [
        "This is around your usual dinner time - a good moment to wrap up and eat.",
        "Dinner time, by your own schedule. The work will still be there after.",
    ],
    "posture": [
        "Posture check: whatever position you're in, see if your shoulders can relax and your screen can move to eye level.",
        "Notice how you're sitting or standing right now. Unclench your jaw and drop those shoulders.",
        "Small adjustment time - shift your weight, relax your neck, let your shoulders settle.",
        "Notice your shoulders right now? They probably crept up toward your ears again.",
    ],
    "meditate": [
        "Want to breathe with me for a minute? It resets everything, honestly.",
        "A minute of slow breathing would feel really good right now.",
        "Let's calm down together for a moment. Just a few slow breaths.",
        "Everything can wait 60 seconds - let's breathe together.",
    ],
    "night": [
        "It's {time} now. Screens make it harder to fall asleep - maybe start wrapping up?",
        "Getting late out there. Your tomorrow self is quietly asking you to go to bed soon.",
        "It's late. Save your work, and let yourself rest - it'll still be there tomorrow.",
    ],
    "battery_low": [
        "Battery's down to {pct}%. Might be time to plug in before it dies mid-thought.",
        "Only {pct}% left on the battery - worth finding a charger before it gets awkward.",
        "Power is low - {pct}% left. Go grab your charger and plug the laptop in.",
    ],
    "battery_full": [
        "Battery's full at {pct}%. Feel free to unplug and let it breathe a little.",
    ],
    "same_app": [
        "You've been in {app} for {mins} minutes now. Might be worth a short pause?",
        "{mins} minutes inside {app} - a good moment to blink, breathe, and stretch.",
    ],
}

STRETCH_IDEAS = [
    "roll your shoulders backwards 10 times, nice and slow",
    "tilt your head gently to each side and hold for 15 seconds",
    "reach both arms up toward the ceiling, as high as feels good",
    "open your chest, squeeze your shoulder blades together for a few seconds",
    "stretch your wrists and fingers, you have been typing a lot",
    "twist gently from side to side, wherever you're sitting or standing",
    "if you're able to, stand for a moment and do a few slow calf raises",
    "look up and breathe out slowly, let your neck relax",
    "shake out both hands for 10 seconds, let them go loose",
    "if you can, change position for a minute - a short walk, a stretch, or just shifting in your seat all count",
    "clench and release your hands a few times, then let your shoulders drop",
    "gently stretch your ankles and feet if you can reach them",
]

TIPS = [
    "drink water before you feel thirsty",
    "your eyes need to look far away sometimes",
    "a 5 minute change of scenery beats a 5 minute scroll",
    "unclench your jaw right now",
    "breathe out longer than you breathe in to calm down",
    "changing position for 2 minutes resets your back",
    "you are doing better than you think",
    "rest is part of the work, not a break from it",
    "blink. properly. a few times",
    "shoulders down, they crept up again",
    "it's okay to do less today than yesterday",
    "a short pause now saves a longer one later",
]

GREET = {
    "morning": ["Good morning! Let's have a kind day.",
                "Morning! Water first, then work.",
                "Hi! A fresh day, take it gently."],
    "afternoon": ["Good afternoon! How is it going?",
                  "Afternoon check in. Shoulders down.",
                  "Hey! Half the day done already."],
    "evening": ["Good evening! Wind down soon.",
                "Evening! Remember to eat something.",
                "Hi! Let's finish the day nicely."],
    "night": ["It is late. I will stay up with you, but not too long.",
              "Night owl mode. Be gentle with yourself.",
              "Still up? Let's wrap up soon."],
}

PRAISE = [
    "nice one!", "proud of you", "that is the way", "good job!",
    "you did the hard thing", "look at you go", "streak continues!",
]


def pick(key, **fmt):
    try:
        return random.choice(MSG[key]).format(**fmt)
    except Exception:
        try:
            return MSG[key][0]
        except Exception:
            return "Time for a little break."


def part_of_day(hour=None):
    h = datetime.now().hour if hour is None else hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


# --------------------------------------------------------------------------
#  Reminder scheduler
# --------------------------------------------------------------------------
class Reminders:
    """Counts *working* time and decides when the buddy should speak up."""

    ORDER = ["break", "eye", "water", "stretch", "posture", "hunger", "meditate"]
    CONF = {
        "break":    ("break_on", "break_every", MINT, "bell"),
        "eye":      ("eye_on", "eye_every", SKY, "eye"),
        "water":    ("water_on", "water_every", SKY, "cup"),
        "stretch":  ("stretch_on", "stretch_every", PEACH, "body"),
        "posture":  ("posture_on", "posture_every", LAV, "body"),
        "hunger":   ("hunger_on", "hunger_every", PEACH, "food"),
        "meditate": ("meditate_on", "meditate_every", LAV, "leaf"),
    }

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.timers = {k: 0.0 for k in self.ORDER}
        self.custom_timers = {}          # custom reminder id -> active seconds
        self.work_seconds = 0.0          # active seconds since the last break
        self.session_seconds = 0.0       # active seconds since the app started
        self.idle_for = 0.0
        self.was_away = False
        self.app_title = ""
        self.app_seconds = 0.0
        self.app_warned = False
        self.batt_low_warned = False
        self.batt_full_warned = False
        self.night_warned_day = None
        self.breakfast_warned_day = None
        self.lunch_warned_day = None
        self.dinner_warned_day = None
        self.last_check = time.time()

    # -------------------------------------------------------------- helpers
    def reset(self, key):
        if key in self.timers:
            self.timers[key] = 0.0

    def reset_all(self):
        for k in self.timers:
            self.timers[k] = 0.0
        for k in self.custom_timers:
            self.custom_timers[k] = 0.0
        self.work_seconds = 0.0

    def customs(self):
        return [r for r in (self.cfg.get("custom_reminders") or []) if isinstance(r, dict)]

    def custom_left(self, rem):
        """Seconds until a custom reminder fires (None when it is off)."""
        if not rem.get("on", True):
            return None
        total = int(rem.get("every", 60)) * 60
        return max(0, total - self.custom_timers.get(rem.get("id"), 0.0))

    def snooze_custom(self, rid, minutes):
        for rem in self.customs():
            if rem.get("id") == rid:
                total = int(rem.get("every", 60)) * 60
                self.custom_timers[rid] = max(0.0, total - minutes * 60)

    def in_work_hours(self):
        try:
            h = datetime.now().hour
            a = int(self.cfg.get("work_start_hour", 9)) % 24
            b = int(self.cfg.get("work_end_hour", 18)) % 24
            if a == b:
                return True
            if a < b:
                return a <= h < b
            return h >= a or h < b
        except Exception:
            return True

    def overview(self):
        """Live state of every reminder for the app: on/off, interval,
        seconds until it fires, and today's count against the target."""
        names = {"break": "Break", "eye": "Eye rest", "water": "Water",
                 "stretch": "Stretch", "posture": "Posture", "hunger": "Snack",
                 "meditate": "Breathing"}
        counters = {"break": "breaks", "eye": "eye", "water": "water",
                    "stretch": "stretch", "posture": "posture", "hunger": "hunger",
                    "meditate": "breath"}
        targets = {"break": "break_target", "eye": "eye_target", "water": "water_target",
                   "stretch": "stretch_target", "posture": "posture_target"}
        out = []
        for key in self.ORDER:
            on_key, every_key, _a, _i = self.CONF[key]
            on = bool(self.cfg.get(on_key, True))
            total = self.cfg.get(every_key, 30) * 60
            spent = self.work_seconds if key == "break" else self.timers[key]
            out.append({
                "key": key, "name": names[key], "custom": False, "on": on,
                "every": int(self.cfg.get(every_key, 30)),
                "left": int(max(0, total - spent)) if on else None,
                "today": self.app.stats.today(counters[key]),
                "target": int(self.cfg.get(targets[key], 0)) if key in targets else None,
                "msg": self.cfg.get(key + "_msg", ""),
            })
        for rem in self.customs():
            rid = rem.get("id")
            left = self.custom_left(rem)
            out.append({
                "key": rid, "name": rem.get("name", "Reminder"), "custom": True,
                "on": bool(rem.get("on", True)), "every": int(rem.get("every", 60)),
                "left": int(left) if left is not None else None,
                "today": self.app.stats.today("custom_%s" % rid),
                "streak": self.app.stats.streak_for("custom_%s" % rid),
                "target": None, "msg": rem.get("msg", ""),
            })
        return out

    def snooze(self, key, minutes):
        """Ask again in exactly N minutes."""
        try:
            total = self.cfg.get(self.CONF[key][1], 30) * 60
            target = max(0.0, total - minutes * 60)
            if key == "break":
                self.work_seconds = target
            else:
                self.timers[key] = target
        except Exception:
            log_exc("Reminders.snooze")

    def next_due(self):
        """(label, seconds) for the reminder that will fire next."""
        best = None
        for key in self.ORDER:
            on_key, every_key, _a, _i = self.CONF[key]
            if not self.cfg.get(on_key, True):
                continue
            total = self.cfg.get(every_key, 30) * 60
            spent = self.work_seconds if key == "break" else self.timers[key]
            left = max(0, total - spent)
            if best is None or left < best[1]:
                best = (key, left)
        for rem in self.customs():
            left = self.custom_left(rem)
            if left is not None and (best is None or left < best[1]):
                best = (rem.get("name", "Reminder"), left)
        return best

    def in_quiet_hours(self):
        if not self.cfg.get("quiet_on", False):
            return False
        try:
            h = datetime.now().hour
            a = int(self.cfg.get("quiet_from", 22)) % 24
            b = int(self.cfg.get("quiet_to", 8)) % 24
            if a == b:
                return False
            if a < b:
                return a <= h < b
            return h >= a or h < b
        except Exception:
            return False

    def blocked(self):
        """Reasons not to interrupt right now."""
        if self.app.card is not None:
            return True
        if self.app.breath is not None:
            return True
        if self.app.focus is not None:       # focus / break session running
            return True
        if self.in_quiet_hours():
            return True
        if self.cfg.get("work_hours_only", False) and not self.in_work_hours():
            return True
        if self.cfg.get("skip_fullscreen", True) and WIN.foreground_is_fullscreen():
            return True
        if self.app.snooze_until and time.time() < self.app.snooze_until:
            return True
        return False

    # ----------------------------------------------------------------- tick
    def tick(self, dt):
        try:
            self.idle_for = WIN.idle_seconds() if IS_WIN else 0.0
            idle_limit = max(60, self.cfg.get("idle_pause", 5) * 60)
            active = self.idle_for < 60

            # came back from a real break?
            if self.idle_for >= idle_limit:
                if not self.was_away:
                    self.was_away = True
            elif self.was_away:
                self.was_away = False
                self._welcome_back()

            if active:
                self.work_seconds += dt
                self.session_seconds += dt
                for k in self.timers:
                    self.timers[k] += dt
                for rem in self.customs():
                    rid = rem.get("id")
                    self.custom_timers[rid] = self.custom_timers.get(rid, 0.0) + dt

            self._check_focus()
            if not self.blocked():
                self._check_reminders()
                self._check_system()
            else:
                self._check_battery_critical()
        except Exception:
            log_exc("Reminders.tick")

    def _welcome_back(self):
        try:
            mins = int(self.idle_for / 60)
            self.work_seconds = 0.0
            self.timers["posture"] = 0.0
            self.timers["eye"] = 0.0
            b = self.app.buddy
            if self.blocked():
                return
            b.anim.set("happy", 1.2, after="idle")
            b.say(random.choice([
                "welcome back! that was a good %d minute break" % max(1, mins),
                "hello again! feeling better?",
                "you came back! let's go",
            ]), 4.0)
            self.app.stats.bump("breaks")
        except Exception:
            log_exc("_welcome_back")

    # ------------------------------------------------------------ reminders
    def _check_reminders(self):
        for key in self.ORDER:
            on_key, every_key, accent, icon = self.CONF[key]
            if not self.cfg.get(on_key, True):
                continue
            total = self.cfg.get(every_key, 30) * 60
            spent = self.work_seconds if key == "break" else self.timers[key]
            if spent < total:
                continue
            self.reset(key)
            if key == "break":
                self.work_seconds = 0.0
            safe(self.fire, key, accent, icon)
            return          # one at a time
        for rem in self.customs():
            left = self.custom_left(rem)
            if left is None or left > 0:
                continue
            self.custom_timers[rem.get("id")] = 0.0
            safe(self.fire_custom, rem)
            return

    def fire_custom(self, rem):
        """A reminder the user defined in the app."""
        app = self.app
        rid = rem.get("id")
        name = rem.get("name", "Reminder")
        text = (rem.get("msg") or "").strip() or ("Time for: %s" % name)
        buttons = [("Done", lambda: app.custom_done(rid)),
                   ("10 more min", lambda: self.snooze_custom(rid, 10)),
                   ("Skip", None)]
        app.buddy.anim.set("wave", 2.0, after="idle")
        app.show_card(name, text, buttons, accent=LAV, icon="bell", seconds=40)

    def fire(self, key, accent=None, icon=None):
        app = self.app
        cfg = self.cfg
        accent = accent or ACCENTS.get(key, MINT)
        icon = icon or self.CONF.get(key, (None, None, None, "bell"))[3]
        is_ganesh = cfg.get("character") == "custom"
        title_extra = None

        if is_ganesh:
            # a little eye-blink to mark that something wants attention
            b = app.buddy
            b.anim.blink_t = 0.18
            b.anim.blink_in = random.uniform(2.5, 6.0)

        if key == "break":
            mins = cfg.get("break_every", 45)
            text = pick("break", mins=mins, len=cfg.get("break_len", 5))
            buttons = [("Take it now", app.start_break),
                       ("5 more min", lambda: app.snooze_key("break", 5)),
                       ("Skip", None)]
            app.buddy.anim.set("wave", 2.0, after="idle")
        elif key == "eye":
            text = pick("eye")
            buttons = [("Start 20s", app.start_eye_rest),
                       ("Done", lambda: app.praise("eye")),
                       ("Later", lambda: app.snooze_key("eye", 5))]
            app.buddy.anim.set("look", 2.2, after="idle")
        elif key == "water":
            text = pick("water")
            buttons = [("Drank it", lambda: app.praise("water")),
                       ("In a bit", lambda: app.snooze_key("water", 10))]
            if is_ganesh:
                text = "I'm feeling a bit dehydrated. Could I have some water?"
                app.buddy.anim.set("worried", 1.6, after="idle")
            else:
                app.buddy.fx.emit("drop", 0, 78, 6, color=SKY)
                app.buddy.anim.set("happy", 1.0, after="idle")
        elif key == "stretch":
            text = pick("stretch", idea=random.choice(STRETCH_IDEAS))
            buttons = [("Did it", lambda: app.praise("stretch")),
                       ("Another idea", lambda: app.reminders.fire("stretch")),
                       ("Later", lambda: app.snooze_key("stretch", 10))]
            app.buddy.anim.set("stretch", 2.2, after="idle")
        elif key == "posture":
            text = pick("posture")
            buttons = [("Fixed it", lambda: app.praise("posture")),
                       ("Later", lambda: app.snooze_key("posture", 10))]
            app.buddy.anim.set("stretch", 1.6, after="idle")
        elif key == "hunger":
            if is_ganesh:
                text = "A modak would be lovely right about now... would you get one for me?"
                title_extra = "Would you like a modak?"
                app.buddy.fx.emit("modak", 0, 76, 3, power=0.6, color="#FFE9B8")
            else:
                text = pick("hunger")
            buttons = [("Had a snack", lambda: app.praise("hunger")),
                       ("Later", lambda: app.snooze_key("hunger", 20))]
            app.buddy.anim.set("happy", 1.2, after="idle")
        elif key == "meditate":
            text = pick("meditate")
            buttons = [("Breathe now", app.start_breathing),
                       ("Not now", lambda: app.snooze_key("meditate", 20))]
            app.buddy.anim.set("meditate", 3.0, after="idle")
        else:
            text = "Time for a little pause."
            buttons = [("Okay", None)]

        titles = {"break": "Break time", "eye": "Rest & blink your eyes",
                  "water": "Drink a glass of water", "stretch": "Stretch",
                  "posture": "Posture check", "hunger": "Snack time",
                  "meditate": "Breathe"}
        custom_text = str(cfg.get(key + "_msg") or "").strip()
        if custom_text:
            text = custom_text          # the user's own words from the app
        app.show_card(title_extra or titles.get(key, "Reminder"), text, buttons,
                      accent=accent, icon=icon, seconds=40)

    def _check_battery_critical(self):
        """A dying battery is worth interrupting even a focus session for."""
        try:
            if not self.cfg.get("battery_on", True):
                return
            if self.app.card is not None or self.app.breath is not None:
                return
            if time.time() - self.last_check < 20:
                return
            self.last_check = time.time()
            pct, plugged = WIN.battery()
            if pct is None or plugged is not False:
                return
            if pct > 10 or self.batt_low_warned:
                return
            self.batt_low_warned = True
            urgent = "run" if self.cfg.get("character") == "custom" else "worried"
            self.app.buddy.anim.set(urgent, 3.0, after="idle")
            self.app.show_card("Battery almost empty",
                               pick("battery_low", pct=pct),
                               [("Okay", None)], accent=SUN, icon="bolt", seconds=30)
            if self.cfg.get("sounds"):
                play_chime("alert")
        except Exception:
            log_exc("_check_battery_critical")

    # --------------------------------------------------------------- system
    def _check_system(self):
        cfg = self.cfg
        app = self.app
        now = time.time()
        if now - self.last_check < 20:
            return
        self.last_check = now

        # battery ---------------------------------------------------------
        if cfg.get("battery_on", True):
            pct, plugged = WIN.battery()
            if pct is not None:
                low = cfg.get("battery_low", 20)
                if plugged is False and pct <= low and not self.batt_low_warned:
                    self.batt_low_warned = True
                    urgent = "run" if cfg.get("character") == "custom" else "worried"
                    app.buddy.anim.set(urgent, 3.0, after="idle")
                    app.show_card("Low battery", pick("battery_low", pct=pct),
                                  [("Okay", None)], accent=SUN, icon="bolt", seconds=30)
                    if cfg.get("sounds"):
                        play_chime("alert")
                if plugged:
                    self.batt_low_warned = False
                    if pct >= 99 and not self.batt_full_warned:
                        self.batt_full_warned = True
                        app.buddy.say(pick("battery_full", pct=pct), 5.0)
                if pct < 95:
                    self.batt_full_warned = False

        # late night ------------------------------------------------------
        if cfg.get("night_on", True):
            h = datetime.now().hour
            today = datetime.now().strftime("%Y-%m-%d")
            if h >= int(cfg.get("night_hour", 23)) and self.night_warned_day != today:
                self.night_warned_day = today
                app.buddy.anim.mood = "sleepy"
                app.show_card("Getting late",
                              pick("night", time=datetime.now().strftime("%H:%M")),
                              [("Wrapping up", None),
                               ("Breathe first", app.start_breathing)],
                              accent=LAV, icon="moon", seconds=40)

        # meal times, if set up during onboarding --------------------------
        today = datetime.now().strftime("%Y-%m-%d")
        h = datetime.now().hour
        for key, on_key, hour_key, tracker, title, icon in (
            ("breakfast", "breakfast_on", "breakfast_hour", "breakfast_warned_day",
             "Breakfast time", "food"),
            ("lunch", "lunch_on", "lunch_hour", "lunch_warned_day", "Lunch time", "food"),
            ("dinner", "dinner_on", "dinner_hour", "dinner_warned_day", "Dinner time", "food"),
        ):
            if cfg.get(on_key, True) and h == int(cfg.get(hour_key, 12)) \
                    and getattr(self, tracker) != today:
                setattr(self, tracker, today)
                app.show_card(title, pick(key),
                              [("Eating now", lambda k=key: app.praise(k)),
                               ("In a bit", lambda k=key: app.snooze_key(k, 20))],
                              accent=PEACH, icon=icon, seconds=40)
                if cfg.get("sounds"):
                    play_chime("up")

        # stuck in one app ------------------------------------------------
        if cfg.get("same_app_on", True) and IS_WIN:
            title = WIN.active_window_title()
            name = title.split(" - ")[-1].strip() if title else ""
            if not name or len(name) > 40:
                name = (title[:36] + "...") if len(title) > 39 else title
            if name and name == self.app_title:
                self.app_seconds += 20
            else:
                self.app_title = name
                self.app_seconds = 0.0
                self.app_warned = False
            limit = cfg.get("same_app_mins", 90) * 60
            if name and not self.app_warned and self.app_seconds >= limit:
                self.app_warned = True
                app.show_card("Long stretch",
                              pick("same_app", app=name,
                                   mins=int(self.app_seconds / 60)),
                              [("Take a break", app.start_break),
                               ("I'm in the zone", None)],
                              accent=PEACH, icon="clock", seconds=35)

    # ----------------------------------------------------------- focus mode
    def _check_focus(self):
        f = self.app.focus
        if not f:
            return
        if time.time() < f["end"]:
            return
        safe(self.app.focus_finished)


# --------------------------------------------------------------------------
#  Start-with-Windows helpers
# --------------------------------------------------------------------------
def _startup_dir():
    try:
        return os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                            "Start Menu", "Programs", "Startup")
    except Exception:
        return ""


def _script_path():
    try:
        if getattr(sys, "frozen", False):
            return os.path.abspath(sys.executable)
        return os.path.abspath(__file__)
    except Exception:
        return os.path.abspath(sys.argv[0])


def _pythonw():
    try:
        if getattr(sys, "frozen", False):
            return os.path.abspath(sys.executable)
        base = os.path.dirname(sys.executable)
        cand = os.path.join(base, "pythonw.exe")
        return cand if os.path.exists(cand) else sys.executable
    except Exception:
        return sys.executable


def _autostart_paths():
    d = _startup_dir()
    if not d:
        return ("", "")
    return (os.path.join(d, APP_NAME + ".lnk"), os.path.join(d, APP_NAME + ".bat"))


def autostart_enabled():
    lnk, bat = _autostart_paths()
    try:
        return bool(lnk and (os.path.exists(lnk) or os.path.exists(bat)))
    except Exception:
        return False


def set_autostart(enable):
    """Create/remove a Startup entry.  Returns True when the state matches."""
    if not IS_WIN:
        return False
    lnk, bat = _autostart_paths()
    if not lnk:
        return False
    try:
        if not enable:
            for p in (lnk, bat):
                if os.path.exists(p):
                    os.remove(p)
            return True

        exe = _pythonw()
        script = _script_path()
        frozen = getattr(sys, "frozen", False)
        target = exe
        args = "" if frozen else '"%s"' % script
        workdir = os.path.dirname(script)

        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
            "$s.TargetPath='{t}';$s.Arguments='{a}';$s.WorkingDirectory='{w}';"
            "$s.WindowStyle=7;$s.Description='{n} desktop buddy';$s.Save()"
        ).format(lnk=lnk.replace("'", "''"), t=target.replace("'", "''"),
                 a=args.replace("'", "''"), w=workdir.replace("'", "''"), n=APP_NAME)
        flags = 0x08000000  # CREATE_NO_WINDOW
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-ExecutionPolicy", "Bypass", "-Command", ps],
                           creationflags=flags, timeout=25,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            log_exc("set_autostart.powershell")

        if os.path.exists(lnk):
            return True

        # fallback: a tiny batch file that launches without a console window
        with open(bat, "w", encoding="utf-8") as fh:
            fh.write('@echo off\r\nstart "" "%s" %s\r\n' % (target, args))
        return os.path.exists(bat)
    except Exception:
        log_exc("set_autostart")
        return False


def open_folder(path):
    try:
        if IS_WIN:
            os.startfile(path)                      # noqa: S606
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        log_exc("open_folder")


# --------------------------------------------------------------------------
#  Onboarding - a short first-run questionnaire about the person's actual
#  daily routine, so reminders line up with real life instead of guessing.
# --------------------------------------------------------------------------
class OnboardingWindow:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.vars = {}
        self.win = tk.Toplevel(app.root)
        self.win.title("Welcome to %s" % APP_NAME)
        self.win.resizable(False, False)
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        self.win.configure(bg=CREAM)
        self.win.protocol("WM_DELETE_WINDOW", self.finish)
        safe(self._build)
        safe(self._center)

    def _center(self):
        try:
            self.win.update_idletasks()
            w, h = self.win.winfo_width(), self.win.winfo_height()
            sx, sy, sw, sh = self.app.buddy._screen_rect()
            self.win.geometry("+%d+%d" % (sx + (sw - w) // 2, sy + (sh - h) // 3))
            self.win.lift()
            self.win.focus_force()
        except Exception:
            log_exc("onboarding._center")

    def _hour_row(self, parent, label, key, default):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=24, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(key, default)))
        self.vars[key] = var
        ttk.Spinbox(row, from_=0, to=23, textvariable=var, width=4,
                    justify="center").pack(side="left")
        ttk.Label(row, text=":00", style="Hint.TLabel").pack(side="left", padx=(2, 0))
        return var

    def _build(self):
        try:
            st = ttk.Style(self.win)
            try:
                st.theme_use("clam")
            except Exception:
                pass
            st.configure(".", background=CREAM, foreground=INK, font=sfont(10))
            st.configure("TFrame", background=CREAM)
            st.configure("TLabel", background=CREAM, foreground=INK)
            st.configure("Hint.TLabel", foreground=INK_SOFT, font=sfont(9))
            st.configure("Head.TLabel", font=sfont(12, True))
            st.configure("TCheckbutton", background=CREAM)
            st.configure("TButton", padding=(int(10 * UI_K), int(6 * UI_K)), font=sfont(10, True))
        except Exception:
            log_exc("onboarding._style")

        f = ttk.Frame(self.win, padding=18)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Hi! Let's set me up around your day",
                  style="Head.TLabel").pack(anchor="w")
        ttk.Label(f,
                  text="A few quick questions so my reminders actually fit your "
                       "routine instead of guessing. You can change any of this "
                       "later in Settings.",
                  style="Hint.TLabel", wraplength=400, justify="left"
                  ).pack(anchor="w", pady=(2, 14))

        ttk.Label(f, text="Your day", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        self._hour_row(f, "Start work / wake up around", "work_start_hour", 9)
        self._hour_row(f, "Breakfast around", "breakfast_hour", 8)
        self._hour_row(f, "Lunch around", "lunch_hour", 13)
        self._hour_row(f, "Dinner around", "dinner_hour", 20)
        self._hour_row(f, "Finish work around", "work_end_hour", 18)

        ttk.Label(f, text="What should I remind you about?",
                  style="Head.TLabel").pack(anchor="w", pady=(14, 4))
        self.water_var = tk.BooleanVar(value=self.cfg.get("water_on", True))
        ttk.Checkbutton(f, text="Drink water", variable=self.water_var).pack(anchor="w")
        self.eye_var = tk.BooleanVar(value=self.cfg.get("eye_on", True))
        ttk.Checkbutton(f, text="Rest my eyes (20-20-20 rule)",
                        variable=self.eye_var).pack(anchor="w")
        self.meal_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Remind me about breakfast / lunch / dinner",
                        variable=self.meal_var).pack(anchor="w")

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(18, 0))
        ttk.Button(bar, text="Skip for now", command=self.skip).pack(side="left")
        ttk.Button(bar, text="Let's go!", command=self.finish).pack(side="right")

    def skip(self):
        self._finish_common()

    def finish(self):
        try:
            for key in ("work_start_hour", "breakfast_hour", "lunch_hour",
                        "dinner_hour", "work_end_hour"):
                try:
                    self.cfg[key] = int(clamp(int(float(self.vars[key].get())), 0, 23))
                except Exception:
                    pass
            self.cfg["water_on"] = bool(self.water_var.get())
            self.cfg["eye_on"] = bool(self.eye_var.get())
            meals_on = bool(self.meal_var.get())
            self.cfg["breakfast_on"] = meals_on
            self.cfg["lunch_on"] = meals_on
            self.cfg["dinner_on"] = meals_on
            # stay quiet outside work hours instead of nagging off the clock
            ws = int(self.cfg.get("work_start_hour", 9))
            we = int(self.cfg.get("work_end_hour", 18))
            if we != ws:
                self.cfg["quiet_on"] = True
                self.cfg["quiet_from"] = we
                self.cfg["quiet_to"] = ws
        except Exception:
            log_exc("onboarding.finish")
        self._finish_common()

    def _finish_common(self):
        try:
            self.cfg["onboarded"] = True
            self.cfg.save()
        except Exception:
            log_exc("onboarding.save")
        try:
            self.win.destroy()
        except Exception:
            pass
        try:
            self.app.buddy.anim.set("wave", 2.6, after="idle")
            self.app.buddy.say("all set - I'll fit around your day from now on!", 4.0)
            if self.cfg.get("sounds"):
                play_chime("up")
        except Exception:
            log_exc("onboarding.greet")


# --------------------------------------------------------------------------
#  Settings window
# --------------------------------------------------------------------------
class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.vars = {}
        self.win = tk.Toplevel(app.root)
        self.win.title(APP_NAME + " settings")
        self.win.resizable(False, False)
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        self.win.configure(bg=CREAM)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        safe(self._build)
        safe(self._center)

    # ---------------------------------------------------------------- build
    def _center(self):
        try:
            self.win.update_idletasks()
            w, h = self.win.winfo_width(), self.win.winfo_height()
            sx, sy, sw, sh = self.app.buddy._screen_rect()
            self.win.geometry("+%d+%d" % (sx + (sw - w) // 2, sy + (sh - h) // 3))
            self.win.lift()
            self.win.focus_force()
        except Exception:
            log_exc("settings._center")

    def _style(self):
        try:
            st = ttk.Style(self.win)
            try:
                st.theme_use("clam")
            except Exception:
                pass
            st.configure(".", background=CREAM, foreground=INK, font=sfont(10))
            st.configure("TNotebook", background=CREAM, borderwidth=0)
            st.configure("TNotebook.Tab", padding=(int(14 * UI_K), int(7 * UI_K)), font=sfont(10, True),
                         background="#EFE6DA", foreground=INK)
            st.map("TNotebook.Tab",
                   background=[("selected", MINT)],
                   foreground=[("selected", "#20343A")])
            st.configure("TFrame", background=CREAM)
            st.configure("TLabel", background=CREAM, foreground=INK)
            st.configure("Hint.TLabel", foreground=INK_SOFT, font=sfont(9))
            st.configure("Head.TLabel", font=sfont(11, True))
            st.configure("TCheckbutton", background=CREAM)
            st.configure("TRadiobutton", background=CREAM)
            st.configure("TButton", padding=(int(10 * UI_K), int(5 * UI_K)), font=sfont(10, True))
            st.configure("TSpinbox", arrowsize=13)
        except Exception:
            log_exc("settings._style")

    def _build(self):
        self._style()
        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self.tab_buddy = ttk.Frame(nb, padding=12)
        self.tab_emotes = ttk.Frame(nb, padding=12)
        self.tab_rem = ttk.Frame(nb, padding=12)
        self.tab_focus = ttk.Frame(nb, padding=12)
        self.tab_sys = ttk.Frame(nb, padding=12)
        self.tab_about = ttk.Frame(nb, padding=12)
        nb.add(self.tab_buddy, text="Buddy")
        nb.add(self.tab_emotes, text="Emotes")
        nb.add(self.tab_rem, text="Reminders")
        nb.add(self.tab_focus, text="Focus")
        nb.add(self.tab_sys, text="System")
        nb.add(self.tab_about, text="About")

        self._build_buddy(self.tab_buddy)
        self._build_emotes(self.tab_emotes)
        self._build_reminders(self.tab_rem)
        self._build_focus(self.tab_focus)
        self._build_system(self.tab_sys)
        self._build_about(self.tab_about)

        bar = ttk.Frame(self.win, padding=(10, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        ttk.Button(bar, text="Reset reminder timers",
                   command=self._reset_timers).pack(side="right", padx=6)

    # ------------------------------------------------------------- widgets
    def _toggle(self, parent, label, key, hint=None, cmd=None):
        var = tk.BooleanVar(value=bool(self.cfg.get(key, True)))
        self.vars[key] = var

        def on():
            self.cfg[key] = bool(var.get())
            self.cfg.save()
            if cmd:
                safe(cmd)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Checkbutton(row, text=label, variable=var, command=on).pack(side="left")
        if hint:
            ttk.Label(row, text=hint, style="Hint.TLabel").pack(side="left", padx=(8, 0))
        return var

    def _number(self, parent, label, key, lo, hi, suffix="min", width=5, cmd=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(key, lo)))
        self.vars[key] = var

        def on(*_a):
            try:
                v = int(float(var.get()))
            except Exception:
                return
            v = int(clamp(v, lo, hi))
            self.cfg[key] = v
            self.cfg.save()
            if cmd:
                safe(cmd)
        sp = ttk.Spinbox(row, from_=lo, to=hi, textvariable=var, width=width,
                         command=on, justify="center")
        sp.pack(side="left", padx=6)
        sp.bind("<FocusOut>", on)
        sp.bind("<Return>", on)
        var.trace_add("write", on)
        if suffix:
            ttk.Label(row, text=suffix, style="Hint.TLabel").pack(side="left")
        return var

    def _section(self, parent, title):
        ttk.Label(parent, text=title, style="Head.TLabel").pack(anchor="w", pady=(10, 2))
        sep = ttk.Separator(parent, orient="horizontal")
        sep.pack(fill="x", pady=(0, 6))

    # ----------------------------------------------------------- tab: buddy
    def _build_buddy(self, f):
        self._section(f, "Who is your buddy?")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        cvar = tk.StringVar(value=self.cfg.get("character", "dog"))
        self.vars["character"] = cvar

        def pick_char():
            self.cfg["character"] = cvar.get()
            self.cfg.save()
            self.app.buddy.anim.set("happy", 1.2, after="idle")
            self.app.buddy.say("hello! new look", 2.4)
        for val, text in (("dog", "Puppy"), ("cat", "Kitty"), ("human", "Buddy")):
            ttk.Radiobutton(row, text=text, value=val, variable=cvar,
                            command=pick_char).pack(side="left", padx=(0, 14))

        row1b = ttk.Frame(f)
        row1b.pack(fill="x", pady=(2, 2))
        ttk.Radiobutton(row1b, text="Ganesh", value="custom", variable=cvar,
                        command=pick_char).pack(side="left", padx=(0, 10))
        ttk.Button(row1b, text="Choose everyday photo...",
                   command=lambda: (self.app.choose_custom_photo("idle"),
                                     cvar.set(self.cfg.get("character", "dog")))
                   ).pack(side="left", padx=(0, 6))
        ttk.Button(row1b, text="Choose 'urgent' photo...",
                   command=lambda: self.app.choose_custom_photo("urgent")
                   ).pack(side="left")

        row1c = ttk.Frame(f)
        row1c.pack(fill="x", pady=(2, 2))
        ttk.Button(row1c, text="Choose 'happy' photo...",
                   command=lambda: self.app.choose_custom_photo("happy")
                   ).pack(side="left", padx=(0, 6))
        ttk.Button(row1c, text="Choose 'wave' photo...",
                   command=lambda: self.app.choose_custom_photo("wave")
                   ).pack(side="left", padx=(0, 6))
        ttk.Button(row1c, text="Fix background on my photos",
                   command=self.app.redo_background_removal).pack(side="left")

        row1d = ttk.Frame(f)
        row1d.pack(fill="x", pady=(0, 2))
        ttk.Label(row1d,
                  text="Every photo you choose above has its background removed "
                       "automatically (no installs needed). PNG works best. Every "
                       "extra photo is optional - each one only replaces the everyday "
                       "photo for its own moment (urgent = low battery / Claude Code "
                       "needing you, happy = praise or celebrating, wave = greetings). "
                       "A walk1.png dropped straight into DeskPal's data folder (About -> "
                       "Open that folder) will also show while wandering - always that "
                       "one photo, one fixed direction. Skip any of them and the everyday "
                       "photo is used "
                       "instead - nothing ever breaks.",
                  style="Hint.TLabel", justify="left", wraplength=420).pack(anchor="w")

        row2 = ttk.Frame(f)
        row2.pack(fill="x", pady=(6, 2))
        ttk.Label(row2, text="Name").pack(side="left")
        nvar = tk.StringVar(value=self.cfg.get("pet_name", "Mochi"))
        self.vars["pet_name"] = nvar

        def on_name(*_a):
            self.cfg["pet_name"] = nvar.get()[:18] or "Mochi"
            self.cfg.save()
        e = ttk.Entry(row2, textvariable=nvar, width=18)
        e.pack(side="left", padx=6)
        nvar.trace_add("write", on_name)

        self._section(f, "Look and feel")
        row3 = ttk.Frame(f)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="Size").pack(side="left")
        svar = tk.DoubleVar(value=float(self.cfg.get("scale", 1.0)))
        self.vars["scale"] = svar
        lbl = ttk.Label(row3, text="%d%%" % int(svar.get() * 100), style="Hint.TLabel")

        def on_scale(_v=None):
            val = round(float(svar.get()), 2)
            self.cfg["scale"] = val
            lbl.config(text="%d%%" % int(val * 100))
            self.cfg.save()
            self.app.buddy.rebuild_scale()
        ttk.Scale(row3, from_=0.6, to=1.8, variable=svar, command=on_scale,
                  length=180).pack(side="left", padx=8)
        lbl.pack(side="left")

        self._number(f, "Animation smoothness", "fps", 12, 60, "frames per second",
                     cmd=self.app.buddy.rebuild_scale)
        self._toggle(f, "Speech bubbles", "speech")
        self._toggle(f, "Gentle sounds", "sounds")
        self._toggle(f, "Wander around the screen", "wander")
        self._number(f, "Wander every", "wander_every", 1, 60)
        self._toggle(f, "Always stay on top of other windows", "always_on_top")

        self._section(f, "Startup")
        av = tk.BooleanVar(value=autostart_enabled())
        self.vars["autostart"] = av

        def on_auto():
            ok = set_autostart(bool(av.get()))
            self.cfg["autostart"] = bool(av.get())
            self.cfg.save()
            if not ok and av.get():
                av.set(False)
                messagebox.showinfo(
                    APP_NAME,
                    "Could not add the Startup shortcut automatically.\n\n"
                    "You can do it by hand: press Win+R, type  shell:startup  and "
                    "drop a shortcut to Start-Buddy.bat into that folder.",
                    parent=self.win)
        ttk.Checkbutton(f, text="Start automatically when Windows starts",
                        variable=av, command=on_auto).pack(anchor="w", pady=2)

    # -------------------------------------------------------- tab: reminders
    def _play_ganesh_emote(self, state, duration, label):
        """Play one bundled Ganesh emote from Settings for easy testing."""
        try:
            self.app.stop_ganesh_emotes()
            if state == "mouse_play":
                self.app.start_modak_scene()
                return
            self.cfg["character"] = "custom"
            self.cfg.save()
            if "character" in self.vars:
                self.vars["character"].set("custom")
            self.app.buddy.anim.set(state, duration, after="idle")
            # Keep the test stage clean: the button label already identifies
            # the emote, so a speech bubble would cover the sprite preview.
        except Exception:
            log_exc("settings.play_ganesh_emote")

    def _build_emotes(self, f):
        self._section(f, "Ganesh emotes")
        ttk.Label(
            f,
            text="Vinayaka, Rat & Modak plays on your desktop. After the rat finds "
                 "the sweet, click Take Modak from Rat to start a two-minute chase. "
                 "Stop scene or drag Ganesh to end it.",
            style="Hint.TLabel", justify="left", wraplength=430
        ).pack(anchor="w", pady=(0, 8))

        grid = ttk.Frame(f)
        grid.pack(fill="x")
        emotes = (
            ("Standing idle", "idle", 2.0, "standing idle"),
            ("Walking", "walk", 3.0, "walking"),
            ("Running", "run_cycle", 2.4, "running"),
            ("Waving", "wave", 2.4, "waving"),
            ("Breathing", "breathe_cycle", 3.0, "breathing"),
            ("Meditation peek", "meditation_peek", 2.4, "meditation peek"),
            ("Modak jump & catch", "eat_laddu", 5.0, "modak jump and catch"),
            ("Window-edge peek", "window_peek", 2.4, "window edge peek"),
            ("Thirsty slump", "water_slump", 2.4, "thirsty slump"),
            ("Drink water", "drink_water", 3.0, "drinking water"),
            ("Blessing", "bless_cycle", 2.6, "blessing"),
            ("Study", "study_cycle", 3.2, "studying"),
            ("Vinayaka, Rat & Modak", "mouse_play", 3.2, "Vinayaka, Rat and Modak"),
            ("Ride mouse", "mouse_ride", 3.2, "riding mouse"),
            ("Happy jump", "happy_jump", 1.3, "happy jump"),
            ("Celebrate", "celebrate", 3.0, "celebrating"),
            ("Stop", "idle", 0.1, "stopped"),
        )
        for index, (text, state, duration, label) in enumerate(emotes):
            button = ttk.Button(
                grid, text=text, width=20,
                command=lambda s=state, d=duration, l=label:
                self._play_ganesh_emote(s, d, l)
            )
            button.grid(row=index // 2, column=index % 2,
                        padx=(0 if index % 2 == 0 else 8, 8), pady=4,
                        sticky="ew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        controls = ttk.Frame(f)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Play all animations", command=self.app.play_all_ganesh_emotes).pack(side="left")
        ttk.Button(controls, text="Stop", command=self.app.stop_ganesh_emotes).pack(side="right")

        self._section(f, "Animation order")
        ttk.Label(
            f,
            text="New emotes: breathing, meditation peek, modak jump, window peek, "
                 "water, blessing, study, mouse play, mouse ride, and happy jump.\n"
                 "Optional production frames use custom_breathe1.png through "
                 "custom_happy_jump4.png in DeskPal's data folder.",
            style="Hint.TLabel", justify="left", wraplength=430
        ).pack(anchor="w", pady=(0, 5))
        ttk.Label(
            f,
            text="Walking: 4-step walk cycle  •  Running: 4-step run cycle\n"
                 "Hungry: tummy ache → looking for food  •  Laddu: hold → bite → savor → satisfied",
            style="Hint.TLabel", justify="left", wraplength=430
        ).pack(anchor="w")

    # -------------------------------------------------------- tab: reminders
    def _build_reminders(self, f):
        self._section(f, "Take a break")
        self._toggle(f, "Remind me to take a break", "break_on")
        self._number(f, "After", "break_every", 5, 240, "minutes of active work")
        self._number(f, "Break length", "break_len", 1, 60)

        self._section(f, "Little things")
        self._toggle(f, "Blink & eye rest (20-20-20 rule)", "eye_on")
        self._number(f, "Every", "eye_every", 5, 180)
        self._toggle(f, "Drink a glass of water", "water_on")
        self._number(f, "Every", "water_every", 10, 360)
        self._toggle(f, "Stretch", "stretch_on")
        self._number(f, "Every", "stretch_every", 10, 360)
        self._toggle(f, "Posture check", "posture_on")
        self._number(f, "Every", "posture_every", 5, 240)
        self._toggle(f, "Snack / food reminder", "hunger_on")
        self._number(f, "Every", "hunger_every", 30, 480)

        self._section(f, "Breathing and meditation")
        self._toggle(f, "Offer a breathing session", "meditate_on")
        self._number(f, "Every", "meditate_every", 15, 720)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Pattern").pack(side="left")
        pvar = tk.StringVar(value=BREATH_LABEL.get(self.cfg.get("breath_pattern", "box")))
        self.vars["breath_pattern"] = pvar
        cb = ttk.Combobox(row, textvariable=pvar, state="readonly", width=24,
                          values=[BREATH_LABEL[k] for k in ("box", "478", "calm")])
        cb.pack(side="left", padx=6)

        def on_pat(_e=None):
            for k, v in BREATH_LABEL.items():
                if v == pvar.get():
                    self.cfg["breath_pattern"] = k
                    self.cfg.save()
                    break
        cb.bind("<<ComboboxSelected>>", on_pat)
        self._number(f, "Cycles", "breath_cycles", 2, 30, "rounds")
        self._toggle(f, "Dim the screen while breathing", "dim_on_breathe")
        ttk.Button(f, text="Try a breathing session now",
                   command=lambda: (self.close(), self.app.start_breathing())
                   ).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------ tab: focus
    def _build_focus(self, f):
        self._section(f, "Focus sessions (Pomodoro technique)")
        ttk.Label(f, text="Work in short, timed sprints with a real break in between -\n"
                          "the classic Pomodoro method. A session hides the small\n"
                          "reminders, keeps a timer next to your buddy, and celebrates\n"
                          "when you finish. 25 min work / 5 min break is the traditional\n"
                          "Pomodoro split, and it is the default below.",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=(0, 8))
        self._number(f, "Focus length", "focus_len", 5, 120)
        self._number(f, "Break after focus", "focus_break", 1, 60)
        ttk.Button(f, text="Start a Pomodoro session now",
                   command=lambda: (self.close(), self.app.start_focus())
                   ).pack(anchor="w", pady=(10, 0))

        self._section(f, "Quiet hours")
        self._toggle(f, "Stay completely quiet during these hours", "quiet_on")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="From").pack(side="left")
        qf = tk.StringVar(value=str(self.cfg.get("quiet_from", 22)))
        qt = tk.StringVar(value=str(self.cfg.get("quiet_to", 8)))

        def on_q(*_a):
            try:
                self.cfg["quiet_from"] = int(clamp(int(qf.get()), 0, 23))
                self.cfg["quiet_to"] = int(clamp(int(qt.get()), 0, 23))
                self.cfg.save()
            except Exception:
                pass
        s1 = ttk.Spinbox(row, from_=0, to=23, textvariable=qf, width=4, command=on_q,
                         justify="center")
        s1.pack(side="left", padx=6)
        ttk.Label(row, text="to").pack(side="left")
        s2 = ttk.Spinbox(row, from_=0, to=23, textvariable=qt, width=4, command=on_q,
                         justify="center")
        s2.pack(side="left", padx=6)
        ttk.Label(row, text="o'clock", style="Hint.TLabel").pack(side="left")
        qf.trace_add("write", on_q)
        qt.trace_add("write", on_q)

    # ----------------------------------------------------------- tab: system
    def _build_system(self, f):
        self._section(f, "Watch my laptop")
        self._toggle(f, "Warn me about low battery", "battery_on")
        self._number(f, "Warn below", "battery_low", 5, 50, "%")
        self._toggle(f, "Nudge me when it gets late", "night_on")
        self._number(f, "After", "night_hour", 18, 23, "o'clock")
        self._toggle(f, "Notice when I stay in one app too long", "same_app_on")
        self._number(f, "After", "same_app_mins", 15, 300)

        self._section(f, "Your routine")
        ttk.Label(f, text="Set during onboarding - change anytime.",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 4))
        self._number(f, "Start work / wake up around", "work_start_hour", 0, 23, "o'clock")
        self._toggle(f, "Remind me about breakfast", "breakfast_on")
        self._number(f, "Around", "breakfast_hour", 0, 23, "o'clock")
        self._toggle(f, "Remind me about lunch", "lunch_on")
        self._number(f, "Around", "lunch_hour", 0, 23, "o'clock")
        self._toggle(f, "Remind me about dinner", "dinner_on")
        self._number(f, "Around", "dinner_hour", 0, 23, "o'clock")
        self._number(f, "Finish work around", "work_end_hour", 0, 23, "o'clock")

        self._section(f, "Being polite")
        self._toggle(f, "Say hello when I come back", "greet_on")
        self._toggle(f, "Stay quiet during full-screen apps and games",
                     "skip_fullscreen")
        self._number(f, "Pause reminders after", "idle_pause", 1, 60,
                     "minutes away from the keyboard")
        ttk.Label(f, text="Break reminders count only the time you are actually\n"
                          "using the laptop, so stepping away already counts.",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------ tab: about
    def _build_about(self, f):
        ttk.Label(f, text="%s %s" % (APP_NAME, APP_VERSION),
                  style="Head.TLabel").pack(anchor="w")
        self._section(f, "Start DeskPal")
        ttk.Label(f, text="Double-click Start-DeskPal.bat in the DeskPal folder.\n"
                          "When the buddy appears, choose Ganesh in the Buddy tab,\n"
                          "then use the Emotes tab to test every animation.",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Button(f, text="Play Ganesh welcome",
                   command=lambda: self._play_ganesh_emote("idle", 2.0, "Ganesh is ready")
                   ).pack(anchor="w", pady=(0, 10))
        ttk.Label(f, text="A small companion that keeps you company and reminds\n"
                          "you to look after yourself while you work.",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=(2, 10))
        ttk.Label(f, text="Left click: pet    Double click: settings\n"
                          "Right click: menu    Drag: move it anywhere",
                  justify="left").pack(anchor="w", pady=(0, 10))
        ttk.Label(f, text="Your settings live in:", style="Hint.TLabel").pack(anchor="w")
        ttk.Label(f, text=DATA_DIR, style="Hint.TLabel",
                  wraplength=360, justify="left").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=4)
        ttk.Button(row, text="Open that folder",
                   command=lambda: open_folder(DATA_DIR)).pack(side="left")
        ttk.Button(row, text="Reset everything",
                   command=self._reset_all).pack(side="left", padx=6)

    # ---------------------------------------------------------------- misc
    def _reset_timers(self):
        try:
            self.app.reminders.reset_all()
            self.app.buddy.say("timers reset!", 2.4)
        except Exception:
            log_exc("_reset_timers")

    def _reset_all(self):
        if not messagebox.askyesno(APP_NAME,
                                   "Reset every setting back to the defaults?",
                                   parent=self.win):
            return
        try:
            for k, v in DEFAULTS.items():
                self.cfg[k] = v
            self.cfg["first_run"] = False
            self.cfg.save()
            self.app.buddy.rebuild_scale()
            self.close()
            self.app.open_settings_classic()
        except Exception:
            log_exc("_reset_all")

    def close(self):
        try:
            self.cfg.clamp()
            self.cfg.save()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        try:
            if self.app.settings_win is self:
                self.app.settings_win = None
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Stats window
# --------------------------------------------------------------------------
class StatsWindow:
    W = 580
    H = 344

    def __init__(self, app):
        self.app = app
        self.k = UI_K
        self.w = int(self.W * self.k)
        self.h = int(self.H * self.k)
        self.win = tk.Toplevel(app.root)
        self.win.title(APP_NAME + " - how you are doing")
        self.win.resizable(False, False)
        self.win.configure(bg=CREAM)
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        self.cv = tk.Canvas(self.win, width=self.w, height=self.h, bg=CREAM,
                            highlightthickness=0)
        self.cv.pack()
        safe(self._draw)
        try:
            self.win.update_idletasks()
            sx, sy, sw, sh = app.buddy._screen_rect()
            self.win.geometry("+%d+%d" % (sx + (sw - self.w) // 2,
                                          sy + (sh - self.h) // 3))
            self.win.lift()
        except Exception:
            pass

    def _draw(self):
        c = self.cv
        st = self.app.stats
        k = self.k
        c.delete("all")
        c.create_text(24 * k, 26 * k, text="Your week", anchor="w", fill=INK,
                      font=sfont(15, True))

        streak = st.streak()
        c.create_text(24 * k, 54 * k, anchor="w", fill=INK_SOFT, font=sfont(10),
                      width=540 * k,
                      text="%d day streak of taking breaks. All time: %d breaks, "
                           "%d glasses of water, %d focus sessions."
                           % (streak, st.total("breaks"), st.total("water"),
                              st.total("focus")))

        days = st.last_days(7)
        keys = [("breaks", MINT, "breaks"), ("water", SKY, "water"),
                ("focus", PINK, "focus")]
        top, bottom = 96 * k, 256 * k
        left, right = 44 * k, 540 * k
        colw = (right - left) / 7.0
        peak = 1
        for _label, rec in days:
            for key, _col, _name in keys:
                peak = max(peak, rec.get(key, 0))

        for i in range(4):
            y = bottom - (bottom - top) * i / 3.0
            c.create_line(left, y, right, y, fill="#E7DED2")
            c.create_text(left - 8 * k, y, text=str(int(round(peak * i / 3.0))),
                          anchor="e", fill=INK_SOFT, font=sfont(8))

        bw = colw / (len(keys) + 1.4)
        for di, (label, rec) in enumerate(days):
            x0 = left + di * colw
            for ki, (key, col, _name) in enumerate(keys):
                v = rec.get(key, 0)
                h = (bottom - top) * (v / float(peak)) if peak else 0
                bx = x0 + bw * (ki + 0.5) + colw * 0.08
                px_round_rect(c, bx, bottom - h, bx + bw * 0.9, bottom,
                              min(5 * k, bw * 0.4), fill=col, outline="")
                if v:
                    c.create_text(bx + bw * 0.45, bottom - h - 9 * k, text=str(v),
                                  fill=INK_SOFT, font=sfont(8, True))
            c.create_text(x0 + colw / 2.0, bottom + 15 * k, text=label, fill=INK,
                          font=sfont(9, True))

        lx = 44 * k
        for key, col, name in keys:
            c.create_oval(lx, 300 * k, lx + 11 * k, 311 * k, fill=col, outline="")
            c.create_text(lx + 17 * k, 306 * k, text=name, anchor="w", fill=INK,
                          font=sfont(9))
            lx += 78 * k

        mins = st.total("breath_min")
        c.create_text(556 * k, 306 * k, anchor="e", fill=INK_SOFT, font=sfont(9),
                      text="%d minutes of breathing so far" % mins)

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        try:
            if self.app.stats_win is self:
                self.app.stats_win = None
        except Exception:
            pass


# --------------------------------------------------------------------------
#  The application
# --------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = Config()
        self.cfg.clamp()
        if "--desktop-launch" in sys.argv:
            self.cfg["character"] = "custom"
        self.stats = Stats()

        self.card = None
        self.breath = None
        self.chip = None
        self.settings_win = None
        self.stats_win = None
        self.focus = None                 # {kind, end, total}
        self.snooze_until = 0.0
        self.hidden_until = 0.0
        self.started = time.time()
        self.last_logic = time.time()
        self.wander_in = self.cfg.get("wander_every", 3) * 60.0
        self._activity_accum = {"active": 0.0, "idle": 0.0}
        self._activity_hour = datetime.now().hour

        self.buddy = Buddy(self, root, self.cfg)
        self.modak_scene = None
        self.last_scene_error = None
        self.reminders = Reminders(self)
        self.menu = None

        root.after(80, self.buddy.tick)
        root.after(1000, self.logic_tick)
        root.after(900, self.hello)
        if _LOCK_SOCK is not None:
            root.after(100, self._desktop_commands)
        if "--desktop-launch" in sys.argv:
            root.after(150, self.activate_desktop)
        if "--modak-scene" in sys.argv:
            root.after(1100, self.start_modak_scene)

    def activate_desktop(self):
        self.stop_modak_scene()
        self.cfg["character"] = "custom"
        self.cfg.save()
        self.hidden_until = 0.0
        self.buddy.hide(False)
        self.buddy.target_x = None
        self.buddy.go_home()
        self.buddy.shut_up()
        self.buddy.anim.character = "custom"
        self.buddy.anim.set("wave", 2.4, after="idle")
        self.root.attributes("-topmost", True)
        self.root.lift()

    def _desktop_commands(self):
        """Process the pending local commands on Tk's own thread.

        The app window polls every second and the launcher may relay a
        settings change or an emote at the same moment, so drain everything
        queued this tick instead of one connection per 100 ms - otherwise
        the backlog overflows and a user's change is refused and lost."""
        for _ in range(32):
            try:
                conn, _addr = _LOCK_SOCK.accept()
            except BlockingIOError:
                break
            self._desktop_command(conn)
        self.root.after(100, self._desktop_commands)

    def _desktop_command(self, conn):
        if conn is not None:
            try:
                with conn:
                    conn.settimeout(0.1)
                    raw_cmd = conn.recv(4096).decode("utf-8", errors="replace").strip()
                    allowed = {"walk": ("walk", 4.0), "run": ("run_cycle", 3.0),
                               "hungry": ("hungry_cycle", 3.0), "laddu": ("eat_laddu", 5.0),
                               "wave": ("wave", 2.4), "celebrate": ("celebrate", 3.0)}
                    # Every Ganesh emote the old Settings window could play.
                    ganesh_emotes = {
                        "idle": 2.0, "walk": 3.0, "run_cycle": 2.4, "wave": 2.4,
                        "breathe_cycle": 3.0, "meditation_peek": 2.4, "eat_laddu": 5.0,
                        "window_peek": 2.4, "water_slump": 2.4, "drink_water": 3.0,
                        "bless_cycle": 2.6, "study_cycle": 3.2, "mouse_ride": 3.2,
                        "happy_jump": 1.3, "celebrate": 3.0, "hungry_cycle": 3.0,
                        "dance": 6.0, "stretch": 2.4, "jumping_jacks": 3.0,
                    }
                    action_note = None

                    cmd = raw_cmd
                    payload = None
                    if ":" in raw_cmd:
                        cmd, _, json_part = raw_cmd.partition(":")
                        cmd = cmd.strip()
                        try:
                            payload = json.loads(json_part)
                        except Exception:
                            payload = None

                    if cmd == "launch":
                        self.activate_desktop()
                    elif cmd == "scene":
                        self.root.after(0, self.start_modak_scene)
                    elif cmd == "scene_chase":
                        if self.modak_scene:
                            self.modak_scene.begin_chase()
                    elif cmd == "scene_stop":
                        self.stop_modak_scene()
                    elif cmd == "settings":
                        self.open_settings()
                    elif cmd == "settings_set" and isinstance(payload, dict):
                        action_note = self.apply_settings(payload)
                    elif cmd == "quit":
                        self.root.after(200, self.quit_app)
                    elif cmd == "emote" and isinstance(payload, dict):
                        state = str(payload.get("state", ""))
                        if state == "mouse_play":
                            self.root.after(0, self.start_modak_scene)
                        elif state in ganesh_emotes:
                            self.stop_ganesh_emotes()
                            self.cfg["character"] = "custom"
                            self.cfg.save()
                            self.buddy.target_x = None
                            self.buddy.shut_up()
                            self.buddy.anim.set(state, ganesh_emotes[state], after="idle")
                        else:
                            raise ValueError("Unknown emote: %s" % state)
                    elif cmd == "play_all":
                        self.play_all_ganesh_emotes()
                    elif cmd == "emote_stop":
                        self.stop_ganesh_emotes()
                    elif cmd == "reset_timers":
                        self.reminders.reset_all()
                        self.buddy.say("timers reset!", 2.4)
                    elif cmd == "reset_all":
                        for k, v in DEFAULTS.items():
                            if k not in ("goals", "pos_x", "pos_y"):
                                self.cfg[k] = v
                        self.cfg["first_run"] = False
                        self.cfg["onboarded"] = True
                        self.cfg["character"] = "custom"
                        self.cfg.clamp()
                        self.cfg.save()
                        self.reminders.reset_all()
                        self.buddy.rebuild_scale()
                        self.buddy.say("fresh start!", 2.4)
                    elif cmd == "open_folder":
                        open_folder(DATA_DIR)
                    elif cmd == "breathe":
                        self.stop_modak_scene()
                        self.start_breathing()
                    elif cmd == "eye_rest":
                        self.stop_modak_scene()
                        self.start_eye_rest()
                    elif cmd == "snooze" and isinstance(payload, dict):
                        mins = int(clamp(int(payload.get("minutes", 30)), 1, 720))
                        self.snooze_all(mins)
                    elif cmd == "snooze_off":
                        self.snooze_until = 0.0
                        self.buddy.say("reminders are on", 2.4)
                    elif cmd == "hide" and isinstance(payload, dict):
                        mins = int(clamp(int(payload.get("minutes", 15)), 1, 720))
                        self.hide_for(mins)
                    elif cmd == "show":
                        self.hidden_until = 0.0
                        self.buddy.hide(False)
                    elif cmd == "come_here":
                        self.come_here()
                    elif cmd == "go_home":
                        self.buddy.go_home()
                    elif cmd in allowed:
                        self.stop_modak_scene()
                        self.buddy.target_x = None
                        self.buddy.anim.set(*allowed[cmd], after="idle")
                        self.buddy.shut_up()
                    elif cmd == "stats":
                        pass
                    elif cmd == "goals_get":
                        pass
                    elif cmd == "goals_add" and isinstance(payload, dict):
                        self.goal_add(payload.get("name", ""))
                    elif cmd == "goals_delete" and isinstance(payload, dict):
                        self.goal_delete(payload.get("id", ""))
                    elif cmd == "goals_toggle" and isinstance(payload, dict):
                        self.goal_toggle(payload.get("id", ""))
                    elif cmd == "exercise_done":
                        self.stats.bump("exercise")
                    elif cmd == "log" and isinstance(payload, dict):
                        if not self.log_done(str(payload.get("what", ""))):
                            raise ValueError("Unknown log item")
                    elif cmd == "rem_add" and isinstance(payload, dict):
                        self.custom_add(payload)
                    elif cmd == "rem_update" and isinstance(payload, dict):
                        self.custom_update(payload)
                    elif cmd == "rem_delete" and isinstance(payload, dict):
                        self.custom_delete(str(payload.get("id") or ""))
                    elif cmd == "rem_done" and isinstance(payload, dict):
                        self.custom_done(str(payload.get("id") or ""))
                    elif cmd == "focus_start":
                        mins = None
                        if isinstance(payload, dict):
                            try:
                                mins = max(5, min(120, int(payload.get("minutes", 0))))
                            except (TypeError, ValueError):
                                mins = None
                        self.stop_modak_scene()
                        self.start_focus(mins)
                    elif cmd == "focus_stop":
                        self.stop_focus(by_click=True)
                    elif cmd == "break_start":
                        self.stop_modak_scene()
                        self.start_break()
                    elif cmd not in ("status", "settings_get"):
                        raise ValueError("Unknown desktop command: %s" % cmd)

                    nd = self.reminders.next_due()
                    next_name = None
                    next_sec = None
                    if nd:
                        key_names = {"break": "Break", "eye": "Eye rest", "water": "Water",
                                     "stretch": "Stretch", "posture": "Posture", "hunger": "Snack",
                                     "meditate": "Breathing"}
                        next_name = key_names.get(nd[0], nd[0].title())
                        next_sec = int(nd[1])

                    paused_reason = None
                    if self.reminders.idle_for >= max(60, self.cfg.get("idle_pause", 5) * 60):
                        paused_reason = "idle"
                    elif self.reminders.in_quiet_hours():
                        paused_reason = "quiet"
                    elif self.snooze_until and time.time() < self.snooze_until:
                        paused_reason = "snooze"
                    elif self.buddy.hidden:
                        paused_reason = "hidden"

                    settings_data = self.settings_payload()

                    if cmd in ("settings_get", "settings_set"):
                        response = {"app": "DeskPal", "ok": True, "settings": settings_data}
                        if action_note:
                            response["note"] = action_note
                    elif cmd in ("stats", "goals_get", "goals_add", "goals_delete",
                                "goals_toggle", "exercise_done", "focus_start",
                                "focus_stop", "break_start", "log", "rem_add",
                                "rem_update", "rem_delete", "rem_done"):
                        response = {"app": "DeskPal", "ok": True, "stats": self.stats_payload()}
                    else:
                        now = time.time()
                        f = self.focus
                        response = {
                            "app": "DeskPal",
                            "running": True,
                            "visible": not self.buddy.hidden,
                            "character": self.cfg.get("character"),
                            "pet_name": self.cfg.get("pet_name", "Mochi"),
                            "state": self.buddy.anim.state,
                            "scene": self.modak_scene.story.state if self.modak_scene else None,
                            "scene_error": self.last_scene_error,
                            "next_reminder": next_name,
                            "next_reminder_in_seconds": next_sec,
                            "quiet_mode": self.reminders.in_quiet_hours() or bool(self.snooze_until and now < self.snooze_until),
                            "paused_reason": paused_reason,
                            "idle_seconds": int(self.reminders.idle_for),
                            "snooze_seconds": int(max(0.0, self.snooze_until - now)) if self.snooze_until else 0,
                            "hidden_seconds": int(max(0.0, self.hidden_until - now)) if self.hidden_until else 0,
                            "uptime_seconds": int(now - self.started),
                            "focus_kind": f.get("kind") if f else None,
                            "focus_left": int(max(0.0, f.get("end", now) - now)) if f else 0,
                            "reminders": self.reminders.overview(),
                            "work_hours": self.reminders.in_work_hours(),
                            "version": APP_VERSION,
                            "settings": settings_data
                        }

                    conn.sendall(json.dumps(response).encode("utf-8"))
            except (OSError, ValueError):
                pass
            except Exception:
                # A bug inside one command must never silence the engine;
                # the launcher turns the empty reply into a clear error.
                log_exc("desktop_command")


    # ------------------------------------------------------------- greeting
    def hello(self):
        try:
            if "--desktop-launch" in sys.argv:
                return
            if self.cfg.get("first_run", True):
                self.cfg["first_run"] = False
                self.cfg.save()
                self.buddy.anim.set("wave", 2.6, after="idle")
                self.show_card(
                    "Hi, I am %s" % self.cfg.get("pet_name", "Mochi"),
                    "I live on top of your screen and I will remind you to take "
                    "breaks, drink water, rest your eyes and breathe.\n"
                    "Left click to pet me, drag to move me, right click for the menu.",
                    [("Let's set me up", self.open_onboarding),
                     ("Skip, use defaults", None)],
                    accent=SUN, icon="star", seconds=60)
                if self.cfg.get("sounds"):
                    play_chime("up")
                return
            if self.cfg.get("greet_on", True):
                self.buddy.anim.set("wave", 2.2, after="idle")
                self.buddy.say(random.choice(GREET[part_of_day()]), 5.0)
                if self.cfg.get("sounds"):
                    play_chime("soft")
        except Exception:
            log_exc("hello")

    # ------------------------------------------------------------ main loop
    def logic_tick(self):
        try:
            now = time.time()
            dt = clamp(now - self.last_logic, 0.05, 5.0)
            self.last_logic = now

            self.reminders.tick(dt)
            self._update_mood()
            self._check_notify()
            self._accumulate_activity(dt)

            # come back from "hide for a while"
            if self.buddy.hidden and self.hidden_until and now >= self.hidden_until:
                self.hidden_until = 0.0
                self.buddy.hide(False)
                self.buddy.say("i'm back!", 3.0)

            # wandering
            if (self.cfg.get("wander", True) and not self.buddy.hidden
                    and self.focus is None and self.breath is None):
                self.wander_in -= dt
                if self.wander_in <= 0:
                    self.wander_in = max(30.0, self.cfg.get("wander_every", 3) * 60.0)
                    if WIN.idle_seconds() > 4 or random.random() < 0.4:
                        self.buddy.wander()
        except Exception:
            log_exc("logic_tick")
        try:
            self.root.after(1000, self.logic_tick)
        except Exception:
            log_exc("logic_tick.reschedule")

    def _accumulate_activity(self, dt):
        """Roll idle_seconds() into per-hour active/idle minute buckets."""
        try:
            hour = datetime.now().hour
            if hour != self._activity_hour:
                self._activity_hour = hour
                self._activity_accum = {"active": 0.0, "idle": 0.0}
            bucket = "idle" if WIN.idle_seconds() >= 60 else "active"
            self._activity_accum[bucket] += dt
            while self._activity_accum[bucket] >= 60.0:
                self._activity_accum[bucket] -= 60.0
                self.stats.bump("%s_h%d" % (bucket, hour))
                self.stats.bump("%s_min" % bucket)
        except Exception:
            log_exc("_accumulate_activity")

    # ------------------------------------------------------------- goals
    def goals_list(self):
        try:
            out = []
            for g in self.cfg.get("goals", []) or []:
                gid = g.get("id")
                if not gid:
                    continue
                key = "goal_%s" % gid
                out.append({
                    "id": gid,
                    "name": g.get("name", "Goal"),
                    "done_today": self.stats.today(key) > 0,
                    "streak": self.stats.streak_for(key),
                    "week": [1 if rec.get(key, 0) > 0 else 0
                             for _label, rec in self.stats.last_days(7)],
                })
            return out
        except Exception:
            log_exc("goals_list")
            return []

    def goal_add(self, name):
        try:
            name = (name or "").strip()[:60]
            if not name:
                return
            goals = list(self.cfg.get("goals", []) or [])
            if len(goals) >= 20:
                return
            goals.append({"id": uuid.uuid4().hex[:8], "name": name,
                          "created": Stats.today_key()})
            self.cfg["goals"] = goals
            self.cfg.save()
        except Exception:
            log_exc("goal_add")

    def goal_delete(self, gid):
        try:
            goals = [g for g in (self.cfg.get("goals", []) or []) if g.get("id") != gid]
            self.cfg["goals"] = goals
            self.cfg.save()
        except Exception:
            log_exc("goal_delete")

    def goal_toggle(self, gid):
        try:
            key = "goal_%s" % gid
            day = self.stats.data.setdefault("days", {}).setdefault(Stats.today_key(), {})
            if day.get(key, 0) > 0:
                day[key] = 0
                tot = self.stats.data.setdefault("totals", {})
                tot[key] = max(0, tot.get(key, 0) - 1)
                self.stats.save()
            else:
                self.stats.bump(key)
        except Exception:
            log_exc("goal_toggle")

    # Keys the dashboard may read and write.  Position, goals and the
    # first-run flags stay private to the engine.
    SETTINGS_PRIVATE = ("pos_x", "pos_y", "goals", "first_run", "onboarded",
                        "custom_reminders")

    def settings_payload(self):
        """Every user-facing setting, plus the facts the About page shows."""
        out = {}
        for key, default in DEFAULTS.items():
            if key in self.SETTINGS_PRIVATE:
                continue
            out[key] = self.cfg.get(key, default)
        out["autostart"] = autostart_enabled()
        out["data_dir"] = DATA_DIR
        out["version"] = APP_VERSION
        return out

    def apply_settings(self, payload):
        """Store dashboard changes and apply the ones that need a live effect."""
        note = None
        changed = []
        for k, v in payload.items():
            if k not in DEFAULTS or k in self.SETTINGS_PRIVATE:
                continue
            default = DEFAULTS[k]
            try:
                if isinstance(default, bool):
                    v = bool(v)
                elif isinstance(default, int) and not isinstance(default, bool):
                    v = int(float(v))
                elif isinstance(default, float):
                    v = float(v)
                elif isinstance(default, str):
                    v = str(v)
            except (TypeError, ValueError):
                continue
            if self.cfg.get(k) != v:
                changed.append(k)
            self.cfg[k] = v
        self.cfg.clamp()
        self.cfg.save()
        if "autostart" in payload:
            want = bool(payload.get("autostart"))
            ok = set_autostart(want)
            self.cfg["autostart"] = autostart_enabled()
            self.cfg.save()
            if want and not ok:
                note = ("Could not add the Startup shortcut. Press Win+R, type shell:startup "
                        "and drop a shortcut to Start DeskPal.bat in that folder.")
        if "scale" in changed or "fps" in changed:
            safe(self.buddy.rebuild_scale)
        if "character" in changed:
            safe(self.buddy.anim.set, "happy", 1.2, after="idle")
            safe(self.buddy.say, "hello! new look", 2.4)
        if "always_on_top" in changed:
            try:
                self.root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
            except Exception:
                pass
        if "wander_every" in changed:
            self.wander_in = self.cfg.get("wander_every", 3) * 60.0
        return note

    def stats_payload(self):
        """Everything the dashboard needs for live charts, in one shot."""
        try:
            today_rec = self.stats.data.get("days", {}).get(Stats.today_key(), {})
            hour_now = datetime.now().hour
            hours = [{"h": h, "active": today_rec.get("active_h%d" % h, 0),
                     "idle": today_rec.get("idle_h%d" % h, 0)}
                    for h in range(0, hour_now + 1)]
            history = []
            for label, rec in self.stats.last_days(7):
                history.append({
                    "label": label,
                    "water": rec.get("water", 0),
                    "eye": rec.get("eye", 0),
                    "stretch": rec.get("stretch", 0),
                    "posture": rec.get("posture", 0),
                    "exercise": rec.get("exercise", 0),
                    "focus": rec.get("focus", 0),
                    "breaks": rec.get("breaks", 0),
                    "breath": rec.get("breath", 0),
                    "active_min": rec.get("active_min", 0),
                    "idle_min": rec.get("idle_min", 0),
                })
            targets = {k.replace("_target", ""): int(self.cfg.get(k, DEFAULTS[k]))
                       for k in TARGET_LIMITS}
            totals = self.stats.data.get("totals", {})
            heatmap = [{"label": label,
                       "hours": [rec.get("active_h%d" % h, 0) for h in range(24)]}
                      for label, rec in self.stats.last_days(7)]
            f = self.focus
            focus_session = None
            if f:
                total = float(f.get("total", 0))
                left = max(0.0, f.get("end", time.time()) - time.time())
                focus_session = {"kind": f.get("kind"),
                                 "label": f.get("label", f.get("kind")),
                                 "total": total, "left": left,
                                 "elapsed": max(0.0, total - left)}
            return {
                "today": {
                    "active_min": today_rec.get("active_min", 0),
                    "idle_min": today_rec.get("idle_min", 0),
                    "water": today_rec.get("water", 0),
                    "eye": today_rec.get("eye", 0),
                    "stretch": today_rec.get("stretch", 0),
                    "exercise": today_rec.get("exercise", 0),
                    "focus": today_rec.get("focus", 0),
                    "breaks": today_rec.get("breaks", 0),
                    "posture": today_rec.get("posture", 0),
                    "hunger": today_rec.get("hunger", 0),
                    "breath": today_rec.get("breath", 0),
                    "breath_min": today_rec.get("breath_min", 0),
                    "pets": today_rec.get("pets", 0),
                    "hours": hours,
                },
                "history": history,
                "streak": self.stats.streak(),
                "streaks": {k: self.stats.streak_for(v) for k, v in
                            (("water", "water"), ("eye", "eye"), ("stretch", "stretch"),
                             ("posture", "posture"), ("focus", "focus"), ("breaks", "breaks"))},
                "targets": targets,
                "totals": {k: int(totals.get(k, 0)) for k in
                           ("water", "eye", "stretch", "posture", "focus", "breaks",
                            "exercise", "breath", "active_min", "pets")},
                "days_tracked": len(self.stats.data.get("days", {})),
                "heatmap": heatmap,
                "focus_session": focus_session,
                "goals": self.goals_list(),
                "custom_reminders": self.custom_list(),
            }
        except Exception:
            log_exc("stats_payload")
            return {"today": {"hours": []}, "history": [], "streak": 0,
                   "streaks": {}, "targets": {}, "totals": {}, "days_tracked": 0,
                   "heatmap": [], "focus_session": None, "goals": [], "custom_reminders": []}

    # ------------------------------------------------------- outside events
    def _check_notify(self):
        """Poll notify.txt for lines dropped by outside tools (Claude Code, scripts, ...).

        Each line looks like  KIND|message text  where KIND is one of
        done / wait / error - anything else is just spoken as-is.
        """
        try:
            if not os.path.exists(NOTIFY_PATH):
                return
            with open(NOTIFY_PATH, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if not lines:
                return
            try:
                open(NOTIFY_PATH, "w", encoding="utf-8").close()
            except Exception:
                log_exc("_check_notify.clear")
            for raw in lines[-4:]:              # do not spam if a lot piled up
                line = raw.strip()
                if line:
                    self._react_to_notify(line)
        except Exception:
            log_exc("_check_notify")

    def _react_to_notify(self, line):
        try:
            kind, sep, text = line.partition("|")
            kind = kind.strip().lower() if sep else ""
            text = (text if sep else line).strip()
            b = self.buddy
            is_ganesh = self.cfg.get("character") == "custom"
            if self.card is not None:
                self.card.close()
            if kind == "done":
                if is_ganesh:
                    b.anim.set("bless_cycle", 2.6, after="idle")
                else:
                    b.anim.set("celebrate", 2.8, after="idle")
                b.say(text or "All done! Come take a look.", 6.0)
                if self.cfg.get("sounds"):
                    play_chime("up")
            elif kind in ("wait", "input", "needs_input"):
                b.anim.set("run" if is_ganesh else "wave", 2.4, after="idle")
                b.say(text or "I need you for a second!", 6.0)
                if self.cfg.get("sounds"):
                    play_chime("soft")
            elif kind == "error":
                b.anim.set("run" if is_ganesh else "shiver", 1.8, after="idle")
                b.say(text or "Something went wrong over there.", 6.0)
                if self.cfg.get("sounds"):
                    play_chime("soft")
            else:
                b.anim.set("wave", 1.8, after="idle")
                b.say(text or line, 5.0)
            WIN.push_topmost(self.root)
        except Exception:
            log_exc("_react_to_notify")

    def _update_mood(self):
        try:
            a = self.buddy.anim
            if a.state in ("meditate", "sleep"):
                return
            h = datetime.now().hour
            pct, plugged = WIN.battery()
            if pct is not None and plugged is False and pct <= self.cfg.get("battery_low", 20):
                a.mood = "worried"
            elif h >= int(self.cfg.get("night_hour", 23)) or h < 5:
                a.mood = "sleepy"
            elif self.reminders.work_seconds > self.cfg.get("break_every", 45) * 60 * 0.9:
                a.mood = "sleepy"
            else:
                a.mood = "normal"
        except Exception:
            log_exc("_update_mood")

    # ----------------------------------------------------------------- cards
    def show_card(self, title, message, buttons=None, accent=MINT, icon="bell",
                  seconds=35):
        try:
            if self.card is not None:
                self.card.close()
            self.card = ReminderCard(self, title, message, buttons, accent,
                                     seconds, icon)
            if self.cfg.get("sounds"):
                play_chime("up")
        except Exception:
            log_exc("show_card")
            self.card = None

    def status_line(self):
        """Short line for the hover bubble."""
        try:
            bits = [datetime.now().strftime("%H:%M:%S")]
            pct, plugged = WIN.battery()
            if pct is not None:
                bits.append("battery %d%%%s" % (pct, " (charging)" if plugged else ""))
            nd = self.reminders.next_due()
            if nd:
                key, left = nd
                names = {"break": "break", "eye": "eye rest", "water": "water",
                         "stretch": "stretch", "posture": "posture", "hunger": "snack",
                         "meditate": "breathing"}
                if left < 60:
                    bits.append("%s in under a minute" % names.get(key, key))
                else:
                    bits.append("%s in %d min" % (names.get(key, key), int(left // 60)))
            if self.focus:
                left = max(0, self.focus["end"] - time.time())
                bits.append("%s %d:%02d left" % (self.focus["kind"],
                                                 int(left // 60), int(left % 60)))
            return " - ".join(bits)
        except Exception:
            return "hello!"

    def tiny_tip(self):
        try:
            return random.choice(TIPS)
        except Exception:
            return "take care of yourself"

    def praise(self, what=None):
        try:
            if what in ("water", "stretch", "posture", "eye", "hunger"):
                self.stats.bump(what)
            if self.cfg.get("character") == "custom":
                # a real blessing for finishing the exercise/reminder,
                # not just a generic happy bounce
                self.buddy.anim.set("bless_cycle", 2.6, after="idle")
                self.buddy.fx.emit("sparkle", 0, 76, 6, power=0.8, color=SUN)
            else:
                self.buddy.anim.set("happy", 1.3, after="idle")
                self.buddy.fx.emit("star", 0, 76, 6, power=0.8, color=SUN)
            self.buddy.say(random.choice(PRAISE), 2.6)
            if self.cfg.get("sounds"):
                play_chime("happy")
        except Exception:
            log_exc("praise")

    def snooze_key(self, key, minutes):
        try:
            self.reminders.snooze(key, minutes)
            self.buddy.say("okay, in %d minutes" % minutes, 2.4)
        except Exception:
            log_exc("snooze_key")

    LOGGABLE = ("water", "eye", "stretch", "posture", "hunger")

    def log_done(self, what):
        """The user ticked something off in the app: count it, thank them,
        and start that reminder's interval again from now."""
        try:
            if what not in self.LOGGABLE:
                return False
            self.praise(what)
            self.reminders.reset(what)
            return True
        except Exception:
            log_exc("log_done")
            return False

    # ------------------------------------------------------ custom reminders
    def custom_list(self):
        try:
            out = []
            for rem in self.reminders.customs():
                rid = rem.get("id")
                key = "custom_%s" % rid
                left = self.reminders.custom_left(rem)
                out.append({"id": rid, "name": rem.get("name"), "every": rem.get("every", 60),
                            "on": bool(rem.get("on", True)), "msg": rem.get("msg", ""),
                            "left": int(left) if left is not None else None,
                            "today": self.stats.today(key),
                            "streak": self.stats.streak_for(key)})
            return out
        except Exception:
            log_exc("custom_list")
            return []

    def custom_add(self, payload):
        try:
            items = list(self.cfg.get("custom_reminders") or [])
            if len(items) >= 12:
                return
            items.append({"id": uuid.uuid4().hex[:8], "name": payload.get("name", ""),
                          "every": payload.get("every", 60), "on": True,
                          "msg": payload.get("msg", "")})
            self.cfg["custom_reminders"] = items
            self.cfg.clamp()
            self.cfg.save()
        except Exception:
            log_exc("custom_add")

    def custom_update(self, payload):
        try:
            rid = str(payload.get("id") or "")
            items = []
            for rem in (self.cfg.get("custom_reminders") or []):
                if rem.get("id") == rid:
                    rem = dict(rem)
                    for k in ("name", "every", "on", "msg"):
                        if k in payload:
                            rem[k] = payload[k]
                items.append(rem)
            self.cfg["custom_reminders"] = items
            self.cfg.clamp()
            self.cfg.save()
        except Exception:
            log_exc("custom_update")

    def custom_delete(self, rid):
        try:
            self.cfg["custom_reminders"] = [r for r in (self.cfg.get("custom_reminders") or [])
                                            if r.get("id") != rid]
            self.reminders.custom_timers.pop(rid, None)
            self.cfg.save()
        except Exception:
            log_exc("custom_delete")

    def custom_done(self, rid):
        try:
            if not any(r.get("id") == rid for r in self.reminders.customs()):
                return
            self.stats.bump("custom_%s" % rid)
            self.reminders.custom_timers[rid] = 0.0
            self.praise(None)
        except Exception:
            log_exc("custom_done")

    def snooze_all(self, minutes):
        try:
            self.snooze_until = time.time() + minutes * 60
            self.buddy.say("quiet for %d minutes" % minutes, 3.0)
            self.buddy.anim.set("sit", 3.0, after="idle")
        except Exception:
            log_exc("snooze_all")

    # ------------------------------------------------------------- sessions
    def _start_session(self, kind, minutes, label=None):
        try:
            self.focus = {"kind": kind, "end": time.time() + minutes * 60,
                          "total": minutes * 60.0, "label": label or kind}
            if self.chip is None:
                self.chip = TimerChip(self)
        except Exception:
            log_exc("_start_session")
            self.focus = None

    def start_break(self):
        try:
            mins = self.cfg.get("break_len", 5)
            self._start_session("break", mins)
            self.reminders.work_seconds = 0.0
            self.stats.bump("breaks")
            self.buddy.anim.set("stretch", 2.2, after="sit")
            self.buddy.say("nice! go do whatever feels good, i will wait here", 4.0)
            if self.cfg.get("sounds"):
                play_chime("calm")
        except Exception:
            log_exc("start_break")

    def start_focus(self, minutes=None):
        try:
            mins = int(minutes or self.cfg.get("focus_len", 25))
            self._start_session("focus", mins)
            self.buddy.anim.set("think", 2.4, after="sit")
            self.buddy.say("focus time! %d minutes. i'll keep quiet" % mins, 4.0)
            if self.cfg.get("sounds"):
                play_chime("up")
        except Exception:
            log_exc("start_focus")

    def start_eye_rest(self):
        try:
            self._start_session("eye", 20.0 / 60.0)
            self.buddy.anim.set("look", 3.0, after="idle")
            self.buddy.say("look far away... i'll count", 4.0)
        except Exception:
            log_exc("start_eye_rest")

    def stop_focus(self, by_click=False):
        try:
            kind = self.focus["kind"] if self.focus else ""
            self.focus = None
            if self.chip:
                self.chip.close()
            if by_click:
                self.buddy.say("stopped the %s timer" % (kind or "timer"), 2.6)
        except Exception:
            log_exc("stop_focus")

    def focus_finished(self):
        try:
            f = self.focus or {}
            kind = f.get("kind", "focus")
            self.focus = None
            if self.chip:
                self.chip.close()

            is_ganesh = self.cfg.get("character") == "custom"
            if kind == "focus":
                self.stats.bump("focus")
                self.buddy.anim.set("bless_cycle" if is_ganesh else "celebrate",
                                    2.6 if is_ganesh else 3.0, after="idle")
                self.buddy.fx.burst_ring("confetti", 0, 70, 14)
                if self.cfg.get("sounds"):
                    play_chime("happy")
                self.show_card("Focus session done",
                               "That was %d minutes of real work. Take the break, "
                               "you earned it." % int(f.get("total", 1500) / 60),
                               [("Break now", self.start_break),
                                ("One more round", self.start_focus),
                                ("Done for now", None)],
                               accent=PINK, icon="star", seconds=60)
            elif kind == "break":
                self.reminders.reset_all()
                self.buddy.anim.set("bless_cycle" if is_ganesh else "happy",
                                    2.6 if is_ganesh else 1.4, after="idle")
                if self.cfg.get("sounds"):
                    play_chime("up")
                self.show_card("Break is over",
                               "Welcome back. Shoulders down, screen at eye level.",
                               [("Back to work", None),
                                ("5 more minutes", lambda: self._start_session("break", 5)),
                                ("Focus session", self.start_focus)],
                               accent=MINT, icon="clock", seconds=45)
            elif kind == "eye":
                self.stats.bump("eye")
                self.buddy.anim.set("bless_cycle" if is_ganesh else "happy",
                                    2.6 if is_ganesh else 1.2, after="idle")
                self.buddy.fx.emit("sparkle", 0, 76, 6, color=SKY)
                self.buddy.say("eyes refreshed! " + random.choice(PRAISE), 3.4)
                if self.cfg.get("sounds"):
                    play_chime("soft")
        except Exception:
            log_exc("focus_finished")

    # ------------------------------------------------------------ breathing
    def start_breathing(self, pattern=None):
        try:
            if self.breath is not None:
                return
            if self.card is not None:
                self.card.close()
            self.breath = BreathOverlay(self, pattern=pattern)
        except Exception:
            log_exc("start_breathing")
            self.breath = None

    def on_breath_complete(self, cycles):
        try:
            self.stats.bump("breath")
            self.stats.bump("breath_min", max(1, int(cycles * 16 / 60)))
            self.reminders.reset("meditate")
            if self.cfg.get("sounds"):
                play_chime("calm")
            self.root.after(2600, lambda: safe(self._after_breath))
        except Exception:
            log_exc("on_breath_complete")

    def _after_breath(self):
        if self.cfg.get("character") == "custom":
            self.buddy.anim.set("bless_cycle", 2.6, after="idle")
        else:
            self.buddy.anim.set("happy", 1.6, after="idle")
        self.buddy.fx.burst_ring("sparkle", 0, 72, 10, color=LAV)
        self.buddy.say("that felt good. " + random.choice(PRAISE), 4.0)

    # ----------------------------------------------------------------- menu
    def show_menu(self, x, y):
        try:
            if self.menu is not None:
                try:
                    self.menu.destroy()
                except Exception:
                    pass
            m = tk.Menu(self.root, tearoff=0)
            self.menu = m
            name = self.cfg.get("pet_name", "Mochi")
            m.add_command(label="%s  (%s)" % (name, CHAR_LABELS.get(
                self.cfg.get("character", "dog"), "buddy")), state="disabled")
            m.add_separator()
            m.add_command(label="Take a break now", command=self.start_break)
            m.add_command(label="Start Pomodoro session (%d min)" % self.cfg.get("focus_len", 25),
                          command=lambda: self.start_focus())

            breathe = tk.Menu(m, tearoff=0)
            for key in ("box", "478", "calm"):
                breathe.add_command(label=BREATH_LABEL[key],
                                    command=lambda k=key: self.start_breathing(k))
            m.add_cascade(label="Breathe with me", menu=breathe)
            m.add_command(label="Rest & blink my eyes (20 sec)", command=self.start_eye_rest)
            m.add_separator()

            tricks = tk.Menu(m, tearoff=0)
            tricks.add_command(label="Running", command=lambda: self._trick("run_cycle", 2.0))
            tricks.add_command(label="Pooja (blessing)",
                               command=lambda: self._trick("bless_cycle", 2.6))
            tricks.add_command(label="Getting hungry", 
                               command=lambda: self._trick("hungry_cycle", 2.4))
            tricks.add_command(label="Eat a laddu", 
                               command=lambda: self._trick("eat_laddu", 3.0))
            tricks.add_command(label="Dance!", command=lambda: self._trick("dance", 6.0))
            tricks.add_command(label="Disco moves", command=lambda: self._trick("disco", 4.0))
            tricks.add_command(label="Wave", command=lambda: self._trick("wave", 2.4))
            tricks.add_command(label="Spin around!", command=lambda: self._trick("spin", 1.2))
            tricks.add_command(label="Take a bow", command=lambda: self._trick("bow", 1.8))
            tricks.add_command(label="Do a stretch", command=lambda: self._trick("stretch", 2.4))
            tricks.add_command(label="Jumping jacks",
                               command=lambda: self._trick("jumping_jacks", 3.2))
            tricks.add_command(label="Celebrate", command=lambda: self._trick("celebrate", 3.4))
            tricks.add_command(label="Take a nap", command=lambda: self._trick("sleep", None))
            tricks.add_separator()

            silly = tk.Menu(tricks, tearoff=0)
            silly.add_command(label="Shimmy", command=lambda: self._trick("shimmy", 2.0))
            silly.add_command(label="Applause", command=lambda: self._trick("applause", 1.8))
            silly.add_command(label="Peekaboo!", command=lambda: self._trick("peekaboo", 1.6))
            silly.add_command(label="Ta-da!", command=lambda: self._trick("tada", 1.6))
            silly.add_command(label="Moonwalk", command=lambda: self._trick("moonwalk", 2.4))
            silly.add_command(label="Robot mode", command=lambda: self._trick("robot", 2.8))
            silly.add_command(label="Fly like a hero", command=lambda: self._trick("fly", 2.4))
            silly.add_command(label="Karate chop!", command=lambda: self._trick("karate", 1.2))
            silly.add_command(label="Magic trick", command=lambda: self._trick("magic", 1.8))
            silly.add_command(label="Brrr (shiver)", command=lambda: self._trick("shiver", 1.6))
            silly.add_command(label="Achoo! (sneeze)", command=lambda: self._trick("sneeze", 1.0))
            silly.add_command(label="Hiccup", command=lambda: self._trick("hiccup", 2.2))
            silly.add_command(label="Confused", command=lambda: self._trick("confused", 2.6))
            silly.add_command(label="Boo! (surprise)",
                              command=lambda: self._trick("surprised", 0.8))
            tricks.add_cascade(label="More silly tricks", menu=silly)

            tricks.add_separator()
            tricks.add_command(label="Say something nice", command=self._say_nice)
            m.add_cascade(label="Tricks", menu=tricks)

            chars = tk.Menu(m, tearoff=0)
            for key, label in (("dog", "Puppy"), ("cat", "Kitty"), ("human", "Buddy")):
                chars.add_command(label=label + ("  *" if self.cfg.get("character") == key else ""),
                                  command=lambda k=key: self.set_character(k))
            chars.add_separator()
            has_photo = os.path.exists(CUSTOM_IDLE_PATH) or os.path.exists(GANESH_BUNDLED_IDLE)
            if has_photo:
                chars.add_command(
                    label="Ganesh" + ("  *" if self.cfg.get("character") == "custom" else ""),
                    command=lambda: self.set_character("custom"))
                chars.add_command(label="Choose a different everyday photo...",
                                  command=lambda: self.choose_custom_photo("idle"))
                chars.add_command(label="Choose an 'urgent' photo (optional)...",
                                  command=lambda: self.choose_custom_photo("urgent"))
                chars.add_command(label="More photo poses (happy/wave)... in Settings",
                                  command=self.open_settings)
            else:
                chars.add_command(label="Use my own photo...",
                                  command=lambda: self.choose_custom_photo("idle"))
            m.add_cascade(label="Change character", menu=chars)

            m.add_command(label="Come to my mouse", command=self.come_here)
            m.add_command(label="Go back to the corner", command=self.buddy.go_home)
            m.add_separator()

            quiet = tk.Menu(m, tearoff=0)
            for mins, label in ((30, "30 minutes"), (60, "1 hour"), (120, "2 hours")):
                quiet.add_command(label=label, command=lambda mm=mins: self.snooze_all(mm))
            quiet.add_command(label="Turn reminders back on",
                              command=lambda: (setattr(self, "snooze_until", 0.0),
                                               self.buddy.say("reminders are on", 2.4)))
            m.add_cascade(label="Quiet for a while", menu=quiet)

            hide = tk.Menu(m, tearoff=0)
            for mins, label in ((15, "15 minutes"), (60, "1 hour"), (240, "4 hours")):
                hide.add_command(label=label, command=lambda mm=mins: self.hide_for(mm))
            m.add_cascade(label="Hide me", menu=hide)
            m.add_separator()

            m.add_command(label="Open DeskPal app (stats)...", command=self.open_stats)
            m.add_command(label="Settings (DeskPal app)...", command=self.open_settings)
            m.add_separator()
            m.add_command(label="Quit %s" % APP_NAME, command=self.quit_app)

            try:
                m.tk_popup(int(x), int(y))
            finally:
                m.grab_release()
        except Exception:
            log_exc("show_menu")

    def _trick(self, state, duration):
        try:
            self.buddy.anim.set(state, duration, after="idle")
            if state == "dance":
                self.buddy.say_random(("watch this!", "my favourite song!", "woo!"), 2.6)
                if self.cfg.get("sounds"):
                    play_chime("happy")
            elif state == "sleep":
                self.buddy.say("wake me up any time", 3.0)
            elif state == "celebrate":
                self.buddy.fx.burst_ring("confetti", 0, 70, 14)
            elif state == "hungry_cycle":
                self.buddy.say_random(("i am getting hungry...", "is that a laddu?", "my tummy says snack time"), 2.6)
            elif state == "eat_laddu":
                self.buddy.say_random(("laddu time!", "mmm, delicious!", "that was yummy"), 3.2)
                self.buddy.fx.emit("sparkle", 0, 72, 5, color=SUN)
            elif state == "disco":
                self.buddy.say_random(("stayin' alive!", "feel the beat!", "disco time!"), 2.4)
                if self.cfg.get("sounds"):
                    play_chime("happy")
            elif state == "spin":
                self.buddy.say_random(("wheee!", "look at me go!", "so dizzy!"), 1.4)
            elif state == "bow":
                self.buddy.say_random(("thank you, thank you", "you're too kind"), 2.0)
            elif state == "jumping_jacks":
                self.buddy.say_random(("one! two!", "getting my steps in!",
                                       "phew, exercise!"), 2.4)
            elif state == "shimmy":
                self.buddy.say_random(("shimmy shimmy!", "shake it off"), 1.8)
            elif state == "applause":
                self.buddy.say_random(("bravo!", "well done, you!", "clap clap clap"), 1.6)
            elif state == "peekaboo":
                self.buddy.say_random(("peekaboo!", "i see you!", "boo... just kidding"), 1.6)
            elif state == "tada":
                self.buddy.fx.burst_ring("confetti", 0, 70, 10)
                self.buddy.say_random(("ta-da!", "and there it is!"), 1.4)
                if self.cfg.get("sounds"):
                    play_chime("up")
            elif state == "moonwalk":
                self.buddy.say_random(("smooth...", "how did i do that"), 2.0)
            elif state == "robot":
                self.buddy.say_random(("BEEP. BOOP.", "SYSTEMS. NOMINAL.",
                                       "I. AM. ROBOT."), 2.4)
            elif state == "fly":
                self.buddy.say_random(("up, up and away!",
                                       "flying buddy, reporting in!"), 2.2)
            elif state == "karate":
                self.buddy.say_random(("hiyah!", "kapow!"), 1.0)
            elif state == "magic":
                self.buddy.say_random(("abracadabra!", "ta-da, magic!"), 1.6)
                if self.cfg.get("sounds"):
                    play_chime("up")
            elif state == "shiver":
                self.buddy.say_random(("b-b-brrr", "kinda chilly"), 1.4)
            elif state == "sneeze":
                self.buddy.say_random(("achoo!", "*sniff* excuse me"), 1.0)
            elif state == "hiccup":
                self.buddy.say_random(("*hic*", "oh no, hiccups"), 1.8)
            elif state == "confused":
                self.buddy.say_random(("wait, what?", "hmm, huh?", "i am so confused"), 2.2)
            elif state == "surprised":
                self.buddy.say_random(("whoa!", "you scared me!", "oh!"), 1.0)
        except Exception:
            log_exc("_trick")

    def _say_nice(self):
        try:
            if self.cfg.get("character") == "custom":
                self.buddy.anim.set("happy", 2.2, after="idle")
                self.buddy.fx.emit("sparkle", 0, 74, 6, color=SUN)
            else:
                self.buddy.anim.set("love", 2.2, after="idle")
                self.buddy.fx.emit("heart", 0, 74, 6, color=PINK)
            self.buddy.say(random.choice([
                "you are doing better than you think",
                "one thing at a time, that is enough",
                "i am glad you are here",
                "you have survived every hard day so far",
                "be as kind to yourself as you are to others",
                "rest is not lazy, it is maintenance",
            ]), 5.0)
        except Exception:
            log_exc("_say_nice")

    def set_character(self, key):
        self.stop_modak_scene()
        try:
            self.cfg["character"] = key
            self.cfg.save()
            self.buddy.anim.set("happy", 1.4, after="idle")
            self.buddy.fx.burst_ring("sparkle", 0, 66, 10, color=SUN)
            self.buddy.say("ta-da!", 2.4)
            if self.settings_win:
                try:
                    self.settings_win.vars["character"].set(key)
                except Exception:
                    pass
        except Exception:
            log_exc("set_character")

    def redo_background_removal(self):
        """Re-run background removal on every custom photo already in place."""
        try:
            paths = [CUSTOM_IDLE_PATH] + list(CUSTOM_POSE_PATHS.values())
            done = 0
            for p in paths:
                if not os.path.exists(p):
                    continue
                try:
                    raw = tk.PhotoImage(file=p)
                    cut = remove_background_tk(raw)
                    cut.write(p, format="png")
                    _CUSTOM_IMG_CACHE.pop(p, None)
                    done += 1
                except Exception:
                    log_exc("redo_background_removal.one")
            if done:
                self.buddy.say("cleaned up the background on %d photo%s!" %
                               (done, "" if done == 1 else "s"), 3.0)
            else:
                self.buddy.say("I don't have any photos to clean up yet - choose one first!", 3.5)
        except Exception:
            log_exc("redo_background_removal")

    def choose_custom_photo(self, slot="idle"):
        """Let the user pick a picture for one pose of their custom character.

        slot "idle" is the everyday look and switches the buddy to it right
        away. Every other slot ("urgent", "happy", "wave", "walk1", "walk2")
        is an optional extra pose shown only for its matching moment, and
        never switches the character on its own - missing ones simply fall
        back to the idle photo, so nothing ever breaks if you skip them.
        """
        try:
            titles = {
                "idle": "Choose your buddy's everyday photo",
                "urgent": "Choose an 'urgent' photo (optional)",
                "happy": "Choose a 'happy' photo (optional)",
                "wave": "Choose a 'wave / greeting' photo (optional)",
                "walk1": "Choose a walking photo, facing left (optional)",
                "walk2": "Choose a walking photo, facing right (optional)",
            }
            path = filedialog.askopenfilename(
                title=titles.get(slot, "Choose a photo"),
                filetypes=[("Image files", "*.png *.gif *.ppm *.pgm"), ("All files", "*.*")])
            if not path:
                return
            try:
                raw = tk.PhotoImage(file=path)
            except Exception:
                messagebox.showerror(
                    APP_NAME,
                    "Could not open that picture.\n\n"
                    "DeskPal can only load PNG (or GIF/PPM/PGM) images without "
                    "installing anything extra. If your photo is a JPG, save or "
                    "export it as a PNG first and try again.")
                return
            dest = CUSTOM_IDLE_PATH if slot == "idle" else CUSTOM_POSE_PATHS.get(slot, CUSTOM_IDLE_PATH)
            self.buddy.say("give me a second, cutting out the background...", 3.0)
            self.root.update_idletasks()
            cut = remove_background_tk(raw)
            try:
                cut.write(dest, format="png")
            except Exception:
                log_exc("choose_custom_photo.write")
                shutil.copyfile(path, dest)   # fall back to the plain photo, uncut
            _CUSTOM_IMG_CACHE.pop(dest, None)
            if slot == "idle":
                self.set_character("custom")
            else:
                self.buddy.say("got it - I'll use that one at the right moment!", 3.0)
        except Exception:
            log_exc("choose_custom_photo")
            try:
                messagebox.showerror(APP_NAME, "Something went wrong loading that picture.")
            except Exception:
                pass

    def come_here(self):
        try:
            b = self.buddy
            x = self.root.winfo_pointerx() - b.cw / 2
            y = self.root.winfo_pointery() - b.ch + 40
            b.x, b.y = x, y
            b._clamp_into_screen()
            b._apply_geometry()
            b.floor_y = b.y
            b.anim.set("happy", 1.2, after="idle")
            b.say_random(("here!", "you called?", "hi!"), 2.4)
            self.cfg["pos_x"], self.cfg["pos_y"] = int(b.x), int(b.y)
            self.cfg.save()
        except Exception:
            log_exc("come_here")

    def hide_for(self, minutes):
        try:
            self.hidden_until = time.time() + minutes * 60
            self.buddy.hide(True)
        except Exception:
            log_exc("hide_for")

    # -------------------------------------------------------------- windows
    def start_modak_scene(self):
        self.stop_ganesh_emotes()
        self.last_scene_error = None
        try:
            if not IS_WIN or not self.buddy.transparent_ok:
                raise RuntimeError("The live scene requires Windows desktop transparency.")
            if self.breath is not None:
                raise RuntimeError("Finish the breathing session before starting the desktop scene.")
            from modak_scene import ModakScene
            self.cfg["character"] = "custom"
            self.buddy.hide(False)
            self.buddy.shut_up()
            self.buddy.canvas.delete("all")
            self.buddy.canvas.create_text(self.buddy.cw/2, self.buddy.ch/2,
                text="Preparing Vinayaka, Rat & Modak...", fill=INK, width=self.buddy.cw-30)
            self.root.update_idletasks()
            scene = ModakScene(self, PROJECT_ASSET_DIR, KEY_COLOR, FOOT_PAD_UNITS, WIN)
            self.modak_scene = scene
            scene.start()
            return True
        except Exception as error:
            self.scene_error(error)
            return False

    def stop_modak_scene(self):
        scene = getattr(self, "modak_scene", None)
        self.modak_scene = None
        if scene is not None:
            scene.close()

    def scene_error(self, error):
        self.last_scene_error = str(error)
        log("Modak scene stopped: %s" % error)
        self.stop_modak_scene()
        self.buddy.say("Scene stopped: " + str(error), 6.0)

    def play_all_ganesh_emotes(self):
        """Run the safe Ganesh showcase once; each clip returns to idle."""
        self.stop_modak_scene()
        try:
            self._ganesh_playlist_id = getattr(self, "_ganesh_playlist_id", 0) + 1
            token = self._ganesh_playlist_id
            clips = (("breathe_cycle", 3.0), ("meditation_peek", 2.4),
                     ("mouse_play", 3.2), ("study_cycle", 3.2),
                     ("bless_cycle", 2.6), ("eat_laddu", 5.0),
                     ("happy_jump", 1.3))
            def play_next(index):
                if token != self._ganesh_playlist_id:
                    return
                if index >= len(clips):
                    self.buddy.anim.set("idle")
                    return
                state, duration = clips[index]
                self.buddy.anim.set(state, duration, after="idle",
                                    on_done=lambda: play_next(index + 1))
            self.cfg["character"] = "custom"
            self.cfg.save()
            play_next(0)
        except Exception:
            log_exc("play_all_ganesh_emotes")

    def stop_ganesh_emotes(self):
        self.stop_modak_scene()
        self._ganesh_playlist_id = getattr(self, "_ganesh_playlist_id", 0) + 1
        self.buddy.anim.set("idle")

    def open_dashboard(self, section=""):
        """Open the DeskPal app window (the modern dashboard) on a background
        thread so the buddy never freezes; falls back to the classic Tk
        window when no browser can be started."""
        def worker():
            try:
                from deskpal_launch_server import ensure_launcher, open_app_window
                url = ensure_launcher() + "/dashboard" + ("#" + section if section else "")
                if open_app_window(url):
                    return
            except Exception:
                log_exc("open_dashboard")
            self.root.after(0, lambda: safe(self.open_settings_classic))
        threading.Thread(target=worker, daemon=True).start()

    def open_settings(self):
        self.open_dashboard("settings")

    def open_settings_classic(self):
        try:
            if self.settings_win is not None:
                try:
                    self.settings_win.win.lift()
                    self.settings_win.win.focus_force()
                    return
                except Exception:
                    self.settings_win = None
            self.settings_win = SettingsWindow(self)
        except Exception:
            log_exc("open_settings")
            self.settings_win = None

    def open_onboarding(self):
        try:
            OnboardingWindow(self)
        except Exception:
            log_exc("open_onboarding")

    def open_stats(self):
        self.open_dashboard("today")

    def open_stats_classic(self):
        try:
            if self.stats_win is not None:
                try:
                    self.stats_win.win.lift()
                    return
                except Exception:
                    self.stats_win = None
            self.stats_win = StatsWindow(self)
        except Exception:
            log_exc("open_stats")
            self.stats_win = None

    # ----------------------------------------------------------------- quit
    def quit_app(self):
        self.stop_modak_scene()
        try:
            self.cfg["pos_x"], self.cfg["pos_y"] = int(self.buddy.x), int(self.buddy.y)
            self.cfg.save()
            self.stats.save()
        except Exception:
            pass
        try:
            self.buddy.alive = False
        except Exception:
            pass
        for w in (self.card, self.breath, self.chip):
            try:
                if w:
                    w.close()
            except Exception:
                pass
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Single instance guard
# --------------------------------------------------------------------------
_LOCK_SOCK = None


def acquire_lock():
    """Bind a loopback port so only one buddy runs at a time."""
    global _LOCK_SOCK
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore
        except Exception:
            pass
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(16)   # launcher relays + app-window polling may overlap
        s.setblocking(False)
        _LOCK_SOCK = s
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#  Entry point
# --------------------------------------------------------------------------
def main():
    WIN.make_dpi_aware()

    if "--no-lock" not in sys.argv and not acquire_lock():
        if "--modak-scene" in sys.argv:
            try:
                with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2) as connection:
                    connection.sendall(b"scene")
                    reply = json.loads(connection.recv(4096))
                if "scene" in reply:
                    return 0
            except (OSError, ValueError):
                pass
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showinfo(APP_NAME,
                                "%s is already running.\n\n"
                                "Look for your buddy on the screen - it may be "
                                "hidden behind a window or on another monitor.\n"
                                "Right-click it and choose Quit to close it."
                                % APP_NAME)
            r.destroy()
        except Exception:
            pass
        return 0

    root = tk.Tk()

    # Fonts are asked for in points; pin Tk's conversion to the 96 dpi
    # baseline so a "10 point" font is always the same number of pixels,
    # then scale everything ourselves by the screen's real DPI.  Without
    # this, text and artwork drift apart on scaled displays.
    try:
        root.tk.call("tk", "scaling", 96.0 / 72.0)
    except Exception:
        log_exc("tk scaling")
    try:
        global UI_K
        UI_K = clamp(WIN.system_dpi() / 96.0, 0.75, 3.0)
        log("display scaling: %.2fx" % UI_K)
    except Exception:
        log_exc("UI_K")

    def on_tk_error(exc, val, tb):
        try:
            log("TK CALLBACK ERROR: %s" % "".join(
                traceback.format_exception(exc, val, tb)))
        except Exception:
            pass
    root.report_callback_exception = on_tk_error

    def on_hook(exc, val, tb):
        try:
            log("UNCAUGHT: %s" % "".join(traceback.format_exception(exc, val, tb)))
        except Exception:
            pass
    sys.excepthook = on_hook

    app = App(root)
    log("%s %s started (python %s, platform %s)"
        % (APP_NAME, APP_VERSION, sys.version.split()[0], sys.platform))

    if os.environ.get("DESKPAL_SELFTEST"):
        try:
            seconds = float(os.environ.get("DESKPAL_SELFTEST", "5"))
        except Exception:
            seconds = 5.0
        root.after(int(seconds * 1000), app.quit_app)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        safe(app.quit_app)
    except Exception:
        log_exc("mainloop")
    log("%s stopped" % APP_NAME)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        log_exc("__main__")
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(
                APP_NAME,
                "Something went wrong while starting up.\n\n"
                "The details were written to:\n%s" % LOG_PATH)
            r.destroy()
        except Exception:
            pass
        sys.exit(1)
