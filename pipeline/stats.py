"""
This season's advanced stats from Basketball Reference: python stats.py

Replaces the Mac's nba_api pull (stats.nba.com times out from GitHub's runners).
One page load: the league advanced table. Writes data/advanced_2026_27.csv, which
predict.py and sim_data.py read. Keeps the old file if the page can't be read.
"""
import csv
import sys
from pathlib import Path

import bref

URL = "https://www.basketball-reference.com/leagues/NBA_2027_advanced.html"
OUT = Path(__file__).parent / "data" / "advanced_2026_27.csv"
MIN_ROWS = 100   # fewer than this means the page changed; keep last week's file

# column -> Basketball Reference data-stat names (new site names first, then old ones)
COLUMNS = {
    "Player": ["name_display", "player"], "Age": ["age"], "Team": ["team_name_abbr", "team_id"],
    "Pos": ["pos"], "G": ["games", "g"], "MP": ["mp"], "WS": ["ws"], "WS/48": ["ws_per_48"],
    "BPM": ["bpm"], "VORP": ["vorp"], "Player-additional": ["player_id"],
    # added after the original columns (pages read by name)
    "GS": ["games_started", "gs"], "PER": ["per"], "TS%": ["ts_pct"], "USG%": ["usg_pct"],
    "OWS": ["ows"], "DWS": ["dws"], "OBPM": ["obpm"], "DBPM": ["dbpm"],
}


def pick(row, names):
    return next((row[n] for n in names if n in row), "")


def main():
    rows = bref.read_table(bref.fetch(URL), "advanced")
    out = []
    for r in rows:
        rec = {col: pick(r, names) for col, names in COLUMNS.items()}
        if rec["Player"] and rec["Player"] != "League Average" and rec["Team"]:
            out.append(rec)
    if len(out) < MIN_ROWS:
        sys.exit(f"stats.py: only {len(out)} players on {URL}; keeping the old file")
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"stats.py: {len(out)} rows -> {OUT.name}")


if __name__ == "__main__":
    main()
