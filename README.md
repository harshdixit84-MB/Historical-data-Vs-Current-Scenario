# Historical Data vs Current Scenario

Studies past Nifty 50 / sector / stock behaviour across bull, bear, and
sideways market cycles — reversal points, indicator levels, cycle duration,
sector leadership — and compares the present cycle against historical
analogs.

## Structure

- `scripts/fetch_nifty_data.py` — pulls daily OHLCV for Nifty 50 and major
  sector indices via yfinance.
- `data/nifty50.csv` — Nifty 50 daily history.
- `data/sectors/*.csv` — one CSV per sector index.
- `.github/workflows/fetch-data.yml` — runs the fetch script daily
  (weekdays, post-market-close IST) and commits updated data automatically.

## Status

- [x] Step 1: Data fetch pipeline
- [x] Step 2: Cycle-tagging logic (bull/bear detection, now on **monthly** data — see note below)
- [ ] Step 3: Reversal-point deep-dive (indicator snapshots) — in progress
- [ ] Step 4: Sector leadership analysis per cycle
- [ ] Step 5: Present-cycle vs historical-cycle comparator
- [ ] Step 6: Dashboard

## Note: monthly basis

Since this study spans 15+ years, all calculations (moving averages, RSI,
MACD, cycle/zigzag detection) are done on **monthly-aggregated** data rather
than daily, going forward. Daily-basis equivalents used for monthly:

| Daily convention | Monthly equivalent |
|---|---|
| 50-day MA | 3-month MA |
| 200-day MA | 10-month MA |
| RSI-14 (daily) | RSI-14 on monthly closes |
| MACD(12,26,9) | same periods, monthly closes |
| 52-week high/low | trailing 12-month high/low |

`scripts/detect_cycles.py` outputs `data/cycles_monthly.csv` / `.json`.
