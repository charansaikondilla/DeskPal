# Ganesh animation production plan v5

## Scope and quality rule

These five sheets are pose and timing references. A master sheet is **not** a
desktop-ready animation. Before a clip is installed, every selected cell must
be cut into an individual 512 × 512 transparent PNG, with no neighbouring
sprite, white box, warm backdrop, grid, or cropped crown/feet.

Use one locked character model throughout: peach skin, pink ears, curly black
hair, red tilak, gold crown with red jewel and green peacock feather, yellow
dhoti with red trim, gold jewelry, and two arms. Keep camera angle, body scale,
light direction, and ground anchor consistent.

## 01 · Meditation and one-eye peek

Reference: `01-meditation-and-one-eye-peek-reference.png`

The current sitting error must be removed. Ganesh remains upright in a stable
lotus pose. He never lies down.

| Frames | Action | Acceptance rule |
|---|---|---|
| 1–4 | Sit, settle, inhale, exhale | Crown and torso stay steady; only gentle chest/tummy movement. |
| 5–6 | Both eyes peacefully closed | This is meditation only. |
| 7–8 | One eye opens halfway, then a small peek/wink | One eye must visibly remain open and the other eye must be visibly closed. |
| 9–12 | Both eyes open, gentle head tilt, small blink | Do not restart the breathing timer. |
| 13–16 | Stand-up transition to idle | Feet finish on the shared standing floor anchor. |

The supplied sheet has a warm generated background, so it is a **pose
reference only**. Regenerate or cut against a pure-white/transparent master
before runtime installation.

## 02 · Ganesh and mouse play

Reference: `02-ganesh-and-mouse-play-master.png`

Ganesh and the mouse are separate actors. Ganesh owns the body animation;
the mouse uses its own run and sniff frames. The mouse should lead by a small,
variable distance and remain within the same screen work area.

| Frames | Action | Acceptance rule |
|---|---|---|
| 1–4 | Kneel, offer palm, mouse approaches and sniffs | Mouse is clearly separate from the hand. |
| 5–8 | Bounded playful chase | Use true left/right movement, not a slide or static mouse. |
| 9–10 | Gentle catch and cuddle | Hands cup the mouse; never hold its tail. |
| 11–12 | Safe release | Mouse returns to the ground before moving away. |
| 13–16 | Follow, pause, wave, settle | Cancel instantly if the user drags Ganesh. |

Install the mouse as a separate transparent sprite atlas; do not bake a second
mouse into every Ganesh runtime frame.

## 03 · Study and sacred writing

Reference: `03-study-and-sacred-writing-master.png`

This is the additional well-known Ganesh-as-writer animation. The book remains
plain; do not generate unreadable tiny text or religious script.

| Frames | Action | Acceptance rule |
|---|---|---|
| 1–4 | Read left page, trace a line, thoughtful nod | Book stays attached to lap. |
| 5–8 | Read right page, blink, lift and turn one page | Page turns around the book hinge; it does not teleport. |
| 9–12 | Flatten page, read, get an idea, take pen | Pen appears in the hand only after it is picked up. |
| 13–16 | Write, reread, close book, rest | Writing is a gentle hand motion; book exit is a separate transition. |

Keep body, book, page, and pen as separate layers when possible. Loop frames
1–12 for focus sessions; play frames 13–16 only on completion or cancellation.

## 04 · Natural blessing

Reference: `04-natural-blessing-reference.png`

| Frames | Action | Acceptance rule |
|---|---|---|
| 1–4 | Neutral stand, attention, shoulder relaxes, hand begins lifting | No sudden arm jump. |
| 5–8 | Elbow bends, palm rotates outward, fingers stay relaxed | Palm never covers face, trunk, crown, or feather. |
| 9–12 | Blessing pose and short quiet hold | Use one small gold glow behind the palm, not repeated waving. |
| 13–16 | Glow fades, hand lowers, idle return | End at the common standing anchor. |

The supplied sheet has a warm generated background, so it is **not approved for
runtime cutting**. Keep it as a motion reference until a clean white or
transparent version is generated.

## 05 · Modak and laddu

Reference: `05-modak-and-laddu-master.png`

The modak and laddu are two distinct treats. They must use separate props and
never appear together.

| Frames | Action | Acceptance rule |
|---|---|---|
| 1–3 | Hold one pointed cream-gold modak; glance and bend knees | Modak attached to hand anchor. |
| 4–6 | Toss upward and track the continuous arc | Modak detaches at release and has enough headroom. |
| 7–8 | Open mouth and catch modak | Modak visibly reaches the mouth before it disappears. |
| 9–12 | Chew, swallow, tummy pat, satisfied settle | No visible sweet inside the body; Ganesh stays awake. |
| 13–16 | Separate laddu mini-emote: hold, raise, bite, satisfied | One round laddu only; no modak in these frames. |

For the modak clip, the sweet must be a separate animated sprite travelling on
a continuous curve. Do not use an effect that makes it jump from the air to
the stomach.

## Runtime test gate

1. All final PNGs decode and have transparent corners.
2. No white, brown, or magenta fringe is visible on light and dark desktops.
3. Consecutive frames have deliberate motion and no crown, feet, mouse tail,
   book, pen, modak, or laddu clipping.
4. Manual Emotes replay safely. Dragging cancels mouse motion. Breathing and
   focus timers keep their correct state after any visual animation.
5. Do not replace existing approved runtime frames until the new clip passes
   these tests.
