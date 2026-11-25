"""
One-time download of past seasons' player stats for the ML backtest: python ml/fetch_rosters.py

Reads Basketball Reference's league advanced-stats page once per season (2015-16
through 2025-26, 11 pages, 6 seconds apart) and keeps Player, id, Team, G, MP and WS in
ml/data/advanced/NBA_<year>.csv. Seasons already saved are skipped. Run from pipeline/.

The backtest uses these to rate each team's roster before a season the way the live
formula does: last season's WS/48 times last season's minutes for the players on the
team this season.
"""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bref  # noqa: E402

OUT = Path("ml/data/advanced")
FIRST, LAST = 2016, 2026
URL = "https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html"
COLUMNS = {"Player": ["name_display", "player"], "player_id": ["player_id"],
           "Team": ["team_name_abbr", "team_id"], "G": ["games", "g"], "MP": ["mp"], "WS": ["ws"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for year in range(FIRST, LAST + 1):
        path = OUT / f"NBA_{year}.csv"
        if path.exists():
            continue
        try:
            rows = bref.read_table(bref.fetch(URL.format(year=year)), "advanced")
        except Exception as e:   # keep what we have; the next run picks up the rest
            print(f"  {year}: failed ({e})")
            break
        out = []
        for r in rows:
            rec = {c: next((r[n] for n in names if n in r), "") for c, names in COLUMNS.items()}
            if rec["Player"] and rec["Player"] != "League Average" and rec["Team"]:
                out.append(rec)
        if len(out) < 300:
            print(f"  {year}: only {len(out)} rows; page changed? stopping")
            break
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(COLUMNS), lineterminator="\n")
            w.writeheader()
            w.writerows(out)
        print(f"  {year}: {len(out)} rows")
        time.sleep(2)


if __name__ == "__main__":
    main()
