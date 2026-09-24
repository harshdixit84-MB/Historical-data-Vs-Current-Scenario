"""
Fetches Nifty option chain data (current month + next month expiry) from the
already-deployed, already-authenticated endpoint in the Harsh repo
(harsh-nu.vercel.app/api/option-chain), which handles the Angel One
login/TOTP/quote-fetching internally. This script does NOT need or touch any
broker credentials — it just calls the existing live API.

Output: data/option_chain.json
Run (requires real internet — GitHub Actions, not the sandbox):
    python scripts/fetch_option_chain.py
"""

import os
import json
import time
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASE_URL = "https://harsh-nu.vercel.app/api/option-chain"
SYMBOL = "NIFTY"


def fetch(expiry_index):
    url = f"{BASE_URL}?symbol={SYMBOL}&expiryIndex={expiry_index}"
    req = urllib.request.Request(url, headers={"User-Agent": "nifty-cycle-study/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    result = {"fetched_at": None, "current_month": None, "next_month": None, "errors": []}

    import datetime
    result["fetched_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    for label, idx in [("current_month", 0), ("next_month", 1)]:
        try:
            data = fetch(idx)
            result[label] = data
            print(f"{label} (expiryIndex={idx}): expiry={data.get('expiry')}, "
                  f"spot={data.get('spot_price')}, pcr={data.get('pcr')}, bias={data.get('bias')}")
        except Exception as e:
            result["errors"].append(f"{label}: {e}")
            print(f"[ERROR] {label}: {e}")
        time.sleep(2)  # avoid hammering the Angel One session back-to-back

    with open(os.path.join(DATA_DIR, "option_chain.json"), "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
