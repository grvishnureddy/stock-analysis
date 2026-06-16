#!/usr/bin/env python3
"""Build a feed of recent company announcements and upcoming events."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import update_results as common


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_JSON = DATA_DIR / "news.json"
OUTPUT_CSV = DATA_DIR / "news.csv"
META_JSON = DATA_DIR / "news-update-status.json"
NSE_ANNOUNCEMENTS_API = "https://www.nseindia.com/api/corporate-announcements"
NSE_ANNOUNCEMENTS_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"


def parse_datetime(value: str) -> str:
    clean = value.strip().replace(",", "")
    formats = (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).isoformat(timespec="seconds")
        except ValueError:
            pass
    parsed = common.parse_date(clean)
    return datetime.combine(parsed, datetime.min.time()).isoformat(timespec="seconds") if parsed else ""


def normalize_news(item: dict, exchange: str = "NSE", kind: str = "announcement") -> dict[str, str] | None:
    symbol = common.first_value(item, ("symbol", "sm_symbol", "ticker", "scrip_code", "scripcode", "code"))
    company = common.first_value(item, ("company", "companyname", "company_name", "sm_name", "name", "securityname"))
    headline = common.first_value(item, ("headline", "subject", "desc", "description", "purpose", "agenda", "category"))
    raw_time = common.first_value(
        item,
        ("publishedAt", "published_at", "an_dt", "broadcastdate", "broadcast_date", "date", "eventdate", "meetingdate", "bm_date"),
    )
    published_at = parse_datetime(raw_time)
    if not symbol or not company or not headline or not published_at:
        return None
    url = common.first_value(item, ("url", "link", "attachment", "attchmntfile", "attachmentfile"))
    if url.startswith("/"):
        url = f"https://www.nseindia.com{url}"
    return {
        "company": company,
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "publishedAt": published_at,
        "type": common.first_value(item, ("type", "category")) or kind,
        "headline": headline,
        "summary": common.first_value(item, ("summary", "details", "remark", "remarks")),
        "url": url,
    }


def fetch_nse_announcements(from_date: date, to_date: date) -> list[dict[str, str]]:
    opener = common.nse_opener()
    rows: list[dict[str, str]] = []
    for index in ("equities", "sme"):
        query = urlencode(
            {
                "index": index,
                "from_date": from_date.strftime("%d-%m-%Y"),
                "to_date": to_date.strftime("%d-%m-%Y"),
            }
        )
        payload = common.fetch_json(f"{NSE_ANNOUNCEMENTS_API}?{query}", opener, NSE_ANNOUNCEMENTS_HOME)
        source_rows = common.list_payload(payload)
        normalized = [normalize_news(item) for item in source_rows]
        rows.extend(item for item in normalized if item)
        common.log(f"NSE {index} news: retained {sum(item is not None for item in normalized)} of {len(source_rows)} announcements")
    return rows


def fetch_nse_events(today: date, to_date: date) -> list[dict[str, str]]:
    opener = common.nse_opener()
    rows: list[dict[str, str]] = []
    for index in ("equities", "sme"):
        query = urlencode({"index": index, "from_date": today.strftime("%d-%m-%Y"), "to_date": to_date.strftime("%d-%m-%Y")})
        payload = common.fetch_json(f"{common.NSE_EVENT_API}?{query}", opener, common.NSE_HOME)
        normalized = [normalize_news(item, "NSE", "upcoming event") for item in common.list_payload(payload)]
        rows.extend(item for item in normalized if item)
    return rows


def fetch_fallback(url: str) -> list[dict[str, str]]:
    payload = common.fetch_json(url)
    rows = []
    for item in common.list_payload(payload):
        normalized = normalize_news(item, common.first_value(item, ("exchange",)) or "BSE")
        if normalized:
            rows.append(normalized)
    return rows


def load_previous() -> list[dict[str, str]]:
    if not OUTPUT_JSON.exists():
        return []
    try:
        return common.list_payload(json.loads(OUTPUT_JSON.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return []


def merge_rows(rows: list[dict[str, str]], previous: list[dict[str, str]], cutoff: date) -> list[dict[str, str]]:
    combined = [item for item in previous if item.get("publishedAt", "")[:10] >= cutoff.isoformat()] + rows
    unique: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for item in combined:
        key = (item["exchange"], item["symbol"], item["publishedAt"], item["headline"])
        unique[key] = item
    return sorted(unique.values(), key=lambda item: item["publishedAt"], reverse=True)


def write_outputs(rows: list[dict[str, str]], sources: list[str], errors: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    fields = ("company", "symbol", "exchange", "publishedAt", "type", "headline", "summary", "url")
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    META_JSON.write_text(
        json.dumps(
            {
                "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "recordCount": len(rows),
                "sources": sources,
                "errors": errors,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-days", type=int, default=7)
    parser.add_argument("--event-days", type=int, default=30)
    parser.add_argument("--skip-nse", action="store_true")
    args = parser.parse_args()
    today = date.today()
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    errors: list[str] = []

    if not args.skip_nse:
        try:
            rows.extend(fetch_nse_announcements(today - timedelta(days=args.history_days), today))
            rows.extend(fetch_nse_events(today, today + timedelta(days=args.event_days)))
            sources.extend(("NSE Corporate Announcements", "NSE Event Calendar"))
        except RuntimeError as error:
            errors.append(str(error))
            common.log(f"WARNING: {error}")

    for url in (value.strip() for value in os.environ.get("NEWS_FALLBACK_URLS", "").split(",")):
        if not url:
            continue
        try:
            rows.extend(fetch_fallback(url))
            sources.append(url)
        except RuntimeError as error:
            errors.append(str(error))
            common.log(f"WARNING: {error}")

    merged = merge_rows(rows, load_previous(), today - timedelta(days=args.history_days))
    write_outputs(merged, sources, errors)
    common.log(f"Wrote {len(merged)} news and event items to {OUTPUT_JSON.relative_to(ROOT)}")
    return 0 if rows or merged else 1


if __name__ == "__main__":
    sys.exit(main())
