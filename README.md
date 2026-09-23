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

- [x] Step 1: Data fetch pipeline (this commit)
- [ ] Step 2: Cycle-tagging logic (bull/bear/sideways detection)
- [ ] Step 3: Reversal-point detector + indicator snapshot at each reversal
- [ ] Step 4: Sector leadership analysis per cycle
- [ ] Step 5: Present-cycle vs historical-cycle comparator
- [ ] Step 6: Dashboard
