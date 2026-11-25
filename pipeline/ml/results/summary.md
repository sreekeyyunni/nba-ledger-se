# ML backtest: game predictor

Lower log loss and Brier are better. Accuracy = share of winners picked.

## Past five seasons (2022-2026, about 6,000 games, walk-forward)

| Model | Accuracy | Log loss | Brier | Beats formula replay in resamples |
|---|---|---|---|---|
| Linear regression on margin | 66.0% | 0.6166 | 0.2140 | 94% |
| Logistic regression | 65.7% | 0.6173 | 0.2144 | 82% |
| Average of LR + boosting | 65.7% | 0.6182 | 0.2147 | 57% |
| Formula replay (no injuries) | 65.7% | 0.6184 | 0.2149 | 0% |
| Random forest | 65.7% | 0.6197 | 0.2153 | 14% |
| Extra trees | 65.7% | 0.6197 | 0.2153 | 12% |
| Hist. gradient boosting (LightGBM-style) | 65.3% | 0.6206 | 0.2157 | 5% |
| Gradient boosting | 65.7% | 0.6206 | 0.2156 | 5% |
| Neural network | 65.4% | 0.6208 | 0.2158 | 5% |
| k-nearest neighbors | 65.7% | 0.6242 | 0.2173 | 0% |
| Elo (hand-tuned) | 65.2% | 0.6403 | 0.2228 | 0% |
| Home team always | 55.4% | 0.6878 | 0.2473 | 0% |

## This season vs. the current formula's locked picks

| Model | Games | Accuracy | Log loss | Brier | Beats formula in resamples |
|---|---|---|---|---|---|
| Formula + best ML blend | 260 | 68.5% | 0.5916 | 0.2017 | 65% |
| Hist. gradient boosting (LightGBM-style) | 260 | 68.8% | 0.5930 | 0.2034 | 52% |
| Average of LR + boosting | 260 | 69.2% | 0.5934 | 0.2036 | 50% |
| Current formula | 260 | 68.8% | 0.5937 | 0.2015 | 0% |
| Gradient boosting | 260 | 68.8% | 0.5955 | 0.2041 | 42% |
| Logistic regression | 260 | 68.5% | 0.5955 | 0.2044 | 42% |
| Linear regression on margin | 260 | 67.7% | 0.5962 | 0.2046 | 39% |
| Neural network | 260 | 66.9% | 0.5967 | 0.2040 | 37% |
| Random forest | 260 | 68.8% | 0.5970 | 0.2050 | 35% |
| Formula replay (no injuries) | 260 | 67.7% | 0.5992 | 0.2049 | 19% |
| Extra trees | 260 | 69.2% | 0.6015 | 0.2061 | 16% |
| k-nearest neighbors | 260 | 67.7% | 0.6075 | 0.2093 | 10% |
| Elo (hand-tuned) | 260 | 66.9% | 0.6233 | 0.2149 | 5% |
| Home team always | 260 | 51.5% | 0.6971 | 0.2520 | 0% |

Live picks only (made before tip-off with injury news):

| Model | Games | Accuracy | Log loss | Brier |
|---|---|---|---|---|
| Formula + best ML blend | 224 | 69.6% | 0.5959 | 0.2035 |
| Average of LR + boosting | 224 | 70.1% | 0.5967 | 0.2050 |
| Logistic regression | 224 | 69.6% | 0.5971 | 0.2049 |
| Linear regression on margin | 224 | 69.2% | 0.5979 | 0.2051 |
| Hist. gradient boosting (LightGBM-style) | 224 | 69.2% | 0.5980 | 0.2056 |
| Gradient boosting | 224 | 69.6% | 0.5992 | 0.2057 |
| Neural network | 224 | 67.0% | 0.6000 | 0.2054 |
| Random forest | 224 | 69.6% | 0.6004 | 0.2064 |
| Current formula | 224 | 69.2% | 0.6011 | 0.2045 |
| Extra trees | 224 | 70.1% | 0.6041 | 0.2070 |
| Formula replay (no injuries) | 224 | 67.9% | 0.6048 | 0.2072 |
| k-nearest neighbors | 224 | 67.4% | 0.6082 | 0.2096 |
| Elo (hand-tuned) | 224 | 68.3% | 0.6219 | 0.2131 |
| Home team always | 224 | 51.8% | 0.6965 | 0.2517 |

Best ML model on past seasons: Linear regression on margin.

Settings picked on 2019-2021:

- Linear regression on margin: {'alpha': 100.0}
- Logistic regression: {'C': 0.01}
- Random forest: {'n': 400, 'leaf': 100, 'feats': 0.33}
- Extra trees: {'leaf': 50}
- Gradient boosting: {'n': 150, 'depth': 2, 'lr': 0.02}
- Hist. gradient boosting (LightGBM-style): {'it': 150, 'leaves': 7, 'lr': 0.02}
- Neural network: {'hidden': (32, 16), 'alpha': 1.0}
- k-nearest neighbors: {'k': 250}
