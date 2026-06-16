import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_company_fundamentals.py"
SPEC = importlib.util.spec_from_file_location("update_company_fundamentals", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateCompanyFundamentalsTests(unittest.TestCase):
    def test_local_name_removes_xml_namespace(self):
        self.assertEqual(MODULE.local_name("{example}ProfitLossForPeriod"), "ProfitLossForPeriod")

    def test_cache_path_uses_exchange_and_symbol(self):
        self.assertEqual(MODULE.cache_path("NSE", "POWERGRID").name, "NSE-POWERGRID.json")

    def test_useful_data_rejects_empty_failed_payload(self):
        self.assertFalse(MODULE.has_useful_data({"valuation": {}, "shareholding": [], "quarterlyHistory": []}))
        self.assertTrue(MODULE.has_useful_data({"valuation": {}, "shareholding": [{"publicPercent": "50"}], "quarterlyHistory": []}))
        self.assertTrue(MODULE.has_useful_data({"valuation": {}, "shareholding": [], "quarterlyHistory": [], "priceHistory": [{"date": "2026-01-01", "close": 100}]}))

    def test_five_year_chart_url_is_configured(self):
        self.assertIn("range=5y", MODULE.YAHOO_FIVE_YEAR_CHART)
        self.assertIn("interval=15m", MODULE.YAHOO_INTRADAY_CHART)

    def test_merge_preserves_last_known_good_data(self):
        original_cache = MODULE.CACHE_DIR
        with tempfile.TemporaryDirectory() as directory:
            MODULE.CACHE_DIR = Path(directory)
            previous = {"company": "Example", "symbol": "EXAMPLE", "exchange": "NSE", "valuation": {"lastPrice": 100}, "priceHistory": [{"date": "2026-01-01", "close": 100}]}
            MODULE.cache_path("NSE", "EXAMPLE").write_text(json.dumps(previous), encoding="utf-8")
            merged = MODULE.merge_cached_data({"company": "Example", "symbol": "EXAMPLE", "exchange": "NSE", "valuation": {"lastPrice": None}, "priceHistory": [], "errors": ["source failed"]})
            self.assertEqual(merged["valuation"]["lastPrice"], 100)
            self.assertEqual(len(merged["priceHistory"]), 1)
        MODULE.CACHE_DIR = original_cache


if __name__ == "__main__":
    unittest.main()
