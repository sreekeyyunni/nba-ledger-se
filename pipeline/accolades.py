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
    rows, cur = [], None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if not cells:
            continue
        if re.fullmatch(r"\d{4}-\d{2}", cells[0]):
            cur = cells[0]
        team = next((i for i, c in enumerate(cells) if c in ("1st", "2nd", "3rd")), None)
        if cur not in want or team is None or "NBA" not in cells[:team]:
            continue
        for c in cells[team + 1:]:
            name = re.sub(r"\s+[CFG](-[CFG])?$", "", c).strip()
            if name and not re.fullmatch(r"[\d.\s-]*", name):
                rows.append([name, cur, f"All-NBA {cells[team]}"])
    if not any(r[1] == season(last) for r in rows):
        i = html.find(">" + season(last) + "<")
        sample = html[max(0, i - 200):i + 600] if i >= 0 else ""
        seasons = sorted(set(re.findall(r">(\d{4}-\d{2})<", html)))[-3:]
        raise SystemExit(f"::warning::accolades: no {season(last)} All-NBA rows found in {len(html)} bytes "
                         f"(latest seasons on page: {seasons}; sample row: {re.sub(r"\\s+", " ", sample)[:400]}); keeping {OUT}")
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Player", "season", "honor"])
        w.writerows(sorted(rows, key=lambda r: (r[1], r[2])))
    print(f"::notice::accolades: wrote {len(rows)} All-NBA players to {OUT}")


if __name__ == "__main__":
    main()
