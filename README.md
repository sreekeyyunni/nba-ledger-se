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

The source of truth is the Contract Ledger app in Claude. This repo is a copy of its published files.

## Claude-only features

A few features need the Claude app and are hidden or show a note here:

- **AI GM**: the chat that asks Claude. The trade board and manual tools still work.
- **Trade grader**: "Read it with Claude" and "Save image".
- **Trade machine**: the shared trade board and image downloads.
- **Be the GM**: the shared leaderboard (runs are still saved in your browser).

## Updating the data

1. Download the Ledger artifact's files into a folder (same layout: `*.html`, `nav.js`, `data/`, `logos/`).
2. Run `scripts/sync.sh <that folder>` from this repo.
3. Commit and push to `main`. Pages redeploys in about a minute.
