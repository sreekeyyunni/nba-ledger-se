"""
Read tables from Basketball Reference pages using only the standard library.

Each table row becomes a dict keyed by the cells' data-stat names (e.g.
"name_display", "mp", "ws"); the player's BBRef id is stored as "player_id".
Tables hidden inside HTML comments (BBRef does this for some tables) are
found too.
"""
import subprocess
import time
from html.parser import HTMLParser

USER_AGENT = "nba-asset-tracker (personal project; one request per page)"
PAUSE_SECONDS = 4   # be polite between page loads


def fetch(url: str) -> str:
    # macOS's curl uses the system certificate store; python.org builds of
    # Python often have no CA certificates installed.
    result = subprocess.run(["curl", "-sSf", "-m", "30", "-A", USER_AGENT, url],
                            capture_output=True, check=True)
    time.sleep(PAUSE_SECONDS)
    return result.stdout.decode("utf-8")


class _TableParser(HTMLParser):
    def __init__(self, table_id: str):
        super().__init__(convert_charrefs=True)
        self.table_id = table_id
        self.depth = 0          # nesting depth inside the wanted <table>
        self.in_body = False
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.depth or attrs.get("id") == self.table_id:
                self.depth += 1
            return
        if not self.depth:
            return
        if tag == "tbody":
            self.in_body = True
        elif tag == "tr" and self.in_body:
            classes = attrs.get("class") or ""
            self.row = None if "thead" in classes else {}
        elif tag in ("td", "th") and self.row is not None:
            self.cell = attrs.get("data-stat")
            self.row.setdefault(self.cell, "")
            if attrs.get("class"):
                self.row[f"{self.cell}__class"] = attrs["class"]
            if attrs.get("data-append-csv"):
                self.row["player_id"] = attrs["data-append-csv"]

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "table":
            self.depth -= 1
        elif tag == "tbody":
            self.in_body = False
        elif tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None
        elif tag in ("td", "th"):
            self.cell = None

    def handle_data(self, data):
        if self.row is not None and self.cell:
            self.row[self.cell] += data

    def handle_comment(self, data):
        if f'id="{self.table_id}"' in data and not self.rows:
            self.feed(data)


def read_table(html: str, table_id: str) -> list[dict]:
    parser = _TableParser(table_id)
    parser.feed(html)
    return [{k: v.strip() for k, v in r.items()} for r in parser.rows]
