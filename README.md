# SignalForge

**Real-time NLP trade signal engine** — dual-source sentiment ingestion → fine-tuned FinBERT inference → FastAPI signals → React dashboard with interactive backtesting.

Built as a full-stack ML portfolio project by **Tejas Sawant** (MS Applied Data Intelligence, SJSU).

---

![SignalForge Demo](README_assets/demo.gif)

---

## Architecture

```
Finnhub News + Reddit Posts
        ↓  (Kafka: raw-sentiment topic)
  FinBERT Inference Pipeline
        ↓  (PostgreSQL: scored_sentiment)
    Signal Engine  (rolling 24h window)
        ↓
  FastAPI  (/signal · /backtest · /candles)
        ↓
  React Dashboard  (watchlist · candlesticks · lag slider)
```

**Stack:** Python · FastAPI · Kafka · PostgreSQL · HuggingFace Transformers · MLflow · React 18 · Recharts · Docker Compose

---

## Features

| Feature | Detail |
|---|---|
| **Dual-source ingestion** | Finnhub company news + Reddit (wsb, stocks, investing, options) via public JSON |
| **Fine-tuned FinBERT** | `ProsusAI/finbert` fine-tuned on `financial_phrasebank` (all-agree split) |
| **Signal engine** | Rolling 24h window → normalized sentiment score → BUY / SELL / HOLD |
| **Interactive backtester** | Lag slider 1→14 days — dragging visibly shifts the P&L curve |
| **Candlestick chart** | 90d OHLC with per-candle BUY/SELL signal overlay |
| **MLflow tracking** | All training runs logged; best model registered as `finbert-signalforge@champion` |
| **Full Docker Compose** | One command starts all 7 services |

---

## Model Performance

| Metric | Value |
|---|---|
| Dataset | `financial_phrasebank` all-agree split (~2,200 sentences) |
| Classes | positive · neutral · negative |
| Training | 3 epochs, batch=16, warmup=100, weight_decay=0.01 |
| Base model | `ProsusAI/finbert` |
| **F1 score** | **0.962** |
| **Accuracy** | **0.962** |

---

## Backtest Results (sample — AMD, 90d)

| Metric | Value |
|---|---|
| Best Sharpe (lag=1) | 2.65 |
| Total Return | +27.45% |
| Max Drawdown | −7.49% |
| Win Rate | 50.0% |

> Drag the lag slider from 1→14 in the dashboard to see how sentiment timing impacts P&L.

---

## Quick Start

### Prerequisites
- Docker Desktop
- Finnhub API key (free at [finnhub.io](https://finnhub.io))

### 1. Clone & configure

```bash
git clone https://github.com/SawantTej2912/signal-forge.git
cd signal-forge
cp .env.example .env
# Add your FINNHUB_API_KEY to .env
```

### 2. Start everything

```bash
docker-compose up -d
```

This starts: Zookeeper · Kafka · PostgreSQL · MLflow · Producer · Consumer

### 3. Start the API

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Service health check |
| `GET /signal?ticker=TSLA` | Current BUY/SELL/HOLD signal + sentiment score |
| `GET /signal?ticker=TSLA&window_hours=48` | Custom rolling window |
| `GET /backtest?ticker=TSLA&lag=3` | Backtest metrics with equity curve |
| `GET /candles?ticker=TSLA&period=90d` | OHLC price data with signal overlay |
| `GET /signals/all` | Signals for all 8 tracked tickers |

Interactive docs: **http://localhost:8000/docs**

---

## Tracked Tickers

`AAPL` · `TSLA` · `NVDA` · `MSFT` · `AMZN` · `META` · `GOOGL` · `AMD`

---

## Project Structure

```
signalforge/
├── ingestion/producer.py         Finnhub + Reddit → Kafka
├── model/
│   ├── finetune_finbert.py       HuggingFace fine-tuning
│   ├── sentiment_consumer.py     Kafka → FinBERT → PostgreSQL
│   └── mlflow_utils.py           Model registry helpers
├── signals/
│   ├── signal_engine.py          Rolling window → BUY/SELL/HOLD
│   └── backtester.py             Lag window + P&L metrics
├── api/main.py                   FastAPI endpoints
├── frontend/src/                 React + Recharts dashboard
├── docker-compose.yml
└── requirements.txt
```

---

## Author

**Tejas Sawant** — MS Applied Data Intelligence, SJSU  
[GitHub](https://github.com/SawantTej2912) · [LinkedIn](https://www.linkedin.com/in/tejas-nandkishor-sawant-70a3531a6/)
