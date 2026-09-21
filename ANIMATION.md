# Building Real Sprite-Sheet Animation for Your Ganesh Photo

## What you're looking at, honestly assessed first

Your reference photo (`lord ganesh .png`) is a seated pose: legs fully
crossed and tucked under the body, both arms wrapped around a modak held
against the chest, eyes closed. Before picking a method, it matters what
this specific pose does and doesn't give us to work with:

- **Legs**: not visible as separate limbs at all — they're folded under the
  body into one rounded shape. There is no leg silhouette here to turn into
  a walk cycle. A walking animation needs a photo where the legs are
  actually extended and visible.
- **Arms**: visible, but both are wrapped around the modak, overlapping it
  and each other. They can be separated with care, but a "swing" animation
  from this exact pose will look like the arms are still hugging something
  invisible unless the modak moves with them or gets tucked away.
- **Eyes**: closed, but this is actually the *easiest* part to animate,
  for a specific reason explained in Method 1 below.
- **Face/head/trunk**: a clean, non-overlapping unit — the easiest single
  piece to separate cleanly.

This isn't a reason to stop — it's the reason to pick the right method for
what you actually want animated. Below are the three real ways to get
there, in order of how practical they are for *this* photo.

---

## What a "sprite sheet" actually is

A sprite sheet is one image file containing several frames of a character
laid out in a grid, like a contact sheet — frame 1 (stand), frame 2
(mid-step), frame 3 (other foot forward), etc. A program shows one cell at
a time, in sequence, to fake motion — the exact technique behind every
classic 2D game character (Mario, Sonic, Pokémon all work this way).
DeskPal doesn't strictly need one *file*; it works just as well with
several separate PNGs (which is simpler to produce and edit), one per
pose — that's what the current system already uses. A true sprite-sheet
grid is only worth assembling if you want the file itself to be portable
to other tools; for DeskPal alone, separate PNGs are equivalent and easier.

---

## Method 1 — Generate more frames the same way this one was made (recommended)

**Why this is the best fit for your photo specifically:** this image has
the clean, consistent look of an AI-rendered 3D-style character (the kind
made with an image generator, not hand-modeled). If that's how it was
made, the fastest and highest-quality path to real animation is to
generate a small set of **new, matching-style renders** of the same
character in different poses — not cut up the one you have.

### Exactly what to ask for

Using whatever tool produced the original (an image generator, or the
person/service who made it for you), request these as **separate images**,
each described precisely enough to keep the same character design (same
crown, same peacock feather, same gold dhoti, same face):

1. **Standing, walking pose, left foot forward** — full body visible,
   arms in a natural walking swing, plain white background (so it matches
   your existing photos and cuts out the same way).
2. **Standing, walking pose, right foot forward** — the mirror of #1,
   same style. These two alternate to make a walk cycle.
3. **Eyes open, same head angle as the original** — this one is the
   highest-value ask: if you can get a version of the *exact same seated
   pose* with only the eyes open, that gives you a real blink (see the eye
   crop trick below).
4. *(Optional)* **Arms raised, waving** — for a greeting pose.
5. *(Optional)* **A clear jump / mid-air pose** — for celebrations.

### What I do once you have them

Exactly what I already did for your first two photos — background
removal (now fully automatic in DeskPal, verified pixel-clean, no Pillow
needed at runtime) and wiring into the pose-swap system that's already
live. Drop each finished PNG into `%APPDATA%\DeskPal\` under the right
name (`custom_walk1.png`, `custom_walk2.png`, etc. — the exact list is in
`PLAN.md`) and it works immediately, no new code required.

**Effort:** low — a handful of well-worded prompts, then I do the rest.
**Quality:** high — same render engine, same style, no visible seams.
**Risk:** zero new code paths; reuses the tested system already live.

---

## Method 2 — Real eye-blink from what you already have (works today, no new photo needed)

This one doesn't need anything new from you and is worth doing regardless
of which other method you pick.

**The trick:** a blink only needs the *eye region* to change — a small,
flat rectangle near the top of the face, not touching any other moving
part. If you get (or make) one more photo that is the **identical seated
pose, same camera angle, same everything — just eyes open**, I can:

1. Crop just the eye-band from each version (a plain rectangle, no
   limb-tracing judgment calls — this is the one piece of "cutting" that's
   genuinely easy and I could even attempt it algorithmically since it's a
   simple horizontal band, not an interlocking body part).
2. Layer the eyes-open crop on top of the existing idle photo, swap it in
   for a fraction of a second on the same timer that already drives every
   other character's blink, then back to the closed-eyes original.

This gets you a real blink using real photo pixels, with the least amount
of new art needed of any option here.

---

## Method 3 — Full manual cutout rig in GIMP (real illustration work, most flexible, most effort)

This is the "true" rig from `PLAN.md`, unchanged, repeated here for
completeness since you asked for every method in one place:

1. **Tool:** GIMP (free — gimp.org) or Photoshop.
2. **Cut these pieces as separate transparent PNGs**, each on its own
   layer, using the lasso or pen tool:
   - Head + ears + trunk (one piece)
   - Torso
   - Left upper-arm, left forearm+hand
   - Right upper-arm, right forearm+hand
   - Left leg+foot, right leg+foot *(not really possible from this exact
     seated photo — see the honest note at the top; you'd need a standing
     reference photo for this pair specifically)*
3. **Mark a pivot point** on each piece (the joint dot it rotates around)
   — I'll give you exact pixel coordinates once I see the cut layers.
4. **My side once the parts exist:** a one-time Pillow script (dev machine
   only, never shipped, keeps DeskPal's "zero installs" promise intact)
   pre-renders each limb at a handful of rotation angles as its own tiny
   PNG. At runtime, DeskPal just swaps between these pre-made frames —
   plain image loading, nothing exotic, proven technique.
5. **Effort:** genuinely a few hours of careful tracing per limb for a
   clean result. This is real illustration work — I can build 100% of the
   code side correctly (and prove it with the same kind of automated
   no-crash test I've used for every feature so far), but the cutting
   itself needs a person's judgment in an image editor; an algorithm
   guessing where a photographed 3D arm ends and the torso begins on a
   seamless render produces visibly torn seams, not a clean line.

---

## My recommendation, plainly

**Do Method 1 for real walking + more poses, and Method 2 for a real
blink right away.** Both keep DeskPal at zero installs, both reuse code
that's already built and tested, and neither asks you to learn an image
editor. Save Method 3 for later only if you specifically want an actually
rigged, continuously-moving arm rather than pose-to-pose swapping — it's
a real weekend project, not a quick add-on.

## What I need from you to move on any of these

- **For Method 1:** the new images themselves (walking pose ×2, eyes-open
  version, anything else you want) — generated however the original was
  made, saved as PNG, dropped anywhere I can reach them.
- **For Method 2:** just one more photo — same seated pose, eyes open.
- **For Method 3:** confirmation you want to do the GIMP cutting (or know
  someone who will), then I write the exact pivot-point checklist.

Tell me which one (or say "1 and 2") and I'll pick it up immediately.

---

## UPDATE — modern, lightweight methods (a wider menu)

You asked for more modern options, lightweight, HD, seamless, multiple
animations, no errors. Here's the fuller landscape, organized by how they
actually run — because "modern" and "lightweight" pull in different
directions depending on whether the work happens once (before you ever
open DeskPal) or every single frame (30 times a second, live, on your
laptop). Checked what's already on this machine so the feasibility notes
below are accurate, not guesses: **Pillow and numpy are available; OpenCV
and PyTorch are not installed** (those would need a real download — noted
per method below, and I won't install anything without asking first).

### A. Runs live, every frame — must stay pure Python + tkinter

This is the only category allowed to touch DeskPal's actual runtime,
because that's what keeps it at zero installs forever. Everything here is
either already built or a light extension of it:

| Method | What it gives you | Status |
|---|---|---|
| **Sprite pose-swap** (current system) | Whole-photo swaps for idle/urgent/happy/wave/walk1/walk2 | **Live now** |
| **Eye-band crop-swap** | Real blink from real pixels, tiny asset (Method 2 above) | Ready to build once you have an eyes-open reference |
| **Procedural "juice" on top of any photo** | Squash/stretch on landing, overshoot on stop, gentle idle sway, ambient particles (hearts/stars/confetti) | **Already live** — this is exactly what makes the photo bounce/sway instead of sitting frozen; costs nothing extra per new pose |
| **Baked rotation-frame limb rig** | A true swinging arm, from Method 3 / Path B | Needs the GIMP cutout first |

The "seamless" feeling for multiple animations mostly comes from that
third row, not from more source images — a photo that breathes, leans,
and lands with a little squish reads as far more alive than a technically
more complex rig that's held perfectly still between poses. If you want,
I can tune those secondary-motion values further (more sway, a subtle
head-tilt-on-look, etc.) with zero new art and zero new risk.

### B. Runs once, before you ever open DeskPal — can use heavier tools

These produce plain PNG files that then feed into category A. The
deployed app never sees the tool that made them.

- **AI multi-pose generation** (Method 1 above) — ask whatever generated
  the original photo for more poses in the same style. Zero installs on
  this machine either way; the generation happens on the image tool's
  side. Highest quality-per-effort of everything here.

- **AI frame interpolation** (e.g. RIFE, FILM) — given two *aligned*
  photos of the same pose with something moving between them (say, arms
  down → arms up, same camera angle), these AI models generate the
  smooth in-between frames automatically, turning a hard cut into a fluid
  multi-frame swing. Genuinely modern technique, used in real animation
  pipelines. **Caveat that matters for your specific photos:** your idle
  and "riding the rat" images are completely different poses/framing, not
  aligned — interpolating between them would produce a blurry double-
  exposure ghost, not a clean motion. This only pays off between two
  *matching-framing* poses (which ties back to Method 1 — ask for those
  aligned pairs on purpose). Feasibility here: would need a real package
  install (not currently on this machine) — happy to set it up if you get
  aligned pose pairs and want to try it.

- **AI motion-transfer from a single photo** (e.g. LivePortrait, Thin-
  Plate-Spline-Motion-Model) — the most "modern" option on this list.
  These take **one** still photo and animate it directly — blinking,
  small head turns, subtle smiling — driven by either a short reference
  video or a built-in preset, no second photo needed at all. This is the
  most direct answer to "make the existing photo itself blink." The
  output is a short video; I'd extract a handful of frames from it and
  feed those into the category-A swap system exactly like any other pose.
  **Feasibility honestly:** these are real ML models — they need PyTorch
  and a downloaded model checkpoint (real disk space and setup time, likely
  15-30+ minutes and a few GB), and without a GPU they run slower than
  real-time (fine here, since we only need to run it once and save the
  output frames — we're not animating live). I have not installed this on
  your machine; I'd want your go-ahead first since it's a genuine,
  non-trivial install, not a quick pip line.

- **2D skeletal tools** (DragonBones - free, or Spine - paid) — the
  professional way to build a jointed rig with smooth bending at joints
  instead of rigid cutout pieces. Produces a small JSON skeleton + a PNG
  atlas. I could write a pure-tkinter reader for the JSON + do the bone
  transforms myself (rotation/translation only, since tkinter can't do
  the smooth mesh-bending these tools are really designed for) — so you'd
  get the same rigid-piece result as Method 3, just built inside a nicer
  visual tool than plain GIMP layers. Worth it only if you'd genuinely
  rather pose a rig visually than trace masks by hand.

### Recommendation, updated

For "better, HD, seamless, multiple animations, no errors" specifically:
1. **Turn up the procedural juice** on what's already running — free,
   instant, zero risk, I can do this right now.
2. **Method 1** (more AI-generated poses in matching style) for real new
   animations — best quality per effort, nothing to install.
3. **LivePortrait-style motion transfer** only if you want the *actual*
   photo to blink on its own with no second reference photo — but this is
   the one item here with a real install cost, so say the word and I'll
   set it up rather than doing it unasked.

One honest note on "HD": your character renders at roughly 130px tall on
screen, so the limiting factor was never resolution — it's already using
a clean, high-res source photo and DeskPal downsamples it once and caches
the result. Rendering at true HD internally would cost CPU for zero
visible difference at that size; the current pipeline is already the
"HD-in, small-and-crisp-out" approach you'd want.

---

## UPDATE — the actual prompt, ready to paste into an AI image tool

This is Method 1, written out as real prompt text. Paste it into whatever
generated your original two photos (or Midjourney, DALL-E 3 / ChatGPT
images, Leonardo.ai, or similar).

### One honest heads-up before you use it

Asking one image generation for a perfect grid of 6-8 poses, all
identically proportioned and instantly croppable, is the hardest thing to
get a clean result from today's AI tools — most of them drift the
character's face, colors, or proportions slightly from cell to cell, even
within one image. The **single-sheet prompt** is below exactly as you
asked for it, but the **reliable fallback** if the sheet comes out
inconsistent is the same prompt run **once per pose** (swap only the
bracketed `[POSE]` line each time, keep everything else identical) — that
consistently keeps the character on-model because the tool isn't trying
to juggle 6 versions of it in one canvas at once. Try the sheet first;
fall back to one-at-a-time if the cells don't match closely enough to cut
apart cleanly.

### The single-sheet prompt

```
A single reference sprite sheet, one image divided into a clean 2x4 grid
of 8 square cells with thin white gutters between them, each cell showing
the SAME character in a different pose, character sheet style, consistent
scale and camera distance in every cell.

CHARACTER (identical in every cell): a cute chibi baby Ganesha, 3D
rendered in a soft glossy Pixar/Disney-style, big round elephant head
with a gently curled trunk and large rounded elephant ears, short dark
curly hair, an ornate gold crown set with a red gem, a blue-and-green
peacock feather tucked into the crown, warm rosy blush on the cheeks,
soft warm tan skin, wearing a golden-yellow dhoti wrap with a thin
patterned border, gold bracelets on the wrists and gold anklets, small
and round child-like proportions, gentle sweet expression.

BACKGROUND: pure flat white, no shadows, no floor line, even soft studio
lighting from the front, no rim light, no gradient - flat white behind
the character in every single cell so each pose can be cut out cleanly.

POSES (one per cell, left to right, top to bottom):
1. Sitting cross-legged, both arms hugging a golden teardrop-shaped
   modak sweet against the chest, eyes gently closed, soft smile
2. Identical sitting cross-legged pose and framing as cell 1, but eyes
   open wide and bright, same soft smile
3. Standing, mid-walk with the LEFT foot stepped forward, arms swinging
   naturally in an opposite walking rhythm, gentle happy expression
4. Standing, mid-walk with the RIGHT foot stepped forward, arms swinging
   the opposite way from cell 3, same gentle happy expression
5. Standing upright with both arms relaxed at the sides, calm neutral
   idle stance, eyes open, soft smile
6. One arm raised in a cheerful wave above the head, big bright happy
   eyes, open joyful smile
7. Both arms thrown up overhead, mid-air hop with both feet slightly off
   the ground, big excited open-mouth smile, celebrating
8. Sitting on top of a small white pet mouse, both arms raised
   excitedly, big open bright eyes, joyful open-mouth smile

Same character design, same colors, same crown, same proportions in
every cell - only the pose and eye state change. High detail, smooth
glossy 3D render, front-facing camera angle in every cell, centered
composition in every cell.
```

### If your tool supports an image reference (recommended)

Text alone often drifts the character slightly between generations. If
the tool lets you attach a reference image alongside the prompt
(Midjourney's `--cref`, an "image prompt" upload, ChatGPT's "match the
style of this image," Leonardo's image guidance, etc.), attach
`lord ganesh .png` and/or `lord ganesh rat.png` and add a line like:

```
Match the exact character design, colors, crown, and art style of the
attached reference image(s) in every cell.
```

This locks identity far better than description alone.

### One-pose-at-a-time version (the reliable fallback)

Same character block and background block as above, but generate one
image per pose instead of a grid — same wording, just this single line
swapped each time for the `POSES` section:

```
POSE: [sitting cross-legged, hugging a modak, eyes closed, soft smile]
POSE: [identical sitting pose, eyes open, soft smile]
POSE: [mid-walk, left foot forward, arms swinging naturally]
POSE: [mid-walk, right foot forward, arms swinging the opposite way]
POSE: [standing upright, arms relaxed at sides, calm neutral stance]
POSE: [one arm raised in a cheerful wave, big bright happy eyes]
POSE: [both arms thrown up overhead, mid-air hop, excited open-mouth smile]
```

### After you generate them

Send me whatever comes out (the sheet, or the separate images) — I'll
crop, background-remove (fully automatic now, verified pixel-clean, no
installs), and wire each one into the pose-swap system that's already
live, exactly as I did for your first two photos.

---

## UPDATE — the real blink pair, and the full 15-pose companion sheet

### Blink pair prompt (single image, matched to your live idle photo)

```
Generate a single image, one character only, no grid, no multiple poses.

CHARACTER: a cute chibi baby Ganesha, 3D rendered in a soft glossy
Pixar/Disney-style. Sitting cross-legged. Big round pink elephant ears.
Short dark curly brown hair. A gold crown with a red gem in the center and
a blue-and-green peacock feather tucked into the right side of the crown.
Warm tan skin. One hand raised near the chest/chin in a gentle, relaxed
gesture. Wearing a golden-yellow dhoti wrap. Small, round, child-like
proportions.

EYES: closed, in a soft, peaceful, gently-shut expression (a calm blink,
not scrunched or squinting) - this is the ONE thing that should be
different from the reference.

EVERYTHING ELSE must match the attached reference photo exactly: same
camera angle, same head tilt, same hand position, same crown position,
same body pose, same proportions, same lighting, same framing/crop, same
plain white background. Do not change the pose, the hand gesture, the
crown, the outfit, the colors, or the camera framing in any way - only
close the eyes.
```

Attach `C:\Users\cc221\AppData\Roaming\DeskPal\custom_idle.png` as the
reference image if your tool supports it - this is what makes the framing
actually match closely enough for a clean blink swap.

### Full 15-pose companion sprite sheet, one prompt

Covers every animation requested: walking, riding the rat, running left
and right, sleeping, meditating, eyes open/closed, eating a modak, sad/
dehydrated, blessing, celebrating, jumping, dancing, and studying.

**The same honest heads-up as always:** a single generation holding 15
cells perfectly consistent is genuinely hard for today's AI tools - some
drift is likely even with everything below done right. This prompt
minimizes that (one locked character block repeated for every cell,
related poses placed next to each other, a reference image to attach if
supported), but if some cells still come out off-model, regenerate just
that one pose afterward using the single-image prompt pattern above with
its `POSE:` line swapped - don't fight the grid harder.

```
Generate a single reference sprite sheet: one image, a clean 5-column by
3-row grid of 15 equal cells with thin white gutters between them. Every
cell shows the SAME character in a different pose or action. Character
sheet style. Identical scale, camera distance and front-facing camera
angle in every cell. A short text label in a simple dark serif font
appears centered directly under each character, naming that cell's pose
(the exact label text is given with each pose below).

CHARACTER - identical in all 15 cells, do not vary the design:
a cute chibi baby Ganesha (Lord Ganesh / Vinayaka), 3D rendered in a soft
glossy Pixar/Disney-style. Big round elephant head with a gently curled
trunk and large rounded pink elephant ears. Short dark curly brown hair.
An ornate gold crown (mukut) with a red gem centered and a blue-and-green
peacock feather tucked into the right side. A small tilak mark on the
forehead. Warm tan skin with soft rosy cheeks. Wearing a golden-yellow
dhoti wrap with a thin patterned border, gold bracelets and anklets.
Small, round, child-like proportions throughout. Gentle, sweet expression
unless a pose specifically calls for a different one.

BACKGROUND - identical in all 15 cells: pure flat white, no shadows, no
floor line, even soft studio lighting from the front, no gradient.

GRID LAYOUT AND LABELS (row by row, left to right):

Row 1:
1. "Walking" - standing, mid-stride walk, arms swinging naturally,
   facing toward the right side of the frame
2. "Riding the Rat" - sitting on top of a small white pet mouse that is
   walking, both arms relaxed or gently holding on, facing right
3. "Running Right" - dynamic running pose, both feet off the ground
   mid-stride, leaning slightly forward, facing toward the right
4. "Running Left" - the exact same dynamic running pose and energy as
   cell 3, but facing toward the left instead
5. "Sleeping" - lying curled on its side, eyes closed, peaceful, hands
   tucked near the chin

Row 2:
6. "Meditating" - sitting cross-legged in a lotus position, both palms
   resting together at chest height, eyes closed, calm serene expression
7. "Eyes Open" - sitting cross-legged, hands resting on the knees, eyes
   open wide and bright, gentle smile
8. "Eyes Closed" - the exact same sitting cross-legged pose, camera
   angle and hand position as cell 7, only the eyes are gently closed
9. "Eating Modak" - sitting cross-legged, both hands holding a golden
   teardrop-shaped modak sweet up near the mouth, joyful expression
10. "Feeling Dehydrated" - sitting, shoulders slightly slumped, eyes
    half-closed and tired-looking, one hand near the throat, a single
    small sweat drop, a slightly parched/tired expression

Row 3:
11. "Blessing" - sitting or standing, one hand raised palm-forward in a
    gentle blessing gesture, calm warm expression
12. "Celebrating" - both arms thrown up overhead, joyful open-mouthed
    smile, small confetti pieces around the character
13. "Jumping" - both feet off the ground mid-jump, arms up, big happy
    open-mouthed smile
14. "Dancing" - one arm up and one arm out, mid-dance-step pose, playful
    joyful expression
15. "Studying" - sitting cross-legged with an open book held in both
    hands, looking down at the pages, calm focused expression

Consistent character design, colors, crown, and proportions in every
cell - only the pose, action and expression change. High detail, smooth
glossy 3D render, centered composition in every cell.
```

Attach `C:\Users\cc221\AppData\Roaming\DeskPal\custom_idle.png` as a
reference image if supported, and add:

```
Match the exact character design, colors, crown, and art style of the
attached reference image in every cell.
```

### After you generate it

Send me the sheet (or individual poses). I'll analyze the grid precisely
- exact pixel boundaries, not guesses - crop each pose, run it through the
real background-removal pipeline, and wire it in. Walking and the rat
already have a home in the engine; sleeping, meditating, the eyes open/
closed pair, eating, dehydrated, blessing, celebrating, jumping, dancing
and studying will each need a small trigger added (praise reactions,
reminders, focus sessions, idle moments) - I'll map each to where it
actually fits once I see what came out.

---

## UPDATE — second sheet: better blessing + food/hunger set (10 poses)

This one worked genuinely well as a template (`image.png` - real distinct
poses, clean labels, one matched pair) so this new sheet follows the exact
same format: 5 columns x 2 rows, same character block, same white
background, same label style. Two goals: a richer, more expressive
blessing gesture (you asked for "much more better"), and a real food/
hunger set (modak, laddu, and an actual hungry expression - which now has
somewhere to go, since DeskPal already has a "getting hungry" reminder
that only had text before).

```
Generate a single reference sprite sheet: one image, a clean 5-column by
2-row grid of 10 equal cells with thin white gutters between them. Every
cell shows the SAME character in a different pose or action. Character
sheet style. Identical scale, camera distance and front-facing camera
angle in every cell. A short text label in a simple dark serif font
appears centered directly under each character, naming that cell's pose
(the exact label text is given with each pose below).

CHARACTER - identical in all 10 cells, do not vary the design:
a cute chibi baby Ganesha (Lord Ganesh / Vinayaka), 3D rendered in a soft
glossy Pixar/Disney-style. Big round elephant head with a gently curled
trunk and large rounded pink elephant ears. Short dark curly brown hair.
An ornate gold crown (mukut) with a red gem centered and a blue-and-green
peacock feather tucked into the right side. A small tilak mark on the
forehead. Warm tan skin with soft rosy cheeks. Wearing a golden-yellow
dhoti wrap with a thin patterned border, gold bracelets and anklets.
Small, round, child-like proportions throughout.

BACKGROUND - identical in all 10 cells: pure flat white, no shadows, no
floor line, even soft studio lighting from the front, no gradient.

GRID LAYOUT AND LABELS (row by row, left to right):

Row 1 - blessing, three richer variations:
1. "Blessing Gentle" - sitting, one hand raised palm-forward at chest
   height, soft warm close-eyed smile, calm and tender
2. "Blessing Grand" - sitting or kneeling slightly forward, BOTH hands
   raised palms-forward in a wide, generous blessing gesture, warm
   open-eyed smile, a soft golden glow or a few small sparkles around the
   raised hands
3. "Blessing Close" - upper body leaning slightly toward the viewer, one
   hand raised close to the frame in a warm inviting blessing gesture,
   big gentle eyes looking directly at the viewer
4. "Eating Modak" - sitting cross-legged, both hands holding a golden
   teardrop-shaped modak sweet up near the mouth, mid-bite, joyful eyes
5. "Eating Laddu" - sitting cross-legged, both hands holding a round
   golden-orange laddu sweet up near the mouth, mid-bite, delighted
   expression, a few crumbs visible

Row 2 - hunger and food reactions:
6. "Hungry" - sitting, one hand resting on the belly, eyes looking
   slightly down and to the side toward an empty bowl in front, a gentle
   wistful/longing expression, mouth in a small pout
7. "Craving Sweets" - sitting, both hands clasped together excitedly,
   eyes wide and fixed on a small bowl of laddus and modaks placed in
   front, an eager anticipating expression
8. "Offering Modak" - sitting, holding a single modak out toward the
   viewer with both hands, warm generous smile, as if sharing
9. "Satisfied" - sitting back slightly, both hands resting on a full
   round belly, eyes closed, a content and blissful smile, totally happy
10. "Happy After Treat" - sitting, one hand near the mouth wiping a
    crumb away, big cheerful grin, sparkling happy eyes

Consistent character design, colors, crown, and proportions in every
cell - only the pose, action and expression change. High detail, smooth
glossy 3D render, centered composition in every cell.
```

Attach `C:\Users\cc221\AppData\Roaming\DeskPal\custom_idle.png` as a
reference image if your tool supports it, and add:

```
Match the exact character design, colors, crown, and art style of the
attached reference image in every cell.
```

### Where these will plug in once you send them

- Blessing Gentle/Grand/Close -> the wave/greeting trigger picks one at
  random each time for variety, instead of always the same single image
- Eating Modak / Eating Laddu -> alternate on the praise/celebration
  reaction
- Hungry / Craving Sweets -> the existing "getting hungry" reminder
  (currently text-only) gets a real face for the first time
- Offering Modak / Satisfied / Happy After Treat -> extra praise-moment
  variety, picked at random alongside the eating poses

Send whatever comes out and I'll wire it the same way as last time -
precise grid analysis, real background removal, zero errors.

---

## UPDATE — third sheet: better running + office/work (6 poses)

Smaller and focused: improved running energy, and a work/office pose for
focus sessions (ties into "pro time when your working" from onboarding).

```
Generate a single reference sprite sheet: one image, a clean 3-column by
2-row grid of 6 equal cells with thin white gutters between them. Every
cell shows the SAME character in a different pose or action. Character
sheet style. Identical scale, camera distance and front-facing camera
angle in every cell. A short text label in a simple dark serif font
appears centered directly under each character, naming that cell's pose.

CHARACTER - identical in all 6 cells: a cute chibi baby Ganesha (Lord
Ganesh / Vinayaka), 3D rendered in a soft glossy Pixar/Disney-style. Big
round elephant head with a gently curled trunk and large rounded pink
elephant ears. Short dark curly brown hair. An ornate gold crown with a
red gem and a blue-and-green peacock feather on the right side. A small
tilak mark on the forehead. Warm tan skin, rosy cheeks. Golden-yellow
dhoti wrap with a patterned border, gold bracelets and anklets. Small,
round, child-like proportions.

BACKGROUND - identical in all 6 cells: pure flat white, no shadows, no
floor line, even soft studio lighting, no gradient.

Row 1:
1. "Sprinting" - full-effort dynamic run, both feet off the ground, body
   leaning forward hard, arms pumping, determined excited expression,
   facing right
2. "Running Energetic" - a livelier running stride than a calm jog, one
   leg fully extended back and one knee driven high, trunk swinging with
   the motion, joyful open-mouth expression, facing right
3. "Running Tired" - running but clearly winded, slightly hunched
   forward, mouth open panting, one hand near the chest, still moving but
   effortful

Row 2:
4. "At the Desk" - sitting at a small desk or table with a laptop open in
   front, both hands near the keyboard, focused calm expression, looking
   at the screen
5. "Writing" - sitting with a notebook and a pen, one hand writing, the
   other holding the notebook steady, concentrated thoughtful expression
6. "Office Break" - leaning back slightly, both arms stretched up and
   back in a stretch, eyes closed, content relieved expression, as if
   pausing during a work session

Consistent character design, colors, crown, and proportions in every
cell - only the pose, action and expression change. High detail, smooth
glossy 3D render, centered composition in every cell.
```

Attach `custom_idle.png` as a reference image if your tool supports it,
plus: "Match the exact character design, colors, crown, and art style of
the attached reference image in every cell."

**Where these plug in:** Sprinting/Running Energetic pick by facing
direction for the urgent dash (replacing today's run_left/run_right, or
added as more variety); Running Tired could show up on longer urgent
waits; At the Desk / Writing show during Pomodoro focus sessions (a real
trigger DeskPal already has, just never had a matching pose); Office
Break shows on the break reminder.

Send it over when ready and I'll wire it in the same tested way.

---

## UPDATE — fourth sheet: walking, focused on consistency

A dedicated walking sheet with several stages of the stride, and much
stronger consistency wording (repeating the character block per row, not
just once) since that's been the main risk with every sheet so far.

```
Generate a single reference sprite sheet: one image, a clean 3-column by
2-row grid of 6 equal cells with thin white gutters between them. Every
cell shows the EXACT SAME character - same face, same crown, same colors,
same proportions - only the walking stride stage changes. Character sheet
style, like a game animator's reference sheet. Identical scale, identical
camera height, identical front-facing camera angle, identical lighting in
every single cell, as if the camera never moved and only the character
stepped forward between shots. A short text label in a simple dark serif
font appears centered directly under each character, naming that cell.

CHARACTER (repeat this exact design in every one of the 6 cells without
any variation): a cute chibi baby Ganesha (Lord Ganesh / Vinayaka), 3D
rendered in a soft glossy Pixar/Disney-style. Big round elephant head
with a gently curled trunk and large rounded pink elephant ears. Short
dark curly brown hair. An ornate gold crown with a red gem centered and a
blue-and-green peacock feather tucked into the right side. A small tilak
mark on the forehead. Warm tan skin with soft rosy cheeks. Golden-yellow
dhoti wrap with a thin patterned border, gold bracelets and anklets.
Small, round, child-like proportions. Cheerful, calm expression, walking
at an easy natural pace, not running.

BACKGROUND - identical in all 6 cells: pure flat white, no shadows, no
floor line, even soft studio lighting from the front, no gradient.

WALK CYCLE STAGES (row by row, left to right - each is the SAME character
from cell 1, only the leg and arm position changes to match a natural
walking stride, all facing right):

Row 1:
1. "Walk Contact Left" - left foot just touching the ground out in front,
   right leg trailing behind, right arm forward and left arm back
2. "Walk Passing" - legs crossing directly under the body, mid-step,
   arms near the sides passing each other
3. "Walk Push Left" - left leg pushing off behind the body, right foot
   now forward reaching for the ground, arms swapped from cell 1

Row 2:
4. "Walk Contact Right" - right foot just touching the ground out in
   front, left leg trailing behind, left arm forward and right arm back
   (the mirror-opposite stride of cell 1)
5. "Walk Passing Reverse" - legs crossing under the body again, opposite
   arm swing from cell 2
6. "Walk Push Right" - right leg pushing off behind, left foot forward
   reaching for the ground, arms swapped from cell 4

This is a walk-cycle reference sheet: cells 1-3-4-6 in particular must
line up into one continuous, believable walking stride when viewed in
order, the way a real animator's turnaround sheet does - not six
unrelated standing poses. Same character, same colors, same crown, same
proportions in every cell, only the stride stage changes. High detail,
smooth glossy 3D render, centered composition in every cell.
```

Attach `custom_idle.png` as a reference image if your tool supports it,
plus: "Match the exact character design, colors, crown, and art style of
the attached reference image in every cell - this is the same character
in every single frame, only walking."

### The honest note on this one specifically

Six real stride stages is asking more of the consistency than any sheet
so far - if some cells drift (a different crown angle, a slightly
different face), that's expected, not a failure on your end. Send
whatever comes out regardless; I'll use whichever cells are clean and
consistent with each other (even if that ends up being 3 or 4 good ones
instead of all 6) and quietly drop any that don't match, rather than
using a pose that breaks the illusion.

### What this actually gets you, honestly

More walking variety than today's single fixed photo - possibly enough
clean stages to cycle through 3-4 frames per stride instead of 1, which
reads as noticeably smoother motion even though it's still frame-swapping
under the hood, not true continuous movement. For genuinely continuous
motion (a leg that actually swings through space, not steps between
photos), that's what the separate animated vector Ganesh is for - still
mid-build from a few messages ago, happy to finish that alongside this.

---

## UPDATE — fifth sheet: the best possible frame-loop illusion (12 poses)

One honest thing first, since "seamless" came up: no static image sheet
can be truly seamless - that word means continuous, and a sheet is
discrete pictures no matter how many. What genuinely gets closest is what
traditional 2D animation has always done: several real sequential frames
per action, tightly aligned, that loop back to the start cleanly, shown
in fast succession. That's what this sheet is designed for - 4 real
frames each for walking, running, and blessing, built to loop.

```
Generate a single reference sprite sheet: one image, a clean 4-column by
3-row grid of 12 equal cells with thin white gutters between them. Every
cell shows the EXACT SAME character - identical face, crown, colors,
proportions - only the motion stage changes within each row. Character
sheet style, like a professional game animator's cycle sheet. Identical
scale, identical camera height, identical front-facing camera angle,
identical lighting in every cell. A short text label in a simple dark
serif font appears centered directly under each character.

CHARACTER (identical in all 12 cells, no variation): a cute chibi baby
Ganesha (Lord Ganesh / Vinayaka), 3D rendered in a soft glossy
Pixar/Disney-style. Big round elephant head with a gently curled trunk
and large rounded pink elephant ears. Short dark curly brown hair. An
ornate gold crown with a red gem centered and a blue-and-green peacock
feather tucked into the right side. A small tilak mark on the forehead.
Warm tan skin with soft rosy cheeks. Golden-yellow dhoti wrap with a thin
patterned border, gold bracelets and anklets. Small, round, child-like
proportions.

BACKGROUND - identical in all 12 cells: pure flat white, no shadows, no
floor line, even soft studio lighting from the front, no gradient.

Each row is ONE continuous 4-frame loop - frame 4 should flow naturally
back into frame 1 with no jump, the way a looping animation cycle does.

ROW 1 - WALK CYCLE (calm, natural walking pace, facing right):
1. "Walk 1" - left foot planted forward touching the ground, right leg
   trailing behind, right arm forward, left arm back
2. "Walk 2" - legs passing directly under the body, arms near the sides
   mid-swing
3. "Walk 3" - right foot now planted forward, left leg trailing behind,
   left arm forward, right arm back (mirror of frame 1)
4. "Walk 4" - legs passing under the body again, arms mid-swing the
   opposite way from frame 2 - flows back into frame 1

ROW 2 - RUN CYCLE (energetic running, facing right):
5. "Run 1" - front foot striking the ground, back leg bent behind, arms
   pumping hard, leaning forward, excited expression
6. "Run 2" - both feet momentarily off the ground mid-stride, legs
   tucked, peak of the airborne moment
7. "Run 3" - the opposite foot striking the ground, other leg bent
   behind, arms pumping the opposite way (mirror of frame 5)
8. "Run 4" - both feet off the ground again, opposite tuck from frame 6
   - flows back into frame 5

ROW 3 - BLESSING GESTURE (a full raise-and-bless motion):
9. "Bless 1" - starting position, hand resting near the chest, eyes open,
   calm neutral expression, about to begin the gesture
10. "Bless 2" - hand rising, now at shoulder height, palm starting to
    turn forward, eyes still open, a gentle smile forming
11. "Bless 3" - hand fully raised, palm forward in the complete blessing
    gesture, eyes gently closed, warm serene expression, the peak of the
    gesture - a soft golden glow or a few small sparkles near the raised
    hand
12. "Bless 4" - hand lowering back down from the peak, eyes opening
    again, warm lingering smile - flows back into frame 1

Same character, same colors, same crown, same proportions in every cell -
only the motion stage changes. High detail, smooth glossy 3D render,
centered composition in every cell.
```

Attach `custom_idle.png` as a reference image if your tool supports it,
plus: "Match the exact character design, colors, crown, and art style of
the attached reference image in every cell - this is the same character
throughout, only the motion stage changes."

### The same honest note as always, worth repeating once more

12 cells across 3 real motion cycles is the most ambitious ask yet -
expect some drift, and that's fine. Send back whatever comes out even if
only some frames per row are clean and matched; a 3-frame loop from
mostly-consistent cells beats a 4-frame loop where one frame breaks the
character's face. I'll tell you plainly which rows worked and which
didn't once I see it.

### What changes on my side once you send this

Right now the engine picks between at most 2 images per action (or 1). To
actually use 4-frame loops, I'll extend the pose-swap system to cycle
through an array of frames on a proper animation timer (roughly 6-8
frames per second, the same cadence classic sprite animation uses)
instead of just alternating two. This is a real engine change, not just
new pictures - I'll build and test it the same careful way as everything
else here once there are real frames to drive it with.

---

## UPDATE — the definitive prompt (everything learned, one sheet)

This replaces the need to read the four prompts above - it's the
distilled best version, keeping only what proved highest-value across
every attempt so far, sized to stay realistic about consistency risk
(15 cells, not 24+). Use this one.

```
Generate a single reference sprite sheet for a 3D character design: one
image, a precise 5-column by 3-row grid of 15 equal-sized cells separated
by thin white gutters. This is a professional character reference /
turnaround sheet, not a mood board - every cell must show the IDENTICAL
character: same face shape, same eye size and color, same crown, same
peacock feather, same proportions, same skin tone, same outfit colors.
Only the pose, action, and expression are allowed to change between
cells. Identical camera distance, identical camera height, identical
front-facing angle, identical soft studio lighting in every cell, as if
one camera on a tripod photographed the same figure between poses without
moving. A short text label in a simple dark serif font is centered
directly beneath each character, naming that cell exactly as given below.

THE CHARACTER (repeat this identically for every one of the 15 cells - do
not let the design drift):
A cute chibi baby Ganesha (Lord Ganesh / Vinayaka), 3D rendered in a soft
glossy Pixar/Disney-style. A big round elephant head with a gently curled
trunk and large rounded pink elephant ears. Short dark curly brown hair.
An ornate gold crown (mukut) with one red gem centered and a blue-and-
green peacock feather tucked into the right side. A small red tilak mark
on the forehead. Warm tan skin with soft rosy cheeks. A golden-yellow
dhoti wrap with a thin patterned border, gold bracelets on the wrists and
gold anklets. Small, round, child-like proportions throughout every cell.

BACKGROUND (identical in every cell): pure flat white, no shadow, no
floor line, even soft lighting from the front, no gradient, nothing else
in frame but the character.

GRID CONTENT (row by row, left to right):

Row 1 - a short walk cycle, facing right, calm natural pace:
1. "Walk Contact" - left foot planted forward, right leg trailing behind,
   right arm forward and left arm back
2. "Walk Passing" - legs crossing under the body mid-step, arms near the
   sides passing each other
3. "Walk Push" - left leg pushing off behind, right foot reaching forward
   to plant, arms swapped from frame 1
4. "Eyes Open" - standing at rest, hands relaxed at the sides, eyes open
   wide, calm gentle smile, facing forward
5. "Eyes Closed" - the IDENTICAL standing pose, camera framing and hand
   position as frame 4, only the eyes are gently closed - nothing else
   changes from frame 4

Row 2 - running, blessing, and food:
6. "Run Stride" - dynamic running pose, one leg extended back and one
   knee driven forward, arms pumping, leaning into the run, excited
   expression, facing right
7. "Run Airborne" - both feet off the ground mid-stride, legs tucked,
   peak of the running motion, facing right
8. "Blessing" - one hand raised, palm forward, in a complete gentle
   blessing gesture, eyes softly closed, warm serene expression, a subtle
   golden glow near the raised hand
9. "Eating Modak" - sitting cross-legged, both hands holding a golden
   teardrop-shaped modak sweet up near the mouth, mid-bite, joyful eyes
10. "Hungry" - sitting, one hand resting on the belly, eyes glancing
    toward an empty bowl in front, a gentle wistful expression

Row 3 - rest, focus, and reactions:
11. "Meditating" - sitting cross-legged in a lotus position, both palms
    resting together at chest height, eyes closed, serene expression
12. "Sleeping" - lying curled on its side, eyes closed, peaceful, hands
    tucked near the chin
13. "At the Desk" - sitting at a small desk with a laptop open in front,
    both hands near the keyboard, focused calm expression
14. "Celebrating" - both arms thrown up overhead, joyful open-mouthed
    smile, a few small confetti pieces around the character
15. "Riding the Mouse" - sitting on top of a small white pet mouse that
    is walking, arms relaxed or gently holding on, cheerful expression

Every cell: the same character, the same colors, the same crown, the same
proportions - only the pose, action and expression differ. High detail,
smooth glossy 3D render, centered composition, consistent scale.
```

### Attach a reference image - this matters most on this one

If your tool accepts an attached image, attach `custom_idle.png`
(`C:\Users\cc221\AppData\Roaming\DeskPal\custom_idle.png`) and add this
line to the end of the prompt:

```
Match the exact character design, face, crown, colors, and art style of
the attached reference image in every single cell - this is the same
character in all 15 cells, only the pose changes.
```

Without an attached reference, text alone can still drift the face
slightly across 15 cells - expected, not a failure. Send back whatever
comes out; I only need the cells that came out clean and consistent with
each other, and I'll tell you plainly which ones to regenerate if any
look off-model.

### Why this version and not the earlier four

- Frames 1-3 give a real (if short) walk cycle instead of one static pose
- Frames 4-5 are the pixel-matched blink pair - the single highest-value
  pair from everything requested, made a priority this time instead of a
  hopeful afterthought
- Frames 6-7 give running with actual leg extension, not a repeat of the
  same static stride
- Frame 8 is one strong blessing gesture (dropped the 3-variant and
  4-frame versions - one excellent blessing beats three inconsistent ones)
- Frames 9-10 cover the food/hunger request directly
- Frames 11-15 fill in meditating, sleeping, desk work, celebrating and
  the rat - the remaining real triggers already built into DeskPal that
  had no pose yet

Send it over when it's ready.

---

## UPDATE — switched approach: one pose at a time in ChatGPT/DALL-E

Grids were producing inconsistent results, so here's the reliable
alternative for ChatGPT specifically: generate **one image per pose**,
each time **attaching your best existing clean photo** as a reference and
asking ChatGPT to edit/regenerate with only the pose changed. ChatGPT is
noticeably better at "keep this exact character, change this one thing"
than at holding one character consistent across 10+ cells in a single
image - this plays to that strength instead of fighting it.

### The anchor image

Use this one, every time, as the attachment:

```
C:\Users\cc221\AppData\Roaming\DeskPal\custom_idle.png
```

This is your cleanest, already-working reference. Every new pose gets
generated FROM this same attached image, not from a text description
alone - that's what keeps the face, crown, and colors locked.

### The prompt template (copy this, swap only the bracketed part)

```
Using the attached image as the exact reference for the character's
face, crown, colors, and proportions, generate a new image of the SAME
character in this pose: [POSE DESCRIPTION HERE].

Keep the face, crown, peacock feather, skin tone, and outfit colors
identical to the attached image. Only the pose and expression should
change. Plain flat white background, no shadow, same soft studio
lighting and camera framing as the attached image.
```

### Ready-to-use pose descriptions, highest priority first

Paste the template above and swap in one of these each time (one
generation per pose):

```
1. Eyes closed - the exact same seated pose as the reference image, only
   the eyes gently closed, everything else unchanged
2. Standing mid-walk, left foot planted forward, right leg trailing
   behind, arms swinging naturally, facing right
3. Standing mid-walk, right foot planted forward, left leg trailing
   behind, arms swinging the opposite way, facing right (the mirror
   stride of the previous pose)
4. Dynamic running pose, one leg extended back and one knee driven
   forward, arms pumping, leaning into the run, excited expression,
   facing right
5. One hand raised, palm forward, in a complete gentle blessing gesture,
   eyes softly closed, warm serene expression
6. Sitting, one hand resting on the belly, eyes glancing toward an empty
   bowl in front, a gentle wistful hungry expression
7. Both hands holding a golden teardrop-shaped modak sweet up near the
   mouth, mid-bite, joyful expression
8. Sitting cross-legged in a lotus position, both palms resting together
   at chest height, eyes closed, serene meditating expression
9. Lying curled on its side, eyes closed, peaceful, hands tucked near
   the chin, sleeping
10. Both arms thrown up overhead, joyful open-mouthed smile, a few small
    confetti pieces around the character, celebrating
```

### Why this works better than the grid

- ChatGPT only has to track ONE character in ONE pose per generation,
  not juggle 15 at once
- The attached image does the consistency work instead of a paragraph of
  description trying to do it from scratch each time
- If one comes out wrong, you only lose that one - not the whole sheet
- You can literally look at each result before moving to the next, and
  re-roll just that one if it drifts

Send me each result as you get it (one at a time is fine, or a batch
later) and I'll crop, background-remove, and wire each in exactly like
before.

---

## UPDATE — minimal start: 4 frames each for running and blessing

Starting small on purpose: just these two animations, done properly, one
image per frame, each one built from your actual photo as the reference.
Prove this works, then expand using the same method.

### Anchor image - attach this to every single generation

```
d:\charangmail downloads\DeskPal (1)\lord ganesh .png
```

### The template (same as before - swap only the bracketed part)

```
Using the attached image as the exact reference for the character's
face, crown, colors, and proportions, generate a new image of the SAME
character in this pose: [POSE DESCRIPTION HERE].

Keep the face, crown, peacock feather, skin tone, and outfit colors
identical to the attached image. Only the pose and expression should
change. Plain flat white background, no shadow, same soft studio
lighting and camera framing as the attached image.
```

### Running - 4 frames, generate one at a time

```
1. "Run Start" - a coiled, about-to-move stance: knees slightly bent,
   body leaning forward, arms drawn back, eyes forward with excited
   anticipation, feet still close together but weight shifting forward,
   facing right

2. "Run Push" - the first push-off: back leg extending fully behind,
   front leg driving up and forward with a bent knee, arms pumping hard
   in opposite swing, body leaning into the run, facing right

3. "Run Peak" - the airborne peak of the stride: both feet momentarily
   off the ground, front leg fully extended forward, back leg tucked up
   behind, arms at their widest swing, dynamic mid-air energy, facing
   right

4. "Run Land" - landing and settling: front foot planting down flat,
   back leg trailing behind bent, arms starting to relax back toward
   center, slightly forward lean easing off, facing right
```

### Blessing - 4 frames, generate one at a time

```
1. "Bless Rest" - starting position: one hand resting gently near the
   chest, palm facing inward, eyes open, calm neutral expression, about
   to begin the gesture

2. "Bless Half" - the hand rising to about shoulder height, palm turning
   to face forward, eyes still open, a gentle smile beginning to form

3. "Bless Near" - the hand nearly fully raised, palm mostly forward, eyes
   starting to soften and close, warmth building in the expression

4. "Bless Peak" - the hand fully raised overhead or at head height, palm
   completely forward in the finished blessing gesture, eyes gently
   closed, warm serene expression, a soft golden glow or a few small
   sparkles near the raised hand
```

### After you generate these 8

Send them over (one at a time as you go, or all 8 together - either
works). I'll check each one against the others in its set for real
consistency (not just eyeballing it - the same pixel-difference check I
used to verify your last good sheet), crop, remove backgrounds, and wire
a proper 4-frame cycling animation into the engine for running, and the
same for blessing. If any single frame in a set of 4 doesn't match the
others closely enough, I'll tell you exactly which one to regenerate
rather than using a mismatched frame.

---

## UPDATE — same 8 frames, combined into one single image

```
Generate a single reference sprite sheet: one image, a precise 4-column
by 2-row grid of 8 equal-sized cells separated by thin white gutters.
Every cell shows the IDENTICAL character - same face, same crown, same
colors, same proportions - only the pose changes. This is a professional
animation reference sheet, not a mood board: identical camera distance,
identical camera height, identical front-facing angle, identical soft
studio lighting in every cell, as if one camera on a tripod photographed
the same figure between poses without moving. A short text label in a
simple dark serif font is centered directly beneath each character,
naming that cell exactly as given below.

THE CHARACTER (repeat identically in all 8 cells, matching the attached
reference photo exactly - same face, same crown, same peacock feather,
same skin tone, same outfit colors, do not let the design drift):
a cute chibi baby Ganesha (Lord Ganesh / Vinayaka), 3D rendered in a soft
glossy Pixar/Disney-style. A big round elephant head with a gently curled
trunk and large rounded pink elephant ears. Short dark curly brown hair.
An ornate gold crown with a red gem centered and a blue-and-green peacock
feather tucked into the right side. A small tilak mark on the forehead.
Warm tan skin with soft rosy cheeks. A golden-yellow dhoti wrap with a
thin patterned border, gold bracelets and anklets. Small, round,
child-like proportions.

BACKGROUND - identical in all 8 cells: pure flat white, no shadow, no
floor line, even soft studio lighting from the front, no gradient.

Row 1 - RUNNING, a 4-stage cycle, facing right:
1. "Run Start" - a coiled, about-to-move stance: knees slightly bent,
   body leaning forward, arms drawn back, excited anticipation, feet
   still close together but weight shifting forward
2. "Run Push" - the first push-off: back leg extending fully behind,
   front leg driving up and forward with a bent knee, arms pumping hard
   in opposite swing, body leaning into the run
3. "Run Peak" - the airborne peak of the stride: both feet momentarily
   off the ground, front leg fully extended forward, back leg tucked up
   behind, arms at their widest swing, dynamic mid-air energy
4. "Run Land" - landing and settling: front foot planting down flat,
   back leg trailing behind bent, arms starting to relax back toward
   center, forward lean easing off

Row 2 - BLESSING, a 4-stage gesture:
5. "Bless Rest" - one hand resting gently near the chest, palm facing
   inward, eyes open, calm neutral expression, about to begin the gesture
6. "Bless Half" - the hand rising to about shoulder height, palm turning
   to face forward, eyes still open, a gentle smile beginning to form
7. "Bless Near" - the hand nearly fully raised, palm mostly forward, eyes
   starting to soften and close, warmth building in the expression
8. "Bless Peak" - the hand fully raised, palm completely forward in the
   finished blessing gesture, eyes gently closed, warm serene expression,
   a soft golden glow or a few small sparkles near the raised hand

Every cell: the same character, the same colors, the same crown, the
same proportions - only the pose changes, forming two believable 4-stage
motion sequences when read left to right. High detail, smooth glossy 3D
render, centered composition, consistent scale throughout.
```

### Attach the reference photo - important for this one

```
d:\charangmail downloads\DeskPal (1)\lord ganesh .png
```

Add this line at the end of the prompt:

```
Match the exact character design, face, crown, colors, and art style of
the attached reference photo in every one of the 8 cells.
```

### One honest note, briefly

8 cells is a much safer size than the 15-cell attempt that didn't work -
real chance this comes out clean. If a couple of cells still drift, that
's fine - send it anyway and I'll tell you plainly which ones to
individually regenerate using the single-pose prompts above, rather than
starting over.
