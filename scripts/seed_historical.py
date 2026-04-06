"""
Seed 90 days of synthetic sentiment data into scored_sentiment.

Generates per-day sentiment that correlates with the NEXT day's price return,
so lag=1 captures the best signal and P&L degrades as lag increases —
making the lag slider demo visually compelling.

Usage:
    python scripts/seed_historical.py
    python scripts/seed_historical.py --days 90 --articles-per-day 25
"""

import argparse
import hashlib
import logging
import os
import random
import sys
from datetime import datetime, timezone

import numpy as np
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB       = os.getenv("POSTGRES_DB", "signalforge")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "signalforge")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "signalforge123")

INSERT_SQL = """
INSERT INTO scored_sentiment (id, ticker, source, label, score, text, created_utc, inferred_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING;
"""

LABEL_TEMPLATES = {
    "positive": [
        "{ticker} shows strong momentum as analysts raise price targets.",
        "{ticker} beats earnings expectations, stock rallies in after-hours.",
        "Analysts upgrade {ticker} to buy citing strong demand outlook.",
        "{ticker} reports record revenue, market reacts positively.",
        "Institutional investors increase {ticker} holdings significantly.",
    ],
    "negative": [
        "{ticker} misses revenue estimates, shares drop on heavy volume.",
        "Analysts cut {ticker} price target amid macro uncertainty.",
        "{ticker} faces headwinds as competition intensifies.",
        "Regulatory concerns weigh on {ticker} outlook.",
        "{ticker} guidance disappoints investors, stock under pressure.",
    ],
    "neutral": [
        "{ticker} announces board meeting scheduled for next quarter.",
        "Analysts maintain {ticker} hold rating ahead of earnings.",
        "{ticker} files routine SEC disclosure.",
        "Market participants watch {ticker} closely ahead of Fed decision.",
        "{ticker} trading in line with sector peers today.",
    ],
}


def connect_db():
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD,
    )
    conn.autocommit = True
    return conn


def next_day_return(prices: "pd.DataFrame", date) -> float:
    """Return the next trading day's close-to-close return, or 0 if unavailable."""
    import pandas as pd
    dates = prices.index.normalize()
    try:
        loc = dates.get_loc(pd.Timestamp(date))
    except KeyError:
        return 0.0
    if loc + 1 >= len(prices):
        return 0.0
    ret = (prices.iloc[loc + 1]["Close"] - prices.iloc[loc]["Close"]) / prices.iloc[loc]["Close"]
    return float(ret)


def generate_day_sentiment(ticker: str, date, ret: float, n: int, rng: random.Random):
    """
    Generate n synthetic sentiment records for ticker on date.

    Sentiment distribution is driven by next-day return so that lag=1 is
    the optimal lag and longer lags produce measurably different P&L.

    ret > +1%  → ~70% positive, 10% negative
    ret < -1%  → ~10% positive, 70% negative
    else       → ~40% positive, 25% negative (mild positive bias)
    """
    if ret > 0.01:
        weights = {"positive": 0.70, "negative": 0.10, "neutral": 0.20}
    elif ret < -0.01:
        weights = {"positive": 0.10, "negative": 0.70, "neutral": 0.20}
    else:
        weights = {"positive": 0.40, "negative": 0.25, "neutral": 0.35}

    labels = rng.choices(
        list(weights.keys()),
        weights=list(weights.values()),
        k=n,
    )

    # Spread articles across the trading day (9:30 AM – 4:00 PM ET = 13:30–20:00 UTC)
    day_start = int(datetime(date.year, date.month, date.day, 13, 30, tzinfo=timezone.utc).timestamp())
    day_end   = int(datetime(date.year, date.month, date.day, 20,  0, tzinfo=timezone.utc).timestamp())

    rows = []
    for i, label in enumerate(labels):
        template = rng.choice(LABEL_TEMPLATES[label])
        text = template.format(ticker=ticker)
        ts   = rng.randint(day_start, day_end)

        # Score: high confidence when signal is strong, noisier when neutral
        if label == "neutral":
            score = round(rng.uniform(0.50, 0.75), 4)
        else:
            score = round(rng.uniform(0.65, 0.97), 4)

        uid = hashlib.md5(f"synthetic_{ticker}_{date}_{i}".encode()).hexdigest()[:12]
        msg_id = f"synthetic_{uid}"
        rows.append((msg_id, ticker, "synthetic", label, score, text, ts,
                     datetime.now(timezone.utc)))
    return rows


def run(days: int = 90, articles_per_day: int = 25):
    import pandas as pd

    conn = connect_db()
    rng  = random.Random(42)  # reproducible

    total_inserted = 0

    for ticker in TICKERS:
        log.info("Seeding %s …", ticker)
        hist = yf.Ticker(ticker).history(period=f"{days + 5}d")
        if hist.empty:
            log.warning("  No price data for %s, skipping.", ticker)
            continue

        hist.index = hist.index.tz_localize(None)
        trading_days = hist.index.normalize().unique()

        inserted = 0
        for date in trading_days[-(days):]:
            ret   = next_day_return(hist, date)
            n     = rng.randint(max(1, articles_per_day - 5), articles_per_day + 5)
            batch = generate_day_sentiment(ticker, date, ret, n, rng)

            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, batch)
                inserted += sum(1 for b in batch if True)  # executemany doesn't return rowcount reliably

        log.info("  Seeded ~%d articles for %s", inserted, ticker)
        total_inserted += inserted

    log.info("Seed complete — ~%d articles across %d tickers.", total_inserted, len(TICKERS))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, COUNT(*) as n,
                   MIN(TO_TIMESTAMP(created_utc)::date) as earliest,
                   MAX(TO_TIMESTAMP(created_utc)::date) as latest
            FROM scored_sentiment GROUP BY ticker ORDER BY ticker
        """)
        for r in cur.fetchall():
            log.info("%-8s  %5d rows  %s → %s", *r)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",             type=int, default=90)
    parser.add_argument("--articles-per-day", type=int, default=25)
    args = parser.parse_args()
    run(args.days, args.articles_per_day)
