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
    "fed", "fomc", "interest rate", "rate cut", "rate hike",
    "cpi", "inflation",
    "nfp", "jobs", "unemployment", "payroll",
    "election", "president", "congress", "senate",
    "gdp", "recession",
    "tariff", "trade war", "sanctions",
    "trump", "biden",
    "war", "nato", "china", "russia", "iran",
    "debt ceiling", "government shutdown",
    "oil", "opec",
]

# ---------------------------------------------------------------------------
# API fetch with retry
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_active_events(limit=50, offset=0):
    """Fetch active events from the Gamma API with exponential backoff."""
    url = f"{GAMMA_API}/events"
    params = {"active": "true", "limit": limit, "offset": offset}
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

    volume = market.get("volume", "N/A")
    if isinstance(volume, (int, float)):
        volume = f"${volume:,.0f}"

    end_date = market.get("endDate", "N/A")
    if end_date and end_date != "N/A":
        end_date = end_date[:10]  # Keep only YYYY-MM-DD

    invariant_flag = " ✓" if invariant_ok else f" ⚠ SUM={total:.3f}"

    return (
        f"  {market.get('question', 'Unknown')}\n"
        f"    {price_str}{invariant_flag}\n"
        f"    Volume: {volume} | End: {end_date}\n"
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
    macro_markets = [m for m in markets if is_macro(m)]

    if macro_markets:
        print(f"MACRO MARKETS FOUND: {len(macro_markets)}")
        print("-" * 60)
        for m in macro_markets:
            formatted = format_market(m)
            if formatted:
                print(formatted)
                print()
    else:
        print("No macro markets found with current keywords.")
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
