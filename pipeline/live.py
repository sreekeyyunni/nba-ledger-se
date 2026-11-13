"""
Trade values that move with each night's games: python live.py [data dir]

For every finished game in the last 7 days this reads ESPN's public box score and
gives each player a game score (points, rebounds, assists and so on, minus misses and
turnovers). A player's week is compared with his own norm over the last three weeks:
every game-score point above or below it moves his trade value by $0.25M, capped at
$10M either way. The Monday refresh re-prices everyone from full-season stats, so this
is only the nudge between refreshes.

Box scores are kept in pipeline/data/game_lines.csv (three weeks), so each run asks
ESPN only for games it hasn't seen: about ten small requests a run.
Writes data/live_values.csv.
"""
import csv
import json
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import bref

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else "../data")
LINES = Path(__file__).parent / "data" / "game_lines.csv"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={ymd}"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={id}"
CODES = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO", "GS": "GSW", "NY": "NYK", "NO": "NOP",
         "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
KEEP_DAYS, WEEK_DAYS, MIN_GAMES = 21, 7, 4
PER_POINT_M, CAP_M = 0.25, 10.0
COLS = ["date", "event", "player", "team", "opp", "min", "pts", "reb", "ast", "gmsc"]


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ").replace(" jr", "").replace(" sr", "").replace(" iii", "").replace(" ii", "").strip()


def pair(x):
    """'10-18' -> (10, 18)"""
    a, _, b = str(x).partition("-")
    return num(a), num(b)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def box_lines(summary, day, event):
    """One row per player who played, from ESPN's summary JSON."""
    teams = summary.get("boxscore", {}).get("players", [])
    abbrs = [CODES.get(t["team"]["abbreviation"], t["team"]["abbreviation"]) for t in teams]
    rows = []
    for i, t in enumerate(teams):
        for block in t.get("statistics", []):
            labels = [str(x).upper() for x in (block.get("labels") or block.get("names") or [])]
            for a in block.get("athletes", []):
                st = dict(zip(labels, a.get("stats") or []))
                mins = num(st.get("MIN"))
                if a.get("didNotPlay") or not st or mins <= 0:
                    continue
                fg, fga = pair(st.get("FG"))
                ft, fta = pair(st.get("FT"))
                pts, orb, drb = num(st.get("PTS")), num(st.get("OREB")), num(st.get("DREB"))
                reb = num(st.get("REB")) or orb + drb
                if "OREB" not in st:            # split unknown: use the usual 1-in-4 share
                    orb, drb = reb * 0.25, reb * 0.75
                gmsc = (pts + 0.4 * fg - 0.7 * fga - 0.4 * (fta - ft) + 0.7 * orb + 0.3 * drb
                        + num(st.get("STL")) + 0.7 * num(st.get("AST")) + 0.7 * num(st.get("BLK"))
                        - 0.4 * num(st.get("PF")) - num(st.get("TO")))
                rows.append({"date": day, "event": event, "player": a["athlete"]["displayName"],
                             "team": abbrs[i], "opp": abbrs[1 - i] if len(abbrs) == 2 else "",
                             "min": f"{mins:.0f}", "pts": f"{pts:.0f}", "reb": f"{reb:.0f}",
                             "ast": f'{num(st.get("AST")):.0f}', "gmsc": f"{gmsc:.1f}"})
    return rows


def values(lines, names, today):
    """Rows for live_values.csv from the stored box scores."""
    week = (today - timedelta(days=WEEK_DAYS)).isoformat()
    by = {}
    for r in lines:
        by.setdefault(norm(r["player"]), []).append(r)
    out = []
    for key, games in by.items():
        if key not in names:
            continue
        games.sort(key=lambda r: r["date"])
        recent = [g for g in games if g["date"] >= week]
        if len(games) < MIN_GAMES or not recent:
            continue
        base = sum(num(g["gmsc"]) for g in games) / len(games)
        delta = sum(num(g["gmsc"]) - base for g in recent) * PER_POINT_M
        delta = max(-CAP_M, min(CAP_M, delta))
        last = recent[-1]
        player, team = names[key]
        out.append({"Player": player, "Team": team, "week_m": f"{delta:.2f}", "games": len(recent),
                    "norm_gmsc": f"{base:.1f}", "last_date": last["date"], "last_gmsc": last["gmsc"],
                    "last_line": f'{last["pts"]} pts, {last["reb"]} reb, {last["ast"]} ast vs {last["opp"]}'})
    return sorted(out, key=lambda r: -num(r["week_m"]))


def main(today=None, fetch=bref.fetch):
    today = today or date.today()
    lines = list(csv.DictReader(open(LINES))) if LINES.exists() else []
    oldest = (today - timedelta(days=KEEP_DAYS)).isoformat()
    lines = [r for r in lines if r["date"] >= oldest]
    seen = {r["event"] for r in lines}
    # first run fills the three weeks; later runs only look back a week for games they missed
    back = KEEP_DAYS if not lines else WEEK_DAYS
    new = 0
    for n in range(back, -1, -1):
        d = today - timedelta(days=n)
        try:
            events = json.loads(fetch(SCOREBOARD.format(ymd=d.strftime("%Y%m%d")))).get("events", [])
        except Exception as e:
            print(f"::warning::live.py: no scoreboard for {d} ({e})")
            continue
        for ev in events:
            if ev["id"] in seen or not ev.get("status", {}).get("type", {}).get("completed"):
                continue
            try:
                rows = box_lines(json.loads(fetch(SUMMARY.format(id=ev["id"]))), d.isoformat(), ev["id"])
            except Exception as e:
                print(f"::warning::live.py: no box score for game {ev['id']} ({e})")
                continue
            lines += rows
            seen.add(ev["id"])
            new += 1
    LINES.parent.mkdir(parents=True, exist_ok=True)
    with open(LINES, "w", newline="") as f:
        w = csv.DictWriter(f, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(lines, key=lambda r: (r["date"], r["event"], r["team"], r["player"])))

    names = {norm(r["Player"]): (r["Player"], r["Team"]) for r in csv.DictReader(open(DATA / "trade_values.csv"))}
    out = values(lines, names, today)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(DATA / "live_values.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["Player", "Team", "week_m", "games", "norm_gmsc", "last_date", "last_gmsc", "last_line", "updated"], lineterminator="\n")
        w.writeheader()
        w.writerows({**r, "updated": stamp} for r in out)
    print(f"::notice::live.py: {new} new games, {len(lines)} player lines kept, {len(out)} players with a moving value")


if __name__ == "__main__":
    main()
