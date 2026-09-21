"""Cut the v4 master sheets into transparent DeskPal runtime frames.

Run with: py -3 cut_v4_animation_frames.py
The generated white sheets remain untouched as review masters.
"""
from pathlib import Path
import tkinter as tk

from deskpal import remove_background_tk


ROOT = Path(__file__).resolve().parent
SHEETS = ROOT / "assets" / "ganesh" / "animation-sheets-v5"
OUT = ROOT / "assets" / "ganesh"

# name: (source sheet, row, column). Each master is a 4 by 4 grid.
FRAMES = {
    # Personality: standing, breathing, blink, peek, blessing, study, water.
    "custom_breathe1.png": ("01-meditation-and-one-eye-peek-master.png", 0, 0),
    "custom_breathe2.png": ("01-meditation-and-one-eye-peek-master.png", 0, 1),
    "custom_breathe3.png": ("01-meditation-and-one-eye-peek-master.png", 0, 2),
    "custom_breathe4.png": ("01-meditation-and-one-eye-peek-master.png", 0, 3),
    "custom_peek1.png": ("01-meditation-and-one-eye-peek-master.png", 1, 1),
    "custom_peek2.png": ("01-meditation-and-one-eye-peek-master.png", 1, 2),
    "custom_peek3.png": ("01-meditation-and-one-eye-peek-master.png", 1, 1),
    "custom_peek4.png": ("01-meditation-and-one-eye-peek-master.png", 1, 3),
    "custom_window_peek1.png": ("01-personality-sprite-sheet.png", 2, 0),
    "custom_window_peek2.png": ("01-personality-sprite-sheet.png", 2, 0),
    "custom_window_peek3.png": ("01-personality-sprite-sheet.png", 1, 2),
    "custom_window_peek4.png": ("01-personality-sprite-sheet.png", 1, 3),
    "custom_water_slump1.png": ("01-personality-sprite-sheet.png", 3, 1),
    "custom_water_slump2.png": ("01-personality-sprite-sheet.png", 3, 1),
    "custom_water_slump3.png": ("01-personality-sprite-sheet.png", 3, 1),
    "custom_water_slump4.png": ("01-personality-sprite-sheet.png", 3, 1),
    "custom_water_drink1.png": ("01-personality-sprite-sheet.png", 3, 2),
    "custom_water_drink2.png": ("01-personality-sprite-sheet.png", 3, 2),
    "custom_water_drink3.png": ("01-personality-sprite-sheet.png", 3, 2),
    "custom_water_drink4.png": ("01-personality-sprite-sheet.png", 3, 3),
    "custom_study1.png": ("03-study-and-sacred-writing-master.png", 0, 0),
    "custom_study2.png": ("03-study-and-sacred-writing-master.png", 1, 2),
    "custom_study3.png": ("03-study-and-sacred-writing-master.png", 2, 3),
    "custom_study4.png": ("03-study-and-sacred-writing-master.png", 3, 1),
    "custom_bless1.png": ("04-natural-blessing-master.png", 0, 3),
    "custom_bless2.png": ("04-natural-blessing-master.png", 1, 1),
    "custom_bless3.png": ("04-natural-blessing-master.png", 2, 1),
    "custom_bless4.png": ("04-natural-blessing-master.png", 3, 2),
    # Mouse play: greet, chase, gentle catch, settle.
    "custom_mouse_play1.png": ("02-ganesh-and-mouse-play-master.png", 0, 0),
    "custom_mouse_play2.png": ("02-ganesh-and-mouse-play-master.png", 1, 1),
    "custom_mouse_play3.png": ("02-ganesh-and-mouse-play-master.png", 2, 0),
    "custom_mouse_play4.png": ("02-ganesh-and-mouse-play-master.png", 3, 3),
    # Happy jump: anticipation, takeoff, apex, landing/recovery.
    "custom_happy_jump1.png": ("02-mouse-play-happy-jump-sprite-sheet.png", 2, 0),
    "custom_happy_jump2.png": ("02-mouse-play-happy-jump-sprite-sheet.png", 2, 2),
    "custom_happy_jump3.png": ("02-mouse-play-happy-jump-sprite-sheet.png", 3, 0),
    "custom_happy_jump4.png": ("02-mouse-play-happy-jump-sprite-sheet.png", 3, 2),
}


def crop_cell(source, row, col):
    width, height = source.width(), source.height()
    cell_w, cell_h = width // 4, height // 4
    left, top = col * cell_w, row * cell_h
    frame = tk.PhotoImage(width=cell_w, height=cell_h)
    frame.tk.call(str(frame), "copy", str(source), "-from",
                  left, top, left + cell_w, top + cell_h)
    return remove_background_tk(frame, thresh=38, max_side=260)


def main():
    root = tk.Tk()
    root.withdraw()
    sources = {}
    written = 0
    try:
        for output_name, (sheet_name, row, col) in FRAMES.items():
            source = sources.get(sheet_name)
            if source is None:
                source = tk.PhotoImage(file=str(SHEETS / sheet_name))
                sources[sheet_name] = source
            image = crop_cell(source, row, col)
            image.write(str(OUT / output_name), format="png")
            written += 1
    finally:
        root.destroy()
    print("Wrote %d transparent runtime frames to %s" % (written, OUT))


if __name__ == "__main__":
    main()
