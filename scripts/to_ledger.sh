#!/usr/bin/env bash
# Build the Contract Ledger artifact's files from this repo (the repo is the source of truth).
# Usage: scripts/to_ledger.sh <out folder>
# Writes: <out>/contract-ledger.html (the artifact's main page, from index.html) plus the
# other pages, scripts, data/*.csv, data/*.json and logos/*.png, with site-only tweaks undone.
set -euo pipefail
out="${1:?usage: scripts/to_ledger.sh <out folder>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
LEDGER_URL="https://claude.ai/artifact/N3ebKmu62fS6TdqjXyLyNX"
mkdir -p "$out/data" "$out/logos"

for f in "$repo"/*.html "$repo"/*.js; do cp "$f" "$out/"; done
rm -f "$out/index.html"
cp "$repo"/data/*.csv "$out/data/"
cp "$repo"/data/*.json "$out/data/" 2>/dev/null || true
cp "$repo"/logos/*.png "$out/logos/"

python3 - "$repo" "$out" "$LEDGER_URL" <<'PY'
import re, sys, pathlib
repo, out, url = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
pwa = re.compile(r"<!--pwa-->.*?<!--/pwa-->", re.S)
# The artifact wraps its main page itself: drop the site's skeleton line and closing tags.
idx = (repo / "index.html").read_text().split("\n", 1)[1]
idx = re.sub(r"</body></html>\s*$", "", idx)
(out / "contract-ledger.html").write_text(idx)
for p in out.glob("*.html"):
    t = pwa.sub("", p.read_text())
    if p.name == "gm.html":
        t = re.sub(r'const PLAY_URL="[^"]*"', f'const PLAY_URL="{url}"', t)
    p.write_text(t)
PY
echo "Built Ledger files in $out. Publish $out/contract-ledger.html with the rest as files."
