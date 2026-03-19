#!/usr/bin/env python3
"""
Étape 4 — Preuve de calibration de la foule (Brier Score).

Calcule le Brier Score de Polymarket à différents horizons temporels
(J-30, J-7, J-1, H-4, H-1) et compare contre un benchmark naïf.

Produit un calibration plot et un tableau comparatif.

Prérequis:
    - data/polymarket_hourly.parquet  (output étape 2)
    - data/selected_markets.csv       (output étape 1)

Usage:
    python3 phase-5-research/brier_score.py

Output:
    data/brier_results.csv
    outputs/calibration_plot.png
    outputs/brier_comparison.png
"""

import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Chemins ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

POLY_HOURLY = os.path.join(DATA_DIR, "polymarket_hourly.parquet")
MARKETS_CSV = os.path.join(DATA_DIR, "selected_markets.csv")

# Horizons à évaluer : (nom, timedelta avant end_date)
HORIZONS = [
    ("J-30", pd.Timedelta(days=30)),
    ("J-7", pd.Timedelta(days=7)),
    ("J-1", pd.Timedelta(days=1)),
    ("H-4", pd.Timedelta(hours=4)),
    ("H-1", pd.Timedelta(hours=1)),
]


# ── Fonctions ────────────────────────────────────────────────────────────────


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """BS = mean((prob - outcome)²). Plus bas = mieux calibré."""
    return float(np.mean((probs - outcomes) ** 2))


def extract_price_at_horizon(
    poly: pd.DataFrame, markets: pd.DataFrame, horizon_td: pd.Timedelta
) -> pd.DataFrame:
    """
    Pour chaque marché, extrait le prix Polymarket le plus proche
    de (end_date - horizon).
    """
    rows = []

    for _, mkt in markets.iterrows():
        cid = mkt["condition_id"]
        end = mkt["end_date"]
        outcome = mkt["outcome_real"]
        target_time = end - horizon_td

        # Séries de prix pour ce marché
        series = poly[poly["condition_id"] == cid]
        if series.empty:
            continue

        # Trouver l'observation la plus proche de target_time
        series = series.copy()
        series["delta"] = (series["hour_utc"] - target_time).abs()

        # Ne garder que si dans une fenêtre raisonnable (±12h pour daily, ±2h pour hourly)
        max_delta = pd.Timedelta(hours=12) if horizon_td >= pd.Timedelta(days=1) else pd.Timedelta(hours=2)
        close_enough = series[series["delta"] <= max_delta]

        if close_enough.empty:
            continue

        nearest = close_enough.loc[close_enough["delta"].idxmin()]
        rows.append({
            "condition_id": cid,
            "category": mkt["category"],
            "question": mkt["question"],
            "outcome_real": outcome,
            "price_at_horizon": nearest["vwap_yes"],
            "volume_at_horizon": nearest["volume_usd"],
            "actual_delta_h": nearest["delta"].total_seconds() / 3600,
        })

    return pd.DataFrame(rows)


def calibration_data(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10):
    """Calcule les données pour le calibration plot."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    bin_means = []
    bin_counts = []

    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i + 1])
        if i == n_bins - 1:  # dernier bin inclut 1.0
            mask = (probs >= bins[i]) & (probs <= bins[i + 1])
        count = mask.sum()
        if count > 0:
            bin_centers.append((bins[i] + bins[i + 1]) / 2)
            bin_means.append(outcomes[mask].mean())
            bin_counts.append(count)

    return np.array(bin_centers), np.array(bin_means), np.array(bin_counts)


# ── Visualisations ───────────────────────────────────────────────────────────


def plot_calibration(results_by_horizon: dict, output_path: str):
    """Calibration plot : probabilité prédite vs fréquence observée."""
    fig, ax = plt.subplots(figsize=(8, 8))

    # Diagonale parfaite
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Calibration parfaite")

    colors = ["#2196F3", "#4CAF50", "#FF9800", "#F44336", "#9C27B0"]

    for (horizon_name, df), color in zip(results_by_horizon.items(), colors):
        probs = df["price_at_horizon"].values
        outcomes = df["outcome_real"].values
        bs = brier_score(probs, outcomes)

        centers, means, counts = calibration_data(probs, outcomes, n_bins=10)
        ax.plot(centers, means, "o-", color=color, markersize=8,
                label=f"{horizon_name} (BS={bs:.4f}, n={len(df)})")

    ax.set_xlabel("Probabilité prédite (prix Polymarket)", fontsize=12)
    ax.set_ylabel("Fréquence observée (outcome réel)", fontsize=12)
    ax.set_title("Calibration de Polymarket — La foule est-elle fiable ?", fontsize=14)
    ax.legend(fontsize=10)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  → {output_path}")


def plot_brier_comparison(brier_by_horizon: dict, output_path: str):
    """Bar chart comparatif Brier Scores vs benchmark naïf."""
    horizons = list(brier_by_horizon.keys())
    polymarket_bs = [brier_by_horizon[h]["polymarket"] for h in horizons]
    naive_bs = [brier_by_horizon[h]["naive_50_50"] for h in horizons]

    x = np.arange(len(horizons))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width / 2, polymarket_bs, width, label="Polymarket",
                   color="#2196F3", alpha=0.85)
    bars2 = ax.bar(x + width / 2, naive_bs, width, label="Naïf 50/50 (BS=0.25)",
                   color="#9E9E9E", alpha=0.6)

    ax.set_xlabel("Horizon avant résolution", fontsize=12)
    ax.set_ylabel("Brier Score (plus bas = mieux)", fontsize=12)
    ax.set_title("Polymarket vs Benchmark naïf — Brier Score par horizon", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(horizons)
    ax.legend(fontsize=11)
    ax.grid(True, axis="y", alpha=0.3)

    # Annoter les barres
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  → {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    # Charger
    poly = pd.read_parquet(POLY_HOURLY)
    markets = pd.read_csv(MARKETS_CSV)

    poly["hour_utc"] = pd.to_datetime(poly["hour_utc"], utc=True)
    markets["end_date"] = pd.to_datetime(markets["end_date"], format="ISO8601", utc=True)

    print(f"Marchés sélectionnés : {len(markets)}")
    print(f"Séries horaires : {len(poly):,} observations")

    # Calculer Brier Score à chaque horizon
    results_by_horizon = {}
    brier_by_horizon = {}
    all_results = []

    print("\nCalcul du Brier Score par horizon...")
    for horizon_name, horizon_td in HORIZONS:
        df = extract_price_at_horizon(poly, markets, horizon_td)

        if df.empty:
            print(f"  {horizon_name}: aucune donnée")
            continue

        probs = df["price_at_horizon"].values
        outcomes = df["outcome_real"].values
        bs = brier_score(probs, outcomes)

        results_by_horizon[horizon_name] = df
        brier_by_horizon[horizon_name] = {
            "polymarket": bs,
            "naive_50_50": 0.25,
            "n_markets": len(df),
        }

        # Brier Score par catégorie
        print(f"\n  {horizon_name} : BS = {bs:.4f} (n={len(df)}) vs naïf 0.2500")
        for cat, g in df.groupby("category"):
            cat_bs = brier_score(g["price_at_horizon"].values, g["outcome_real"].values)
            print(f"    {cat:20s} │ BS = {cat_bs:.4f} │ n = {len(g)}")

        # Ajouter au résultat global
        df_out = df.copy()
        df_out["horizon"] = horizon_name
        all_results.append(df_out)

    # Sauvegarder résultats
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if all_results:
        results_df = pd.concat(all_results, ignore_index=True)
        results_path = os.path.join(DATA_DIR, "brier_results.csv")
        results_df.to_csv(results_path, index=False)
        print(f"\n✓ Résultats → {results_path}")

    # Plots
    if results_by_horizon:
        plot_calibration(results_by_horizon,
                         os.path.join(OUTPUT_DIR, "calibration_plot.png"))
        plot_brier_comparison(brier_by_horizon,
                              os.path.join(OUTPUT_DIR, "brier_comparison.png"))

    # Résumé final
    print("\n══ RÉSUMÉ ══")
    for h, scores in brier_by_horizon.items():
        ratio = scores["naive_50_50"] / scores["polymarket"]
        print(f"  {h:5s} : Polymarket BS = {scores['polymarket']:.4f} "
              f"│ {ratio:.1f}x mieux que le hasard │ n = {scores['n_markets']}")


if __name__ == "__main__":
    main()
