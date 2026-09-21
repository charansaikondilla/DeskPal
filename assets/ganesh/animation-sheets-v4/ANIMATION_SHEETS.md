# Ganesh animation sheets v4

These are white-background master sheets for visual review and frame planning.
They are not yet transparent runtime atlases. Keep them separate from the
desktop-ready PNG frames until each pose has been reviewed and cut cleanly.

## 01-personality-sprite-sheet.png

4 columns × 4 rows, read left to right and top to bottom.

1. Neutral stand
2. Neutral stand, small breath
3. Blink closed
4. Blink open
5. Blink closed / idle variation
6. Idle recovery
7. Meditation inhale
8. Meditation exhale
9. One-eye peek
10. Friendly wave
11. Blessing hand raise
12. Blessing hold
13. Study with book
14. Thirsty seated slump
15. Drink water
16. Happy tummy-pat / satisfied pose

## 02-mouse-play-happy-jump-sprite-sheet.png

4 columns × 4 rows, read left to right and top to bottom.

1. Kneel and greet mouse
2. Mouse sniffs hand
3. Chase pose one
4. Chase pose two
5. Gentle catch
6. Cuddle
7. Release
8. Settle with mouse
9. Happy-jump anticipation
10. Deep knee bend
11. Takeoff
12. Rise
13. Apex
14. Descend
15. Soft landing
16. Standing recovery

## Runtime acceptance before installation

- Cut each cell into one transparent PNG with no white background, grid line,
  or neighbouring sprite fragment.
- Keep a fixed 512 × 512 frame canvas and use the same ground anchor.
- Verify the crown, feather, ears, mouse tail, and airborne hands are never
  clipped.
- Review all frames against light and dark desktops before adding them as
  `custom_*.png` emote frames.
