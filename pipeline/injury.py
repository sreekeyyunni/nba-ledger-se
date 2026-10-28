"""
How many games an injury report says a player will miss, from today.

Reads the timeline in the note ("expected to miss up to two months", "out 4-6 weeks",
"will miss 10 games", "season-ending") and counts it from the report's date at about
3.5 games a week. Returns None when the note gives no timeline.
"""
import re
from datetime import date

GAMES_PER_DAY = 0.5
WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "several": 3, "a few": 3, "a couple": 2,
         "couple of": 2}
NUM = r"(\d+|a few|a couple|couple of|several|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
SPAN = re.compile(NUM + r"(?:\s*(?:to|-|–|or)\s*" + NUM + r")?[\s-]+(days?|weeks?|months?|games)\b")
SEASON_OVER = re.compile(r"(remainder|rest) of the (\d{4}-\d{2} )?(regular )?season|miss the (entire )?(\d{4}-\d{2} )?season"
                         r"|out for the season|season-ending")
DAYS = {"day": 1, "week": 7, "month": 30}


def _n(s):
    return int(s) if s.isdigit() else WORDS[s]


def games_out(note, updated, today, season_left=82):
    n = (note or "").lower()
    if not n.startswith("out"):
        return None
    if SEASON_OVER.search(n):
        return season_left
    m = SPAN.search(n)
    if not m:
        return None
    hi = _n(m.group(2) or m.group(1))
    unit = m.group(3).rstrip("s")
    try:
        since = (today - date.fromisoformat(updated[:10])).days
    except (TypeError, ValueError):
        since = 0
    games = hi if unit == "game" else round((hi * DAYS[unit] - max(since, 0)) * GAMES_PER_DAY)
    return max(0, min(games, season_left))
