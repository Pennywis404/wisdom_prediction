# Deprecated

Notebooks and scripts kept for traceability of the research process but no longer
part of the active pipeline.

## `tfidf_classification_polymarket_v2.ipynb`

First attempt at classifying the 607K Polymarket markets into 15 categories.

**Pipeline**: `labeled_500.csv` → TF-IDF (unigrams + bigrams, 10K features) →
Logistic Regression (class-weight balanced) → predictions.

**Why deprecated**:

| Metric | TF-IDF + LogReg | Regex (Le 2026 + extensions) |
|---|---|---|
| Training set | 500 labels (very unbalanced) | 0 (zero-shot) |
| F1 macro (5-fold CV) | **0.59 ± 0.08** | — |
| F1 macro on `labeled_1500.csv` | — | **0.81** |
| Prediction confidence (mean) | 0.18 (very low) | deterministic |
| Reproducibility | Depends on training seed | Deterministic regex |
| Academic attribution | None | Le (2026), arXiv:2602.19520 |

The TF-IDF approach was abandoned because:
1. `labeled_500.csv` is severely unbalanced (Sports 222, Weather 1, Press 1) — many
   classes have too few samples for a 5-fold CV.
2. Mean prediction confidence on 607K markets was **0.18** (median 0.16) —
   essentially random guessing for many predictions.
3. TF-IDF captures surface-level lexical patterns but misses context
   (e.g. "SSC Bari" classified as Geopolitics because of "Bari" → Italy).

The current approach (see `../notebooks/04_classification.ipynb`) uses the regex
patterns published with Le, N.A. (2026), *Decomposing Crowd Wisdom*
(arXiv:2602.19520, MIT license), extended with custom sub-patterns for the 15
project categories. It achieves F1 macro 0.81 on the balanced `labeled_1500.csv`
validation set, with zero training required.
