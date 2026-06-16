#!/usr/bin/env python3
"""Fetch recent intraday prices for paper-trading practice."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import update_results as common
import update_stock_analysis as stocks


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "practice-prices.json"
STATUS = DATA_DIR / "practice-prices-update-status.json"
YAHOO_INTRADAY = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=15m"


def fetch_price(symbol: str, exchange: str) -> dict[str, object]:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    payload = common.fetch_json(YAHOO_INTRADAY.format(ticker=quote(f"{symbol}{suffix}")))
    result = payload["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    latest_index = max(index for index, value in enumerate(closes) if value is not None)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "price": round(closes[latest_index], 2),
        "asOf": datetime.fromtimestamp(result["timestamp"][latest_index]).astimezone().isoformat(timespec="seconds"),
    }


def main() -> int:
    rows, errors = [], []
    for item in stocks.priority_companies():
        try:
            rows.append({"company": item["company"], **fetch_price(item["symbol"], item.get("exchange", "NSE"))})
        except Exception as error:
            errors.append(f"{item['symbol']}: {error}")
        time.sleep(0.15)
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({"updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "recordCount": len(rows), "errors": errors}, indent=2) + "\n", encoding="utf-8")
    common.log(f"Wrote intraday practice prices for {len(rows)} stocks to {OUTPUT.relative_to(ROOT)}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
