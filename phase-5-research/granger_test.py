#!/usr/bin/env python3
"""
Étape 5 — Tests de causalité Granger et cross-correlation.

Teste si les mouvements de prix Polymarket anticipent (lead)
les mouvements des marchés financiers.

Prérequis:
    - data/aligned_hourly.parquet  (output étape 3)

Usage:
    python3 phase-5-research/granger_test.py

Output:
    data/granger_results.csv
    outputs/cross_correlation_heatmap.png
"""

import os
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import correlate
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Chemins ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

ALIGNED_HOURLY = os.path.join(DATA_DIR, "aligned_hourly.parquet")

# Lags à tester pour Granger (en heures)
MAX_GRANGER_LAG = 12
# Lags pour cross-correlation
MAX_XCORR_LAG = 48
# Minimum d'observations pour un test valide
MIN_OBS = 100


# ── Fonctions statistiques ──────────────────────────────────────────────────


def check_stationarity(series: pd.Series) -> tuple[bool, float]:
    """Test ADF de stationnarité. Retourne (is_stationary, p_value)."""
    clean = series.dropna()
    if len(clean) < 20:
        return False, 1.0
    try:
        result = adfuller(clean, autolag="AIC")
        return result[1] < 0.05, result[1]
    except Exception:
        return False, 1.0


def run_granger_test(poly_returns: pd.Series, fin_returns: pd.Series,
                     max_lag: int = MAX_GRANGER_LAG) -> dict:
    """
    Test de Granger : est-ce que poly_returns aide à prédire fin_returns ?

    Retourne dict {lag: p_value} pour chaque lag testé.
    """
    combined = pd.DataFrame({
        "fin": fin_returns,
        "poly": poly_returns,
    }).dropna()

    if len(combined) < MIN_OBS:
        return {}

    try:
        results = grangercausalitytests(
            combined[["fin", "poly"]],
            maxlag=max_lag,
            verbose=False,
        )
        return {
            lag: result[0]["ssr_ftest"][1]  # p-value du F-test
            for lag, result in results.items()
        }
    except Exception:
        return {}


def cross_correlation(poly_returns: pd.Series, fin_returns: pd.Series,
                      max_lag: int = MAX_XCORR_LAG) -> tuple[np.ndarray, np.ndarray]:
    """
    Cross-correlation normalisée entre rendements Polymarket et financiers.

    Retourne (lags, correlations).
    Un pic à lag > 0 = Polymarket LEAD le financier.
    """
    combined = pd.DataFrame({
        "poly": poly_returns,
        "fin": fin_returns,
    }).dropna()

    if len(combined) < MIN_OBS:
        return np.array([]), np.array([])

    p = (combined["poly"] - combined["poly"].mean()) / combined["poly"].std()
    f = (combined["fin"] - combined["fin"].mean()) / combined["fin"].std()

    xcorr = correlate(p, f, mode="full") / len(combined)
    center = len(f) - 1
    start = max(center - max_lag, 0)
    end = min(center + max_lag + 1, len(xcorr))

    lags = np.arange(start - center, end - center)
    corrs = xcorr[start:end]

    return lags, corrs


# ── Analyse par catégorie ────────────────────────────────────────────────────


def analyze_category_ticker(df: pd.DataFrame, category: str, ticker: str) -> dict:
    """
    Analyse Granger + cross-correlation pour une paire (catégorie, ticker).

    Agrège tous les marchés de la catégorie en un seul signal.
    """
    sub = df[(df["category"] == category) & (df["ticker"] == ticker)].copy()

    if sub.empty:
        return None

    # Agréger par heure : moyenne pondérée par volume des variations Poly
    agg = (
        sub.sort_values("hour_utc")
        .groupby("hour_utc")
        .agg(
            poly_return=("poly_return_1h", lambda x: np.average(x, weights=sub.loc[x.index, "volume_usd"].clip(lower=1))),
            fin_return=("fin_return_1h", "mean"),
            n_markets=("condition_id", "nunique"),
        )
        .dropna()
    )

    if len(agg) < MIN_OBS:
        return None

    # Stationnarité
    poly_stat, poly_p = check_stationarity(agg["poly_return"])
    fin_stat, fin_p = check_stationarity(agg["fin_return"])

    # Granger test
    granger_pvals = run_granger_test(agg["poly_return"], agg["fin_return"])

    # Cross-correlation
    lags, xcorr = cross_correlation(agg["poly_return"], agg["fin_return"])

    # Meilleur lag (pic de cross-correlation côté positif = Poly lead)
    best_lag = None
    best_corr = 0
    peak_lag_positive = None
    peak_corr_positive = 0

    if len(lags) > 0:
        best_idx = np.argmax(np.abs(xcorr))
        best_lag = int(lags[best_idx])
        best_corr = float(xcorr[best_idx])

        # Meilleur lag positif uniquement (Poly lead)
        pos_mask = lags > 0
        if pos_mask.any():
            pos_idx = np.argmax(np.abs(xcorr[pos_mask]))
            peak_lag_positive = int(lags[pos_mask][pos_idx])
            peak_corr_positive = float(xcorr[pos_mask][pos_idx])

    # Min p-value Granger
    min_granger_p = min(granger_pvals.values()) if granger_pvals else 1.0
    best_granger_lag = min(granger_pvals, key=granger_pvals.get) if granger_pvals else None

    return {
        "category": category,
        "ticker": ticker,
        "n_obs": len(agg),
        "n_markets": sub["condition_id"].nunique(),
        "poly_stationary": poly_stat,
        "fin_stationary": fin_stat,
        "granger_min_p": min_granger_p,
        "granger_best_lag": best_granger_lag,
        "granger_significant": min_granger_p < 0.05,
        "xcorr_best_lag": best_lag,
        "xcorr_best_corr": best_corr,
        "xcorr_poly_lead_lag": peak_lag_positive,
        "xcorr_poly_lead_corr": peak_corr_positive,
        "granger_all_pvals": granger_pvals,
        "xcorr_lags": lags,
        "xcorr_values": xcorr,
    }


# ── Visualisations ───────────────────────────────────────────────────────────


def plot_heatmap(results: list[dict], output_path: str):
    """Heatmap des résultats Granger (p-values) par catégorie × ticker."""
    # Construire la matrice
    categories = sorted(set(r["category"] for r in results))
    tickers = sorted(set(r["ticker"] for r in results))

    matrix = pd.DataFrame(index=categories, columns=tickers, dtype=float)
    for r in results:
        matrix.loc[r["category"], r["ticker"]] = r["granger_min_p"]

    fig, ax = plt.subplots(figsize=(12, 6))
    matrix_vals = matrix.values.astype(float)

    im = ax.imshow(matrix_vals, cmap="RdYlGn_r", vmin=0, vmax=0.15, aspect="auto")

    ax.set_xticks(range(len(tickers)))
    ax.set_xticklabels(tickers, rotation=45, ha="right", fontsize=10)
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(categories, fontsize=10)

    # Annoter chaque cellule
    for i in range(len(categories)):
        for j in range(len(tickers)):
            val = matrix_vals[i, j]
            if np.isnan(val):
                text = "—"
                color = "gray"
            else:
                text = f"{val:.3f}"
                color = "white" if val < 0.05 else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=9, color=color,
                    fontweight="bold" if not np.isnan(val) and val < 0.05 else "normal")

    plt.colorbar(im, ax=ax, label="p-value Granger (vert = significatif)")
    ax.set_title("Test de Granger : Polymarket lead-t-il les marchés financiers ?", fontsize=13)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  → {output_path}")


def plot_xcorr_examples(results: list[dict], output_path: str):
    """Cross-correlation plots pour les paires les plus significatives."""
    # Top 6 par significance
    significant = [r for r in results if r["granger_significant"] and len(r["xcorr_lags"]) > 0]
    significant.sort(key=lambda r: r["granger_min_p"])
    top = significant[:6]

    if not top:
        print("  Pas assez de résultats significatifs pour le cross-correlation plot")
        return

    n = len(top)
    cols = min(3, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows))
    if n == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if hasattr(axes, "flatten") else [axes]

    for idx, r in enumerate(top):
        ax = axes[idx]
        lags = r["xcorr_lags"]
        xcorr = r["xcorr_values"]

        ax.bar(lags, xcorr, color=np.where(lags > 0, "#2196F3", "#9E9E9E"), alpha=0.7)
        ax.axvline(x=0, color="red", linestyle="--", alpha=0.5)
        ax.set_title(f"{r['category']} → {r['ticker']}\np={r['granger_min_p']:.4f}", fontsize=10)
        ax.set_xlabel("Lag (h)")
        ax.set_ylabel("Corrélation")
        ax.grid(True, alpha=0.3)

    # Masquer les axes vides
    for idx in range(n, len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle("Cross-correlation (bleu = Polymarket lead)", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    if not os.path.exists(ALIGNED_HOURLY):
        print(f"Erreur : {ALIGNED_HOURLY} introuvable. Lancer d'abord alignment.py")
        sys.exit(1)

    df = pd.read_parquet(ALIGNED_HOURLY)
    df["hour_utc"] = pd.to_datetime(df["hour_utc"], utc=True)

    print(f"Données alignées : {len(df):,} obs")
    print(f"  {df['condition_id'].nunique()} marchés × {df['ticker'].nunique()} tickers")

    # Toutes les paires (catégorie, ticker) à tester
    pairs = df.groupby(["category", "ticker"]).size().reset_index(name="n")
    pairs = pairs[pairs["n"] >= MIN_OBS]
    print(f"\nPaires à tester : {len(pairs)}")

    # Analyser chaque paire
    results = []
    print("\nAnalyse Granger + cross-correlation...")
    for _, row in pairs.iterrows():
        cat, ticker = row["category"], row["ticker"]
        result = analyze_category_ticker(df, cat, ticker)
        if result:
            sig = "✓" if result["granger_significant"] else "✗"
            print(f"  {cat:20s} → {ticker:12s} │ "
                  f"p={result['granger_min_p']:.4f} {sig} │ "
                  f"lead={result['xcorr_poly_lead_lag']}h │ "
                  f"n={result['n_obs']}")
            results.append(result)

    if not results:
        print("Aucun résultat. Vérifier les données.")
        sys.exit(1)

    # Sauvegarder (sans les arrays numpy)
    save_cols = [
        "category", "ticker", "n_obs", "n_markets",
        "poly_stationary", "fin_stationary",
        "granger_min_p", "granger_best_lag", "granger_significant",
        "xcorr_best_lag", "xcorr_best_corr",
        "xcorr_poly_lead_lag", "xcorr_poly_lead_corr",
    ]
    results_df = pd.DataFrame([{k: r[k] for k in save_cols} for r in results])
    results_path = os.path.join(DATA_DIR, "granger_results.csv")
    results_df.to_csv(results_path, index=False)
    print(f"\n✓ Résultats → {results_path}")

    # Plots
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plot_heatmap(results, os.path.join(OUTPUT_DIR, "granger_heatmap.png"))
    plot_xcorr_examples(results, os.path.join(OUTPUT_DIR, "cross_correlation.png"))

    # Résumé
    sig_results = [r for r in results if r["granger_significant"]]
    print(f"\n══ RÉSUMÉ ══")
    print(f"  Paires testées     : {len(results)}")
    print(f"  Paires significatives (p<0.05) : {len(sig_results)}")
    if sig_results:
        print(f"\n  Top résultats :")
        for r in sorted(sig_results, key=lambda x: x["granger_min_p"])[:10]:
            print(f"    {r['category']:20s} → {r['ticker']:12s} │ "
                  f"p={r['granger_min_p']:.4f} │ lag={r['granger_best_lag']}h │ "
                  f"corr lead={r['xcorr_poly_lead_corr']:+.4f}")


if __name__ == "__main__":
    main()
