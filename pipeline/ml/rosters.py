"""
Preseason roster ratings for every season, built the way predict.py rates a roster:
last season's WS/48 (shrunk toward 0.060 for small samples) times last season's minutes
per game, for the players on the team this season, filled to 240 minutes with
replacement-level players, in points per game vs. an average team.

Who is "on the team this season" comes from that season's stats page (each player's
first team). That leaks a little: a player who never plays that season is left out.
"""
import csv
from collections import defaultdict
from pathlib import Path

PRIOR_WS48, PRIOR_MP, REPLACEMENT_WS48, MAX_MPG = 0.060, 500, 0.030, 37.0
POINTS_PER_WIN_PCT, RATING_SPREAD = 1 / 0.033, 0.80
ADV = Path("ml/data/advanced")
TEAMS = {"ATL", "BOS", "BRK", "CHO", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM",
         "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"}
OLD_CODES = {"NJN": "BRK", "CHA": "CHO", "CHH": "CHO", "NOH": "NOP", "NOK": "NOP", "PHX": "PHO", "BKN": "BRK"}


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _season_rows(year):
    """Rows of a season's advanced table with a player id, or None if we don't have it."""
    p = ADV / f"NBA_{year}.csv"
    if p.exists():
        return [dict(r, pid=r["player_id"]) for r in _read(p)]
    local = {2026: Path("data/advanced_2025_26.csv"), 2027: Path("data/advanced_2026_27.csv")}.get(year)
    if local and local.exists():
        return [dict(r, pid=r.get("Player-additional") or r["Player"]) for r in _read(local)]
    return None


def roster_ratings(seasons):
    """{(season, team): rating} for each season whose stats and last season's stats exist."""
    out = {}
    for s in seasons:
        now, last = _season_rows(s), _season_rows(s - 1)
        if not now or not last:
            continue
        prev = {}
        for r in last:   # first row per player is the season total (TOT/2TM) for traded players
            prev.setdefault(r["pid"], r)
        team_of = {}
        for r in now:
            t = OLD_CODES.get(r["Team"], r["Team"])
            if t not in TEAMS:      # TOT/2TM season totals and repeated header rows
                continue
            team_of.setdefault(r["pid"], t)   # first team they played for this season
        rosters = defaultdict(list)
        for pid, t in team_of.items():
            a = prev.get(pid)
            mp, ws, g = (_num(a["MP"]), _num(a["WS"]), _num(a["G"])) if a else (0, 0, 0)
            ws48 = (ws * 48 + PRIOR_WS48 * PRIOR_MP) / (mp + PRIOR_MP)
            mpg = min(mp / g, MAX_MPG) if g else 0.0
            rosters[t].append((ws48, mpg))
        ratings = {}
        for t, pool in rosters.items():
            pool.sort(key=lambda x: -x[1])
            minutes = wsg = 0.0
            for ws48, mpg in pool:
                m = min(mpg, 240 - minutes)
                if m <= 0:
                    break
                minutes += m
                wsg += ws48 * m / 48
            wsg += REPLACEMENT_WS48 * (240 - minutes) / 48
            ratings[t] = (wsg - 0.5) * POINTS_PER_WIN_PCT
        mean = sum(ratings.values()) / len(ratings)
        for t, v in ratings.items():
            out[(s, t)] = (v - mean) * RATING_SPREAD
    return out
