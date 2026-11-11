import json
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_card as bc  # noqa: E402

D = date(2026, 11, 11)


def days(*spec):
    """spec: counts ending today, oldest first."""
    return {D - timedelta(days=len(spec) - 1 - i): c for i, c in enumerate(spec)}


class Streaks(unittest.TestCase):
    def test_current_includes_today(self):
        self.assertEqual(bc.compute_streaks(days(0, 1, 2, 3), D), (3, 3))

    def test_empty_today_does_not_break_streak(self):
        self.assertEqual(bc.compute_streaks(days(1, 1, 1, 0), D), (3, 3))

    def test_gap_resets_current_not_best(self):
        self.assertEqual(bc.compute_streaks(days(1, 1, 1, 1, 0, 0, 1), D), (1, 4))

    def test_no_activity(self):
        self.assertEqual(bc.compute_streaks({}, D), (0, 0))


class Formatting(unittest.TestCase):
    def test_short(self):
        self.assertEqual(bc.short(910_980_487), "911M")
        self.assertEqual(bc.short(16_514_463), "16.5M")
        self.assertEqual(bc.short(2_000_000_000), "2B")

    def test_milestone(self):
        self.assertEqual(bc.milestone(910_980_487), 1_000_000_000)
        self.assertEqual(bc.milestone(1_000_000_000), 2_000_000_000)
        self.assertEqual(bc.milestone(3), 5)

    def test_px_width(self):
        # five-wide glyphs plus one column of spacing between them
        self.assertEqual(bc.px_width("AB", 2), 22)
        self.assertEqual(bc.px_width("", 3), 0)

    def test_clip(self):
        self.assertEqual(bc.clip("short", 12, 500), "short")
        self.assertTrue(bc.clip("x" * 100, 12, 100).endswith("…"))


def fixture():
    window = [(D - timedelta(days=i), i % 4) for i in range(29, -1, -1)]
    return {
        "now": datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
        "today": D,
        "window": window,
        "total": 916,
        "streak": (3, 13),
        "langs": [("TypeScript", 40.8, "#3178c6"), ("Python", 25.6, "#3572A5")],
        "langs_note": "22 repos",
        "pinned": [{
            "nwo": "a/b", "name": "b <&>", "badge": "winner", "blurb": "does things",
            "lang": "typescript", "lang_color": "#3178c6", "stars": 2, "pushed": D,
        }],
        "tokens": {
            "total": 910_980_487, "fresh": 54_291_064, "since": "2026-01-18",
            "updated": "2026-11-11T18:07:44Z",
            "by_tool": {"claude_code": {"total": 894_466_024, "fresh": 1},
                        "codex": {"total": 16_514_463, "fresh": 1}},
        },
    }


class Render(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "data" / "profile.json").read_text())
        self.stack = json.loads((ROOT / "data" / "stack.json").read_text())
        self.icons = json.loads((ROOT / "data" / "icons.json").read_text())

    def test_renders_well_formed_svg(self):
        for motion in (True, False):
            svg = bc.render(fixture(), self.profile, self.stack, self.icons, motion=motion)
            root = ET.fromstring(svg)
            self.assertTrue(root.tag.endswith("svg"))
            self.assertEqual(root.get("width"), str(bc.W))

    def test_escapes_repo_text(self):
        svg = bc.render(fixture(), self.profile, self.stack, self.icons)
        self.assertIn("b &lt;&amp;&gt;", svg)

    def test_static_has_no_animation(self):
        svg = bc.render(fixture(), self.profile, self.stack, self.icons, motion=False)
        self.assertNotIn("<animate", svg)

    def test_optional_sections_drop_out(self):
        d = fixture()
        d["tokens"] = None
        d["pinned"] = []
        svg = bc.render(d, self.profile, self.stack, self.icons)
        self.assertNotIn("AI TOKEN SPEND", svg)
        self.assertNotIn("PINNED", svg)

    def test_every_stack_item_has_a_logo(self):
        for group in self.stack:
            for item in group["items"]:
                self.assertTrue("mono" in item or item["name"] in self.icons, item["name"])


if __name__ == "__main__":
    unittest.main()
