"""Exports a compact monthly Nifty 50 close series as JSON for the dashboard chart."""
import os
import json
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
NIFTY_CSV = os.path.join(DATA_DIR, "nifty50.csv")


def main():
    df = pd.read_csv(NIFTY_CSV, index_col="Date", parse_dates=True)
    monthly = df["Close"].resample("ME").last().dropna()
    out = [{"month": str(d.date()), "close": round(float(v), 2)} for d, v in monthly.items()]
    with open(os.path.join(DATA_DIR, "nifty_monthly_close.json"), "w") as f:
        json.dump(out, f)
    print(f"Exported {len(out)} months to nifty_monthly_close.json")


if __name__ == "__main__":
    main()
