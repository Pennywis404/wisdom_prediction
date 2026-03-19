#!/usr/bin/env python3
"""
Étape 2 — Construction des séries de prix horaires Polymarket depuis BigQuery.

Lit les marchés sélectionnés (étape 1), requête BigQuery pour calculer
le VWAP horaire du token YES sur chaque marché, puis forward-fill les trous.

Prérequis:
    - data/selected_markets.csv (output étape 1)
    - Accès BigQuery (google-cloud-bigquery + credentials)

Usage:
    python3 phase-5-research/build_price_series.py

Output:
    data/polymarket_hourly.parquet
"""

import os
import sys
import time

import pandas as pd
from google.cloud import bigquery

# ── Chemins ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INPUT_FILE = os.path.join(DATA_DIR, "selected_markets.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "polymarket_hourly.parquet")

# ── Configuration ────────────────────────────────────────────────────────────

BQ_PROJECT = "polymarket-research-490517"
TRADES_TABLE = "polymarket.trades"

# Maximum de heures sans trade avant de couper le forward-fill
MAX_FFILL_HOURS = 48


# ── BigQuery ─────────────────────────────────────────────────────────────────


def query_hourly_vwap(client: bigquery.Client, condition_ids: list[str]) -> pd.DataFrame:
    """
    Construit les séries VWAP horaires pour tous les marchés en une requête.

    Pour chaque (condition_id, heure), calcule :
    - vwap_yes : prix moyen pondéré par volume du token YES
    - volume_usd : volume total en USD
    - trade_count : nombre de trades
    """
    query = """
    SELECT
        t.condition_id,
        TIMESTAMP_TRUNC(TIMESTAMP_SECONDS(CAST(t.timestamp AS INT64)), HOUR) AS hour_utc,
        SUM(t.price * t.usd_amount) / NULLIF(SUM(t.usd_amount), 0) AS vwap_yes,
        SUM(t.usd_amount) AS volume_usd,
        COUNT(*) AS trade_count
    FROM polymarket.trades t
    WHERE t.condition_id IN UNNEST(@cids)
      AND t.nonusdc_side = 'token1'
    GROUP BY t.condition_id, hour_utc
    ORDER BY t.condition_id, hour_utc
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("cids", "STRING", condition_ids),
        ]
    )

    print(f"  Requête BigQuery pour {len(condition_ids)} marchés...")
    start = time.time()
    df = client.query(query, job_config=job_config).to_dataframe()
    elapsed = time.time() - start
    print(f"  → {len(df):,} rows en {elapsed:.1f}s")

    return df


# ── Forward-fill ─────────────────────────────────────────────────────────────


def forward_fill_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pour chaque marché, génère un index horaire complet et forward-fill
    les heures sans trades (max MAX_FFILL_HOURS heures consécutives).
    """
    results = []

    for cid, group in df.groupby("condition_id"):
        group = group.sort_values("hour_utc")

        # Index horaire complet du premier au dernier trade
        full_idx = pd.date_range(
            start=group["hour_utc"].min(),
            end=group["hour_utc"].max(),
            freq="h",
            tz="UTC",
        )

        # Réindexer
        group = group.set_index("hour_utc").reindex(full_idx)
        group.index.name = "hour_utc"
        group["condition_id"] = cid

        # Marquer les heures interpolées AVANT le ffill
        group["is_interpolated"] = group["vwap_yes"].isna()

        # Forward-fill avec limite
        group["vwap_yes"] = group["vwap_yes"].ffill(limit=MAX_FFILL_HOURS)
        group["volume_usd"] = group["volume_usd"].fillna(0)
        group["trade_count"] = group["trade_count"].fillna(0).astype(int)

        # Supprimer les lignes où le ffill n'a pas pu combler (gap > MAX_FFILL_HOURS)
        group = group.dropna(subset=["vwap_yes"])

        results.append(group.reset_index())

    out = pd.concat(results, ignore_index=True)
    return out


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    # 1. Charger les marchés sélectionnés
    if not os.path.exists(INPUT_FILE):
        print(f"Erreur : {INPUT_FILE} introuvable. Lancer d'abord select_markets.py")
        sys.exit(1)

    markets = pd.read_csv(INPUT_FILE)
    condition_ids = markets["condition_id"].unique().tolist()
    print(f"Marchés sélectionnés : {len(condition_ids)}")

    # 2. Requêter BigQuery
    client = bigquery.Client(project=BQ_PROJECT)
    raw = query_hourly_vwap(client, condition_ids)

    if raw.empty:
        print("Aucun trade trouvé. Vérifier les condition_ids.")
        sys.exit(1)

    # Stats brutes
    n_markets_found = raw["condition_id"].nunique()
    print(f"  Marchés avec trades : {n_markets_found} / {len(condition_ids)}")

    # 3. Forward-fill
    print("  Forward-fill des trous (max 48h)...")
    filled = forward_fill_series(raw)
    pct_interpolated = filled["is_interpolated"].mean() * 100
    print(f"  → {len(filled):,} rows ({pct_interpolated:.1f}% interpolées)")

    # 4. Sauvegarder
    os.makedirs(DATA_DIR, exist_ok=True)
    filled.to_parquet(OUTPUT_FILE, index=False)
    print(f"\n✓ Séries horaires sauvegardées → {OUTPUT_FILE}")
    print(f"  {filled['condition_id'].nunique()} marchés, "
          f"{len(filled):,} observations")


if __name__ == "__main__":
    main()
