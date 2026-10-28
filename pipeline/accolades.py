"""
All-NBA teams for star credit: python accolades.py [data dir]

One polite request to Basketball Reference's All-League page, keeping the last two
finished seasons in data/accolades.csv (Player, season, honor). Skips the request when
the file already has the latest finished season.
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

import bref

URL = "https://www.basketball-reference.com/awards/all_league.html"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "../data") / "accolades.csv"


def season(end_year):
    return f"{end_year - 1}-{str(end_year)[2:]}"


def main():
    today = date.today()
    last = today.year if today.month >= 6 else today.year - 1      # All-NBA is out by June
    want = {season(last), season(last - 1)}
    have = list(csv.DictReader(open(OUT))) if OUT.exists() else []
    if season(last) in {r["season"] for r in have}:
        print(f"  accolades: {season(last)} already in {OUT}")
        return
    try:
        html = bref.fetch(URL)
    except Exception as e:                                             # shows as a warning on the Actions run
        raise SystemExit(f"::warning::accolades: Basketball Reference request failed: {e}")
    html = html.replace("<!--", "").replace("-->", "")                 # tables can sit inside comments
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        s = re.search(r">(\d{4}-\d{2})<", tr)
        team = re.search(r">(1st|2nd|3rd)<", tr)
        if not (s and team and s.group(1) in want) or ">NBA<" not in tr:
            continue
        for name in re.findall(r'href="/players/[^"]+">([^<]+)</a>', tr):
            rows.append([name.strip(), s.group(1), f"All-NBA {team.group(1)}"])
    if not any(r[1] == season(last) for r in rows):
        seasons = sorted(set(re.findall(r">(\d{4}-\d{2})<", html)))[-3:]
        raise SystemExit(f"::warning::accolades: no {season(last)} All-NBA rows found in {len(html)} bytes "
                         f"(latest seasons on page: {seasons}); keeping {OUT}")
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Player", "season", "honor"])
        w.writerows(sorted(rows, key=lambda r: (r[1], r[2])))
    print(f"::notice::accolades: wrote {len(rows)} All-NBA players to {OUT}")


if __name__ == "__main__":
    main()
