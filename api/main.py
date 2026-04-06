"""
FastAPI layer for SignalForge.

Endpoints:
    GET /health
    GET /signal?ticker=TSLA[&window_hours=24]
    GET /signals/all[?window_hours=24]
    GET /backtest?ticker=TSLA&lag=3[&period=90d]
"""

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Make sibling packages importable when running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from signals.backtester import run_backtest
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
