# DeskPal — Ganesh animation design, v3

Status: design proposal, September 19, 2026. No runtime code or live assets changed in this round.

The two generated boards are pose concepts, not playback-ready sprite sheets. Their poses establish the expressions and story beats. They still need matching camera, scale, registration, transitions, and in-between drawings before use in DeskPal. The first board's standing pose includes a raised hand; the production neutral pose below must have relaxed arms. Its mouth-catch concept still shows the sweet above the trunk; the production contact frames must show entry into the mouth. These differences are not accepted as finished animation.

## Visual direction

Use `lord ganesh .png` as the primary identity reference: the same baby face, peach skin, pink ears, brown curls, red tilak, gold crown and red jewel, peacock feather, yellow dhoti with red trim, jewelry, and two arms. Preserve these details across every sheet. The personality is curious, playful, reassuring, and gentle.

Premium motion comes from anticipation, clear contact poses, consistent proportions, and settling after an action. Increasing frame rate or adding duplicate drawings alone will not improve the existing motion. AI concept grids are suitable for exploring poses; production needs individually reviewed sequential frames or animation from a consistent rig.

Keep the white-background master sheets the user requested. Export a separate transparent runtime atlas; white must never be drawn around the desktop character. No cell borders, labels, drop shadows, or adjacent sprite fragments belong in runtime crops.

## The concept boards

- [Personality concepts](01-personality-concepts.png): 4 columns × 3 rows, read left to right. Standing greeting; breathing; one-eye peek; modak jump; mouth-catch idea; happy tummy pat; window-edge peek; thirsty slump; drinking; blessing; studying; mouse riding.
- [Play and jump concepts](02-play-and-jump-concepts.png): 4 columns × 2 rows. Meet mouse; chase; gentle catch; cuddle; jump anticipation; takeoff; apex; landing.

The window card in the peek concept only explains occlusion. It must not be baked into the character artwork. Mouse sizes in the play and riding concepts are illustrative: establish two deliberately different scales, small play companion and larger ride companion, and use a clear transition rather than switching size during motion.

## Production sheet plan

All frame numbers below are zero-based. Counts are planned distinct drawings, not assets already created. Ten character sheets contain 200 planned drawings, plus separate prop and mouse atlases. The frames may be split into smaller atlases for runtime use.

| Sheet | Planned frames | Grid | Timing and use |
|---|---:|---|---|
| 01 · Standing & blink | 16 | 4 × 4 | 12 quiet idle frames over 3 seconds; 4 blink inserts |
| 02 · Breathe & peek | 16 | 4 × 4 | 12 phase-controlled breathing frames; 4 one-eye-peek inserts |
| 03 · Modak jump & catch | 32 | 4 × 8 | One 4.2-second story; separate animated sweet |
| 04 · Window-edge peek | 12 | 4 × 3 | 2.5–3 seconds; left/right variants |
| 05 · Thirst, drink & recover | 24 | 4 × 6 | 8 tired/fall frames; 12 drink frames; 4 recovery frames |
| 06 · Blessing | 20 | 4 × 5 | 3 seconds, then a gentle hold or return to idle |
| 07 · Studying | 24 | 4 × 6 | 6 enter, 8 reading, 6 page-turn, 4 exit frames |
| 08 · Mouse play | 24 | 4 × 6 | Greeting, chase cycle, gentle catch, cuddle, release |
| 09 · Mouse riding | 16 | 4 × 4 | 4 mount, 8 trot, 4 dismount frames |
| 10 · Happy jump | 16 | 4 × 4 | One 1.3-second jump with anticipation and landing |

## 01 — Standing with personality

Frames 0–2: neutral stand with relaxed arms and balanced feet. 3–5: tiny inhalation, trunk tip lifts slightly. 6–8: soft exhalation and ear settle. 9–11: ease back to neutral with identical foot anchors. Frames 12–15: eyelids lower, close, half-open, open; composite or substitute without changing the head angle.

Loop 0–11 slowly, vary blink timing independently. A blink must not restart the whole-body idle cycle. Use occasional gaze changes rather than continuous bouncing. This supplies the true standing emote and the shared entry/exit pose for other actions.

## 02 — Breathing with a mischievous one-eye peek

Enter a seated lotus pose. Frames 0–5 gently expand chest and tummy during inhale; crown and head remain stable. Frames 6–11 relax during exhale. Drive these poses from the existing breathing session's phase, not an unrelated fixed animation timer. Holds use a still pose with only slight secondary motion.

Frames 12–15 are a short optional eye overlay/pose insert: open one eye halfway, glance toward the cursor, smile, close again. Show it once during a suitable pause or between rounds, not on every inhale. It must not change the breathing countdown or interrupt the session. Start/end transitions stand → sit and sit → stand are separate short transition clips if needed.

## 03 — Jump, catch a modak, happy tummy

Use a cream-gold, pleated, pointed modak consistently. The existing round laddu is a different sweet and should remain a separate emote. Use one visible modak at a time.

| Frames | Story beat | Duration | Prop/contact rule |
|---|---|---:|---|
| 0–3 | Hold modak; glance at it; bend knees | 450 ms | Attached to the hand anchor |
| 4–7 | Wind up; toss; begin takeoff | 350 ms | Detach sweet at the release event |
| 8–11 | Rise; track the sweet; ears lag behind | 350 ms | Sweet follows its own upward arc |
| 12–15 | Reach apex; open mouth; sweet begins falling | 450 ms | Sweet and body have separate trajectories |
| 16–19 | Mouth aligns under sweet; catch; land | 450 ms | Sweet enters mouth at the catch event |
| 20–23 | Close mouth; chew; swallow | 700 ms | Hide separate sweet after mouth contact |
| 24–27 | Small tummy bounce; delighted hand pat | 650 ms | No sweet visible through the body |
| 28–31 | Satisfied smile; settle to standing | 800 ms | Return to the common idle anchor |

Total: 4.2 seconds. The “falls into his stomach” idea reads as mouth catch → swallow → tummy bounce, with no transparent anatomy. Keep the moment of contact visible; do not make the modak teleport from the air to the hand or stomach. Animate the prop along a continuous curved path, with an explicit release point and a mouth catch anchor. The body jump may be lower than the sweet's arc.

The complete clip begins holding the sweet, unlike the existing sequence that starts with it already airborne. Land softly before the long chew/satisfaction hold. A subtle sparkle at the tummy pat may reinforce the joke without obscuring the character.

## 04 — Peeking from a window edge

Frames 0–2: ear, crown, and fingertips appear. 3–5: half the head emerges. 6–8: a blink, curious head tilt, one-eye peek. 9–11: smile and retreat.

Prepare left and right compositions. Only show the visible portion of the sprite through a clip/mask; do not attach a white rectangular card to the sprite. Stay away from close buttons, typing fields, and menus. Suppress during dragging, full-screen activity, and breathing. Offer an opt-in “Window peek” setting with a long randomized interval.

Implementation distinction: the existing app can be extended to follow the active window's rectangle; that is not the same as identifying individual browser tabs. A true peek behind an actual tab needs browser integration or a dedicated visual tab edge inside DeskPal's own UI. Phase one should use window edges and describe them accurately.

## 05 — Thirsty little slump, drink, recover

Frames 0–2: drooping ears and tired eyes, one hand on tummy. 3–5: knees soften and he lowers himself. 6–7: gentle seated sideways flop, one hand supporting the head. Make the “fall down” a soft cartoon movement, not a painful or frightening collapse.

Hold a calm seated tired pose while the water reminder waits. Frames 8–11: notice and lift a blue cup. 12–15: drink with trunk curling aside and a visible rim contact. 16–19: lower cup and brighten expression. 20–23: stand and smile. Trigger the drink/recovery after “Drank it”; snooze dismisses the tired pose gracefully. Do not repeat the collapse while the reminder remains open or treat it as a statement about the user's health.

Cup and water glint are separate props. Their anchors follow the hand. Use the same cup size through the entire sequence.

## 06 — Warm, deliberate blessing

Frames 0–3: settle and turn attention toward the user. 4–7: hand rises smoothly from chest level. 8–11: palm faces outward, fingers natural, soft eye close. 12–15: peaceful smile and a held blessing; one small pulse of gold light behind the palm. 16–19: open eyes and gently lower hand.

Keep the palm, trunk, crown, and face unobstructed. A quiet hold sells the blessing better than repeated waving or confetti. Use for the Blessing emote, completion of breathing, or a chosen success moment. Do not mirror a finished blessing clip if that changes the intended blessing hand; make a separate view when needed.

## 07 — Studying beside you

Frames 0–5: sit and open book on lap. 6–13: follow lines with the eyes, tiny finger movement, thoughtful nod, blink. 14–19: lift and turn one page, settle it flat. 20–23: close book and return to rest.

During a focus session, loop reading and use page-turn occasionally. Do not reopen/close the book every loop. Keep book pages visually plain or subtly marked; tiny AI-generated text will flicker. On focus completion, exit reading before celebration. Anchor the book to the lap, with the page as a separate hinged layer.

## 08 — Play and chase the mouse

Frames 0–3: kneel and offer a hand; mouse sniffs. 4–11: genuine two-sided running gait for a playful chase. 12–15: slow down and cup hands gently around the mouse. 16–19: cuddle and laugh. 20–23: lower hands and release the mouse.

Animate the small mouse separately so it can lead by a variable distance. Use an 8-frame mouse run and 4-frame sniff/sit atlas. Keep both actors inside the desktop work area. The chase follows a bounded route and ends at an intentional catch point; never grab the mouse by its tail. Cancel movement cleanly when the user grabs Ganesh. Do not let actors separate across monitors.

## 09 — Riding the mouse

Use the familiar mouse identity at the deliberately larger ride scale seen in the concept. Frame 0–3: Ganesh approaches and settles onto its back. 4–11: mouse trot with alternating leg contact; Ganesh torso follows with small delayed bounce, hands balanced, trunk and feather trailing. 12–15: decelerate, step off, settle.

Export aligned mouse and rider layers or a fully registered combined clip. The rider's seat anchor stays attached to the mouse's back every frame; no hovering or sliding. Trot is a loop; mounting and dismounting are one-shots. Leftward travel requires a left-facing variant; check feather and jewelry orientation before deciding whether mirroring is acceptable.

## 10 — Happy jump

Frames 0–3: knees bend, arms sweep down (240 ms). 4–6: push off with both feet (140 ms). 7–9: open joyful pose at apex (260 ms). 10–12: descend with arms balancing (180 ms). 13–15: soft landing and recover (480 ms). Total: 1.3 seconds.

Feet push off the shared floor line; the whole actor follows a continuous jump arc. Keep character size unchanged in the air. Ears, trunk, and feather settle a little later than the torso. This clip works without a modak or mouse and should stay separately accessible as “Happy jump”.

## Registration and export specification

- Default frame canvas: 512 × 512 px. Mouse-play and ride frames: 768 × 512 px to fit both actors, with the same vertical character scale. Do not independently scale every frame to fill its cell.
- Default ground anchor: (256, 464); wide frame anchor: (384, 464). For standing clips, feather tip sits around y=112, leaving overhead room for a jump or thrown sweet. Anchors are starting targets to verify against the approved standing model, not measurements from the concept grids.
- Allocate prop motion and jump headroom before painting. If needed, enlarge the full sequence's canvas once; never crop or resize isolated frames differently.
- Pack atlases deterministically with 16 px empty gutters. Gutters are external to frame rectangles; the runtime uses exact rectangles from metadata. White master backgrounds are display/export copies, not source pixels for the desktop compositor.
- Work at final approved scale with locked camera, light direction, palette, trunk curl, and crown proportions. Use one standing and one seated model sheet as references for every batch.
- Keep layers for Ganesh body, optional eye expression, modak, cup, book/page, mouse, and effects. Store hand, mouth, seat, floor, and peek-edge anchors in frame metadata.
- Master cutouts: straight-alpha RGBA with clean edge colors. Browser preview can use smooth alpha. Current Windows Tk color-key output needs a separately derived binary-alpha export after downscaling to display size; partial alpha blended over magenta caused the earlier halo. Do not destroy the smooth master to make the Tk version.
- Runtime render target: 30 updates/sec with time-based movement. Use 12–24 distinct drawings/sec where movement warrants it, plus intentional held poses. Do not claim a 30-fps timer turns a few static poses into cinematic animation.
- A visible bounce, screen translation, blink, and prop arc can run independently from pose selection. Do not crossfade incompatible silhouettes to hide missing in-betweens: that creates ghost limbs.

## Planned app behavior

Priority: user dragging > active breathing/focus session > acknowledged reminder action > manual emote > idle play. A manual emote can interrupt idle play, but a random chase or peek must not interrupt a guided breathing session. User input cancels any scheduled movement or stale completion callback.

Settings → Emotes should list: Standing, Breathe, Meditation peek, Modak jump & catch, Window peek, Thirsty slump, Drink water, Blessing, Study, Play with mouse, Ride mouse, Happy jump. Add Replay and Stop, with an optional Loop toggle only for safe loopable clips. One-shot jump/eating clips return to the prior appropriate idle, seated, or focus pose.

Automatic triggers: breathing phase drives breathing; water reminder plays the slump; “Drank it” drives drinking/recovery; focus starts study; focus completion exits study then performs happy jump; occasional opt-in idle events can choose mouse play or window peek. Modak and riding are initially manual to avoid surprising movement during work.

## Production order and review gates

1. Lock the neutral standing/seated model and the modak, cup, book, and mouse designs. Confirm neutral arms-down standing and true mouth contact instead of accepting the concept deviations noted above.
2. Produce standing/blink and breathing/peek first. Validate the shared anchors and transparent export on actual dark and light desktops.
3. Produce modak sequence and blessing. Review contact and choreography at full size and at 130 px character height.
4. Produce water and study loops, including enter/exit states. Check reminder/session interruption behavior.
5. Produce mouse play, ride, happy jump, and the edge-peek clip. Test screen boundaries and occlusion.

Generate or draw only 4–8 adjacent key poses per batch from the approved model. Build intermediate poses deliberately. Assemble the planned larger atlas only after registration review; do not rely on a generator to produce 32 perfectly registered animation frames in one image.

Before implementation acceptance: every referenced file exists and decodes; counts match metadata; consecutive frames show intentional change; foot/seat contact has no unwanted drift; correct left/right gait; no clipped crown, tail, or airborne sweet; no grid remnants; no magenta or white fringe against dark/light desktops; exactly one sweet before mouth catch and none after; smooth loop seam; stable focus/breathing timers; interrupt/resume tests; zero new callback exceptions after repeated playback. Visual quality and runtime correctness must be checked separately.

## Deliverables in this design round

Two visual concept PNGs, this production plan, a machine-readable planning manifest, and the exact image-generation prompts. Concept images were generated with the built-in image tool. The proposed 200-frame production pack has not been rendered or installed into DeskPal.
