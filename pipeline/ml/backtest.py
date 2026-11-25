"""
Backtest machine-learning game predictors against the current formula: python ml/backtest.py

Data (run from pipeline/):
  ml/data/games_history.csv      past regular seasons (ml/fetch_history.py)
  data/schedule_2026_27.csv      this season so far
  outputs/predictions_log.csv    the formula's locked picks (read only, never written)

How it stays honest:
  * Features for a game use only games from earlier dates (ml/features.py).
  * Walk-forward by season: to test season S, models train on seasons before S only.
  * Settings for each model are picked on 2019-2021 (trained on earlier seasons) and
    then frozen before the 2022-2026 test seasons and this season are scored.
  * This season, each model is compared game by game with the formula's own locked pick.

Writes ml/results/metrics.csv, ml/results/h2h_2026_27.csv and ml/results/summary.md.
"""
import csv
import itertools
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES, build_features  # noqa: E402
from rosters import roster_ratings  # noqa: E402

from sklearn.ensemble import (ExtraTreesClassifier, GradientBoostingClassifier,  # noqa: E402
                              HistGradientBoostingClassifier, RandomForestClassifier)
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.neural_network import MLPClassifier  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

warnings.filterwarnings("ignore")
HISTORY = Path("ml/data/games_history.csv")
THIS_SEASON = Path("data/schedule_2026_27.csv")
LOG = Path("outputs/predictions_log.csv")
RESULTS = Path("ml/results")
CURRENT = 2027
FIRST_TRAIN = 2017          # 2016 only warms up Elo and "last season"
TUNE_SEASONS = [2019, 2020, 2021]
TEST_SEASONS = [2022, 2023, 2024, 2025, 2026]
SEED = 7

MODELS = {
    "Logistic regression": (
        lambda C: make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000)),
        {"C": [0.001, 0.01, 0.1, 1.0]}),
    "Random forest": (
        lambda n, leaf, feats: RandomForestClassifier(n_estimators=n, min_samples_leaf=leaf, max_features=feats,
                                                      n_jobs=-1, random_state=SEED),
        {"n": [400], "leaf": [25, 50, 100], "feats": [0.33, 0.6]}),
    "Extra trees": (
        lambda leaf: ExtraTreesClassifier(n_estimators=400, min_samples_leaf=leaf, max_features=0.5,
                                          n_jobs=-1, random_state=SEED),
        {"leaf": [25, 50, 100]}),
    "Gradient boosting": (
        lambda n, depth, lr: GradientBoostingClassifier(n_estimators=n, max_depth=depth, learning_rate=lr,
                                                        subsample=0.8, random_state=SEED),
        {"n": [150, 400], "depth": [2, 3], "lr": [0.02, 0.05]}),
    "Hist. gradient boosting (LightGBM-style)": (
        lambda it, leaves, lr: HistGradientBoostingClassifier(max_iter=it, max_leaf_nodes=leaves, learning_rate=lr,
                                                              l2_regularization=1.0, min_samples_leaf=50,
                                                              random_state=SEED),
        {"it": [150, 400], "leaves": [7, 15], "lr": [0.02, 0.05]}),
    "Neural network": (
        lambda hidden, alpha: make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=hidden, alpha=alpha,
                                                                            max_iter=600, early_stopping=True,
                                                                            random_state=SEED)),
        {"hidden": [(16,), (32, 16)], "alpha": [0.01, 0.1, 1.0]}),
    "k-nearest neighbors": (
        lambda k: make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=k)),
        {"k": [100, 250, 500]}),
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_games():
    games = []
    for r in read_csv(HISTORY):
        if r.get("playoffs") == "1":
            continue
        games.append({"season": int(r["season"]), "date": r["date"], "home": r["home"], "away": r["away"],
                      "home_pts": r["home_pts"], "away_pts": r["away_pts"]})
    for r in read_csv(THIS_SEASON):
        games.append({"season": CURRENT, "date": r["date"], "home": r["home"], "away": r["away"],
                      "home_pts": r["home_pts"], "away_pts": r["away_pts"]})
    games.sort(key=lambda g: (g["date"], g["home"]))
    return games


def metrics(y, p):
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return {"n": len(y), "accuracy": float(((p >= 0.5) == (y == 1)).mean()),
            "log_loss": float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()),
            "brier": float(((p - y) ** 2).mean())}


def fit_predict(name, params, Xtr, ytr, Xte):
    make, _ = MODELS[name]
    m = make(**params)
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def main():
    games = load_games()
    roster = roster_ratings(sorted({g["season"] for g in games}))
    have = sorted({s for s, _ in roster})
    print(f"roster ratings for seasons {have}")
    feats = build_features(games, roster)
    X = np.array([[f[k] for k in FEATURES] for f in feats])
    y = np.array([f["home_win"] if f["home_win"] is not None else -1 for f in feats])
    season = np.array([g["season"] for g in games])
    elo_p = np.array([f["elo_prob"] for f in feats])
    formula_replay = np.array([f["formula_prob"] for f in feats])
    played = y >= 0
    print(f"{played.sum()} played games, seasons {season.min()}-{season.max()}")

    def split(test_season):
        tr = played & (season >= FIRST_TRAIN) & (season < test_season)
        te = played & (season == test_season)
        return tr, te

    # 1) pick settings on the tuning seasons
    best = {}
    for name, (_, grid) in MODELS.items():
        scores = []
        for combo in itertools.product(*grid.values()):
            params = dict(zip(grid.keys(), combo))
            ll = []
            for s in TUNE_SEASONS:
                tr, te = split(s)
                ll.append(metrics(y[te], fit_predict(name, params, X[tr], y[tr], X[te]))["log_loss"])
            scores.append((float(np.mean(ll)), params))
        scores.sort(key=lambda x: x[0])
        best[name] = scores[0][1]
        print(f"  {name}: {best[name]} (tuning log loss {scores[0][0]:.4f})")

    # 2) walk forward through the test seasons and this season
    preds = {}          # model -> array of probabilities (nan where not predicted)
    for name in list(MODELS) + ["Home team always", "Elo (hand-tuned)", "Formula replay (no injuries)", "Average of LR + boosting"]:
        preds[name] = np.full(len(y), np.nan)
    for s in TEST_SEASONS + [CURRENT]:
        tr, te = split(s)
        te_all = (season == s) & played
        for name, params in best.items():
            preds[name][te_all] = fit_predict(name, params, X[tr], y[tr], X[te_all])
        preds["Home team always"][te_all] = y[tr].mean()
        preds["Elo (hand-tuned)"][te_all] = elo_p[te_all]
        preds["Formula replay (no injuries)"][te_all] = formula_replay[te_all]
        print(f"  season {s}: trained on {tr.sum()} games, scored {te_all.sum()}")
    preds["Average of LR + boosting"] = (preds["Logistic regression"]
                                         + preds["Hist. gradient boosting (LightGBM-style)"]) / 2

    rows = []
    for name, p in preds.items():
        for s in TEST_SEASONS + [CURRENT]:
            m = (season == s) & played
            rows.append({"model": name, "season": s, **metrics(y[m], p[m])})
        m = np.isin(season, TEST_SEASONS) & played
        rows.append({"model": name, "season": "2022-2026", **metrics(y[m], p[m])})

    # 3) head to head with the formula's locked picks this season
    log = {(r["date"], r["away"], r["home"]): r for r in read_csv(LOG)}
    idx, formula_p, modes = [], [], []
    for i, g in enumerate(games):
        k = (g["date"], g["away"], g["home"])
        if g["season"] == CURRENT and played[i] and k in log:
            idx.append(i)
            formula_p.append(float(log[k]["home_prob"]))
            modes.append(log[k]["mode"])
    idx = np.array(idx)
    formula_p = np.array(formula_p)
    modes = np.array(modes)
    yh = y[idx]
    h2h = {"Current formula": formula_p}
    for name, p in preds.items():
        h2h[name] = p[idx]
    h2h["Formula + best ML blend"] = None   # filled below

    pooled = {r["model"]: r for r in rows if r["season"] == "2022-2026"}
    best_ml = min((n for n in MODELS), key=lambda n: pooled[n]["log_loss"])
    h2h["Formula + best ML blend"] = (formula_p + h2h[best_ml]) / 2

    rng = np.random.default_rng(SEED)

    def ll_vec(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(yh * np.log(p) + (1 - yh) * np.log(1 - p))

    f_ll = ll_vec(formula_p)
    h2h_rows = []
    for name, p in h2h.items():
        for subset, mask in (("all", np.ones(len(idx), bool)), ("live", modes == "live")):
            r = {"model": name, "games": subset, **metrics(yh[mask], p[mask])}
            d = (ll_vec(p) - f_ll)[mask]
            bs = d[rng.integers(0, len(d), size=(5000, len(d)))].mean(axis=1)
            r["log_loss_vs_formula"] = float(d.mean())
            r["share_of_resamples_better_than_formula"] = float((bs < 0).mean())
            h2h_rows.append(r)

    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / "metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "season", "n", "accuracy", "log_loss", "brier"])
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    with open(RESULTS / "h2h_2026_27.csv", "w", newline="") as f:
        keys = ["model", "games", "n", "accuracy", "log_loss", "brier", "log_loss_vs_formula",
                "share_of_resamples_better_than_formula"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in h2h_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    # per-game picks this season, so anyone can check
    with open(RESULTS / "picks_2026_27.csv", "w", newline="") as f:
        w = csv.writer(f)
        names = list(h2h)
        w.writerow(["date", "away", "home", "home_win", "mode"] + names)
        for j, i in enumerate(idx):
            g = games[i]
            w.writerow([g["date"], g["away"], g["home"], yh[j], modes[j]] + [f"{h2h[n][j]:.3f}" for n in names])

    write_summary(rows, h2h_rows, best, best_ml)
    print((RESULTS / "summary.md").read_text())


def write_summary(rows, h2h_rows, best, best_ml):
    pooled = sorted((r for r in rows if r["season"] == "2022-2026"), key=lambda r: r["log_loss"])
    lines = ["# ML backtest: game predictor", "",
             "Lower log loss and Brier are better. Accuracy = share of winners picked.", "",
             "## Past five seasons (2022-2026, about 6,000 games, walk-forward)", "",
             "| Model | Accuracy | Log loss | Brier |", "|---|---|---|---|"]
    for r in pooled:
        lines.append(f"| {r['model']} | {r['accuracy']:.1%} | {r['log_loss']:.4f} | {r['brier']:.4f} |")
    lines += ["", "## This season vs. the current formula's locked picks", "",
              "| Model | Games | Accuracy | Log loss | Brier | Beats formula in resamples |",
              "|---|---|---|---|---|---|"]
    for r in sorted((r for r in h2h_rows if r["games"] == "all"), key=lambda r: r["log_loss"]):
        lines.append(f"| {r['model']} | {r['n']} | {r['accuracy']:.1%} | {r['log_loss']:.4f} | {r['brier']:.4f} | "
                     f"{r['share_of_resamples_better_than_formula']:.0%} |")
    lines += ["", "Live picks only (made before tip-off with injury news):", "",
              "| Model | Games | Accuracy | Log loss | Brier |", "|---|---|---|---|---|"]
    for r in sorted((r for r in h2h_rows if r["games"] == "live"), key=lambda r: r["log_loss"]):
        lines.append(f"| {r['model']} | {r['n']} | {r['accuracy']:.1%} | {r['log_loss']:.4f} | {r['brier']:.4f} |")
    lines += ["", f"Best ML model on past seasons: {best_ml}.", "", "Settings picked on 2019-2021:", ""]
    for n, p in best.items():
        lines.append(f"- {n}: {p}")
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
