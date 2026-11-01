"""
Rebuild the two hand-captured Spotrac inputs from what the site already publishes:
python spotrac_inputs.py

The raw Spotrac captures stay on the Mac (they aren't republished). The numbers
taken from them are already in the site's data, so the cloud refresh reads those:
- data/spotrac_cash_2026_27.csv  <- team_summary.csv (active, dead, retained cash)
                                    and team_cap.csv (total cash = payroll)
- data/picks/spotrac_future_raw.txt <- draft_picks.csv (owner, original team,
                                    rights and the pick description)
A file that already exists (a real capture) is left alone.
"""
import csv
import re
from pathlib import Path

HERE = Path(__file__).parent
SITE = HERE.parent / "data"
CASH = HERE / "data" / "spotrac_cash_2026_27.csv"
PICKS = HERE / "data" / "picks" / "spotrac_future_raw.txt"
FROM_BREF = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_cash():
    payroll = {r["Team"]: float(r["payroll_m"]) for r in rows(SITE / "team_cap.csv")}
    summary = HERE / "data" / "raw" / "team_summary.csv"   # same cash columns, before adjust.py
    with open(CASH, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Team", "Active", "Dead", "Retained", "Total Cash"])
        for r in rows(summary if summary.exists() else SITE / "team_summary.csv"):
            w.writerow([FROM_BREF.get(r["Team"], r["Team"])]
                       + [round(float(r[c]) * 1e6) for c in ("active_m", "dead_m", "retained_m")]
                       + [round(payroll[r["Team"]] * 1e6)])
    print(f"spotrac_inputs.py: rebuilt {CASH.name}")


def build_picks():
    """One canonical line per pick: year|original team|round|C|owners in order|description."""
    picks = {}
    for r in rows(SITE / "draft_picks.csv"):
        if "-SWAP-" in r["pick_id"]:
            continue   # swap rows are derived again from the pick descriptions
        key = (r["year"], r["original_team"], r["round"])
        p = picks.setdefault(key, {"owners": [], "desc": None})
        base = f'{r["year"]}-{FROM_BREF.get(r["original_team"], r["original_team"])}-R{r["round"]}'
        owner = FROM_BREF.get(r["owner"], r["owner"])
        if r["pick_id"] == base:
            p["owners"].insert(0, owner)   # the pick's main holder comes first
        else:
            p["owners"].append(owner)
        desc = re.sub(r" \[pool(; slot limits in pool ignored)?\]$", "", r["notes"])
        p["desc"] = "FORFEIT" if desc == "Forfeited pick (no value)" else desc
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    with open(PICKS, "w", encoding="utf-8") as f:
        f.write("# Rebuilt from data/draft_picks.csv by spotrac_inputs.py\n")
        for (year, orig, rnd), p in picks.items():
            f.write("|".join([year, FROM_BREF.get(orig, orig), rnd, "C", ",".join(p["owners"]), p["desc"]]) + "\n")
    print(f"spotrac_inputs.py: rebuilt {PICKS.name} ({len(picks)} picks)")


if __name__ == "__main__":
    if not CASH.exists():
        build_cash()
    if not PICKS.exists():
        build_picks()
