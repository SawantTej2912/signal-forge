"""
Backtester: replays scored_sentiment signals against historical prices
with a variable lag window.

The lag slider is the demo centrepiece — shifting lag=1→14 visibly
moves the P&L curve, showing that sentiment timing matters.

Usage (CLI):
    python signals/backtester.py --ticker TSLA --lag 3
    python signals/backtester.py --ticker TSLA --lag 3 --period 90d
"""

import argparse
import os
import time

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "signalforge")
POSTGRES_USER = os.getenv("POSTGRES_USER", "signalforge")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "signalforge123")

BUY_THRESHOLD = 0.3
SELL_THRESHOLD = -0.3


def get_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def fetch_sentiment(ticker: str, period: str = "90d") -> pd.DataFrame:
    """Return daily aggregated sentiment scores for ticker over period."""
    days = int(period.replace("d", ""))
    cutoff_utc = int(time.time()) - days * 86400

    query = """
        SELECT
            DATE(TO_TIMESTAMP(created_utc)) AS date,
            SUM(CASE WHEN label = 'positive' THEN score ELSE 0 END) AS pos_sum,
            SUM(CASE WHEN label = 'negative' THEN score ELSE 0 END) AS neg_sum,
            COUNT(*) AS total
        FROM scored_sentiment
        WHERE ticker = %s AND created_utc >= %s
        GROUP BY DATE(TO_TIMESTAMP(created_utc))
        ORDER BY date
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, (ticker, cutoff_utc))
            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "sentiment_score"])

    df = pd.DataFrame(rows, columns=["date", "pos_sum", "neg_sum", "total"])
    df["date"] = pd.to_datetime(df["date"])
    df["raw_score"] = df["pos_sum"] - df["neg_sum"]
    df["sentiment_score"] = (df["raw_score"] / df["total"]).clip(-1, 1)
    return df[["date", "sentiment_score"]]


def fetch_prices(ticker: str, period: str = "90d") -> pd.DataFrame:
    """Return daily OHLCV from yfinance."""
    tk = yf.Ticker(ticker)
    hist = tk.history(period=period)
    if hist.empty:
        return pd.DataFrame()
    hist = hist.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
    hist.columns = ["date", "open", "high", "low", "close", "volume"]
    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None).dt.normalize()
    return hist


def run_backtest(ticker: str, lag_days: int = 3, period: str = "90d") -> dict:
    sentiment = fetch_sentiment(ticker, period)
    prices = fetch_prices(ticker, period)

    if sentiment.empty or prices.empty:
        return {
            "ticker": ticker,
            "lag_days": lag_days,
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "num_trades": 0,
            "period": period,
            "equity_curve": [],
        }

    # Shift sentiment by lag days to simulate delayed signal execution
    sentiment = sentiment.copy()
    sentiment["signal_date"] = sentiment["date"] + pd.Timedelta(days=lag_days)

    merged = prices.merge(
        sentiment.rename(columns={"signal_date": "date"}),
        on="date",
        how="left",
    ).fillna(method="ffill")

    merged["signal"] = merged["sentiment_score"].apply(
        lambda s: "BUY" if s > BUY_THRESHOLD else ("SELL" if s < SELL_THRESHOLD else "HOLD")
    )

    # Simple long-only strategy: enter on BUY, exit on SELL or HOLD
    position = 0
    entry_price = 0.0
    cash = 1.0
    equity = []
    trades = []

    for _, row in merged.iterrows():
        price = row["close"]
        sig = row["signal"]

        if sig == "BUY" and position == 0:
            position = cash / price
            entry_price = price
            cash = 0.0
        elif sig in ("SELL", "HOLD") and position > 0:
            cash = position * price
            trades.append((cash / (position * entry_price)) - 1)
            position = 0

        total_value = cash + position * price
        equity.append({"date": str(row["date"].date()), "equity": round(total_value, 4)})

    # Close any open position at end
    if position > 0:
        cash = position * merged.iloc[-1]["close"]
        trades.append((cash / (position * entry_price)) - 1)

    total_return = (cash - 1.0) * 100
    returns = pd.Series([e["equity"] for e in equity]).pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)).round(3) if returns.std() > 0 else 0.0

    equity_vals = pd.Series([e["equity"] for e in equity])
    rolling_max = equity_vals.cummax()
    drawdown = ((equity_vals - rolling_max) / rolling_max).min() * 100

    win_rate = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0.0

    return {
        "ticker": ticker,
        "lag_days": lag_days,
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": float(sharpe),
        "max_drawdown_pct": round(float(drawdown), 2),
        "win_rate_pct": round(win_rate, 1),
        "num_trades": len(trades),
        "period": period,
        "equity_curve": equity,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--lag", type=int, default=3)
    parser.add_argument("--period", default="90d")
    args = parser.parse_args()

    result = run_backtest(args.ticker, args.lag, args.period)
    curve = result.pop("equity_curve")
    print(result)
    print(f"Equity curve points: {len(curve)}")
