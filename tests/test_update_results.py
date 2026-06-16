import importlib.util
import unittest
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_results.py"
SPEC = importlib.util.spec_from_file_location("update_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateResultsTests(unittest.TestCase):
    def test_normalizes_nse_event(self):
        row = MODULE.normalize(
            {
                "symbol": "EXAMPLE",
                "company": "Example Limited",
                "bm_date": "10-Jul-2026",
                "purpose": "Financial Results/Dividend",
            },
            "NSE",
            True,
        )
        self.assertEqual(row["company"], "Example Limited")
        self.assertEqual(row["symbol"], "EXAMPLE")
        self.assertEqual(row["date"], "2026-07-10")
        self.assertEqual(row["status"], "confirmed")
        self.assertEqual(row["verificationLevel"], "official-exchange")

    def test_ignores_non_result_nse_event(self):
        row = MODULE.normalize(
            {"symbol": "EXAMPLE", "company": "Example Limited", "date": "2026-07-10", "purpose": "Fund raising"},
            "NSE",
            True,
        )
        self.assertIsNone(row)

    def test_new_row_replaces_previous_duplicate(self):
        previous = [{"company": "Old", "symbol": "ABC", "exchange": "NSE", "date": "2026-07-10", "quarter": "Q1 FY27", "status": "estimated"}]
        latest = [{"company": "New", "symbol": "ABC", "exchange": "NSE", "date": "2026-07-10", "quarter": "Q1 FY27", "status": "confirmed"}]
        merged = MODULE.merge_rows(latest, previous, date(2026, 6, 1))
        self.assertEqual(merged, latest)

    def test_fallback_without_explicit_status_is_estimated(self):
        row = MODULE.normalize({"symbol": "ABC", "company": "ABC Limited", "date": "2026-07-10"}, "BSE", False, "fallback")
        self.assertEqual(row["status"], "estimated")
        self.assertEqual(row["verificationLevel"], "external-feed")


if __name__ == "__main__":
    unittest.main()
