# Real-time Ganesh, Rat & Modak scene

## Runtime design

| Layer | Desktop object | Responsibility |
|---|---|---|
| Ganesh | Existing DeskPal buddy window | Notice, run, reach, catch and share poses. |
| Rat | Separate transparent always-on-top window | Roam, discover, carry, run, glance back and settle. |
| Modak | Separate transparent canvas image | Spawn on floor, attach to rat paws, then transfer to Ganesh hand. |
| Control | Small live button window | Shows `Take Modak from Rat` only after rat holds the modak. |

## State sequence

`ROAM (15s) -> DISCOVER (5s) -> PICK_UP (5s) -> READY -> CHASE (120s) -> CATCH (4s) -> SHARE (4s) -> IDLE`

* The button begins `CHASE`; the story never auto-starts the chase.
* Ganesh, rat and modak each have independent position, velocity and animation clocks.
* Rat turns before a desktop edge, varies speed every 6–10 seconds and stays at least 110px ahead until the final 25 seconds.
* Dragging Ganesh, hiding DeskPal, quitting, missing art or a rendering error safely cancels the scene and returns every layer to `IDLE`.

## Sprite contract

* One transparent PNG per pose; never install a contact sheet as a runtime frame.
* Required clean source assets: Ganesh run poses, rat roam/run poses and modak idle/carry poses.
* Transparent corners, no grey floor shadow, no edge debris, no crop, and no combined Ganesh/rat artwork.
* Use anchors rather than compositing: rat paw -> modak while carrying; Ganesh hands -> rat only during `CATCH`.

## Acceptance test

1. Rat appears as a separate desktop actor and remains fully on screen.
2. Exactly one modak appears and follows the correct anchor.
3. The button works once and begins a live chase.
4. Ganesh and rat do not overlap before the catch state.
5. Drag/hide/quit/restart leaves no stray rat, modak or button window.
6. Test on light and dark desktops at 100% and 150% Windows scaling.
