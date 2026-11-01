"""
Value adjustments on top of the Mac's contract model: python adjust.py [data dir]

1. Star credit. A plain price-per-win model calls most max-contract stars overpaid,
   because box-score win shares undersell high-usage scorers. Stars whose play or
   honors back it up get part of that overpay forgiven, every season of the deal:
   - tier 2: All-NBA in the last two seasons (data/accolades.csv) or top 10 in VORP
     last season: 75% of any overpay forgiven
   - tier 1: top 25 in VORP last season: 40% forgiven
   Players who already grade as good value are unchanged.
2. Injury time. A reported timeline ("out two months", "season-ending", see injury.py)
   takes the games he'll miss out of his 2026-27 value: the "Healthy + 2026-27" lens,
   year 1 of his trade value and his team's totals. "If healthy" stays as it is.

The Mac's weekly refresh writes the unadjusted files. The first run after that saves
them to pipeline/data/raw/, and every run adjusts from those copies, so running this
twice changes nothing and new injury news replaces old.
"""
import csv
import shutil
import sys
from datetime import date
from pathlib import Path

from injury import games_out

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else "../data")
RAW = Path(__file__).parent / "data" / "raw"
INJURIES = Path(__file__).parent / "data" / "injuries.csv"
SEASON_GAMES = 82
DISCOUNT = 1.08                     # trade_value_m discounts each later season by 8%
FORGIVE = {2: 0.75, 1: 0.40}
MIN_GAMES = 30                      # last-season games to count in the VORP ranks
MARKER = {"contract_value.csv": "star_tier", "trade_values.csv": "star_m", "team_summary.csv": "adj_net_m"}

# surplus column -> value column that moves with it
SURPLUS = {"surplus_m": "market_value_m", "healthy_surplus_m": None, "blended_surplus_m": None,
           "surplus_new_m": "value_new_m", "healthy_new_m": None, "blended_new_m": None, "vorp_surplus_m": None}
TEAM = {"surplus_m": "team_surplus_m", "healthy_surplus_m": "team_healthy_surplus_m",
        "blended_surplus_m": "team_blended_surplus_m", "surplus_new_m": "team_surplus_new_m",
        "healthy_new_m": "team_healthy_new_m", "blended_new_m": "team_blended_new_m",
        "vorp_surplus_m": "team_vorp_surplus_m"}


def read(name):
    """The unadjusted rows: a fresh file from the Mac, or the saved raw copy."""
    path, raw = DATA / name, RAW / name
    with open(path, newline="") as f:
        header = next(csv.reader(f))
    if MARKER[name] not in header:
        RAW.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, raw)
    with open(raw, newline="") as f:
        return list(csv.DictReader(f))


def write(name, rows, extra):
    cols = [c for c in rows[0] if c not in extra] + extra
    with open(DATA / name, "w", newline="") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def fmt(x):
    return f"{x:.3f}".rstrip("0").rstrip(".") if x else "0"


def forgive(s, share):
    return s + share * -s if s < 0 else s


def main(today=None):
    today = today or date.today()
    players = read("contract_value.csv")
    trades = read("trade_values.csv")
    teams = read("team_summary.csv")

    honored = set()
    if (DATA / "accolades.csv").exists():
        seasons = {"2024-25", "2025-26"}
        honored = {r["Player"] for r in csv.DictReader(open(DATA / "accolades.csv"))
                   if r["season"] in seasons and r["honor"].startswith("All-NBA")}
    ranked = sorted((p for p in players if num(p["G"]) >= MIN_GAMES), key=lambda p: -num(p["VORP"]))
    vorp_rank = {p["Player"]: i + 1 for i, p in enumerate(ranked)}

    out = {}
    if INJURIES.exists():
        for r in csv.DictReader(open(INJURIES)):
            if r.get("updated", "") < "2026-07-01":
                continue
            g = games_out(r["note"], r.get("updated", ""), today)
            if g:
                out[r["player"]] = (g, r["note"].split(" - ", 1)[-1])

    team_delta = {}
    by_player = {}
    for p in players:
        name, rank = p["Player"], vorp_rank.get(p["Player"], 999)
        raw_blended = num(p["blended_surplus_m"])
        tier = 2 if name in honored or rank <= 10 else 1 if rank <= 25 else 0
        star_m = 0.0
        for col, val_col in SURPLUS.items():
            before = num(p[col])
            after = forgive(before, FORGIVE[tier]) if tier else before
            p[col] = fmt(round(after, 3))
            if val_col:
                p[val_col] = fmt(round(num(p[val_col]) + after - before, 3))
            if col == "healthy_surplus_m":
                star_m = after - before
            team_delta.setdefault(p["Team"], {}).setdefault(col, 0.0)
            team_delta[p["Team"]][col] += after - before
        games, note = out.get(name, (0, ""))
        inj = 0.0
        if games:
            share = games / SEASON_GAMES
            for col in ("blended_surplus_m", "blended_new_m"):
                lost = share * max(0.0, num(p[col]) + num(p["salary_m"]))
                p[col] = fmt(round(num(p[col]) - lost, 3))
                team_delta[p["Team"]][col] += -lost
                if col == "blended_surplus_m":
                    inj = lost
        if p.get("rookie_scale") == "False":
            d = team_delta[p["Team"]]
            d["ex_rookie"] = d.get("ex_rookie", 0.0) + (num(p["blended_surplus_m"]) - raw_blended)
        p.update(star_tier=str(tier), star_m=fmt(round(star_m, 2)), games_out=str(games),
                 injury_m=fmt(round(inj, 2)), injury_note=note)
        by_player[(name, p["Team"])] = (tier, games)
    write("contract_value.csv", players, ["star_tier", "star_m", "games_out", "injury_m", "injury_note"])

    for t in trades:
        tier, games = by_player.get((t["Player"], t["Team"]), (0, 0))
        tv, star, inj = num(t["trade_value_m"]), 0.0, 0.0
        for i in range(6):
            col = f"sv_y{i + 1}"
            if t.get(col, "") == "":
                continue
            before = num(t[col])
            after = forgive(before, FORGIVE[tier]) if tier else before
            if i == 0 and games:
                lost = games / SEASON_GAMES * max(0.0, after + num(t["salary_2026_27_m"]))
                after -= lost
                inj = lost
            star += (forgive(before, FORGIVE[tier]) - before if tier else 0.0) / DISCOUNT ** i
            tv += (after - before) / DISCOUNT ** i
            t[col] = fmt(round(after, 2))
        t["trade_value_m"] = fmt(round(tv, 2))
        t.update(star_m=fmt(round(star, 2)), injury_m=fmt(round(inj, 2)))
    write("trade_values.csv", trades, ["star_m", "injury_m"])

    for r in teams:
        d = team_delta.get(r["Team"], {})
        for col, tcol in TEAM.items():
            r[tcol] = f'{num(r[tcol]) + d.get(col, 0.0):.1f}'
        r["team_ex_rookie_m"] = f'{num(r["team_ex_rookie_m"]) + d.get("ex_rookie", 0.0):.1f}'
        net = d.get("blended_surplus_m", 0.0)
        r["net_m"] = f'{num(r["net_m"]) + net:.1f}'
        r["adj_net_m"] = f"{net:.1f}"
    write("team_summary.csv", teams, ["adj_net_m"])

    # positions for Guess the Player (this season's listing, else last season's)
    pos = {}
    for f in ("advanced_2026_27.csv", "advanced_2025_26.csv"):
        path = Path(__file__).parent / "data" / f
        for r in csv.DictReader(open(path)) if path.exists() else []:
            if r.get("Pos") and r["Player"] not in pos:
                pos[r["Player"]] = r["Pos"]
    if pos:
        with open(DATA / "positions.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["Player", "Pos"])
            w.writerows(sorted(pos.items()))

    stars = sum(1 for v in by_player.values() if v[0])
    hurt = sum(1 for v in by_player.values() if v[1])
    print(f"  adjusted {DATA}: star credit for {stars} players, injury time for {hurt}")


if __name__ == "__main__":
    main()
