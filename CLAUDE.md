# CLAUDE.md — Projet : Polymarket comme Indicateur Avancé des Marchés Financiers

## Contexte général

Ce projet est conduit par Théo, développeur en apprentissage basé à Nice (France).
Les réponses et instructions doivent être en **français** par défaut.
L'apprentissage se fait par la pratique : **toujours privilégier le code concret** avant la théorie abstraite.

---

## Objectif du projet

Démontrer que **Polymarket est un thermomètre du sentiment collectif** suffisamment fiable et puissant pour anticiper les mouvements des marchés financiers.

La thèse centrale :

> La foule sur Polymarket agrège de l'information de manière plus efficace et plus rapide que les indicateurs de sentiment traditionnels, parce que chaque participant met de l'argent réel — ce qui filtre les opinions non-réfléchies et force l'honnêteté.

Ce n'est pas un projet de causalité technique pure. C'est une démonstration en deux parties :

1. **Preuve de la qualité de la foule** — Polymarket est mieux calibré historiquement que les indicateurs traditionnels (sondages Bloomberg, consensus économistes, Fear & Greed Index).
2. **Corrélation avec les marchés financiers** — les mouvements du sentiment Polymarket coïncident avec les mouvements des assets financiers autour des événements macro.

---

## Stack technique

- **Langage** : Python
- **Éditeur** : Cursor (AI-powered)
- **Environnement** : `.env` + `python-dotenv` pour les credentials
- **SDK principal** : `py-clob-client` (SDK officiel Polymarket)
- **Blockchain** : Polygon Mainnet (`chain_id = 137`)
- **Librairies analytiques** : `pandas`, `numpy`, `statsmodels`, `matplotlib`, `plotly`
- **Data financière** : `yfinance`, `pandas-datareader`
- **WebSocket** : `asyncio` + `websockets`
- **Onchain** : `web3.py`

---

## Architecture du projet

```
polymarket-leading-indicator/
├── CLAUDE.md                          ← ce fichier
├── README.md                          ← vitrine GitHub
├── .env                               ← credentials (jamais commité)
├── .env.example                       ← template pour collaborateurs
├── .gitignore                         ← inclure .env
│
├── phase-1-concepts/
│   ├── notes.md                       ← notes théoriques
│   └── fetch_market.py                ← premier script public
│
├── phase-2-market-data/
│   ├── pipeline.py                    ← collecte données marchés
│   ├── websocket_listener.py          ← écoute temps réel
│   └── historical_prices.py           ← time series historiques
│
├── phase-3-trading/
│   ├── auth.py                        ← setup L1/L2
│   ├── place_order.py                 ← poster un ordre
│   └── bot_heartbeat.py               ← bot avec heartbeat
│
├── phase-4-onchain/
│   ├── ctf_split_merge.py             ← Split/Merge tokens
│   ├── market_maker.py                ← MM basique
│   └── subgraph_queries.py            ← GraphQL onchain
│
├── phase-5-research/
│   ├── data_collection.py             ← collecte Polymarket + yfinance
│   ├── alignment.py                   ← alignement time series
│   ├── granger_test.py                ← test de causalité
│   ├── brier_score.py                 ← calibration de la foule
│   └── dashboard.py                   ← visualisation finale
│
└── notebooks/
    ├── eda_spreads.ipynb               ← analyse exploratoire spreads
    ├── sentiment_vs_markets.ipynb      ← corrélation principale
    └── crowd_quality.ipynb             ← preuve de calibration
```

---

## APIs Polymarket

### Trois APIs distinctes — ne pas confondre les URLs

| API | URL de base | Usage |
|-----|-------------|-------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Découverte marchés, events, recherche |
| **CLOB API** | `https://clob.polymarket.com` | Prix, orderbook, spread, historique |
| **Data API** | `https://data-api.polymarket.com` | Positions, trades, analytics |

### Endpoints prioritaires pour ce projet

```python
# Découverte des marchés macro actifs
GET gamma-api.polymarket.com/events?active=true&limit=50

# Historique des prix (granularité 1 minute)
GET clob.polymarket.com/prices-history?token_id=XXX&fidelity=60

# Spread en temps réel
GET clob.polymarket.com/spread?token_id=XXX

# Orderbook complet
GET clob.polymarket.com/book?token_id=XXX

# Trades historiques onchain
GET data-api.polymarket.com/trades?market=XXX
```

### Format des données — point d'attention

```python
# outcomes et outcomePrices sont des strings JSON imbriquées
# Toujours faire json.loads() dessus
import json
outcomes = json.loads(market["outcomes"])        # ["Yes", "No"]
prices   = json.loads(market["outcomePrices"])   # ["0.20", "0.80"]
# Index 0 = Yes, Index 1 = No — mapping 1:1 garanti
```

---

## Modèle de données Polymarket

```
Event  (question globale)
  └── Market  (outcome tradable binaire)
        ├── condition_id      ← identifiant du contrat CTF
        ├── question_id       ← identifiant de la question UMA
        ├── clobTokenIds      ← [token_id_yes, token_id_no]
        ├── outcomes          ← string JSON ["Yes", "No"]
        ├── outcomePrices     ← string JSON ["0.XX", "0.XX"]
        └── enableOrderBook   ← bool, doit être True pour trader
```

Le **token_id** est l'identifiant fondamental pour toutes les requêtes CLOB.

---

## Authentification — Architecture L1/L2

```python
from py_clob_client.client import ClobClient
import os

host       = "https://clob.polymarket.com"
chain_id   = 137  # Polygon Mainnet
private_key = os.getenv("PRIVATE_KEY")

# Étape 1 — Client L1 temporaire (clé privée seulement)
temp_client = ClobClient(host, key=private_key, chain_id=chain_id)

# Étape 2 — Dériver les credentials L2 depuis la clé L1
# Déterministe : même clé privée → mêmes credentials L2 toujours
api_creds = temp_client.create_or_derive_api_creds()

# Étape 3 — Client final L1 + L2 (trading complet)
client = ClobClient(
    host,
    key=private_key,
    chain_id=chain_id,
    creds=api_creds,
    signature_type=0,              # 0 = EOA (wallet standard)
    funder="YOUR_WALLET_ADDRESS",  # adresse publique Polygon
)
```

Règle de sécurité absolue : la `PRIVATE_KEY` ne doit jamais apparaître dans le code. Toujours via `os.getenv()`.

---

## Mécanique des tokens (CTF — Conditional Token Framework)

Les tokens sont des **ERC1155 sur Polygon**, gérés par le Gnosis CTF.

| Opération | Description | Usage |
|-----------|-------------|-------|
| **Split** | $1 USDC.e → 1 Yes + 1 No | Créer de l'inventaire |
| **Trade** | Acheter/vendre sur le CLOB | Usage principal |
| **Merge** | 1 Yes + 1 No → $1 USDC.e | Arbitrage interne, sortie sans trade |
| **Redeem** | Token gagnant → $1 USDC.e | Après résolution |

**Invariant fondamental** : `Prix(Yes) + Prix(No) = $1.00` toujours.
Si cet invariant est brisé → opportunité d'arbitrage via Merge.

---

## Order Lifecycle

```
Création (EIP-712 signature)
    ↓
Soumission au CLOB
    ↓
Match ou Rest dans le book
    ↓
Settlement onchain (atomique)
    ↓
Confirmation sur Polygon
```

### Types d'ordres

| Type | Comportement |
|------|-------------|
| **GTC** | Good Till Cancelled — reste jusqu'à annulation |
| **GTD** | Good Till Date — expire à une date |
| **FOK** | Fill Or Kill — tout ou rien immédiatement |
| **FAK** | Fill And Kill — remplit ce qui est dispo |
| **Post-Only** | Toujours maker, jamais taker |

### Statuts d'un ordre

```
live      → dans le book, en attente
matched   → matché immédiatement
delayed   → délai 3s (marchés sports uniquement)
unmatched → délai expiré sans contrepartie
```

### Statuts d'un trade

```
MATCHED → MINED → CONFIRMED  ✅ terminal succès
                → RETRYING
                → FAILED     ❌ terminal échec
```

---

## Résolution des marchés (UMA Optimistic Oracle)

### Principe "Optimistic"

La proposition est supposée correcte par défaut. Si personne ne conteste dans les 2 heures → résolution automatique.

### Les 3 flows de résolution

```
Flow 1 (nominal)  : Proposition → 2h → Résolution ✅ (~2h)
Flow 2 (dispute)  : Proposition → Dispute → 2ème proposition → Résolution (~quelques heures)
Flow 3 (escalade) : Proposition → Dispute → 2ème dispute → Vote UMA → Résolution (~4-6 jours)
```

### Bonds et rewards

| Action | Bond | Reward si succès |
|--------|------|-----------------|
| Proposer | $750 USDC.e | $750 récupéré + **$2** |
| Disputer | $750 USDC.e | $750 + $375 (moitié bond adverse) |

**Attention** : Polymarket migre vers MOOV2 (Managed OOV2) — seules les adresses whitelistées peuvent proposer. Pour rejoindre la whitelist : 20+ propositions avec >95% de précision.

### Conditions pour proposer en sécurité

```python
# Avant toute proposition, vérifier les 3 conditions :
# 1. end_date du marché est passée
# 2. La source officielle spécifiée dans les règles a publié
# 3. La source dit exactement ce que la règle attend
# → Seulement si les 3 sont True → proposer
```

### Risques de résolution à gérer

- **Too Early** : proposer avant la source officielle → perte du bond
- **Outcome 50/50** : ambiguïté des règles → chaque token vaut $0.50
- **Résolution disputée** : capital bloqué 4-6 jours

---

## Analyse de marché — variables clés

Pour chaque marché, collecter et analyser :

| Variable | Calcul | Signification analytique |
|----------|--------|--------------------------|
| **Midpoint** | (Ask + Bid) / 2 | Probabilité implicite |
| **Spread** | Ask − Bid | Proxy d'incertitude / liquidité |
| **Last traded price** | — | Affiché si spread > $0.10 (signal d'illiquidité) |
| **Volume** | — | Conviction du marché |
| **Open Interest** | — | Taille totale des positions ouvertes |

Filtre qualité : **exclure ou pondérer les observations où spread > $0.10**.

---

## Pipeline de recherche — Preuve de l'indicateur psychologique

### Étape 1 — Collecte des données (Semaine 1)

```python
# Marchés cibles : macro et politique
categories = ["Fed", "CPI", "NFP", "elections", "geopolitique"]

# Polymarket : historique prix sur ces marchés
# → prices-history avec fidelity=60 (1 minute)

# Marchés financiers correspondants via yfinance :
# → ZN (futures taux 10 ans)
# → DXY (dollar index)
# → SPY (S&P 500)
# → GLD (or)
# → BTC-USD (bitcoin)
```

### Étape 2 — Alignement temporel (Semaine 1-2)

```python
import pandas as pd

# Problème : Polymarket 24/7 vs marchés financiers avec sessions
# Solution : pandas.merge_asof() pour aligner par timestamp
# Granularité commune : 15 minutes ou 1 heure
# Attention aux timezones : Polygon UTC vs NYSE EST
```

### Étape 3 — Preuve de calibration de la foule (Semaine 2)

```python
# Brier Score = mesure de précision probabiliste
# BS = (1/N) × Σ(prix_polymarket - outcome_réel)²
# Plus le BS est proche de 0, plus la foule est calibrée

# Comparer contre :
# → Consensus Bloomberg (sondages économistes)
# → Probabilités implicites des options (marché des options)
# → Fear & Greed Index
# → Sondages d'opinion classiques
```

### Étape 4 — Test de corrélation (Semaine 3)

```python
from statsmodels.tsa.stattools import grangercausalitytests

# Test de Granger : Polymarket lead-il les marchés financiers ?
# H0 : Polymarket ne cause pas (au sens Granger) les prix financiers
# Si p-value < 0.05 → signal statistiquement significatif

# Cross-correlation avec différents lags :
# lag 0 = simultané
# lag +1h = Polymarket lead d'1 heure
# lag +1j = Polymarket lead d'1 jour
```

### Étape 5 — Construction de l'indicateur (Semaine 4)

```python
# Signal : variation du prix Polymarket sur une fenêtre glissante
# → rolling_delta = prix[t] - prix[t-4h]

# Backtest :
# → Sharpe ratio du signal
# → Maximum drawdown
# → Win rate sur les trades déclenchés par le signal
```

---

## Opportunités identifiées sur Polymarket

### Par ordre de priorité et d'accessibilité

**1. Late-stage market making (résolution proche)**
Acheter des tokens quasi-certains à $0.93-$0.96, redeem à $1.00.
Risque faible si les règles de résolution sont claires.

**2. Spread collection (market making passif)**
Quoter bid/ask autour du mid, collecter le spread.
Nécessite du volume et une gestion d'inventaire via Split/Merge.

**3. Arbitrage cross-market (Polymarket vs Kalshi)**
```
Si Yes(Polymarket) + No(Kalshi) < $1.00 → acheter les deux
```
Risque principal : résolution divergente entre les deux plateformes.

**4. Dispute de mauvaises résolutions**
Monitorer les propositions UMA, disputer les incorrectes.
Profit : $375 si on a raison.

**5. Favorite-longshot bias**
Les marchés à faible probabilité ($0.03-$0.10) sont systématiquement surévalués.
Shorter les longshots sur des séries de marchés similaires.

---

## Règles de développement

### Sécurité

```python
# TOUJOURS utiliser les variables d'environnement
private_key = os.getenv("PRIVATE_KEY")    # ✅
private_key = "0xabc123..."               # ❌ jamais

# .env dans .gitignore — toujours
# .env.example dans le repo — toujours
```

### Gestion des erreurs et rate limits

```python
# Implémenter exponential backoff sur toutes les requêtes API
# Rate limits Polymarket : vérifier docs/api-reference/rate-limits
# Utiliser tenacity pour le retry automatique

from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_market_data(token_id):
    ...
```

### Heartbeat pour les bots de trading

```python
# Si pas de heartbeat toutes les ~15 secondes
# → Polymarket annule TOUS les ordres ouverts automatiquement
# C'est un dead-man's switch de sécurité — toujours implémenter

async def heartbeat_loop(client):
    while True:
        client.post_heartbeat()
        await asyncio.sleep(15)
```

### Validation des données

```python
# Avant d'utiliser un prix Polymarket :
# 1. Vérifier que spread < $0.10 (sinon c'est last_trade_price affiché)
# 2. Vérifier que enableOrderBook == True
# 3. Vérifier que le marché n'est pas resolved
```

---

## Stratégie de visibilité GitHub et réseaux

### Structure des commits

- Committer régulièrement, même les petites choses
- Un historique actif raconte la progression
- Nommer les commits de façon descriptive en anglais

### Cadence de publication

- **Fin de chaque phase** → push GitHub + post LinkedIn/X avec un visuel
- **Résultats analytiques intéressants** → post X dans la communauté Polymarket
- **Articles techniques** → Substack ou blog (ex: "Comment j'ai analysé les inefficiences de Polymarket")

### Output final visé

```
"Sur les 50 dernières décisions de la Fed,
Polymarket avait le bon outcome à J-7 dans 89% des cas,
contre 71% pour le consensus Bloomberg.

Dans les cas où Polymarket divergeait fortement
du consensus des économistes,
les marchés obligataires bougeaient en moyenne
de X% dans le sens Polymarket."
```

---

## Ressources et documentation

| Ressource | URL |
|-----------|-----|
| Documentation Polymarket | https://docs.polymarket.com |
| Index complet de la doc | https://docs.polymarket.com/llms.txt |
| Oracle UMA | https://oracle.uma.xyz |
| Subgraph Polymarket | https://docs.polymarket.com/market-data/subgraph.md |
| Contrats Polygon | https://docs.polymarket.com/resources/contract-addresses.md |
| SDK Python | https://github.com/Polymarket/py-clob-client |
| CTF Gnosis | https://github.com/gnosis/conditional-tokens-contracts |

---

## Notions théoriques maîtrisées

- **CLOB** (Central Limit Order Book) : carnet d'ordres centralisé, makers/takers, spread, slippage
- **Bayesian adjustment** : mise à jour des croyances via la règle de Bayes, prior/posterior
- **Price discovery** : émergence du prix via confrontation d'ordres complémentaires
- **Adverse selection** : risque pour le market maker d'avoir en face un trader informé
- **Spread decomposition** (Glosten-Milgrom) : adverse selection + inventory cost + processing
- **Wisdom of crowds** : agrégation de l'information dispersée via les prix
- **No-trade theorem** (Milgrom-Stokey) : pourquoi les marchés fonctionnent malgré la rationalité
- **Favorite-longshot bias** : surcotat systématique des événements à faible probabilité
- **Arbitrage cross-market** : Yes(A) + No(B) < $1.00 → opportunité sans risque théorique
- **EIP-712** : standard de signature de messages structurés sur Ethereum/Polygon
- **CTF** (Conditional Token Framework) : mécanique Split/Merge/Redeem
- **UMA Optimistic Oracle** : système de résolution décentralisé par bonds et disputes

---

*Ce fichier doit être maintenu à jour à chaque avancée significative du projet.*
*Dernière mise à jour : début du projet — phase 1 non démarrée.*
