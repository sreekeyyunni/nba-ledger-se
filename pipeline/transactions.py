"""
League transactions since July 1, 2026: python transactions.py (refresh.py
also runs it). Writes outputs/transactions.csv, newest first.

Sources, one polite request each:
- NBA.com's player movement feed (the main source; trades share a group id)
- ESPN's transactions API, newest MAX_ESPN_PAGES pages, to add anything NBA.com
  doesn't list yet (matched on team, player surname and a date within two days)

Columns: id, date, type, team (BBRef code), player (as named in
contract_value.csv / contracts_clean.csv when matched, else NBA.com's name),
description, group_id, source, years, total_m.
type is one of trade, signing, extension, waive, two_way, conversion, claim, other.
years / total_m are filled only when the text gives contract terms.
"""
import hashlib
import re
import time
import unicodedata

import pandas as pd
import requests
from nba_api.stats.library.http import STATS_HEADERS
from nba_api.stats.static import players as nba_players
from nba_api.stats.static import teams as nba_teams

SINCE = "2026-07-01"
NBA_URL = "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/transactions"
MAX_ESPN_PAGES = 3
PAUSE_SECONDS = 1
TIMEOUT = 30
TO_BREF = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
ESPN_TO_BREF = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS",
                "PHX": "PHO", "BKN": "BRK", "CHA": "CHO"}
TEAM_BY_ID = {t["id"]: TO_BREF.get(t["abbreviation"], t["abbreviation"]) for t in nba_teams.get_teams()}
NAME_BY_ID = {p["id"]: p["full_name"] for p in nba_players.get_players()}
VERBS = r"\b(?:Signed|Re-signed|Waived|Claimed|Converted|Traded|Acquired|Released|Exercised|Declined|Assigned|Recalled|Activated|Placed|Extended)\b"
POSITIONS = r"(?<![\w'])(?:G|F|C|Gs|Fs|Cs|G-F|F-G|F-C|C-F|guard|forward|center)\.?(?![\w'])"


def espn_names(text: str) -> list[str]:
    """Player names in an ESPN description, e.g. 'Waived Gs Bruce Brown and Dink Pate.'"""
    text = re.sub(VERBS, "|", text)
    text = re.sub(POSITIONS, "|", text)
    names = []
    for chunk in re.split(r"\||,|\band\b|\bto\b|\bfrom\b|\bon\b|\bwith\b", text):
        found = re.findall(r"[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)+", chunk)
        names += [re.sub(r"('s|\.)+$", "", n).strip() for n in found]
    return [n for n in names if len(n.split()) >= 2]


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name.lower().replace(".", "").replace("'", "").replace("-", " "))
    return re.sub(r"\s+", " ", name).strip()


def get(url: str, **kwargs) -> dict:
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=TIMEOUT, **kwargs)
            response.raise_for_status()
            time.sleep(PAUSE_SECONDS)
            return response.json()
        except Exception:
            if attempt:
                raise
            time.sleep(PAUSE_SECONDS * 3)


def classify(kind: str, text: str) -> str:
    t = text.lower()
    if kind == "Trade" or "traded" in t or "acquired" in t:
        return "trade"
    if kind == "ContractConverted" or "convert" in t:
        return "conversion"
    if kind == "AwardOnWaivers" or "claimed" in t:
        return "claim"
    if kind == "Waive" or "waived" in t or "released" in t:
        return "waive"
    if "two-way" in t:
        return "two_way"
    if "extension" in t or "extended" in t:
        return "extension"
    if kind == "Signing" or "signed" in t or "re-signed" in t:
        return "signing"
    return "other"


def contract_terms(text: str) -> tuple[float | None, float | None]:
    years = re.search(r"(\d+)[- ]year", text, re.I)
    money = re.search(r"\$\s?(\d+(?:\.\d+)?)\s?(million|M\b)", text, re.I)
    return (int(years[1]) if years else None, float(money[1]) if money else None)


def main() -> None:
    known = pd.concat([pd.read_csv("outputs/contract_value.csv")["Player"],
                       pd.read_csv("outputs/contracts_clean.csv")["Player"]]).drop_duplicates()
    by_key = dict(zip(known.map(normalize), known))

    feed = get(NBA_URL, headers=STATS_HEADERS)["NBA_Player_Movement"]["rows"]
    rows = []
    for i, r in enumerate(feed):
        day = r["TRANSACTION_DATE"][:10]
        if day < SINCE:
            continue
        text = r["TRANSACTION_DESCRIPTION"]
        slug = r.get("PLAYER_SLUG") or ""
        player_id = int(r["PLAYER_ID"] or 0)
        fallback = NAME_BY_ID.get(player_id) or slug.replace("-", " ").title()
        player = by_key.get(normalize(slug)) or (fallback if slug else "")
        group = r["GroupSort"]
        years, total = contract_terms(text)
        rows.append({"id": f"nba-{group.split()[-1]}-{player_id}-{int(r['Additional_Sort'] or 0)}",
                     "date": day, "type": classify(r["Transaction_Type"], text),
                     "team": TEAM_BY_ID.get(int(r["TEAM_ID"] or 0), ""), "player": player,
                     "description": text, "group_id": group.split()[-1] if r["Transaction_Type"] == "Trade" else "",
                     "source": "nba", "years": years, "total_m": total, "matched": normalize(slug) in by_key})
    nba = pd.DataFrame(rows)

    espn_rows = []
    for page in range(1, MAX_ESPN_PAGES + 1):
        data = get(ESPN_URL, params={"page": page})
        for t in data.get("transactions", []):
            day, text = t["date"][:10], t["description"]
            if day < SINCE:
                continue
            team = ESPN_TO_BREF.get(t["team"]["abbreviation"], t["team"]["abbreviation"])
            names = espn_names(text)
            name = names[0] if len(names) == 1 else ""
            years, total = contract_terms(text)
            espn_rows.append({"id": "espn-" + hashlib.sha1(f"{day}|{team}|{text}".encode()).hexdigest()[:12],
                              "date": day, "type": classify("", text), "team": team,
                              "player": by_key.get(normalize(name), name), "description": text, "group_id": "",
                              "source": "espn", "years": years, "total_m": total,
                              "matched": normalize(name) in by_key, "names": names})
        if page >= data.get("pageCount", 1):
            break
    espn = pd.DataFrame(espn_rows)

    # Keep ESPN rows only when NBA.com has nothing for that team and surname within 2 days
    def covered(row) -> bool:
        surnames = [normalize(n).split()[-1] for n in row["names"] if normalize(n)]
        if nba.empty or not surnames:
            return False
        near = nba[(nba["team"] == row["team"])
                   & ((pd.to_datetime(nba["date"]) - pd.to_datetime(row["date"])).abs().dt.days <= 2)]
        text = " ".join(near["description"].map(normalize))
        return any(s in text for s in surnames)

    extra = espn[~espn.apply(covered, axis=1)] if not espn.empty else espn
    out = pd.concat([nba, extra.drop(columns="names", errors="ignore")], ignore_index=True)
    out = out.sort_values(["date", "id"], ascending=[False, True])
    repeat = out.groupby("id").cumcount()
    out["id"] = out["id"].where(repeat == 0, out["id"] + "-" + repeat.astype(str))
    matched = out.pop("matched")
    out.to_csv("outputs/transactions.csv", index=False)

    print(f"Saved outputs/transactions.csv: {len(out)} rows since {SINCE} "
          f"({len(nba)} NBA.com, {len(extra)} added from ESPN of {len(espn)} checked)")
    print("By type: " + ", ".join(f"{k} {v}" for k, v in out["type"].value_counts().items()))
    with_player = out["player"].ne("")
    print(f"Players matched to contract_value.csv names: {int(matched[with_player].sum())} of "
          f"{int(with_player.sum())} rows with a player")


if __name__ == "__main__":
    main()
