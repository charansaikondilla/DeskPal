# Ganesh, Rat & Modak animation sprint sheet

## Character lock

| Character | Fixed design | Size | Never include |
|---|---|---:|---|
| Ganesh | Peach skin, curly dark hair, gold crown + green peacock feather, yellow dhoti/red trim, gold jewellery | 1.0 | Rat, modak, background, ground shadow |
| Rat | Grey-brown fur, large pink ears, red-gold waistcoat, short yellow scarf | 0.33 of Ganesh | Ganesh, background, glow |
| Modak | One pointed golden sweet | 0.14 of Ganesh | Hand, rat, duplicate sweet |

Every pose is an individual transparent PNG with the feet/body aligned to the same bottom anchor.

## Ganesh frames

| Clip | Frames | Behaviour | Exit |
|---|---:|---|---|
| Idle | 4 | Calm breathing, tiny blink, gentle smile | Idle loop |
| Far notice | 4 | Looks across screen; eyes widen; turns toward modak | Point |
| Point | 4 | Gentle point toward modak; smile; no sudden arm jump | Ready |
| Run | 8 | Alternating stride, 10 fps, scarf/dhoti follows body | Run loop |
| Catch | 6 | Slow down, bend knees, cupped hands, safe hold | Share |
| Share | 4 | Offers modak, warm smile, settles | Idle |

## Rat frames

| Clip | Frames | Behaviour | Exit |
|---|---:|---|---|
| Roam | 8 | Walk, sniff, tail flick, tiny pause | Roam loop / Notice |
| Notice | 4 | Ears lift, eyes follow modak, surprised lean | Approach |
| Approach | 4 | Two cautious steps; nose reaches modak | Pick-up |
| Pick-up | 5 | Paws reach, lift; modak is attached only on final frame | Hold |
| Hold | 4 | Looks left/right, scarf sway, happy fidget | Button / Run |
| Run | 8 | Fast alternating stride, scarf trails, no prop baked in | Run loop |
| Glance | 3 | Turns head back while body continues forward | Run |
| Caught | 4 | Calm safe pose, tail visible, happy face | Share |

## Modak frames

| Clip | Frames | Behaviour | Anchor |
|---|---:|---|---|
| Idle | 2 | Quiet still / tiny settle | Desktop floor |
| Bounce | 6 | Rise, peak, fall, settle | Desktop floor |
| Carry | 2 | Same prop, no new copy | Rat paw |
| Handoff | 3 | Moves from rat paw to Ganesh hand | Animated path |

## Live scene timing

`ROAM 15s → DISCOVER 5s → PICK-UP 5s → BUTTON → CHASE 120s → CATCH 4s → SHARE 4s`

* Rat changes direction every 6–10 seconds and turns before an edge.
* Ganesh begins far away, then gains gradually; no overlap before `CATCH`.
* Modak remains a third independent layer throughout.
* Cancel on drag/hide/quit/error; destroy rat, modak and button windows; return Ganesh to idle.

## Export gate

1. Transparent corners on light and dark desktop.
2. No cropped crown, ears, feet, tail, or scarf.
3. No glow, background, floor shadow, text, fragments, or adjacent-frame pixels.
4. One actor/prop only per file; test decode every PNG before installation.
