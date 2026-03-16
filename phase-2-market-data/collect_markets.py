"""
collect_markets.py — Full snapshot of all Polymarket markets (active + closed).

Fetches events from the Gamma API (active + closed from the last 2 years),
flattens all markets with ALL available fields, and saves to CSV.

Usage:
    python3 phase-2-market-data/collect_markets.py
Output:
    data/markets_snapshot.csv
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "markets_snapshot.csv")

# 2 years ago
TWO_YEARS_AGO = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%dT00:00:00Z")

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_events_page(limit=50, offset=0, **kwargs):
    """Fetch one page of events from the Gamma API."""
    url = f"{GAMMA_API}/events"
    params = {"limit": limit, "offset": offset, **kwargs}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_all_events(max_pages=200, **kwargs):
    """Paginate through all events matching filters (capped at max_pages)."""
    all_events = []
    offset = 0
    limit = 50

    for page in range(max_pages):
        try:
            events = fetch_events_page(limit=limit, offset=offset, **kwargs)
        except Exception as e:
            print(f"    ⚠ Error at offset {offset}: {e}")
            break

        if not events:
            break

        all_events.extend(events)
        print(f"    {len(all_events)} events (page {page+1})...", flush=True)
        offset += limit
        time.sleep(0.15)  # Rate limit courtesy

    print()  # Clear the \r line
    return all_events

# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------

# JSON-encoded list fields that need to be parsed and expanded
JSON_LIST_FIELDS = ["outcomes", "outcomePrices", "clobTokenIds", "shortOutcomes"]

# Nested object/array fields to skip (not useful in flat CSV)
SKIP_FIELDS = {
    "markets", "series", "categories", "collections", "tags",
    "imageOptimized", "iconOptimized", "featuredImageOptimized",
    "eventCreators", "chats", "templates", "subEvents",
}


def flatten_market(market, event):
    """Flatten one market + its parent event into a single dict for CSV."""
    row = {}

    # --- Event-level fields (prefixed with event_) ---
    for key, value in event.items():
        if key in SKIP_FIELDS or isinstance(value, (dict, list)):
            continue
        row[f"event_{key}"] = value

    # --- Market-level fields (all scalar values) ---
    for key, value in market.items():
        if key in SKIP_FIELDS or isinstance(value, (dict, list)):
            continue
        row[key] = value

    # --- Parse JSON-encoded string fields into indexed columns ---
    for field in JSON_LIST_FIELDS:
        raw = market.get(field)
        if not isinstance(raw, str):
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for i, val in enumerate(parsed):
                    row[f"{field}_{i}"] = val
        except (json.JSONDecodeError, ValueError):
            pass

    return row

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("=" * 60)
    print("  COLLECT MARKETS — Full Snapshot")
    print("=" * 60)
    print()

    # --- Fetch active events ---
    print("[1/2] Fetching ACTIVE events...")
    active_events = fetch_all_events(
        active="true",
        closed="false",
        order="volume",
        ascending="false",
    )
    print(f"  → {len(active_events)} active events")
    print()

    # --- Fetch closed events from last 2 years ---
    print(f"[2/2] Fetching CLOSED events (since {TWO_YEARS_AGO[:10]})...")
    closed_events = fetch_all_events(
        closed="true",
        end_date_min=TWO_YEARS_AGO,
        order="volume",
        ascending="false",
    )
    print(f"  → {len(closed_events)} closed events")
    print()

    # --- Deduplicate by event ID ---
    seen_ids = set()
    all_events = []
    for event in active_events + closed_events:
        eid = event.get("id")
        if eid and eid not in seen_ids:
            seen_ids.add(eid)
            all_events.append(event)

    print(f"Total unique events: {len(all_events)}")

    # --- Flatten all markets ---
    rows = []
    for event in all_events:
        for market in event.get("markets", []):
            rows.append(flatten_market(market, event))

    print(f"Total markets extracted: {len(rows)}")

    if not rows:
        print("No markets found. Exiting.")
        return

    # --- Save to CSV ---
    df = pd.DataFrame(rows)

    # Sort by volume (descending) for convenience
    if "volumeNum" in df.columns:
        df["volumeNum"] = pd.to_numeric(df["volumeNum"], errors="coerce")
        df = df.sort_values("volumeNum", ascending=False)

    df.to_csv(OUTPUT_FILE, index=False)
    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)

    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"  → {len(df)} rows, {len(df.columns)} columns, {size_mb:.1f} MB")

    # Quick stats
    n_active = df["active"].sum() if "active" in df.columns else "?"
    n_closed = df["closed"].sum() if "closed" in df.columns else "?"
    print(f"  → Active: {n_active} | Closed: {n_closed}")

    # Show column names for reference
    print(f"\nAll columns ({len(df.columns)}):")
    for i, col in enumerate(sorted(df.columns)):
        print(f"  {col}", end="")
        if (i + 1) % 4 == 0:
            print()
    print()


if __name__ == "__main__":
    main()
