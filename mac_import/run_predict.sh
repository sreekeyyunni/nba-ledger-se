#!/bin/zsh
# Twice-daily predictor run: afternoon (locks tonight's picks with fresh injuries)
# and overnight (grades last night's games). ESPN feed, ~3 requests per run.
cd "$HOME/nba-asset-tracker" || exit 1
echo "=== $(date) ==="
# ESPN sometimes times out; try the picks step up to 3 times, a minute apart
for i in 1 2 3; do .venv/bin/python predict.py && break; echo "predict.py failed (try $i)"; sleep 60; done
.venv/bin/python sim_data.py
.venv/bin/python transactions.py
