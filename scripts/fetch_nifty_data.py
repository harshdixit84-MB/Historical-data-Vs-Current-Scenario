"""
Fetch historical daily OHLCV data for Nifty 50 and major sector indices.
Runs inside GitHub Actions (which has open internet access) — not meant
to be run in a sandboxed/restricted-network environment.

Output:
    data/nifty50.csv
    data/sectors/<sector_name>.csv
"""

import os
import time
import pandas as pd
import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SECTOR_DIR = os.path.join(DATA_DIR, "sectors")

START_DATE = "2005-01-01"

# Each entry is a list of candidate tickers, tried in order. Real Nifty index
# symbols (^NSEI etc.) are preferred where Yahoo still supports them; sector
# indices Yahoo doesn't track directly fall back to a tracking ETF (NSE-listed
# equity, ticker.NS) as a close proxy. The first candidate that returns a
# real multi-row history wins.
INDICES = {
    "nifty50": ["^NSEI"],
    "nifty_bank": ["^NSEBANK", "BANKBEES.NS"],
    "nifty_it": ["^CNXIT", "ITBEES.NS"],
    "nifty_pharma": ["^CNXPHARMA", "PHARMABEES.NS"],
    "nifty_midcap100": ["^NSEMDCP50"],
    "nifty_auto": ["AUTOBEES.NS", "AUTOIETF.NS", "^CNXAUTO"],
    "nifty_fmcg": ["FMCGIETF.NS", "^CNXFMCG"],
    "nifty_metal": ["METAL.NS", "METALIETF.NS", "GROWWMETAL.NS"],
    "nifty_energy": ["ENERGY.NS", "MOENERGY.NS"],
    "nifty_realty": ["MOREALTY.NS"],
    "nifty_psu_bank": ["PSUBNKBEES.NS"],
    "nifty_fin_service": ["BFSI.NS", "FINIETF.NS"],
    # No ETF currently tracks Nifty Media; kept as best-effort only.
    "nifty_media": ["^CNXMEDIA"],
}

MIN_ROWS = 50  # below this, treat the candidate as a failed/placeholder fetch


def fetch_one(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, start=START_DATE, progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.index.name = "Date"
    return df


def fetch_with_fallback(name: str, candidates: list) -> tuple:
    """Try each candidate ticker in order; return (df, ticker_used) for the
    first one that returns a real history, or (empty df, None) if all fail."""
    for ticker in candidates:
        try:
            df = fetch_one(ticker)
        except Exception as e:
            print(f"  [FAIL] {ticker}: {e}")
            continue
        if len(df) >= MIN_ROWS:
            print(f"  [OK]   {ticker}: {len(df)} rows")
            return df, ticker
        else:
            print(f"  [SKIP] {ticker}: only {len(df)} row(s), trying next candidate")
    return pd.DataFrame(), None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SECTOR_DIR, exist_ok=True)

    summary = []

    for name, candidates in INDICES.items():
        print(f"Fetching {name} (candidates: {candidates})...")
        df, used_ticker = fetch_with_fallback(name, candidates)
        time.sleep(1)  # be polite to the API

        if df.empty:
            summary.append((name, "ALL FAILED", "FAILED", ""))
            continue

        out_path = (
            os.path.join(DATA_DIR, f"{name}.csv")
            if name == "nifty50"
            else os.path.join(SECTOR_DIR, f"{name}.csv")
        )
        df.to_csv(out_path)
        summary.append(
            (name, used_ticker, "OK", f"{len(df)} rows, {df.index.min().date()} to {df.index.max().date()}")
        )

    print("\n=== Fetch summary ===")
    for name, ticker, status, info in summary:
        print(f"{name:20s} {str(ticker):16s} {status:8s} {info}")


if __name__ == "__main__":
    main()
