"""
fetch_market.py — First script to fetch and display Polymarket markets.

Fetches active events from the Gamma API, extracts markets,
filters for macro-relevant ones, and displays formatted results.
No authentication required (Gamma API is public).
"""

import json
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GAMMA_API = "https://gamma-api.polymarket.com"

MACRO_KEYWORDS = [
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
    # Real estate & misc assets
    "housing", "real estate", "home price",
]

MAX_DISPLAY = 30  # Cap output to avoid flooding the terminal

# ---------------------------------------------------------------------------
# API fetch with retry
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_active_events(limit=50, offset=0):
    """Fetch active, non-closed events sorted by volume (descending)."""
    url = f"{GAMMA_API}/events"
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume",
        "ascending": "false",
        "liquidity_min": 1000,
        "limit": limit,
        "offset": offset,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def flatten_markets(events):
    """Extract all markets from a list of events."""
    markets = []
    for event in events:
        for market in event.get("markets", []):
            market["_event_title"] = event.get("title", "Unknown Event")
            markets.append(market)
    return markets


def is_macro(market):
    """Check if a market matches macro keywords (case-insensitive)."""
    text = (
        market.get("question", "")
        + " "
        + market.get("_event_title", "")
    ).lower()
    return any(kw in text for kw in MACRO_KEYWORDS)


def parse_prices(market):
    """Parse outcomes and prices from JSON strings. Returns (outcomes, prices) or None."""
    try:
        outcomes_raw = market.get("outcomes")
        prices_raw = market.get("outcomePrices")
        if not outcomes_raw or not prices_raw:
            return None

        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        prices = [float(p) for p in prices]
        return outcomes, prices
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def check_invariant(prices):
    """Check that Yes + No ≈ $1.00. Returns (sum, is_valid)."""
    total = sum(prices)
    return total, abs(total - 1.0) < 0.02  # 2 cent tolerance


def format_market(market):
    """Format a single market for display."""
    parsed = parse_prices(market)
    if not parsed:
        return None

    outcomes, prices = parsed
    total, invariant_ok = check_invariant(prices)

    # Build price string: "Yes: $0.75 | No: $0.25"
    price_parts = [f"{o}: ${p:.2f}" for o, p in zip(outcomes, prices)]
    price_str = " | ".join(price_parts)

    volume = market.get("volume", "0")
    try:
        volume = f"${float(volume):,.0f}"
    except (ValueError, TypeError):
        volume = "N/A"

    liquidity = market.get("liquidity", "0")
    try:
        liquidity = f"${float(liquidity):,.0f}"
    except (ValueError, TypeError):
        liquidity = "N/A"

    end_date = market.get("endDate", "N/A")
    if end_date and end_date != "N/A":
        end_date = end_date[:10]  # Keep only YYYY-MM-DD

    invariant_flag = " ✓" if invariant_ok else f" ⚠ SUM={total:.3f}"

    return (
        f"  {market.get('question', 'Unknown')}\n"
        f"    {price_str}{invariant_flag}\n"
        f"    Volume: {volume} | Liquidity: {liquidity} | End: {end_date}\n"
        f"    Event: {market.get('_event_title', 'N/A')}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  POLYMARKET — Macro Market Scanner")
    print("=" * 60)
    print()

    # Fetch events (multiple pages to get more coverage)
    print("Fetching active events from Gamma API...")
    all_events = []
    for offset in range(0, 200, 50):
        try:
            events = fetch_active_events(limit=50, offset=offset)
            if not events:
                break
            all_events.extend(events)
        except Exception as e:
            print(f"  Warning: failed to fetch offset {offset}: {e}")
            break

    print(f"  → {len(all_events)} events fetched")

    # Flatten into markets
    markets = flatten_markets(all_events)
    print(f"  → {len(markets)} markets extracted")
    print()

    # Filter macro markets
    financial_markets = [m for m in markets if is_macro(m)]

    if financial_markets:
        print(f"FINANCIAL / MACRO MARKETS FOUND: {len(financial_markets)}")
        if len(financial_markets) > MAX_DISPLAY:
            print(f"  (showing top {MAX_DISPLAY} by volume)")
        print("-" * 60)
        for m in financial_markets[:MAX_DISPLAY]:
            formatted = format_market(m)
            if formatted:
                print(formatted)
                print()
    else:
        print("No financial/macro markets found with current keywords.")
        print()

    # Fallback: show 5 sample markets regardless
    print(f"SAMPLE MARKETS (5 of {len(markets)} total)")
    print("-" * 60)
    shown = 0
    for m in markets:
        formatted = format_market(m)
        if formatted:
            print(formatted)
            print()
            shown += 1
            if shown >= 5:
                break

    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
