"""
Season stats from NBA.com via nba_api, with Win Shares computed the way
Basketball Reference does (nba_api has no Win Shares).

Requests per season: player totals, team totals, opponent totals (three calls,
one second apart, 30s timeout, one retry each). Each request carries a
"through today" date filter: without it NBA.com can serve a stale cached copy.

Win Shares follow Basketball Reference's method:
- Offense: Dean Oliver's points produced and offensive possessions;
  OWS = (points produced - 0.92 x league points per possession x possessions)
        / marginal points per win.
- Defense: Oliver's individual defensive rating;
  DWS = (MP / team MP) x team defensive possessions x (1.08 x league points per
        possession - DRtg / 100) / marginal points per win.
- Marginal points per win = 0.32 x league points per game x team pace / league pace.
Players traded mid-season are computed against their latest team (NBA.com
combines their totals), so their WS can differ a little from BBRef's.
"""
import time
from datetime import date

import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats

PAUSE_SECONDS = 1
TIMEOUT = 30
TO_BREF = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}


def _call(endpoint, **kwargs) -> pd.DataFrame:
    for attempt in range(2):
        try:
            frame = endpoint(timeout=TIMEOUT, **kwargs).get_data_frames()[0]
            time.sleep(PAUSE_SECONDS)
            return frame
        except Exception:
            if attempt:
                raise
            time.sleep(PAUSE_SECONDS * 3)


def fetch_season(season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Player totals and team totals (with opponent columns) for e.g. '2026-27'."""
    through = date.today().strftime("%m/%d/%Y")
    players = _call(leaguedashplayerstats.LeagueDashPlayerStats, season=season, date_to_nullable=through,
                    measure_type_detailed_defense="Base", per_mode_detailed="Totals")
    teams = _call(leaguedashteamstats.LeagueDashTeamStats, season=season, date_to_nullable=through,
                  measure_type_detailed_defense="Base", per_mode_detailed="Totals")
    opp = _call(leaguedashteamstats.LeagueDashTeamStats, season=season, date_to_nullable=through,
                measure_type_detailed_defense="Opponent", per_mode_detailed="Totals")
    teams = teams.merge(opp[["TEAM_ID"] + [c for c in opp.columns if c.startswith("OPP_")]], on="TEAM_ID")
    abbr = players.groupby("TEAM_ID")["TEAM_ABBREVIATION"].agg(lambda s: s.mode()[0])
    teams["TEAM_ABBREVIATION"] = teams["TEAM_ID"].map(abbr)
    return players, teams


def win_shares(players: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    t = teams.set_index("TEAM_ID")
    t_mp = t["MIN"] * 5   # team totals are game minutes; BBRef team MP counts all five players

    def poss(fga, fta, orb, drb_opp, fgm, tov):
        return fga + 0.4 * fta - 1.07 * (orb / (orb + drb_opp)) * (fga - fgm) + tov

    t_poss = 0.5 * (poss(t["FGA"], t["FTA"], t["OREB"], t["OPP_DREB"], t["FGM"], t["TOV"])
                    + poss(t["OPP_FGA"], t["OPP_FTA"], t["OPP_OREB"], t["DREB"], t["OPP_FGM"], t["OPP_TOV"]))
    pace = 48 * t_poss / (t_mp / 5)
    lg_ppp = t["PTS"].sum() / t_poss.sum()
    lg_ppg = t["PTS"].sum() / t["GP"].sum()
    lg_pace = 48 * t_poss.sum() / (t_mp.sum() / 5)

    p = players.copy()
    T = t.loc[p["TEAM_ID"]].reset_index(drop=True)
    p = p.reset_index(drop=True)
    tmp, tposs, tpace = t_mp.loc[p["TEAM_ID"]].values, t_poss.loc[p["TEAM_ID"]].values, pace.loc[p["TEAM_ID"]].values
    mp = p["MIN"]

    # --- Offense (points produced, possessions)
    q_ast = ((mp / (tmp / 5)) * (1.14 * ((T["AST"] - p["AST"]) / T["FGM"]))
             + (((T["AST"] / tmp) * mp * 5 - p["AST"]) / ((T["FGM"] / tmp) * mp * 5 - p["FGM"]))
             * (1 - (mp / (tmp / 5))))
    fg_share = (1 - 0.5 * ((p["PTS"] - p["FTM"]) / (2 * p["FGA"])) * q_ast).where(p["FGA"] > 0, 0)
    ft_pct = (p["FTM"] / p["FTA"]).where(p["FTA"] > 0, 0)
    t_ft = T["FTM"] / T["FTA"]
    t_sc_poss = T["FGM"] + (1 - (1 - t_ft) ** 2) * T["FTA"] * 0.4
    t_orb_pct = T["OREB"] / (T["OREB"] + (T["OPP_REB"] - T["OPP_OREB"]))
    t_play = t_sc_poss / (T["FGA"] + T["FTA"] * 0.4 + T["TOV"])
    t_orb_w = ((1 - t_orb_pct) * t_play) / ((1 - t_orb_pct) * t_play + t_orb_pct * (1 - t_play))
    others_scoring = ((T["PTS"] - T["FTM"]) - (p["PTS"] - p["FTM"])) / (2 * (T["FGA"] - p["FGA"]))
    orb_factor = 1 - (T["OREB"] / t_sc_poss) * t_orb_w * t_play

    sc_poss = ((p["FGM"] * fg_share + 0.5 * others_scoring * p["AST"]
                + (1 - (1 - ft_pct) ** 2) * 0.4 * p["FTA"]) * orb_factor
               + p["OREB"] * t_orb_w * t_play)
    tot_poss = (sc_poss + (p["FGA"] - p["FGM"]) * (1 - 1.07 * t_orb_pct)
                + (1 - ft_pct) ** 2 * 0.4 * p["FTA"] + p["TOV"])
    pprod = ((2 * (p["FGM"] + 0.5 * p["FG3M"]) * fg_share
              + 2 * ((T["FGM"] - p["FGM"] + 0.5 * (T["FG3M"] - p["FG3M"])) / (T["FGM"] - p["FGM"]))
              * 0.5 * others_scoring * p["AST"] + p["FTM"]) * orb_factor
             + p["OREB"] * t_orb_w * t_play * (T["PTS"] / t_sc_poss))

    # --- Defense (individual defensive rating)
    dor = T["OPP_OREB"] / (T["OPP_OREB"] + T["DREB"])
    dfg = T["OPP_FGM"] / T["OPP_FGA"]
    fmwt = (dfg * (1 - dor)) / (dfg * (1 - dor) + (1 - dfg) * dor)
    stops = (p["STL"] + p["BLK"] * fmwt * (1 - 1.07 * dor) + p["DREB"] * (1 - fmwt)
             + (((T["OPP_FGA"] - T["OPP_FGM"] - T["BLK"]) / tmp) * fmwt * (1 - 1.07 * dor)
                + ((T["OPP_TOV"] - T["STL"]) / tmp)) * mp
             + (p["PF"] / T["PF"]) * 0.4 * T["OPP_FTA"] * (1 - T["OPP_FTM"] / T["OPP_FTA"]) ** 2)
    stop_pct = (stops * tmp) / (tposs * mp)
    team_drtg = 100 * T["OPP_PTS"] / tposs
    d_pts_per_sc = T["OPP_PTS"] / (T["OPP_FGM"] + (1 - (1 - T["OPP_FTM"] / T["OPP_FTA"]) ** 2) * T["OPP_FTA"] * 0.4)
    drtg = team_drtg + 0.2 * (100 * d_pts_per_sc * (1 - stop_pct) - team_drtg)

    # --- Win Shares
    pts_per_win = 0.32 * lg_ppg * (tpace / lg_pace)
    ows = (pprod - 0.92 * lg_ppp * tot_poss) / pts_per_win
    dws = ((mp / tmp) * tposs * (1.08 * lg_ppp - drtg / 100)) / pts_per_win
    out = p[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN"]].copy()
    out["WS"] = (ows.fillna(0) + dws.where(mp > 0, 0).fillna(0)).values
    out["TEAM_ABBREVIATION"] = out["TEAM_ABBREVIATION"].replace(TO_BREF)
    return out
