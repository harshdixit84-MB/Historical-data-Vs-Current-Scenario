"""
For each detected Nifty cycle phase (from detect_cycles.py), rank sector
indices by their return during that phase, and by their return RELATIVE to
Nifty (true leadership = outperformance, not just a rising tide).

Sectors with shorter history (ETF-proxy sectors: Auto, FMCG, Metal, Energy,
Realty, Fin Service) will show "no data" for phases before their data starts
— this is a real data limitation (see README), not a bug.

Output:
    data/sector_leadership.csv  — one row per (phase, sector)
    data/sector_leadership.json

Run locally after detect_cycles.py has produced data/cycles_monthly.csv:
    python scripts/sector_leadership.py
"""

import os
import json
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SECTOR_DIR = os.path.join(DATA_DIR, "sectors")
CYCLES_CSV = os.path.join(DATA_DIR, "cycles_monthly.csv")
NIFTY_CSV = os.path.join(DATA_DIR, "nifty50.csv")

SECTOR_FILES = {
    "Bank": "nifty_bank.csv",
    "IT": "nifty_it.csv",
    "Pharma": "nifty_pharma.csv",
    "PSU Bank": "nifty_psu_bank.csv",
    "Midcap100": "nifty_midcap100.csv",
    "Auto": "nifty_auto.csv",
    "FMCG": "nifty_fmcg.csv",
    "Metal": "nifty_metal.csv",
    "Energy": "nifty_energy.csv",
    "Realty": "nifty_realty.csv",
    "Fin Service": "nifty_fin_service.csv",
}


def load_monthly_close(path):
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    monthly_close = df["Close"].resample("ME").last().dropna()
    return monthly_close


def phase_return(monthly_close: pd.Series, start_month: str, end_month: str):
    """Return % change of the series between the two month-end dates
    closest to (>=) start_month and (<=) end_month. Returns None if the
    series doesn't cover that range."""
    start_ts = pd.Timestamp(start_month)
    end_ts = pd.Timestamp(end_month)

    covering = monthly_close[(monthly_close.index >= start_ts - pd.Timedelta(days=20))]
    if covering.empty or monthly_close.index.min() > start_ts:
        return None
    if monthly_close.index.max() < end_ts - pd.Timedelta(days=20):
        return None

    start_val = monthly_close.asof(start_ts)
    end_val = monthly_close.asof(end_ts)
    if pd.isna(start_val) or pd.isna(end_val):
        return None
    return (end_val - start_val) / start_val * 100


def main():
    phases = pd.read_csv(CYCLES_CSV).to_dict("records")

    nifty_close = load_monthly_close(NIFTY_CSV)
    sector_series = {}
    for name, fname in SECTOR_FILES.items():
        path = os.path.join(SECTOR_DIR, fname)
        if os.path.exists(path):
            sector_series[name] = load_monthly_close(path)

    rows = []
    for p in phases:
        nifty_ret = phase_return(nifty_close, p["start_month"], p["end_month"])
        phase_rows = []
        for sector, series in sector_series.items():
            ret = phase_return(series, p["start_month"], p["end_month"])
            if ret is None:
                phase_rows.append({
                    "phase_id": p["phase_id"], "type": p["type"],
                    "start_month": p["start_month"], "end_month": p["end_month"],
                    "sector": sector, "sector_return_pct": None,
                    "nifty_return_pct": round(nifty_ret, 2) if nifty_ret is not None else None,
                    "relative_return_pct": None, "rank_by_relative": None,
                })
            else:
                rel = ret - nifty_ret if nifty_ret is not None else None
                phase_rows.append({
                    "phase_id": p["phase_id"], "type": p["type"],
                    "start_month": p["start_month"], "end_month": p["end_month"],
                    "sector": sector, "sector_return_pct": round(ret, 2),
                    "nifty_return_pct": round(nifty_ret, 2) if nifty_ret is not None else None,
                    "relative_return_pct": round(rel, 2) if rel is not None else None,
                    "rank_by_relative": None,
                })

        # rank sectors that have data, by relative outperformance, best first
        ranked = sorted(
            [r for r in phase_rows if r["relative_return_pct"] is not None],
            key=lambda r: r["relative_return_pct"], reverse=True,
        )
        for rank, r in enumerate(ranked, start=1):
            r["rank_by_relative"] = rank

        rows.extend(phase_rows)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(os.path.join(DATA_DIR, "sector_leadership.csv"), index=False)
    with open(os.path.join(DATA_DIR, "sector_leadership.json"), "w") as f:
        json.dump(rows, f, indent=2)

    print("=== Sector leadership by phase (ranked by outperformance vs Nifty) ===\n")
    for p in phases:
        pid = p["phase_id"]
        print(f"Phase {pid} ({p['type']}, {p['start_month']} to {p['end_month']}, Nifty {p['pct_move']}%):")
        phase_ranked = sorted(
            [r for r in rows if r["phase_id"] == pid and r["rank_by_relative"] is not None],
            key=lambda r: r["rank_by_relative"],
        )
        if not phase_ranked:
            print("   (no sector had sufficient data for this phase)")
        for r in phase_ranked:
            print(f"   #{r['rank_by_relative']:<2} {r['sector']:<12} {r['sector_return_pct']:>8}%  "
                  f"(vs Nifty {r['nifty_return_pct']:>8}%, relative {r['relative_return_pct']:>+7}%)")
        no_data = [r["sector"] for r in rows if r["phase_id"] == pid and r["sector_return_pct"] is None]
        if no_data:
            print(f"   [no data: {', '.join(no_data)}]")
        print()


if __name__ == "__main__":
    main()
