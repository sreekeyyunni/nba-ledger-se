# ML backtest: game predictor

Lower log loss and Brier are better. Accuracy = share of winners picked.

## Past five seasons (2022-2026, about 6,000 games, walk-forward)

| Model | Accuracy | Log loss | Brier |
|---|---|---|---|
| Logistic regression | 65.7% | 0.6180 | 0.2147 |
| Formula replay (no injuries) | 65.7% | 0.6184 | 0.2149 |
| Average of LR + boosting | 65.4% | 0.6196 | 0.2153 |
| Neural network | 65.6% | 0.6199 | 0.2154 |
| Random forest | 65.6% | 0.6207 | 0.2158 |
| Extra trees | 65.5% | 0.6209 | 0.2158 |
| Gradient boosting | 65.3% | 0.6226 | 0.2165 |
| Hist. gradient boosting (LightGBM-style) | 64.9% | 0.6227 | 0.2166 |
| k-nearest neighbors | 65.4% | 0.6257 | 0.2179 |
| Elo (hand-tuned) | 65.2% | 0.6403 | 0.2228 |
| Home team always | 55.4% | 0.6878 | 0.2473 |

## This season vs. the current formula's locked picks

| Model | Games | Accuracy | Log loss | Brier | Beats formula in resamples |
|---|---|---|---|---|---|
| Formula + best ML blend | 260 | 68.8% | 0.5931 | 0.2024 | 55% |
| Current formula | 260 | 68.8% | 0.5937 | 0.2015 | 0% |
| Average of LR + boosting | 260 | 68.8% | 0.5966 | 0.2050 | 38% |
| Hist. gradient boosting (LightGBM-style) | 260 | 68.8% | 0.5967 | 0.2050 | 39% |
| Logistic regression | 260 | 68.8% | 0.5981 | 0.2055 | 31% |
| Formula replay (no injuries) | 260 | 67.7% | 0.5992 | 0.2049 | 19% |
| Gradient boosting | 260 | 69.2% | 0.6000 | 0.2062 | 27% |
| Random forest | 260 | 68.5% | 0.6017 | 0.2071 | 17% |
| Neural network | 260 | 67.3% | 0.6035 | 0.2075 | 16% |
| Extra trees | 260 | 68.1% | 0.6040 | 0.2074 | 10% |
| k-nearest neighbors | 260 | 67.7% | 0.6086 | 0.2098 | 9% |
| Elo (hand-tuned) | 260 | 66.9% | 0.6233 | 0.2149 | 6% |
| Home team always | 260 | 51.5% | 0.6971 | 0.2520 | 0% |

Live picks only (made before tip-off with injury news):

| Model | Games | Accuracy | Log loss | Brier |
|---|---|---|---|---|
| Formula + best ML blend | 224 | 69.6% | 0.5968 | 0.2038 |
| Average of LR + boosting | 224 | 69.6% | 0.5971 | 0.2052 |
| Hist. gradient boosting (LightGBM-style) | 224 | 69.2% | 0.5972 | 0.2053 |
| Gradient boosting | 224 | 70.1% | 0.5986 | 0.2054 |
| Logistic regression | 224 | 69.6% | 0.5986 | 0.2056 |
| Current formula | 224 | 69.2% | 0.6011 | 0.2045 |
| Random forest | 224 | 69.2% | 0.6020 | 0.2072 |
| Extra trees | 224 | 69.2% | 0.6043 | 0.2074 |
| Formula replay (no injuries) | 224 | 67.9% | 0.6048 | 0.2072 |
| Neural network | 224 | 67.4% | 0.6088 | 0.2096 |
| k-nearest neighbors | 224 | 67.4% | 0.6090 | 0.2099 |
| Elo (hand-tuned) | 224 | 68.3% | 0.6219 | 0.2131 |
| Home team always | 224 | 51.8% | 0.6965 | 0.2517 |

Best ML model on past seasons: Logistic regression.

Settings picked on 2019-2021:

- Logistic regression: {'C': 0.01}
- Random forest: {'n': 400, 'leaf': 100, 'feats': 0.33}
- Extra trees: {'leaf': 50}
- Gradient boosting: {'n': 150, 'depth': 2, 'lr': 0.02}
- Hist. gradient boosting (LightGBM-style): {'it': 150, 'leaves': 7, 'lr': 0.02}
- Neural network: {'hidden': (16,), 'alpha': 1.0}
- k-nearest neighbors: {'k': 250}
