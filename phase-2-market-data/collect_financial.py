"""
collect_financial.py — Collect financial market data via yfinance.

Downloads 2 years of hourly + daily OHLCV data for key assets
that will be correlated with Polymarket sentiment.

Usage:
    python3 phase-2-market-data/collect_financial.py

Output:
    data/financial_hourly.csv
    data/financial_daily.csv
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_HOURLY = os.path.join(DATA_DIR, "financial_hourly.csv")
OUTPUT_DAILY = os.path.join(DATA_DIR, "financial_daily.csv")

# Assets to track and their categories
TICKERS = {
    # Equities
    "SPY":      "US equities (S&P 500)",
    "QQQ":      "US tech (Nasdaq 100)",
    "IWM":      "US small caps (Russell 2000)",
    # Bonds / Rates
    "TLT":      "US long-term bonds (20Y+)",
    "^TNX":     "US 10Y yield",
    # Currencies
    "DX-Y.NYB": "US Dollar Index (DXY)",
    "EURUSD=X": "EUR/USD",
    # Commodities
    "GLD":      "Gold",
    "CL=F":     "Crude Oil (WTI)",
    "NG=F":     "Natural Gas",
    # Crypto
    "BTC-USD":  "Bitcoin",
    "ETH-USD":  "Ethereum",
    "SOL-USD":  "Solana",
    # Volatility
    "^VIX":     "VIX (volatility index)",
}

# yfinance hourly data: max 730 days
TWO_YEARS_AGO = (datetime.now(timezone.utc) - timedelta(days=729)).strftime("%Y-%m-%d")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_ticker(ticker, interval, start, end):
    """Download OHLCV data for a single ticker. Returns DataFrame or None."""
    try:
        data = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        if data.empty:
            return None

        # Flatten MultiIndex columns if present (yfinance sometimes does this)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        data = data.reset_index()

        # Normalize the datetime column name
        date_col = "Datetime" if "Datetime" in data.columns else "Date"
        data = data.rename(columns={date_col: "datetime"})

        data["ticker"] = ticker
        data["description"] = TICKERS[ticker]

        return data
    except Exception as e:
        print(f"  ⚠ Error downloading {ticker}: {e}")
        return None


def collect_all(interval, start, end):
    """Download all tickers at given interval. Returns consolidated DataFrame."""
    frames = []
    tickers = list(TICKERS.keys())
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        desc = TICKERS[ticker]
        print(f"  [{i+1}/{total}] {ticker} ({desc})...", end=" ")

        df = download_ticker(ticker, interval, start, end)
        if df is not None and not df.empty:
            frames.append(df)
            print(f"✓ {len(df)} rows")
        else:
            print("✗ no data")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Standardize column names to lowercase
    result.columns = [c.lower() for c in result.columns]

    return result

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("=" * 60)
    print("  COLLECT FINANCIAL — Market Data via yfinance")
    print("=" * 60)
    print(f"\nPeriod: {TWO_YEARS_AGO} → {TODAY}")
    print(f"Tickers: {len(TICKERS)}")
    print()

    # --- Hourly data (2 years max for yfinance) ---
    print("[1/2] Downloading HOURLY data...")
    df_hourly = collect_all("1h", TWO_YEARS_AGO, TODAY)

    if not df_hourly.empty:
        df_hourly = df_hourly.sort_values(["ticker", "datetime"])
        df_hourly.to_csv(OUTPUT_HOURLY, index=False)
        size_mb = os.path.getsize(OUTPUT_HOURLY) / (1024 * 1024)
        print(f"  → Saved: {len(df_hourly):,} rows, {size_mb:.1f} MB")
        print(f"  → {df_hourly['ticker'].nunique()} tickers")
    else:
        print("  → No hourly data collected")
    print()

    # --- Daily data (2 years, more reliable) ---
    print("[2/2] Downloading DAILY data...")
    df_daily = collect_all("1d", TWO_YEARS_AGO, TODAY)

    if not df_daily.empty:
        df_daily = df_daily.sort_values(["ticker", "datetime"])
        df_daily.to_csv(OUTPUT_DAILY, index=False)
        size_mb = os.path.getsize(OUTPUT_DAILY) / (1024 * 1024)
        print(f"  → Saved: {len(df_daily):,} rows, {size_mb:.1f} MB")
        print(f"  → {df_daily['ticker'].nunique()} tickers")
    else:
        print("  → No daily data collected")
    print()

    # --- Summary ---
    print("=" * 60)
    print("Summary:")
    if not df_hourly.empty:
        print(f"  Hourly: {OUTPUT_HOURLY}")
    if not df_daily.empty:
        print(f"  Daily:  {OUTPUT_DAILY}")
    print("Done.")


if __name__ == "__main__":
    main()
