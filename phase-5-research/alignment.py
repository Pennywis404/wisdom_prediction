#!/usr/bin/env python3
"""
Étape 3 — Alignement temporel Polymarket / marchés financiers.

Fusionne les séries horaires Polymarket (24/7 UTC) avec les données
financières (sessions NYSE ou 24/7 crypto) via merge_asof.

Produit deux datasets :
- aligned_hourly.parquet : pour Granger / cross-correlation (heures communes)
- aligned_daily.parquet  : pour Brier Score / visualisations (agrégé par jour)

Prérequis:
    - data/polymarket_hourly.parquet  (output étape 2)
    - data/selected_markets.csv       (output étape 1)
    - data/financial_hourly.csv       (output phase 2)
    - data/financial_daily.csv        (output phase 2)

Usage:
    python3 phase-5-research/alignment.py

Output:
    data/aligned_hourly.parquet
    data/aligned_daily.parquet
"""

import os
import sys

import numpy as np
import pandas as pd

# ── Chemins ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

POLY_HOURLY = os.path.join(DATA_DIR, "polymarket_hourly.parquet")
MARKETS_CSV = os.path.join(DATA_DIR, "selected_markets.csv")
FIN_HOURLY = os.path.join(DATA_DIR, "financial_hourly.csv")
FIN_DAILY = os.path.join(DATA_DIR, "financial_daily.csv")

OUT_HOURLY = os.path.join(DATA_DIR, "aligned_hourly.parquet")
OUT_DAILY = os.path.join(DATA_DIR, "aligned_daily.parquet")

# Tolérance pour merge_asof : on accepte un point financier à max 2h
HOURLY_TOLERANCE = pd.Timedelta("2h")


# ── Chargement ───────────────────────────────────────────────────────────────


def load_data():
    """Charge toutes les sources de données."""
    for path in [POLY_HOURLY, MARKETS_CSV, FIN_HOURLY, FIN_DAILY]:
        if not os.path.exists(path):
            print(f"Erreur : {path} introuvable")
            sys.exit(1)

    poly = pd.read_parquet(POLY_HOURLY)
    markets = pd.read_csv(MARKETS_CSV)
    fin_h = pd.read_csv(FIN_HOURLY)
    fin_d = pd.read_csv(FIN_DAILY)

    # Normaliser les datetime en UTC
    poly["hour_utc"] = pd.to_datetime(poly["hour_utc"], utc=True)
    fin_h["datetime"] = pd.to_datetime(fin_h["datetime"], utc=True)
    fin_d["datetime"] = pd.to_datetime(fin_d["datetime"], utc=True)

    # Enrichir poly avec les infos marché
    markets["end_date"] = pd.to_datetime(markets["end_date"], format="ISO8601", utc=True)
    poly = poly.merge(
        markets[["condition_id", "category", "matched_tickers", "outcome_real", "end_date", "question"]],
        on="condition_id",
        how="left",
    )

    return poly, fin_h, fin_d


# ── Alignement horaire ──────────────────────────────────────────────────────


def align_hourly(poly: pd.DataFrame, fin_h: pd.DataFrame) -> pd.DataFrame:
    """
    Pour chaque (marché, ticker associé), aligne les séries horaires
    via merge_asof avec tolérance de 2h.
    """
    results = []

    # Grouper par marché
    for cid, group in poly.groupby("condition_id"):
        tickers = group["matched_tickers"].iloc[0]
        if pd.isna(tickers):
            continue

        group = group.sort_values("hour_utc")

        for ticker in tickers.split(","):
            ticker = ticker.strip()
            fin_ticker = fin_h[fin_h["ticker"] == ticker][["datetime", "close"]].copy()
            fin_ticker = fin_ticker.sort_values("datetime")

            if fin_ticker.empty:
                continue

            # merge_asof : pour chaque heure Polymarket,
            # trouver le prix financier le plus proche (direction=backward)
            merged = pd.merge_asof(
                group[["hour_utc", "condition_id", "vwap_yes", "volume_usd",
                        "category", "outcome_real", "end_date", "question"]],
                fin_ticker.rename(columns={"datetime": "hour_utc", "close": "fin_price"}),
                on="hour_utc",
                direction="backward",
                tolerance=HOURLY_TOLERANCE,
            )

            # Supprimer les lignes sans match financier
            merged = merged.dropna(subset=["fin_price"])

            if merged.empty:
                continue

            merged["ticker"] = ticker

            # Calculer les rendements financiers sur différents horizons
            merged["fin_return_1h"] = merged["fin_price"].pct_change(1)
            merged["fin_return_4h"] = merged["fin_price"].pct_change(4)
            merged["fin_return_1d"] = merged["fin_price"].pct_change(24)

            # Rendement Polymarket
            merged["poly_return_1h"] = merged["vwap_yes"].diff(1)
            merged["poly_return_4h"] = merged["vwap_yes"].diff(4)

            results.append(merged)

    if not results:
        return pd.DataFrame()

    out = pd.concat(results, ignore_index=True)
    return out


# ── Alignement daily ────────────────────────────────────────────────────────


def align_daily(poly: pd.DataFrame, fin_d: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège Polymarket en daily (dernier VWAP de la journée) et
    joint avec les prix financiers daily.
    """
    # Agréger Polymarket par jour : dernier VWAP, volume total
    poly["date"] = poly["hour_utc"].dt.date

    daily_poly = (
        poly.sort_values("hour_utc")
        .groupby(["condition_id", "date"])
        .agg(
            vwap_yes=("vwap_yes", "last"),        # dernier prix de la journée
            volume_usd=("volume_usd", "sum"),
            trade_count=("trade_count", "sum"),
            category=("category", "first"),
            outcome_real=("outcome_real", "first"),
            end_date=("end_date", "first"),
            matched_tickers=("matched_tickers", "first"),
            question=("question", "first"),
        )
        .reset_index()
    )

    daily_poly["date"] = pd.to_datetime(daily_poly["date"], utc=True)

    results = []

    for cid, group in daily_poly.groupby("condition_id"):
        tickers = group["matched_tickers"].iloc[0]
        if pd.isna(tickers):
            continue

        for ticker in tickers.split(","):
            ticker = ticker.strip()
            fin_ticker = fin_d[fin_d["ticker"] == ticker][["datetime", "close"]].copy()
            fin_ticker = fin_ticker.sort_values("datetime")
            fin_ticker["date_key"] = fin_ticker["datetime"].dt.normalize()

            if fin_ticker.empty:
                continue

            # Join exact sur la date
            merged = group.copy()
            merged["date_key"] = merged["date"].dt.normalize()
            merged = merged.merge(
                fin_ticker[["date_key", "close"]].rename(columns={"close": "fin_price"}),
                on="date_key",
                how="inner",
            )

            if merged.empty:
                continue

            merged["ticker"] = ticker
            merged["fin_return_1d"] = merged["fin_price"].pct_change(1)
            merged["poly_return_1d"] = merged["vwap_yes"].diff(1)

            # Jours avant résolution
            merged["days_to_end"] = (merged["end_date"] - merged["date"]).dt.days

            results.append(merged.drop(columns=["date_key"]))

    if not results:
        return pd.DataFrame()

    out = pd.concat(results, ignore_index=True)
    return out


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    print("Chargement des données...")
    poly, fin_h, fin_d = load_data()
    print(f"  Polymarket : {len(poly):,} obs, {poly['condition_id'].nunique()} marchés")
    print(f"  Financier hourly : {len(fin_h):,} obs, {fin_h['ticker'].nunique()} tickers")
    print(f"  Financier daily  : {len(fin_d):,} obs")

    # Alignement horaire
    print("\nAlignement horaire (merge_asof, tolérance 2h)...")
    hourly = align_hourly(poly, fin_h)
    if hourly.empty:
        print("  ERREUR : aucun alignement horaire trouvé")
    else:
        print(f"  → {len(hourly):,} observations alignées")
        print(f"    {hourly['condition_id'].nunique()} marchés × {hourly['ticker'].nunique()} tickers")

        # Stats par catégorie
        for cat, g in hourly.groupby("category"):
            n_m = g["condition_id"].nunique()
            n_t = g["ticker"].nunique()
            print(f"    {cat:20s} │ {n_m:3d} marchés │ {len(g):>8,} obs │ {n_t} tickers")

    # Alignement daily
    print("\nAlignement daily...")
    daily = align_daily(poly, fin_d)
    if daily.empty:
        print("  ERREUR : aucun alignement daily trouvé")
    else:
        print(f"  → {len(daily):,} observations alignées")
        print(f"    {daily['condition_id'].nunique()} marchés × {daily['ticker'].nunique()} tickers")

    # Sauvegarder
    os.makedirs(DATA_DIR, exist_ok=True)

    if not hourly.empty:
        hourly.to_parquet(OUT_HOURLY, index=False)
        print(f"\n✓ Hourly → {OUT_HOURLY}")

    if not daily.empty:
        daily.to_parquet(OUT_DAILY, index=False)
        print(f"✓ Daily  → {OUT_DAILY}")


if __name__ == "__main__":
    main()
