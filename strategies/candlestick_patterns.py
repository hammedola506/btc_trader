"""
Candlestick pattern detection, implemented directly from OHLC math
(no TA-Lib dependency required).

Each function returns a boolean pandas Series aligned to the DataFrame index:
True where the pattern is detected on that candle.

Patterns implemented:
  Single-candle:  hammer, shooting_star, doji
  Two-candle:     bullish_engulfing, bearish_engulfing
  Three-candle:   morning_star, evening_star
"""
import pandas as pd
import numpy as np


def _body(df):
    return (df["close"] - df["open"]).abs()


def _range(df):
    return df["high"] - df["low"]


def _upper_wick(df):
    return df["high"] - df[["open", "close"]].max(axis=1)


def _lower_wick(df):
    return df[["open", "close"]].min(axis=1) - df["low"]


def doji(df, threshold=0.1):
    """Body is a very small fraction of the candle's total range."""
    rng = _range(df).replace(0, np.nan)
    return (_body(df) / rng) < threshold


def hammer(df):
    """Small body near the top, long lower wick, little/no upper wick. Bullish reversal."""
    body = _body(df)
    lower = _lower_wick(df)
    upper = _upper_wick(df)
    rng = _range(df).replace(0, np.nan)
    return (lower > body * 2) & (upper < body * 0.5) & (body / rng < 0.4)


def shooting_star(df):
    """Small body near the bottom, long upper wick, little/no lower wick. Bearish reversal."""
    body = _body(df)
    lower = _lower_wick(df)
    upper = _upper_wick(df)
    rng = _range(df).replace(0, np.nan)
    return (upper > body * 2) & (lower < body * 0.5) & (body / rng < 0.4)


def bullish_engulfing(df):
    """Current green candle's body fully engulfs the prior red candle's body."""
    prev_open = df["open"].shift(1)
    prev_close = df["close"].shift(1)
    prev_red = prev_close < prev_open
    curr_green = df["close"] > df["open"]
    engulfs = (df["open"] <= prev_close) & (df["close"] >= prev_open)
    return prev_red & curr_green & engulfs


def bearish_engulfing(df):
    """Current red candle's body fully engulfs the prior green candle's body."""
    prev_open = df["open"].shift(1)
    prev_close = df["close"].shift(1)
    prev_green = prev_close > prev_open
    curr_red = df["close"] < df["open"]
    engulfs = (df["open"] >= prev_close) & (df["close"] <= prev_open)
    return prev_green & curr_red & engulfs


def morning_star(df):
    """3-candle bullish reversal: big red, small indecisive candle, big green closing into the first body."""
    c1_open, c1_close = df["open"].shift(2), df["close"].shift(2)
    c2_body = _body(df.shift(1))
    c3_open, c3_close = df["open"], df["close"]

    c1_red = c1_close < c1_open
    c1_body = (c1_open - c1_close).abs()
    c2_small = c2_body < (c1_body * 0.5)
    c3_green = c3_close > c3_open
    c3_recovers = c3_close > (c1_open + c1_close) / 2

    return c1_red & c2_small & c3_green & c3_recovers


def evening_star(df):
    """3-candle bearish reversal: big green, small indecisive candle, big red closing into the first body."""
    c1_open, c1_close = df["open"].shift(2), df["close"].shift(2)
    c2_body = _body(df.shift(1))
    c3_open, c3_close = df["open"], df["close"]

    c1_green = c1_close > c1_open
    c1_body = (c1_close - c1_open).abs()
    c2_small = c2_body < (c1_body * 0.5)
    c3_red = c3_close < c3_open
    c3_drops = c3_close < (c1_open + c1_close) / 2

    return c1_green & c2_small & c3_red & c3_drops


def bullish_harami(df):
    """Small green body sits entirely inside the prior large red body. Bullish reversal."""
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_red = prev_close < prev_open
    curr_green = df["close"] > df["open"]
    inside = (df["open"] > prev_close) & (df["close"] < prev_open)
    return prev_red & curr_green & inside


def bearish_harami(df):
    """Small red body sits entirely inside the prior large green body. Bearish reversal."""
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_green = prev_close > prev_open
    curr_red = df["close"] < df["open"]
    inside = (df["open"] < prev_close) & (df["close"] > prev_open)
    return prev_green & curr_red & inside


def piercing_line(df):
    """Green candle opens below prior red candle's low close and closes above its midpoint. Bullish reversal."""
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_red = prev_close < prev_open
    curr_green = df["close"] > df["open"]
    midpoint = (prev_open + prev_close) / 2
    return (
        prev_red
        & curr_green
        & (df["open"] < prev_close)
        & (df["close"] > midpoint)
        & (df["close"] < prev_open)
    )


def dark_cloud_cover(df):
    """Red candle opens above prior green candle's high close and closes below its midpoint. Bearish reversal."""
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_green = prev_close > prev_open
    curr_red = df["close"] < df["open"]
    midpoint = (prev_open + prev_close) / 2
    return (
        prev_green
        & curr_red
        & (df["open"] > prev_close)
        & (df["close"] < midpoint)
        & (df["close"] > prev_open)
    )


def three_white_soldiers(df):
    """Three consecutive green candles, each opening/closing higher than the last. Strong bullish continuation."""
    c1_green = df["close"].shift(2) > df["open"].shift(2)
    c2_green = df["close"].shift(1) > df["open"].shift(1)
    c3_green = df["close"] > df["open"]
    rising_closes = (df["close"].shift(1) > df["close"].shift(2)) & (df["close"] > df["close"].shift(1))
    rising_opens = (df["open"].shift(1) > df["open"].shift(2)) & (df["open"] > df["open"].shift(1))
    return c1_green & c2_green & c3_green & rising_closes & rising_opens


def three_black_crows(df):
    """Three consecutive red candles, each opening/closing lower than the last. Strong bearish continuation."""
    c1_red = df["close"].shift(2) < df["open"].shift(2)
    c2_red = df["close"].shift(1) < df["open"].shift(1)
    c3_red = df["close"] < df["open"]
    falling_closes = (df["close"].shift(1) < df["close"].shift(2)) & (df["close"] < df["close"].shift(1))
    falling_opens = (df["open"].shift(1) < df["open"].shift(2)) & (df["open"] < df["open"].shift(1))
    return c1_red & c2_red & c3_red & falling_closes & falling_opens


def spinning_top(df):
    """Small body centered between two long, roughly equal wicks. Pure indecision."""
    body = _body(df)
    rng = _range(df).replace(0, np.nan)
    upper = _upper_wick(df)
    lower = _lower_wick(df)
    return (body / rng < 0.3) & (upper > body) & (lower > body)


def bullish_marubozu(df):
    """Green candle with almost no wicks - buyers in full control the entire candle."""
    body = _body(df)
    rng = _range(df).replace(0, np.nan)
    return (df["close"] > df["open"]) & (body / rng > 0.95)


def bearish_marubozu(df):
    """Red candle with almost no wicks - sellers in full control the entire candle."""
    body = _body(df)
    rng = _range(df).replace(0, np.nan)
    return (df["close"] < df["open"]) & (body / rng > 0.95)


def tweezer_top(df):
    """Two candles with matching highs, first green then red. Bearish reversal at resistance."""
    prev_high = df["high"].shift(1)
    similar_highs = (df["high"] - prev_high).abs() / df["high"] < 0.001
    prev_green = df["close"].shift(1) > df["open"].shift(1)
    curr_red = df["close"] < df["open"]
    return similar_highs & prev_green & curr_red


def tweezer_bottom(df):
    """Two candles with matching lows, first red then green. Bullish reversal at support."""
    prev_low = df["low"].shift(1)
    similar_lows = (df["low"] - prev_low).abs() / df["low"] < 0.001
    prev_red = df["close"].shift(1) < df["open"].shift(1)
    curr_green = df["close"] > df["open"]
    return similar_lows & prev_red & curr_green


def detect_all(df):
    """
    Run every pattern detector and return a DataFrame of booleans,
    one column per pattern, aligned to df's index.
    """
    return pd.DataFrame({
        "doji": doji(df),
        "hammer": hammer(df),
        "shooting_star": shooting_star(df),
        "bullish_engulfing": bullish_engulfing(df),
        "bearish_engulfing": bearish_engulfing(df),
        "morning_star": morning_star(df),
        "evening_star": evening_star(df),
        "bullish_harami": bullish_harami(df),
        "bearish_harami": bearish_harami(df),
        "piercing_line": piercing_line(df),
        "dark_cloud_cover": dark_cloud_cover(df),
        "three_white_soldiers": three_white_soldiers(df),
        "three_black_crows": three_black_crows(df),
        "spinning_top": spinning_top(df),
        "bullish_marubozu": bullish_marubozu(df),
        "bearish_marubozu": bearish_marubozu(df),
        "tweezer_top": tweezer_top(df),
        "tweezer_bottom": tweezer_bottom(df),
    })


def latest_patterns(df):
    """Return a list of pattern names detected on the most recent (last) candle."""
    all_patterns = detect_all(df)
    last_row = all_patterns.iloc[-1]
    return [name for name, hit in last_row.items() if bool(hit)]
