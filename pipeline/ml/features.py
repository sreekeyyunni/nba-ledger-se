"""
Game features for the ML predictor, built only from games played on earlier dates.

Everything here comes from final scores (no box scores, no players), so it can be
rebuilt for any past season from one results file. For each game, both teams get:

  elo        538-style Elo (K=20, margin-of-victory multiplier), carried across seasons
             with 25% regression to the mean
  srs        opponent-adjusted margin so far this season (ridge least squares; shrinks
             toward 0 early in the season)
  mov        average margin so far (capped at 25), and the formula's shrunk version
  last10/5   average margin over the last 10 and 5 games
  prior      last season's final opponent-adjusted margin
  win_pct    share of games won so far
  rest       days since the last game (capped at 4); b2b and 3-in-4-nights flags
  road       how many road games in a row this team has played going in
  roster     preseason roster rating, as the live formula rates a roster (ml/rosters.py)
  formula    the live formula's predicted margin, replayed without injuries
             (roster + form + home court - back-to-back), so models can build on it

Results of a date only feed games on later dates, so no game ever sees its own score.
"""
import math
from collections import defaultdict, deque

import numpy as np

MARGIN_CAP = 25
ELO_K = 20
ELO_HOME = 100
ELO_MEAN = 1505
ELO_CARRY = 0.75
SRS_RIDGE = 3.0      # games of "average team" prior in the opponent-adjusted margin

FEATURES = [
    "elo_diff", "srs_diff", "mov_diff", "mov_shrunk_diff", "last10_diff", "last5_diff", "prior_diff",
    "winpct_diff", "rest_h", "rest_a", "b2b_h", "b2b_a", "three_in_four_h", "three_in_four_a",
    "road_h", "road_a", "gp_min", "roster_diff", "formula_margin",
]


def _elo_prob(diff):
    return 1 / (1 + 10 ** (-diff / 400))


def _srs(games, teams):
    """Ridge least squares: margin = r_home - r_away + hca. Returns {team: rating}."""
    if not games:
        return {t: 0.0 for t in teams}
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X = np.zeros((len(games), n + 1))
    y = np.zeros(len(games))
    for k, (h, a, m) in enumerate(games):
        X[k, idx[h]] = 1
        X[k, idx[a]] = -1
        X[k, n] = 1
        y[k] = m
    pen = np.eye(n + 1) * SRS_RIDGE
    pen[n, n] = 0.01
    beta = np.linalg.solve(X.T @ X + pen, X.T @ y)
    r = beta[:n] - beta[:n].mean()
    return {t: float(r[idx[t]]) for t in teams}


def build_features(games, roster=None):
    """games: list of dicts with season, date (ISO), home, away, home_pts, away_pts
    (empty strings for games not played yet), sorted by date.
    Returns a list of feature dicts (one per game, same order) with the target `home_win`
    (None if not played) and `elo_prob` (Elo's own home win probability)."""
    roster = roster or {}
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
    elo = {t: ELO_MEAN for t in teams}
    prior = defaultdict(float)          # (season, team) -> last season's final srs
    out = []
    by_date = defaultdict(list)
    for i, g in enumerate(games):
        by_date[(g["season"], g["date"])].append(i)

    season = None
    for (s, d) in sorted(by_date, key=lambda k: (k[0], k[1])):
        if s != season:
            if season is not None:      # close the old season
                final = _srs(season_games, teams)
                for t in teams:
                    prior[(s, t)] = final[t]
                for t in teams:
                    elo[t] = ELO_MEAN + ELO_CARRY * (elo[t] - ELO_MEAN)
            season = s
            season_games = []
            margins = defaultdict(list)
            wins = defaultdict(int)
            last_dates = defaultdict(list)
            road = defaultdict(int)
            resid = defaultdict(list)    # the live formula's "form": margin vs. roster expectation
            srs_now = {t: 0.0 for t in teams}
        day = _day(d)
        for i in by_date[(s, d)]:
            g = games[i]
            h, a = g["home"], g["away"]
            f = {}

            def team_stats(t):
                m = margins[t]
                gp = len(m)
                rest = min(4, day - last_dates[t][-1]) if last_dates[t] else 4
                recent = [x for x in last_dates[t] if day - x <= 3]
                return {
                    "elo": elo[t], "srs": srs_now[t], "gp": gp,
                    "mov": sum(m) / gp if gp else 0.0,
                    "mov_shrunk": sum(m) / (gp + 8),
                    "last10": sum(m[-10:]) / len(m[-10:]) if gp else 0.0,
                    "last5": sum(m[-5:]) / len(m[-5:]) if gp else 0.0,
                    "prior": prior[(s, t)],
                    "winpct": (wins[t] + 2) / (gp + 4),
                    "rest": rest, "b2b": int(rest == 1), "three_in_four": int(len(recent) >= 2),
                    "road": road[t],
                }

            th, ta = team_stats(h), team_stats(a)
            for k in ("elo", "srs", "mov", "mov_shrunk", "last10", "last5", "prior", "winpct"):
                f[f"{k}_diff" if k != "winpct" else "winpct_diff"] = th[k] - ta[k]
            for k in ("rest", "b2b", "three_in_four", "road"):
                f[f"{k}_h"], f[f"{k}_a"] = th[k], ta[k]
            f["gp_min"] = min(th["gp"], ta["gp"])
            f["roster_diff"] = roster.get((s, h), 0.0) - roster.get((s, a), 0.0)
            # replay of the live formula without injuries: roster + form + home court - back-to-back
            form = lambda t: sum(resid[t]) / (len(resid[t]) + 8)  # noqa: E731
            fm = f["roster_diff"] + form(h) - form(a) + 2.3 - 1.5 * th["b2b"] + 1.5 * ta["b2b"]
            f["formula_margin"] = fm
            f["formula_prob"] = 0.5 * (1 + math.erf(fm / 11.5 / math.sqrt(2)))
            f["elo_prob"] = _elo_prob(th["elo"] - ta["elo"] + ELO_HOME)
            played = g["home_pts"] not in ("", None) and g["away_pts"] not in ("", None)
            f["home_win"] = (int(float(g["home_pts"]) > float(g["away_pts"])) if played else None)
            out.append((i, f))
        # after the whole date: feed results forward
        for i in by_date[(s, d)]:
            g = games[i]
            if g["home_pts"] in ("", None) or g["away_pts"] in ("", None):
                continue
            h, a = g["home"], g["away"]
            raw = float(g["home_pts"]) - float(g["away_pts"])
            m = max(-MARGIN_CAP, min(MARGIN_CAP, raw))
            margins[h].append(m)
            margins[a].append(-m)
            wins[h if raw > 0 else a] += 1
            last_dates[h].append(day)
            last_dates[a].append(day)
            road[h] = 0
            road[a] += 1
            season_games.append((h, a, m))
            exp = roster.get((s, h), 0.0) - roster.get((s, a), 0.0) + 2.3
            resid[h].append(m - exp)
            resid[a].append(exp - m)
            # Elo update (538's margin multiplier)
            diff = elo[h] - elo[a] + ELO_HOME
            p = _elo_prob(diff)
            win = 1.0 if raw > 0 else 0.0
            elo_w = diff if raw > 0 else -diff
            mult = math.log(abs(raw) + 1) * 2.2 / (elo_w * 0.001 + 2.2)
            delta = ELO_K * mult * (win - p)
            elo[h] += delta
            elo[a] -= delta
        srs_now = _srs(season_games, teams)

    out.sort(key=lambda x: x[0])
    return [f for _, f in out]


def _day(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    from datetime import date
    return date(y, m, d).toordinal()
