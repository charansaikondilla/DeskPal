"""Exercise real Tk windows and Emotes controls without changing saved preferences."""
import json
from pathlib import Path
import time
import tkinter as tk

import deskpal as d


def main():
    d.Config.save = lambda self: None
    d.Stats.save = lambda self: None
    errors = []
    d.log_exc = lambda where: errors.append(where)
    root = tk.Tk()
    root.report_callback_exception = lambda *args: errors.append(str(args))
    app = d.App(root)
    for timer in root.tk.call("after", "info"):
        root.after_cancel(timer)
    app.cfg["first_run"] = False
    saved = app.buddy.x, app.buddy.y
    started = time.perf_counter()
    assert app.start_modak_scene(), app.last_scene_error
    print("Scene loaded in %.2fs" % (time.perf_counter()-started), flush=True)
    scene = app.modak_scene
    root.after_cancel(scene.timer)
    scene.timer = None
    art = scene.art
    # Render the actual runtime frames on a dark backdrop for visual review.
    sheet = tk.PhotoImage(master=root, width=1000, height=320)
    sheet.put("#222a36", to=(0,0,1000,320))
    for i in range(8):
        img = art.get(f"r{i}")
        sheet.tk.call(sheet,"copy",img,"-to",i*122+6,30)
    for i in range(5):
        img = art.get(f"g{i}")
        sheet.tk.call(sheet,"copy",img,"-to",i*180+6,130)
    sheet.tk.call(sheet,"copy",art.get("modak"),"-to",920,160)
    sheet.write("modak_scene_runtime_audit.png",format="png")
    scene.begin_chase()
    assert scene.story.state == "roam", "Early button must do nothing"
    visited = set()
    while scene.story.state != "ready":
        scene.story.update(.1)
        scene.render()
        scene.draw_ganesh()
        visited.add(scene.story.state)
        root.update()
    assert str(scene.button["state"]) == "normal"
    scene.button.invoke()
    assert scene.story.state == "chase"
    scene.button.invoke()
    while scene.story.state != "done":
        scene.story.update(.1)
        if int(scene.story.chase*10) % 5 == 0:
            scene.render()
            scene.draw_ganesh()
            root.update()
        visited.add(scene.story.state)
    print("Rendered states:",sorted(visited),flush=True)
    app.stop_modak_scene()
    root.update()
    assert app.modak_scene is None
    assert (app.buddy.x,app.buddy.y) == saved
    assert not scene.windows and scene.timer is None
    # Exercise real Emotes handler, stop button path, hide, drag and missing art.
    d.SettingsWindow._play_ganesh_emote(type("Emotes",(),{"cfg":app.cfg,"vars":{},"app":app})(),
                                      "mouse_play",3.2,"Scene")
    assert app.modak_scene is not None
    app.buddy.hide(True)
    assert app.modak_scene is None
    assert app.start_modak_scene()
    app.buddy.on_press(type("Event",(),{"x_root":300,"y_root":300})())
    assert app.modak_scene is None
    app.buddy._drag = None
    assert app.start_modak_scene()
    app.stop_ganesh_emotes()
    assert app.modak_scene is None
    original = d.PROJECT_ASSET_DIR
    d.PROJECT_ASSET_DIR = str(Path(original)/"deliberately_missing_test_assets")
    assert not app.start_modak_scene()
    assert app.modak_scene is None and app.last_scene_error
    d.PROJECT_ASSET_DIR = original
    assert app.start_modak_scene()
    app.quit_app()
    assert not errors, errors
    print("PASS: real Tk frames, Emotes start, button gating, full timeline, stop/hide/drag/quit cleanup, missing-art recovery.",flush=True)


if __name__ == "__main__":
    main()
