"""
Dual-source Kafka producer.
Polls Finnhub (company news) + Reddit (4 subreddits) every 5 minutes.
Publishes normalized JSON messages to the 'raw-sentiment' topic.
"""

import json
import time
import logging
import hashlib
from datetime import datetime, timezone

import finnhub
import requests
from kafka import KafkaProducer
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]
SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options"]
KAFKA_TOPIC = "raw-sentiment"
POLL_INTERVAL = 300  # 5 minutes

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        retries=5,
        acks="all",
    )


# ---------------------------------------------------------------------------
# Finnhub
# ---------------------------------------------------------------------------

def fetch_finnhub(client: finnhub.Client, ticker: str) -> list[dict]:
    """Return normalized messages from Finnhub company-news for one ticker."""
    try:
        news_items = client.company_news(ticker, _from="2020-01-01", to="2099-01-01")
    except Exception as exc:
        log.warning("Finnhub error for %s: %s", ticker, exc)
        return []

    messages = []
    for item in news_items:
        text = f"{item.get('headline', '')} {item.get('summary', '')}".strip()
        if not text:
            continue
        msg_id = f"finnhub_{item.get('id', hashlib.md5(text.encode()).hexdigest()[:8])}"
        messages.append({
            "id": msg_id,
            "source": "finnhub_news",
            "ticker": ticker,
            "tickers": [ticker],
            "text": text[:2000],
            "created_utc": item.get("datetime", int(time.time())),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        })
    return messages


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------

REDDIT_HEADERS = {"User-Agent": "signalforge/1.0 (portfolio research)"}


def fetch_reddit(subreddit: str) -> list[dict]:
    """Return normalized messages from a subreddit's /new feed."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
    try:
        resp = requests.get(url, headers=REDDIT_HEADERS, timeout=10)
        resp.raise_for_status()
        posts = resp.json()["data"]["children"]
    except Exception as exc:
        log.warning("Reddit error for r/%s: %s", subreddit, exc)
        return []

    messages = []
    for post in posts:
        data = post["data"]
        title = data.get("title", "")
        selftext = data.get("selftext", "")
        text = f"{title} {selftext}".strip()

        # Only forward posts that mention at least one tracked ticker
        mentioned = [t for t in TICKERS if t.upper() in text.upper()]
        if not mentioned:
            continue

        post_id = data.get("id", hashlib.md5(text.encode()).hexdigest()[:8])
        messages.append({
            "id": f"reddit_{post_id}",
            "source": "reddit_post",
            "ticker": mentioned[0],
            "tickers": mentioned,
            "text": text[:2000],
            "created_utc": int(data.get("created_utc", time.time())),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        })
    return messages


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    log.info("Starting SignalForge producer. Kafka: %s", KAFKA_BOOTSTRAP_SERVERS)
    producer = make_producer()
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

    seen_ids: set[str] = set()

    while True:
        cycle_start = time.time()
        published = 0

        # --- Finnhub ---
        for ticker in TICKERS:
            messages = fetch_finnhub(finnhub_client, ticker)
            for msg in messages:
                if msg["id"] not in seen_ids:
                    producer.send(KAFKA_TOPIC, value=msg)
                    seen_ids.add(msg["id"])
                    published += 1
            time.sleep(1)  # respect 60 calls/min rate limit

        # --- Reddit ---
        for sub in SUBREDDITS:
            messages = fetch_reddit(sub)
            for msg in messages:
                if msg["id"] not in seen_ids:
                    producer.send(KAFKA_TOPIC, value=msg)
                    seen_ids.add(msg["id"])
                    published += 1
            time.sleep(1)

        producer.flush()
        elapsed = time.time() - cycle_start
        log.info("Cycle complete — published %d new messages in %.1fs", published, elapsed)

        sleep_time = max(0, POLL_INTERVAL - elapsed)
        log.info("Sleeping %.0fs until next cycle...", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    run()
