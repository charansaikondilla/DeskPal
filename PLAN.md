# Ganesh Character — Full Rig Plan

## The honest starting point

DeskPal's other characters (Puppy, Kitty, Buddy, and the vector Ganesh already
built into `deskpal.py`) are **drawn live, every frame, out of simple shapes**
(circles, curved lines, polygons) — not photos. That's *why* they can blink,
swing an arm, wag a tail, walk, and squash-and-stretch when they jump: each
part is its own shape that the code can move independently, 30 times a second.

Your two reference photos (`lord ganesh .png`, `lord ganesh rat.png`) are
**flat, finished 3D renders** — one single image each, with no separate
layers underneath. A flat image has no "arm" the computer can grab and
rotate; it's just pixels. So a real, fully-rigged, "moves like the vector
characters do" version has exactly two honest paths. This document lays out
both in full, so you can pick one with your eyes open.

---

## Path A — Vector rig tuned to match your photos (recommended)

**What it is:** `deskpal.py` already has a hand-coded `draw_ganesh()`
function (added earlier this session) that draws a full rig from scratch:
independent head, big ears, a curling trunk, a crown, two arms, two legs,
and it plugs into the exact same animation system as every other
character — so it already blinks, walks, waves, jumps when happy, sits in
a meditative lotus pose to rest, and reacts to reminders.

**What's left to do:** tune its proportions, colors, crown/peacock-feather
detail, and trunk curl so it visually echoes your two reference photos as
closely as vector shapes reasonably can (rounder cheeks, that specific gold
crown with the red gem, the peacock feather, the golden dhoti, the modak
prop it hugs when idle).

**Requirements:** none beyond what's already on your laptop — Python 3 +
tkinter (already confirmed working, zero installs, zero pip packages).

**Effort / risk:** Low. I edit code, compile-check it, run the existing
43-state automated smoke test (already built and proven earlier), and
deploy. No new asset pipeline, no new failure modes.

**The honest limit:** it will read as a cute, clearly-related vector-art
tribute to your photos — not a pixel-identical reproduction of a 3D render.
Vector art and photoreal 3D rendering are different mediums; no amount of
code closes that gap completely.

---

## Path B — True photo-cutout rig (photoreal, real illustration work)

This is what "real illustration animation" from an actual photo requires,
step by step, with nothing glossed over.

### 1. The part list

To move independently, each of these needs to become its **own transparent
PNG**, cut out of the source photo:

| Part | Notes |
|---|---|
| Head + ears + trunk | One rigid piece — the head doesn't bend internally |
| Torso | The seated/standing body core |
| Left upper-arm | From shoulder joint |
| Left forearm + hand | From elbow joint |
| Right upper-arm | From shoulder joint |
| Right forearm + hand | From elbow joint |
| Left leg + foot | From hip joint |
| Right leg + foot | From hip joint |
| Eyes-open head crop | You already have this — `lord ganesh rat.png` |
| Eyes-closed head crop | You already have this — `lord ganesh .png` |

Each part also needs a marked **pivot point** — the exact pixel coordinate
of the joint it rotates around (e.g., the shoulder dot for an upper arm).

### 2. How the cutting actually gets done

This is the part I need to be direct about: **cleanly separating a
continuous 3D render into interlocking limb pieces is manual image-editing
work.** An algorithm can remove a *background* reliably (I already did that
well for your two photos — flood-fill from the edges works great when
there's one clean backdrop). It cannot reliably guess *where an arm ends
and a torso begins* on a seamless 3D render — there's no color or edge
boundary marking that line, only the original 3D geometry, which no longer
exists once it's flattened into a photo. An automated attempt would produce
visibly torn, jagged seams.

So this step needs a human tracing over the image in a real editor:
- **GIMP** (free, no cost) or Photoshop.
- For each part: select it with the lasso/pen tool, copy to a new layer,
  erase everything outside it, export as its own PNG with transparency.
- Mark each pivot point (I can supply an exact pixel-coordinate checklist
  once I see the cut layers).

I'm glad to write a precise, numbered checklist for this (which part,
roughly which region of the image, which joint is the pivot) so it's a
mechanical follow-along task rather than a design decision — but the
actual cutting has to happen in an image editor, by a person, because it's
a judgment call an algorithm can't make reliably here.

### 3. How the code side works once the parts exist

`tk.PhotoImage` (what DeskPal uses to avoid any installs) **cannot rotate
an image** at runtime — only Pillow can, and Pillow isn't part of the
deployed app on purpose (that's DeskPal's "no installs, ever" promise).
The fix is a standard game-dev technique that keeps the deployed app at
zero pip packages:

1. **One-time, on a dev machine only** (not shipped, not run by your
   laptop at all): a small Pillow script rotates each limb PNG through its
   full swing range in fixed steps (say, every 5°) and saves each angle as
   its own tiny PNG — a *pre-rendered rotation sprite sheet*.
2. **At runtime**, DeskPal just picks the pre-made frame closest to the
   angle the current animation needs and swaps to it — plain image
   loading, the same `tk.PhotoImage` mechanism Path A already proved
   works with zero errors.
3. I wire this into the exact same shared pose system every character
   already uses: the blink timer swaps the eyes-open/closed head crops,
   the walk cycle swaps leg-swing frames, waving swaps arm frames, and so
   on.

### 4. Effort and risk, plainly

- **My side (code):** I can build 100% of this correctly — the rotation
  pre-render script, the frame-picking engine, the pose-system wiring —
  and I'll prove it with the same kind of automated no-crash smoke test
  I've used for every character so far.
- **Your side (or a designer's):** the actual limb cutting in GIMP/
  Photoshop. Realistically a few hours of careful tracing for a clean
  8-part rig, longer if you want it pixel-perfect.
- **Ongoing cost:** none — once the sprite sheets exist, the deployed app
  still needs nothing beyond Python + tkinter.

---

## Recommendation

Do **Path A today** — I can finish tuning the vector Ganesh to match your
photos in this session, it's fully animated already, and it carries zero
risk of new bugs.

Then, if you still want the photoreal rig, do **Path B as a follow-up**:
you (or a designer) cut the 8 parts in GIMP using a checklist I'll write
once we get there, and I build the rotation-frame engine on top of it.

## Decision needed from you

1. **Path A now** — I proceed immediately, no further input needed.
2. **Path A now, Path B later** — same as above, and I prepare the GIMP
   cutting checklist for whenever you're ready to do the manual part.
3. **Path B only, skip A** — I prepare the GIMP checklist now, and we
   pause on new engine code until the cut parts exist.

Tell me the number and I'll move immediately — no more questions after
that until there's something concrete to show you.

---

## UPDATE — what's actually live right now (built this session)

You picked "real photoreal character with real-time animation." Here's the
honest, working middle ground I built and deployed, using your own two
photos, with zero manual cutting required from you:

### What changed: one photo → a small named set of photos

Instead of a single flat image, the "My Photo" character now supports **up
to six named poses**, each a whole photo, swapped automatically at the
right moment - the same technique classic 2D game sprites use (a handful
of full frames, not a rigged skeleton):

| File (drop into DeskPal's data folder) | Required? | Shown when |
|---|---|---|
| `custom_idle.png` | **Required** | Everyday - idle, sitting, resting |
| `custom_urgent.png` | Optional | Low battery, or an urgent Claude Code event |
| `custom_happy.png` | Optional | Praised, celebrating, jumping for joy |
| `custom_wave.png` | Optional | Waving / greeting |
| `custom_walk1.png` + `custom_walk2.png` | Optional (as a pair) | Alternate every ~0.3s while wandering, for a real walk-cycle feel |

**Live right now:** your idle (calm, hugging the modak) and urgent (riding
the mouse, arms up) photos are both wired in and working - background
removed, verified pixel-clean (the rat's white fur survived the cutout;
only the true background went transparent). Find that folder any time via
**Settings → About → Open that folder**.

Any slot you skip just falls back to the everyday photo — nothing ever
breaks, verified with an automated test across every animation state and
every combination of present/missing/corrupt files (zero exceptions).

### The two easiest ways to fill in the optional slots

1. **Generate more frames from whatever produced these two** — if these
   came from an AI image tool, that's by far the easiest route: ask it for
   the same character, same style, doing a wave, looking happy, or a
   walking pose. I'll background-remove and crop each one exactly like I
   did for the first two (proven pipeline, already works).
2. **Manually crop from a bigger reference sheet** in GIMP/Photoshop if
   you have or can get one — same idea, just a plain rectangular crop per
   pose, no limb-separation needed since each pose is still one whole
   image.

### What this is *not*

This is real photos, really swapping at the right moments in real time -
but it is **not** a single photo with a moving arm or blinking eyes inside
it. That still needs true Path B (the 8-part GIMP rig above) or a vector
rig (Path A). This update is the most animation you can get from whole
photos without cutting anything.
