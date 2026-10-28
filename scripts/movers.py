"""Weekly movers: python scripts/movers.py [data_dir] [snapshot_date]

Saves a snapshot of every player's trade value and every team's net value
(data/snapshots/<date>.csv), then compares the current data with the newest
snapshot from an earlier date and writes data/movers.csv: value and rank now
vs then for each player and team. Run after every data refresh.
"""
import csv, sys, glob, os
from datetime import date

D = sys.argv[1] if len(sys.argv) > 1 else "data"
TODAY = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()
SNAP = os.path.join(D, "snapshots")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def current():
    rows = []
    with open(os.path.join(D, "trade_values.csv"), newline="") as f:
        for r in csv.DictReader(f):
            v = num(r["trade_value_m"])
            if v is not None:
                rows.append(("player", r["Player"], r["Team"], v))
    with open(os.path.join(D, "team_summary.csv"), newline="") as f:
        for r in csv.DictReader(f):
            v = num(r["net_m"])
            if v is not None:
                rows.append(("team", r["Team"], r["Team"], v))
    return rows


def ranks(rows):
    out = {}
    for kind in ("player", "team"):
        rs = sorted((r for r in rows if r[0] == kind), key=lambda r: -r[3])
        for i, r in enumerate(rs, 1):
            out[(kind, r[1])] = i
    return out


now = current()
os.makedirs(SNAP, exist_ok=True)
with open(os.path.join(SNAP, TODAY + ".csv"), "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["kind", "key", "team", "value"])
    w.writerows(now)

older = sorted(p for p in glob.glob(os.path.join(SNAP, "*.csv")) if os.path.basename(p)[:-4] < TODAY)
with open(os.path.join(D, "movers.csv"), "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["kind", "key", "team", "value", "prev_value", "rank", "prev_rank", "since"])
    if older:
        since = os.path.basename(older[-1])[:-4]
        with open(older[-1], newline="") as g:
            prev = [(r["kind"], r["key"], r["team"], float(r["value"])) for r in csv.DictReader(g)]
        pv = {(r[0], r[1]): r[3] for r in prev}
        rn, rp = ranks(now), ranks(prev)
        for kind, key, team, v in now:
            k = (kind, key)
            w.writerow([kind, key, team, round(v, 2), "" if k not in pv else round(pv[k], 2), rn[k], rp.get(k, ""), since])
        print(f"movers.csv: {len(now)} rows vs snapshot {since}")
    else:
        print("first snapshot saved; movers.csv will fill after the next refresh")
