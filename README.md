# Doc’s Basketball IQ War Room

The included Thanksgiving board covers 21 men’s Division I games on November 26, 2026. The attachment is a static copy of the research. The GitHub Pages build reads the same board and history files after every refresh.

## Local preview

Run `python -m http.server 8765 --directory site` from this directory. Open http://localhost:8765 to browse matchups. Run `python refresh.py` to collect the current Central Time slate and update the local board using the public source feeds.

## GitHub Pages

Use a separate public repository with `main` as its default branch. In its Pages settings, select GitHub Actions. The included workflow refreshes at :17 and :47 past the hour, and accepts manual runs. GitHub may delay scheduled jobs. The workflow requires its repository-scoped token to make regular commits to the default branch. It publishes only the `site` directory.

## Data and verification

ESPN supplies the schedule, game logs, attributed full-game quotes and results. Bart Torvik supplies adjusted team offense, defense and tempo. Opponent strength is the average adjusted efficiency margin of ranked opponents in available box scores. RotoWire depth-chart updates supplement projections based on prior starts. The first-half comparison parses book-attributed spreads and totals from Maddux Sports, matching both team names and exact tip time.

Lineups are estimates. Routine DNPs are kept distinct from a sourced absence. First-half scores are based on historical scoring share with shrinkage and full-game scores include a rotation scoring component. Estimates can be sensitive to small samples, late availability and overtime. There is no validated probability model. No tracking values are fabricated.

The first timestamped pregame forecast is retained. New first-half comparisons can be added as separately timestamped receipts before tipoff. Final grades use the archived comparisons and ESPN’s final and halftime scores. The workflow has a latest-board view and retains forecasts across dates in its history table.

The Thanksgiving scouting notes link to public game notes and other previews. Tracking data for potential assists, rebounding opportunities and defensive matchups, systematic film review, automatic official availability, rotation experience, Kambi, sportsbook team totals and alternate markets are incomplete. The NBA has no games on the requested date. NBA player projection and tracking integration are outside this build.

The public feeds vary by schedule and can change format. No provider credentials are included.
