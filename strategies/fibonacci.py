"""
Fibonacci retracement analysis for BTC/USDT.

Finds the most recent significant swing high and swing low, calculates the
standard retracement levels between them, and checks whether the current
price is reacting near one of those levels - the way a trader watches for
a bounce or rejection at a key Fib zone before entering.
"""
import pandas as pd
import numpy as np

# Standard retracement ratios. 0.618 (the "golden ratio") and 0.5 are
# typically the most closely watched.
FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]


def find_swing_points(df, lookback=50):
    """
    Find the most recent significant swing high and swing low within the
    last `lookback` candles. Returns (swing_high, swing_high_idx,
    swing_low, swing_low_idx).
    """
    window = df.iloc[-lookback:]
    swing_high = window["high"].max()
    swing_high_idx = window["high"].idxmax()
    swing_low = window["low"].min()
    swing_low_idx = window["low"].idxmin()
    return swing_high, swing_high_idx, swing_low, swing_low_idx


def calculate_levels(swing_high, swing_low, direction):
    """
    Calculate Fibonacci retracement price levels between a swing high and
    swing low.

    direction="up"   -> swing_low happened before swing_high (uptrend leg);
                         retracement levels are measured DOWN from the high,
                         since price is expected to pull back before
                         continuing up.
    direction="down" -> swing_high happened before swing_low (downtrend leg);
                         retracement levels are measured UP from the low.
    """
    diff = swing_high - swing_low
    levels = {}
    for ratio in FIB_LEVELS:
        if direction == "up":
            levels[ratio] = swing_high - diff * ratio
        else:
            levels[ratio] = swing_low + diff * ratio
    return levels


def analyze(df, lookback=50, proximity_pct=0.3):
    """
    Full Fibonacci analysis on the given candle data. Returns a dict:
        {
            "direction": "up" | "down",
            "swing_high": float, "swing_low": float,
            "levels": {ratio: price, ...},
            "at_level": ratio or None,   # which level price is currently near
            "signal": "bullish_bounce" | "bearish_rejection" | None,
        }
    """
    swing_high, swing_high_idx, swing_low, swing_low_idx = find_swing_points(df, lookback)

    # Determine which swing happened more recently to infer trend direction
    # of the most recent leg.
    direction = "up" if swing_low_idx < swing_high_idx else "down"
    levels = calculate_levels(swing_high, swing_low, direction)

    current_price = df["close"].iloc[-1]
    price_range = swing_high - swing_low
    if price_range <= 0:
        return {
            "direction": direction, "swing_high": swing_high, "swing_low": swing_low,
            "levels": levels, "at_level": None, "signal": None,
        }

    # Check if current price is within `proximity_pct`% of the total range
    # from any Fib level - i.e. "reacting" at that level.
    at_level = None
    for ratio, price in levels.items():
        proximity_threshold = price_range * (proximity_pct / 100)
        if abs(current_price - price) <= proximity_threshold:
            at_level = ratio
            break

    # ── Signal logic ──────────────────────────────────────────────────
    # In an uptrend leg (direction="up"), price pulling back to a Fib level
    # and holding (last candle green, closing above the level) suggests a
    # bullish bounce continuation.
    # In a downtrend leg (direction="down"), price retracing up to a Fib
    # level and getting rejected (last candle red, closing below the level)
    # suggests a bearish continuation.
    signal = None
    last_candle = df.iloc[-1]
    last_green = last_candle["close"] > last_candle["open"]
    last_red = last_candle["close"] < last_candle["open"]

    if at_level is not None:
        if direction == "up" and last_green:
            signal = "bullish_bounce"
        elif direction == "down" and last_red:
            signal = "bearish_rejection"

    return {
        "direction": direction,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "levels": {k: round(v, 2) for k, v in levels.items()},
        "at_level": at_level,
        "signal": signal,
    }
