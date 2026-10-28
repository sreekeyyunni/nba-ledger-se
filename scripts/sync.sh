#!/usr/bin/env bash
# Copy the app's published files into this repo and apply the few site-only tweaks.
# Usage: scripts/sync.sh <folder holding the Contract Ledger artifact's files>
# The folder is the artifact's file layout: *.html, *.js, data/*.csv and *.json, logos/*.png.
set -euo pipefail
src="${1:?usage: scripts/sync.sh <artifact files folder>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"

cp "$src"/*.html "$src"/*.js "$repo"/
mkdir -p "$repo/data" "$repo/logos"
cp "$src"/data/*.csv "$repo/data/"
cp "$src"/data/*.json "$repo/data/" 2>/dev/null || true
cp "$src"/logos/*.png "$repo/logos/"

# Share links in Be the GM point at the site, not the Claude artifact.
sed -i.bak 's#const PLAY_URL="https://claude.ai/artifact/[A-Za-z0-9]*"#const PLAY_URL="https://sreekeyyunni.github.io/nba-ledger-se/gm.html"#' "$repo/gm.html"
rm -f "$repo/gm.html.bak"

python3 "$repo/scripts/pwa.py"
python3 "$repo/scripts/movers.py" "$repo/data" || true
echo "Synced from $src. Review with: git -C \"$repo\" status"
