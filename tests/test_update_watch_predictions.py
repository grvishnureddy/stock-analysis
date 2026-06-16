import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("watch_predictions", ROOT / "scripts" / "update_watch_predictions.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WatchPredictionTests(unittest.TestCase):
    def test_social_and_rumor_items_are_gossip(self):
        self.assertTrue(MODULE.is_gossip({"platform": "social", "title": "Strong outlook"}))
        self.assertTrue(MODULE.is_gossip({"platform": "news", "title": "Unconfirmed takeover buzz"}))
        self.assertFalse(MODULE.is_gossip({"platform": "news", "title": "Company wins contract"}))

    def test_direction_uses_clear_thresholds(self):
        self.assertEqual(MODULE.direction(3), "Positive watch")
        self.assertEqual(MODULE.direction(-3), "Negative watch")
        self.assertEqual(MODULE.direction(0), "Neutral watch")

    def test_risk_words_score_negatively(self):
        self.assertLess(MODULE.sentiment_score("fraud probe and penalty", "risk"), 0)
        self.assertGreater(MODULE.sentiment_score("wins major contract", "contract"), 0)


if __name__ == "__main__":
    unittest.main()
