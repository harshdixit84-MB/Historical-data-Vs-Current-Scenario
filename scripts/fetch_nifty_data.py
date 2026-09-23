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

# Yahoo Finance tickers for Nifty 50 and major NSE sector indices
INDICES = {
    "nifty50": "^NSEI",
    "nifty_bank": "^NSEBANK",
    "nifty_auto": "^CNXAUTO",
    "nifty_it": "^CNXIT",
    "nifty_pharma": "^CNXPHARMA",
    "nifty_fmcg": "^CNXFMCG",
    "nifty_metal": "^CNXMETAL",
    "nifty_energy": "^CNXENERGY",
    "nifty_realty": "^CNXREALTY",
    "nifty_media": "^CNXMEDIA",
    "nifty_psu_bank": "^CNXPSUBANK",
    "nifty_fin_service": "NIFTY_FIN_SERVICE.NS",
    "nifty_midcap100": "^NSEMDCP50",  # fallback proxy if midcap100 unavailable
}


def fetch_one(name: str, ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, start=START_DATE, progress=False, auto_adjust=False)
    if df.empty:
        print(f"[WARN] No data returned for {name} ({ticker})")
        return df
    # Flatten yfinance's MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.index.name = "Date"
    return df


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SECTOR_DIR, exist_ok=True)

    summary = []

    for name, ticker in INDICES.items():
        print(f"Fetching {name} ({ticker})...")
        try:
            df = fetch_one(name, ticker)
        except Exception as e:
            print(f"[ERROR] {name} ({ticker}): {e}")
            summary.append((name, ticker, "FAILED", str(e)))
            time.sleep(1)
            continue

        if df.empty:
            summary.append((name, ticker, "EMPTY", ""))
            time.sleep(1)
            continue

        out_path = (
            os.path.join(DATA_DIR, f"{name}.csv")
            if name == "nifty50"
            else os.path.join(SECTOR_DIR, f"{name}.csv")
        )
        df.to_csv(out_path)
        summary.append((name, ticker, "OK", f"{len(df)} rows, {df.index.min().date()} to {df.index.max().date()}"))
        time.sleep(1)  # be polite to the API

    print("\n=== Fetch summary ===")
    for name, ticker, status, info in summary:
        print(f"{name:20s} {ticker:20s} {status:8s} {info}")


if __name__ == "__main__":
    main()
