# Notes théoriques — Phase 1

## Prediction Markets

Un marché de prédiction est un marché où les participants achètent et vendent des contrats dont le paiement dépend d'un événement futur. Le prix d'un contrat "Yes" à $0.75 signifie que le marché estime la probabilité de l'événement à 75%.

## Pourquoi Polymarket est spécial

- **Argent réel** : chaque position coûte de l'argent → filtre les opinions faibles
- **24/7** : contrairement aux marchés financiers, Polymarket ne dort jamais
- **Granularité** : des marchés sur des événements très spécifiques (décision Fed, résultat CPI exact)
- **Transparence** : toutes les transactions sont onchain sur Polygon (autrement dit elles sont accessibles sur la blockchain de Polygon)

## Les 3 APIs Polymarket

| API | Usage | Auth requise |
|-----|-------|--------------|
| **Gamma** (`gamma-api.polymarket.com`) | Découverte des marchés, recherche | Non |
| **CLOB** (`clob.polymarket.com`) | Prix, orderbook, trading | Oui (pour trading) |
| **Data** (`data-api.polymarket.com`) | Positions, trades historiques | Non |

## Invariant fondamental

Pour tout marché binaire : `Prix(Yes) + Prix(No) = $1.00`

Si cet invariant est brisé → opportunité d'arbitrage.

## Données imbriquées

Les champs `outcomes` et `outcomePrices` sont des strings JSON qu'il faut parser avec `json.loads()`.
