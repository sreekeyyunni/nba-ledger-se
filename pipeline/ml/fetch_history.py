"""
One-time download of past NBA results for the ML backtest: python ml/fetch_history.py

Reads Basketball Reference's season schedule pages (one page per month, about 9 a
season, 6 seconds apart) for 2015-16 through 2025-26 and writes
ml/data/games_history.csv. Seasons already in the file are skipped, so re-running
only fetches what is missing. Run from pipeline/.
"""
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bref  # noqa: E402
from predict import TEAMS  # noqa: E402

OUT = Path("ml/data/games_history.csv")
FIRST, LAST = 2016, 2026          # season end years
OLD_NAMES = {"New Jersey Nets": "BRK", "Charlotte Bobcats": "CHO", "New Orleans Hornets": "NOP"}
HEADER = ["season", "date", "away", "away_pts", "home", "home_pts", "ot", "playoffs"]


def team(name):
    return TEAMS.get(name) or OLD_NAMES[name]


def season_rows(year):
    base = f"https://www.basketball-reference.com/leagues/NBA_{year}_games.html"
    html = bref.fetch(base)
    months = list(dict.fromkeys(re.findall(rf'/leagues/NBA_{year}_games-([a-z0-9-]+)\.html', html)))
    pages = {months[0]: html} if months else {"": html}
    rows = []
    for m in months:
        if m not in pages:
            time.sleep(2)
            pages[m] = bref.fetch(f"https://www.basketball-reference.com/leagues/NBA_{year}_games-{m}.html")
        for r in bref.read_table(pages[m], "schedule"):
            if not r.get("home_pts"):
                continue
            d = datetime.strptime(r["date_game"], "%a, %b %d, %Y").date()
            rows.append([year, d.isoformat(), team(r["visitor_team_name"]), r["visitor_pts"],
                         team(r["home_team_name"]), r["home_pts"], r.get("overtimes", ""), ""])
    # Mark playoff games: everything from the first date on BBRef's playoff schedule page.
    po = bref.fetch(f"https://www.basketball-reference.com/playoffs/NBA_{year}_games.html")
    po_dates = {datetime.strptime(r["date_game"], "%a, %b %d, %Y").date().isoformat()
                for r in bref.read_table(po, "schedule") if r.get("date_game")}
    start = min(po_dates) if po_dates else "9999"
    for r in rows:
        r[7] = "1" if r[1] >= start else ""
    print(f"  {year}: {len(rows)} games, {sum(r[7] == '1' for r in rows)} playoff")
    return rows


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    have = []
    if OUT.exists():
        with open(OUT, newline="") as f:
            have = list(csv.reader(f))[1:]
    done = {int(r[0]) for r in have}
    for year in range(FIRST, LAST + 1):
        if year in done:
            continue
        try:
            have += season_rows(year)
        except Exception as e:  # keep what we have; the next run picks up the rest
            print(f"  {year}: failed ({e})")
            break
        with open(OUT, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(sorted(have, key=lambda r: (r[1], r[4])))
    print(f"wrote {len(have)} games to {OUT}")


if __name__ == "__main__":
    main()
