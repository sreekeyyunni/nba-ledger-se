# NBA Asset Tracker

Sreekar's NBA project, live at **https://sreekeyyunni.github.io/nba-ledger-se/**.

Every NBA team as a balance sheet: contract surplus value, trade machine, Be the GM, trade grader,
offseason planner, nightly game predictions, weekly media sentiment, and a daily Guess the Player.

## How it's built

Plain static files served by GitHub Pages from `main`, no build step:

- `index.html` (My team, Players, Teams, Trade machine), `gm.html`, `desk.html`, `grader.html`,
  `offseason.html`, `predict.html`, `sentiment.html`, `guess.html`, and the shared top bar `nav.js`
- `data/*.csv` read by the pages at load time
- `logos/*.png` team logos

This repo is the source of truth. The Contract Ledger app in Claude is republished from it.
Contributing (people or AI tools): read [AGENTS.md](AGENTS.md) first.

## Claude-only features

A few features need the Claude app and are hidden or show a note here:

- **AI GM**: the chat that asks Claude. The trade board and manual tools still work.
- **Trade grader**: "Read it with Claude" and "Save image".
- **Trade machine**: the shared trade board and image downloads.
- **Be the GM**: the shared leaderboard (runs are still saved in your browser).

## Updating the app

1. Change pages or data on a branch here and open a pull request (see [AGENTS.md](AGENTS.md)).
2. After it merges, Pages redeploys in about a minute.
3. Claude republishes the Ledger from `main`: `scripts/to_ledger.sh <folder>` builds its files.

## Nightly data (no Mac needed)

`.github/workflows/nightly-data.yml` runs twice a day (about 4:30pm and 2am ET) on GitHub's servers.
It runs `pipeline/predict.py` (ESPN scores and injuries), `pipeline/sim_data.py` and
`pipeline/transactions.py` (NBA.com and ESPN), copies the results into `data/` and pushes to `main`.

- `pipeline/outputs/predictions_log.csv` is the locked-picks record. Never edit or rewrite it.
- Player stats (`pipeline/data/advanced_2026_27.csv`) come from nba_api, which blocks GitHub's servers,
  so they still update from the Mac's weekly refresh.
- The balldontlie key (score backup if ESPN fails) is the repo secret `BALLDONTLIE_API_KEY`.
- Run it now: Actions tab, "Nightly data", "Run workflow".
