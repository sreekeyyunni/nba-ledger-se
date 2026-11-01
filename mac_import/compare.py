"""Test only: compare the cloud refresh's outputs with the Mac's (mac_import/baseline/).
python ../mac_import/compare.py   (from pipeline/, after a run on the Mac's Oct 27 stats)"""
import pandas as pd

KEYS = {"contract_value.csv": "Player", "trade_values.csv": "Player", "team_summary.csv": "Team",
        "draft_picks.csv": "pick_id"}
bad = 0
for f, key in KEYS.items():
    b, n = pd.read_csv(f"../mac_import/baseline/{f}"), pd.read_csv(f"outputs/{f}")
    print(f"\n{f}: Mac {len(b)} rows, cloud {len(n)} rows; columns same: {list(b.columns) == list(n.columns)}")
    only = set(b[key]) ^ set(n[key])
    if only:
        bad += 1
        print("  rows on one side only:", sorted(only)[:10])
    m = b.merge(n, on=key, suffixes=("_mac", "_cloud"))
    for c in b.columns:
        if c == key or c + "_cloud" not in m:
            continue
        x, y = m[c + "_mac"], m[c + "_cloud"]
        if all(pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) for s in (x, y)):
            d = (x - y).abs().max()
            if d > 0.05:
                bad += 1
                print(f"  {c}: max diff {d:.2f}")
        else:
            diff = (x.fillna("").astype(str) != y.fillna("").astype(str)).sum()
            if diff:
                bad += 1
                print(f"  {c}: {diff} rows differ")
print("\nMATCH" if not bad else f"\n{bad} differences")
