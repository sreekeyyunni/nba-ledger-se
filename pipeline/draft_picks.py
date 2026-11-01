"""
Future draft pick ownership and value. Run after contract_value.py and
trade_value.py (refresh.py runs all three).

Ownership comes from Spotrac's future picks page, captured once into
data/picks/spotrac_future_raw.txt (Spotrac blocks scripts; ask Claude to
re-capture it). Each pick has exactly one row from its owner's side of the
page, which is the one used here.

Pricing (change the constants below):
- Slot value: value(slot) = A * exp(-B * slot) + C, refit every run on the
  2023-2025 first-round picks' current trade value (players who never earned a
  trade value count as $0, so busts aren't left out). Second-rounders are a
  flat value: their average outcome is skewed by a few hits (median $0), so
  it's capped at 35% of the #30 pick.
- Expected slot: each team's strength is the projected Win Shares of its
  current roster (blended healthy rate x projected minutes, top 19,680 minutes,
  about one season of team minutes); that's roughly a win total. Each year after
  2027 regresses 35% further toward average. Seasons are simulated with noise
  and the 2019 lottery odds (bottom 14, four drawings), giving every team a
  probability for each slot.
- Protections: the receiver only gets the pick in its slot range; outside it
  the pick stays with the original team. Picks that depend on an earlier pick
  not conveying ("if not already settled", "does not convey") are valued at 50%.
- Swaps: the swap holder gains E[max(0, value(other slot) - value(own slot))]
  and the other team loses the same.
- Pool picks ("most/least favorable of A, B and C"): valued at the expected
  value of that order statistic across the named teams' slots. Slot limits
  inside a pool (e.g. "MIN 6-30") are ignored, which the notes say.
- Discount 8% a year from 2026-27.
Output: outputs/draft_picks.csv, plus pick_value_m added to outputs/team_summary.csv.
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import bref

FIT_DRAFTS = range(2023, 2026)   # 2026 rookies are too new to judge
SECOND_ROUND_SHARE = 0.35        # second-rounders: this share of the #30 pick
DISCOUNT_RATE = 0.08
REGRESS_PER_YEAR = 0.35
WIN_SD, WIN_SD_GROWTH = 7.0, 3.0   # wins noise in 2027, extra per later year
TEAM_MINUTES = 19_680
LEAGUE_AVG_WS48 = 0.100
SIMS = 5000
CONDITIONAL_FACTOR = 0.5
LOTTERY_COMBOS = [140, 140, 140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 10, 5]   # 2019 odds
YEARS = range(2027, 2034)
ALIASES = {"PHL": "PHI", "GOS": "GSW", "UTH": "UTA", "SAN": "SAS", "BRK": "BKN"}
TO_BREF = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
FROM_BREF = {v: k for k, v in TO_BREF.items()}
RAW_FILE = "data/picks/spotrac_future_raw.txt"


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name.lower().replace(".", "").replace("'", ""))
    return re.sub(r"\s+", " ", name).strip()


def fit_slot_curve() -> tuple[float, float, float, int]:
    """Least squares fit of trade value = A * exp(-B * pick) + C on recent first-rounders."""
    picks = [(int(r["pick_overall"]), normalize(r["player"])) for year in FIT_DRAFTS
             for r in bref.read_table(Path(f"data/drafts/NBA_{year}.html").read_text(encoding="utf-8"), "stats")
             if r.get("pick_overall", "").isdigit() and int(r["pick_overall"]) <= 30]
    values = pd.read_csv("outputs/trade_values.csv")
    values = dict(zip(values["Player"].map(normalize), values["trade_value_m"]))
    x = np.array([p for p, _ in picks], dtype=float)
    y = np.array([values.get(k, 0.0) for _, k in picks])
    best = None
    for b in np.arange(0.01, 0.6, 0.005):
        design = np.c_[np.exp(-b * x), np.ones_like(x)]
        (a, c), *_ = np.linalg.lstsq(design, y, rcond=None)
        sse = ((design @ [a, c] - y) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, a, b, c)
    return best[1], best[2], best[3], len(x)


SLOT_A, SLOT_B, SLOT_C, SLOT_N = fit_slot_curve()
SECOND_ROUND_M = round(SECOND_ROUND_SHARE * (SLOT_A * np.exp(-SLOT_B * 30) + SLOT_C), 2)


def slot_value(slot: np.ndarray) -> np.ndarray:
    return np.where(slot <= 30, SLOT_A * np.exp(-SLOT_B * slot) + SLOT_C, SECOND_ROUND_M)


def team_strength() -> pd.Series:
    """Projected wins (Win Shares) for 2026-27 from each current roster."""
    p = pd.read_csv("outputs/player_inputs.csv")
    p["rate"] = p["rate_ws48"].fillna(LEAGUE_AVG_WS48)   # position-normalized, shrunk
    p["mins"] = p["proj_MP"].clip(upper=3000)
    wins = {}
    for team, roster in p.sort_values("mins", ascending=False).groupby("Team"):
        mins = roster["mins"].clip(upper=(TEAM_MINUTES - roster["mins"].cumsum().shift(fill_value=0)).clip(lower=0))
        wins[FROM_BREF.get(team, team)] = (roster["rate"] * mins / 48).sum()
    return pd.Series(wins)


def simulate_slots(strength: pd.Series, rng: np.random.Generator) -> dict[int, pd.DataFrame]:
    """For each draft year, a SIMS x teams array of draft slots (1-30)."""
    teams, mean = list(strength.index), strength.mean()
    combos = np.array(LOTTERY_COMBOS, dtype=float)
    out = {}
    for i, year in enumerate(YEARS):
        proj = mean + (strength.values - mean) * (1 - REGRESS_PER_YEAR) ** i
        wins = proj + rng.normal(0, WIN_SD + WIN_SD_GROWTH * i, (SIMS, len(teams)))
        order = np.argsort(wins + rng.random(wins.shape) * 1e-6, axis=1)   # worst first
        slots = np.empty_like(order)
        for s in range(SIMS):
            lottery, rest = list(order[s, :14]), list(order[s, 14:])
            weights, picked = combos.copy(), []
            for _ in range(4):
                k = rng.choice(len(lottery), p=weights / weights.sum())
                picked.append(lottery.pop(k))
                weights = np.delete(weights, k)
            for slot, team in enumerate(picked + lottery + rest, start=1):
                slots[s, team] = slot
        out[year] = pd.DataFrame(slots, columns=teams)
    return out


def parse_teams(text: str) -> list[str]:
    head = re.split(r"\bthen\b|\bto [A-Z]{3}\b|\(via|·", text)[0]
    found = [ALIASES.get(t, t) for t in re.findall(r"\b[A-Z]{3}\b", head)]
    return list(dict.fromkeys(found))


def pool_rank(text: str, n: int) -> list[int] | None:
    """Which order statistics (0 = best slot) a pool pick receives."""
    t = text.lower()
    table = [("most and least favorable", [0, n - 1]), ("two most favorable", [0, 1]),
             ("two least favorable", [n - 2, n - 1]), ("second most favorable", [1]),
             ("third most favorable", [2]), ("middle pick", [n // 2]),
             ("most favorable", [0]), ("more favorable", [0]),
             ("least favor", [n - 1]), ("less favorable", [n - 1])]
    return next((ranks for phrase, ranks in table if phrase in t), None)


def main() -> None:
    rng = np.random.default_rng(2027)
    strength = team_strength()
    slots = simulate_slots(strength, rng)

    raw = [line.rstrip("\n").split("|") for line in open(RAW_FILE, encoding="utf-8")
           if not line.startswith("#")]
    canon = [r for r in raw if r[3] in "OC"]
    rows, swaps = [], {}
    for year_s, orig, rnd_s, _, rights_s, desc in canon:
        year, rnd = int(year_s), int(rnd_s)
        rights = [ALIASES.get(r.strip(), r.strip()) for r in rights_s.split(",")]
        disc = (1 + DISCOUNT_RATE) ** (year - 2026)
        own_slots = slots[year][orig].values + (30 if rnd == 2 else 0)
        base = dict(year=year, round=rnd, original_team=orig, protection="", swap_with="",
                    exp_slot=round(own_slots.mean(), 1), notes=desc)

        def add(owner, mask, value, protection="", factor=1.0, note=None):
            rows.append({**base, "pick_id": f"{year}-{orig}-R{rnd}" + ("" if owner == rights[0] else f"-{owner}"),
                         "owner": owner, "protection": protection,
                         "p_conveys": round(mask.mean(), 3),
                         "value_m": round(factor * value / disc, 2),
                         "notes": note if note is not None else desc})

        if "FORFEIT" in desc:
            add(rights[0], np.zeros(SIMS, bool), 0.0, note="Forfeited pick (no value)")
            continue
        factor = CONDITIONAL_FACTOR if re.search(r"not already settled|does not convey", desc) else 1.0
        ranges = [tuple(map(int, m)) if m[1] else (int(m[0]), int(m[0]))
                  for m in re.findall(r"(?:If|·)\s*(?:[A-Z]{3}\s)?(\d+)(?:-(\d+))?", desc)]
        swap = re.search(r"via (\w{3}) swap (?:for|with) (\w{3})", desc)
        if swap and "favorable" not in desc.split("(via")[0].lower():
            holder, other = (ALIASES.get(t, t) for t in swap.groups())
            key = (year, rnd, frozenset((holder, other)))
            if key not in swaps and holder != other:
                swaps[key] = (year, rnd, holder, other, desc)
            first = ranges[0] if desc.startswith("If") and ranges else None
            if first:   # e.g. "If 1 · Or swap 2-30": swap only applies outside the protected range
                swaps[key] = (year, rnd, holder, other, desc, first)
            vals = slot_value(own_slots)
            add(rights[0], np.ones(SIMS, bool), (vals.mean()), factor=factor)
            continue
        if len(rights) >= 2 and len(ranges) >= 2 and rnd == 1:
            vals = slot_value(own_slots)
            for owner, (lo, hi) in zip(rights, ranges):
                mask = (own_slots >= lo) & (own_slots <= hi)
                add(owner, mask, (vals * mask).mean(), protection=f"slots {lo}-{hi}", factor=factor)
            continue
        ranks = pool_rank(desc, 0)
        teams = parse_teams(desc) if ranks is not None else []
        teams = [t for t in teams if t in slots[year].columns]
        if rnd == 1 and len(teams) >= 2:
            pool = np.sort(slots[year][teams].values, axis=1)
            ranks = pool_rank(desc, len(teams))
            # The pool's named receiver ("... to X", or the swap holder) gets these
            # ranks; any other owner holds the leftover pick(s).
            pool_part = re.split(r"\bthen\b|·", desc)[0]
            receiver = re.search(r"\bto ([A-Z]{3})\b", pool_part) or re.search(r"via (\w{3}) swap", desc)
            if receiver and ALIASES.get(receiver[1], receiver[1]) != rights[0]:
                ranks = [r for r in range(len(teams)) if r not in ranks]
            vals = np.mean([slot_value(pool[:, r]) for r in ranks], axis=0)
            note = desc + (" [pool; slot limits in pool ignored]" if re.search(r"\d+-\d+", desc) else " [pool]")
            add(rights[0], np.ones(SIMS, bool), vals.mean(), factor=factor, note=note)
            continue
        if rnd == 2 and len(rights) >= 2 and len(ranges) >= 2:
            for owner, (lo, hi) in zip(rights, ranges):
                mask = (own_slots >= lo) & (own_slots <= hi)
                add(owner, mask, SECOND_ROUND_M * mask.mean(), protection=f"slots {lo}-{hi}")
            continue
        add(rights[0], np.ones(SIMS, bool), slot_value(own_slots).mean(), factor=factor)

    for year, rnd, holder, other, desc, *protect in swaps.values():
        if holder not in slots[year] or other not in slots[year]:
            continue
        mine, theirs = slots[year][holder].values, slots[year][other].values
        gain = np.maximum(0, slot_value(theirs) - slot_value(mine)) if rnd == 1 else np.zeros(SIMS)
        if protect:   # protected range on the other team's pick: no swap there
            lo, hi = protect[0]
            gain = np.where((theirs >= lo) & (theirs <= hi), 0, gain)
        value = gain.mean() / (1 + DISCOUNT_RATE) ** (year - 2026)
        for owner, sign in ((holder, 1), (other, -1)):
            rows.append(dict(pick_id=f"{year}-SWAP-{holder}-{other}-R{rnd}" + ("" if sign > 0 else "-OWED"),
                             year=year, round=rnd,
                             original_team=other, owner=owner, protection="", swap_with=other if sign > 0 else holder,
                             exp_slot=round(theirs.mean(), 1), p_conveys=round((gain > 0).mean(), 3),
                             value_m=round(sign * value, 2),
                             notes=f"Swap right held by {holder} over {other}'s pick: {desc}"))

    picks = pd.DataFrame(rows)
    for col in ("original_team", "owner"):
        picks[col] = picks[col].replace(TO_BREF)
    picks["swap_with"] = picks["swap_with"].replace(TO_BREF)
    picks = picks[["pick_id", "year", "round", "original_team", "owner", "protection", "swap_with",
                   "exp_slot", "p_conveys", "value_m", "notes"]].sort_values(["year", "round", "exp_slot"])
    picks.to_csv("outputs/draft_picks.csv", index=False)

    totals = picks.groupby("owner")["value_m"].sum().round(1).rename("pick_value_m")
    summary = pd.read_csv("outputs/team_summary.csv").drop(columns="pick_value_m", errors="ignore")
    summary = summary.merge(totals, left_on="Team", right_index=True, how="left")
    summary.to_csv("outputs/team_summary.csv", index=False)

    curve = {k: round(float(slot_value(np.array([k]))[0]), 1) for k in (1, 5, 14, 30)}
    print(f"Slot value ($M at draft) = {SLOT_A:.2f}*exp(-{SLOT_B:.3f}*slot)+{SLOT_C:.2f}, "
          f"fit on {SLOT_N} picks: {curve}; second round ${SECOND_ROUND_M}M")
    print("\nProjected 2026-27 wins (roster Win Shares):")
    print(strength.rename(index=TO_BREF).sort_values().round(1).to_string())
    print(f"\nPICK VALUE BY TEAM ($M, discounted {DISCOUNT_RATE:.0%}/yr)")
    print(totals.sort_values(ascending=False).to_string())
    print(f"\nSaved {len(picks)} rows to outputs/draft_picks.csv; added pick_value_m to team_summary.csv")


if __name__ == "__main__":
    main()
