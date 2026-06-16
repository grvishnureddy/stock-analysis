#!/usr/bin/env python3
"""Fetch valuation, ownership, and quarterly profit/loss history for one NSE company."""

from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import update_financials as financials
import update_results as common
import update_stock_analysis as stock_analysis


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "company-fundamentals"
SHAREHOLDING_API = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities"
SHAREHOLDING_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
MASTER_CACHE_SECONDS = 1800
YAHOO_FIVE_YEAR_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d&events=history"
YAHOO_INTRADAY_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=15m&events=history"
master_cache: dict[str, tuple[float, object]] = {}
master_cache_lock = threading.Lock()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_xml(url: str) -> ElementTree.Element:
    request = Request(url, headers={"User-Agent": common.USER_AGENT, "Accept": "application/xml,text/xml,*/*"})
    with urlopen(request, timeout=30) as response:
        return ElementTree.fromstring(response.read())


def cached_json(name: str, url: str, home: str) -> object:
    with master_cache_lock:
        cached = master_cache.get(name)
        if cached and time.monotonic() - cached[0] < MASTER_CACHE_SECONDS:
            return cached[1]
    payload = common.fetch_json(url, common.nse_opener(), home)
    if not common.list_payload(payload):
        raise RuntimeError(f"{name} source returned no records")
    with master_cache_lock:
        master_cache[name] = (time.monotonic(), payload)
    return payload


def parse_quarter_xbrl(url: str) -> dict[str, object] | None:
    root = fetch_xml(url)
    contexts: dict[str, tuple[date, date]] = {}
    for element in root.iter():
        if local_name(element.tag) != "context" or any(local_name(child.tag) == "scenario" for child in element.iter()):
            continue
        start = next((child.text for child in element.iter() if local_name(child.tag) == "startDate"), None)
        end = next((child.text for child in element.iter() if local_name(child.tag) == "endDate"), None)
        if start and end:
            contexts[element.attrib.get("id", "")] = (date.fromisoformat(start), date.fromisoformat(end))
    quarterly_contexts = {key: value for key, value in contexts.items() if 75 <= (value[1] - value[0]).days <= 100}
    wanted = {
        "ProfitLossForPeriod": "profitLossCrore",
        "ProfitLossForPeriodFromContinuingOperations": "profitLossCrore",
        "Income": "revenueCrore",
        "RevenueFromOperations": "revenueCrore",
    }
    values: dict[str, float] = {}
    period_end = None
    for element in root.iter():
        key = wanted.get(local_name(element.tag))
        context = quarterly_contexts.get(element.attrib.get("contextRef", ""))
        if not key or not context or key in values or not element.text:
            continue
        try:
            values[key] = round(float(element.text) / 10_000_000, 2)
            period_end = context[1].isoformat()
        except ValueError:
            continue
    if "profitLossCrore" not in values or not period_end:
        return None
    paid_up = next((element.text for element in root.iter() if local_name(element.tag) == "PaidUpValueOfEquityShareCapital" and element.attrib.get("contextRef", "") in quarterly_contexts), None)
    face_value = next((element.text for element in root.iter() if local_name(element.tag) == "FaceValueOfEquityShareCapital" and element.attrib.get("contextRef", "") in quarterly_contexts), None)
    issued_shares = round(float(paid_up) / float(face_value)) if paid_up and face_value and float(face_value) else None
    return {"periodEnded": period_end, **values, "issuedShares": issued_shares, "currency": "INR crore", "sourceUrl": url}


def parse_named_investors(url: str) -> list[dict[str, object]]:
    root = fetch_xml(url)
    percentages = {}
    shares = {}
    for element in root.iter():
        context = element.attrib.get("contextRef", "")
        if local_name(element.tag) == "ShareholdingAsAPercentageOfTotalNumberOfShares" and element.text:
            percentages[context] = float(element.text) * 100
        elif local_name(element.tag) in ("NumberOfShares", "NumberOfFullyPaidUpEquityShares") and element.text:
            shares.setdefault(context, int(float(element.text)))
    investors = []
    for element in root.iter():
        if local_name(element.tag) != "NameOfTheShareholder" or not element.text:
            continue
        context = element.attrib.get("contextRef", "").removeprefix("D_")
        percent = percentages.get(context, 0)
        if percent > 0:
            investors.append({"name": element.text.strip(), "percent": round(percent, 4), "shares": shares.get(context)})
    unique = {item["name"].upper(): item for item in investors}
    return sorted(unique.values(), key=lambda item: float(item["percent"]), reverse=True)[:12]


def fetch_financial_history(symbol: str, opener=None) -> list[dict[str, object]]:
    rows = []
    today = date.today()
    payload = cached_json(
        "financial-results",
        f"{financials.NSE_API}?{urlencode({'index': 'equities', 'period': 'Quarterly', 'from_date': (today - timedelta(days=1095)).strftime('%d-%m-%Y'), 'to_date': today.strftime('%d-%m-%Y')})}",
        financials.NSE_HOME,
    )
    candidates = [financials.normalize(item, "NSE") for item in common.list_payload(payload)]
    candidates = sorted(
        (item for item in candidates if item and item["symbol"] == symbol and item["sourceUrl"]),
        key=lambda item: item["periodEnded"],
        reverse=True,
    )
    unique_candidates = []
    seen = set()
    for item in candidates:
        if item["periodEnded"] not in seen:
            unique_candidates.append(item)
            seen.add(item["periodEnded"])
        if len(unique_candidates) >= 12:
            break
    def parse(item):
        try:
            parsed = parse_quarter_xbrl(item["sourceUrl"])
        except Exception:
            parsed = None
        return {**parsed, "quarter": item["quarter"]} if parsed else None
    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = [item for item in executor.map(parse, unique_candidates) if item][:8]
    return sorted(rows, key=lambda item: str(item["periodEnded"]))


def fetch_shareholding(symbol: str, opener=None) -> list[dict[str, object]]:
    payload = cached_json("shareholding", SHAREHOLDING_API, SHAREHOLDING_HOME)
    rows = [item for item in common.list_payload(payload) if str(item.get("symbol", "")).upper() == symbol]
    rows.sort(key=lambda item: common.parse_date(str(item.get("date", ""))) or date.min, reverse=True)
    output = [{
        "asOnDate": (common.parse_date(str(item.get("date", ""))) or date.min).isoformat(),
        "promoterPercent": item.get("pr_and_prgrp"),
        "publicPercent": item.get("public_val"),
        "employeeTrustPercent": item.get("employeeTrusts"),
        "detailedFilingUrl": item.get("xbrl"),
    } for item in rows[:4]]
    if output and output[0]["detailedFilingUrl"]:
        try:
            output[0]["majorInvestors"] = parse_named_investors(str(output[0]["detailedFilingUrl"]))
        except Exception:
            output[0]["majorInvestors"] = []
    return output


def fetch_valuation(symbol: str, opener) -> dict[str, object]:
    payload = common.fetch_json(
        f"https://www.nseindia.com/api/quote-equity?{urlencode({'symbol': symbol})}",
        opener,
        f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
    )
    price = payload.get("priceInfo", {}).get("lastPrice")
    issued = payload.get("securityInfo", {}).get("issuedSize")
    market_cap = round(float(price) * float(issued) / 10_000_000, 2) if price and issued else None
    return {"lastPrice": price, "issuedShares": issued, "marketCapCrore": market_cap, "currency": "INR crore", "priceSource": "NSE quote"}


def fallback_valuation(symbol: str, history: list[dict[str, object]]) -> dict[str, object]:
    candles = stock_analysis.fetch_candles(symbol, "NSE")
    price = candles[-1]["close"] if candles else None
    issued = history[-1].get("issuedShares") if history else None
    market_cap = round(float(price) * float(issued) / 10_000_000, 2) if price and issued else None
    return {"lastPrice": round(float(price), 2) if price else None, "issuedShares": issued, "marketCapCrore": market_cap, "currency": "INR crore", "priceSource": "Yahoo delayed close + NSE XBRL issued shares"}


def fetch_price_history(symbol: str, exchange: str) -> list[dict[str, object]]:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    payload = common.fetch_json(YAHOO_FIVE_YEAR_CHART.format(ticker=quote(f"{symbol}{suffix}")))
    result = payload["chart"]["result"][0]
    quote_data = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(result.get("timestamp", [])):
        close = quote_data["close"][index]
        if close is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(timestamp).date().isoformat(),
            "close": round(float(close), 2),
            "volume": quote_data["volume"][index],
        })
    return rows


def fetch_intraday_history(symbol: str, exchange: str) -> list[dict[str, object]]:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    payload = common.fetch_json(YAHOO_INTRADAY_CHART.format(ticker=quote(f"{symbol}{suffix}")))
    result = payload["chart"]["result"][0]
    quote_data = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(result.get("timestamp", [])):
        close = quote_data["close"][index]
        if close is None:
            continue
        rows.append({
            "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="minutes"),
            "close": round(float(close), 2),
            "volume": quote_data["volume"][index],
        })
    return rows


def fetch_company_fundamentals(company: str, symbol: str, exchange: str) -> dict[str, object]:
    if exchange != "NSE":
        return {"company": company, "symbol": symbol, "exchange": exchange, "error": "Only NSE fundamentals are currently supported"}
    errors, history, shareholding, valuation, candles, price_history, intraday_history = [], [], [], {}, [], [], []
    executor = ThreadPoolExecutor(max_workers=6)
    futures = {
        "Financial history": executor.submit(fetch_financial_history, symbol),
        "Shareholding": executor.submit(fetch_shareholding, symbol),
        "Valuation": executor.submit(lambda: fetch_valuation(symbol, common.nse_opener())),
        "Delayed price": executor.submit(stock_analysis.fetch_candles, symbol, "NSE"),
        "Five-year price history": executor.submit(fetch_price_history, symbol, exchange),
        "Intraday price history": executor.submit(fetch_intraday_history, symbol, exchange),
    }
    done, pending = wait(futures.values(), timeout=22)
    executor.shutdown(wait=False, cancel_futures=True)
    for label, future in futures.items():
        if future in pending:
            errors.append(f"{label}: timed out")
            continue
        try:
            value = future.result()
            if label == "Financial history":
                history = value
            elif label == "Shareholding":
                shareholding = value
            elif label == "Valuation":
                valuation = value
            elif label == "Five-year price history":
                price_history = value
            elif label == "Intraday price history":
                intraday_history = value
            else:
                candles = value
        except Exception as error:
            errors.append(f"{label}: {error}")
    if not valuation:
        price = candles[-1]["close"] if candles else None
        issued = history[-1].get("issuedShares") if history else None
        market_cap = round(float(price) * float(issued) / 10_000_000, 2) if price and issued else None
        valuation = {
            "lastPrice": round(float(price), 2) if price else None,
            "issuedShares": issued,
            "marketCapCrore": market_cap,
            "currency": "INR crore",
            "priceSource": "Yahoo delayed close + NSE XBRL issued shares",
        }
    return {
        "company": company, "symbol": symbol, "exchange": exchange,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "valuation": valuation, "shareholding": shareholding, "quarterlyHistory": history,
        "priceHistory": price_history, "intradayHistory": intraday_history,
        "priceHistorySource": "Yahoo Finance delayed daily and 15-minute prices",
        "errors": errors,
    }


def cache_path(exchange: str, symbol: str) -> Path:
    return CACHE_DIR / f"{exchange}-{symbol}.json"


def has_useful_data(payload: dict[str, object]) -> bool:
    valuation = payload.get("valuation") or {}
    return bool(valuation.get("marketCapCrore") or payload.get("shareholding") or payload.get("quarterlyHistory") or payload.get("priceHistory"))


def merge_cached_data(payload: dict[str, object]) -> dict[str, object]:
    path = cache_path(str(payload["exchange"]), str(payload["symbol"]))
    if not path.exists():
        return payload
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload
    merged = {**previous, **payload}
    for key in ("shareholding", "quarterlyHistory", "priceHistory", "intradayHistory"):
        if not payload.get(key) and previous.get(key):
            merged[key] = previous[key]
    valuation = {**(previous.get("valuation") or {})}
    valuation.update({key: value for key, value in (payload.get("valuation") or {}).items() if value is not None})
    merged["valuation"] = valuation
    return merged


def save(payload: dict[str, object]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(str(payload["exchange"]), str(payload["symbol"]))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: update_company_fundamentals.py COMPANY SYMBOL EXCHANGE", file=sys.stderr)
        return 2
    payload = merge_cached_data(fetch_company_fundamentals(sys.argv[1], sys.argv[2].upper(), sys.argv[3].upper()))
    path = save(payload)
    print(f"[stockscope] Wrote company fundamentals to {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
