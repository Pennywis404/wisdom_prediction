"""
collect_prices.py — Collect price history for Polymarket markets (async).

Uses asyncio + aiohttp for parallel requests (20 concurrent).
Collects Yes token only (No = 1 - Yes).

Usage:
    python3 phase-2-market-data/collect_prices.py              # financial/macro only
    python3 phase-2-market-data/collect_prices.py --all         # all markets

Output:
    data/prices_history.csv
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

import aiohttp
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLOB_API = "https://clob.polymarket.com"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MARKETS_FILE = os.path.join(DATA_DIR, "markets_snapshot.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "prices_history.csv")

FIDELITY = 60  # 1 hour granularity
MAX_CONCURRENT = 20  # parallel requests
BATCH_SAVE_SIZE = 500  # save progress every N markets

FINANCIAL_KEYWORDS = [
    "fed ", "fomc", "interest rate", "rate cut", "rate hike", "federal reserve",
    "cpi", "inflation", "nfp", "unemployment rate", "payroll", "gdp", "recession",
    "tariff", "trade war", "sanctions", "debt ceiling", "government shutdown",
    "war ", "opec", "oil price",
    "s&p", "sp500", "nasdaq", "dow jones", "stock price", "stock market",
    "ipo", "market cap", "all-time high", "all time high",
    "tesla", "apple", "nvidia", "google", "amazon", "microsoft", "meta ",
    "openai", "spacex",
    "bitcoin", "btc", "ethereum", "eth ", "crypto", "solana",
    "gold", "silver", "oil ", "natural gas", "commodity",
    "price above", "price below", "price of", "reach $", "above $", "below $",
    "market crash", "bear market", "bull market",
    "housing", "real estate", "home price",
]

# ---------------------------------------------------------------------------
# Async fetch
# ---------------------------------------------------------------------------

semaphore = None

async def fetch_price_history(session, token_id, retries=3):
    """Fetch price history for one token with retry and concurrency limit."""
    url = f"{CLOB_API}/prices-history"
    params = {"market": token_id, "interval": "max", "fidelity": FIDELITY}

    for attempt in range(retries):
        try:
            async with semaphore:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:  # Rate limited
                        await asyncio.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("history", [])
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                return None
    return None


async def fetch_one_market(session, market):
    """Fetch price history for a single market (Yes token only)."""
    condition_id = market["conditionId"]
    question = market["question"]
    event_title = market["event_title"]
    token_id = str(market["clobTokenIds_0"])
    outcome = market.get("outcomes_0", "Yes")

    history = await fetch_price_history(session, token_id)
    if not history:
        return []

    rows = []
    for point in history:
        rows.append({
            "condition_id": condition_id,
            "question": question,
            "event_title": event_title,
            "token_id": token_id,
            "outcome": outcome,
            "timestamp": point["t"],
            "datetime": datetime.fromtimestamp(point["t"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "price": point["p"],
        })
    return rows

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def is_financial(row):
    text = f"{row.get('question', '')} {row.get('event_title', '')}".lower()
    return any(kw in text for kw in FINANCIAL_KEYWORDS)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(args):
    global semaphore
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # --- Load markets snapshot (lightweight) ---
    if not os.path.exists(MARKETS_FILE):
        print(f"ERROR: {MARKETS_FILE} not found. Run collect_markets.py first.")
        sys.exit(1)

    ID_COLUMNS = [
        "conditionId", "question", "event_title",
        "clobTokenIds_0", "outcomes_0", "enableOrderBook",
    ]
    df = pd.read_csv(MARKETS_FILE, usecols=ID_COLUMNS, low_memory=False)

    print("=" * 60)
    print("  COLLECT PRICES — Async (20 concurrent)")
    print("=" * 60)
    print(f"\nLoaded {len(df)} markets")

    # Filter
    valid = df[df["clobTokenIds_0"].notna() & (df["enableOrderBook"] == True)].copy()
    print(f"With orderbook + token: {len(valid)}")

    if not args.all:
        valid = valid[valid.apply(is_financial, axis=1)]
        print(f"Financial/macro filter: {len(valid)}")

    markets = valid.to_dict("records")
    total = len(markets)
    print(f"\nFetching Yes token prices for {total} markets...")
    print(f"Concurrency: {MAX_CONCURRENT} | Fidelity: {FIDELITY}min")
    print()

    # --- Fetch in batches and save progressively ---
    all_rows = []
    errors = 0
    processed = 0

    async with aiohttp.ClientSession() as session:
        for batch_start in range(0, total, BATCH_SAVE_SIZE):
            batch = markets[batch_start:batch_start + BATCH_SAVE_SIZE]
            tasks = [fetch_one_market(session, m) for m in batch]
            results = await asyncio.gather(*tasks)

            for rows in results:
                if rows:
                    all_rows.extend(rows)
                else:
                    errors += 1

            processed += len(batch)
            pct = processed / total * 100
            print(f"  [{processed}/{total}] {pct:.0f}% — {len(all_rows):,} data points | {errors} errors", flush=True)

    print(f"\nCollection complete: {len(all_rows):,} data points, {errors} errors")

    if not all_rows:
        print("No data collected.")
        return

    # --- Save ---
    df_prices = pd.DataFrame(all_rows)
    df_prices = df_prices.sort_values(["condition_id", "timestamp"])
    df_prices.to_csv(OUTPUT_FILE, index=False)
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)

    n_markets = df_prices["condition_id"].nunique()
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"  → {len(df_prices):,} rows, {size_mb:.1f} MB")
    print(f"  → {n_markets} unique markets")
    print(f"  → {df_prices['datetime'].min()} → {df_prices['datetime'].max()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
