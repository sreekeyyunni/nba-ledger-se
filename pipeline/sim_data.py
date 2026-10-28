"""
Season simulator data: python sim_data.py

Writes outputs/sim_data.json, everything the browser simulator (sim.js) needs
to play out the rest of the 2026-27 season:

- teams: conference, record so far, "form" (from outputs/team_power.csv, so run
  predict.py first) and the roster rating for the rest of the season
- players: name, team, WS/48, minutes per game and rest-of-season availability,
  so a trade can re-rate both teams the same way predict.py does
- games: every unplayed game with back-to-back flags

Ratings are predict.py's: WS/48 x projected minutes filled to 240 with
replacement players, centred on the league and pulled 20% toward average.
Injuries count for the rest of the season only when they are long: season-ending
news takes a player out, a reported timeline ("out two months") costs him those
games (injury.py), a plain "out" costs him 15% of his games, day-to-day nothing.

The predictor only keeps about a week of schedule; the first run downloads the
whole season from Basketball Reference (7 pages, ~30 s) into the predictor's
schedule file, and predict.py keeps it up to date from then on.
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import predict as P
from injury import games_out

EAST = {"ATL", "BOS", "BRK", "CHO", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS"}
SEASON_START, SEASON_END = "2026-07-01", "2027-04-01"   # news before July is last season's
SEASON_OVER = re.compile(r"(remainder|rest) of the (\d{4}-\d{2} )?(regular )?season|miss the (entire )?(\d{4}-\d{2} )?season"
                         r"|out for the season|season-ending")
OUT_SHARE = 0.85        # a plain "out" plays 85% of what's left
TEAM_SD = 2.0           # how far off a team's rating can be, in points (sim.js draws it per season)
OUT = Path("outputs/sim_data.json")

# BBRef and NBA.com spell some names differently; without this a player shows up twice
ALIASES = {"ronald holland": "ron holland"}
_key = P.key
P.key = lambda name: ALIASES.get(_key(name), _key(name))


def season_availability(note, updated):
    n = note.lower()
    if updated and updated < SEASON_START:
        return 1.0                      # stale entry from last season
    if SEASON_OVER.search(n):
        return 0.0
    if n.startswith("out"):
        return OUT_SHARE
    return 1.0


def main():
    games = P.read_csv(P.SCHEDULE_FILE)
    if max(g["date"] for g in games) < SEASON_END:
        print("Downloading the full season schedule from Basketball Reference...")
        live = {(g["date"], g["away"], g["home"]): g for g in games}
        P.fetch_schedule(date(2027, 7, 1))
        games = P.read_csv(P.SCHEDULE_FILE)
        # keep scores ESPN filled in that BBRef doesn't have yet
        for g in games:
            old = live.get((g["date"], g["away"], g["home"]))
            if old and g["home_pts"] == "" and old["home_pts"] != "":
                g["away_pts"], g["home_pts"], g["ot"] = old["away_pts"], old["home_pts"], old.get("ot", "")
        P.write_csv(P.SCHEDULE_FILE, ["date", "time_et", "away", "away_pts", "home", "home_pts", "ot", "live"],
                    [[g["date"], g["time_et"], g["away"], g["away_pts"], g["home"], g["home_pts"], g.get("ot", ""),
                      g.get("live", "")] for g in games])

    players = P.load_players()

    rosters = {t: [p for p in players if p["team"] == t] for t in P.TEAMS.values()}
    healthy_raw = {t: P.team_rating(rosters[t]) for t in rosters}
    mean_raw = sum(healthy_raw.values()) / len(healthy_raw)   # same centre predict.py uses
    form = {r["team"]: float(r["form"]) for r in P.read_csv("outputs/team_power.csv")}

    record = {t: [0, 0] for t in P.TEAMS.values()}
    played = {}
    for g in games:
        for t in (g["away"], g["home"]):
            played.setdefault(t, set()).add(g["date"])
        if g["home_pts"] != "" and g["away_pts"] != "":
            hw = float(g["home_pts"]) > float(g["away_pts"])
            record[g["home"]][0 if hw else 1] += 1
            record[g["away"]][1 if hw else 0] += 1

    left = []
    for g in sorted(games, key=lambda g: (g["date"], g["time_et"])):
        if g["home_pts"] != "" and g["away_pts"] != "":
            continue
        prev = (date.fromisoformat(g["date"]) - timedelta(days=1)).isoformat()
        left.append([g["date"], g["away"], g["home"], int(prev in played[g["away"]]), int(prev in played[g["home"]])])

    # a reported timeline ("out two months") becomes the share of his team's games left that he misses
    games_left = {}
    for g in left:
        for t in (g[1], g[2]):
            games_left[t] = games_left.get(t, 0) + 1
    team_of = {p["player"]: p["team"] for p in players}
    avail = {}
    for r in P.read_csv(P.INJURY_FILE) if P.INJURY_FILE.exists() else []:
        k = P.key(r["player"])
        n_left = games_left.get(team_of.get(k), 0)
        out = games_out(r["note"], r.get("updated", ""), date.today(), n_left) if n_left else None
        a = season_availability(r["note"], r.get("updated", "")) if out is None or r.get("updated", "") < SEASON_START \
            else 1 - out / n_left
        if a < 1:
            avail[k] = min(avail.get(k, 1.0), round(a, 3))

    teams = {}
    for t in sorted(P.TEAMS.values()):
        rated = P.team_rating(rosters[t], avail)
        teams[t] = {"conf": "E" if t in EAST else "W", "w": record[t][0], "l": record[t][1],
                    "form": form.get(t, 0.0),
                    "roster": round((rated - mean_raw) * P.RATING_SPREAD, 2)}

    data = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "params": {"mean_raw": round(mean_raw, 4), "spread": P.RATING_SPREAD, "home_court": P.HOME_COURT,
                   "back_to_back": P.BACK_TO_BACK, "margin_sd": P.MARGIN_SD, "team_sd": TEAM_SD,
                   "replacement_ws48": P.REPLACEMENT_WS48, "points_per_win_pct": P.POINTS_PER_WIN_PCT},
        "teams": teams,
        "players": [[p["name"], p["team"], round(p["ws48"], 4), round(p["mpg"], 1), avail.get(p["player"], 1.0)]
                    for p in sorted(players, key=lambda p: (p["team"], -p["mpg"]))],
        "games": left,
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"  wrote {OUT}: {len(players)} players, {len(left)} games left")


if __name__ == "__main__":
    main()
