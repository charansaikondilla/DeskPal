# Vinayaka, Rat & Modak — live desktop scene

This version runs three independent actors on the Windows desktop. It is
available in **Settings → Emotes → Vinayaka, Rat & Modak**. You can also
double-click `Start-Vinayaka-Scene.bat`.

## Playing

1. Allow approximately 12 seconds for the first artwork load. Repeat plays
   reuse the images already loaded in memory.
2. The rat explores for 15 seconds, discovers the modak for 5 seconds, then
   picks it up over 5 seconds. Ganesh waits across the desktop.
3. Click **Take Modak from Rat** in the small control window. It becomes
   available once the rat holds the sweet and waits for you without a timeout.
4. A two-minute sequence follows: 112 seconds of pursuit, 4 seconds for a
   gentle catch, and 4 seconds for handoff and release. The modak remains a
   separate prop throughout.
5. The temporary rat, prop and control windows close automatically and Ganesh
   returns to the position occupied before the scene started.

**Stop scene**, the Emotes Stop button, dragging Ganesh, hiding DeskPal,
changing character/size, or quitting ends the scene. Right-clicking the rat
or modak also stops it. Finish a breathing session before starting the scene.

## Artwork and behavior

The scene uses five Ganesh poses, eight rat poses and one independent modak
image. Rat poses are extracted from measured regions of the supplied atlas,
not assumed equal-width cells. Images are validated and cached before playback.
Partial transparency is converted in memory for Windows colour-key windows;
the original source PNG files are not rewritten by the loader.

Motion is computed live: the rat follows desktop bounds, changes speed and
glances back; Ganesh follows its recorded path at a safe distance. Directional
frames are mirrored in memory. The prop moves continuously from ground to
paw and then hand. The catch uses separate actors and positional anchors.

This is sprite animation using the available pose artwork. It is not a fully
rigged 3D character; a dedicated hand-closing catch cycle, facial reaction
cycle and more run in-betweens would improve the art further.

## Verification

* `py -3 -B -m unittest test_modak_scene -v`: full timeline, button gating,
  bounded movement, actor separation, scales, and negative monitor origins.
* `py -3 -B verify_modak_desktop.py`: real Tk window rendering, Emotes
  handler, actual button invocation, all states, stop/hide/drag/quit and
  missing-art recovery. Uses temporary windows and does not save preferences.
* `py -3 -B verify_live_modak.py`: monitors a running scene, starts its chase
  when ready and checks completion in real time via the local command API.

The preview `modak_scene_runtime_audit.png` shows the exact loaded poses on
a dark background for inspection. Tests establish the checked behavior;
they cannot guarantee zero errors on every Windows desktop or hardware setup.
