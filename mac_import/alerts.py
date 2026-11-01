"""
Compare this run's outputs with the previous run and write outputs/alerts.md,
plus a macOS notification with a one-line summary. Run after refresh.py.

Followed teams and players come from follow.json ({"teams": [...], "players": [...]},
BBRef team codes). Flagged for each followed team / player:
- the team's rank in net_m (team value minus dead money)
- trade_value_m moves of at least TRADE_VALUE_MOVE_M, and healthy or blended
  surplus moves of at least SURPLUS_MOVE_M
- players who changed teams (trades, signings) to or from the team
- draft picks the team gained or lost
A league-wide section always lists the biggest team and player movers.

The first run (or any run without outputs/prev/) just saves a baseline.
"""
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd

TRADE_VALUE_MOVE_M = 5.0
SURPLUS_MOVE_M = 3.0
LEAGUE_MOVERS = 5
FILES = ["contract_value.csv", "trade_values.csv", "team_summary.csv", "draft_picks.csv"]
OUT, PREV = Path("outputs"), Path("outputs/prev")


def load(folder: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(folder / name)


def notify(message: str) -> None:
    script = f'display notification "{message.replace(chr(34), chr(39))}" with title "NBA Asset Tracker"'
    subprocess.run(["osascript", "-e", script], check=False)


def player_line(r) -> str:
    return (f"- {r.Player} ({r.Team}): trade value {r.trade_value_m_move:+.1f}M, healthy "
            f"{r.healthy_surplus_m_move:+.1f}M, blended {r.blended_surplus_m_move:+.1f}M")


def main() -> None:
    follow = json.loads(Path("follow.json").read_text())
    teams_followed = follow.get("teams") or ([follow["team"]] if follow.get("team") else [])
    followed_players = set(follow.get("players") or [])
    today = date.today().isoformat()

    if not all((PREV / f).exists() for f in FILES):
        PREV.mkdir(parents=True, exist_ok=True)
        for f in FILES:
            shutil.copy(OUT / f, PREV / f)
        (OUT / "alerts.md").write_text(f"# Alerts {today}\n\nBaseline saved; changes will be "
                                       f"reported from the next refresh.\n")
        notify("Baseline saved; alerts start next week")
        return

    # Team ranks
    new_t, old_t = load(OUT, "team_summary.csv"), load(PREV, "team_summary.csv")
    for t in (new_t, old_t):
        t["rank"] = t["net_m"].rank(ascending=False, method="min").astype(int)
    teams = new_t.merge(old_t[["Team", "rank", "net_m"]], on="Team", suffixes=("", "_old"))
    teams["rank_move"] = teams["rank_old"] - teams["rank"]

    # Player moves
    def players_at(folder: Path) -> pd.DataFrame:
        return load(folder, "contract_value.csv").merge(
            load(folder, "trade_values.csv")[["Player", "trade_value_m"]], on="Player", how="left")
    cols = ["trade_value_m", "healthy_surplus_m", "blended_surplus_m"]
    players = players_at(OUT)[["Player", "Team"] + cols].merge(
        players_at(PREV)[["Player", "Team"] + cols], on="Player", how="outer", suffixes=("", "_old"))
    for c in cols:
        players[f"{c}_move"] = players[c] - players[f"{c}_old"]
    big = players[(players["trade_value_m_move"].abs() >= TRADE_VALUE_MOVE_M)
                  | (players["healthy_surplus_m_move"].abs() >= SURPLUS_MOVE_M)
                  | (players["blended_surplus_m_move"].abs() >= SURPLUS_MOVE_M)]
    switched = players[players["Team"].notna() & players["Team_old"].notna()
                       & (players["Team"] != players["Team_old"])]

    # Pick ownership
    picks = load(OUT, "draft_picks.csv")[["pick_id", "owner"]].merge(
        load(PREV, "draft_picks.csv")[["pick_id", "owner"]], on="pick_id", how="outer", suffixes=("", "_old"))
    changed = picks[picks["owner"] != picks["owner_old"]]

    lines = [f"# Alerts {today}", "",
             f"Following {', '.join(teams_followed) or 'no teams'}"
             + (f" and {', '.join(sorted(followed_players))}" if followed_players else "")]
    headline = []
    for team in teams_followed:
        row = teams[teams["Team"] == team]
        if row.empty:
            lines += ["", f"## {team}", "- Not found in team_summary.csv"]
            continue
        row = row.iloc[0]
        mine = big[(big["Team"] == team) | (big["Team_old"] == team)]
        moves = switched[(switched["Team"] == team) | (switched["Team_old"] == team)]
        picks_t = changed[(changed["owner"] == team) | (changed["owner_old"] == team)]
        lines += ["", f"## {team}",
                  f"- Value rank #{row['rank_old']} -> #{row['rank']} "
                  f"(${row['net_m_old']:.1f}M -> ${row['net_m']:.1f}M)"]
        lines += [player_line(r) for r in mine.itertuples()]
        lines += [f"- {r.Player}: {r.Team_old} -> {r.Team}" for r in moves.itertuples()]
        lines += [f"- Pick {r.pick_id}: {r.owner_old} -> {r.owner}" for r in picks_t.itertuples()]
        if row["rank_move"]:
            headline.append(f"{team} #{row['rank_old']}→#{row['rank']}")
        headline += [f"{r.Player} {r.Team_old}→{r.Team}" for r in moves.itertuples()]
        headline += [f"{team} {'+' if r.owner == team else '-'}{r.pick_id}" for r in picks_t.itertuples()]
        headline += [f"{r.Player} {r.trade_value_m_move:+.0f}M" for r in mine.itertuples()]

    if followed_players:
        mine = big[big["Player"].isin(followed_players)]
        lines += ["", "## Followed players"] + ([player_line(r) for r in mine.itertuples()] or ["- No big moves"])
        headline += [f"{r.Player} {r.trade_value_m_move:+.0f}M" for r in mine.itertuples()]

    lines += ["", "## League-wide movers", "Team value rank:"]
    moved = teams[teams["rank_move"] != 0]
    moved = moved.reindex(moved["rank_move"].abs().sort_values(ascending=False).index).head(LEAGUE_MOVERS)
    lines += [f"- {r.Team}: #{r.rank_old} -> #{r.rank}" for r in moved.itertuples()] or ["- No rank changes"]
    lines.append("Player value:")
    top = big.reindex(big["trade_value_m_move"].abs().sort_values(ascending=False).index).head(LEAGUE_MOVERS)
    lines += [player_line(r) for r in top.itertuples()] or ["- None above the thresholds"]
    lines.append(f"Players who changed teams: {len(switched)}; picks that changed owner: {len(changed)}")

    lines += ["", "Ask Claude to republish the Ledger."]
    (OUT / "alerts.md").write_text("\n".join(lines) + "\n")
    for f in FILES:
        shutil.copy(OUT / f, PREV / f)

    summary = (f"{len(headline)} alerts: " + ", ".join(headline[:4])
               + (" …" if len(headline) > 4 else "")) if headline else "No changes for your teams"
    notify(summary)
    print(f"Wrote outputs/alerts.md ({summary})")


if __name__ == "__main__":
    main()
