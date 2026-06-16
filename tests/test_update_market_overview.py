import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("market_overview", ROOT / "scripts" / "update_market_overview.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MarketOverviewTests(unittest.TestCase):
    def test_percentage_change(self):
        self.assertEqual(MODULE.percentage_change(110, 100), 10)
        self.assertIsNone(MODULE.percentage_change(110, None))

    def test_normalizes_nse_component(self):
        row = MODULE.normalize_component({"symbol": "ABC", "meta": {"companyName": "ABC Limited"}, "lastPrice": 50, "pChange": 2})
        self.assertEqual(row["company"], "ABC Limited")
        self.assertEqual(row["pChange"], 2)

    def test_includes_indices_and_metals(self):
        types = {item["type"] for item in MODULE.INSTRUMENTS}
        names = {item["name"] for item in MODULE.INSTRUMENTS}
        self.assertTrue({"index", "sector", "metal"}.issubset(types))
        self.assertTrue({"Nifty 50", "Sensex", "Gold", "Silver"}.issubset(names))
        self.assertIn("NIFTY 50", MODULE.NSE_COMPONENT_CSV)


if __name__ == "__main__":
    unittest.main()
