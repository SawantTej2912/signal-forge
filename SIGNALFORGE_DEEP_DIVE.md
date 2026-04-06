# SignalForge — Complete Technical Deep Dive
### A Real-Time NLP Trade Signal Engine: Architecture, Implementation, and Engineering Decisions

**Author:** Tejas Sawant — MS Applied Data Intelligence, SJSU  
**Repository:** https://github.com/SawantTej2912/signal-forge  
**Stack:** Python · Apache Kafka · PostgreSQL · HuggingFace Transformers · MLflow · FastAPI · React 18 · Recharts · Docker Compose

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Data Ingestion Layer](#3-data-ingestion-layer)
4. [FinBERT Fine-Tuning](#4-finbert-fine-tuning)
5. [Sentiment Consumer & Inference Pipeline](#5-sentiment-consumer--inference-pipeline)
6. [PostgreSQL Schema & Storage](#6-postgresql-schema--storage)
7. [Signal Engine](#7-signal-engine)
8. [Backtester](#8-backtester)
9. [FastAPI Layer](#9-fastapi-layer)
10. [React Frontend](#10-react-frontend)
11. [Docker Compose & Infrastructure](#11-docker-compose--infrastructure)
12. [MLflow Model Registry](#12-mlflow-model-registry)
13. [End-to-End Data Flow](#13-end-to-end-data-flow)
14. [Engineering Challenges & Solutions](#14-engineering-challenges--solutions)
15. [Performance & Metrics](#15-performance--metrics)
16. [What I Would Do Next](#16-what-i-would-do-next)

---

## 1. Project Overview

SignalForge is a production-grade, end-to-end machine learning system that ingests financial news and social media content in real time, scores each piece of text with a fine-tuned FinBERT model, aggregates scores into rolling sentiment signals, and serves those signals through a REST API to an interactive React dashboard.

The system was designed to demonstrate every layer of an applied ML pipeline in a single project: data engineering (Kafka, dual-source ingestion), NLP model development (fine-tuning, MLflow), backend serving (FastAPI), and frontend visualization (React, Recharts, candlestick charts, interactive backtesting).

**Tracked tickers:** AAPL, TSLA, NVDA, MSFT, AMZN, META, GOOGL, AMD

**Key numbers:**
- FinBERT F1: **0.962** (weighted, financial_phrasebank all-agree split)
- FinBERT Accuracy: **0.962**
- Messages processed per pipeline run: **1,000+**
- End-to-end latency (news → scored DB row): **< 30 seconds**
- Best backtest Sharpe Ratio (AMD, lag=1): **2.65**
- Best backtest Total Return (AMD, 90d): **+27.45%**

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│   Finnhub REST API          Reddit Public JSON (/new.json)      │
│   (company news, 7d window) (wsb, stocks, investing, options)   │
└──────────────┬──────────────────────────┬───────────────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ingestion/producer.py                          │
│  • Polls every 5 minutes                                        │
│  • Deduplicates via in-memory seen_ids set                      │
│  • Normalizes to unified Kafka message schema                   │
│  • Publishes to Kafka topic: raw-sentiment                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │  Apache Kafka
                               │  topic: raw-sentiment
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               model/sentiment_consumer.py                       │
│  • Consumes from raw-sentiment topic                            │
│  • Loads fine-tuned FinBERT from local weights                  │
│  • Runs text-classification inference per message               │
│  • Writes (id, ticker, label, score, ...) to PostgreSQL         │
└──────────────────────────────┬──────────────────────────────────┘
                               │  PostgreSQL
                               │  table: scored_sentiment
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              signals/signal_engine.py                           │
│  • Queries scored_sentiment over rolling 24h window             │
│  • Computes weighted sentiment score, normalized [-1, 1]        │
│  • Applies BUY (>0.3) / SELL (<-0.3) / HOLD thresholds         │
│                                                                 │
│              signals/backtester.py                              │
│  • Pulls 90d OHLCV from yfinance                                │
│  • Joins with daily aggregated sentiment                        │
│  • Simulates long-only strategy with variable lag offset        │
│  • Returns equity curve + Sharpe, drawdown, win rate            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     api/main.py (FastAPI)                       │
│  GET /health · /signal · /signals/all · /backtest · /candles    │
└──────────────────────────────┬──────────────────────────────────┘
                               │  HTTP (CORS enabled)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               frontend/src/ (React 18 + Vite)                   │
│  Watchlist · SignalBadge · CandlestickChart · BacktestPanel     │
└─────────────────────────────────────────────────────────────────┘
```

**Infrastructure managed by Docker Compose (7 services):**
Zookeeper → Kafka → PostgreSQL → MLflow → Producer → Consumer  
API and Frontend run on the host machine.

---

## 3. Data Ingestion Layer

**File:** `ingestion/producer.py`

### 3.1 Dual-Source Design

The producer polls two distinct sources on a 5-minute cycle:

**Source 1 — Finnhub (`finnhub_news`):**
- Uses the official `finnhub-python` SDK
- Queries `GET /company-news?symbol={ticker}&from={date}&to={date}` for each of the 8 tickers
- Rolling 7-day lookback window per cycle
- Rate limit: 60 calls/min → 1-second sleep between ticker calls enforced
- Message ID: `finnhub_{article_id}` — stable, prevents re-ingestion

**Source 2 — Reddit (`reddit_post`):**
- Public JSON endpoint: `https://www.reddit.com/r/{subreddit}/new.json?limit=100`
- No credentials, no PRAW (Reddit blocked self-serve PRAW signups in late 2025)
- Custom User-Agent: `signalforge/1.0 (portfolio research)`
- Subreddits: `wallstreetbets`, `stocks`, `investing`, `options`
- Posts are only forwarded if they mention at least one tracked ticker (case-insensitive scan)
- Message ID: `reddit_{post_id}`

### 3.2 Deduplication

An in-memory `seen_ids: set[str]` prevents publishing duplicate messages within a running session. Since the producer uses a 7-day lookback on Finnhub, without deduplication it would re-publish the same articles every cycle.

### 3.3 Kafka Message Schema

Every message published to `raw-sentiment` conforms to:

```json
{
  "id": "finnhub_139609198",
  "source": "finnhub_news",
  "ticker": "TSLA",
  "tickers": ["TSLA"],
  "text": "Tesla cuts prices in China... (max 2000 chars)",
  "created_utc": 1712345678,
  "ingested_at": "2026-04-06T20:06:13Z"
}
```

Text is truncated at 2,000 characters before publishing. The `tickers` array supports Reddit posts that mention multiple tickers — the primary `ticker` field is the first mentioned.

### 3.4 Kafka Producer Config

```python
KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=5,
    acks="all",
)
```

`acks="all"` ensures the broker acknowledges the write before the producer continues — no silent message loss.

---

## 4. FinBERT Fine-Tuning

**File:** `model/finetune_finbert.py`

### 4.1 Base Model

`ProsusAI/finbert` — a BERT-base model pre-trained on financial corpora (Reuters, financial news). Used as the foundation because financial language (e.g., "EPS beat", "revenue miss", "guidance raised") differs significantly from general-purpose text, and ProsusAI/finbert already encodes domain-specific vocabulary.

### 4.2 Dataset

`financial_phrasebank` — `sentences_allagree` split. This is the highest-quality subset: sentences where **all** human annotators agreed on the sentiment label. Approximately 2,200 sentences.

- Label 0: **negative**
- Label 1: **neutral**
- Label 2: **positive**

85/15 train/test split with `seed=42` for reproducibility.

### 4.3 Training Configuration

```python
TrainingArguments(
    num_train_epochs=3,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=32,
    warmup_steps=100,
    weight_decay=0.01,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    fp16=False,
)
```

Key decisions:
- **`load_best_model_at_end=True`**: restores the checkpoint with the highest F1 at the end of training, not necessarily the final epoch
- **`EarlyStoppingCallback(patience=2)`**: halts training if eval F1 doesn't improve for 2 consecutive epochs — prevents overfitting
- **`weight_decay=0.01`**: L2 regularization on transformer weights
- **`fp16=False`**: disabled because training was run on CPU/MPS; fp16 requires CUDA

### 4.4 Tokenization

```python
tokenizer(sentence, truncation=True, padding="max_length", max_length=128)
```

Max length 128 is sufficient for financial_phrasebank sentences (most are under 50 tokens). During inference, the consumer uses `max_length=512` to handle longer news articles and Reddit posts.

### 4.5 Results

| Metric | Value |
|---|---|
| eval_f1 (weighted) | **0.9620** |
| eval_accuracy | **0.9618** |
| eval_loss | logged to MLflow |

These results significantly exceed the >0.85 F1 target. The all-agree split of financial_phrasebank is a relatively clean dataset, which contributes to high performance. The model is saved with `trainer.save_model()` and `tokenizer.save_pretrained()` to `./model/finbert-finetuned/`.

### 4.6 MLflow Logging

Every training run logs:
- **Parameters:** base_model, dataset, epochs, batch_size, warmup_steps, weight_decay
- **Metrics:** eval_f1, eval_accuracy, eval_loss
- **Artifacts:** full model weights + tokenizer files
- **Model registry:** registered as `finbert-signalforge`, alias `@champion` set on best run

---

## 5. Sentiment Consumer & Inference Pipeline

**File:** `model/sentiment_consumer.py`

### 5.1 Architecture

The consumer is a long-running Kafka consumer loop that:
1. Connects to PostgreSQL and ensures the `scored_sentiment` table exists
2. Loads the fine-tuned FinBERT pipeline from disk
3. Reads messages from `raw-sentiment` topic one at a time
4. Runs inference → gets `(label, score)`
5. Writes the result to PostgreSQL with `ON CONFLICT (id) DO NOTHING`

### 5.2 Inference

```python
pipeline(
    "text-classification",
    model=model,
    tokenizer=tokenizer,
    truncation=True,
    max_length=512,
)
```

The HuggingFace `pipeline` abstraction handles tokenization, forward pass, and softmax. The output is a label string (`POSITIVE`/`NEGATIVE`/`NEUTRAL`) and a confidence score (0–1). Labels are lowercased before storage.

### 5.3 Kafka Consumer Config

A critical issue encountered: FinBERT inference takes ~15 seconds per message on CPU. The default Kafka `max_poll_interval_ms=300000` (5 min) was causing the consumer to leave the consumer group when processing large backlogs, producing `Heartbeat poll expired, leaving group` warnings.

Fix:
```python
KafkaConsumer(
    max_poll_interval_ms=600000,   # 10 minutes
    session_timeout_ms=60000,      # 60 seconds
    heartbeat_interval_ms=20000,   # heartbeat every 20s
)
```

### 5.4 Idempotency

`ON CONFLICT (id) DO NOTHING` in the INSERT SQL ensures that if the consumer is restarted or a message is re-delivered, it won't create duplicate rows. The `id` field (e.g., `finnhub_139609198`) is the primary key.

---

## 6. PostgreSQL Schema & Storage

### 6.1 Table: `scored_sentiment`

```sql
CREATE TABLE IF NOT EXISTS scored_sentiment (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    source      TEXT,                      -- finnhub_news | reddit_post
    label       TEXT,                      -- positive | negative | neutral
    score       FLOAT,                     -- confidence 0.0–1.0
    text        TEXT,
    created_utc BIGINT,                    -- Unix timestamp of original content
    inferred_at TIMESTAMP DEFAULT NOW()    -- when FinBERT scored it
);
CREATE INDEX IF NOT EXISTS idx_ticker ON scored_sentiment(ticker);
CREATE INDEX IF NOT EXISTS idx_created ON scored_sentiment(created_utc);
```

### 6.2 Index Strategy

Two indexes:
- `idx_ticker`: the signal engine always filters by ticker — this index makes that O(log n) instead of a full table scan
- `idx_created`: the rolling window query filters by `created_utc >= cutoff` — this index avoids scanning all historical rows on every signal request

### 6.3 PostgreSQL in Docker

Using `postgres:16-alpine` (minimal footprint). Data persisted via named Docker volume `postgres_data` — survives container restarts.

---

## 7. Signal Engine

**File:** `signals/signal_engine.py`

### 7.1 Rolling Window Query

```sql
SELECT label, score
FROM scored_sentiment
WHERE ticker = %s AND created_utc >= %s
```

`created_utc >= now() - window_hours * 3600` — default 24h, configurable up to 168h (7 days) via the API.

### 7.2 Scoring Formula

```python
pos_contribution = count(positive) × avg_confidence(positive)
neg_contribution = count(negative) × avg_confidence(negative)
raw_score = pos_contribution - neg_contribution
normalized = clip(raw_score / total_samples, -1.0, 1.0)
```

This formula rewards both **volume** (more positive articles = higher score) and **confidence** (high-confidence labels weighted more). Dividing by total samples normalizes across tickers with different news volumes.

### 7.3 Thresholds

```
normalized > 0.3   →  BUY
normalized < -0.3  →  SELL
else               →  HOLD
```

### 7.4 Minimum Sample Guard

```python
MIN_SAMPLES = 20
if len(rows) < MIN_SAMPLES:
    return HOLD with score=0.0
```

Prevents spurious signals from 1–2 articles. A signal requires at least 20 scored records in the window.

### 7.5 Output Schema

```json
{
  "ticker": "AAPL",
  "signal": "BUY",
  "sentiment_score": 0.3762,
  "sample_size": 87,
  "window_hours": 24,
  "generated_at": "2026-04-06T20:06:13Z"
}
```

---

## 8. Backtester

**File:** `signals/backtester.py`

### 8.1 Design Philosophy

The backtester's centerpiece feature is the **lag slider** — it simulates the real-world delay between a sentiment signal being generated and a trader acting on it. Dragging the slider from lag=1 to lag=14 visibly shifts the P&L curve, demonstrating that sentiment timing matters.

### 8.2 Data Sources

- **Price data:** `yfinance` — 90-day OHLCV history. Free, 15-minute delayed. Acceptable for portfolio demo.
- **Sentiment data:** Daily aggregated from `scored_sentiment` via SQL GROUP BY date

### 8.3 Daily Sentiment Aggregation

```sql
SELECT
    DATE(TO_TIMESTAMP(created_utc)) AS date,
    SUM(CASE WHEN label = 'positive' THEN score ELSE 0 END) AS pos_sum,
    SUM(CASE WHEN label = 'negative' THEN score ELSE 0 END) AS neg_sum,
    COUNT(*) AS total
FROM scored_sentiment
WHERE ticker = %s AND created_utc >= %s
GROUP BY DATE(TO_TIMESTAMP(created_utc))
ORDER BY date
```

Daily score = `(pos_sum - neg_sum) / total`, clipped to [-1, 1].

### 8.4 Lag Application

```python
sentiment["date"] = sentiment["date"] + pd.Timedelta(days=lag_days)
merged = prices.merge(sentiment, on="date", how="left").ffill()
```

Shifting the sentiment dates forward by `lag_days` simulates "act on today's sentiment `lag` days from now." Forward-fill handles trading days with no new sentiment data.

### 8.5 Strategy Simulation

Simple long-only strategy:
- **Entry:** sentiment_score > 0.3 (BUY signal) and not in position → buy at close price
- **Exit:** sentiment_score ≤ 0.3 (SELL or HOLD) and in position → sell at close price

### 8.6 Metrics Computed

| Metric | Formula |
|---|---|
| Total Return % | `(final_cash - 1.0) × 100` |
| Sharpe Ratio | `(mean_daily_return / std_daily_return) × √252` |
| Max Drawdown % | `min((equity - rolling_max) / rolling_max) × 100` |
| Win Rate % | `winning_trades / total_trades × 100` |

The equity curve (list of `{date, equity}`) is returned to the frontend for the P&L chart.

### 8.7 Output Schema

```json
{
  "ticker": "AMD",
  "lag_days": 1,
  "total_return_pct": 27.45,
  "sharpe_ratio": 2.65,
  "max_drawdown_pct": -7.49,
  "win_rate_pct": 50.0,
  "num_trades": 34,
  "period": "90d",
  "equity_curve": [{"date": "2025-11-24", "equity": 1.0}, ...]
}
```

---

## 9. FastAPI Layer

**File:** `api/main.py`

### 9.1 Endpoints

| Method | Endpoint | Parameters | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| GET | `/signal` | `ticker`, `window_hours=24` | Current signal for one ticker |
| GET | `/signals/all` | `window_hours=24` | Signals for all 8 tickers |
| GET | `/backtest` | `ticker`, `lag=3`, `period=90d` | Backtest metrics + equity curve |
| GET | `/candles` | `ticker`, `period=90d` | OHLCV + per-day signal overlay |

### 9.2 CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Required for the React frontend running on a different port to call the API in development.

### 9.3 `/candles` Endpoint — Design

The candles endpoint was built specifically to power the CandlestickChart component. It:
1. Fetches 90d OHLCV from yfinance via `fetch_prices()`
2. Fetches 90d daily aggregated sentiment via `fetch_sentiment()`
3. Left-merges prices with sentiment on date, forward-fills gaps
4. Applies the same BUY/SELL/HOLD thresholds as the signal engine
5. Returns a list of `{date, open, high, low, close, volume, signal}` — one row per trading day

This gives the frontend everything it needs to draw both the candles and the signal markers in a single API call.

### 9.4 Input Validation

FastAPI's `Query()` with `ge`, `le`, and `pattern` constraints:
```python
lag: int = Query(3, ge=1, le=14)
period: str = Query("90d", pattern=r"^\d+d$")
window_hours: int = Query(24, ge=1, le=168)
```

Invalid inputs return 422 Unprocessable Entity automatically.

---

## 10. React Frontend

**Directory:** `frontend/src/`  
**Stack:** React 18, Vite, Recharts 3.8.1, Axios, TailwindCSS, shadcn/ui components

### 10.1 Component Architecture

```
App.jsx
├── HealthStatus          API heartbeat dot (green/red, polls /health every 30s)
├── Watchlist             All 8 tickers with live scores and signal badges
├── SignalDetail          Current signal for selected ticker (refreshes every 60s)
├── CandlestickChart      90d OHLC candles with BUY/SELL signal overlays
└── BacktestPanel         Lag slider + equity curve + metric cards
```

### 10.2 CandlestickChart — Technical Implementation

This was the most technically complex frontend component. Recharts does not have a native candlestick chart type.

**Approach evaluated and rejected:** Recharts v3 introduced `useXAxisScale()` and `useYAxisScale()` hooks for custom rendering. Initial implementation used these hooks in custom layer components rendered as direct children of `ComposedChart`. This silently failed — the hooks returned `undefined` because the custom components were not rendered within Recharts' internal Redux provider context.

**Final approach:** Used `Bar` with a custom `shape` function. Recharts injects the following into every custom Bar shape:
- `x`, `width` — pixel position and width of this bar's slot
- `background` — `{ x, y, width, height }` of the full plot area rect
- All data props from the row (`open`, `high`, `low`, `close`, `signal`)

With `background.y` and `background.height` known, and `domain={[yMin, yMax]}` explicitly set on the YAxis, any price value can be mapped to a pixel coordinate:

```javascript
const toY = (val) => background.y + background.height * (1 - (val - yMin) / (yMax - yMin))
```

This is defined as a `useCallback` closure that captures `yMin` and `yMax`, so it updates whenever the data changes.

Each candle renders:
1. A `<line>` from `toY(high)` to `toY(low)` — the wick
2. A `<rect>` from `min(toY(open), toY(close))` with height `abs(toY(close)-toY(open))` — the body
3. Green `▲` text below the wick for BUY signals
4. Red `▼` text above the wick for SELL signals

Fill color: `#22c55e` (green) for bullish candles (`close >= open`), `#ef4444` (red) for bearish.

### 10.3 BacktestPanel — Lag Slider

The lag slider is built with shadcn/ui's `Slider` component:

```jsx
<Slider min={1} max={14} step={1} value={[lag]} onValueChange={([v]) => setLag(v)} />
```

Every slider change triggers a new `fetchBacktest(ticker, lag, '90d')` call. The equity curve re-renders in the `AreaChart` below with a gradient fill colored green (positive return) or red (negative). Metric cards update simultaneously showing Sharpe, drawdown, win rate.

### 10.4 API Module

```javascript
// frontend/src/api.js
const api = axios.create({ baseURL: 'http://localhost:8000' })

export const fetchHealth    = () => api.get('/health').then(r => r.data)
export const fetchSignal    = (ticker, windowHours = 24) => ...
export const fetchAllSignals = (windowHours = 24) => ...
export const fetchBacktest  = (ticker, lag, period = '90d') => ...
export const fetchCandles   = (ticker, period = '90d') => ...
```

All API calls are centralized here. Components import only what they need.

---

## 11. Docker Compose & Infrastructure

### 11.1 Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| zookeeper | confluentinc/cp-zookeeper:7.6.1 | — | Kafka coordinator |
| kafka | confluentinc/cp-kafka:7.6.1 | 9092 | Message broker |
| postgres | postgres:16-alpine | 5432 | Sentiment storage |
| mlflow | ghcr.io/mlflow/mlflow:v2.12.2 | 5001 | Experiment tracking |
| producer | signal-forge (custom) | — | Ingestion loop |
| consumer | signal-forge (custom) | — | FinBERT inference loop |

### 11.2 Kafka Listener Configuration

A critical networking detail: Kafka must expose two listeners:
- `PLAINTEXT://localhost:9092` — for the host machine (API, dev tools)
- `PLAINTEXT_INTERNAL://kafka:29092` — for other Docker containers

```yaml
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,PLAINTEXT_INTERNAL://kafka:29092
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_INTERNAL:PLAINTEXT
KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT_INTERNAL
```

Producer and consumer override `KAFKA_BOOTSTRAP_SERVERS=kafka:29092` via environment variables to use the internal listener. Similarly, `POSTGRES_HOST=postgres` overrides localhost.

### 11.3 Dockerfile Design

```dockerfile
FROM python:3.11-slim
RUN pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt . && pip install -r requirements.txt
COPY . .
```

Key decision: **CPU-only PyTorch** (`--index-url https://download.pytorch.org/whl/cpu`). The default `pip install torch` pulls the CUDA build (~2.5GB). The CPU-only build is ~700MB — 72% smaller — and sufficient for inference workloads.

Model weights are baked into the image (`COPY . .` includes `model/finbert-finetuned/`) rather than mounted as a Docker volume. This was necessary because macOS Docker Desktop's VirtioFS bind-mount implementation raises `OSError: [Errno 35] Resource deadlock avoided` when HuggingFace's tokenizer attempts file locking on mounted volumes.

### 11.4 .dockerignore Strategy

```
mlartifacts/          # MLflow artifacts — 14GB+, not needed at runtime
frontend/node_modules/
.git/
mlflow.db
```

`mlartifacts/` was the root cause of an initial 15.34GB build context that crashed Docker's layer export with an I/O error. Excluding it reduced the build context to ~500MB.

### 11.5 Health Checks

Kafka and PostgreSQL have Docker health checks with `condition: service_healthy` dependencies. This ensures the producer and consumer only start after the infrastructure is ready, preventing connection errors on cold start.

---

## 12. MLflow Model Registry

MLflow runs at `http://localhost:5001` backed by SQLite (`mlflow.db`) with artifacts stored in a named Docker volume.

Every fine-tuning run logs:
- Hyperparameters as MLflow params
- eval_f1, eval_accuracy, eval_loss as metrics
- Full model weights as artifacts

The best model is registered as `finbert-signalforge` with alias `@champion`. This alias pattern enables zero-downtime model updates in production — change the alias to point to a new version without changing any code.

---

## 13. End-to-End Data Flow

A complete trace of one piece of data through the system:

1. **10:06:00** — Producer polls Finnhub for TSLA news. Receives article: *"Tesla cuts delivery estimates"*
2. **10:06:01** — Producer constructs message `{id: "finnhub_139609198", ticker: "TSLA", text: "...", created_utc: 1744041600}`
3. **10:06:01** — Message published to Kafka topic `raw-sentiment`, `id` added to `seen_ids`
4. **10:06:15** — Consumer reads message from Kafka
5. **10:06:30** — FinBERT inference: label=`negative`, score=`0.97`
6. **10:06:30** — Row inserted into `scored_sentiment`: `(finnhub_139609198, TSLA, finnhub_news, negative, 0.97, "Tesla cuts...", 1744041600, now())`
7. **10:19:11** — Frontend calls `GET /signal?ticker=TSLA`
8. **10:19:11** — Signal engine queries `scored_sentiment` where `ticker=TSLA` and `created_utc >= now()-86400`
9. **10:19:11** — Computes normalized score from all rows, returns `{signal: "HOLD", sentiment_score: -0.179, sample_size: 47}`
10. **10:19:11** — React renders HOLD badge, score -0.179, samples 47

---

## 14. Engineering Challenges & Solutions

### Challenge 1: 15GB Docker Build Context
**Problem:** First `docker-compose up --build` transferred a 15.34GB build context, crashing mid-export with `sync: input/output error`.  
**Root cause:** `mlartifacts/` directory (MLflow artifact store containing multiple copies of model weights) was not excluded.  
**Solution:** Added `mlartifacts/` to `.dockerignore`. Build context dropped to ~500MB.

### Challenge 2: macOS Docker Volume File Locking
**Problem:** `OSError: [Errno 35] Resource deadlock avoided` when consumer tried to load FinBERT tokenizer from a bind-mounted volume.  
**Root cause:** macOS Docker Desktop's VirtioFS filesystem implementation doesn't support the `flock()` syscall that HuggingFace's tokenizer uses when loading from local paths.  
**Solution:** Removed bind mount, baked model weights into the Docker image via `COPY . .`.

### Challenge 3: Kafka Consumer Group Timeout
**Problem:** `Heartbeat poll expired, leaving group` warnings in consumer logs. Consumer would briefly disconnect from the consumer group during large backlogs.  
**Root cause:** FinBERT inference takes ~15 seconds per message on CPU. Default `max_poll_interval_ms=300000` (5 min) was occasionally exceeded when processing bursts.  
**Solution:** Set `max_poll_interval_ms=600000` (10 min), `session_timeout_ms=60000`, `heartbeat_interval_ms=20000`.

### Challenge 4: Recharts v3 Custom Rendering
**Problem:** CandlestickChart rendered blank — X-axis dates showed but no candles appeared. No console errors.  
**Root cause:** Initial implementation used `useXAxisScale()` and `useYAxisScale()` hooks from Recharts v3 in custom layer components. These hooks require the component to be rendered within Recharts' internal Redux store provider. Components rendered as direct `ComposedChart` children are not in that provider context — hooks returned `undefined` silently.  
**Solution:** Switched to `Bar` with a custom `shape` function. Recharts injects `background` (the plot area bounding rect) and all data props. Manual linear mapping `toY(val) = bgY + bgH * (1 - (val - yMin) / range)` computes pixel coordinates from known domain.

### Challenge 5: Duplicate Training Checkpoints (Disk Space)
**Problem:** Fine-tuning with `save_strategy="epoch"` over 3 epochs saved 3 intermediate checkpoints (checkpoint-121, checkpoint-242, checkpoint-363) at 1.2GB each, plus the final model — 4.1GB total for the model directory.  
**Solution:** Deleted checkpoints post-training. Only `model.safetensors` (418MB), tokenizer files, and config are needed for inference.

### Challenge 6: Kafka Internal vs External Networking
**Problem:** Producer and consumer containers couldn't connect to Kafka — using `localhost:9092` inside Docker resolves to the container's loopback, not the Kafka container.  
**Solution:** Kafka configured with dual listeners (external: `localhost:9092`, internal: `kafka:29092`). Producer/consumer set `KAFKA_BOOTSTRAP_SERVERS=kafka:29092` via Docker environment overrides.

---

## 15. Performance & Metrics

### Model Performance
| Metric | Value | Target |
|---|---|---|
| F1 (weighted) | **0.962** | > 0.85 |
| Accuracy | **0.962** | > 0.88 |
| Dataset | financial_phrasebank all-agree (~2,200 sentences) | — |
| Training time | ~20 min CPU | — |

### Backtest Performance (90-day period)
| Ticker | Lag | Total Return | Sharpe | Max Drawdown | Win Rate |
|---|---|---|---|---|---|
| AMD | 1d | **+27.45%** | **2.65** | -7.49% | 50.0% |
| AMD | 3d | -5.36% | -0.19 | -29.11% | 50.0% |

*The lag slider demo — showing AMD's return shifting from +27% to -5% as lag increases from 1→3 — is the centerpiece of the interactive demo.*

### Pipeline Throughput
| Metric | Value |
|---|---|
| Messages per first cycle | 1,455 |
| Consumer throughput | ~10 messages / 2 min (CPU FinBERT) |
| Producer poll interval | 5 minutes |
| Signal refresh interval | 60 seconds (frontend) |

---

## 16. What I Would Do Next

1. **GPU inference in Docker** — Replace CPU-only torch with CUDA build, add `deploy: resources: reservations: devices:` GPU config to docker-compose. Would reduce inference from ~15s to ~0.5s per message.

2. **Batch inference** — Instead of scoring messages one-at-a-time, batch them in groups of 32 before writing to Postgres. Would dramatically increase consumer throughput.

3. **Redis caching** — Cache `/signal` responses with a 60-second TTL. Current implementation queries Postgres on every API call.

4. **FinBERT quantization** — INT8 quantization via `torch.quantization` would halve model size (418MB → ~200MB) with minimal accuracy loss.

5. **Real-time WebSocket** — Replace the frontend's 60-second polling with a WebSocket connection pushing signal updates as they're computed.

6. **Expand tickers** — The architecture is ticker-agnostic. Adding more tickers requires only appending to the `TICKERS` list.

7. **Short selling** — Current backtester is long-only. Adding a short leg on SELL signals would make the strategy more complete.

8. **Multi-source sentiment fusion** — Weight Finnhub (professional news) higher than Reddit (retail noise) in the signal computation.

---

## Appendix: File Structure

```
signal-forge/
├── api/
│   └── main.py                   FastAPI: /health, /signal, /signals/all, /backtest, /candles
├── ingestion/
│   └── producer.py               Dual-source Kafka producer (Finnhub + Reddit)
├── model/
│   ├── finetune_finbert.py       HuggingFace fine-tuning + MLflow logging
│   ├── sentiment_consumer.py     Kafka → FinBERT → PostgreSQL
│   ├── mlflow_utils.py           Model registry helpers
│   └── finbert-finetuned/        Saved model weights (model.safetensors + tokenizer)
├── signals/
│   ├── signal_engine.py          Rolling window aggregation → BUY/SELL/HOLD
│   └── backtester.py             yfinance prices + sentiment + lag → P&L metrics
├── frontend/
│   └── src/
│       ├── App.jsx               Root layout
│       ├── api.js                Axios API client
│       └── components/
│           ├── Watchlist.jsx     8-ticker sidebar with live scores
│           ├── SignalBadge.jsx   BUY/SELL/HOLD badge component
│           ├── SignalDetail.jsx  Current signal panel (score, samples, window)
│           ├── CandlestickChart.jsx  OHLC candles + signal overlays (custom Bar shape)
│           ├── BacktestPanel.jsx Equity curve + lag slider + metric cards
│           └── HealthStatus.jsx  API liveness indicator
├── docker-compose.yml            7-service orchestration
├── Dockerfile                    Python 3.11-slim + CPU torch + requirements
├── requirements.txt
├── .env                          Secrets (gitignored)
├── .env.example                  Template for new contributors
├── .dockerignore
├── .gitignore
├── README.md
├── README_assets/demo.gif
└── SIGNALFORGE_DEEP_DIVE.md      This document
```

---

*This document covers every engineering decision, failure encountered, and solution implemented in building SignalForge from scratch. The system is fully operational at the time of writing with live ingestion, real-time FinBERT scoring, and an interactive dashboard serving historical backtests and live trade signals.*
