#!/usr/bin/env python3
"""Build QuarterWatch's result-date feed from NSE and optional fallback feeds."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_JSON = DATA_DIR / "results.json"
OUTPUT_CSV = DATA_DIR / "results.csv"
META_JSON = DATA_DIR / "update-status.json"
NSE_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"
NSE_EVENT_API = "https://www.nseindia.com/api/event-calendar"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
RESULT_WORDS = re.compile(r"\b(financial results?|quarterly results?|audited results?|unaudited results?)\b", re.I)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%B-%Y",
    "%d %B %Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
)


def log(message: str) -> None:
    print(f"[quarterwatch] {message}", flush=True)


def fetch_json(url: str, opener=None, referer: str | None = None, retries: int = 3) -> Any:
    opener = opener or build_opener()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    for attempt in range(retries):
        try:
            with opener.open(Request(url, headers=headers), timeout=30) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == retries - 1:
                raise RuntimeError(f"Could not fetch {url}: {error}") from error
            time.sleep(2 ** attempt)


def nse_opener():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    request = Request(
        NSE_HOME,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            response.read(1024)
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not initialize NSE session: {error}") from error
    return opener


def list_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "records", "events", "items"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def first_value(item: dict[str, Any], names: tuple[str, ...]) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_date(value: str) -> date | None:
    clean = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?.*$", "", value.strip())
    clean = clean.replace(",", "")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            pass
    match = re.search(r"\d{4}-\d{2}-\d{2}", clean)
    if match:
        try:
            return date.fromisoformat(match.group())
        except ValueError:
            pass
    return None


def infer_quarter(meeting_date: date) -> str:
    # Indian financial year: Apr-Mar. Result meetings usually follow quarter-end.
    if meeting_date.month in (7, 8, 9):
        quarter, start_year = "Q1", meeting_date.year
    elif meeting_date.month in (10, 11, 12):
        quarter, start_year = "Q2", meeting_date.year
    elif meeting_date.month in (1, 2, 3):
        quarter, start_year = "Q3", meeting_date.year - 1
    else:
        quarter, start_year = "Q4", meeting_date.year - 1
    return f"{quarter} FY{str(start_year + 1)[-2:]}"


def normalize(item: dict[str, Any], exchange: str, require_result_purpose: bool, source: str = "") -> dict[str, str] | None:
    purpose = first_value(item, ("purpose", "subject", "agenda", "desc", "description", "bm_purpose"))
    if require_result_purpose and not RESULT_WORDS.search(purpose):
        return None
    symbol = first_value(item, ("symbol", "sm_symbol", "ticker", "scrip_code", "scripcode", "code"))
    company = first_value(item, ("company", "companyname", "company_name", "sm_name", "name"))
    raw_date = first_value(item, ("date", "meetingdate", "meeting_date", "bm_date", "eventdate", "event_date"))
    meeting_date = parse_date(raw_date)
    if not symbol or not company or not meeting_date:
        return None
    quarter = first_value(item, ("quarter", "period")) or infer_quarter(meeting_date)
    status = first_value(item, ("status",)).lower()
    if status not in ("confirmed", "estimated"):
        status = "confirmed" if require_result_purpose and exchange.upper() == "NSE" else "estimated"
    official = require_result_purpose and exchange.upper() == "NSE"
    return {
        "company": company,
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "date": meeting_date.isoformat(),
        "quarter": quarter,
        "status": status,
        "verificationLevel": "official-exchange" if official else "external-feed",
        "source": source or ("NSE Event Calendar" if official else f"{exchange.upper()} fallback"),
        "sourceReference": first_value(item, ("url", "sourceurl", "source_url", "attachment", "fileurl")) or (NSE_HOME if official else ""),
        "verifiedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def fetch_nse(from_date: date, to_date: date) -> list[dict[str, str]]:
    opener = nse_opener()
    rows: list[dict[str, str]] = []
    for index in ("equities", "sme"):
        query = urlencode(
            {
                "index": index,
                "from_date": from_date.strftime("%d-%m-%Y"),
                "to_date": to_date.strftime("%d-%m-%Y"),
            }
        )
        payload = fetch_json(f"{NSE_EVENT_API}?{query}", opener, NSE_HOME)
        source_rows = list_payload(payload)
        normalized = [normalize(item, "NSE", True, "NSE Event Calendar") for item in source_rows]
        rows.extend(item for item in normalized if item)
        log(f"NSE {index}: retained {sum(item is not None for item in normalized)} of {len(source_rows)} events")
    return rows


def fetch_fallbacks(urls: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for url in urls:
        payload = fetch_json(url)
        source_rows = list_payload(payload)
        normalized = [normalize(item, first_value(item, ("exchange",)) or "BSE", False, url) for item in source_rows]
        rows.extend(item for item in normalized if item)
        log(f"Fallback {url}: retained {sum(item is not None for item in normalized)} of {len(source_rows)} rows")
    return rows


def load_previous() -> list[dict[str, str]]:
    if not OUTPUT_JSON.exists():
        return []
    try:
        return list_payload(json.loads(OUTPUT_JSON.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return []


def merge_rows(rows: list[dict[str, str]], previous: list[dict[str, str]], today: date) -> list[dict[str, str]]:
    # Preserve future records from other exchanges and last good runs, but let newer rows win.
    retained = []
    for item in previous:
        if item.get("date", "") < today.isoformat():
            continue
        retained.append({
            **item,
            "verificationLevel": item.get("verificationLevel", "legacy-unverified"),
            "source": item.get("source", "Previous successful feed"),
            "sourceReference": item.get("sourceReference", ""),
            "verifiedAt": item.get("verifiedAt", ""),
        })
    combined = retained + rows
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in combined:
        key = (item["exchange"], item["symbol"], item["date"])
        unique[key] = item
    return sorted(unique.values(), key=lambda item: (item["date"], item["exchange"], item["symbol"]))


def write_outputs(rows: list[dict[str, str]], sources: list[str], errors: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("company", "symbol", "exchange", "date", "quarter", "status", "verificationLevel", "source", "sourceReference", "verifiedAt"))
        writer.writeheader()
        writer.writerows(rows)
    META_JSON.write_text(
        json.dumps(
            {
                "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "recordCount": len(rows),
                "sources": sources,
                "errors": errors,
                "verification": {
                    "officialExchange": sum(item.get("verificationLevel") == "official-exchange" for item in rows),
                    "externalFeed": sum(item.get("verificationLevel") == "external-feed" for item in rows),
                    "legacyUnverified": sum(item.get("verificationLevel") == "legacy-unverified" for item in rows),
                    "confirmed": sum(item.get("status") == "confirmed" for item in rows),
                    "estimated": sum(item.get("status") == "estimated" for item in rows),
                },
                "verificationPolicy": "NSE event-calendar matches are official-exchange verified. External feeds remain estimated unless they explicitly report confirmed status.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180, help="Number of future days to fetch")
    parser.add_argument("--skip-nse", action="store_true", help="Only process configured fallback feeds")
    args = parser.parse_args()
    today = date.today()
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    errors: list[str] = []

    if not args.skip_nse:
        try:
            rows.extend(fetch_nse(today, today + timedelta(days=args.days)))
            sources.append("NSE Event Calendar")
        except RuntimeError as error:
            errors.append(str(error))
            log(f"WARNING: {error}")

    fallback_urls = [url.strip() for url in os.environ.get("RESULTS_FALLBACK_URLS", "").split(",") if url.strip()]
    for url in fallback_urls:
        try:
            rows.extend(fetch_fallbacks([url]))
            sources.append(url)
        except RuntimeError as error:
            errors.append(str(error))
            log(f"WARNING: {error}")

    merged = merge_rows(rows, load_previous(), today)
    write_outputs(merged, sources, errors)
    log(f"Wrote {len(merged)} upcoming result dates to {OUTPUT_JSON.relative_to(ROOT)}")
    if not rows and not merged:
        log("ERROR: no source returned data and no previous feed was available")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
