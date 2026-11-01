"""
NBA Contract Value - Weekend 1
Merges last season's advanced stats with this season's salaries and ranks
every contract by "surplus value": what a player's production is worth on
the open market minus what he's actually paid.

Inputs (put them in a folder called data/):
  data/advanced_2025_26.csv  - last season's advanced stats (needs Player, MP, WS)
  data/contracts.csv         - current contracts (needs Player and a 2026-27 salary column)
  data/advanced_2026_27.csv  - OPTIONAL: this season's advanced stats so far. When
                               present, adds a blended (both seasons) valuation.
  data/spotrac_cash_2026_27.csv - OPTIONAL: Spotrac team cash table (Team, Active,
                               Dead, Retained, Total Cash). Adds a team summary.

Raw Basketball Reference exports work as-is: lines wrapped in quotes (from
saving through Numbers/TextEdit) and extra rows above the headers are handled.

Run:  python contract_value.py
"""
import csv
import io
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import bref

STATS_FILE = "data/advanced_2025_26.csv"
CURRENT_STATS_FILE = "data/advanced_2026_27.csv"   # optional
SPOTRAC_CASH_FILE = "data/spotrac_cash_2026_27.csv"  # optional
SPOTRAC_TEAMS = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}   # Spotrac -> BRef codes
# First-round picks from these drafts are on rookie-scale deals in 2026-27
# (4-year scale; 2022 picks finished theirs in 2025-26). Pages cached by
# refresh.py in data/drafts/NBA_<year>.html.
ROOKIE_SCALE_DRAFTS = range(2023, 2027)
CONTRACTS_FILE = "data/contracts.csv"
SALARY_COL = "2026-27"   # this season's salary column in the contracts file
MIN_MINUTES = 500        # ignore players who barely played
PROJ_MAX_MINUTES = 3000  # cap on a full-season minutes projection
FIT_MIN_MINUTES = 1000   # price curves are fit on veterans with at least this many MP
MIN_DEAL_SALARY = 2_800_000   # at or below this a deal is minimum-type; left out of the fit
# Replacement-level pricing: a player is worth the league minimum plus a price
# per Win Share above what a freely available replacement (0.040 WS/48) would
# produce in his minutes. The price is set so total value equals total salary.
LEAGUE_MIN_SALARY = 1_357_763     # 2026-27 minimum, 0 years of service
REPLACEMENT_WS48 = 0.040
# Rate adjustments for the healthy, blended and trade-value lenses:
LEAGUE_AVG_WS48 = 0.100
SHRINK_MINUTES = 300    # rate shrinks toward average with weight MP / (MP + 300)
OFFSET_FADE_MINUTES = 2500   # position offset fades out linearly by this many minutes
SMALL_SAMPLE_MIN = 50    # 2026-27-only players need at least this many minutes

# Stats-file name -> contracts-file name, for genuine spelling differences.
ALIASES = {}


def normalize(name: str) -> str:
    """Make names matchable across sources: strip accents, periods, Jr./III, etc."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = name.lower().replace(".", "").replace("'", "")
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


def to_money(series: pd.Series) -> pd.Series:
    """'$45,000,000' -> 45000000.0"""
    return pd.to_numeric(series.astype(str).str.replace(r"[^\d.]", "", regex=True),
                         errors="coerce")


def read_bref_csv(path: str, header_col: str = "Player") -> pd.DataFrame:
    """Read a Basketball Reference export, cleaning up common copy/paste damage."""
    lines = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        # A whole line wrapped in one pair of quotes -> unwrap it.
        if len(line) >= 2 and line[0] == line[-1] == '"' and line.count('"') == 2:
            line = line[1:-1]
        if line:
            lines.append(line)
    # Skip anything above the real header (e.g. the ",,,Salary,Salary" row).
    header = next(i for i, l in enumerate(lines) if header_col in next(csv.reader([l])))
    return pd.read_csv(io.StringIO("\n".join(lines[header:])))


def load_stats(path: str) -> pd.DataFrame:
    stats = read_bref_csv(path)
    stats = stats[stats["Player"].notna()]
    stats = stats[~stats["Player"].isin(["Player", "League Average"])]   # drop repeated headers
    # Traded players have one row per team; the combined-season row comes first.
    stats = stats.drop_duplicates("Player", keep="first")
    for col in ["G", "MP", "WS", "VORP"]:
        if col in stats.columns:
            stats[col] = pd.to_numeric(stats[col], errors="coerce")
    stats["key"] = stats["Player"].replace(ALIASES).map(normalize)
    return stats.rename(columns={"Tm": "Team"})


# --- 1. Load stats -----------------------------------------------------------
stats = load_stats(STATS_FILE)
stats = stats[stats["MP"] >= MIN_MINUTES]

current = None
if Path(CURRENT_STATS_FILE).exists():
    current = load_stats(CURRENT_STATS_FILE)
    current = current.rename(columns={"G": "G_26-27", "MP": "MP_26-27", "WS": "WS_26-27",
                                      "Age": "Age_26-27"})
    current = current.rename(columns={"Pos": "Pos_26-27"})
    current = current[["key", "Player", "Age_26-27", "Pos_26-27", "G_26-27", "MP_26-27", "WS_26-27"]]

# --- 2. Load this season's salaries ------------------------------------------
con = read_bref_csv(CONTRACTS_FILE)
con = con[con["Player"].notna() & (con["Player"] != "Player")]
con["salary"] = to_money(con[SALARY_COL])
con["guaranteed"] = to_money(con["Guaranteed"])
con = con.dropna(subset=["salary"])
con = con.drop_duplicates(subset=[c for c in con.columns if c != "Rk"])   # exact repeats
con = con.rename(columns={"Tm": "Team"})               # current (2026-27) team
# Waived/bought-out players are listed once per team, each row repeating the
# old salary. The row with the smallest guarantee is the current team; the
# others are dead money on the old team's books.
con = con.sort_values("guaranteed")
split = con["Player"].duplicated(keep=False)
dead_money = con[split & con["Player"].duplicated(keep="first")]
con = con.drop_duplicates("Player", keep="first")
con["flag"] = con["Player"].isin(dead_money["Player"]).map({True: "split contract",
                                                             False: ""})
con["key"] = con["Player"].map(normalize)

rookie_keys = set()
for year in ROOKIE_SCALE_DRAFTS:
    draft_page = Path(f"data/drafts/NBA_{year}.html")
    if draft_page.exists():
        picks = bref.read_table(draft_page.read_text(encoding="utf-8"), "stats")
        rookie_keys |= {normalize(r["player"]) for r in picks
                        if r.get("pick_overall", "").isdigit() and int(r["pick_overall"]) <= 30}
con["rookie_scale"] = con["key"].isin(rookie_keys)

# --- 3. Merge ----------------------------------------------------------------
stats = stats.rename(columns={"Team": "2025-26 team"})
df = stats.merge(con[["key", "salary", "Team", "flag", "rookie_scale"]], on="key", how="inner")
unmatched = stats[~stats["key"].isin(con["key"])]

# --- 4. Value every contract -------------------------------------------------
# Old flat price (kept for reference in the printout): total salary / total WS.
dollars_per_ws = df["salary"].sum() / df["WS"].clip(lower=0).sum()
df["WS/48"] = df["WS"] / df["MP"] * 48
df["salary_m"] = df["salary"] / 1e6


def wins_above_replacement(ws: pd.Series, mp: pd.Series) -> pd.Series:
    return (ws - REPLACEMENT_WS48 * mp / 48).clip(lower=0)


# Price per Win Share above replacement, set on last season's actual production
price_per_war = ((df["salary"].sum() - len(df) * LEAGUE_MIN_SALARY)
                 / wins_above_replacement(df["WS"], df["MP"]).sum())


def market_value(ws: pd.Series, mp: pd.Series) -> pd.Series:
    """$ value of producing `ws` Win Shares in `mp` minutes."""
    return LEAGUE_MIN_SALARY + price_per_war * wins_above_replacement(ws, mp)


df["market_value_m"] = market_value(df["WS"], df["MP"]) / 1e6
df["surplus_m"] = df["market_value_m"] - df["salary_m"]

# Win Shares favor big men, so each position group's minutes-weighted WS/48 is
# shifted to the league average (offsets from last season's pool). The shift
# applies fully to bench players and fades to zero for 2,500-minute starters.
def position_group(pos: pd.Series) -> pd.Series:
    return pos.fillna("").astype(str).str.split("-").str[0]


league_ws48 = df["WS"].sum() / df["MP"].sum() * 48
groups = df.assign(group=position_group(df["Pos"])).groupby("group")[["WS", "MP"]].sum()
POSITION_OFFSET = (league_ws48 - groups["WS"] / groups["MP"] * 48).to_dict()


def adjusted_rate(ws: pd.Series, mp: pd.Series, pos: pd.Series) -> pd.Series:
    """Position-normalized WS/48, shrunk toward average for small samples."""
    fade = (1 - mp / OFFSET_FADE_MINUTES).clip(lower=0, upper=1)
    rate = ws / mp * 48 + position_group(pos).map(POSITION_OFFSET).fillna(0) * fade
    weight = mp / (mp + SHRINK_MINUTES)
    return weight * rate + (1 - weight) * LEAGUE_AVG_WS48

# Healthy view: project each player to all 82 games at his own minutes per
# game, so injured starters get full credit while low-minute backups stay
# modest. This separates "missed time" from "played badly".
def project_minutes(mp: pd.Series, g: pd.Series) -> pd.Series:
    full = (mp / g * 82).clip(upper=PROJ_MAX_MINUTES)
    return full.where(g < 82, mp).combine(mp, max)


df["proj_MP"] = project_minutes(df["MP"], df["G"])
df["rate_ws48"] = adjusted_rate(df["WS"], df["MP"], df["Pos"])
df["healthy_ws"] = df["rate_ws48"] * df["proj_MP"] / 48
df["healthy_value_m"] = market_value(df["healthy_ws"], df["proj_MP"]) / 1e6
df["healthy_surplus_m"] = df["healthy_value_m"] - df["salary_m"]



# Market curve: stars cost more per Win Share than role players. Fit
# salary = a * stat^b on veteran deals (no rookie-scale or minimum contracts),
# then rescale so the pool's total value equals its total salary.
def fit_price_curve(stat: str):
    vets = df[~df["rookie_scale"] & (df["salary"] > MIN_DEAL_SALARY)
              & (df["MP"] >= FIT_MIN_MINUTES) & (df[stat] > 0)]
    b = np.polyfit(np.log(vets[stat]), np.log(vets["salary"]), 1)[0]
    scale = df["salary"].sum() / (df[stat].clip(lower=0) ** b).sum()
    return b, len(vets), lambda x: scale * x.clip(lower=0) ** b


ws_b, ws_n, ws_price = fit_price_curve("WS")
vorp_b, vorp_n, vorp_price = fit_price_curve("VORP")
df["value_new_m"] = ws_price(df["WS"]) / 1e6
df["surplus_new_m"] = df["value_new_m"] - df["salary_m"]
df["healthy_new_m"] = ws_price(df["healthy_ws"]) / 1e6 - df["salary_m"]
df["vorp_surplus_m"] = vorp_price(df["VORP"]) / 1e6 - df["salary_m"]

cols = ["Player", "Team", "2025-26 team", "G", "MP", "proj_MP", "WS", "WS/48", "VORP",
        "salary_m", "market_value_m", "surplus_m", "healthy_surplus_m",
        "value_new_m", "surplus_new_m", "healthy_new_m", "vorp_surplus_m",
        "rookie_scale", "flag"]

# Blended view: pool both seasons' minutes, so 2026-27 counts for more as the
# season goes on. Players new to the pool (rookies, <500 MP last season) are
# valued on 2026-27 alone and flagged.
if current is not None:
    df = df.merge(current.drop(columns="Player"), on="key", how="left")
    new = current[~current["key"].isin(df["key"]) & (current["MP_26-27"] >= SMALL_SAMPLE_MIN)]
    new = new.merge(con[["key", "salary", "Team", "flag", "rookie_scale"]], on="key", how="inner")
    new["salary_m"] = new["salary"] / 1e6
    new["flag"] = (new["flag"] + ", small sample").str.lstrip(", ")
    df = pd.concat([df, new], ignore_index=True)

    df["WS/48_26-27"] = df["WS_26-27"] / df["MP_26-27"] * 48
    both_ws = df["WS"].fillna(0) + df["WS_26-27"].fillna(0)
    both_mp = df["MP"].fillna(0) + df["MP_26-27"].fillna(0)
    df["blended_WS/48"] = both_ws / both_mp * 48
    df["proj_MP"] = df["proj_MP"].fillna(project_minutes(df["MP_26-27"], df["G_26-27"]))
    df["rate_ws48"] = adjusted_rate(both_ws, both_mp, df["Pos"].fillna(df["Pos_26-27"]))
    blended_ws = df["rate_ws48"] * df["proj_MP"] / 48
    df["blended_surplus_m"] = market_value(blended_ws, df["proj_MP"]) / 1e6 - df["salary_m"]
    df["blended_new_m"] = ws_price(blended_ws) / 1e6 - df["salary_m"]
    df["change_m"] = df["blended_surplus_m"] - df["healthy_surplus_m"]
    cols[-2:-2] = ["G_26-27", "WS/48_26-27", "blended_surplus_m", "blended_new_m"]

df = df.sort_values("surplus_m", ascending=False)
last_season = df[df["surplus_m"].notna()]


def show(title: str, frame: pd.DataFrame) -> None:
    out = frame[cols].copy().round(1)
    for col in ["G", "MP", "proj_MP", "G_26-27"]:
        if col in out:
            out[col] = frame[col].map(lambda x: "" if pd.isna(x) else f"{x:.0f}")
    for col in ["WS/48", "WS/48_26-27"]:
        if col in out:
            out[col] = frame[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    print(f"\n{title}")
    print(out.astype(object).fillna("").to_string(index=False))


# --- 5. Output ---------------------------------------------------------------
pd.set_option("display.width", 200)
print(f"\nPlayers matched: {len(last_season)}   |   Price per Win Share above replacement: "
      f"${price_per_war / 1e6:.2f}M (league minimum ${LEAGUE_MIN_SALARY / 1e6:.2f}M + that; "
      f"old flat price ${dollars_per_ws / 1e6:.2f}M/WS)")
print("Position offsets to WS/48: " + ", ".join(f"{g or '?'} {o:+.3f}" for g, o in POSITION_OFFSET.items()))
Path("outputs").mkdir(exist_ok=True)
Path("outputs/pricing.json").write_text(json.dumps({
    "price_per_war": price_per_war, "league_min_salary": LEAGUE_MIN_SALARY,
    "replacement_ws48": REPLACEMENT_WS48}, indent=2))
print(f"Market curve (WS): salary ~ WS^{ws_b:.2f}, fit on {ws_n} veteran deals. "
      f"1st Win Share ${ws_price(pd.Series([1.0]))[0] / 1e6:.2f}M, "
      f"10th ${(ws_price(pd.Series([10.0])) - ws_price(pd.Series([9.0])))[0] / 1e6:.2f}M")
print(f"Market curve (VORP): salary ~ VORP^{vorp_b:.2f}, fit on {vorp_n} veteran deals")
show("BEST CONTRACTS (most surplus value, $M)", last_season.head(15))
show("WORST CONTRACTS (most overpaid, $M)", last_season.tail(15).iloc[::-1])
show("MOST OVERPAID EVEN WHEN HEALTHY (projected to 82 games at own MP/G, $M)",
     last_season.sort_values("healthy_surplus_m").head(15))

new_rank = last_season.sort_values("surplus_new_m", ascending=False)
show("BEST CONTRACTS, MARKET CURVE (surplus_new, $M)", new_rank.head(10))
show("WORST CONTRACTS, MARKET CURVE (surplus_new, $M)", new_rank.tail(10).iloc[::-1])

ranks = last_season[["surplus_new_m", "vorp_surplus_m"]].rank(ascending=False)
print(f"\nWS vs VORP surplus rank correlation (Spearman): "
      f"{ranks['surplus_new_m'].corr(ranks['vorp_surplus_m']):.3f}")
gap = (ranks["surplus_new_m"] - ranks["vorp_surplus_m"]).abs().sort_values(ascending=False)
disagree = last_season.loc[gap.index[:10]].assign(
    ws_rank=ranks["surplus_new_m"], vorp_rank=ranks["vorp_surplus_m"])
print("BIGGEST WS vs VORP DISAGREEMENTS (rank 1 = best contract)")
print(disagree[["Player", "Team", "WS", "VORP", "salary_m", "surplus_new_m", "vorp_surplus_m",
                "ws_rank", "vorp_rank"]].round(1).to_string(index=False))

if current is not None:
    print(f"\n2026-27 stats loaded: {current['MP_26-27'].notna().sum()} players, "
          f"up to {int(current['G_26-27'].max())} games. Early-season numbers are noisy.")
    blended = df.sort_values("blended_surplus_m", ascending=False)
    show("BEST CONTRACTS, BLENDED 2025-26 + 2026-27 ($M)", blended.head(10))
    show("WORST CONTRACTS, BLENDED 2025-26 + 2026-27 ($M)", blended.tail(10).iloc[::-1])
    movers = df[df["change_m"].notna()]
    movers = movers.reindex(movers["change_m"].abs().sort_values(ascending=False).index)
    show("BIGGEST MOVERS (blended surplus vs last-season healthy surplus, $M)",
         movers.head(15))
    rookies = df[df["flag"].str.contains("small sample")]
    if len(rookies):
        print(f"\n{len(rookies)} players valued on 2026-27 only (small sample).")

Path("outputs").mkdir(exist_ok=True)
df[cols].round(3).to_csv("outputs/contract_value.csv", index=False)
print("\nSaved full list to outputs/contract_value.csv")

# Inputs for trade_value.py: production rate, minutes, age and the full
# remaining contract (salary per season) for every valued player.
CONTRACT_YEARS = ["2026-27", "2027-28", "2028-29", "2029-30", "2030-31", "2031-32"]
contract_years = con[["key"] + CONTRACT_YEARS].copy()
for col in CONTRACT_YEARS:
    contract_years[col] = to_money(contract_years[col]) / 1e6
model_cols = ["Player", "Team", "Age", "MP", "proj_MP", "WS/48", "blended_WS/48", "rate_ws48",
              "Age_26-27", "MP_26-27", "WS/48_26-27", "rookie_scale", "flag"]
df[["key"] + [c for c in model_cols if c in df]].merge(contract_years, on="key").drop(
    columns="key").to_csv("outputs/player_inputs.csv", index=False)
# Every contract with its current team (split contracts resolved), for trade.py
con.assign(option_years=con.get("Options", pd.Series("", index=con.index)).fillna(""))[
    ["Player", "Team"] + CONTRACT_YEARS + ["option_years", "flag"]].assign(
    **{y: contract_years[y] for y in CONTRACT_YEARS}).to_csv("outputs/contracts_clean.csv",
                                                             index=False)

split_detail = dead_money[["Player", "Team", "salary", "guaranteed"]]
split_detail.columns = ["Player", "Old team", f"{SALARY_COL} listed", "guaranteed"]
split_detail = split_detail.astype({f"{SALARY_COL} listed": "int64", "guaranteed": "int64"})
split_detail.to_csv("outputs/split_contracts.csv", index=False)

# --- 6. Team summary ---------------------------------------------------------
if Path(SPOTRAC_CASH_FILE).exists():
    cash = read_bref_csv(SPOTRAC_CASH_FILE, header_col="Team")
    cash["Team"] = cash["Team"].replace(SPOTRAC_TEAMS)
    for col in ["Active", "Dead", "Retained", "Total Cash"]:
        cash[col] = to_money(cash[col]) / 1e6

    # Flat $/WS is the default; market-curve (*_new_m) totals are kept for comparison.
    sort_col = "blended_surplus_m" if current is not None else "healthy_surplus_m"
    df["ex_rookie_m"] = df[sort_col].where(~df["rookie_scale"].astype(bool), 0)
    surplus_cols = [c for c in ["surplus_m", "healthy_surplus_m", "blended_surplus_m",
                                "ex_rookie_m", "surplus_new_m", "healthy_new_m",
                                "blended_new_m", "vorp_surplus_m"] if c in df]
    ranked = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=False)
    teams = ranked.groupby("Team").agg(
        players=("Player", "size"),
        best=("Player", "first"),
        worst=("Player", "last"),
        **{c: (c, "sum") for c in surplus_cols})
    teams = cash.set_index("Team")[["Active", "Dead", "Retained", "Total Cash"]].join(teams)
    teams.columns = ["active_m", "dead_m", "retained_m", "total_cash_m", "players",
                     "best_contract", "worst_contract"] + [f"team_{c}" for c in surplus_cols]
    rookie_counts = ranked[ranked["rookie_scale"].astype(bool)].groupby("Team").size()
    teams.insert(5, "rookie_scale_players", rookie_counts.reindex(teams.index, fill_value=0))
    teams["net_m"] = teams[f"team_{sort_col}"] - teams["dead_m"]
    teams = teams.sort_values("net_m", ascending=False).round(1)
    teams.index.name = "Team"
    teams.to_csv("outputs/team_summary.csv")
    print(f"\nTEAM SUMMARY (ranked by total {sort_col.replace('_m', '')} minus "
          f"dead money, $M; cash from Spotrac)")
    print(teams.to_string())
    print("Saved team summary to outputs/team_summary.csv")

    dead = teams[["dead_m"]].copy()
    dead["split_contract_players"] = dead.index.map(
        lambda t: ", ".join(split_detail.loc[split_detail["Old team"] == t, "Player"]))
    dead.sort_values("dead_m", ascending=False).to_csv("outputs/dead_money.csv")
    print("Saved Spotrac team dead money to outputs/dead_money.csv "
          "(per-player split contracts in outputs/split_contracts.csv)")

if len(unmatched):
    print(f"\nNo {SALARY_COL} contract in the contracts file ({len(unmatched)} players "
          f"with {MIN_MINUTES}+ MP: free agents, two-way, overseas or retired):")
    print(", ".join(unmatched.sort_values("MP", ascending=False)["Player"]))
