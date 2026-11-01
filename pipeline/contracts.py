"""
Weekly contracts pull: python contracts.py

One page load: Basketball Reference's player contracts table, written to
data/contracts.csv in the same columns the Mac's refresh.py --contracts wrote.
Keeps the old file if the page looks wrong.
"""
import csv
import sys
from pathlib import Path

import bref

URL = "https://www.basketball-reference.com/contracts/players.html"
OUT = Path(__file__).parent / "data" / "contracts.csv"
YEARS = ["2026-27", "2027-28", "2028-29", "2029-30", "2030-31", "2031-32"]
MIN_ROWS = 300   # the table has about 460 contracts


def option_years(row: dict) -> str:
    """BBRef colors option seasons: salary-pl = player option, salary-tm = team option."""
    kinds = {"salary-pl": "PO", "salary-tm": "TO", "salary-et": "ETO"}
    return ";".join(f"{year}:{kind}" for i, year in enumerate(YEARS, start=1)
                    for css, kind in kinds.items() if css in row.get(f"y{i}__class", ""))


def main():
    rows = [r for r in bref.read_table(bref.fetch(URL), "player-contracts")
            if r.get("player") or r.get("name_display")]
    if len(rows) < MIN_ROWS:
        sys.exit(f"contracts.py: only {len(rows)} contracts on {URL}; keeping the old file")
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Rk", "Player", "Tm"] + YEARS + ["Guaranteed", "-9999", "Options"])
        for r in rows:
            w.writerow([r.get("ranker", ""), r.get("player") or r.get("name_display"),
                        r.get("team_id") or r.get("team_name_abbr", "")]
                       + [r.get(f"y{i}", "") for i in range(1, len(YEARS) + 1)]
                       + [r.get("remain_gtd", ""), r.get("player_id", ""), option_years(r)])
    print(f"contracts.py: {len(rows)} contracts -> {OUT.name}")


if __name__ == "__main__":
    main()
