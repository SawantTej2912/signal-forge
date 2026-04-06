"""
Kafka consumer: reads raw-sentiment topic → runs FinBERT inference → writes to PostgreSQL.

Usage:
    python model/sentiment_consumer.py
"""

import json
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from kafka import KafkaConsumer
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "raw-sentiment"
KAFKA_GROUP_ID = "sentiment-consumer"

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "signalforge")
POSTGRES_USER = os.getenv("POSTGRES_USER", "signalforge")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "signalforge123")

MODEL_PATH = os.path.abspath("./model/finbert-finetuned")

ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}

INSERT_SQL = """
INSERT INTO scored_sentiment (id, ticker, source, label, score, text, created_utc, inferred_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING;
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scored_sentiment (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    source      TEXT,
    label       TEXT,
    score       FLOAT,
    text        TEXT,
    created_utc BIGINT,
    inferred_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ticker ON scored_sentiment(ticker);
CREATE INDEX IF NOT EXISTS idx_created ON scored_sentiment(created_utc);
"""


def connect_db():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    conn.autocommit = True
    return conn


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    log.info("scored_sentiment table ready.")


def load_pipeline():
    log.info("Loading FinBERT from %s ...", MODEL_PATH)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    clf = pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        truncation=True,
        max_length=512,
    )
    log.info("FinBERT loaded.")
    return clf


def classify(clf, text: str) -> tuple[str, float]:
    result = clf(text[:512])[0]
    label = result["label"].lower()  # POSITIVE / NEGATIVE / NEUTRAL → lowercase
    score = round(result["score"], 4)
    return label, score


def run():
    conn = connect_db()
    ensure_table(conn)
    clf = load_pipeline()

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        max_poll_interval_ms=600000,   # 10 min — gives FinBERT time between polls
        session_timeout_ms=60000,      # 60s session timeout
        heartbeat_interval_ms=20000,   # heartbeat every 20s
    )

    log.info("Consuming from topic '%s' ...", KAFKA_TOPIC)
    processed = 0

    for message in consumer:
        msg = message.value
        msg_id = msg.get("id", "")
        text = msg.get("text", "")

        if not text:
            continue

        try:
            label, score = classify(clf, text)
        except Exception as exc:
            log.warning("Inference error for %s: %s", msg_id, exc)
            continue

        with conn.cursor() as cur:
            cur.execute(INSERT_SQL, (
                msg_id,
                msg.get("ticker", ""),
                msg.get("source", ""),
                label,
                score,
                text[:2000],
                msg.get("created_utc"),
                datetime.now(timezone.utc),
            ))

        processed += 1
        if processed % 10 == 0:
            log.info("Processed %d messages. Last: %s → %s (%.2f)", processed, msg_id, label, score)


if __name__ == "__main__":
    run()
