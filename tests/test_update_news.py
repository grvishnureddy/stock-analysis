import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_news.py"
SPEC = importlib.util.spec_from_file_location("update_news", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateNewsTests(unittest.TestCase):
    def test_normalizes_nse_announcement(self):
        row = MODULE.normalize_news(
            {
                "symbol": "ABC",
                "sm_name": "ABC Limited",
                "desc": "Investor presentation",
                "an_dt": "06-Jun-2026 10:30:00",
                "attchmntFile": "/corporate/abc.pdf",
            }
        )
        self.assertEqual(row["publishedAt"], "2026-06-06T10:30:00")
        self.assertEqual(row["url"], "https://www.nseindia.com/corporate/abc.pdf")
        self.assertEqual(row["headline"], "Investor presentation")

    def test_rejects_incomplete_news(self):
        self.assertIsNone(MODULE.normalize_news({"symbol": "ABC", "desc": "Missing company and date"}))

    def test_merge_deduplicates_news(self):
        item = {
            "company": "ABC Limited",
            "symbol": "ABC",
            "exchange": "NSE",
            "publishedAt": "2026-06-06T10:30:00",
            "type": "announcement",
            "headline": "Investor presentation",
            "summary": "",
            "url": "",
        }
        self.assertEqual(MODULE.merge_rows([item], [item], date(2026, 6, 1)), [item])


if __name__ == "__main__":
    unittest.main()
