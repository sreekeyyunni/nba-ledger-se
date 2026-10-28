"""Add home-screen app tags (manifest, icons, standalone mode) to every page: python scripts/pwa.py"""
import glob, os, re
TAGS = ('<!--pwa--><link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="apple-touch-icon.png">'
        '<link rel="icon" href="icon-192.png"><meta name="theme-color" content="#16212D"><meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default">'
        '<meta name="apple-mobile-web-app-title" content="NBA Ledger"><!--/pwa-->')
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
for p in glob.glob(os.path.join(root, "*.html")):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"<!--pwa-->.*?<!--/pwa-->", "", s, flags=re.S)
    m = re.search(r"<meta[^>]*charset[^>]*>", s, re.I) or re.search(r"<head[^>]*>", s, re.I)
    s = s[:m.end()] + TAGS + s[m.end():] if m else TAGS + s
    open(p, "w", encoding="utf-8").write(s)
print("pwa tags added")
