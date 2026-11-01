#!/bin/zsh
# Weekly job: refresh Basketball Reference data (one request per page), re-run
# the models, then write outputs/alerts.md and a macOS notification. Spotrac is
# a manual snapshot and isn't touched here.
cd "$HOME/nba-asset-tracker" || exit 1
echo "=== $(date) ==="
.venv/bin/python refresh.py && .venv/bin/python alerts.py
