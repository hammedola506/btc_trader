"""
The decision engine: combines candlestick patterns + technical indicators
+ Fibonacci retracement + support/resistance zones + trend strength (ADX)
into a single trade signal with a confidence score, the way a discretionary
human trader would weigh several pieces of evidence before acting.

Fixes applied (2026-07-20):
  1. three_white_soldiers reweighted from strong (+30) to medium (+20).
     As a multi-candle continuation pattern it fires readily during
     overextended moves and was a primary driver of false confidence.
  2. Pattern stacking cap: 1st same-direction pattern = full weight,
     2nd = 50%, 3rd+ = 25%.  Multiple patterns on one candle share
     the same underlying price action — they are not independent signals.
  3. RSI hard veto: LONG is blocked when RSI > 70; SHORT is blocked when
     RSI < 30.  Backtesting showed 0/39 win rate on RSI-overbought+LONG
     entries — this is a structural error, not a marginal case.
  4. MACD crossover suppressed when RSI contradicts the direction.
     A bullish MACD cross while RSI is already overbought is stale
     momentum. Adding it to bull_score produces false confidence.
  5. Market-structure alignment gate: counter-trend entries (LONG in a
     downtrend, SHORT in an uptrend) are blocked unless reversal-specific
     evidence is present (RSI extreme or Fibonacci bounce/rejection).
     Pure trend-following signals in counter-trend context drove 49/51
     with-trend losses in the 70-79 confidence bucket.
"""
from strategies import candlestick_patterns as patterns
from strategies import indicators as ind
from strategies import fibonacci as fib
from strategies import support_resistance as sr
from strategies import market_structure as ms
import pandas as pd

SR_PROXIMITY_BLOCK_PCT = 0.3


def evaluate(df):
    current_tick = df.iloc[-1]

    # Calculate indicators ONLY on closed candles to prevent repainting
    closed_df = df.iloc[:-1].copy()

    if len(closed_df) < 50:
        return {
            "action": "WAIT",
            "confidence": 0,
            "reasons": ["Not enough closed candles"],
            "price": current_tick["close"],
            "atr": 0,
            "details": {},
        }

    closed_df = ind.add_indicators(closed_df)

    # ── Market Structure Pre-Flight Check ─────────────────────────
    market_context = ms.classify(closed_df)
    last = closed_df.iloc[-1]

    if not market_context["tradeable"]:
        details = {
            "ema_fast": round(float(last.get("ema_fast", 0)), 2) if pd.notna(last.get("ema_fast")) else None,
            "ema_slow": round(float(last.get("ema_slow", 0)), 2) if pd.notna(last.get("ema_slow")) else None,
            "rsi": round(float(last.get("rsi", 0)), 2) if pd.notna(last.get("rsi")) else None,
            "macd": round(float(last.get("macd", 0)), 4) if pd.notna(last.get("macd")) else None,
            "macd_signal": round(float(last.get("macd_signal", 0)), 4) if pd.notna(last.get("macd_signal")) else None,
            "macd_hist": round(float(last.get("macd_hist", 0)), 4) if pd.notna(last.get("macd_hist")) else None,
            "adx": round(float(market_context.get("adx", 0)), 2) if market_context.get("adx") else None,
            "volume": round(float(last.get("volume", 0)), 2),
            "volume_sma": round(float(last.get("volume_sma", 0)), 2) if pd.notna(last.get("volume_sma")) else None,
            "candlestick_patterns": None,
            "swing_high": None,
            "swing_low": None,
            "fib_level": None,
            "fib_signal": None,
            "nearest_support": None,
            "nearest_resistance": None,
            "support_distance_pct": None,
            "resistance_distance_pct": None,
            "trend_direction": market_context["trend"],
        }
        return {
            "action": "WAIT",
            "confidence": 0,
            "reasons": [market_context["reason"]],
            "bull_case": [],
            "bear_case": [],
            "price": current_tick["close"],
            "atr": last.get("atr", 0),
            "details": details,
        }

    detected = patterns.latest_patterns(closed_df)
    prev = closed_df.iloc[-2]

    bullish_score = 0
    bearish_score = 0

    reasons = [market_context["reason"]]
    bull_case = []
    bear_case = []

    # ── Candlestick pattern evidence ─────────────────────────────
    # FIX #1: three_white_soldiers moved from strong_bullish to medium_bullish.
    strong_bullish = {"morning_star"}
    strong_bearish = {"evening_star", "three_black_crows"}
    medium_bullish = {
        "hammer", "bullish_engulfing", "piercing_line", "tweezer_bottom",
        "bullish_marubozu", "three_white_soldiers",
    }
    medium_bearish = {
        "shooting_star", "bearish_engulfing", "dark_cloud_cover",
        "tweezer_top", "bearish_marubozu",
    }
    weak_bullish = {"bullish_harami"}
    weak_bearish = {"bearish_harami"}

    # FIX #2: stacking cap — diminishing returns for same-direction patterns
    # on the same candle.  They share the same price action; they are not
    # independent signals.
    bull_pattern_count = 0
    bear_pattern_count = 0

    def _pattern_weight(base_weight, count):
        if count == 0:
            return base_weight
        if count == 1:
            return int(base_weight * 0.5)
        return int(base_weight * 0.25)

    for p in detected:
        if p in strong_bullish:
            w = _pattern_weight(30, bull_pattern_count)
            bullish_score += w
            bull_pattern_count += 1
            msg = f"Strong bullish pattern detected: {p}"
            reasons.append(msg)
            bull_case.append(msg)
        elif p in strong_bearish:
            w = _pattern_weight(30, bear_pattern_count)
            bearish_score += w
            bear_pattern_count += 1
            msg = f"Strong bearish pattern detected: {p}"
            reasons.append(msg)
            bear_case.append(msg)
        elif p in medium_bullish:
            w = _pattern_weight(20, bull_pattern_count)
            bullish_score += w
            bull_pattern_count += 1
            msg = f"Bullish candlestick pattern detected: {p}"
            reasons.append(msg)
            bull_case.append(msg)
        elif p in medium_bearish:
            w = _pattern_weight(20, bear_pattern_count)
            bearish_score += w
            bear_pattern_count += 1
            msg = f"Bearish candlestick pattern detected: {p}"
            reasons.append(msg)
            bear_case.append(msg)
        elif p in weak_bullish:
            w = _pattern_weight(10, bull_pattern_count)
            bullish_score += w
            bull_pattern_count += 1
            msg = f"Minor bullish pattern detected: {p}"
            reasons.append(msg)
            bull_case.append(msg)
        elif p in weak_bearish:
            w = _pattern_weight(10, bear_pattern_count)
            bearish_score += w
            bear_pattern_count += 1
            msg = f"Minor bearish pattern detected: {p}"
            reasons.append(msg)
            bear_case.append(msg)
        elif p == "spinning_top":
            msg = "Spinning top detected: market indecision, reduces confidence"
            reasons.append(msg)
        elif p == "doji":
            msg = "Doji detected: market indecision, reduces confidence"
            reasons.append(msg)

    # ── Trend evidence (EMA crossover) ───────────────────────────
    if last["ema_fast"] > last["ema_slow"] and prev["ema_fast"] <= prev["ema_slow"]:
        bullish_score += 20
        msg = "EMA9 crossed above EMA21 (bullish trend shift)"
        reasons.append(msg)
        bull_case.append(msg)
    elif last["ema_fast"] < last["ema_slow"] and prev["ema_fast"] >= prev["ema_slow"]:
        bearish_score += 20
        msg = "EMA9 crossed below EMA21 (bearish trend shift)"
        reasons.append(msg)
        bear_case.append(msg)
    elif last["ema_fast"] > last["ema_slow"]:
        bullish_score += 10
        msg = "Price trend is up (EMA9 above EMA21)"
        reasons.append(msg)
        bull_case.append(msg)
    else:
        bearish_score += 10
        msg = "Price trend is down (EMA9 below EMA21)"
        reasons.append(msg)
        bear_case.append(msg)

    # ── Momentum evidence (RSI) ───────────────────────────────────
    rsi_value = float(last["rsi"]) if pd.notna(last.get("rsi")) else 50.0
    rsi_is_oversold = rsi_value < 30
    rsi_is_overbought = rsi_value > 70

    if rsi_is_oversold:
        bullish_score += 15
        msg = f"RSI oversold at {rsi_value:.1f}"
        reasons.append(msg)
        bull_case.append(msg)
    elif rsi_is_overbought:
        bearish_score += 15
        msg = f"RSI overbought at {rsi_value:.1f}"
        reasons.append(msg)
        bear_case.append(msg)

    # ── Momentum evidence (MACD) ──────────────────────────────────
    # FIX #4: MACD crossover suppressed when RSI contradicts the direction.
    # A bullish MACD cross while RSI is overbought is stale/exhausted momentum.
    macd_bull_cross = (
        last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]
    )
    macd_bear_cross = (
        last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]
    )

    if macd_bull_cross and not rsi_is_overbought:
        bullish_score += 15
        msg = "MACD bullish crossover"
        reasons.append(msg)
        bull_case.append(msg)
    elif macd_bull_cross and rsi_is_overbought:
        msg = "MACD bullish crossover (suppressed: RSI overbought, momentum already exhausted)"
        reasons.append(msg)
    elif macd_bear_cross and not rsi_is_oversold:
        bearish_score += 15
        msg = "MACD bearish crossover"
        reasons.append(msg)
        bear_case.append(msg)
    elif macd_bear_cross and rsi_is_oversold:
        msg = "MACD bearish crossover (suppressed: RSI oversold, momentum already exhausted)"
        reasons.append(msg)

    # ── Volume confirmation ────────────────────────────────────────
    if last["volume"] > last["volume_sma"] * 1.3:
        msg = "Volume is significantly above average (confirms move strength)"
        reasons.append(msg)
        if bullish_score > bearish_score:
            bullish_score += 10
            bull_case.append(msg)
        elif bearish_score > bullish_score:
            bearish_score += 10
            bear_case.append(msg)

    # ── Fibonacci retracement evidence ────────────────────────────
    fib_analysis = fib.analyze(closed_df)
    has_fib_reversal_signal = False

    if fib_analysis["at_level"] is not None:
        level_pct = int(fib_analysis["at_level"] * 100)
        fib_weight = 25 if fib_analysis["at_level"] in (0.618, 0.5) else 15

        if fib_analysis["signal"] == "bullish_bounce":
            bullish_score += fib_weight
            has_fib_reversal_signal = True
            msg = (
                f"Price bouncing off {level_pct}% Fibonacci retracement level "
                f"({fib_analysis['levels'][fib_analysis['at_level']]}) in an uptrend leg"
            )
            reasons.append(msg)
            bull_case.append(msg)
        elif fib_analysis["signal"] == "bearish_rejection":
            bearish_score += fib_weight
            has_fib_reversal_signal = True
            msg = (
                f"Price rejected at {level_pct}% Fibonacci retracement level "
                f"({fib_analysis['levels'][fib_analysis['at_level']]}) in a downtrend leg"
            )
            reasons.append(msg)
            bear_case.append(msg)
        else:
            msg = f"Price is near the {level_pct}% Fibonacci level but without a clear confirming candle yet"
            reasons.append(msg)

    # ── ADX trend strength filter ──────────────────────────────────
    adx_value = last["adx"]
    if pd.isna(adx_value):
        adx_value = 0

    if adx_value >= 35:
        msg = f"ADX={adx_value:.1f}: very strong trend, boosting confidence"
        reasons.append(msg)
        if bullish_score > bearish_score:
            bullish_score += 10
            bull_case.append(msg)
        elif bearish_score > bullish_score:
            bearish_score += 10
            bear_case.append(msg)
    elif adx_value >= 25:
        msg = f"ADX={adx_value:.1f}: trend strong enough to trust"
        reasons.append(msg)
        if bullish_score > bearish_score:
            bullish_score += 5
            bull_case.append(msg)
        elif bearish_score > bullish_score:
            bearish_score += 5
            bear_case.append(msg)
    elif adx_value < 20:
        bullish_score *= 0.6
        bearish_score *= 0.6
        msg = f"ADX={adx_value:.1f}: weak/no trend, dampening confidence (choppy market)"
        reasons.append(msg)

    # ── Preliminary direction decision ────────────────────────────
    net_score = bullish_score - bearish_score
    confidence = min(100, round(abs(net_score)))

    if net_score > 0:
        action = "LONG"
    elif net_score < 0:
        action = "SHORT"
    else:
        action = "WAIT"

    # ── FIX #3: RSI Hard Veto ─────────────────────────────────────
    # RSI overbought means the move is already stretched — a LONG here
    # is chasing.  RSI oversold means the sell-off is already exhausted —
    # a SHORT here is chasing in the opposite direction.
    # Backtesting showed 0 wins in 39 RSI-overbought+LONG trades.
    if action == "LONG" and rsi_is_overbought:
        msg = (
            f"BLOCKED: RSI={rsi_value:.1f} overbought — LONG would chase an exhausted move. "
            f"Waiting for RSI to reset below 70."
        )
        reasons.append(msg)
        action = "WAIT"

    if action == "SHORT" and rsi_is_oversold:
        msg = (
            f"BLOCKED: RSI={rsi_value:.1f} oversold — SHORT would chase an exhausted sell-off. "
            f"Waiting for RSI to reset above 30."
        )
        reasons.append(msg)
        action = "WAIT"

    # ── FIX #5: Market-Structure Alignment Gate ───────────────────
    # Counter-trend entries (LONG in downtrend, SHORT in uptrend) require
    # explicit reversal evidence.  Trend-following signals (EMA, MACD,
    # continuation patterns) stacking in a counter-trend direction are not
    # reversal evidence — they just reflect recent price momentum, which is
    # about to exhaust.  Only RSI extreme readings or Fibonacci bounce/
    # rejection at a key level constitute genuine reversal evidence.
    macro_trend = market_context.get("trend", "")
    has_reversal_evidence = rsi_is_oversold or rsi_is_overbought or has_fib_reversal_signal

    if action == "LONG" and "downtrend" in macro_trend and not has_reversal_evidence:
        msg = (
            f"BLOCKED: LONG against a {macro_trend.replace('_', ' ')} requires reversal evidence "
            f"(RSI < 30 or Fibonacci bounce). Trend-following signals alone are insufficient here."
        )
        reasons.append(msg)
        action = "WAIT"

    if action == "SHORT" and "uptrend" in macro_trend and not has_reversal_evidence:
        msg = (
            f"BLOCKED: SHORT against a {macro_trend.replace('_', ' ')} requires reversal evidence "
            f"(RSI > 70 or Fibonacci rejection). Trend-following signals alone are insufficient here."
        )
        reasons.append(msg)
        action = "WAIT"

    # ── Support/Resistance veto ─────────────────────────────────────
    sr_levels = sr.nearest_levels(closed_df, current_price=current_tick["close"])

    if action == "LONG" and sr_levels["resistance_distance_pct"] is not None:
        if sr_levels["resistance_distance_pct"] <= SR_PROXIMITY_BLOCK_PCT:
            msg = (
                f"BLOCKED: resistance zone only {sr_levels['resistance_distance_pct']:.2f}% away "
                f"(zone ~{sr_levels['nearest_resistance']['center']}), waiting instead of going long into it"
            )
            reasons.append(msg)
            action = "WAIT"

    if action == "SHORT" and sr_levels["support_distance_pct"] is not None:
        if sr_levels["support_distance_pct"] <= SR_PROXIMITY_BLOCK_PCT:
            msg = (
                f"BLOCKED: support zone only {sr_levels['support_distance_pct']:.2f}% away "
                f"(zone ~{sr_levels['nearest_support']['center']}), waiting instead of shorting into it"
            )
            reasons.append(msg)
            action = "WAIT"

    # ── Build the full details payload for the trade journal ────────
    details = {
        "ema_fast": round(float(last.get("ema_fast", 0)), 2) if pd.notna(last.get("ema_fast")) else None,
        "ema_slow": round(float(last.get("ema_slow", 0)), 2) if pd.notna(last.get("ema_slow")) else None,
        "rsi": round(float(last.get("rsi", 0)), 2) if pd.notna(last.get("rsi")) else None,
        "macd": round(float(last.get("macd", 0)), 4) if pd.notna(last.get("macd")) else None,
        "macd_signal": round(float(last.get("macd_signal", 0)), 4) if pd.notna(last.get("macd_signal")) else None,
        "macd_hist": round(float(last.get("macd_hist", 0)), 4) if pd.notna(last.get("macd_hist")) else None,
        "adx": round(float(adx_value), 2),
        "volume": round(float(last.get("volume", 0)), 2),
        "volume_sma": round(float(last.get("volume_sma", 0)), 2) if pd.notna(last.get("volume_sma")) else None,
        "candlestick_patterns": ", ".join(detected) if detected else None,
        "swing_high": fib_analysis["swing_high"],
        "swing_low": fib_analysis["swing_low"],
        "fib_level": fib_analysis["at_level"],
        "fib_signal": fib_analysis["signal"],
        "nearest_support": sr_levels["nearest_support"]["center"] if sr_levels["nearest_support"] else None,
        "nearest_resistance": sr_levels["nearest_resistance"]["center"] if sr_levels["nearest_resistance"] else None,
        "support_distance_pct": sr_levels["support_distance_pct"],
        "resistance_distance_pct": sr_levels["resistance_distance_pct"],
        "trend_direction": "up" if last.get("ema_fast", 0) > last.get("ema_slow", 0) else "down",
    }

    raw_action = "LONG" if net_score > 0 else "SHORT" if net_score < 0 else "NEUTRAL"
    ema_score = 0
    if raw_action == "LONG":
        if any("crossed above" in item.lower() for item in bull_case):
            ema_score = 20
        elif any("price trend is up" in item.lower() for item in bull_case):
            ema_score = 10
    elif raw_action == "SHORT":
        if any("crossed below" in item.lower() for item in bear_case):
            ema_score = 20
        elif any("price trend is down" in item.lower() for item in bear_case):
            ema_score = 10

    indicator_scores = {
        "ema_trend": ema_score,
        "rsi_momentum": 15 if "rsi" in " ".join(reasons).lower() else 0,
        "macd": 15 if "macd" in " ".join(reasons).lower() else 0,
        "adx": 10 if "adx" in " ".join(reasons).lower() else 0,
        "support_resistance": 15 if "support" in " ".join(reasons).lower() or "resistance" in " ".join(reasons).lower() else 0,
        "fibonacci": 15 if "fibonacci" in " ".join(reasons).lower() else 0,
        "candlestick": 10 if detected else 0,
    }

    return {
        "action": action,
        "raw_action": raw_action,
        "confidence": confidence,
        "indicator_scores": indicator_scores,
        "reasons": reasons,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "price": current_tick["close"],
        "atr": last.get("atr", 0),
        "details": details,
    }
