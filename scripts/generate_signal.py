"""
Combines two independent things already computed elsewhere in this project:
  1. The PRICE-side lean: how many of our own downside/upside confirmation
     tiers (from reversal_projection.py) are already active right now.
  2. The OPTIONS-side lean: today's PCR/bias for the current and next month
     contracts (from fetch_option_chain.py, sourced from the live Angel One
     endpoint).

Only when both agree does this produce a directional signal (PE or CE) with
a specific, liquid strike. When they disagree, or either is neutral, it
says so plainly rather than forcing a pick.

This is a MECHANICAL, RULE-BASED output — not personal financial advice.
Options can expire worthless; nothing here should be read as a
recommendation to trade.

Output: data/trade_signal.json
Run (after both current_status.json and option_chain.json exist):
    python scripts/generate_signal.py
"""

import os
import json
import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
STATUS_JSON = os.path.join(DATA_DIR, "current_status.json")
OPTION_CHAIN_JSON = os.path.join(DATA_DIR, "option_chain.json")
OUT_JSON = os.path.join(DATA_DIR, "trade_signal.json")

DAYS_TO_EXPIRY_CAUTION = 3  # below this, flag the near-month contract as high-decay-risk


def parse_expiry(s):
    return datetime.datetime.strptime(s, "%d%b%Y").date()


def price_side_lean(projection):
    down_tiers = projection.get("downside_confirmation_tiers") or []
    up_tiers = projection.get("upside_recovery_tiers") or []
    down_active = sum(1 for t in down_tiers if t["already_true"])
    up_active = sum(1 for t in up_tiers if t["already_true"])

    if down_active > up_active:
        lean = "Bearish"
    elif up_active > down_active:
        lean = "Bullish"
    else:
        lean = "Neutral"

    return {
        "lean": lean,
        "downside_tiers_active": down_active, "downside_tiers_total": len(down_tiers),
        "upside_tiers_active": up_active, "upside_tiers_total": len(up_tiers),
    }


def pick_strike(levels, spot, direction):
    """levels: list of {strike, oi}, sorted by OI desc (as the source gives them).
    direction='below' picks the highest strike <= spot (for a Put);
    direction='above' picks the lowest strike >= spot (for a Call).
    Falls back to the highest-OI level in the list if none qualifies."""
    if not levels:
        return None
    candidates = [l for l in levels if (l["strike"] <= spot if direction == "below" else l["strike"] >= spot)]
    if candidates:
        if direction == "below":
            return max(candidates, key=lambda l: l["strike"])
        else:
            return min(candidates, key=lambda l: l["strike"])
    return max(levels, key=lambda l: l["oi"])  # fallback: most liquid strike available


def build_expiry_view(label, data, spot, today):
    if not data:
        return {"label": label, "available": False}

    expiry_date = parse_expiry(data["expiry"])
    days_to_expiry = (expiry_date - today).days
    high_decay_risk = days_to_expiry <= DAYS_TO_EXPIRY_CAUTION

    pe_strike = pick_strike(data["support"], spot, "below")
    ce_strike = pick_strike(data["resistance"], spot, "above")

    return {
        "label": label, "available": True, "expiry": data["expiry"],
        "days_to_expiry": days_to_expiry, "high_decay_risk": high_decay_risk,
        "pcr": data["pcr"], "option_chain_bias": data["bias"], "option_chain_confidence": data["confidence"],
        "max_pain": data["max_pain"],
        "candidate_pe_strike": pe_strike, "candidate_ce_strike": ce_strike,
    }


def combine_signal(price, expiry_view):
    if not expiry_view["available"]:
        return {"signal": "No data", "reason": "Option chain data unavailable for this expiry."}

    oc_bias = expiry_view["option_chain_bias"]
    p_lean = price["lean"]

    if p_lean == "Neutral" or oc_bias == "Neutral":
        return {
            "signal": "No clear trade",
            "reason": f"Price-trend signal is {p_lean} and option-chain signal is {oc_bias} — "
                      f"at least one side isn't showing a clear lean, so the two aren't confirming each other.",
        }

    if p_lean == oc_bias:
        instrument = "PE" if p_lean == "Bearish" else "CE"
        strike_info = expiry_view["candidate_pe_strike"] if instrument == "PE" else expiry_view["candidate_ce_strike"]
        return {
            "signal": p_lean,
            "instrument": instrument,
            "strike": strike_info["strike"] if strike_info else None,
            "strike_oi": strike_info["oi"] if strike_info else None,
            "reason": f"Price trend and today's option-chain positioning both lean {p_lean} for the "
                      f"{expiry_view['label']} ({expiry_view['expiry']}) contract.",
        }

    return {
        "signal": "Conflicting",
        "reason": f"Price trend leans {p_lean} but the option chain for {expiry_view['label']} "
                  f"({expiry_view['expiry']}) leans {oc_bias} — the two disagree, so no clean trade case exists right now.",
    }


def main():
    if not (os.path.exists(STATUS_JSON) and os.path.exists(OPTION_CHAIN_JSON)):
        print("Missing current_status.json or option_chain.json — run those scripts first.")
        return

    with open(STATUS_JSON) as f:
        status = json.load(f)
    with open(OPTION_CHAIN_JSON) as f:
        oc = json.load(f)

    projection = status.get("projection", {})
    price = price_side_lean(projection)
    spot = projection.get("latest_close")
    today = datetime.date.today()

    current_view = build_expiry_view("Current month", oc.get("current_month"), spot, today)
    next_view = build_expiry_view("Next month", oc.get("next_month"), spot, today)

    # Prefer current month unless it's in high-decay territory, then prefer next month
    primary = next_view if (current_view.get("high_decay_risk") and next_view["available"]) else current_view

    result = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "spot_reference": spot,
        "spot_reference_note": "Last available daily close (not intraday) — see project notes.",
        "price_side": price,
        "current_month": current_view,
        "next_month": next_view,
        "primary_expiry_used": primary["label"] if primary.get("available") else None,
        "signal": combine_signal(price, primary) if primary.get("available") else {"signal": "No data"},
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
