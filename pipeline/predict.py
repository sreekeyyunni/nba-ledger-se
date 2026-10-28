"""
Nightly game predictor: python predict.py

1. Downloads this season's schedule/results (one Basketball Reference page per
   month played so far, plus next month near month end) and the BBRef injury
   report. Skip with --offline to reuse data/schedule_2026_27.csv and
   data/injuries.csv.
2. Rates every team from its roster: each player's WS/48 (2025-26 blended with
   2026-27, shrunk toward 0.060 for small samples) times projected minutes,
   filled to 240 minutes a game with replacement-level players. Injured players
   are taken out (day-to-day ones count half), which is how injuries move a line.
3. Adds "form": how much each team has beaten or missed its expected margin in
   games played so far, shrunk toward zero (worth ~half after 8 games).
4. Predicted home margin = home rating - away rating + home court, minus a
   back-to-back penalty; win probability = normal CDF(margin / 11.5).
5. Picks are locked in outputs/predictions_log.csv the first time a game is
   predicted on or before game day, and never rewritten, so the record is honest.
   Games played before the predictor existed are filled in as "backtest" picks
   that only use results from earlier dates and no injury news.

Writes outputs/predictions.csv (every game with pick, probability, result) and
outputs/team_power.csv (ratings), which the app's Predictions page reads.
"""
import argparse
import csv
import math
import re
import unicodedata
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SEASON_MONTHS = ["october", "november", "december", "january", "february", "march", "april"]
SCHEDULE_URL = "https://www.basketball-reference.com/leagues/NBA_2027_games-{month}.html"
INJURY_URL = "https://www.basketball-reference.com/friv/injuries.fcgi"
# ESPN's public JSON feeds (the data behind espn.com/nba/scoreboard); scores update live
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={ymd}"
ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
ESPN_CODES = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO", "GS": "GSW", "NY": "NYK", "NO": "NOP",
              "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
SCHEDULE_FILE = Path("data/schedule_2026_27.csv")
INJURY_FILE = Path("data/injuries.csv")
LOG_FILE = Path("outputs/predictions_log.csv")

HOME_COURT = 2.3        # points
BACK_TO_BACK = 1.5      # points lost by a team on the second night
MARGIN_SD = 11.5        # spread of real margins around the prediction
MARGIN_CAP = 25         # blowouts count as 25-point games for form
FORM_SHRINK = 8         # games of "prior" weight in the form average
PRIOR_WS48 = 0.060      # small-sample players shrink toward this
PRIOR_MP = 500          # ...with this many minutes of weight
REPLACEMENT_WS48 = 0.030
THIS_SEASON_WEIGHT = 2.0  # one 2026-27 minute counts as much as two 2025-26 minutes
MAX_MPG = 37.0
POINTS_PER_WIN_PCT = 1 / 0.033   # ~1 point of margin per 2.7 wins over 82 games
RATING_SPREAD = 0.80    # roster ratings are noisy; pull them a bit toward average

TEAMS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BRK", "Charlotte Hornets": "CHO",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHO", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {len(rows)} rows to {path}")


def key(name):
    """Match names across sources: no accents, punctuation or Jr./II suffixes."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z ]", "", n)
    return re.sub(r" (jr|sr|ii|iii|iv)$", "", n.strip())


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------- download ----------

def fetch_schedule(today):
    import bref
    rows = []
    for month in SEASON_MONTHS:
        html = bref.fetch(SCHEDULE_URL.format(month=month))
        for r in bref.read_table(html, "schedule"):
            d = datetime.strptime(r["date_game"], "%a, %b %d, %Y").date()
            rows.append([d.isoformat(), r.get("game_start_time", ""), TEAMS[r["visitor_team_name"]],
                         r.get("visitor_pts", ""), TEAMS[r["home_team_name"]], r.get("home_pts", ""),
                         r.get("overtimes", "")])
        last = max(date.fromisoformat(x[0]) for x in rows)
        if last > today + timedelta(days=7):   # far enough ahead; don't load later months
            break
    write_csv(SCHEDULE_FILE, ["date", "time_et", "away", "away_pts", "home", "home_pts", "ot"], rows)


def fetch_injuries():
    import bref
    rows = bref.read_table(bref.fetch(INJURY_URL), "injuries")
    write_csv(INJURY_FILE, ["player", "team", "updated", "note"],
              [[r.get("player", ""), TEAMS.get(r.get("team_name", ""), r.get("team_name", "")),
                r.get("date_update", ""), r.get("note", "")] for r in rows])


def espn_team(code):
    code = ESPN_CODES.get(code, code)
    if code not in TEAMS.values():
        raise ValueError(f"unknown ESPN team code {code}")
    return code


def update_scores_espn(today):
    """Fill in scores from ESPN for every night from the oldest unfinished game through tomorrow.

    The BBRef schedule CSV stays the base (it has the whole month); usually this is
    two requests: last night's results and tonight's slate (live scores mid-game too).
    """
    import json
    from zoneinfo import ZoneInfo
    import bref
    games = read_csv(SCHEDULE_FILE) if SCHEDULE_FILE.exists() else []
    index = {(g["date"], g["away"], g["home"]): g for g in games}
    open_dates = [g["date"] for g in games if g["home_pts"] == "" and g["date"] <= today.isoformat()]
    start = date.fromisoformat(min(open_dates)) if open_dates else today
    d = start
    while d <= today + timedelta(days=1):
        data = json.loads(bref.fetch(ESPN_SCOREBOARD.format(ymd=d.strftime("%Y%m%d"))))
        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            side = {c["homeAway"]: c for c in comp["competitors"]}
            away, home = espn_team(side["away"]["team"]["abbreviation"]), espn_team(side["home"]["team"]["abbreviation"])
            tip = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
            key3 = (tip.date().isoformat(), away, home)
            g = index.get(key3)
            if g is None:      # not in the BBRef file yet (or rescheduled): add it
                g = {"date": key3[0], "time_et": tip.strftime("%-I:%M") + tip.strftime("%p")[0].lower(),
                     "away": away, "away_pts": "", "home": home, "home_pts": "", "ot": "", "live": ""}
                games.append(g)
                index[key3] = g
            state = ev.get("status", {}).get("type", {})
            if state.get("completed"):
                g["away_pts"], g["home_pts"] = side["away"].get("score", ""), side["home"].get("score", "")
                period = ev.get("status", {}).get("period", 4)
                g["ot"] = "" if period <= 4 else ("OT" if period == 5 else f"{period - 4}OT")
                g["live"] = ""
            elif state.get("state") == "in":   # game on: keep the live score separately, not as a result
                g["live"] = f'{side["away"].get("score", "")}-{side["home"].get("score", "")} {state.get("shortDetail", "")}'
        d += timedelta(days=1)
    games.sort(key=lambda g: (g["date"], g["time_et"]))
    write_csv(SCHEDULE_FILE, ["date", "time_et", "away", "away_pts", "home", "home_pts", "ot", "live"],
              [[g["date"], g["time_et"], g["away"], g["away_pts"], g["home"], g["home_pts"], g.get("ot", ""),
                g.get("live", "")] for g in games])


BDL_GAMES = "https://api.balldontlie.io/v1/games"


def bdl_key():
    """balldontlie API key from the environment (GitHub secret) or .env (BALLDONTLIE_API_KEY=...), or None."""
    import os
    if os.environ.get("BALLDONTLIE_API_KEY"):
        return os.environ["BALLDONTLIE_API_KEY"].strip()
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("BALLDONTLIE_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    return None


def update_scores_bdl(today, api_key):
    """Fallback when ESPN fails: final scores from balldontlie's free games endpoint.

    One request covers every open night through tomorrow. The free tier has no live
    scores, box scores or injuries; with a paid key, live scores come through too.
    """
    import json
    import subprocess
    games = read_csv(SCHEDULE_FILE) if SCHEDULE_FILE.exists() else []
    index = {(g["date"], g["away"], g["home"]): g for g in games}
    open_dates = [g["date"] for g in games if g["home_pts"] == "" and g["date"] <= today.isoformat()]
    d = date.fromisoformat(min(open_dates)) if open_dates else today
    dates = []
    while d <= today + timedelta(days=1):
        dates.append(d.isoformat())
        d += timedelta(days=1)
    url = BDL_GAMES + "?per_page=100&" + "&".join(f"dates[]={x}" for x in dates)
    out = subprocess.run(["curl", "-sSf", "-m", "30", "-H", f"Authorization: {api_key}", url],
                         capture_output=True, check=True, text=True).stdout
    for ev in json.loads(out).get("data", []):
        away, home = espn_team(ev["visitor_team"]["abbreviation"]), espn_team(ev["home_team"]["abbreviation"])
        g = index.get((ev["date"][:10], away, home))
        if g is None:
            continue    # keep the schedule's own rows; tip times come from BBRef/ESPN
        state = ev.get("status_state") or ""
        if state == "final" or str(ev.get("status", "")).lower().startswith("final"):
            g["away_pts"], g["home_pts"] = str(ev["visitor_team_score"]), str(ev["home_team_score"])
            period = ev.get("period") or 4
            g["ot"] = "" if period <= 4 else ("OT" if period == 5 else f"{period - 4}OT")
            g["live"] = ""
        elif state == "in_progress":   # paid tiers only; the free one never reports games in progress
            g["live"] = f'{ev["visitor_team_score"]}-{ev["home_team_score"]} {ev.get("time") or ev.get("status", "")}'
    write_csv(SCHEDULE_FILE, ["date", "time_et", "away", "away_pts", "home", "home_pts", "ot", "live"],
              [[g["date"], g["time_et"], g["away"], g["away_pts"], g["home"], g["home_pts"], g.get("ot", ""),
                g.get("live", "")] for g in games])


def fetch_injuries_espn():
    import json
    import bref
    data = json.loads(bref.fetch(ESPN_INJURIES))
    names = {v: k for k, v in TEAMS.items()}
    by_name = {k.lower(): v for k, v in TEAMS.items()}
    rows = []
    for team in data.get("injuries", []):
        code = by_name.get(team.get("displayName", "").lower(), team.get("displayName", ""))
        for inj in team.get("injuries", []):
            status = inj.get("status", "")
            note = f'{status} - {inj.get("shortComment", "")}'.strip(" -")
            rows.append([inj.get("athlete", {}).get("displayName", ""), code, inj.get("date", "")[:10], note])
    if not rows:
        raise ValueError("ESPN injury feed came back empty")
    write_csv(INJURY_FILE, ["player", "team", "updated", "note"], rows)


# balldontlie team ids are the 30 teams in order of full name
BDL_TEAMS = ["ATL", "BOS", "BRK", "CHO", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM",
             "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"]


def fetch_injuries_bdl(today, api_key, out=INJURY_FILE):
    """Injury report from balldontlie (paid tiers only; the free key gets a 401, so the caller moves on)."""
    import json
    import subprocess
    import time
    rows, cursor = [], None
    for page in range(5):   # about 2 pages in season; paced for the free tier's 5 requests a minute
        url = "https://api.balldontlie.io/v1/player_injuries?per_page=100" + (f"&cursor={cursor}" if cursor else "")
        data = json.loads(subprocess.run(["curl", "-sSf", "-m", "30", "-H", f"Authorization: {api_key}", url],
                                         capture_output=True, check=True, text=True).stdout)
        for inj in data.get("data", []):
            pl, status = inj.get("player", {}), inj.get("status", "")
            tid = pl.get("team_id")
            if not tid or status == "Available" or not 1 <= tid <= 30:
                continue
            desc = (inj.get("description") or "").split(" Prior reporting")[0]
            back = f' Expected back {inj["return_date"]}.' if inj.get("return_date") else ""
            rows.append([f'{pl.get("first_name", "")} {pl.get("last_name", "")}'.strip(), BDL_TEAMS[tid - 1],
                         today.isoformat(), f"{status} - {desc}{back}".strip(" -")])
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(13)
    if not rows:
        raise ValueError("balldontlie injury feed came back empty")
    write_csv(out, ["player", "team", "updated", "note"], rows)


# ---------- model ----------

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def load_players():
    """Current rosters with a blended WS/48 and projected minutes per game."""
    last = {}
    for r in read_csv("data/advanced_2025_26.csv"):
        if r.get("Player"):
            last.setdefault(key(r["Player"]), r)    # first row = season total for traded players
    now, names = {}, {}
    for r in read_csv("data/advanced_2026_27.csv"):
        if r.get("Player") and not r["Team"].endswith("TM"):
            now[key(r["Player"])] = r          # a traded player's last team row wins
            names[key(r["Player"])] = r["Player"]
    team_of = {p: r["Team"] for p, r in now.items()}
    for r in read_csv("outputs/contract_value.csv"):   # signed players who haven't played yet
        team_of.setdefault(key(r["Player"]), r["Team"])
        names.setdefault(key(r["Player"]), r["Player"])

    players = []
    for p, team in team_of.items():
        if team not in TEAMS.values():
            continue
        a, b = last.get(p), now.get(p)
        mp_a = num(a["MP"]) if a else 0
        mp_b = num(b["MP"]) if b else 0
        ws_a = num(a["WS"]) if a else 0
        ws_b = num(b["WS"]) if b else 0
        w_mp = mp_a + THIS_SEASON_WEIGHT * mp_b
        w_ws = ws_a + THIS_SEASON_WEIGHT * ws_b
        ws48 = (w_ws * 48 + PRIOR_WS48 * PRIOR_MP) / (w_mp + PRIOR_MP)
        g_a = num(a["G"]) if a else 0
        g_b = num(b["G"]) if b else 0
        mpg_a = mp_a / g_a if g_a else 0
        mpg_b = mp_b / g_b if g_b else 0
        if g_a and g_b:
            wb = min(g_b / 20, 0.8)        # trust this season's role more as games pile up
            mpg = (1 - wb) * mpg_a + wb * mpg_b
        else:
            mpg = mpg_a or mpg_b
        players.append({"player": p, "name": names[p], "team": team, "ws48": ws48, "mpg": min(mpg, MAX_MPG)})
    return players


GAME_NOTE = re.compile(r"for (\w{3})\.? (\d{1,2}) game")


def injury_status(note, today):
    """Share of normal minutes we expect tonight: 0 out, 0.5 maybe, 1 healthy."""
    n = note.lower()
    m = GAME_NOTE.search(n)
    if m:   # "Out for Oct. 23 game": once that game has passed, he's a maybe
        try:
            d = datetime.strptime(f"{m.group(1)} {m.group(2)} {today.year}", "%b %d %Y").date()
            if d < today:
                return 0.5
        except ValueError:
            pass
    if n.startswith("out"):
        return 0.0
    if "day to day" in n or "day-to-day" in n or "questionable" in n or "doubtful" in n:
        return 0.5
    return 1.0


def team_rating(roster, availability=None):
    """Expected net points per game vs an average team, from who is available."""
    availability = availability or {}
    pool = sorted(((p["ws48"], p["mpg"] * availability.get(p["player"], 1.0)) for p in roster),
                  key=lambda x: -x[1])
    minutes, ws_per_game = 0.0, 0.0
    for ws48, mpg in pool:
        m = min(mpg, 240 - minutes)
        if m <= 0:
            break
        minutes += m
        ws_per_game += ws48 * m / 48
    ws_per_game += REPLACEMENT_WS48 * (240 - minutes) / 48
    return (ws_per_game - 0.5) * POINTS_PER_WIN_PCT


def build(today):
    players = load_players()
    rosters = {t: [p for p in players if p["team"] == t] for t in TEAMS.values()}

    injuries = read_csv(INJURY_FILE) if INJURY_FILE.exists() else []
    avail, status = {}, {}
    for r in injuries:
        s = injury_status(r["note"], today)
        if s < 1:
            k = key(r["player"])
            avail[k] = min(avail.get(k, 1.0), s)
            status[k] = "out" if avail[k] == 0 else "questionable"

    healthy = {t: team_rating(rosters[t]) for t in rosters}
    tonight = {t: team_rating(rosters[t], avail) for t in rosters}
    mean = sum(healthy.values()) / len(healthy)
    healthy = {t: (v - mean) * RATING_SPREAD for t, v in healthy.items()}
    tonight = {t: (v - mean) * RATING_SPREAD for t, v in tonight.items()}

    # what each missing player costs his team, so the page can name the ones that matter
    notes = {t: [] for t in TEAMS.values()}
    for t, roster in rosters.items():
        hurt = []
        for p in roster:
            if p["player"] in avail:
                cost = (team_rating(roster) - team_rating(roster, {p["player"]: 0.0})) * RATING_SPREAD
                if cost >= 0.3:
                    hurt.append((cost, f'{p["name"]} ({status[p["player"]]}, {cost:.1f} pts)'))
        notes[t] = [h for _, h in sorted(hurt, reverse=True)]

    games = read_csv(SCHEDULE_FILE)
    games.sort(key=lambda g: (g["date"], g["time_et"]))
    played_dates = {}
    for g in games:
        for t in (g["away"], g["home"]):
            played_dates.setdefault(t, set()).add(g["date"])

    log = {}
    if LOG_FILE.exists():
        for r in read_csv(LOG_FILE):
            log[(r["date"], r["away"], r["home"])] = r

    resid = {t: [] for t in TEAMS.values()}   # form residuals so far (by date order)
    record = {t: [0, 0] for t in TEAMS.values()}
    out_rows, new_log = [], []
    by_date = {}
    for g in games:
        by_date.setdefault(g["date"], []).append(g)

    def form(t):
        r = resid[t]
        return sum(r) / (len(r) + FORM_SHRINK)

    for d in sorted(by_date):
        day = date.fromisoformat(d)
        if day > today + timedelta(days=0):
            break   # only predict through tonight
        prev = (day - timedelta(days=1)).isoformat()
        day_rows = []
        for g in by_date[d]:
            a, h = g["away"], g["home"]
            live = day == today
            ra = (tonight if live else healthy)[a] + form(a)
            rh = (tonight if live else healthy)[h] + form(h)
            b2b_a = prev in played_dates.get(a, ())
            b2b_h = prev in played_dates.get(h, ())
            margin = rh - ra + HOME_COURT - BACK_TO_BACK * b2b_h + BACK_TO_BACK * b2b_a
            p_home = norm_cdf(margin / MARGIN_SD)
            gkey = (d, a, h)
            if gkey in log:                  # locked earlier: keep the original pick
                L = log[gkey]
                p_home, margin, mode = float(L["home_prob"]), float(L["home_margin"]), L["mode"]
            else:
                mode = "live" if live else "backtest"
                new_log.append([d, a, h, f"{p_home:.4f}", f"{margin:.2f}", mode,
                                datetime.now().isoformat(timespec="minutes")])
            pick = h if p_home >= 0.5 else a
            final = g["home_pts"] != "" and g["away_pts"] != ""
            correct = ""
            if final:
                winner = h if num(g["home_pts"]) > num(g["away_pts"]) else a
                correct = "1" if pick == winner else "0"
            why = []
            if b2b_a:
                why.append(f"{a} on a back-to-back")
            if b2b_h:
                why.append(f"{h} on a back-to-back")
            inj_a = "; ".join(notes[a]) if live else ""
            inj_h = "; ".join(notes[h]) if live else ""
            day_rows.append((g, a, h, p_home, margin, pick, final, correct, mode, why, inj_a, inj_h, ra, rh))
        # results of this date feed form for later dates only
        for (g, a, h, p_home, margin, pick, final, correct, mode, why, inj_a, inj_h, ra, rh) in day_rows:
            out_rows.append([d, g["time_et"], a, h, g["away_pts"], g["home_pts"], g.get("ot", ""),
                             f"{p_home:.3f}", f"{margin:.1f}", pick, "final" if final else ("live" if g.get("live") else "upcoming"),
                             correct, mode, f"{ra:.1f}", f"{rh:.1f}", " | ".join(why), inj_a, inj_h, g.get("live", "")])
            if final:
                actual = max(-MARGIN_CAP, min(MARGIN_CAP, num(g["home_pts"]) - num(g["away_pts"])))
                expected = healthy[h] - healthy[a] + HOME_COURT
                resid[h].append(actual - expected)
                resid[a].append(-(actual - expected))
                win_h = num(g["home_pts"]) > num(g["away_pts"])
                record[h][0 if win_h else 1] += 1
                record[a][1 if win_h else 0] += 1

    # upcoming slate after tonight is not predicted (injuries and form will change)
    Path("outputs").mkdir(exist_ok=True)
    write_csv("outputs/predictions.csv",
              ["date", "time_et", "away", "home", "away_pts", "home_pts", "ot", "home_prob", "home_margin",
               "pick", "status", "correct", "mode", "away_rating", "home_rating", "factors",
               "away_injuries", "home_injuries", "live"], out_rows)
    power = sorted(TEAMS.values(), key=lambda t: -(tonight[t] + form(t)))
    write_csv("outputs/team_power.csv",
              ["rank", "team", "rating", "roster_healthy", "roster_tonight", "form", "wins", "losses", "out"],
              [[i + 1, t, f"{tonight[t] + form(t):.1f}", f"{healthy[t]:.1f}", f"{tonight[t]:.1f}",
                f"{form(t):.1f}", record[t][0], record[t][1], "; ".join(notes[t])]
               for i, t in enumerate(power)])
    if new_log:
        exists = LOG_FILE.exists()
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "away", "home", "home_prob", "home_margin", "mode", "logged_at"])
            w.writerows(new_log)
        print(f"  locked {len(new_log)} new picks in {LOG_FILE}")

    done = [r for r in out_rows if r[11] != ""]
    for mode in ("backtest", "live"):
        m = [r for r in done if r[12] == mode]
        if m:
            print(f"  {mode}: {sum(r[11] == '1' for r in m)}-{sum(r[11] == '0' for r in m)}")
    print(f"\nTonight ({today}):")
    for r in out_rows:
        if r[0] == today.isoformat():
            p = float(r[7])
            print(f"  {r[2]} @ {r[3]}: pick {r[9]} ({max(p, 1 - p):.0%}, line {r[3]} {-float(r[8]):+.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="reuse the downloaded schedule and injuries")
    ap.add_argument("--full", action="store_true", help="re-download the whole BBRef schedule first")
    ap.add_argument("--date", help="treat this date (YYYY-MM-DD) as tonight")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else date.today()
    if not args.offline:
        if args.full or not SCHEDULE_FILE.exists():
            print("Downloading the season schedule from Basketball Reference...")
            fetch_schedule(today)
        print("Updating scores and injuries from ESPN...")
        try:
            update_scores_espn(today)
        except Exception as e:   # ESPN times out now and then; balldontlie has final scores
            api_key = bdl_key()
            if not api_key:
                raise
            print(f"  ESPN scores failed ({e}); using balldontlie")
            update_scores_bdl(today, api_key)
        try:
            fetch_injuries_espn()
        except Exception as e:   # ESPN changes its feeds now and then; balldontlie (paid key) or BBRef has the same list
            try:
                if not bdl_key():
                    raise ValueError("no balldontlie key")
                print(f"  ESPN injuries failed ({e}); using balldontlie")
                fetch_injuries_bdl(today, bdl_key())
            except Exception as e2:
                print(f"  balldontlie injuries unavailable ({e2}); using Basketball Reference")
                fetch_injuries()
    build(today)


if __name__ == "__main__":
    sys.exit(main())
