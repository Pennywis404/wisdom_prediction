#!/usr/bin/env python3
"""
Étape 1 — Sélection et catégorisation des marchés macro/financiers Polymarket.

Filtre les marchés résolus pertinents pour la recherche, les catégorise
en 5 groupes, détermine l'outcome réel, et mappe aux tickers financiers.

Usage:
    python3 phase-5-research/select_markets.py             # BigQuery (défaut)
    python3 phase-5-research/select_markets.py --local      # CSV local (fallback)

Output:
    data/selected_markets.csv
"""

import json
import os
import sys

import pandas as pd

# ── Chemins ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "selected_markets.csv")

# ── Règles de catégorisation ─────────────────────────────────────────────────
#
# Chaque catégorie a :
#   include  — mots-clés qui matchent (OR)
#   exclude  — mots-clés qui disqualifient (OR, priorité sur include)
#   tickers  — assets financiers corrélés (pour l'alignement étape 3)

CATEGORY_RULES = {
    "fed_rates": {
        "include": [
            "fed decrease", "fed increase", "no change in fed",
            "interest rate", "rate cut", "rate hike",
        ],
        "exclude": [
            "fed chair", "nominate", "fire", "say \"", "say '",
            "resign", "impeach",
        ],
        "tickers": ["TLT", "^TNX", "DX-Y.NYB", "SPY"],
    },
    "inflation_cpi": {
        "include": [
            "monthly inflation", "annual inflation",
            "inflation increase", "inflation reach", "inflation get",
            "cpi ",
        ],
        "exclude": [
            "powell say", "argentina", "canada", "japan",
            "india", "uk ", "mexico", "turkey", "brazil",
        ],
        "tickers": ["TLT", "GLD", "SPY", "^TNX"],
    },
    "macro_gdp": {
        "include": [
            "recession", "gdp growth", "gdp decline",
            "gdp contraction", "negative gdp",
        ],
        "exclude": ["china gdp", "uk gdp", "euro gdp"],
        "tickers": ["SPY", "QQQ", "^VIX", "TLT"],
    },
    "geopolitics_trade": {
        "include": ["tariff", "trade war", "sanction"],
        "exclude": ["fart", "dividend", "tariff rate on china"],
        "tickers": ["SPY", "CL=F", "GLD", "DX-Y.NYB"],
    },
    "crypto_price": {
        "include": [
            "bitcoin above", "bitcoin below", "bitcoin dip",
            "bitcoin reach", "btc above", "btc below",
            "ethereum above", "ethereum below",
        ],
        "exclude": ["up or down"],
        "tickers": ["BTC-USD", "ETH-USD", "SOL-USD"],
    },
}

MIN_VOLUME_USD = 100_000


# ── Fonctions utilitaires ────────────────────────────────────────────────────


def categorize(question: str) -> str | None:
    """Catégorise un marché par mots-clés. Retourne None si non pertinent."""
    q = question.lower()
    for cat, rules in CATEGORY_RULES.items():
        if any(exc in q for exc in rules["exclude"]):
            continue
        if any(inc in q for inc in rules["include"]):
            return cat
    return None


def parse_outcome(outcome_prices_str: str) -> float | None:
    """
    Extrait l'outcome réel depuis outcome_prices.

    Format attendu : "['0.XX', '0.YY']" (index 0 = Yes, index 1 = No)
    - Yes >= 0.90 → outcome = 1 (Yes a gagné)
    - Yes <= 0.10 → outcome = 0 (No a gagné)
    - Sinon → None (ambigu, ex: résolution 50/50)
    """
    if pd.isna(outcome_prices_str):
        return None
    try:
        s = str(outcome_prices_str).replace("'", '"')
        prices = json.loads(s)
        yes_p = float(prices[0])
        if yes_p >= 0.90:
            return 1.0
        elif yes_p <= 0.10:
            return 0.0
        return None
    except Exception:
        return None


# ── Chargement des données ───────────────────────────────────────────────────


def load_bigquery() -> pd.DataFrame:
    """Charge les marchés résolus depuis BigQuery."""
    from google.cloud import bigquery

    client = bigquery.Client(project="polymarket-research-490517")
    query = """
    SELECT
        id, question, event_title, event_id, condition_id,
        token1, token2, answer1, answer2,
        volume, outcome_prices, closed, active,
        CAST(created_at AS STRING) AS created_at,
        CAST(end_date AS STRING) AS end_date
    FROM polymarket.markets
    WHERE closed = 1
    ORDER BY volume DESC
    """
    return client.query(query).to_dataframe()


def load_local_csv() -> pd.DataFrame:
    """Charge depuis data/markets_snapshot.csv et normalise les colonnes."""
    path = os.path.join(DATA_DIR, "markets_snapshot.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV introuvable : {path}")

    df = pd.read_csv(path, low_memory=False)

    # Mapper colonnes Gamma API → noms standardisés
    col_map = {
        "conditionId": "condition_id",
        "clobTokenIds_0": "token1",
        "clobTokenIds_1": "token2",
        "outcomes_0": "answer1",
        "outcomes_1": "answer2",
        "outcomePrices": "outcome_prices",
        "endDate": "end_date",
        "createdAt": "created_at",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Filtrer les marchés fermés
    if "closed" in df.columns:
        df = df[df["closed"].astype(str).isin(["1", "True", "true"])]

    return df


# ── Pipeline principal ───────────────────────────────────────────────────────


def select_markets(df: pd.DataFrame) -> pd.DataFrame:
    """Filtre, catégorise et enrichit les marchés sélectionnés."""

    # 1. Filtrer par volume
    df = df[df["volume"] >= MIN_VOLUME_USD].copy()
    print(f"  Marchés résolus, volume >= ${MIN_VOLUME_USD:,.0f} : {len(df)}")

    # 2. Catégoriser
    df["category"] = df["question"].apply(categorize)
    df = df.dropna(subset=["category"])
    print(f"  Après catégorisation macro/financière       : {len(df)}")

    # 3. Déterminer outcome réel
    df["outcome_real"] = df["outcome_prices"].apply(parse_outcome)
    df = df.dropna(subset=["outcome_real"])
    df["outcome_real"] = df["outcome_real"].astype(int)
    print(f"  Avec outcome clair (>90% ou <10%)           : {len(df)}")

    # 4. Ajouter tickers correspondants
    df["matched_tickers"] = df["category"].map(
        {cat: ",".join(r["tickers"]) for cat, r in CATEGORY_RULES.items()}
    )

    # 5. Trier par catégorie puis volume décroissant
    df = df.sort_values(["category", "volume"], ascending=[True, False])

    # 6. Afficher stats
    print("\n  ── Répartition par catégorie ──")
    for cat, g in df.groupby("category"):
        tickers = CATEGORY_RULES[cat]["tickers"]
        print(
            f"    {cat:20s} │ {len(g):3d} marchés │ "
            f"vol ${g['volume'].sum() / 1e6:>8.1f}M │ "
            f"tickers: {', '.join(tickers)}"
        )
    print(
        f"    {'TOTAL':20s} │ {len(df):3d} marchés │ "
        f"vol ${df['volume'].sum() / 1e6:>8.1f}M"
    )

    # 7. Colonnes finales
    cols = [
        "id", "condition_id", "token1", "token2",
        "question", "event_title", "event_id",
        "category", "outcome_real", "matched_tickers",
        "volume", "outcome_prices", "created_at", "end_date",
    ]
    cols = [c for c in cols if c in df.columns]
    return df[cols].reset_index(drop=True)


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    use_local = "--local" in sys.argv

    if use_local:
        print("Source : CSV local (data/markets_snapshot.csv)")
        df = load_local_csv()
    else:
        try:
            print("Source : BigQuery (polymarket.markets)")
            df = load_bigquery()
        except Exception as e:
            print(f"  BigQuery échoué : {e}")
            print("  Fallback → CSV local")
            df = load_local_csv()

    print(f"  Marchés chargés : {len(df)}")

    selected = select_markets(df)

    os.makedirs(DATA_DIR, exist_ok=True)
    selected.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✓ {len(selected)} marchés sauvegardés → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
