"""
Technical indicators, built on top of the `ta` library.
"""
import ta


def add_indicators(df):
    df["ema_fast"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
    df["ema_slow"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=14
    ).average_true_range()
    df["volume_sma"] = df["volume"].rolling(window=20).mean()

    df["macd_hist"] = macd.macd_diff()

    # ADX measures trend STRENGTH (not direction). Used to filter out
    # choppy/ranging conditions where trend-following signals tend to fail.
    #   ADX < 20        -> weak/no trend, be skeptical of trend signals
    #   20 <= ADX < 25   -> borderline
    #   ADX >= 25        -> trend strong enough to trust
    #   ADX >= 35        -> very strong trend
    df["adx"] = ta.trend.ADXIndicator(
        df["high"], df["low"], df["close"], window=14
    ).adx()

    return df
