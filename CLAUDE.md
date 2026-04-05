# SignalForge — Agent Context

**Purpose:** Single source of truth for architecture, data flows, APIs, and non-obvious decisions. When stuck, consult this file first.

---

## Pause Protocol

Two tags signal when user action is required:

> 🛑 **PAUSE** — User must complete a step before agent resumes (API key signup, long training jobs, recording demo)
>
> ✅ **RESUMES** — Condition that triggers agent to continue

---

## Project Identity

| Field | Value |
|---|---|
| **Name** | SignalForge |
| **Scope** | Full-stack ML end-to-end portfolio |
| **Goal** | Real-time NLP trade signal engine → AI/ML internship applications |
| **Owner** | Tejas (MS Applied Data Intelligence, SJSU) |
| **Timeline** | ~7 days |

**Resume headline:**
> Built SignalForge, a real-time NLP trade signal engine: Finnhub + Reddit dual-source → fine-tuned FinBERT (F1: X on financial_phrasebank) → FastAPI signals → React dashboard with interactive backtesting; MLflow tracking.

---

## Architecture

```
Finnhub News + Reddit Posts
    ↓ (Kafka: raw-sentiment topic)
FinBERT Inference Pipeline
    ↓ (PostgreSQL: scored_sentiment table)
Signal Engine (rolling 24h window)
    ↓
FastAPI (/signal, /backtest, /health)
    ↓
React Dashboard (lag slider, candlesticks, P&L chart)
```

**Folder structure:**
```
signalforge/
├── ingestion/producer.py         (Finnhub + Reddit → Kafka)
├── model/
│   ├── finetune_finbert.py       (HF fine-tuning)
│   ├── sentiment_consumer.py     (Kafka → FinBERT → PostgreSQL)
│   └── mlflow_utils.py           (model registry)
├── signals/
│   ├── signal_engine.py          (rolling window → BUY/SELL/HOLD)
│   └── backtester.py             (lag window + P&L metrics)
├── api/main.py                   (FastAPI endpoints)
├── frontend/src/                 (React + Recharts)
├── docker-compose.yml
├── requirements.txt
├── .env                          (secrets — add to .gitignore)
└── tests/
```

---

## Data Sources

### Finnhub (Primary)

- **Signup:** finnhub.io → free tier, instant API key
- **Rate:** 60 calls/min (use 1s sleep between tickers, 5min poll cycle)
- **Endpoint:** `GET /company-news?symbol={TICKER}&token={key}`

> 🛑 **PAUSE**
> Go to **finnhub.io**, sign up, copy API key → add to `.env` as `FINNHUB_API_KEY=`
>
> ✅ **RESUMES** when: *"Finnhub key added"*

### Reddit (Secondary)

- **No credentials needed.** Use public JSON: `https://www.reddit.com/r/{subreddit}/new.json?limit=100`
- **Critical:** Reddit blocked PRAW self-serve signup in Nov 2025. DO NOT attempt PRAW.
- **Headers:** `{"User-Agent": "signalforge/1.0 (portfolio research)"}`
- **Subreddits:** `wallstreetbets`, `stocks`, `investing`, `options`
- **Filter:** Only forward posts mentioning tracked tickers

### Tracked Tickers
```python
TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]
```

---

## Kafka Message Schema

```json
{
  "id": "finnhub_12345 | reddit_abc123",
  "source": "finnhub_news | reddit_post",
  "ticker": "TSLA",
  "tickers": ["TSLA", "NVDA"],
  "text": "...(max 2000 chars)",
  "created_utc": 1712345678,
  "ingested_at": "2026-04-04T20:00:00Z"
}
```

**Topic:** `raw-sentiment` (auto-created)

---

## FinBERT Fine-Tuning

- **Model:** `ProsusAI/finbert` (HuggingFace)
- **Dataset:** `financial_phrasebank` (all-agree split, ~2200 sentences)
- **Classes:** 0=negative, 1=neutral, 2=positive
- **Config:** 3 epochs, batch=16, warmup=100, weight_decay=0.01
- **Target:** F1 > 0.85
- **MLflow:** All runs logged. Best model registered as `finbert-signalforge`, set alias `@champion`

> 🛑 **PAUSE**
> Run: `python model/finetune_finbert.py` (20–40 min CPU, ~5 min GPU)
> Open MLflow UI at `http://localhost:5001` → Model Registry → set `@champion` alias
>
> ✅ **RESUMES** when: *"Fine-tuning complete, @champion alias set"*

See `.claude/skills/finbert-finetuning.md` for full workflow.

---

## PostgreSQL: `scored_sentiment` Table

```sql
CREATE TABLE scored_sentiment (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    source      TEXT,
    label       TEXT,              -- positive | negative | neutral
    score       FLOAT,
    text        TEXT,
    created_utc BIGINT,
    inferred_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ticker ON scored_sentiment(ticker);
CREATE INDEX idx_created ON scored_sentiment(created_utc);
```

See `.claude/skills/db-setup.md` for creation workflow.

---

## Signal Engine

**Logic:**
1. Query `scored_sentiment` for ticker over 24h rolling window
2. Score = (positive_count × avg_confidence) − (negative_count × avg_confidence)
3. Normalize to [-1, 1]
4. Apply thresholds:
   - score > 0.3 → **BUY**
   - score < -0.3 → **SELL**
   - else → **HOLD**

**Output schema:**
```python
{
    "ticker": "TSLA",
    "signal": "BUY",
    "sentiment_score": 0.67,
    "sample_size": 42,
    "window_hours": 24,
    "generated_at": "2026-04-04T21:00:00Z"
}
```

---

## Backtester

**Inputs:** ticker, lag_days (1–14), yfinance historical prices, scored_sentiment records

**Key insight:** Lag slider is the **demo centerpiece**. Dragging from lag=1→7 visibly shifts P&L curve, showing sentiment timing matters.

**Output schema:**
```python
{
    "ticker": "TSLA",
    "lag_days": 3,
    "total_return_pct": 18.4,
    "sharpe_ratio": 1.23,
    "max_drawdown_pct": -7.2,
    "win_rate_pct": 61.0,
    "num_trades": 34,
    "period": "90d"
}
```

---

## FastAPI Layer

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /signal?ticker=TSLA` | Current signal + sentiment score |
| `GET /signal?ticker=TSLA&window_hours=48` | Custom window |
| `GET /backtest?ticker=TSLA&lag=3` | Backtest metrics |
| `GET /backtest?ticker=TSLA&lag=3&period=90d` | Custom period |

**Important:** Enable CORS in dev:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
```

Load model at startup via MLflow:
```python
@app.on_event("startup")
async def load_model():
    model = mlflow.transformers.load_model("models:/finbert-signalforge@champion")
```

---

## React Frontend

**Stack:** React 18 + Vite, Recharts, Axios, TailwindCSS

**Three components:**
- **CandlestickChart** — OHLC price + signal dots (green=BUY, red=SELL, gray=HOLD)
- **BacktestPanel** — P&L curve + lag slider (1–14) + metric cards (Sharpe, drawdown, win rate)
- **SignalBadge** — Large BUY/SELL/HOLD badge, refreshes every 60s

> 🛑 **PAUSE**
> Open `http://localhost:3000` → pick TSLA → record 15s screen capture dragging lag slider 1→14
> Save as `README_assets/demo.gif`
>
> ✅ **RESUMES** when: *"demo.gif saved"*

See `.claude/skills/demo-script.md` for interview walkthrough.

---

## Docker Compose

8 services: zookeeper, kafka, postgres, mlflow, producer, consumer, api (8000), frontend (3000)

Verify with: `docker ps` and `docker logs <service>`

---

## Environment Variables (`.env`)

```bash
FINNHUB_API_KEY=...
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=signalforge
POSTGRES_USER=signalforge
POSTGRES_PASSWORD=signalforge123
MLFLOW_TRACKING_URI=http://localhost:5001
API_HOST=0.0.0.0
API_PORT=8000
```

**Never commit `.env`. Load via `python-dotenv`.**

---

## Known Gotchas

| Issue | Fix |
|---|---|
| Reddit PRAW doesn't work | Use public JSON endpoint. Never attempt PRAW for this project. |
| FinBERT OOM on CPU | Reduce batch_size to 8 in TrainingArguments |
| MLflow model not found | Ensure `MLFLOW_TRACKING_URI` matches training env. Always use `@champion` alias. |
| React CORS error | FastAPI needs `CORSMiddleware` with `allow_origins=["*"]` |
| Kafka consumer lagging | Check offset with `kafka-consumer-groups.sh`. Run multiple instances if needed. |
| yfinance 15min delay | Acceptable for portfolio project |
| Docker volume conflicts | Run `docker-compose down -v` to reset Postgres schema |

---

## Metrics to Capture

| Metric | Target |
|---|---|
| FinBERT F1 on financial_phrasebank | > 0.85 |
| FinBERT accuracy | > 88% |
| Backtest Sharpe (best ticker) | > 1.0 |
| End-to-end latency (news → signal) | < 30s |

---

## Git Workflow

Create clean commit history with day-based branches:

```bash
git init
git add .
git commit -m "init: SignalForge scaffold"
git checkout -b day1-ingestion
# ... work on day 1 ...
git commit -m "feat: dual-source Kafka producer"
git checkout -b day2-finbert
# ... etc.
```

Push to GitHub when complete. Recruiters review commit logs.

---

## Quick Links

- **Fine-tuning workflow:** `.claude/skills/finbert-finetuning.md`
- **Database setup:** `.claude/skills/db-setup.md`
- **Interview demo script:** `.claude/skills/demo-script.md`
- **Day-by-day build plan:** See git log + original CLAUDE.md v1 if needed

---

*Last updated: April 2026. Consult this file for architecture, data sources, and non-obvious decisions.*
