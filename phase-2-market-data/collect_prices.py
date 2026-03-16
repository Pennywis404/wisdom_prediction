"""
collect_prices.py — Collect price history for Polymarket markets.

Reads the markets snapshot CSV, selects markets with valid orderbook data,
and downloads hourly price history from the CLOB API.

Usage:
    python3 phase-2-market-data/collect_prices.py              # financial/macro only
    python3 phase-2-market-data/collect_prices.py --all         # all markets

Depends on:
    data/markets_snapshot.csv (run collect_markets.py first)

Output:
    data/prices_history.csv
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLOB_API = "https://clob.polymarket.com"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MARKETS_FILE = os.path.join(DATA_DIR, "markets_snapshot.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "prices_history.csv")

FIDELITY = 60  # 1 hour granularity (in minutes)

# Same keywords as fetch_market.py — broadened for finance
FINANCIAL_KEYWORDS = [
    # Monetary policy
    "fed ", "fomc", "interest rate", "rate cut", "rate hike", "federal reserve",
    # Economic indicators
    "cpi", "inflation", "nfp", "unemployment rate", "payroll", "gdp", "recession",
    # Fiscal / trade policy
    "tariff", "trade war", "sanctions", "debt ceiling", "government shutdown",
    # Geopolitics with market impact
    "war ", "opec", "oil price",
    # Stocks & indices
    "s&p", "sp500", "nasdaq", "dow jones", "stock price", "stock market",
    "ipo", "market cap", "all-time high", "all time high",
    # Companies / tech
    "tesla", "apple", "nvidia", "google", "amazon", "microsoft", "meta ",
    "openai", "spacex",
    # Crypto
    "bitcoin", "btc", "ethereum", "eth ", "crypto", "solana",
    # Commodities & assets
    "gold", "silver", "oil ", "natural gas", "commodity",
    # Prices & financial
    "price above", "price below", "price of", "reach $", "above $", "below $",
    "market crash", "bear market", "bull market",
    # Real estate
    "housing", "real estate", "home price",
]

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_price_history(token_id):
    """Fetch full price history for a token at hourly granularity."""
    url = f"{CLOB_API}/prices-history"
    params = {
        "market": token_id,
        "interval": "max",
        "fidelity": FIDELITY,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("history", [])

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def is_financial(row):
    """Check if a market matches financial keywords."""
    text = f"{row.get('question', '')} {row.get('event_title', '')}".lower()
    return any(kw in text for kw in FINANCIAL_KEYWORDS)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Collect ALL markets, not just financial")
    args = parser.parse_args()

    # --- Load markets snapshot ---
    if not os.path.exists(MARKETS_FILE):
        print(f"ERROR: {MARKETS_FILE} not found.")
        print("Run collect_markets.py first.")
        sys.exit(1)

    df_markets = pd.read_csv(MARKETS_FILE, low_memory=False)
    print("=" * 60)
    print("  COLLECT PRICES — Historical Price Data")
    print("=" * 60)
    print(f"\nLoaded {len(df_markets)} markets from snapshot")

    # --- Filter markets ---
    # Must have clobTokenIds (at least token 0) and orderbook enabled
    has_tokens = df_markets["clobTokenIds_0"].notna()
    has_orderbook = df_markets["enableOrderBook"] == True
    valid = df_markets[has_tokens & has_orderbook].copy()
    print(f"Markets with orderbook + token IDs: {len(valid)}")

    if not args.all:
        valid = valid[valid.apply(is_financial, axis=1)]
        print(f"Financial/macro markets after keyword filter: {len(valid)}")
    else:
        print("Collecting ALL markets (--all flag)")

    if valid.empty:
        print("No markets to process. Exiting.")
        return

    # --- Collect price history ---
    print(f"\nFetching price history (fidelity={FIDELITY}min)...")
    print(f"Estimated API calls: ~{len(valid) * 2}")
    print()

    all_rows = []
    errors = 0
    total = len(valid)

    for idx, (_, market) in enumerate(valid.iterrows()):
        condition_id = market.get("conditionId", "unknown")
        question = market.get("question", "Unknown")
        event_title = market.get("event_title", market.get("event_title", ""))

        # Process each outcome token (Yes=0, No=1, possibly more)
        for token_idx in range(10):  # Support up to 10 outcomes
            token_col = f"clobTokenIds_{token_idx}"
            outcome_col = f"outcomes_{token_idx}"

            if token_col not in market.index or pd.isna(market.get(token_col)):
                break

            token_id = str(market[token_col])
            outcome = market.get(outcome_col, f"outcome_{token_idx}")

            try:
                history = fetch_price_history(token_id)

                for point in history:
                    all_rows.append({
                        "condition_id": condition_id,
                        "question": question,
                        "event_title": event_title,
                        "token_id": token_id,
                        "outcome": outcome,
                        "timestamp": point["t"],
                        "datetime": datetime.utcfromtimestamp(point["t"]).strftime("%Y-%m-%d %H:%M:%S"),
                        "price": point["p"],
                    })
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  ⚠ Error for {question[:50]}... ({outcome}): {e}")
                elif errors == 6:
                    print("  ⚠ Suppressing further error messages...")

            time.sleep(0.3)  # Rate limit: ~3 requests/sec

        # Progress
        pct = (idx + 1) / total * 100
        n_points = len(all_rows)
        print(f"  [{idx+1}/{total}] {pct:.0f}% — {n_points:,} data points collected", end="\r")

    print()  # Clear the \r line
    print(f"\nCollection complete:")
    print(f"  → {len(all_rows):,} total data points")
    print(f"  → {errors} errors")

    if not all_rows:
        print("No data collected. Exiting.")
        return

    # --- Save to CSV ---
    df_prices = pd.DataFrame(all_rows)

    # Sort by condition_id + timestamp for clean output
    df_prices = df_prices.sort_values(["condition_id", "outcome", "timestamp"])

    df_prices.to_csv(OUTPUT_FILE, index=False)
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)

    # Stats
    n_markets = df_prices["condition_id"].nunique()
    date_min = df_prices["datetime"].min()
    date_max = df_prices["datetime"].max()

    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"  → {len(df_prices):,} rows, {size_mb:.1f} MB")
    print(f"  → {n_markets} unique markets")
    print(f"  → Date range: {date_min} → {date_max}")


if __name__ == "__main__":
    main()
