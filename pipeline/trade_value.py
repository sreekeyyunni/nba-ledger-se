"""
Trade value of every contract, plus each team's cap status. Run after
contract_value.py (refresh.py runs both).

Trade value = the surplus a contract produces over all its remaining years:
  sum over years t of (projected Win Shares x price per WS - salary) / 1.08^t
with t = 0 for 2026-27.

Assumptions (change them here):
- Every listed salary year is treated as owed. The contracts table doesn't
  mark player/team options, so option years count as guaranteed.
- Starting production rate is contract_value.py's rate_ws48: blended
  (2025-26 + 2026-27) WS/48, position-normalized and shrunk toward league
  average with weight MP/(MP+1000).
- Minutes are the healthy projection (82 games at own MP/G), capped at 3000.
- Aging changes WS/48 each future year by the AGING table, using the player's
  age in that season. From age 32, minutes fall 4% a year. WS/48 floors at 0.
- Value each season = league minimum + price x Win Shares above replacement
  (0.040 WS/48), with the minimum and price from contract_value.py
  (outputs/pricing.json), both growing 7% a year with the salary cap.
- Future years are discounted 8% a year.

Outputs: outputs/trade_values.csv and outputs/team_cap.csv
"""
from pathlib import Path

import json
from pathlib import Path

import pandas as pd

PRICING = json.loads(Path("outputs/pricing.json").read_text())
PRICE_PER_WAR_M = PRICING["price_per_war"] / 1e6
LEAGUE_MIN_M = PRICING["league_min_salary"] / 1e6
REPLACEMENT_WS48 = PRICING["replacement_ws48"]
PRICE_GROWTH = 0.07           # salary cap growth per year
DISCOUNT_RATE = 0.08
MAX_MINUTES = 3000
MINUTES_DECLINE_AGE = 32
MINUTES_DECLINE = 0.04
AGING = [   # (max age, WS/48 change per year)
    (22, +0.010), (24, +0.006), (27, 0.0), (30, -0.006), (33, -0.012), (200, -0.018),
]
YEARS = ["2026-27", "2027-28", "2028-29", "2029-30", "2030-31", "2031-32"]

# Official 2026-27 thresholds, NBA announcement (pr.nba.com/2026-27-salary-cap), $M
CAP_M, TAX_M, APRON1_M, APRON2_M = 164.961, 200.428, 209.015, 221.686
SPOTRAC_TEAMS = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}


def aging_step(age: float) -> float:
    return next(step for max_age, step in AGING if age <= max_age)


def project(row: pd.Series) -> dict:
    rate = row["rate_ws48"]
    minutes = min(row["proj_MP"], MAX_MINUTES)
    age = row["Age"] + 1 if pd.notna(row["Age"]) else row["Age_26-27"]

    out = {"Age": age, "years_left": 0, "total_salary_m": 0.0, "trade_value_m": 0.0}
    for t, year in enumerate(YEARS):
        if t > 0:
            season_age = age + t
            rate = max(rate + aging_step(season_age), 0.0)
            if season_age >= MINUTES_DECLINE_AGE:
                minutes *= 1 - MINUTES_DECLINE
        salary = row[year]
        if pd.isna(salary):
            out[f"sv_y{t + 1}"] = None
            continue
        war = max(rate - REPLACEMENT_WS48, 0) * minutes / 48
        value = (LEAGUE_MIN_M + PRICE_PER_WAR_M * war) * (1 + PRICE_GROWTH) ** t
        surplus = value - salary
        out[f"sv_y{t + 1}"] = surplus
        out["years_left"] += 1
        out["total_salary_m"] += salary
        out["trade_value_m"] += surplus / (1 + DISCOUNT_RATE) ** t
    return out


def main() -> None:
    players = pd.read_csv("outputs/player_inputs.csv")
    values = players.apply(project, axis=1, result_type="expand")
    trade = pd.concat([players[["Player", "Team"]], values,
                       players[["2026-27", "rookie_scale", "flag"]]], axis=1)
    trade = trade.rename(columns={"2026-27": "salary_2026_27_m"})
    trade = trade[["Player", "Team", "Age", "years_left", "total_salary_m", "salary_2026_27_m",
                   "trade_value_m"] + [f"sv_y{i}" for i in range(1, 7)] + ["rookie_scale", "flag"]]
    trade = trade.sort_values("trade_value_m", ascending=False)
    trade.round(2).to_csv("outputs/trade_values.csv", index=False)

    pd.set_option("display.width", 200)
    show = ["Player", "Team", "Age", "years_left", "total_salary_m", "trade_value_m", "flag"]
    print(f"TRADE VALUE (min ${LEAGUE_MIN_M:.2f}M + ${PRICE_PER_WAR_M:.2f}M per WS above "
          f"replacement, growing {PRICE_GROWTH:.0%}/yr, "
          f"discounted {DISCOUNT_RATE:.0%}/yr, $M)")
    print("\nMOST VALUABLE CONTRACTS")
    print(trade[show].head(15).round(1).to_string(index=False))
    print("\nLEAST VALUABLE CONTRACTS")
    print(trade[show].tail(15).iloc[::-1].round(1).to_string(index=False))
    print(f"\nSaved {len(trade)} players to outputs/trade_values.csv")

    # --- Team cap status (payroll = Spotrac total cash) ----------------------
    cash = pd.read_csv("data/spotrac_cash_2026_27.csv")
    cap = pd.DataFrame({"Team": cash["Team"].replace(SPOTRAC_TEAMS),
                        "payroll_m": (cash["Total Cash"] / 1e6).round(2),
                        "cap_m": CAP_M, "tax_m": TAX_M, "apron1_m": APRON1_M, "apron2_m": APRON2_M})
    cap["status"] = pd.cut(cap["payroll_m"], [0, CAP_M, TAX_M, APRON1_M, APRON2_M, 1e9],
                           labels=["under cap", "over cap", "over tax", "over 1st apron",
                                   "over 2nd apron"]).astype(str)
    cap.sort_values("payroll_m", ascending=False).to_csv("outputs/team_cap.csv", index=False)
    print("\nTEAM CAP STATUS (Spotrac total cash vs official 2026-27 thresholds)")
    print(cap["status"].value_counts().to_string())
    print("Saved outputs/team_cap.csv")


if __name__ == "__main__":
    main()
