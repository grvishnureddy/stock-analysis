#!/usr/bin/env python3
"""Fetch major Indian indices, commodities, and current NSE index constituents."""

from __future__ import annotations

import csv
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import update_results as common


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "market-overview.json"
STATUS = DATA_DIR / "market-overview-update-status.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d&events=history"
NSE_INDEX_URL = "https://www.nseindia.com/api/equity-stockIndices?"
NSE_COMPONENT_CSV = {
    "NIFTY 50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY BANK": "https://nsearchives.nseindia.com/content/indices/ind_niftybanklist.csv",
    "NIFTY IT": "https://nsearchives.nseindia.com/content/indices/ind_niftyitlist.csv",
    "NIFTY AUTO": "https://nsearchives.nseindia.com/content/indices/ind_niftyautolist.csv",
    "NIFTY METAL": "https://nsearchives.nseindia.com/content/indices/ind_niftymetallist.csv",
    "NIFTY PHARMA": "https://nsearchives.nseindia.com/content/indices/ind_niftypharmalist.csv",
}

INSTRUMENTS = [
    {"name": "Nifty 50", "symbol": "^NSEI", "type": "index", "market": "NSE", "nseIndex": "NIFTY 50"},
    {"name": "Sensex", "symbol": "^BSESN", "type": "index", "market": "BSE"},
    {"name": "Nifty Bank", "symbol": "^NSEBANK", "type": "index", "market": "NSE", "nseIndex": "NIFTY BANK"},
    {"name": "Nifty IT", "symbol": "^CNXIT", "type": "sector", "market": "NSE", "nseIndex": "NIFTY IT"},
    {"name": "Nifty Auto", "symbol": "^CNXAUTO", "type": "sector", "market": "NSE", "nseIndex": "NIFTY AUTO"},
    {"name": "Nifty Metal", "symbol": "^CNXMETAL", "type": "sector", "market": "NSE", "nseIndex": "NIFTY METAL"},
    {"name": "Nifty Pharma", "symbol": "^CNXPHARMA", "type": "sector", "market": "NSE", "nseIndex": "NIFTY PHARMA"},
    {"name": "India VIX", "symbol": "^INDIAVIX", "type": "volatility", "market": "NSE"},
    {"name": "Gold", "symbol": "GC=F", "type": "metal", "market": "Global", "unit": "USD / troy oz"},
    {"name": "Silver", "symbol": "SI=F", "type": "metal", "market": "Global", "unit": "USD / troy oz"},
    {"name": "Copper", "symbol": "HG=F", "type": "metal", "market": "Global", "unit": "USD / lb"},
    {"name": "Crude Oil", "symbol": "CL=F", "type": "energy", "market": "Global", "unit": "USD / barrel"},
]


def percentage_change(current: float, previous: float | None) -> float | None:
    return round((current / previous - 1) * 100, 2) if previous else None


def summarize_chart(payload: dict, instrument: dict) -> dict:
    result = payload["chart"]["result"][0]
    quotes = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(result.get("timestamp", [])):
        close = quotes["close"][index]
        if close is not None:
            rows.append({"date": datetime.fromtimestamp(timestamp).date().isoformat(), "close": round(close, 2)})
    if len(rows) < 2:
        raise RuntimeError("Insufficient market history")
    current = rows[-1]["close"]
    return {
        **instrument,
        "price": current,
        "asOf": rows[-1]["date"],
        "change1d": percentage_change(current, rows[-2]["close"]),
        "change1w": percentage_change(current, rows[-6]["close"] if len(rows) >= 6 else rows[0]["close"]),
        "change1m": percentage_change(current, rows[-22]["close"] if len(rows) >= 22 else rows[0]["close"]),
        "rangeLow": min(row["close"] for row in rows[-22:]),
        "rangeHigh": max(row["close"] for row in rows[-22:]),
        "chart": rows[-65:],
        "sourceUrl": f"https://finance.yahoo.com/quote/{quote(instrument['symbol'])}",
    }


def fetch_instrument(instrument: dict) -> dict:
    payload = common.fetch_json(YAHOO_CHART.format(symbol=quote(instrument["symbol"])))
    return summarize_chart(payload, instrument)


def normalize_component(item: dict) -> dict | None:
    symbol = str(item.get("symbol") or "").strip()
    if not symbol or symbol.upper() == "NIFTY 50":
        return None
    return {
        "symbol": symbol,
        "company": str(item.get("meta", {}).get("companyName") or item.get("companyName") or symbol),
        "lastPrice": item.get("lastPrice"),
        "change": item.get("change"),
        "pChange": item.get("pChange"),
        "volume": item.get("totalTradedVolume"),
        "marketCap": item.get("ffmc"),
    }


def fetch_constituents(opener, index_name: str) -> list[dict]:
    payload = common.fetch_json(
        NSE_INDEX_URL + "index=" + quote(index_name, safe=""),
        opener,
        "https://www.nseindia.com/market-data/live-equity-market",
    )
    rows = []
    for item in common.list_payload(payload):
        if str(item.get("symbol") or "").strip().upper() == index_name.upper():
            continue
        normalized = normalize_component(item)
        if normalized:
            rows.append(normalized)
    return rows


def local_component_metrics() -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for filename in ("stock-analysis.json", "practice-prices.json"):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            symbol = row.get("symbol")
            if symbol:
                metrics.setdefault(symbol, {}).update({
                    "lastPrice": row.get("price", row.get("close")),
                    "pChange": row.get("change1d"),
                    "company": row.get("company"),
                })
    return metrics


def fetch_constituent_csv(index_name: str, metrics: dict[str, dict]) -> list[dict]:
    request = Request(NSE_COMPONENT_CSV[index_name], headers={"User-Agent": common.USER_AGENT, "Accept": "text/csv,*/*"})
    with urlopen(request, timeout=30) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    result = []
    for row in rows:
        symbol = (row.get("Symbol") or "").strip()
        if not symbol:
            continue
        local = metrics.get(symbol, {})
        result.append({
            "symbol": symbol,
            "company": (row.get("Company Name") or local.get("company") or symbol).strip(),
            "industry": (row.get("Industry") or "").strip(),
            "lastPrice": local.get("lastPrice"),
            "change": None,
            "pChange": local.get("pChange"),
            "volume": None,
            "marketCap": None,
        })
    return result


def previous_instruments() -> dict[str, dict]:
    if not OUTPUT.exists():
        return {}
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        return {item["symbol"]: item for item in payload.get("instruments", [])}
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


def main() -> int:
    previous = previous_instruments()
    rows, errors = [], []
    for instrument in INSTRUMENTS:
        try:
            rows.append(fetch_instrument(instrument))
        except Exception as error:
            errors.append(f"{instrument['name']}: {error}")
            if instrument["symbol"] in previous:
                rows.append(previous[instrument["symbol"]])
        time.sleep(0.15)

    components: dict[str, list[dict]] = {}
    local_metrics = local_component_metrics()
    try:
        opener = common.nse_opener()
        for instrument in INSTRUMENTS:
            if instrument.get("nseIndex"):
                try:
                    components[instrument["nseIndex"]] = fetch_constituents(opener, instrument["nseIndex"])
                except Exception:
                    try:
                        components[instrument["nseIndex"]] = fetch_constituent_csv(instrument["nseIndex"], local_metrics)
                    except Exception as error:
                        errors.append(f"{instrument['name']} components: {error}")
                time.sleep(0.2)
    except Exception as error:
        for index_name in NSE_COMPONENT_CSV:
            try:
                components[index_name] = fetch_constituent_csv(index_name, local_metrics)
            except Exception as fallback_error:
                errors.append(f"{index_name} components: {fallback_error}")

    payload = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "instruments": rows,
        "components": components,
        "disclaimer": "Prices may be delayed. Commodity futures are global reference contracts and are not Indian retail spot prices.",
    }
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({"updatedAt": payload["updatedAt"], "recordCount": len(rows), "componentCount": sum(map(len, components.values())), "errors": errors}, indent=2) + "\n", encoding="utf-8")
    common.log(f"Wrote {len(rows)} market instruments and {sum(map(len, components.values()))} components to {OUTPUT.relative_to(ROOT)}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
