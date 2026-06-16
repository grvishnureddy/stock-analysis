#!/usr/bin/env python3
"""Build a latest-quarter financial summary feed for company detail views."""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import update_results as common


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_JSON = DATA_DIR / "financials.json"
OUTPUT_CSV = DATA_DIR / "financials.csv"
META_JSON = DATA_DIR / "financials-update-status.json"
NSE_API = "https://www.nseindia.com/api/corporates-financial-results"
NSE_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
FIELDS = ("company", "symbol", "exchange", "quarter", "periodEnded", "revenue", "profitLoss", "previousRevenue", "previousProfitLoss", "currency", "sourceUrl")


def amount(item: dict, names: tuple[str, ...]) -> str:
    value = common.first_value(item, names)
    if not value or value in ("-", "NA", "N/A"):
        return ""
    return value.replace(",", "").strip()


def normalize(item: dict, exchange: str = "NSE") -> dict[str, str] | None:
    symbol = common.first_value(item, ("symbol", "ticker", "scrip_code", "scripcode", "code"))
    company = common.first_value(item, ("company", "companyname", "company_name", "name", "sm_name"))
    period = common.first_value(item, ("periodended", "period_ended", "todate", "to_date", "date"))
    period_date = common.parse_date(period)
    if not symbol or not company or not period_date:
        return None
    return {
        "company": company,
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "quarter": common.first_value(item, ("quarter", "relatingto", "period")) or "Quarterly",
        "periodEnded": period_date.isoformat(),
        "revenue": amount(item, ("revenue", "totalincome", "total_income", "income")),
        "profitLoss": amount(item, ("profitloss", "profit_loss", "netprofit", "net_profit", "pat")),
        "previousRevenue": amount(item, ("previousrevenue", "previous_revenue", "prev_totalincome", "previous_total_income")),
        "previousProfitLoss": amount(item, ("previousprofitloss", "previous_profit_loss", "prev_netprofit", "previous_net_profit")),
        "currency": common.first_value(item, ("currency", "unit")) or "INR",
        "sourceUrl": common.first_value(item, ("sourceurl", "url", "link", "attachment", "attchmntfile", "xbrl", "resultdetaileddatalink")),
    }


def fetch_nse() -> list[dict[str, str]]:
    opener = common.nse_opener()
    rows: list[dict[str, str]] = []
    for index in ("equities", "sme"):
        query = urlencode({"index": index, "period": "Quarterly"})
        payload = common.fetch_json(f"{NSE_API}?{query}", opener, NSE_HOME)
        normalized = [normalize(item, "NSE") for item in common.list_payload(payload)]
        rows.extend(item for item in normalized if item)
        common.log(f"NSE {index} financials: retained {sum(item is not None for item in normalized)} rows")
    return rows


def fetch_fallback(url: str) -> list[dict[str, str]]:
    rows = []
    for item in common.list_payload(common.fetch_json(url)):
        normalized = normalize(item, common.first_value(item, ("exchange",)) or "BSE")
        if normalized:
            rows.append(normalized)
    return rows


def merge_latest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for item in rows:
        key = (item["exchange"], item["symbol"])
        if key not in latest or item["periodEnded"] > latest[key]["periodEnded"]:
            latest[key] = item
    return sorted(latest.values(), key=lambda item: (item["company"], item["exchange"]))


def write_outputs(rows: list[dict[str, str]], sources: list[str], errors: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    META_JSON.write_text(json.dumps({"updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "recordCount": len(rows), "sources": sources, "errors": errors}, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    errors: list[str] = []
    try:
        rows.extend(fetch_nse())
        sources.append("NSE Financial Results")
    except RuntimeError as error:
        errors.append(str(error))
        common.log(f"WARNING: {error}")
    for url in (value.strip() for value in os.environ.get("FINANCIALS_FALLBACK_URLS", "").split(",")):
        if not url:
            continue
        try:
            rows.extend(fetch_fallback(url))
            sources.append(url)
        except RuntimeError as error:
            errors.append(str(error))
    merged = merge_latest(rows)
    write_outputs(merged, sources, errors)
    common.log(f"Wrote {len(merged)} company financial summaries to {OUTPUT_JSON.relative_to(ROOT)}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
