#!/usr/bin/env python3
"""Calculate transparent daily technical analysis for priority NSE stocks."""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import update_results as common


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "stock-analysis.json"
STATUS = DATA_DIR / "stock-analysis-update-status.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d&events=history"


def sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0) for change in changes[-period:]]
    losses = [abs(min(change, 0)) for change in changes[-period:]]
    avg_gain, avg_loss = sum(gains) / period, sum(losses) / period
    return 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))


def analyze(symbol: str, company: str, exchange: str, candles: list[dict[str, float]]) -> dict[str, object] | None:
    closes = [row["close"] for row in candles if row.get("close")]
    if len(closes) < 30:
        return None
    highs = [row["high"] for row in candles if row.get("high")]
    lows = [row["low"] for row in candles if row.get("low")]
    volumes = [row["volume"] for row in candles if row.get("volume") is not None]
    last = closes[-1]
    sma20, sma50, sma200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    current_rsi = rsi(closes)
    ema12, ema26 = ema_series(closes, 12), ema_series(closes, 26)
    macd_values = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    macd = macd_values[-1]
    signal = ema_series(macd_values, 9)[-1]
    returns = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes))]
    volatility = statistics.pstdev(returns[-20:]) * math.sqrt(252) if len(returns) >= 20 else None
    momentum_20 = (last / closes[-21] - 1) * 100 if len(closes) > 20 else None
    average_volume = sma([float(value) for value in volumes], 20)
    volume_ratio = volumes[-1] / average_volume if average_volume else None
    votes = []
    votes.append(1 if sma20 and last > sma20 else -1)
    votes.append(1 if sma50 and last > sma50 else -1)
    if sma200:
        votes.append(1 if last > sma200 else -1)
    votes.append(1 if macd > signal else -1)
    votes.append(1 if current_rsi and 50 <= current_rsi < 70 else -1 if current_rsi and (current_rsi > 75 or current_rsi < 35) else 0)
    votes.append(1 if momentum_20 and momentum_20 > 0 else -1)
    total = sum(votes)
    label = "Bullish" if total >= 3 else "Bearish" if total <= -3 else "Neutral"
    confidence = round(abs(total) / len(votes) * 100)
    return {
        "company": company, "symbol": symbol, "exchange": exchange, "asOf": candles[-1]["date"], "close": round(last, 2),
        "signal": label, "confidence": confidence, "score": total, "rsi14": round(current_rsi, 2) if current_rsi else None,
        "sma20": round(sma20, 2) if sma20 else None, "sma50": round(sma50, 2) if sma50 else None, "sma200": round(sma200, 2) if sma200 else None,
        "macd": round(macd, 2), "macdSignal": round(signal, 2), "momentum20d": round(momentum_20, 2) if momentum_20 is not None else None,
        "annualizedVolatility": round(volatility, 2) if volatility else None, "volumeRatio": round(volume_ratio, 2) if volume_ratio else None,
        "support20d": round(min(lows[-20:]), 2), "resistance20d": round(max(highs[-20:]), 2),
        "chart": [{"date": row["date"], "close": round(row["close"], 2), "volume": row.get("volume")} for row in candles[-90:]],
        "method": "Indicator agreement: price vs SMA20/50/200, MACD, RSI, and 20-day momentum.",
    }


def fetch_candles(symbol: str, exchange: str) -> list[dict[str, float]]:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    payload = common.fetch_json(YAHOO_CHART.format(ticker=quote(f"{symbol}{suffix}")))
    result = payload["chart"]["result"][0]
    quote_data = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(result["timestamp"]):
        close = quote_data["close"][index]
        if close is None:
            continue
        rows.append({"date": datetime.fromtimestamp(timestamp).date().isoformat(), "open": quote_data["open"][index], "high": quote_data["high"][index], "low": quote_data["low"][index], "close": close, "volume": quote_data["volume"][index]})
    return rows


def priority_companies() -> list[dict[str, str]]:
    companies = {}
    for filename in ("results.json", "market-news.json"):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in common.list_payload(payload):
            candidate = item.get("matchedCompany") or item
            if candidate and candidate.get("symbol") and candidate.get("company"):
                companies[(candidate.get("exchange", "NSE"), candidate["symbol"])] = candidate
    configured = os.environ.get("STOCK_ANALYSIS_SYMBOLS", "")
    names = {item["symbol"]: item["company"] for item in companies.values()}
    for symbol in (value.strip().upper() for value in configured.split(",")):
        if symbol:
            companies[("NSE", symbol)] = {"company": names.get(symbol, symbol), "symbol": symbol, "exchange": "NSE"}
    return list(companies.values())[:100]


def main() -> int:
    rows, errors = [], []
    for item in priority_companies():
        try:
            result = analyze(item["symbol"], item["company"], item.get("exchange", "NSE"), fetch_candles(item["symbol"], item.get("exchange", "NSE")))
            if result:
                rows.append(result)
        except Exception as error:
            errors.append(f"{item['symbol']}: {error}")
        time.sleep(0.2)
    rows.sort(key=lambda item: (item["confidence"], abs(item["score"])), reverse=True)
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps({"updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "recordCount": len(rows), "errors": errors}, indent=2) + "\n", encoding="utf-8")
    common.log(f"Wrote daily analysis for {len(rows)} stocks to {OUTPUT.relative_to(ROOT)}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
