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
import datetime
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASE_URL = "https://harsh-nu.vercel.app/api/option-chain"
SYMBOL = "NIFTY"


def fetch(expiry_index):
    url = f"{BASE_URL}?symbol={SYMBOL}&expiryIndex={expiry_index}"
    req = urllib.request.Request(url, headers={"User-Agent": "nifty-cycle-study/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def parse_expiry(s):
    # format like "29SEP2026"
    return datetime.datetime.strptime(s, "%d%b%Y")


def find_monthly_indices(expiries):
    """Nifty has weekly expiries now; the true 'monthly' contract for a given
    calendar month is the LAST expiry that falls within that month. Returns
    (current_month_index, next_month_index) into the given expiries list."""
    parsed = [parse_expiry(e) for e in expiries]
    by_month = {}
    for i, d in enumerate(parsed):
        key = (d.year, d.month)
        by_month.setdefault(key, []).append(i)

    months_sorted = sorted(by_month.keys())
    if not months_sorted:
        return 0, 0

    current_month_key = months_sorted[0]
    current_month_idx = max(by_month[current_month_key])  # last expiry of that month

    next_month_idx = current_month_idx
    if len(months_sorted) > 1:
        next_month_key = months_sorted[1]
        next_month_idx = max(by_month[next_month_key])

    return current_month_idx, next_month_idx


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    result = {"fetched_at": None, "current_month": None, "next_month": None, "errors": []}
    result["fetched_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    # First call (expiryIndex=0) just to get the full available_expiries list
    try:
        probe = fetch(0)
    except Exception as e:
        result["errors"].append(f"probe: {e}")
        with open(os.path.join(DATA_DIR, "option_chain.json"), "w") as f:
            json.dump(result, f, indent=2)
        print(f"[ERROR] probe call failed: {e}")
        return

    expiries = probe.get("available_expiries", [])
    cur_idx, next_idx = find_monthly_indices(expiries)
    print(f"Available expiries: {expiries}")
    print(f"Resolved current-month index={cur_idx} ({expiries[cur_idx] if expiries else '?'}), "
          f"next-month index={next_idx} ({expiries[next_idx] if expiries else '?'})")

    time.sleep(2)

    for label, idx in [("current_month", cur_idx), ("next_month", next_idx)]:
        try:
            data = probe if idx == 0 else fetch(idx)
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
