import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_financials.py"
SPEC = importlib.util.spec_from_file_location("update_financials", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateFinancialsTests(unittest.TestCase):
    def test_normalizes_financial_summary(self):
        row = MODULE.normalize({"symbol": "ABC", "companyName": "ABC Limited", "periodEnded": "31-Mar-2026", "netProfit": "1,250.5", "totalIncome": "8000"})
        self.assertEqual(row["profitLoss"], "1250.5")
        self.assertEqual(row["revenue"], "8000")
        self.assertEqual(row["periodEnded"], "2026-03-31")

    def test_keeps_latest_company_period(self):
        old = {"exchange": "NSE", "symbol": "ABC", "periodEnded": "2025-12-31", "company": "ABC"}
        new = {"exchange": "NSE", "symbol": "ABC", "periodEnded": "2026-03-31", "company": "ABC"}
        self.assertEqual(MODULE.merge_latest([old, new]), [new])


if __name__ == "__main__":
    unittest.main()
