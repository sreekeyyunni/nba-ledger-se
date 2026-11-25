# ML backtest for the game predictor

An experiment, not part of the nightly run. It asks: would a machine-learning model
pick games better than the hand-built formula in `pipeline/predict.py`?

- `fetch_history.py`, `fetch_rosters.py`: one-time Basketball Reference downloads (results and
  player stats, 2015-16 to 2025-26), cached in `data/`. Run on GitHub by `.github/workflows/ml-backtest.yml`.
- `features.py`: what a model knows before tip-off, from earlier dates only (Elo, opponent-adjusted
  margin, recent form, rest, preseason roster strength, and the formula's own margin replayed without injuries).
- `rosters.py`: preseason roster ratings, the formula's way (last season's WS/48 x minutes).
- `backtest.py`: trains each model on past seasons only, scores 2021-22 to 2025-26 season by season,
  then scores this season against the formula's locked picks in `outputs/predictions_log.csv` (read only).
- `results/`: `summary.md` (tables), `metrics.csv`, `h2h_2026_27.csv`, `picks_2026_27.csv`.

## Verdict (Nov 25, 2026)

No model clearly beats the formula, so live picks stay as they are.

- Over 6,183 games (2022-2026), the fancy models (random forest, gradient boosting, neural net,
  k-NN) did worse than a replay of the formula. Plain linear and logistic regression did a hair
  better: 66.0% vs. 65.7% of winners, about 4 more right picks a season.
- This season (260 games), the real formula, which also knows injuries, is level with the best
  models: 68.8% for both, log loss 0.594 vs. 0.593.
- The formula is already close to the best simple model. Better inputs (injuries, lineups) are more
  likely to help than a fancier algorithm.

Caveat: past rosters come from each season's stats page, so a player who never played that season
is missing. That helps the formula replay and the models equally.
