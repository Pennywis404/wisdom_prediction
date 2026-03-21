# Polymarket comme Indicateur Avancé des Marchés Financiers

## Thèse

Polymarket est un thermomètre du sentiment collectif suffisamment fiable pour anticiper les mouvements des marchés financiers. Chaque participant met de l'argent réel — ce qui filtre les opinions non-réfléchies et force l'honnêteté.

Le projet démontre deux choses :
1. **La foule Polymarket est bien calibrée** — meilleur Brier Score que les indicateurs traditionnels (sondages Bloomberg, Fear & Greed Index)
2. **Le sentiment Polymarket corrèle avec les marchés financiers** — les mouvements de prix Polymarket précèdent ceux des assets autour des événements macro

## Stack technique

- **Python** — langage principal
- **Gamma API / CLOB API / Data API** — données Polymarket
- **yfinance** — données marchés financiers
- **pandas, numpy, statsmodels** — analyse quantitative
- **matplotlib, plotly** — visualisation
- **web3.py, py-clob-client** — interactions blockchain et trading

## Installation

```bash
# Cloner le repo
git clone <url-du-repo>
cd POLYMARKET

# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les credentials
cp .env.example .env
# Éditer .env avec vos clés
```

## Structure du projet

```
├── phase-1-concepts/       ← Notes théoriques + premier fetch
├── phase-2-market-data/    ← Pipeline de collecte de données
├── phase-3-trading/        ← Authentification et ordres
├── phase-4-onchain/        ← Split/Merge, market making
├── phase-5-research/       ← Analyse statistique et dashboard
└── notebooks/              ← Exploration et visualisations
```

## Progression

- [x] Phase 1 — Concepts et premier fetch
- [x] Phase 2 — Collecte de données (150K marchés, 14 tickers financiers, 418M trades sur BigQuery)
- [ ] Phase 3 — Trading (auth L1/L2, ordres)
- [ ] Phase 4 — Onchain (CTF, market making)
- [x] Phase 5a — Preprocessing : classification des 538K marchés en 15 catégories via Gemini 2.0 Flash
- [ ] Phase 5b — Analyse statistique (Granger, Brier, corrélations)
- [ ] Phase 5c — Dashboard et visualisations
