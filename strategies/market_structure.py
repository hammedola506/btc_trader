"""
Market structure classification - the "before I risk money, is this even a
good environment to trade in?" step that runs before the confidence engine
looks at any individual signal.

Classifies the market into a trend state and a volatility state, then
decides whether conditions are good enough to bother looking for a trade
at all. A strong trend with normal volatility is a good hunting ground;
a tight range or extreme volatility usually means most indicator signals
become unreliable, so the bot should stand aside rather than force a trade.
"""
from strategies import indicators as ind

# ADX thresholds for trend strength
# FIX: ADX_WEAK_TREND raised from 20 to 25.  Markets with ADX in the 20-24
# range produce unreliable trend-following signals; raising this threshold
# causes them to be classified as ranging (not tradeable), reducing noise.
ADX_STRONG_TREND = 25
ADX_WEAK_TREND = 25  # below this, treat the market as ranging

# Volatility thresholds, as a ratio of current ATR to its recent average
VOLATILITY_HIGH_RATIO = 1.6
VOLATILITY_LOW_RATIO = 0.6


def classify(df):
    """
    Returns:
        {
            "trend": "strong_uptrend" | "weak_uptrend" | "strong_downtrend" |
                     "weak_downtrend" | "range",
            "volatility": "high" | "normal" | "low",
            "adx": float,
            "tradeable": bool,
            "reason": str,   # human-readable explanation of the verdict
        }
    """
    df = ind.add_indicators(df.copy())
    last = df.iloc[-1]

    adx = last["adx"]
    ema_fast_above_slow = last["ema_fast"] > last["ema_slow"]
    ema50_above_200 = last.get("ema_50", 0) > last.get("ema_200", 0) if not pd_isna(last.get("ema_200")) else None

    # ── Trend direction & strength ──────────────────────────────────
    is_ranging = adx < ADX_WEAK_TREND

    if is_ranging:
        trend = "range"
    else:
        # Direction from EMA alignment: prefer the longer-term 50/200 read
        # when it's available (enough candles), otherwise fall back to the
        # short-term 9/21 alignment.
        bullish_direction = ema50_above_200 if ema50_above_200 is not None else ema_fast_above_slow
        strength = "strong" if adx >= ADX_STRONG_TREND else "weak"
        trend = f"{strength}_{'uptrend' if bullish_direction else 'downtrend'}"

    # ── Volatility state ─────────────────────────────────────────────
    atr_series = df["atr"].dropna()
    if len(atr_series) >= 30:
        recent_avg_atr = atr_series.iloc[-30:].mean()
        current_atr = atr_series.iloc[-1]
        ratio = current_atr / recent_avg_atr if recent_avg_atr > 0 else 1.0

        if ratio >= VOLATILITY_HIGH_RATIO:
            volatility = "high"
        elif ratio <= VOLATILITY_LOW_RATIO:
            volatility = "low"
        else:
            volatility = "normal"
    else:
        volatility = "normal"  # not enough history yet to judge

    # ── Tradeable verdict ─────────────────────────────────────────────
    # Ranging markets: most trend-following signals (EMA crossovers, MACD,
    # trend-following candlestick patterns) produce false signals here, so
    # the bot stands aside rather than forcing a trade.
    # Extreme volatility: stops get hunted and position sizing math (based
    # on ATR) becomes unreliable, so the bot also stands aside.
    if trend == "range":
        tradeable = False
        reason = f"Market is ranging (ADX={adx:.1f}, below {ADX_WEAK_TREND} threshold). No clear trend to trade."
    elif volatility == "high":
        tradeable = False
        reason = f"Volatility is unusually high (ATR {ratio:.1f}x recent average). Standing aside until it normalizes."
    else:
        tradeable = True
        reason = f"Market shows a {trend.replace('_', ' ')} (ADX={adx:.1f}), volatility {volatility}. Looking for setups."

    return {
        "trend": trend,
        "volatility": volatility,
        "adx": round(float(adx), 1) if not pd_isna(adx) else None,
        "tradeable": tradeable,
        "reason": reason,
    }


def pd_isna(value):
    """Small helper so this module doesn't need a top-level pandas import just for NaN checks."""
    import math
    try:
        return value is None or math.isnan(value)
    except TypeError:
        return False
