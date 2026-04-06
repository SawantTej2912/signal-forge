"""
Backfill script: fetch last N days of Finnhub news for all 8 tickers,
run FinBERT inference, and insert into scored_sentiment.

Runs directly against Postgres — no Kafka needed.
Run once before starting the API:
    python scripts/backfill.py
    python scripts/backfill.py --days 30
"""

import argparse
import hashlib
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import finnhub
import psycopg2
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Resolve paths relative to repo root regardless of cwd
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
MODEL_PATH = os.path.join(REPO_ROOT, "model", "finbert-finetuned")

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]

FINNHUB_API_KEY   = os.getenv("FINNHUB_API_KEY")
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


def connect_db():
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD,
    )
    conn.autocommit = True
    return conn


def load_finbert():
    log.info("Loading FinBERT from %s …", MODEL_PATH)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    clf = pipeline("text-classification", model=model, tokenizer=tokenizer,
                   truncation=True, max_length=512)
    log.info("FinBERT ready.")
    return clf


def fetch_finnhub_news(client: finnhub.Client, ticker: str, days: int) -> list[dict]:
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")
    try:
        items = client.company_news(ticker, _from=date_from, to=date_to)
    except Exception as exc:
        log.warning("Finnhub error %s: %s", ticker, exc)
        return []

    rows = []
    for item in items:
        text = f"{item.get('headline', '')} {item.get('summary', '')}".strip()
        if not text:
            continue
        msg_id = f"finnhub_{item.get('id', hashlib.md5(text.encode()).hexdigest()[:8])}"
        rows.append({
            "id":          msg_id,
            "ticker":      ticker,
            "source":      "finnhub_news",
            "text":        text[:2000],
            "created_utc": item.get("datetime", int(time.time())),
        })
    return rows


def run(days: int = 30):
    conn   = connect_db()
    clf    = load_finbert()
    client = finnhub.Client(api_key=FINNHUB_API_KEY)

    total_inserted = 0

    for ticker in TICKERS:
        log.info("Fetching %s — last %d days …", ticker, days)
        rows = fetch_finnhub_news(client, ticker, days)
        log.info("  %d articles from Finnhub", len(rows))

        inserted = 0
        for row in rows:
            try:
                result = clf(row["text"][:512])[0]
                label  = result["label"].lower()
                score  = round(result["score"], 4)
            except Exception as exc:
                log.warning("  Inference error for %s: %s", row["id"], exc)
                continue

            with conn.cursor() as cur:
                cur.execute(INSERT_SQL, (
                    row["id"], row["ticker"], row["source"],
                    label, score, row["text"],
                    row["created_utc"], datetime.now(timezone.utc),
                ))
                if cur.rowcount:
                    inserted += 1

        log.info("  Inserted %d new rows for %s", inserted, ticker)
        total_inserted += inserted
        time.sleep(1)  # Finnhub rate limit

    log.info("Backfill complete — %d total rows inserted.", total_inserted)

    # Summary
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, COUNT(*) as n,
                   MIN(TO_TIMESTAMP(created_utc)::date) as earliest,
                   MAX(TO_TIMESTAMP(created_utc)::date) as latest
            FROM scored_sentiment
            GROUP BY ticker ORDER BY ticker
        """)
        rows = cur.fetchall()

    log.info("%-8s  %5s  %s  %s", "TICKER", "COUNT", "EARLIEST", "LATEST")
    for r in rows:
        log.info("%-8s  %5d  %s  %s", *r)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30,
                        help="How many days of history to backfill (default: 30)")
    args = parser.parse_args()
    run(args.days)
