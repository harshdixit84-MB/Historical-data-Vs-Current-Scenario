"""
Step 5: Compare the CURRENT (latest, still-forming) market state against
every historical reversal point, to find which past turning points looked
most similar on the same indicator set — and what happened after them.

Method: nearest-neighbor matching on a standardized feature vector
[RSI6, RSI14, MACD_hist_pct, Price_vs_10moMA_pct, pct_off_12m_high,
 pct_above_12m_low], Euclidean distance, no assumption of whether "now"
should resemble a top or a bottom — whichever historical points are
closest simply win.

Also reports how the CURRENT ongoing phase's elapsed duration/move compares
to the distribution of past phases of the same type (is this bull run
already unusually long/large, or still young by historical standards).

Requires: data/cycles_monthly.csv (from detect_cycles.py) and
data/nifty50.csv. Run:
    python scripts/cycle_comparator.py
"""

import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from detect_cycles import load_price_data, resample_monthly, compute_indicators  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CYCLES_CSV = os.path.join(DATA_DIR, "cycles_monthly.csv")

FEATURES = [
    ("start_rsi6", "RSI6"),
    ("start_rsi14", "RSI14"),
    ("start_macd_hist_pct", "MACD_hist_pct"),
    ("start_price_vs_ma10_pct", "Price_vs_MAlong_pct"),
    ("start_pct_off_12m_high", "pct_off_high"),
    ("start_pct_above_12m_low", "pct_above_low"),
]


def get_current_snapshot(monthly_df):
    latest = monthly_df.iloc[-1]
    return {
        "month": monthly_df.index[-1],
        "RSI6": latest["RSI6"], "RSI14": latest["RSI14"],
        "MACD_hist_pct": latest["MACD_hist_pct"],
        "Price_vs_MAlong_pct": latest["Price_vs_MAlong_pct"],
        "pct_off_high": latest["pct_off_high"], "pct_above_low": latest["pct_above_low"],
    }


def nearest_neighbors(phases_df, current):
    hist_cols = [f[0] for f in FEATURES]
    live_keys = [f[1] for f in FEATURES]

    hist = phases_df[["phase_id", "type", "start_month"] + hist_cols].dropna(subset=hist_cols).copy()
    if hist.empty:
        return hist, None

    live_vec = np.array([current[k] for k in live_keys], dtype=float)

    # standardize each feature using mean/std across historical points +
    # the current point, so distance isn't dominated by raw-scale features
    combined = np.vstack([hist[hist_cols].values, live_vec])
    means = combined.mean(axis=0)
    stds = combined.std(axis=0)
    stds[stds == 0] = 1.0

    hist_norm = (hist[hist_cols].values - means) / stds
    live_norm = (live_vec - means) / stds

    distances = np.linalg.norm(hist_norm - live_norm, axis=1)
    hist["distance"] = distances
    hist = hist.sort_values("distance")
    return hist, live_vec


def duration_context(phases_df, phase_type, elapsed_months, elapsed_pct_move):
    completed = phases_df[(phases_df["type"] == phase_type) & (phases_df["phase_id"] != phases_df["phase_id"].max())]
    if completed.empty:
        return None
    durations = completed["duration_months"]
    moves = completed["pct_move"].abs()
    return {
        "n": len(completed),
        "duration_min": durations.min(), "duration_median": durations.median(), "duration_max": durations.max(),
        "move_min": moves.min(), "move_median": moves.median(), "move_max": moves.max(),
        "elapsed_months": elapsed_months, "elapsed_pct_move": elapsed_pct_move,
        "duration_percentile": (durations < elapsed_months).mean() * 100,
    }


def main():
    daily = load_price_data()
    monthly = resample_monthly(daily)
    monthly = compute_indicators(monthly)
    current = get_current_snapshot(monthly)

    phases = pd.read_csv(CYCLES_CSV)

    print("=== Current snapshot ===")
    print(f"Month: {current['month'].date()}")
    for _, label in FEATURES:
        print(f"  {label}: {current[label]:.2f}")
    print()

    print("=== Nearest historical analogs (by indicator similarity) ===\n")
    ranked, _ = nearest_neighbors(phases, current)
    analog_records = []
    if ranked is None or ranked.empty:
        print("Not enough historical data with complete indicators to compare.")
    else:
        for rank_pos, (_, row) in enumerate(ranked.head(3).iterrows(), start=1):
            pid = int(row["phase_id"])
            phase_row = phases[phases["phase_id"] == pid].iloc[0]
            print(f"#{rank_pos} match: Phase {pid} ({row['type']} started {row['start_month']}), "
                  f"distance={row['distance']:.2f}")
            print(f"    What happened after this point: {phase_row['type']} phase, "
                  f"{phase_row['duration_months']} months, {phase_row['pct_move']:+.1f}% move, "
                  f"ended {phase_row['end_month']}")
            print()
            analog_records.append({
                "rank": rank_pos, "phase_id": pid, "type": str(row["type"]),
                "start_month": str(row["start_month"]), "distance": round(float(row["distance"]), 3),
                "followed_by_type": str(phase_row["type"]),
                "followed_by_duration_months": int(phase_row["duration_months"]),
                "followed_by_pct_move": float(phase_row["pct_move"]),
                "followed_by_end_month": str(phase_row["end_month"]),
            })

    # Duration/magnitude context for the current ongoing phase
    current_phase = phases.iloc[-1]  # last row = current ongoing phase
    elapsed_months = current_phase["duration_months"]
    elapsed_move = current_phase["pct_move"]
    ctx = duration_context(phases, current_phase["type"], elapsed_months, elapsed_move)

    print("=== Current phase vs historical phases of the same type ===")
    print(f"Current: {current_phase['type']} phase, running {elapsed_months} months, {elapsed_move:+.1f}% so far "
          f"(started {current_phase['start_month']})")
    if ctx:
        print(f"Historical {current_phase['type']} phases (n={ctx['n']}): "
              f"duration min/median/max = {ctx['duration_min']}/{ctx['duration_median']}/{ctx['duration_max']} months, "
              f"move min/median/max = {ctx['move_min']:.1f}%/{ctx['move_median']:.1f}%/{ctx['move_max']:.1f}%")
        print(f"Current duration is longer than {ctx['duration_percentile']:.0f}% of past {current_phase['type']} phases.")
    else:
        print("No completed historical phases of this type to compare against.")

    # Persist everything the dashboard needs
    out = {
        "current_snapshot": {
            "month": str(current["month"].date()),
            "RSI6": round(float(current["RSI6"]), 2) if pd.notna(current["RSI6"]) else None,
            "RSI14": round(float(current["RSI14"]), 2) if pd.notna(current["RSI14"]) else None,
            "MACD_hist_pct": round(float(current["MACD_hist_pct"]), 3) if pd.notna(current["MACD_hist_pct"]) else None,
            "Price_vs_MAlong_pct": round(float(current["Price_vs_MAlong_pct"]), 2) if pd.notna(current["Price_vs_MAlong_pct"]) else None,
            "pct_off_high": round(float(current["pct_off_high"]), 2) if pd.notna(current["pct_off_high"]) else None,
            "pct_above_low": round(float(current["pct_above_low"]), 2) if pd.notna(current["pct_above_low"]) else None,
        },
        "nearest_analogs": analog_records,
        "current_phase": {
            "type": str(current_phase["type"]),
            "start_month": str(current_phase["start_month"]),
            "elapsed_months": int(elapsed_months),
            "elapsed_pct_move": float(elapsed_move),
        },
        "duration_context": {
            "n": int(ctx["n"]), "duration_min": int(ctx["duration_min"]),
            "duration_median": float(ctx["duration_median"]), "duration_max": int(ctx["duration_max"]),
            "move_min": float(ctx["move_min"]), "move_median": float(ctx["move_median"]), "move_max": float(ctx["move_max"]),
            "duration_percentile": round(float(ctx["duration_percentile"]), 1),
        } if ctx else None,
    }
    with open(os.path.join(DATA_DIR, "current_status.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
