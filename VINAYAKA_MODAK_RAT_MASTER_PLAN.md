# Vinayaka, Modak & Rat — master animation plan

Implementation update: the live Emotes scene is now in `modak_scene.py` and
`deskpal.py`. See `VINAYAKA_SCENE_README.md` for the actual shipped controls,
assets, timing and test commands. The fixed-grid sheets below remain an art
production target; the working version uses measured rat-atlas regions and
existing Ganesh pose files instead of assuming those proposed sheets exist.

## Locked character design

| Actor | Correct appearance | Scale | Separate layer |
|---|---|---:|---|
| Vinayaka | Cute respectful child-like Lord Ganesh; peach skin, curly dark hair, gold crown with red jewel and green peacock feather, yellow dhoti with red trim, gold jewellery | 100% | Yes |
| Rat | Friendly grey-brown rat; pink ears, red-gold waistcoat, short yellow scarf | 33% of Vinayaka | Yes |
| Modak | One small pointed golden modak | 14% of Vinayaka | Yes |

Never put two actors in a normal runtime frame. Vinayaka, rat and modak move independently; only the final catch uses a dedicated safe combined pose.

## Sprite-sheet specification

| Sheet | Cell | Grid | Clips |
|---|---:|---:|---|
| `vinayaka_sprint_sheet.png` | 512x512 | 8x4 | idle, notice, point, run, catch, share |
| `rat_sprint_sheet.png` | 256x256 | 8x4 | roam, notice, approach, pick-up, hold, run, glance, caught |
| `modak_sprint_sheet.png` | 128x128 | 6x2 | idle, bounce, carry, handoff |

Every cell has transparent corners, 20px+ padding, one complete subject, and the same bottom anchor. No warm backdrop, glow, shadow, text, grid, neighbouring-frame pixels, crop, or duplicate subject.

## Live desktop story

1. Rat roams and sniffs for 15 seconds.
2. A separate modak appears 80–140px ahead; rat notices, approaches and picks it up.
3. Vinayaka appears far away, notices the modak, points and prepares.
4. Show **Take Modak from Rat**.
5. On click, rat and Vinayaka begin a live 120-second chase. Rat changes lane every 6–10 seconds; Vinayaka gains only near the final 25 seconds.
6. Vinayaka catches the rat safely in cupped hands; modak stays visible.
7. Vinayaka shares the modak; both return to idle.

## Required safety behavior

* One animation clock and x/y position per actor.
* Rat turns before desktop edges; never teleports.
* Modak follows a paw/hand anchor instead of being painted into the rat image.
* Drag, hide, quit, missing asset or render exception cancels the story, removes temporary rat/modak/button windows, and restores Vinayaka idle.
* Verify every PNG on light and dark wallpapers at 100% and 150% Windows scale before shipping.
