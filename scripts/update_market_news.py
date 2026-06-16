#!/usr/bin/env python3
"""Aggregate market news from RSS/Atom/JSON feeds and calculate trend scores."""

from __future__ import annotations

import email.utils
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import update_results as common


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "market-news.json"
STATUS = DATA_DIR / "market-news-update-status.json"
DEFAULT_FEEDS = {
    "Google News India Markets": "https://news.google.com/rss/search?q=India+stock+market+OR+NSE+OR+BSE&hl=en-IN&gl=IN&ceid=IN:en",
    "NDTV Business": "https://feeds.feedburner.com/ndtvprofit-latest",
    "Moneycontrol Markets": "https://www.moneycontrol.com/rss/marketreports.xml",
}
MARKET_WORDS = re.compile(r"\b(nifty|sensex|nse|bse|stock|shares|market|earnings|results|ipo|sebi|rbi|merger|acquisition|order|contract)\b", re.I)
HIGH_IMPACT = {
    "risk": re.compile(r"\b(default|fraud|penalty|fine|litigation|insolvency|bankruptcy|delisting|downgrade|probe|tax demand|notice)\b", re.I),
    "contract": re.compile(r"\b(order|contract|work order|letter of award|tender|project awarded)\b", re.I),
    "results": re.compile(r"\b(earnings|financial results|quarterly results|profit|loss|revenue|margin)\b", re.I),
    "corporate action": re.compile(r"\b(merger|acquisition|buyback|bonus|dividend|split|fund raising|stake sale|ipo)\b", re.I),
}
AMBIGUOUS_SYMBOLS = {"BSE", "NSE", "NDTV", "OIL", "GLOBAL", "TAKE", "VIGOR", "GOLD", "SILVER", "INDIA", "MARKET", "STOCK"}


def parse_time(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: str | None) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("&nbsp;", " ").strip()


def fetch_xml(source: str, url: str) -> list[dict[str, str]]:
    request = Request(url, headers={"User-Agent": common.USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/xml"})
    with urlopen(request, timeout=30) as response:
        root = ElementTree.fromstring(response.read())
    rows = []
    for item in root.findall(".//item"):
        rows.append({"source": source, "platform": "news", "title": clean(item.findtext("title")), "summary": clean(item.findtext("description")), "url": clean(item.findtext("link")), "publishedAt": parse_time(item.findtext("pubDate") or "")})
    for item in root.findall(".//{*}entry"):
        link = item.find("{*}link")
        rows.append({"source": source, "platform": "news", "title": clean(item.findtext("{*}title")), "summary": clean(item.findtext("{*}summary") or item.findtext("{*}content")), "url": link.attrib.get("href", "") if link is not None else "", "publishedAt": parse_time(item.findtext("{*}updated") or item.findtext("{*}published") or "")})
    return [row for row in rows if row["title"] and row["url"]]


def fetch_json_feed(source: str, url: str) -> list[dict[str, str]]:
    rows = []
    for item in common.list_payload(common.fetch_json(url)):
        title = common.first_value(item, ("title", "headline", "text"))
        link = common.first_value(item, ("url", "link", "permalink"))
        if title and link:
            rows.append({"source": source, "platform": common.first_value(item, ("platform",)) or "social", "title": title, "summary": common.first_value(item, ("summary", "description")), "url": link, "publishedAt": parse_time(common.first_value(item, ("publishedAt", "published_at", "date", "created_at")))})
    return rows


def company_universe() -> list[dict[str, str]]:
    companies: dict[tuple[str, str], dict[str, str]] = {}
    for filename in ("financials.json", "news.json", "results.json"):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in common.list_payload(payload):
            symbol = common.first_value(item, ("symbol",))
            company = common.first_value(item, ("company",))
            exchange = common.first_value(item, ("exchange",)) or "NSE"
            if symbol and company:
                companies[(exchange, symbol)] = {"company": company, "symbol": symbol, "exchange": exchange}
    return list(companies.values())


def company_match(text: str, companies: list[dict[str, str]]) -> dict[str, str] | None:
    lowered = text.lower()
    for item in companies:
        symbol = item["symbol"]
        company = re.sub(r"\b(limited|ltd|india)\b", "", item["company"].lower()).strip()
        name_match = len(company) >= 6 and company in lowered
        symbol_match = symbol not in AMBIGUOUS_SYMBOLS and len(symbol) >= 3 and re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text)
        if name_match or symbol_match:
            return item
    return None


def score(rows: list[dict[str, str]], companies: list[dict[str, str]] | None = None) -> list[dict[str, object]]:
    companies = companies or []
    tokens = Counter()
    for row in rows:
        tokens.update(set(re.findall(r"[a-z0-9]{4,}", row["title"].lower())))
    now = datetime.now(timezone.utc)
    scored = []
    for row in rows:
        published = datetime.fromisoformat(row["publishedAt"])
        hours = max(0, (now - published).total_seconds() / 3600)
        repeated = sum(max(0, tokens[word] - 1) for word in set(re.findall(r"[a-z0-9]{4,}", row["title"].lower())))
        market = len(MARKET_WORDS.findall(row["title"]))
        matched = company_match(f"{row['title']} {row['summary']}", companies)
        impact = next((label for label, pattern in HIGH_IMPACT.items() if pattern.search(f"{row['title']} {row['summary']}")), "company news" if matched else "market")
        stock_priority = (80 if matched else 0) + (35 if impact != "market" and impact != "company news" else 0)
        trend_score = round(max(0, 100 - hours * 2) + min(50, repeated * 3) + market * 8 + stock_priority + (10 if row["platform"] == "social" else 0), 1)
        scored.append({**row, "trendScore": trend_score, "stockPriority": stock_priority, "impact": impact, "matchedCompany": matched})
    return sorted(scored, key=lambda item: (bool(item["matchedCompany"]), item["stockPriority"], item["trendScore"], item["publishedAt"]), reverse=True)


def main() -> int:
    rows = []
    sources = []
    errors = []
    feed_map = dict(DEFAULT_FEEDS)
    for value in os.environ.get("MARKET_NEWS_RSS_FEEDS", "").split(","):
        if value.strip():
            feed_map[f"Custom news {len(feed_map) + 1}"] = value.strip()
    for source, url in feed_map.items():
        try:
            rows.extend(fetch_xml(source, url))
            sources.append(source)
        except Exception as error:
            errors.append(f"{source}: {error}")
    for url in (value.strip() for value in os.environ.get("SOCIAL_NEWS_FEED_URLS", "").split(",")):
        if not url:
            continue
        try:
            rows.extend(fetch_json_feed("Configured social feed", url))
            sources.append(url)
        except Exception as error:
            errors.append(f"{url}: {error}")
    unique = {row["url"]: row for row in rows}
    output = score(list(unique.values()), company_universe())[:500]
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({"updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "recordCount": len(output), "sources": sources, "errors": errors}, indent=2) + "\n", encoding="utf-8")
    common.log(f"Wrote {len(output)} market news stories to {OUTPUT.relative_to(ROOT)}")
    return 0 if output else 1


if __name__ == "__main__":
    sys.exit(main())
