import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_company_news.py"
SPEC = importlib.util.spec_from_file_location("update_company_news", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateCompanyNewsTests(unittest.TestCase):
    def test_analyze_story_classifies_contract_and_risk(self):
        contract = MODULE.analyze_story({"title": "ABC wins major contract", "summary": "", "url": "https://a.test", "publishedAt": "2026-01-01"})
        risk = MODULE.analyze_story({"title": "ABC receives tax demand notice", "summary": "", "url": "https://b.test", "publishedAt": "2026-01-01"})
        self.assertEqual(contract["category"], "contract")
        self.assertEqual(risk["category"], "risk")

    def test_search_urls_cover_six_months(self):
        urls = MODULE.search_urls("Coforge Limited", "COFORGE")
        self.assertEqual(len(urls), 3)
        self.assertTrue(all("news.google.com/rss/search" in url for url in urls))

    def test_cache_path_uses_exchange_and_symbol(self):
        self.assertEqual(MODULE.cache_path("NSE", "COFORGE").name, "NSE-COFORGE.json")


if __name__ == "__main__":
    unittest.main()
