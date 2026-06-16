#!/usr/bin/env python3
"""Fetch and analyze up to six months of news for a selected company."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import update_market_news as market_news


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "company-news"
POSITIVE = re.compile(r"\b(wins?|award|growth|profit|surge|rises?|upgrade|expansion|launch|approval|partnership|dividend|buyback)\b", re.I)
NEGATIVE = re.compile(r"\b(loss|falls?|decline|default|fraud|penalty|probe|downgrade|warning|litigation|tax demand|notice|weakness)\b", re.I)
CONTRACT = re.compile(r"\b(order|contract|work order|letter of award|tender|project awarded)\b", re.I)
RESULT = re.compile(r"\b(results?|earnings|profit|loss|revenue|margin|quarter)\b", re.I)


def analyze_story(story: dict[str, str]) -> dict[str, object]:
    text = f"{story['title']} {story.get('summary', '')}"
    positive = len(POSITIVE.findall(text))
    negative = len(NEGATIVE.findall(text))
    category = "contract" if CONTRACT.search(text) else "result" if RESULT.search(text) else "risk" if negative > positive else "positive" if positive > negative else "neutral"
    sentiment = "positive" if positive > negative else "negative" if negative > positive else "neutral"
    return {**story, "category": category, "sentiment": sentiment, "sentimentScore": positive - negative}


def search_urls(company: str, symbol: str) -> list[str]:
    queries = [
        f'"{company}" stock',
        f'{symbol} stock India',
        f'"{company}" results OR order OR contract OR news',
    ]
    return [f"https://news.google.com/rss/search?{urlencode({'q': query, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'})}" for query in queries]


def fetch_company_news(company: str, symbol: str, exchange: str) -> dict[str, object]:
    rows, errors = [], []
    for url in search_urls(company, symbol):
        try:
            rows.extend(market_news.fetch_xml("Google News", url))
        except Exception as error:
            errors.append(str(error))
    cutoff = datetime.now(timezone.utc) - timedelta(days=183)
    recent = [row for row in rows if datetime.fromisoformat(row["publishedAt"]) >= cutoff]
    unique = {re.sub(r"\W+", " ", row["title"].lower()).strip(): analyze_story(row) for row in recent}
    stories = sorted(unique.values(), key=lambda item: item["publishedAt"], reverse=True)[:100]
    counts = {category: sum(item["category"] == category for item in stories) for category in ("positive", "risk", "contract", "result", "neutral")}
    return {
        "company": company,
        "symbol": symbol,
        "exchange": exchange,
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodMonths": 6,
        "storyCount": len(stories),
        "minimumTarget": 10,
        "counts": counts,
        "stories": stories,
        "errors": errors,
    }


def cache_path(exchange: str, symbol: str) -> Path:
    return CACHE_DIR / f"{exchange}-{symbol}.json"


def save_analysis(payload: dict[str, object]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(str(payload["exchange"]), str(payload["symbol"]))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: update_company_news.py COMPANY SYMBOL EXCHANGE", file=sys.stderr)
        return 2
    payload = fetch_company_news(sys.argv[1], sys.argv[2].upper(), sys.argv[3].upper())
    path = save_analysis(payload)
    print(f"[quarterwatch] Wrote {payload['storyCount']} stories to {path.relative_to(ROOT)}")
    return 0 if payload["storyCount"] else 1


if __name__ == "__main__":
    sys.exit(main())
