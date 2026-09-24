"""
Detect bull/bear market cycles in Nifty 50 using MONTHLY data — since the
study spans 15+ years, all calculations here (moving averages, RSI, MACD,
zigzag pivots) are done on monthly-aggregated closes rather than daily,
per project decision. This trades exact-day pivot precision for a cleaner,
lower-noise view appropriate to a multi-decade study.

Monthly equivalents used for daily conventions:
    50-day MA  -> 3-month MA   (~50 trading days ~ 2.3 months)
    200-day MA -> 10-month MA  (~200 trading days ~ 9.5 months)
    RSI-14 (daily) -> RSI-14 computed on monthly closes (14-month lookback)
    MACD(12,26,9) -> same periods, applied to monthly closes (standard
                      "monthly MACD", a well-established long-term variant)
    52-week high/low -> trailing 12-month high/low

Output:
    data/cycles_monthly.csv
    data/cycles_monthly.json

Run locally (no internet needed once data/nifty50.csv exists):
    python scripts/detect_cycles.py
"""

import os
import json
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
NIFTY_CSV = os.path.join(DATA_DIR, "nifty50.csv")

ZIGZAG_THRESHOLD = 0.20   # 20% - standard bull/bear market convention
SUBSWING_THRESHOLD = 0.10  # 10% - used only to count corrections within a phase

MA_SHORT = 3   # months, ~50-day equivalent
MA_LONG = 10   # months, ~200-day equivalent
RANGE_MONTHS = 12  # trailing high/low window, ~52-week equivalent


def load_price_data():
    df = pd.read_csv(NIFTY_CSV, index_col="Date", parse_dates=True)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def resample_monthly(df):
    monthly = pd.DataFrame({
        "Open": df["Open"].resample("ME").first(),
        "High": df["High"].resample("ME").max(),
        "Low": df["Low"].resample("ME").min(),
        "Close": df["Close"].resample("ME").last(),
    }).dropna()
    return monthly


def compute_indicators(df):
    df = df.copy()
    df["MA_short"] = df["Close"].rolling(MA_SHORT).mean()
    df["MA_long"] = df["Close"].rolling(MA_LONG).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["RSI14"] = 100 - (100 / (1 + rs))

    # Faster secondary RSI (6-month) — 14-month RSI is too smoothed to catch
    # reversal extremes on monthly data; a shorter lookback is needed to see
    # genuine overbought/oversold readings at turning points.
    avg_gain6 = gain.ewm(alpha=1 / 6, min_periods=6, adjust=False).mean()
    avg_loss6 = loss.ewm(alpha=1 / 6, min_periods=6, adjust=False).mean()
    rs6 = avg_gain6 / avg_loss6
    df["RSI6"] = 100 - (100 / (1 + rs6))

    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
    # Normalized so magnitude is comparable across eras where Nifty's price
    # level itself grew ~15x (raw MACD points aren't comparable 2008 vs 2025).
    df["MACD_hist_pct"] = df["MACD_hist"] / df["Close"] * 100

    df["range_high"] = df["Close"].rolling(RANGE_MONTHS, min_periods=1).max()
    df["range_low"] = df["Close"].rolling(RANGE_MONTHS, min_periods=1).min()
    df["pct_off_high"] = (df["Close"] - df["range_high"]) / df["range_high"] * 100
    df["pct_above_low"] = (df["Close"] - df["range_low"]) / df["range_low"] * 100

    df["Price_vs_MAlong_pct"] = (df["Close"] - df["MA_long"]) / df["MA_long"] * 100
    df["ma_regime"] = np.where(df["MA_short"] > df["MA_long"], 1, 0)
    return df


def zigzag(prices: pd.Series, threshold: float):
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

    final_kind = "peak" if trend == "up" else "trough" if trend == "down" else "start"
    pivots.append((last_pivot_pos, idx[last_pivot_pos], last_pivot_price, final_kind))
    return pivots


def count_subswings(prices: pd.Series, threshold: float) -> int:
    sub_pivots = zigzag(prices, threshold)
    return max(0, len(sub_pivots) - 2)


def find_confirmation(df, start_pos, end_pos, phase_type):
    """First month after the pivot where close crosses back above (Bull) or
    below (Bear) the long (10-month) moving average."""
    window = df.iloc[start_pos:end_pos + 1]
    if phase_type == "Bull":
        confirmed = window[window["Close"] > window["MA_long"]]
    else:
        confirmed = window[window["Close"] < window["MA_long"]]
    if confirmed.empty:
        return None, None
    conf_date = confirmed.index[0]
    lag_months = window.index.get_loc(conf_date)
    return conf_date, lag_months


def last_cross_before(df, pos, phase_type):
    """Most recent MA_short/MA_long cross (golden/death cross equivalent)
    at or before the pivot month."""
    regime = df["ma_regime"].iloc[:pos + 1]
    target_diff = 1 if phase_type == "Bull" else -1
    changes = regime[regime.diff() == target_diff]
    if changes.empty:
        return None, None
    cross_date = changes.index[-1]
    lead_months = df.index.get_loc(df.index[pos]) - df.index.get_loc(cross_date)
    return cross_date, lead_months


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
        duration_months = end_pos - start_pos
        duration_calendar_days = (end_date - start_date).days

        num_subswings = count_subswings(segment["Close"], SUBSWING_THRESHOLD)
        is_choppy = num_subswings >= 2

        if phase_type == "Bull":
            running_peak = segment["Close"].cummax()
            counter_move = abs(((segment["Close"] - running_peak) / running_peak).min())
        else:
            running_trough = segment["Close"].cummin()
            counter_move = ((segment["Close"] - running_trough) / running_trough).max()

        conf_date, conf_lag = find_confirmation(df, start_pos, end_pos, phase_type)
        cross_date, cross_lead = last_cross_before(df, start_pos, phase_type)

        start_row = df.iloc[start_pos]
        end_row = df.iloc[end_pos]

        phases.append({
            "phase_id": i + 1,
            "type": phase_type,
            "choppy": bool(is_choppy),
            "num_10pct_subswings": int(num_subswings),
            "start_month": str(start_date.date()),
            "end_month": str(end_date.date()),
            "duration_months": int(duration_months),
            "duration_calendar_days": int(duration_calendar_days),
            "pct_move": round(pct_move, 2),
            "max_counter_move_pct": round(counter_move * 100, 2),
            "start_price": round(start_price, 2),
            "end_price": round(end_price, 2),
            "start_ma3": round(start_row["MA_short"], 2) if pd.notna(start_row["MA_short"]) else None,
            "start_ma10": round(start_row["MA_long"], 2) if pd.notna(start_row["MA_long"]) else None,
            "start_rsi14": round(start_row["RSI14"], 2) if pd.notna(start_row["RSI14"]) else None,
            "start_rsi6": round(start_row["RSI6"], 2) if pd.notna(start_row["RSI6"]) else None,
            "start_macd": round(start_row["MACD"], 2) if pd.notna(start_row["MACD"]) else None,
            "start_macd_signal": round(start_row["MACD_signal"], 2) if pd.notna(start_row["MACD_signal"]) else None,
            "start_macd_hist": round(start_row["MACD_hist"], 2) if pd.notna(start_row["MACD_hist"]) else None,
            "start_macd_hist_pct": round(start_row["MACD_hist_pct"], 3) if pd.notna(start_row["MACD_hist_pct"]) else None,
            "start_price_vs_ma10_pct": round(start_row["Price_vs_MAlong_pct"], 2) if pd.notna(start_row["Price_vs_MAlong_pct"]) else None,
            "start_pct_off_12m_high": round(start_row["pct_off_high"], 2) if pd.notna(start_row["pct_off_high"]) else None,
            "start_pct_above_12m_low": round(start_row["pct_above_low"], 2) if pd.notna(start_row["pct_above_low"]) else None,
            "end_ma3": round(end_row["MA_short"], 2) if pd.notna(end_row["MA_short"]) else None,
            "end_ma10": round(end_row["MA_long"], 2) if pd.notna(end_row["MA_long"]) else None,
            "end_rsi14": round(end_row["RSI14"], 2) if pd.notna(end_row["RSI14"]) else None,
            "trend_confirmed_month": str(conf_date.date()) if conf_date is not None else None,
            "trend_confirmed_lag_months": conf_lag,
            "preceding_ma_cross_month": str(cross_date.date()) if cross_date is not None else None,
            "preceding_ma_cross_lead_months": cross_lead,
        })
    return phases


def main():
    daily = load_price_data()
    monthly = resample_monthly(daily)
    monthly = compute_indicators(monthly)
    pivots = zigzag(monthly["Close"], ZIGZAG_THRESHOLD)
    phases = build_phases(monthly, pivots)

    out_csv = os.path.join(DATA_DIR, "cycles_monthly.csv")
    out_json = os.path.join(DATA_DIR, "cycles_monthly.json")

    pd.DataFrame(phases).to_csv(out_csv, index=False)
    with open(out_json, "w") as f:
        json.dump(phases, f, indent=2)

    print(f"Detected {len(phases)} phases on MONTHLY data (threshold={ZIGZAG_THRESHOLD:.0%}).\n")
    print(f"{'#':<4}{'Type':<7}{'Sub':<5}{'Start':<12}{'End':<12}{'Mo':<5}{'Move %':<9}{'Confirmed':<12}{'Lag(mo)':<9}{'MA Cross':<12}{'Lead(mo)'}")
    for p in phases:
        print(f"{p['phase_id']:<4}{p['type']:<7}{p['num_10pct_subswings']:<5}{p['start_month']:<12}{p['end_month']:<12}"
              f"{p['duration_months']:<5}{p['pct_move']:<9}{str(p['trend_confirmed_month']):<12}{str(p['trend_confirmed_lag_months']):<9}"
              f"{str(p['preceding_ma_cross_month']):<12}{p['preceding_ma_cross_lead_months']}")

    latest = monthly.iloc[-1]
    print("\n=== Current status (latest closed month) ===")
    print(f"Month: {monthly.index[-1].date()}  Close: {latest['Close']:.2f}")
    print(f"RSI14: {latest['RSI14']:.2f}   RSI6: {latest['RSI6']:.2f}")
    print(f"MACD hist (% of price): {latest['MACD_hist_pct']:.3f}%")
    print(f"Price vs 10-mo MA: {latest['Price_vs_MAlong_pct']:.2f}%")
    print(f"Off 12-mo high: {latest['pct_off_high']:.2f}%   Above 12-mo low: {latest['pct_above_low']:.2f}%")
    print(f"MA regime (3mo>10mo = uptrend): {'Bullish' if latest['ma_regime'] == 1 else 'Bearish'}")


if __name__ == "__main__":
    main()
