"""
Detect bull/bear market cycles in Nifty 50 daily closing data using a
percentage zigzag (classic 20% peak-to-trough / trough-to-peak convention
for defining bull vs bear markets), then snapshot key indicators (50-DMA,
200-DMA, RSI-14, price vs 200-DMA %) at every reversal point.

This is Step 2 of the project — the foundation the present-vs-past cycle
comparator and sector-leadership analysis will build on.

Output:
    data/cycles.csv   — one row per detected phase
    data/cycles.json  — same data, JSON format

Run locally (no internet needed once data/nifty50.csv exists):
    python scripts/detect_cycles.py
"""

import os
import json
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
NIFTY_CSV = os.path.join(DATA_DIR, "nifty50.csv")

ZIGZAG_THRESHOLD = 0.20  # 20% — standard bull/bear market convention
CHOPPY_MIN_DURATION_DAYS = 250  # trading days
CHOPPY_MAX_RETRACE = 0.12  # 12% intra-phase counter-move


def load_price_data():
    df = pd.read_csv(NIFTY_CSV, index_col="Date", parse_dates=True)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def compute_indicators(df):
    df = df.copy()
    df["50DMA"] = df["Close"].rolling(50).mean()
    df["200DMA"] = df["Close"].rolling(200).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["RSI14"] = 100 - (100 / (1 + rs))

    df["Price_vs_200DMA_pct"] = (df["Close"] - df["200DMA"]) / df["200DMA"] * 100
    return df


def zigzag(prices: pd.Series, threshold: float):
    """Returns a list of (index_position, date, price, kind) pivots,
    kind is 'trough' or 'peak'. First pivot is the series start."""
    idx = prices.index
    vals = prices.values

    pivots = [(0, idx[0], vals[0], "start")]
    trend = None
    last_pivot_pos = 0
    last_pivot_price = vals[0]

    for i in range(1, len(vals)):
        price = vals[i]
        change = (price - last_pivot_price) / last_pivot_price

        if trend is None:
            if change >= threshold:
                trend = "up"
                pivots[0] = (0, idx[0], vals[0], "trough")
                last_pivot_pos, last_pivot_price = i, price
            elif change <= -threshold:
                trend = "down"
                pivots[0] = (0, idx[0], vals[0], "peak")
                last_pivot_pos, last_pivot_price = i, price
        elif trend == "up":
            if price >= last_pivot_price:
                last_pivot_pos, last_pivot_price = i, price
            elif (price - last_pivot_price) / last_pivot_price <= -threshold:
                pivots.append((last_pivot_pos, idx[last_pivot_pos], last_pivot_price, "peak"))
                trend = "down"
                last_pivot_pos, last_pivot_price = i, price
        elif trend == "down":
            if price <= last_pivot_price:
                last_pivot_pos, last_pivot_price = i, price
            elif (price - last_pivot_price) / last_pivot_price >= threshold:
                pivots.append((last_pivot_pos, idx[last_pivot_pos], last_pivot_price, "trough"))
                trend = "up"
                last_pivot_pos, last_pivot_price = i, price

    # final running pivot (the current, still-forming swing)
    final_kind = "peak" if trend == "up" else "trough" if trend == "down" else "start"
    pivots.append((last_pivot_pos, idx[last_pivot_pos], last_pivot_price, final_kind))

    return pivots


def find_confirmation(df, start_pos, end_pos, phase_type):
    """First date after the pivot where price crosses back above (bull) or
    below (bear) its 200-DMA — a simple, transparent 'trend confirmed' rule."""
    window = df.iloc[start_pos:end_pos + 1]
    if phase_type == "Bull":
        confirmed = window[window["Close"] > window["200DMA"]]
    else:
        confirmed = window[window["Close"] < window["200DMA"]]
    if confirmed.empty:
        return None, None
    conf_date = confirmed.index[0]
    lag_days = (conf_date - window.index[0]).days
    return conf_date, lag_days


def build_phases(df, pivots):
    phases = []
    for i in range(len(pivots) - 1):
        start_pos, start_date, start_price, start_kind = pivots[i]
        end_pos, end_date, end_price, end_kind = pivots[i + 1]

        if start_kind == "start":
            phase_type = "Bull" if end_kind == "peak" else "Bear"
        else:
            phase_type = "Bull" if start_kind == "trough" else "Bear"

        segment = df.iloc[start_pos:end_pos + 1]
        pct_move = (end_price - start_price) / start_price * 100
        duration_trading_days = end_pos - start_pos
        duration_calendar_days = (end_date - start_date).days

        # choppiness: biggest counter-move against the phase direction
        if phase_type == "Bull":
            running_peak = segment["Close"].cummax()
            counter_move = ((segment["Close"] - running_peak) / running_peak).min()
            counter_move = abs(counter_move)
        else:
            running_trough = segment["Close"].cummin()
            counter_move = ((segment["Close"] - running_trough) / running_trough).max()

        is_choppy = (duration_trading_days >= CHOPPY_MIN_DURATION_DAYS) and (counter_move >= CHOPPY_MAX_RETRACE)

        conf_date, conf_lag = find_confirmation(df, start_pos, end_pos, phase_type)

        start_row = df.iloc[start_pos]
        end_row = df.iloc[end_pos]

        phases.append({
            "phase_id": i + 1,
            "type": phase_type,
            "choppy": bool(is_choppy),
            "start_date": str(start_date.date()),
            "end_date": str(end_date.date()),
            "duration_trading_days": int(duration_trading_days),
            "duration_calendar_days": int(duration_calendar_days),
            "pct_move": round(pct_move, 2),
            "max_counter_move_pct": round(counter_move * 100, 2),
            "start_price": round(start_price, 2),
            "end_price": round(end_price, 2),
            "start_50dma": round(start_row["50DMA"], 2) if pd.notna(start_row["50DMA"]) else None,
            "start_200dma": round(start_row["200DMA"], 2) if pd.notna(start_row["200DMA"]) else None,
            "start_rsi14": round(start_row["RSI14"], 2) if pd.notna(start_row["RSI14"]) else None,
            "start_price_vs_200dma_pct": round(start_row["Price_vs_200DMA_pct"], 2) if pd.notna(start_row["Price_vs_200DMA_pct"]) else None,
            "end_50dma": round(end_row["50DMA"], 2) if pd.notna(end_row["50DMA"]) else None,
            "end_200dma": round(end_row["200DMA"], 2) if pd.notna(end_row["200DMA"]) else None,
            "end_rsi14": round(end_row["RSI14"], 2) if pd.notna(end_row["RSI14"]) else None,
            "trend_confirmed_date": str(conf_date.date()) if conf_date is not None else None,
            "trend_confirmed_lag_days": conf_lag,
        })
    return phases


def main():
    df = load_price_data()
    df = compute_indicators(df)
    pivots = zigzag(df["Close"], ZIGZAG_THRESHOLD)
    phases = build_phases(df, pivots)

    out_csv = os.path.join(DATA_DIR, "cycles.csv")
    out_json = os.path.join(DATA_DIR, "cycles.json")

    pd.DataFrame(phases).to_csv(out_csv, index=False)
    with open(out_json, "w") as f:
        json.dump(phases, f, indent=2)

    print(f"Detected {len(phases)} phases (threshold={ZIGZAG_THRESHOLD:.0%}).\n")
    print(f"{'#':<4}{'Type':<7}{'Choppy':<8}{'Start':<12}{'End':<12}{'Days':<7}{'Move %':<9}{'Confirmed':<12}{'Lag(d)'}")
    for p in phases:
        print(f"{p['phase_id']:<4}{p['type']:<7}{str(p['choppy']):<8}{p['start_date']:<12}{p['end_date']:<12}"
              f"{p['duration_trading_days']:<7}{p['pct_move']:<9}{str(p['trend_confirmed_date']):<12}{p['trend_confirmed_lag_days']}")


if __name__ == "__main__":
    main()
