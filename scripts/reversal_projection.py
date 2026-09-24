"""
Step 5b: Using the SAME parameters established in the historical analysis
(20% zigzag rule, price-vs-10-month-MA extension at past tops), project:

  1. The current phase classification (per our own rules).
  2. Downside reversal levels: the exact price where our own 20% rule would
     confirm a Bear phase, plus an earlier "correction watch" level.
  3. Upside target zone: current 10-month MA projected forward using the
     range of extension (% above 10-month MA) seen at every past
     historical top.

This does NOT predict the future — it mechanically applies the rules we
already defined to the current data, so the output is only as good as
those rules (small sample: 3 historical tops for the extension range).

Output: data/current_status.json is updated with a "projection" block.
Run:
    python scripts/reversal_projection.py
"""

import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from detect_cycles import load_price_data, resample_monthly, compute_indicators  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CYCLES_CSV = os.path.join(DATA_DIR, "cycles_monthly.csv")
STATUS_JSON = os.path.join(DATA_DIR, "current_status.json")

BEAR_CONFIRM_THRESHOLD = 0.20   # our zigzag rule: 20% down confirms Bear
CORRECTION_WATCH_THRESHOLD = 0.10  # our subswing rule: 10% = a "meaningful" correction


def main():
    daily = load_price_data()
    monthly = resample_monthly(daily)
    monthly = compute_indicators(monthly)
    phases = pd.read_csv(CYCLES_CSV)

    current_phase = phases.iloc[-1]
    phase_type = current_phase["type"]

    # Running peak/trough since the current phase started, using DAILY data
    # for the most current, exact levels (monthly data lags by up to ~4 weeks)
    phase_start_date = pd.Timestamp(current_phase["start_month"])
    since_start = daily[daily.index >= phase_start_date]
    latest_close = daily["Close"].iloc[-1]
    latest_date = daily.index[-1]

    result = {
        "as_of_date": str(latest_date.date()),
        "latest_close": round(float(latest_close), 2),
        "current_phase_type": phase_type,
        "current_phase_start": current_phase["start_month"],
        "current_phase_elapsed_months": int(current_phase["duration_months"]),
    }

    if phase_type == "Bull":
        running_peak = since_start["Close"].max()
        running_peak_date = since_start["Close"].idxmax()
        bear_confirm_level = running_peak * (1 - BEAR_CONFIRM_THRESHOLD)
        watch_level = running_peak * (1 - CORRECTION_WATCH_THRESHOLD)

        result["running_peak"] = round(float(running_peak), 2)
        result["running_peak_date"] = str(running_peak_date.date())
        result["downside_confirmed_bear_level"] = round(float(bear_confirm_level), 2)
        result["downside_confirmed_bear_pct_from_peak"] = -BEAR_CONFIRM_THRESHOLD * 100
        result["downside_correction_watch_level"] = round(float(watch_level), 2)
        result["downside_correction_watch_pct_from_peak"] = -CORRECTION_WATCH_THRESHOLD * 100

        # Upside target zone from historical top extension (% above 10-mo MA)
        bear_starts = phases[phases["type"] == "Bear"].dropna(subset=["start_price_vs_ma10_pct"])
        if not bear_starts.empty:
            ext_min = bear_starts["start_price_vs_ma10_pct"].min()
            ext_max = bear_starts["start_price_vs_ma10_pct"].max()
            ext_median = bear_starts["start_price_vs_ma10_pct"].median()
            current_ma10 = monthly["MA_long"].iloc[-1]

            result["current_ma10"] = round(float(current_ma10), 2)
            result["historical_top_extension_pct"] = {
                "min": round(float(ext_min), 2), "median": round(float(ext_median), 2), "max": round(float(ext_max), 2),
                "n_historical_tops": int(len(bear_starts)),
            }
            result["upside_target_zone"] = {
                "low": round(float(current_ma10 * (1 + ext_min / 100)), 2),
                "median": round(float(current_ma10 * (1 + ext_median / 100)), 2),
                "high": round(float(current_ma10 * (1 + ext_max / 100)), 2),
            }
            result["current_extension_pct_above_ma10"] = round(
                float((latest_close - current_ma10) / current_ma10 * 100), 2
            )
    else:  # Bear phase — mirror logic for downside/bottom projection
        running_trough = since_start["Close"].min()
        running_trough_date = since_start["Close"].idxmin()
        bull_confirm_level = running_trough * (1 + BEAR_CONFIRM_THRESHOLD)
        watch_level = running_trough * (1 + CORRECTION_WATCH_THRESHOLD)

        result["running_trough"] = round(float(running_trough), 2)
        result["running_trough_date"] = str(running_trough_date.date())
        result["upside_confirmed_bull_level"] = round(float(bull_confirm_level), 2)
        result["upside_confirmed_bull_pct_from_trough"] = BEAR_CONFIRM_THRESHOLD * 100
        result["upside_bounce_watch_level"] = round(float(watch_level), 2)

        bull_starts = phases[phases["type"] == "Bull"].dropna(subset=["start_price_vs_ma10_pct"])
        if not bull_starts.empty:
            ext_min = bull_starts["start_price_vs_ma10_pct"].min()
            ext_max = bull_starts["start_price_vs_ma10_pct"].max()
            ext_median = bull_starts["start_price_vs_ma10_pct"].median()
            current_ma10 = monthly["MA_long"].iloc[-1]

            result["current_ma10"] = round(float(current_ma10), 2)
            result["historical_bottom_extension_pct"] = {
                "min": round(float(ext_min), 2), "median": round(float(ext_median), 2), "max": round(float(ext_max), 2),
                "n_historical_bottoms": int(len(bull_starts)),
            }
            result["downside_target_zone"] = {
                "low": round(float(current_ma10 * (1 + ext_max / 100)), 2),
                "median": round(float(current_ma10 * (1 + ext_median / 100)), 2),
                "high": round(float(current_ma10 * (1 + ext_min / 100)), 2),
            }

    # Merge into current_status.json
    if os.path.exists(STATUS_JSON):
        with open(STATUS_JSON) as f:
            status = json.load(f)
    else:
        status = {}
    status["projection"] = result
    with open(STATUS_JSON, "w") as f:
        json.dump(status, f, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
