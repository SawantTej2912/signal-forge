"""
Signal engine: queries scored_sentiment over a rolling window and
produces a BUY / SELL / HOLD signal.

Usage (CLI):
    python signals/signal_engine.py --ticker TSLA
    python signals/signal_engine.py --ticker TSLA --window_hours 48
"""

import argparse
import os
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "signalforge")
POSTGRES_USER = os.getenv("POSTGRES_USER", "signalforge")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "signalforge123")

BUY_THRESHOLD = 0.3
SELL_THRESHOLD = -0.3
MIN_SAMPLES = 20


def get_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def compute_signal(ticker: str, window_hours: int = 24) -> dict:
    cutoff_utc = int(time.time()) - window_hours * 3600

    query = """
        SELECT label, score
        FROM scored_sentiment
        WHERE ticker = %s AND created_utc >= %s
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, (ticker, cutoff_utc))
            rows = cur.fetchall()

    if not rows or len(rows) < MIN_SAMPLES:
        return {
            "ticker": ticker,
            "signal": "HOLD",
            "sentiment_score": 0.0,
            "sample_size": len(rows),
            "window_hours": window_hours,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    pos_scores = [r["score"] for r in rows if r["label"] == "positive"]
    neg_scores = [r["score"] for r in rows if r["label"] == "negative"]

    pos_contribution = len(pos_scores) * (sum(pos_scores) / len(pos_scores)) if pos_scores else 0.0
    neg_contribution = len(neg_scores) * (sum(neg_scores) / len(neg_scores)) if neg_scores else 0.0

    raw_score = pos_contribution - neg_contribution

    # Normalize to [-1, 1] using total sample count
    total = len(rows)
    normalized = max(-1.0, min(1.0, raw_score / total)) if total > 0 else 0.0

    if normalized > BUY_THRESHOLD:
        signal = "BUY"
    elif normalized < SELL_THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "ticker": ticker,
        "signal": signal,
        "sentiment_score": round(normalized, 4),
        "sample_size": total,
        "window_hours": window_hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--window_hours", type=int, default=24)
    args = parser.parse_args()

    result = compute_signal(args.ticker, args.window_hours)
    print(result)
