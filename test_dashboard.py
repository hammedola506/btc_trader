import os, sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from web import controller

states = {
    "WAIT": {
        "price": 75000.0, "signal": "WAIT", "confidence": 10,
        "reasons": ["Market shows a strong downtrend (ADX=27.7), volatility normal. Looking for setups."],
        "bull_case": ["Price is near 75000 support"],
        "bear_case": ["Price trend is down (EMA9 below EMA21)"],
        "hypothetical_risk": {
            "position_size_btc": 0.05,
            "leverage": 3,
            "margin_required_usdt": 1250.0,
            "liquidation_price": 60000.0,
            "distance_to_liquidation_pct": 20.0
        },
        "position": None, "status": "running", "mode": "TESTNET", "consecutive_errors": 0, "uptime_seconds": 120
    },
    "LONG": {
        "price": 75594.8, "signal": "LONG", "confidence": 35,
        "reasons": ["Market shows a strong downtrend (ADX=27.7), volatility normal. Looking for setups."],
        "bull_case": ["Bullish candlestick pattern detected: bullish_engulfing", "ADX=27.7: trend strong enough to trust"],
        "bear_case": ["Price trend is down (EMA9 below EMA21)"],
        "hypothetical_risk": {
            "position_size_btc": 0.007713,
            "leverage": 5,
            "margin_required_usdt": 116.63,
            "liquidation_price": 60626.98,
            "distance_to_liquidation_pct": 19.8
        },
        "position": None, "status": "running", "mode": "TESTNET", "consecutive_errors": 0, "uptime_seconds": 120
    },
    "MALFORMED": {
        "price": 75594.8, "signal": "WAIT", "confidence": 10,
        "reasons": ["Market shows a strong downtrend (ADX=27.7), volatility normal. Looking for setups."],
        "bull_case": [],
        "bear_case": [],
        "hypothetical_risk": {
            "leverage": 5,
            "margin_required_usdt": 116.63,
            # position_size_btc is intentionally missing
        },
        "position": None, "status": "running", "mode": "TESTNET", "consecutive_errors": 0, "uptime_seconds": 120
    }
}

current_test_state = "WAIT"

controller.get_state = lambda: states[current_test_state]

from web.app import app
from flask import request

@app.route("/api/set_test_state")
def set_state():
    global current_test_state
    current_test_state = request.args.get("state", "WAIT")
    return "OK"

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
