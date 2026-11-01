"""
Refresh the data and re-run the valuation.

  python refresh.py              stats only (what the Monday job runs)
  python refresh.py --contracts  also re-pull the contracts table

Stats come from NBA.com through nba_api (three requests, see nba_stats.py;
team play styles are about 30 more, see team_styles.py),
with Win Shares computed the Basketball Reference way, and are written to
data/advanced_2026_27.csv in the same columns as before. BPM and VORP aren't
available there and are left blank (nothing downstream reads them for
2026-27). Positions and BBRef ids carry over from earlier files by name.
Last season's file (data/advanced_2025_26.csv) is final and kept as is.

Contracts come from Basketball Reference's contracts page, only with
--contracts. Spotrac blocks scripted requests, so data/spotrac_cash_2026_27.csv
is captured by hand; the script warns when that snapshot is getting old.
"""
import csv
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd

import bref
import nba_stats

CURRENT_SEASON, CURRENT_FILE = "2026-27", "data/advanced_2026_27.csv"
LAST_SEASON_FILE = "data/advanced_2025_26.csv"
CONTRACTS_URL = "https://www.basketball-reference.com/contracts/players.html"
SPOTRAC_FILE = Path("data/spotrac_cash_2026_27.csv")
SPOTRAC_MAX_AGE_DAYS = 14

ADVANCED_HEADER = ["Player", "Age", "Team", "Pos", "G", "MP", "WS", "WS/48", "BPM", "VORP",
                   "Player-additional"]
CONTRACT_YEARS = ["2026-27", "2027-28", "2028-29", "2029-30", "2030-31", "2031-32"]


def write_csv(path: str, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  wrote {len(rows)} rows to {path}")


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name.lower().replace(".", "").replace("'", ""))
    return re.sub(r"\s+", " ", name).strip()


def known_players() -> dict:
    """Position and BBRef id by player, from the files we already have."""
    known = {}
    for path in (LAST_SEASON_FILE, CURRENT_FILE):   # current file wins
        if Path(path).exists():
            old = pd.read_csv(path).dropna(subset=["Player"])
            for row in old.to_dict("records"):
                known[normalize(row["Player"])] = (row.get("Pos", ""), row.get("Player-additional", ""))
    return known


def refresh_current_stats() -> None:
    known = known_players()
    players, teams = nba_stats.fetch_season(CURRENT_SEASON)
    if Path(CURRENT_FILE).exists() and players["MIN"].sum() < pd.read_csv(CURRENT_FILE)["MP"].sum() * 0.99:
        print("  NBA.com returned fewer total minutes than the file we have (stale data); keeping the old file")
        return
    ws = nba_stats.win_shares(players, teams)
    rows = []
    for r in ws.sort_values("MIN", ascending=False).itertuples():
        pos, bref_id = known.get(normalize(r.PLAYER_NAME), ("", ""))
        ws48 = r.WS / r.MIN * 48 if r.MIN else 0
        rows.append([r.PLAYER_NAME, int(r.AGE), r.TEAM_ABBREVIATION, "" if pd.isna(pos) else pos,
                     int(r.GP), round(r.MIN), round(r.WS, 1), f"{ws48:.3f}", "", "",
                     "" if pd.isna(bref_id) else bref_id])
    write_csv(CURRENT_FILE, ADVANCED_HEADER, rows)


def refresh_contracts() -> None:
    rows = bref.read_table(bref.fetch(CONTRACTS_URL), "player-contracts")
    header = ["Rk", "Player", "Tm"] + CONTRACT_YEARS + ["Guaranteed", "-9999", "Options"]
    write_csv("data/contracts.csv", header,
              [[r.get("ranker", ""), r.get("player", ""), r.get("team_id", "")]
               + [r.get(f"y{i}", "") for i in range(1, len(CONTRACT_YEARS) + 1)]
               + [r.get("remain_gtd", ""), r.get("player_id", ""), option_years(r)] for r in rows])


def option_years(row: dict) -> str:
    """BBRef colors option seasons: salary-pl = player option, salary-tm = team option."""
    kinds = {"salary-pl": "PO", "salary-tm": "TO", "salary-et": "ETO"}
    return ";".join(f"{year}:{kind}" for i, year in enumerate(CONTRACT_YEARS, start=1)
                    for css, kind in kinds.items() if css in row.get(f"y{i}__class", ""))


def main() -> None:
    Path("data").mkdir(exist_ok=True)
    print("Refreshing NBA.com stats (nba_api)...")
    refresh_current_stats()
    print("Refreshing team play styles (nba_api)...")
    subprocess.run([sys.executable, "team_styles.py"], check=False)   # optional; failures don't stop the refresh
    if "--contracts" in sys.argv:
        print("Refreshing contracts (Basketball Reference)...")
        refresh_contracts()
    Path("data/drafts").mkdir(exist_ok=True)
    for year in range(2023, 2027):   # draft pages never change; fetch once
        page = Path(f"data/drafts/NBA_{year}.html")
        if not page.exists():
            page.write_text(bref.fetch(f"https://www.basketball-reference.com/draft/NBA_{year}.html"),
                            encoding="utf-8")

    if SPOTRAC_FILE.exists():
        age = (time.time() - SPOTRAC_FILE.stat().st_mtime) / 86400
        if age > SPOTRAC_MAX_AGE_DAYS:
            print(f"Note: Spotrac snapshot is {age:.0f} days old; ask Claude to update it.")

    print("Running contract_value.py...\n")
    subprocess.run([sys.executable, "contract_value.py"], check=True)
    print("\nRunning trade_value.py...\n")
    subprocess.run([sys.executable, "trade_value.py"], check=True)
    print("\nRunning draft_picks.py...\n")
    subprocess.run([sys.executable, "draft_picks.py"], check=True)
    print("\nRefreshing player play styles (nba_api)...")
    subprocess.run([sys.executable, "player_styles.py"], check=False)   # optional; needs contract_value.csv
    print("\nRefreshing transactions (NBA.com + ESPN)...")
    subprocess.run([sys.executable, "transactions.py"], check=False)   # optional


if __name__ == "__main__":
    main()
