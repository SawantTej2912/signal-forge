"""
FastAPI layer for SignalForge.

Endpoints:
    GET /health
    GET /signal?ticker=TSLA[&window_hours=24]
    GET /signals/all[?window_hours=24]
    GET /backtest?ticker=TSLA&lag=3[&period=90d]
    GET /candles?ticker=TSLA[&period=90d]
"""

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Make sibling packages importable when running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from signals.backtester import fetch_prices, fetch_sentiment, run_backtest
from signals.signal_engine import compute_signal

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]

app = FastAPI(title="SignalForge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/signal")
def signal(
    ticker: str = Query(..., description="Stock ticker, e.g. TSLA"),
    window_hours: int = Query(24, ge=1, le=168),
):
    ticker = ticker.upper()
    try:
        result = compute_signal(ticker, window_hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.get("/signals/all")
def signals_all(window_hours: int = Query(24, ge=1, le=168)):
    return [compute_signal(t, window_hours) for t in TICKERS]


@app.get("/candles")
def candles(
    ticker: str = Query(..., description="Stock ticker, e.g. TSLA"),
    period: str = Query("90d", pattern=r"^\d+d$"),
):
    ticker = ticker.upper()
    try:
        prices = fetch_prices(ticker, period)
        if prices.empty:
            return []

        sentiment = fetch_sentiment(ticker, period)

        if not sentiment.empty:
            merged = prices.merge(sentiment, on="date", how="left").ffill()
            merged["signal"] = merged["sentiment_score"].apply(
                lambda s: "BUY" if s > 0.3 else ("SELL" if s < -0.3 else "HOLD")
            )
        else:
            merged = prices.copy()
            merged["signal"] = "HOLD"

        return [
            {
                "date": str(row["date"].date()),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
                "signal": str(row.get("signal", "HOLD")),
            }
            for _, row in merged.iterrows()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backtest")
def backtest(
    ticker: str = Query(..., description="Stock ticker, e.g. TSLA"),
    lag: int = Query(3, ge=1, le=14),
    period: str = Query("90d", pattern=r"^\d+d$"),
):
    ticker = ticker.upper()
    try:
        result = run_backtest(ticker, lag, period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result
