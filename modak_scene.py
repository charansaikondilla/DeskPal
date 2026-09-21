"""Live desktop scene. Pure motion model plus Tk actors; no video or dependencies."""
from collections import deque
from fractions import Fraction
import math
from pathlib import Path
import struct
import time
import tkinter as tk
from tkinter import ttk
import zlib


def desktop_png(path):
    """Convert partial alpha to a binary mask in memory for Tk colour-keying.

    Bundled artwork is 8-bit RGB/RGBA, non-interlaced PNG. Preserve RGB values;
    tiny almost-transparent generation marks must not become opaque red pixels.
    """
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG: {path}")
    pos, compressed, header = 8, bytearray(), None
    while pos < len(data):
        size = struct.unpack_from(">I", data, pos)[0]
        kind, payload = data[pos+4:pos+8], data[pos+8:pos+8+size]
        if kind == b"IHDR":
            header = payload
        elif kind == b"IDAT":
            compressed.extend(payload)
        pos += size+12
    w,h,depth,color,_,_,interlace = struct.unpack(">IIBBBBB",header)
    if depth != 8 or color not in (2,6) or interlace:
        raise ValueError(f"Unsupported sprite PNG format: {path}")
    channels = 4 if color == 6 else 3
    raw = zlib.decompress(compressed)
    stride = w*channels
    output, previous = bytearray(), bytearray(stride)
    for y in range(h):
        offset = y*(stride+1)
        mode = raw[offset]
        row = bytearray(raw[offset+1:offset+1+stride])
        for i in range(stride):
            a = row[i-channels] if i >= channels else 0
            b = previous[i]
            c = previous[i-channels] if i >= channels else 0
            if mode == 1:
                predictor = a
            elif mode == 2:
                predictor = b
            elif mode == 3:
                predictor = (a+b)//2
            elif mode == 4:
                p = a+b-c
                pa,pb,pc = abs(p-a),abs(p-b),abs(p-c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
            elif mode == 0:
                predictor = 0
            else:
                raise ValueError("Invalid PNG filter")
            row[i] = (row[i]+predictor)&255
        previous = row.copy()
        if channels == 4:
            for i in range(3,stride,4):
                row[i] = 255 if row[i] >= 160 else 0
        output.append(0)
        output.extend(row)
    def chunk(kind,payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff)
    return data[:8]+chunk(b"IHDR",header)+chunk(b"IDAT",zlib.compress(output))+chunk(b"IEND",b"")


def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Story:
    """Positions are screen coordinates at each actor's feet, in pixels."""
    def __init__(self, area, margin, scale=1.0):
        x, y, w, h = area
        self.scale = scale
        self.left, self.right = x + margin, x + w - margin
        if self.right - self.left < 240 * scale:
            raise ValueError("This display is too narrow for the chase at this buddy size. Reduce Buddy size first.")
        self.floor = y + h - 24 * scale
        self.upper = self.floor - min(230 * scale, h * .36)
        self.gx, self.gy = self.left, self.floor
        self.rx, self.ry = lerp(self.left, self.right, .35), self.floor
        self.mx, self.my = lerp(self.left, self.right, .78), self.floor
        self.direction = self.gdirection = 1
        self.state, self.t, self.chase = "roam", 0.0, 0.0
        self.elapsed = 0.0
        self.owner = "floor"
        self.history = deque(maxlen=1600)
        self.waypoint = 0
        self.points = [(self.right, self.floor), (self.right, self.upper),
                       (self.left, self.upper), (self.left, self.floor)]
        self.speed = 0.0

    def enter(self, state):
        self.state, self.t = state, 0.0
        self.start_r = (self.rx, self.ry)
        self.start_g = (self.gx, self.gy)
        self.start_m = (self.mx, self.my)

    def begin_chase(self):
        if self.state != "ready":
            return False
        self.chase = 0.0
        self.history.clear()
        self.initial_gap = math.dist((self.gx, self.gy), (self.rx, self.ry))
        self.history.append((self.gx, self.gy))
        self.history.append((self.rx, self.ry))
        self.enter("chase")
        return True

    def paw(self):
        return self.rx + self.direction * 21 * self.scale, self.ry - 14 * self.scale

    def update(self, dt):
        dt = min(max(dt, 0.0), .1)
        self.t += dt
        self.elapsed += dt
        s = self.scale
        if self.state == "roam":
            # Stop briefly to sniff between little steps.
            phase = self.t % 5
            if phase < 3.2:
                self.rx += self.direction * 26 * s * dt
            lo, hi = lerp(self.left, self.right, .25), lerp(self.left, self.right, .57)
            if self.rx >= hi or self.rx <= lo:
                self.direction = -1 if self.rx >= hi else 1
            self.rx = max(lo, min(hi, self.rx))
            if self.t >= 15:
                self.direction = 1
                self.enter("discover")
        elif self.state == "discover":
            self.rx = lerp(self.start_r[0], self.mx - 21*s, smooth((self.t-1)/4))
            if self.t >= 5:
                self.enter("pickup")
        elif self.state == "pickup":
            px, py = self.paw()
            self.mx = lerp(self.start_m[0], px, smooth((self.t-1)/3))
            self.my = lerp(self.start_m[1], py, smooth((self.t-1)/3))
            if self.t >= 5:
                self.owner = "rat"
                self.enter("ready")
        elif self.state == "chase":
            self.chase += dt
            speed = (100 + 22*math.sin(self.chase*.7)) * s
            if self.chase > 95:
                speed = 70*s
            self.speed += (speed-self.speed)*min(1, dt*2.5)
            tx, ty = self.points[self.waypoint]
            dx, dy = tx-self.rx, ty-self.ry
            distance = math.hypot(dx, dy)
            step = min(distance, self.speed*dt)
            if distance:
                self.rx += dx/distance*step
                self.ry += dy/distance*step
            if abs(dx) > 2*s:
                self.direction = 1 if dx > 0 else -1
            if distance <= 4*s:
                self.waypoint = (self.waypoint+1) % len(self.points)
            self.history.append((self.rx, self.ry))
            # Follow a trail distance behind, including the turns.
            remaining = max(lerp(300*s, 250*s, (self.chase-95)/17),
                            self.initial_gap-self.chase*35*s)
            target = self.history[0]
            previous = self.history[-1]
            for point in reversed(self.history):
                segment = math.dist(previous, point)
                if segment >= remaining and segment:
                    target = (lerp(previous[0], point[0], remaining/segment),
                              lerp(previous[1], point[1], remaining/segment))
                    break
                remaining -= segment
                previous = point
            dx, dy = target[0]-self.gx, target[1]-self.gy
            self.gx, self.gy = target
            if abs(dx) > .1*s:
                self.gdirection = 1 if dx > 0 else -1
            if self.chase >= 112:
                # Finish toward the inside of the desktop, with room for both.
                self.catch_dir = 1 if self.rx > (self.left+self.right)/2 else -1
                self.gdirection = self.catch_dir
                self.enter("catch")
        elif self.state == "catch":
            self.chase = 112 + self.t
            self.gx = lerp(self.start_g[0], self.start_r[0]-self.catch_dir*38*s, smooth(self.t/2))
            self.gy = lerp(self.start_g[1], self.start_r[1], smooth(self.t/2))
            if self.t >= 2:
                self.owner = "rat"
                self.rx = lerp(self.start_r[0], self.gx+self.catch_dir*38*s, smooth((self.t-2)/2))
                self.ry = lerp(self.start_r[1], self.gy-60*s, smooth((self.t-2)/2))
            if self.t >= 4:
                self.enter("share")
        elif self.state == "share":
            self.chase = 116 + self.t
            self.owner = "handoff"
            self.mx = lerp(self.start_m[0], self.gx+self.catch_dir*27*s, smooth(self.t/2))
            self.my = lerp(self.start_m[1], self.gy-48*s, smooth(self.t/2))
            self.rx = lerp(self.start_r[0], self.gx+self.catch_dir*82*s, smooth((self.t-2)/2))
            self.ry = lerp(self.start_r[1], self.gy, smooth((self.t-2)/2))
            if self.t >= 4:
                self.chase = 120
                self.enter("done")
        if self.owner == "rat":
            self.mx, self.my = self.paw()


class Art:
    """Cut atlas regions at load time; cache each size and direction once."""
    RAT_REGIONS = [(0, .146), (.147, .259), (.261, .384), (.386, .491),
                   (.493, .622), (.622, .773), (.775, .901), (.902, 1)]
    FILES = ["clean_ganesh_stand.png", "modak_clean.png", "scene_rat_atlas.png"] + [
        f"clean_ganesh_run{n}.png" for n in range(1,5)]

    def __init__(self, master, directory, scale):
        self.frames = {}
        self.master = master
        base = Path(directory)
        for i, name in enumerate(["clean_ganesh_stand.png"] + [f"clean_ganesh_run{n}.png" for n in range(1,5)]):
            self.add(f"g{i}", tk.PhotoImage(master=master, data=desktop_png(base/name)), 142*scale)
        self.add("modak", tk.PhotoImage(master=master, data=desktop_png(base/"modak_clean.png")), 20*scale)
        atlas = tk.PhotoImage(master=master, data=desktop_png(base/"scene_rat_atlas.png"))
        for i, (left, right) in enumerate(self.RAT_REGIONS):
            frame = tk.PhotoImage(master=master)
            frame.tk.call(frame, "copy", atlas, "-from", int(left*atlas.width()), 0,
                          int(right*atlas.width()), atlas.height())
            self.add(f"r{i}", frame, (36,48,36,48,40,40,44,48)[i]*scale)

    def add(self, name, source, height):
        # Trim only transparent padding. The PNG file itself is never changed.
        visible = {(x,y) for y in range(source.height()) for x in range(source.width())
                   if not source.transparency_get(x,y)}
        # One actor per atlas region: retain its main connected silhouette.
        points = []
        while visible:
            seed = visible.pop()
            stack, component = [seed], [seed]
            while stack:
                x,y = stack.pop()
                for dx,dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
                    p = x+dx,y+dy
                    if p in visible:
                        visible.remove(p)
                        component.append(p)
                        stack.append(p)
            if len(component) > len(points):
                points = component
        if not points:
            raise ValueError(f"Empty animation frame: {name}")
        x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
        x1, y1 = max(p[0] for p in points)+1, max(p[1] for p in points)+1
        cropped = tk.PhotoImage(master=self.master)
        cropped.tk.call(cropped, "copy", source, "-from", x0, y0, x1, y1)
        keep = set(points)
        for y in range(y0,y1):
            for x in range(x0,x1):
                if (x,y) not in keep:
                    cropped.transparency_set(x-x0,y-y0,True)
        ratio = Fraction(height/(y1-y0)).limit_denominator(16)
        resized = cropped.zoom(ratio.numerator).subsample(ratio.denominator)
        # Binary alpha avoids magenta blending on Windows' colour-key window.
        # Preserve only visible pixels; do not flood-fill or guess body colours.
        clean = tk.PhotoImage(master=self.master, width=resized.width(), height=resized.height())
        for y in range(resized.height()):
            for x in range(resized.width()):
                if not resized.transparency_get(x, y):
                    color = resized.get(x, y)
                    clean.put("#%02x%02x%02x" % color, (x, y))
        self.frames[name, 1] = clean
        self.frames[name, -1] = clean.subsample(-1, 1)

    def get(self, name, direction=1):
        return self.frames[name, direction]


class Actor:
    def __init__(self, app, key, width, height):
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=key)
        self.win.attributes("-transparentcolor", key)
        self.width, self.height = width, height
        self.canvas = tk.Canvas(self.win, width=width, height=height, bg=key,
                                highlightthickness=0, bd=0, takefocus=0)
        self.canvas.pack()
        self.item = self.canvas.create_image(width/2, height-2, anchor="s")
        self.win.geometry(f"{width}x{height}")
        self.win.update_idletasks()
        app.scene_tools.set_tool_window(self.win, no_activate=True)
        self.canvas.bind("<Button-3>", lambda event: app.stop_modak_scene())

    def show(self, x, y, frame):
        self.canvas.itemconfigure(self.item, image=frame)
        self.win.geometry("+%d+%d" % (round(x-self.width/2), round(y-self.height+2)))
        self.win.deiconify()

    def close(self):
        self.win.destroy()


class ModakScene:
    def __init__(self, app, directory, key, foot_pad, tools):
        self.app, self.buddy = app, app.buddy
        self.closed = False
        self.windows = []
        self.timer = None
        self.last = time.monotonic()
        self.key, self.foot_pad = key, foot_pad
        self.saved = (self.buddy.x, self.buddy.y, self.buddy.floor_y)
        self.saved_scale = self.buddy.s
        scale = max(.75, min(2, self.buddy.s/1.45))
        self.story = Story(self.buddy._screen_rect(), self.buddy.cw/2+12, scale)
        # Validate/load all art before creating any visible actor.
        signature = (str(directory), scale, tuple((Path(directory)/n).stat().st_mtime_ns for n in Art.FILES))
        cached = getattr(app, "_scene_art", None)
        if cached is not None and cached[0] == signature:
            self.art = cached[1]
        else:
            self.art = Art(app.root, directory, scale)
            app._scene_art = signature, self.art
        app.scene_tools = tools
        try:
            self.rat = Actor(app, key, int(130*scale), int(90*scale))
            self.windows.append(self.rat.win)
            self.modak = Actor(app, key, int(44*scale), int(40*scale))
            self.windows.append(self.modak.win)
            self.control = tk.Toplevel(app.root)
            self.windows.append(self.control)
            self.control.title("Vinayaka, Rat & Modak")
            self.control.resizable(False, False)
            self.control.attributes("-topmost", True)
            self.control.protocol("WM_DELETE_WINDOW", app.stop_modak_scene)
            self.label = ttk.Label(self.control, text="Rat is exploring...", padding=10)
            self.label.pack()
            self.button = ttk.Button(self.control, text="Take Modak from Rat",
                                     command=self.begin_chase, state="disabled")
            self.button.pack(padx=12, pady=4, fill="x")
            ttk.Button(self.control, text="Stop scene", command=app.stop_modak_scene).pack(padx=12, pady=(4,12), fill="x")
            x, y, w, h = self.buddy._screen_rect()
            self.control.geometry("+%d+%d" % (x+int(w/2)-130, y+20))
            self.buddy.target_x = None
            self.buddy.shut_up()
            self.buddy.anim.set("idle")
            self.render()
        except Exception:
            self.close()
            raise

    def begin_chase(self):
        if self.story.begin_chase():
            self.button.configure(state="disabled")

    def start(self):
        self.last = time.monotonic()
        self.timer = self.app.root.after(16, self.tick)

    def tick(self):
        self.timer = None
        if self.closed:
            return
        try:
            if (self.buddy.hidden or self.buddy._drag or not self.buddy.alive
                    or self.app.cfg.get("character") != "custom"
                    or self.buddy.s != self.saved_scale
                    or self.buddy._screen_rect() != self.area):
                self.app.stop_modak_scene()
                return
            now = time.monotonic()
            self.story.update(now-self.last)
            self.last = now
            if self.story.state == "done":
                self.app.stop_modak_scene()
                return
            self.render()
            self.timer = self.app.root.after(16, self.tick)
        except Exception as error:
            self.app.scene_error(error)

    @property
    def area(self):
        # Stored when first drawing; changing display/work area cancels safely.
        return self._area

    def render(self):
        if not hasattr(self, "_area"):
            self._area = self.buddy._screen_rect()
        s, b = self.story, self.buddy
        b.target_x = None
        b.last_ganesh_interaction = time.time()
        running = s.state == "chase"
        rat_pose = (4+(int(s.elapsed*8)%2)) if running else {
            "roam": (0,2)[int(s.elapsed*6)%2] if s.t % 5 < 3.2 else 0,
            "discover": 1 if s.t < 1 else 0, "pickup": 2 if s.t < 2 else 3,
            "ready": 3, "catch": 7, "share": 7}.get(s.state, 0)
        if running and s.chase % 9 > 8:
            rat_pose = 6
        bob = abs(math.sin(s.elapsed*12))*2*s.scale if running else math.sin(s.elapsed*2)*.6*s.scale
        self.gframe = self.art.get(f"g{1+int(s.elapsed*10)%4}" if running else "g0", s.gdirection)
        b.x = s.gx-b.cw/2
        b.y = s.gy-(b.ch-self.foot_pad*b.s)
        b._apply_geometry()
        self.rat.show(s.rx, s.ry-bob, self.art.get(f"r{rat_pose}", s.direction))
        if s.state != "roam":
            self.modak.show(s.mx, s.my-(bob if s.owner == "rat" else 0), self.art.get("modak"))
        else:
            self.modak.win.withdraw()
        self.button.configure(state="normal" if s.state == "ready" else "disabled")
        labels = {"roam": "Rat is exploring...", "discover": "A modak! Vinayaka noticed it too.",
                  "pickup": "The rat picks up the modak.", "ready": "Ready when you are!",
                  "catch": "A gentle catch", "share": "Time to share!"}
        label = ("Playful chase - %d seconds left" % max(0, math.ceil(120-s.chase))) if running else labels.get(s.state, "")
        self.label.configure(text=label)

    def draw_ganesh(self):
        b = self.buddy
        b.canvas.delete("all")
        b.canvas.create_image(b.cw/2, b.ch-self.foot_pad*b.s,
                              image=self.gframe, anchor="s")

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.app.root.after_cancel(self.timer)
            self.timer = None
        for win in self.windows:
            try:
                win.destroy()
            except tk.TclError:
                pass
        self.windows.clear()
        self.buddy.x, self.buddy.y, self.buddy.floor_y = self.saved
        self.buddy.target_x = None
        self.buddy.last_ganesh_interaction = time.time()
        self.buddy.anim.set("idle")
        self.buddy._apply_geometry()
