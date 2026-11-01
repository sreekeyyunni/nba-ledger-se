"""
Player play styles from NBA.com (nba_api). Run by refresh.py after
team_styles.py, or on its own: python player_styles.py

One row per player in outputs/contract_value.csv. Each player uses 2026-27
data, or 2025-26 when he has under MIN_CURRENT_MINUTES this season (the
`season` column says which). About 21 requests per season, one second apart:
Synergy offensive play types (10), shot zones (1), tracking (7), advanced (1),
and player/team/opponent box totals for steal and block percentage (3).

Columns:
- mp, poss: minutes, and Synergy possessions summed over the ten play types
- {type}_freq / _ppp / _poss: share of the player's own possessions, points per
  possession, and possessions, for prbh, prroll, iso, post, trans, spotup, cut,
  handoff, offscreen, putback
- {zone}_fga_share / _fg_pct for ra, paint, mid, corner3, atb3, and fga_pg
- tracking per game: drives, passes, assist points created, catch-and-shoot and
  pull-up FGA and eFG, touches, time of possession (minutes), rebounds, and
  shots defended at the rim with opponents' FG% there
- usg_pct, ast_pct, reb_pct (NBA.com advanced) and stl_pct, blk_pct (computed the
  Basketball Reference way from box totals)
Missing values are left blank.
"""
import re
import time
import unicodedata
from datetime import date

import pandas as pd
from nba_api.stats.endpoints import (leaguedashplayershotlocations, leaguedashplayerstats,
                                     leaguedashptstats, synergyplaytypes)

import nba_stats
from team_styles import PLAY_TYPES, ZONES

SEASONS = ["2026-27", "2025-26"]
MIN_CURRENT_MINUTES = 150
PAUSE_SECONDS = 1
TIMEOUT = 30
TRACKING = {
    "Drives": {"DRIVES": "drives_pg"},
    "Passing": {"PASSES_MADE": "passes_pg", "AST_POINTS_CREATED": "ast_pts_created_pg"},
    "CatchShoot": {"CATCH_SHOOT_FGA": "cs_fga_pg", "CATCH_SHOOT_EFG_PCT": "cs_efg"},
    "PullUpShot": {"PULL_UP_FGA": "pullup_fga_pg", "PULL_UP_EFG_PCT": "pullup_efg"},
    "Possessions": {"TOUCHES": "touches_pg", "TIME_OF_POSS": "time_of_poss_pg"},
    "Rebounding": {"DREB": "dreb_pg", "OREB": "oreb_pg"},
    "Defense": {"DEF_RIM_FGA": "rim_dfga_pg", "DEF_RIM_FG_PCT": "rim_dfg_pct"},
}
failed = []


NAME_ALIASES = {"ronald holland": "ron holland"}   # NBA.com name -> BBRef name (normalized)


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name.lower().replace(".", "").replace("'", ""))
    name = re.sub(r"\s+", " ", name).strip()
    return NAME_ALIASES.get(name, name)


def call(label: str, endpoint, **kwargs) -> pd.DataFrame | None:
    for attempt in range(2):
        try:
            frame = endpoint(timeout=TIMEOUT, **kwargs).get_data_frames()[0]
            time.sleep(PAUSE_SECONDS)
            return frame
        except Exception as error:
            time.sleep(PAUSE_SECONDS * 3)
            if attempt:
                failed.append(f"{label} ({type(error).__name__})")
    return None


def season_styles(season: str) -> pd.DataFrame:
    through = date.today().strftime("%m/%d/%Y") if season == SEASONS[0] else None
    dated = dict(season=season, date_to_nullable=through) if through else dict(season=season)

    players, teams = nba_stats.fetch_season(season)
    df = players[["PLAYER_ID", "PLAYER_NAME", "GP", "MIN", "FGA", "STL", "BLK", "TEAM_ID"]].copy()
    team = teams.set_index("TEAM_ID")
    t = team.loc[df["TEAM_ID"]].reset_index(drop=True)
    df = df.reset_index(drop=True)
    t_mp = t["MIN"] * 5
    opp_poss = (t["OPP_FGA"] + 0.4 * t["OPP_FTA"]
                - 1.07 * (t["OPP_OREB"] / (t["OPP_OREB"] + t["DREB"])) * (t["OPP_FGA"] - t["OPP_FGM"])
                + t["OPP_TOV"])
    df["stl_pct"] = 100 * (df["STL"] * (t_mp / 5)) / (df["MIN"] * opp_poss)
    df["blk_pct"] = 100 * (df["BLK"] * (t_mp / 5)) / (df["MIN"] * (t["OPP_FGA"] - t["OPP_FG3A"]))
    df["fga_pg"] = df["FGA"] / df["GP"]
    df = df.rename(columns={"MIN": "mp"}).drop(columns=["FGA", "STL", "BLK", "TEAM_ID", "GP"])

    adv = call(f"{season} advanced", leaguedashplayerstats.LeagueDashPlayerStats,
               measure_type_detailed_defense="Advanced", per_mode_detailed="Totals", **dated)
    if adv is not None:
        df = df.merge(adv[["PLAYER_ID", "USG_PCT", "AST_PCT", "REB_PCT"]].rename(
            columns={"USG_PCT": "usg_pct", "AST_PCT": "ast_pct", "REB_PCT": "reb_pct"}), on="PLAYER_ID", how="left")

    poss_cols = []
    for play, short in PLAY_TYPES.items():
        frame = call(f"{season} synergy {play}", synergyplaytypes.SynergyPlayTypes, season=season,
                     player_or_team_abbreviation="P", play_type_nullable=play,
                     type_grouping_nullable="offensive", per_mode_simple="Totals")
        if frame is None or frame.empty:
            continue
        # Traded players have one row per team: combine stints by possessions
        frame = frame.assign(all_poss=frame["POSS"] / frame["POSS_PCT"]).groupby("PLAYER_ID").agg(
            poss=("POSS", "sum"), pts=("PTS", "sum"), all_poss=("all_poss", "sum")).reset_index()
        frame["freq"] = frame["poss"] / frame["all_poss"]
        frame["ppp"] = frame["pts"] / frame["poss"]
        frame = frame[["PLAYER_ID", "freq", "ppp", "poss"]]
        frame.columns = ["PLAYER_ID", f"{short}_freq", f"{short}_ppp", f"{short}_poss"]
        df = df.merge(frame, on="PLAYER_ID", how="left")
        poss_cols.append(f"{short}_poss")
    df.insert(3, "poss", df[poss_cols].sum(axis=1, min_count=1) if poss_cols else pd.NA)

    shots = call(f"{season} shot zones", leaguedashplayershotlocations.LeagueDashPlayerShotLocations,
                 distance_range="By Zone", per_mode_detailed="Totals", **dated)
    if shots is not None:
        shots.columns = [f"{zone}|{stat}" if zone else stat for zone, stat in shots.columns]
        total = shots[[c for c in shots.columns if c.endswith("|FGA") and not c.startswith(
            ("Left Corner", "Right Corner", "Corner 3"))]].sum(axis=1) + shots["Corner 3|FGA"]
        zones = pd.DataFrame({"PLAYER_ID": shots["PLAYER_ID"]})
        for zone, short in ZONES.items():
            zones[f"{short}_fga_share"] = (shots[f"{zone}|FGA"] / total).where(total > 0)
            zones[f"{short}_fg_pct"] = shots[f"{zone}|FG_PCT"].where(shots[f"{zone}|FGA"] > 0)
        df = df.merge(zones, on="PLAYER_ID", how="left")

    for measure, cols in TRACKING.items():
        frame = call(f"{season} tracking {measure}", leaguedashptstats.LeagueDashPtStats,
                     player_or_team="Player", pt_measure_type=measure, per_mode_simple="PerGame", **dated)
        if frame is None:
            continue
        present = {k: v for k, v in cols.items() if k in frame.columns}
        failed.extend(f"{season} {measure} has no {k}" for k in cols if k not in frame.columns)
        df = df.merge(frame[["PLAYER_ID"] + list(present)].rename(columns=present), on="PLAYER_ID", how="left")

    df["season"] = season
    df["key"] = df["PLAYER_NAME"].map(normalize)
    return df.drop_duplicates("key")


def main() -> None:
    roster = pd.read_csv("outputs/contract_value.csv")[["Player", "Team"]]
    roster["key"] = roster["Player"].map(normalize)
    current, last = (season_styles(s) for s in SEASONS)

    rows = []
    for player in roster.itertuples():
        now, before = current[current["key"] == player.key], last[last["key"] == player.key]
        pick = now if not now.empty and (now["mp"].iloc[0] >= MIN_CURRENT_MINUTES or before.empty) else before
        if not pick.empty:
            rows.append(pick.iloc[0].to_dict() | {"Player": player.Player, "Team": player.Team})
    styles = pd.DataFrame(rows)
    order = ["Player", "Team", "season", "mp", "poss"]
    rest = [c for c in styles.columns if c not in order + ["PLAYER_ID", "PLAYER_NAME", "key"]]
    styles = styles[order + rest].round(4)
    styles.to_csv("outputs/player_styles.csv", index=False)

    unmatched = sorted(set(roster["Player"]) - set(styles["Player"]))
    print(f"Saved outputs/player_styles.csv: {len(styles)} of {len(roster)} players "
          f"({(styles['season'] == SEASONS[0]).sum()} on {SEASONS[0]}, "
          f"{(styles['season'] == SEASONS[1]).sum()} on {SEASONS[1]}); unmatched {len(unmatched)}"
          + (f": {', '.join(unmatched)}" if unmatched else ""))
    if failed:
        print("Skipped: " + "; ".join(failed))


if __name__ == "__main__":
    main()
