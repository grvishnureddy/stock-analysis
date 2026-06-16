import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_practice_prices.py"
SPEC = importlib.util.spec_from_file_location("update_practice_prices", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PracticePricesTests(unittest.TestCase):
    def test_output_paths_are_in_data_directory(self):
        self.assertEqual(MODULE.OUTPUT.parent, ROOT / "data")
        self.assertEqual(MODULE.STATUS.parent, ROOT / "data")


if __name__ == "__main__":
    unittest.main()
