#!/usr/bin/env python3
"""Build transparent today/tomorrow stock watchlists from local news and signals."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "watch-predictions.json"
STATUS = DATA_DIR / "watch-predictions-update-status.json"

POSITIVE = ("buy", "wins", "order", "contract", "growth", "profit", "upgrade", "approval", "fund raising", "dividend")
NEGATIVE = ("sell", "fraud", "probe", "searches", "loss", "downgrade", "default", "penalty", "risk", "decline")
GOSSIP = ("rumor", "rumour", "gossip", "chatter", "buzz", "speculation", "unconfirmed", "sources say")


def load_rows(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else payload.get("items", [])


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def is_gossip(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('headline', '')} {item.get('summary', '')}".lower()
    return item.get("platform") == "social" or any(word in text for word in GOSSIP)


def sentiment_score(text: str, impact: str = "") -> float:
    lowered = text.lower()
    score = sum(1 for word in POSITIVE if word in lowered) - sum(1 for word in NEGATIVE if word in lowered)
    score += {"contract": 3, "corporate action": 2, "results": 1, "risk": -4}.get(impact.lower(), 0)
    return max(-6, min(6, score))


def direction(score: float) -> str:
    if score >= 2:
        return "Positive watch"
    if score <= -2:
        return "Negative watch"
    return "Neutral watch"


def confidence(score: float, confirmed: int, gossip: int, technical: dict | None) -> int:
    agreement = abs(score) * 7 + confirmed * 7 + (technical or {}).get("confidence", 0) * 0.25 - gossip * 4
    upper = 55 if abs(score) < 2 else 90
    return round(max(20, min(upper, agreement)))


def build_predictions(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    candidates: dict[tuple[str, str], dict] = {}

    def candidate(company: str, symbol: str, exchange: str = "NSE") -> dict:
        key = (exchange, symbol)
        if key not in candidates:
            candidates[key] = {
                "company": company, "symbol": symbol, "exchange": exchange,
                "newsScore": 0.0, "confirmedNewsCount": 0, "gossipCount": 0,
                "catalysts": [], "risks": [], "sources": [], "resultDates": [],
            }
        return candidates[key]

    for item in load_rows("market-news.json"):
        matched = item.get("matchedCompany") or {}
        if not matched.get("symbol"):
            continue
        published = parse_date(item.get("publishedAt", ""))
        if published and published < now - timedelta(days=7):
            continue
        row = candidate(matched.get("company", matched["symbol"]), matched["symbol"], matched.get("exchange", "NSE"))
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        raw_score = sentiment_score(text, item.get("impact", ""))
        gossip = is_gossip(item)
        weight = 0.35 if gossip else 1.0
        age_hours = max(0, (now - published).total_seconds() / 3600) if published else 168
        recency = max(0.35, 1 - age_hours / 240)
        row["newsScore"] += raw_score * weight * recency
        row["gossipCount" if gossip else "confirmedNewsCount"] += 1
        evidence = {"label": item.get("title", "Market story"), "type": item.get("impact", "news"), "verified": not gossip}
        (row["catalysts"] if raw_score >= 0 else row["risks"]).append(evidence)
        if item.get("url"):
            row["sources"].append({"label": item.get("source", "Source"), "url": item["url"], "verified": not gossip})

    for item in load_rows("news.json"):
        published = parse_date(item.get("publishedAt", ""))
        if published and published < now - timedelta(days=14):
            continue
        row = candidate(item.get("company", item["symbol"]), item["symbol"], item.get("exchange", "NSE"))
        text = f"{item.get('headline', '')} {item.get('summary', '')} {item.get('type', '')}"
        score = sentiment_score(text, item.get("type", ""))
        row["newsScore"] += score * 0.75
        row["confirmedNewsCount"] += 1
        evidence = {"label": item.get("headline", "Exchange event"), "type": item.get("type", "event"), "verified": True}
        (row["catalysts"] if score >= 0 else row["risks"]).append(evidence)

    for item in load_rows("results.json"):
        result_date = parse_date(item.get("date", ""))
        if result_date and now.date() <= result_date.date() <= (now + timedelta(days=2)).date():
            row = candidate(item.get("company", item["symbol"]), item["symbol"], item.get("exchange", "NSE"))
            row["resultDates"].append(item["date"])
            row["catalysts"].append({"label": f"{item.get('quarter', 'Quarterly')} results scheduled {item['date']}", "type": "result", "verified": True})

    technical_by_key = {(row.get("exchange", "NSE"), row["symbol"]): row for row in load_rows("stock-analysis.json")}
    for key, technical in technical_by_key.items():
        candidate(technical.get("company", technical["symbol"]), technical["symbol"], technical.get("exchange", "NSE"))

    def ranked(horizon: str) -> list[dict]:
        rows = []
        for key, row in candidates.items():
            if row["confirmedNewsCount"] + row["gossipCount"] == 0 and not row["resultDates"]:
                continue
            technical = technical_by_key.get(key)
            technical_score = float((technical or {}).get("score", 0))
            horizon_score = row["newsScore"] + technical_score * (0.55 if horizon == "today" else 0.8)
            if horizon == "tomorrow" and row["resultDates"]:
                horizon_score += 0.5
            prediction = {
                **{field: row[field] for field in ("company", "symbol", "exchange", "confirmedNewsCount", "gossipCount")},
                "horizon": horizon,
                "direction": direction(horizon_score),
                "predictionScore": round(horizon_score, 1),
                "confidence": confidence(horizon_score, row["confirmedNewsCount"], row["gossipCount"], technical),
                "riskLevel": "High" if row["gossipCount"] > row["confirmedNewsCount"] or abs(horizon_score) < 2 else "Medium" if row["risks"] else "Standard",
                "technicalSignal": (technical or {}).get("signal", "Unavailable"),
                "technicalConfidence": (technical or {}).get("confidence"),
                "lastClose": (technical or {}).get("close"),
                "catalysts": row["catalysts"][:3],
                "risks": row["risks"][:3],
                "sources": row["sources"][:4],
                "reason": "Fresh news and technical indicators agree." if row["newsScore"] * technical_score > 0 else "Mixed news and technical evidence; monitor carefully.",
            }
            rows.append(prediction)
        rows.sort(key=lambda item: (item["confidence"], abs(item["predictionScore"]), item["confirmedNewsCount"]), reverse=True)
        return rows[:12]

    return {
        "generatedAt": now.astimezone().isoformat(timespec="seconds"),
        "method": "Heuristic ranking from recent verified news, downweighted social gossip, exchange events, and technical indicator agreement.",
        "disclaimer": "Research shortlist only. Predictions are not guaranteed and are not investment advice.",
        "today": ranked("today"),
        "tomorrow": ranked("tomorrow"),
    }


def main() -> int:
    try:
        payload = build_predictions()
        DATA_DIR.mkdir(exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        count = len(payload["today"]) + len(payload["tomorrow"])
        STATUS.write_text(json.dumps({"updatedAt": payload["generatedAt"], "recordCount": count, "errors": []}, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {count} today/tomorrow watch predictions to {OUTPUT.relative_to(ROOT)}")
        return 0
    except Exception as error:
        STATUS.write_text(json.dumps({"updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "recordCount": 0, "errors": [str(error)]}, indent=2) + "\n", encoding="utf-8")
        print(f"Prediction job failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
