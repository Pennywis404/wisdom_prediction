# Polymarket comme Indicateur Avancé des Marchés Financiers

**Work in Progress** — projet de recherche personnel.
Phases 1, 2 et 5a complétées, phase 5b en cours.

![Distribution des 607K markets classifiés](outputs/04_classification_distribution.png)

## Objectif

Tester empiriquement deux hypothèses :

1. La foule Polymarket est mieux calibrée que les indicateurs traditionnels
   (sondages Bloomberg, consensus des économistes, Fear & Greed Index) parce
   que chaque participant met de l'argent réel.
2. Les mouvements de prix Polymarket anticipent ceux des marchés financiers
   autour des événements macro (Fed, CPI, NFP, élections, géopolitique).

Livrable visé : une comparaison chiffrée du type "sur les N dernières décisions
de la Fed, Polymarket avait le bon outcome à J-7 dans X% des cas, contre Y%
pour le consensus Bloomberg".

## Progression

| Phase | Statut | Livrable |
|---|---|---|
| 1 — Concepts & scanner | fait | 561 marchés macro / finance identifiés |
| 2 — Collecte données | fait | 607K markets, 14 tickers, 418M trades sur BigQuery |
| 5a — Classification 15 catégories | fait | F1 macro 0.81, table `markets_classified` |
| 5b — Alignement Polymarket × yfinance | en cours | Données alignées hourly sur 2 ans |
| 5c — Stats : Brier + Granger + cross-correlation | à faire | Chiffres principaux |
| 5d — Dashboard final | à faire | Visualisations |
| 5e — Écriture / publication | à faire | Article + posts |

Les phases 3 (trading) et 4 (onchain) sont hors scope actuel.

## Résultats actuels

### Phase 5a — Classification des 607 561 markets

Objectif : segmenter tous les markets Polymarket en 15 catégories pour
permettre l'analyse par domaine dans les phases suivantes.

Méthode : regex publiées avec Le, N.A. (2026), *Decomposing Crowd Wisdom*
([arXiv:2602.19520](https://arxiv.org/abs/2602.19520), licence MIT), étendues
avec des patterns custom pour les catégories absentes du papier (AI/Tech,
Weather, Cinema/TV, Music, Press People, Social Media, Esports, tickers
boursiers).

Validation : F1 macro **0.81** sur `labeled_1500.csv` (1 500 markets
hand-labellisés, équilibrés sur les 15 catégories).

Sortie : table BigQuery `polymarket-research-490517.polymarket.markets_classified`.

Distribution sur les 607K markets :

| Catégorie | markets | % |
|---|---:|---:|
| Sports | 199 651 | 32.9 |
| Crypto Up/Down | 174 185 | 28.7 |
| Other | 90 290 | 14.9 |
| Esports | 40 754 | 6.7 |
| Crypto Price | 38 550 | 6.3 |
| US Politics | 15 943 | 2.6 |
| Weather | 14 922 | 2.5 |
| Stocks/Finance | 9 952 | 1.6 |
| Geopolitics | 6 028 | 1.0 |
| Autres (Social Media, Cinema/TV, Macroeconomy, Music, AI/Tech, Press People) | < 1% chacun | — |

Matrice de confusion sur la validation :

![Confusion matrix](outputs/04_classification_confusion.png)

### Phases 5b et 5c — à venir

- Brier Score Polymarket vs consensus Bloomberg sur les dernières Fed decisions
- Tests de causalité Granger : Polymarket → assets financiers (SPY, DXY, ZN, GLD, BTC-USD)
- Cross-correlation à différents lags (+1h, +1j, +1sem)

## Stack technique

- Python 3.12
- APIs Polymarket : Gamma (discovery), CLOB (prix, orderbook), Data (trades)
- yfinance pour les tickers financiers
- Google Cloud : BigQuery + Colab notebooks
- pandas, numpy, statsmodels, scikit-learn
- matplotlib, seaborn
- py-clob-client, web3.py (phases 3/4, hors scope)

## Structure du projet

```
├── phase-1-concepts/        Scanner des marchés macro / finance
├── phase-2-market-data/     Pipeline de collecte (Gamma, CLOB, yfinance)
├── phase-5-research/        Scripts d'analyse statistique
├── notebooks/               Analyses Colab + BigQuery
│   ├── 01_market_selection.ipynb
│   ├── 02_crowd_calibration.ipynb
│   ├── 03_sentiment_vs_markets.ipynb
│   └── 04_classification.ipynb
├── outputs/                 Figures exportées
├── data/                    Données locales (gitignored)
└── deprecated/              Approches abandonnées (traçabilité)
```

## Installation

```bash
git clone https://github.com/Pennywis404/wisdom_prediction.git
cd wisdom_prediction

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Éditer .env avec les clés nécessaires
```

Les notebooks tournent sur Google Colab (authentification BigQuery via
`google.colab.auth`).

## References

- Le, N.A. (2026). *Decomposing Crowd Wisdom: Domain-Specific Calibration
  Dynamics in Prediction Markets.* [arXiv:2602.19520](https://arxiv.org/abs/2602.19520).
  Code : [namanhz/prediction-market-calibration](https://github.com/namanhz/prediction-market-calibration) (MIT).
- Dataset trades : [SII-WANGZJ/Polymarket_data](https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data)
  (1.1 milliard de trades extraits de Polygon).
- Documentation Polymarket : [docs.polymarket.com](https://docs.polymarket.com).
