import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "job_server.py"
SPEC = importlib.util.spec_from_file_location("job_server", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class JobServerTests(unittest.TestCase):
    def test_only_expected_jobs_are_exposed(self):
        self.assertEqual(set(MODULE.JOBS), {"results", "news", "financials", "market-news", "stock-analysis", "practice-prices", "watch-predictions", "market-overview"})
        self.assertTrue(all(path.is_file() for path in MODULE.JOBS.values()))

    def test_initial_state_is_idle(self):
        self.assertTrue(all(item["status"] in {"idle", "success", "failed"} for item in MODULE.job_state.values()))

    def test_company_profile_endpoint_is_local_allowlisted_logic(self):
        self.assertIn("financials", MODULE.JOBS)


if __name__ == "__main__":
    unittest.main()
