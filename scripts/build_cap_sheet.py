"""Three-year cap sheet: python scripts/build_cap_sheet.py [data_dir]
Reads contracts_clean, contract_value (rookie flag), team_cap, team_summary (dead 2026-27),
dead_2027_28, draft_picks. Writes cap_sheet.csv (team x season totals) and
cap_sheet_lines.csv (every line item). Money in $M. Same approximations as offseason.html."""
import sys, os, re
import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else "data"
rd = lambda f: pd.read_csv(os.path.join(D, f))
con, cv, tc, ts, dd, pk = rd("contracts_clean.csv"), rd("contract_value.csv"), rd("team_cap.csv"), rd("team_summary.csv"), rd("dead_2027_28.csv"), rd("draft_picks.csv")
SEAS = ["2026-27", "2027-28", "2028-29"]
CAP = {"2026-27": 164.961, "2027-28": 176.0}; CAP["2028-29"] = CAP["2027-28"] * 1.07
R = {"tax": 200.428 / 164.961, "a1": 209.015 / 164.961, "a2": 221.686 / 164.961}
R["tax"] = 1.215  # 2027-28 projection uses tax = 1.215 x cap
LINES = {s: dict(cap=CAP[s], tax=CAP[s] * (200.428 / 164.961 if s == "2026-27" else 1.215),
                 a1=CAP[s] * 209.015 / 164.961, a2=CAP[s] * 221.686 / 164.961,
                 ntmle=CAP[s] * .0912, tpmle=CAP[s] * .03676, room=CAP[s] * .05678,
                 rmin=1.36 * 1.07 ** SEAS.index(s), floor=2.4 * 1.07 ** max(0, SEAS.index(s) - 1)) for s in SEAS}
SCALE = [13.83,12.37,11.11,10.02,9.09,8.27,7.55,6.92,6.36,5.91,5.61,5.33,5.07,4.82,4.58,4.35,4.14,3.97,3.82,3.68,3.54,3.40,3.27,3.16,3.08,3.01,2.95,2.88,2.83,2.82]
rookie = set(cv.loc[cv.rookie_scale == True, "Player"])
dead = {s: {} for s in SEAS}
dead["2026-27"] = dict(zip(ts.Team, ts.dead_m)); dead["2027-28"] = dict(zip(dd.Team, dd.dead_m))  # 2028-29 dead money not tracked yet

def opts(s):
    o = {}
    if isinstance(s, str):
        for part in s.split(";"):
            y, k = part.split(":"); o[y] = k
    return o

def tax_bill(over):
    owed, rate, left = 0.0, 1.5, over
    while left > 0:
        step = min(5, left); owed += step * rate; left -= step; rate += 0.25 if rate == 1.5 else 0.75
    return owed

lines, rows = [], []
for team in sorted(tc.Team):
    ros = con[con.Team == team]
    for si, s in enumerate(SEAS):
        k = LINES[s]; items = []
        for _, p in ros.iterrows():
            o = opts(p.option_years); v = p[s]
            if pd.notna(v) and v > 0:
                items.append(("Team option" if o.get(s) == "TO" else "Player option" if o.get(s) == "PO" else "Guaranteed", p.Player, v))
            elif si > 0:
                last = p[SEAS[si - 1]]
                if pd.notna(last) and last >= 0.5:
                    h = 2.5 * last if p.Player in rookie else 1.5 * last if last >= 13.5 else 1.9 * last
                    items.append(("Cap hold", p.Player, min(max(h, k["floor"]), .35 * k["cap"])))
        d = dead[s].get(team, 0)
        if d > 0.05: items.append(("Dead money", "Waived / stretched salary", d))
        if si > 0:
            yr = 2027 + si - 1  # draft held before this season
            for _, r in pk[(pk.owner == team) & (pk.year == yr)].iterrows():
                if r["round"] == 1 and r.p_conveys >= .5:
                    items.append(("Draft pick", f"{yr} 1st ({r.original_team}, ~#{r.exp_slot:.0f})", SCALE[min(29, max(0, int(round(r.exp_slot)) - 1))] * .948 * 1.07 ** (si - 1)))
        for kind, name, amt in items: lines.append((team, s, kind, name, round(amt, 3)))
        g = lambda kinds: sum(a for kd, _, a in items if kd in kinds)
        guar, opt, dm, picks, holds = g(["Guaranteed"]), g(["Team option", "Player option"]), g(["Dead money"]), g(["Draft pick"]), g(["Cap hold"])
        n = sum(1 for kd, _, _ in items if kd in ("Guaranteed", "Team option", "Player option", "Draft pick"))
        fill = max(0, 12 - n) * k["rmin"] if si > 0 else 0
        total = guar + opt + dm + picks + fill
        if s == "2026-27": total = float(tc.set_index("Team").loc[team, "payroll_m"])
        tier = "over 2nd apron" if total > k["a2"] else "over 1st apron" if total > k["a1"] else "over tax" if total > k["tax"] else "over cap" if total > k["cap"] else "under cap"
        exc = ("Room exception" if tier == "under cap" else "Non-taxpayer MLE" if total <= k["a1"] else "Taxpayer MLE" if total <= k["a2"] else "Minimum contracts only")
        pickct = lambda rd_: int(((pk.owner == team) & (pk.year == 2027 + si) & (pk["round"] == rd_)).sum())
        rows.append(dict(Team=team, season=s, cap=k["cap"], tax_line=k["tax"], apron1=k["a1"], apron2=k["a2"],
                         guaranteed=guar, options=opt, dead=dm, picks=picks, roster_fill=fill, payroll=total,
                         holds=holds, space=k["cap"] - total, space_with_holds=k["cap"] - total - holds,
                         status=tier, to_tax=k["tax"] - total, to_apron1=k["a1"] - total, to_apron2=k["a2"] - total,
                         tax_bill=tax_bill(total - k["tax"]) if total > k["tax"] else 0, exception=exc,
                         firsts=pickct(1), seconds=pickct(2)))
pd.DataFrame(rows).round(3).to_csv(os.path.join(D, "cap_sheet.csv"), index=False)
pd.DataFrame(lines, columns=["Team", "season", "kind", "item", "amt_m"]).to_csv(os.path.join(D, "cap_sheet_lines.csv"), index=False)
print(len(rows), "team-seasons,", len(lines), "lines")
