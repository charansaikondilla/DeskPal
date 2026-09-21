# Sprint-sheet quality gate

## Current art-director reference

The latest board is approved for character direction only:

* Ganesh: notice, point, run, catch-ready pose.
* Rat: sniff, notice, carry-ready, sprint pose.
* Modak: rest, bounce, handoff pose.

## Runtime decision: not approved for cutting

The board contains a warm painted background and modak glow/motion marks.
It must **not** be installed as a runtime sprite sheet, because Desktop
DeskPal requires transparent individual PNG frames with no background,
ground shadow, edge debris, or baked effects.

## Required release gate for every individual frame

1. One actor or one prop only.
2. Transparent corners and no coloured/grey halo on light or dark desktop.
3. Full head, crown, ears, feet and tail inside the canvas.
4. No adjacent-frame pixels, text, glow, shadow or duplicate actor.
5. Ganesh, rat and modak exported as separate files and placed by anchors.
