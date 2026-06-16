import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "update_market_news.py"
SPEC = importlib.util.spec_from_file_location("update_market_news", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdateMarketNewsTests(unittest.TestCase):
    def test_market_story_scores_higher_for_market_keywords(self):
        market = {"source": "A", "platform": "news", "title": "Nifty stock market results", "summary": "", "url": "https://a.test/1", "publishedAt": MODULE.datetime.now(MODULE.timezone.utc).isoformat()}
        general = {"source": "B", "platform": "news", "title": "General morning update", "summary": "", "url": "https://b.test/1", "publishedAt": market["publishedAt"]}
        scored = MODULE.score([general, market])
        self.assertEqual(scored[0]["title"], market["title"])

    def test_clean_removes_html(self):
        self.assertEqual(MODULE.clean("<b>Market</b> update"), "Market  update")

    def test_company_specific_story_is_prioritized(self):
        now = MODULE.datetime.now(MODULE.timezone.utc).isoformat()
        company = {"company": "Coforge Limited", "symbol": "COFORGE", "exchange": "NSE"}
        stock = {"source": "A", "platform": "news", "title": "Coforge wins major contract", "summary": "", "url": "https://a.test/stock", "publishedAt": now}
        broad = {"source": "B", "platform": "news", "title": "Nifty stock market outlook", "summary": "", "url": "https://b.test/market", "publishedAt": now}
        scored = MODULE.score([broad, stock], [company])
        self.assertEqual(scored[0]["matchedCompany"]["symbol"], "COFORGE")
        self.assertEqual(scored[0]["impact"], "contract")

    def test_ambiguous_word_symbol_does_not_match(self):
        company = {"company": "Oil India Limited", "symbol": "OIL", "exchange": "NSE"}
        self.assertIsNone(MODULE.company_match("Markets fall as oil prices rise", [company]))

    def test_company_name_matches_without_symbol(self):
        company = {"company": "Yes Bank Limited", "symbol": "YESBANK", "exchange": "NSE"}
        self.assertEqual(MODULE.company_match("Yes Bank receives tax demand notice", [company]), company)


if __name__ == "__main__":
    unittest.main()
