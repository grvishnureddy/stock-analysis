import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_stock_analysis.py"
SPEC = importlib.util.spec_from_file_location("update_stock_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateStockAnalysisTests(unittest.TestCase):
    def candles(self, rising=True):
        rows = []
        for index in range(220):
            close = 100 + index if rising else 320 - index
            rows.append({"date": f"2026-01-{(index % 28) + 1:02d}", "open": close - 1, "high": close + 2, "low": close - 2, "close": close, "volume": 1000 + index})
        return rows

    def test_rising_prices_generate_bullish_signal(self):
        result = MODULE.analyze("ABC", "ABC Limited", "NSE", self.candles(True))
        self.assertEqual(result["signal"], "Bullish")
        self.assertGreater(result["momentum20d"], 0)
        self.assertEqual(len(result["chart"]), 90)

    def test_falling_prices_generate_bearish_signal(self):
        result = MODULE.analyze("ABC", "ABC Limited", "NSE", self.candles(False))
        self.assertEqual(result["signal"], "Bearish")
        self.assertLess(result["momentum20d"], 0)
        self.assertEqual(result["chart"][-1]["close"], 101)


if __name__ == "__main__":
    unittest.main()
