# Working in this repo (for any AI tool or person)

This repo is the source of truth for the NBA Asset Tracker. The public site is GitHub Pages from
`main`. The Contract Ledger app in Claude is republished from this repo with `scripts/to_ledger.sh`.

## Rules

1. Work on a branch and open a pull request. Do not push straight to `main`
   (only the nightly GitHub Action and the integrator do that).
2. Never edit, reorder or rewrite `pipeline/outputs/predictions_log.csv`. It is the locked record of picks.
3. `nav.js` is the only menu. Add a page by adding it to `PAGES` in `nav.js`; do not build a second menu.
4. No secrets in the repo. Keys live in GitHub secrets (`BALLDONTLIE_API_KEY`) or on the Mac in `.env`.
5. Data: polite API requests only, no scraping or crawling. Contracts are pulled only when Sreekar asks.
6. Keep it static: plain HTML/JS/CSV, no build step, no frameworks, no new runtime dependencies.
7. Keep CSV columns stable. Pages read columns by name; if you add one, add it at the end.
8. Don't hand-edit the `<!--pwa-->` blocks; `scripts/pwa.py` writes them.

## Layout

| Path | What it is |
|---|---|
| `home.html` | Landing page |
| `index.html` | Main app: Home, My team, Players, Teams, Trade machine (hash routes) |
| `gm.html`, `desk.html`, `grader.html`, `offseason.html`, `styles.html`, `sim.html`, `series.html`, `capsheet.html`, `predict.html`, `sentiment.html`, `guess.html` | Be the GM, AI GM, Transactions, Offseason, Play styles, Season sim, Starting 5, Cap sheet, Predictions, Sentiment, Guess the player |
| `nav.js` | Shared top bar, menu and team picker (`localStorage.myTeam`) |
| `sim.js`, `simui.js`, `fit.js` | Season simulator, its UI helpers, play-style fit |
| `data/` | Everything the pages read at load time |
| `logos/` | Team logos, `<TEAM>.png` |
| `pipeline/` | Python run by GitHub Actions (`.github/workflows/nightly-data.yml` twice daily, `weekly-data.yml` Mondays) |
| `scripts/` | `to_ledger.sh` (repo to Claude app), `sync.sh` (old reverse direction), `pwa.py`, `movers.py`, `build_cap_sheet.py` |

## Data files and who writes them

Writers: **Mac** = weekly refresh on Sreekar's Mac (`refresh.py`, Mondays, nba_api and contracts),
**Actions** = `pipeline/` twice daily (about 4:30pm and 2am ET), **Weekly** = `weekly-data.yml` on GitHub,
Mondays 9am ET (`pipeline/stats.py`, cap sheet, movers), **Claude** = the integrator. The Mac is a backup only.

| File | Columns (key ones) | Writer |
|---|---|---|
| `contract_value.csv` | Player, Team, G, MP, WS, VORP, salary_m, market_value_m, surplus_m, healthy_surplus_m, ..., star_tier, star_m, games_out, injury_m, injury_note | Mac, then Actions (`pipeline/adjust.py`) |
| `contracts_clean.csv` | Player, Team, 2026-27 ... 2031-32, option_years, flag | Mac (contract pull, on request) |
| `trade_values.csv` | Player, Team, Age, years_left, trade_value_m, sv_y1..sv_y6, rookie_scale, flag, star_m, injury_m | Mac, then Actions (`adjust.py`) |
| `accolades.csv` | Player, season, honor (All-NBA) for star credit | By hand / Claude |
| `team_summary.csv` | Team, active_m, dead_m, team_surplus_m, net_m, best/worst_contract, ..., adj_net_m | Mac, then Actions (`adjust.py`) |
| `team_cap.csv` | payroll, cap, tax, aprons by team | Mac (contract pull) |
| `cap_sheet.csv`, `cap_sheet_lines.csv` | by team and season; lines are Team, season, kind, item, amt_m | Weekly (`scripts/build_cap_sheet.py`) |
| `pipeline/data/advanced_2026_27.csv` | Player, Age, Team, Pos, G, MP, WS, WS/48, BPM, VORP, ... | Weekly (`pipeline/stats.py`, Basketball Reference) |
| `dead_money.csv`, `dead_2027_28.csv` | Team, dead_m | Mac |
| `draft_picks.csv` | pick_id, year, round, original_team, owner, protection, value_m, ... | Mac |
| `prospects.csv` | Rank, Name, Pos, School, Class, Age, Height | Mac |
| `player_styles.csv`, `team_styles.csv`, `team_styles_league.csv` | play-type frequencies and efficiency | Mac |
| `player_ids.csv` | Player, nba_id (for headshots) | Mac |
| `sentiment_teams.csv`, `sentiment_players.csv`, `sentiment_sources.csv` | week, Team/Player, score, label, ... | Claude (Mondays) |
| `predictions.csv` | date, away, home, home_prob, pick, status, correct, mode, ... | Actions |
| `team_power.csv` | rank, team, rating, form, wins, losses, out | Actions |
| `sim_data.json` | teams and players for the season sim | Actions |
| `transactions.csv` | id, date, type, team, player, description, source, years, total_m | Actions |
| `movers.csv`, `snapshots/` | kind, key, team, value, prev_value, rank, prev_rank, since | Weekly (`scripts/movers.py`) |

## Value adjustments

`pipeline/adjust.py` adds star credit and injury time (timelines parsed by `pipeline/injury.py`) on top of
the Mac's values. It keeps the Mac's unadjusted files in `pipeline/data/raw/` and always adjusts from those,
so it is safe to rerun. Change the rules there, not in the pages.

## Testing a change

`python3 -m http.server 8000` from the repo root, then open http://localhost:8000/home.html.
Check a phone width (about 390px) and dark mode. Pages must still work when a data file fails to load.
