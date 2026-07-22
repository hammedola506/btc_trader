"""
Trading style selection. This is what makes the bot behave differently
depending on whether you want to day-trade or swing-trade BTC/USDT -
one question up front sets the timeframe, how patient the stops are,
and how selective the bot is about entering trades.
"""

PROFILES = {
    "daily": {
        "timeframe": "15m",
        "candle_lookback": 200,
        "poll_interval_seconds": 60,
        # FIX: raised from 60 → 80.  Backtest shows 60-79 range has negative
        # expected value (14-28% WR).  Only 80+ trades justify execution after
        # scoring fixes reduce score inflation.
        "min_confidence": 80,
        "stop_loss_atr_mult": 1.2,
        "take_profit_atr_mult": 2.0,
        "description": (
            "Day trading: reads 15-minute candles, checks the market every "
            "minute, trades more frequently with tighter stops. Faster "
            "in-and-out, more trades, smaller moves per trade."
        ),
    },
    "weekly": {
        "timeframe": "4h",
        "candle_lookback": 200,
        "poll_interval_seconds": 3600,
        # FIX: raised from 70 → 80 to match the daily profile floor.
        "min_confidence": 80,
        "stop_loss_atr_mult": 2.5,
        "take_profit_atr_mult": 5.0,
        "description": (
            "Swing/weekly trading: reads 4-hour candles, checks the market "
            "hourly, holds positions for days. Fewer, higher-conviction "
            "trades with wider stops to ride bigger moves."
        ),
    },
}


def apply_profile(style, config_module):
    """Overwrite the relevant settings on the config module in place."""
    if style not in PROFILES:
        raise ValueError(f"Unknown trading style '{style}', choose from {list(PROFILES)}")

    profile = PROFILES[style]
    config_module.TIMEFRAME = profile["timeframe"]
    config_module.CANDLE_LOOKBACK = profile["candle_lookback"]
    config_module.POLL_INTERVAL_SECONDS = profile["poll_interval_seconds"]
    config_module.MIN_CONFIDENCE_TO_TRADE = profile["min_confidence"]
    config_module.STOP_LOSS_ATR_MULT = profile["stop_loss_atr_mult"]
    config_module.TAKE_PROFIT_ATR_MULT = profile["take_profit_atr_mult"]
    return profile


def ask_trading_style():
    """Interactively ask the user which style to trade, return 'daily' or 'weekly'."""
    print("\nHow do you want this bot to trade BTC/USDT?")
    print("  1) Daily  - " + PROFILES["daily"]["description"])
    print("  2) Weekly - " + PROFILES["weekly"]["description"])

    while True:
        choice = input("\nEnter 1 for Daily or 2 for Weekly: ").strip()
        if choice == "1":
            return "daily"
        if choice == "2":
            return "weekly"
        print("Please enter 1 or 2.")
