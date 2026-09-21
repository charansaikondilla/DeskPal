import math
from pathlib import Path
import unittest

from modak_scene import Story


class StoryTests(unittest.TestCase):
    def ready(self, story):
        for _ in range(1560):
            story.update(1/60)
        self.assertEqual(story.state, "ready")
        self.assertEqual(story.owner, "rat")

    def test_complete_chase_at_multiple_scales_and_origins(self):
        for area, scale, margin in [((0,0,1920,1080),1,190), ((-1920,0,1920,1080),1.5,280),
                                    ((0,0,1024,768),.75,140)]:
            with self.subTest(area=area, scale=scale):
                s = Story(area, margin, scale)
                self.assertFalse(s.begin_chase())
                self.ready(s)
                self.assertTrue(s.begin_chase())
                self.assertFalse(s.begin_chase())
                states = set()
                previous = s.rx, s.ry, s.gx, s.gy
                for _ in range(7500):
                    s.update(1/60)
                    states.add(s.state)
                    for value in (s.rx,s.ry,s.gx,s.gy,s.mx,s.my):
                        self.assertTrue(math.isfinite(value))
                    self.assertGreaterEqual(s.rx, area[0]+20)
                    self.assertLessEqual(s.rx, area[0]+area[2]-20)
                    self.assertGreaterEqual(s.gx, area[0]+20)
                    self.assertLessEqual(s.gx, area[0]+area[2]-20)
                    self.assertLessEqual(s.ry, area[1]+area[3])
                    if s.state == "chase":
                        self.assertGreaterEqual(math.dist((s.rx,s.ry),(s.gx,s.gy)),90*scale)
                        overlap = (abs(s.rx-s.gx) < 100*scale and
                                   s.ry > s.gy-150*scale and s.ry-50*scale < s.gy)
                        self.assertFalse(overlap, "Actor rectangles overlap before catch")
                    self.assertLess(math.dist((s.rx,s.ry),previous[:2]),20*scale)
                    if s.owner == "rat":
                        self.assertEqual((s.mx,s.my),s.paw())
                    previous = s.rx,s.ry,s.gx,s.gy
                    if s.state == "done":
                        break
                self.assertEqual(states, {"chase","catch","share","done"})
                self.assertEqual(s.chase,120)

    def test_waits_for_button_without_auto_start(self):
        s = Story((0,0,1920,1080),190)
        self.ready(s)
        for _ in range(1800):
            s.update(.1)
        self.assertEqual(s.state,"ready")
        self.assertEqual(s.chase,0)

    def test_too_small_display_has_clear_error(self):
        with self.assertRaisesRegex(ValueError,"too narrow"):
            Story((0,0,400,400),190)


if __name__ == "__main__":
    unittest.main()
