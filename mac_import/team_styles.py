"""
Team play styles for the current season from NBA.com (nba_api). Run by
refresh.py, or on its own: python team_styles.py

About 30 requests, one second apart:
- Synergy play types, offense and defense: frequency (share of possessions)
  and points per possession for ten play types.
- Tracking per game: drives, passes, catch-and-shoot and pull-up shooting,
  paint / elbow / post touches.
- Shot locations: share of FGA and FG% by zone.
- Pace, offensive and defensive rating, and the four factors for and against.
Any endpoint that fails is skipped and listed at the end; the rest still saves.

Outputs: outputs/team_styles.csv (one row per team, BBRef codes) and
outputs/team_styles_league.csv (the unweighted average of the 30 teams).
"""
import time
from datetime import date

import pandas as pd
from nba_api.stats.endpoints import (leaguedashptstats, leaguedashteamshotlocations,
                                     leaguedashteamstats, synergyplaytypes)

SEASON = "2026-27"
PAUSE_SECONDS = 1
TIMEOUT = 30
TO_BREF = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
PLAY_TYPES = {   # NBA.com name -> column prefix
    "PRBallHandler": "prbh", "PRRollman": "prroll", "Isolation": "iso", "Postup": "post",
    "Transition": "trans", "Spotup": "spotup", "Cut": "cut", "Handoff": "handoff",
    "OffScreen": "offscreen", "OffRebound": "putback",
}
TRACKING = {   # measure type -> {NBA.com column: our column}
    "Drives": {"DRIVES": "drives_pg"},
    "Passing": {"PASSES_MADE": "passes_pg"},
    "CatchShoot": {"CATCH_SHOOT_FGA": "cs_fga_pg", "CATCH_SHOOT_EFG_PCT": "cs_efg"},
    "PullUpShot": {"PULL_UP_FGA": "pullup_fga_pg", "PULL_UP_EFG_PCT": "pullup_efg"},
    "PaintTouch": {"PAINT_TOUCHES": "paint_touches_pg"},
    "ElbowTouch": {"ELBOW_TOUCHES": "elbow_touches_pg"},
    "PostTouch": {"POST_TOUCHES": "post_touches_pg"},
}
ZONES = {"Restricted Area": "ra", "In The Paint (Non-RA)": "paint", "Mid-Range": "mid",
         "Corner 3": "corner3", "Above the Break 3": "atb3"}
failed = []


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


def main() -> None:
    through = date.today().strftime("%m/%d/%Y")
    dated = dict(season=SEASON, date_to_nullable=through)

    adv = call("advanced", leaguedashteamstats.LeagueDashTeamStats, measure_type_detailed_defense="Advanced",
               per_mode_detailed="Totals", **dated)
    teams = adv[["TEAM_ID"]].copy()
    teams[["pace", "ortg", "drtg"]] = adv[["PACE", "OFF_RATING", "DEF_RATING"]]

    four = call("four factors", leaguedashteamstats.LeagueDashTeamStats,
                measure_type_detailed_defense="Four Factors", per_mode_detailed="Totals", **dated)
    if four is not None:
        cols = {"EFG_PCT": "off_efg", "FTA_RATE": "off_fta_rate", "TM_TOV_PCT": "off_tov_pct",
                "OREB_PCT": "off_oreb_pct", "OPP_EFG_PCT": "def_efg", "OPP_FTA_RATE": "def_fta_rate",
                "OPP_TOV_PCT": "def_tov_pct", "OPP_OREB_PCT": "def_oreb_pct"}
        teams = teams.merge(four[["TEAM_ID"] + list(cols)].rename(columns=cols), on="TEAM_ID", how="left")

    abbr = None
    for side in ("offensive", "defensive"):
        for play, short in PLAY_TYPES.items():
            frame = call(f"synergy {side} {play}", synergyplaytypes.SynergyPlayTypes, season=SEASON,
                         player_or_team_abbreviation="T", play_type_nullable=play,
                         type_grouping_nullable=side, per_mode_simple="Totals")
            if frame is None or frame.empty:
                continue
            abbr = frame.set_index("TEAM_ID")["TEAM_ABBREVIATION"] if abbr is None else abbr
            prefix = f"{side[:3]}_{short}"
            frame = frame[["TEAM_ID", "POSS_PCT", "PPP"]].rename(
                columns={"POSS_PCT": f"{prefix}_freq", "PPP": f"{prefix}_ppp"})
            teams = teams.merge(frame, on="TEAM_ID", how="left")

    for measure, cols in TRACKING.items():
        frame = call(f"tracking {measure}", leaguedashptstats.LeagueDashPtStats, player_or_team="Team",
                     pt_measure_type=measure, per_mode_simple="PerGame", **dated)
        if frame is not None:
            abbr = frame.set_index("TEAM_ID")["TEAM_ABBREVIATION"] if abbr is None else abbr
            teams = teams.merge(frame[["TEAM_ID"] + list(cols)].rename(columns=cols), on="TEAM_ID", how="left")

    shots = call("shot locations", leaguedashteamshotlocations.LeagueDashTeamShotLocations,
                 distance_range="By Zone", per_mode_detailed="Totals", **dated)
    if shots is not None:
        shots.columns = [f"{zone}|{stat}" if zone else stat for zone, stat in shots.columns]
        total_fga = shots[[c for c in shots.columns if c.endswith("|FGA") and not c.startswith(
            ("Left Corner", "Right Corner", "Corner 3"))]].sum(axis=1) + shots["Corner 3|FGA"]
        zone_cols = pd.DataFrame({"TEAM_ID": shots["TEAM_ID"]})
        for zone, short in ZONES.items():
            zone_cols[f"{short}_fga_share"] = shots[f"{zone}|FGA"] / total_fga
            zone_cols[f"{short}_fg_pct"] = shots[f"{zone}|FG_PCT"]
        teams = teams.merge(zone_cols, on="TEAM_ID", how="left")

    if abbr is None:
        names = call("team list", leaguedashteamstats.LeagueDashTeamStats, per_mode_detailed="Totals", **dated)
        abbr = names.set_index("TEAM_ID")["TEAM_NAME"]
    teams.insert(0, "Team", teams["TEAM_ID"].map(abbr).replace(TO_BREF))
    teams = teams.drop(columns="TEAM_ID").sort_values("Team").round(4)
    teams.to_csv("outputs/team_styles.csv", index=False)
    league = teams.drop(columns="Team").mean().round(4).to_frame().T
    league.insert(0, "Team", "League average")
    league.to_csv("outputs/team_styles_league.csv", index=False)
    print(f"Saved outputs/team_styles.csv ({len(teams)} teams, {teams.shape[1] - 1} columns) "
          f"and outputs/team_styles_league.csv")
    if failed:
        print("Skipped (failed): " + "; ".join(failed))


if __name__ == "__main__":
    main()
