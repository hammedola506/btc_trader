"""
Support and Resistance detection for BTC/USDT.

Finds recent swing highs/lows, clusters nearby ones into zones (treated as
price RANGES, not exact prices - real S/R is never a single tick), and
identifies the nearest support below and resistance above the current price.
"""
import pandas as pd
import numpy as np


def _find_swing_points(df, window=5):
    """
    A candle is a swing high if its high is the highest within `window`
    candles on either side. Same logic (inverted) for swing lows.
    Returns two lists of prices: swing_highs, swing_lows.
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(window, n - window):
        local_high_slice = highs[i - window: i + window + 1]
        local_low_slice = lows[i - window: i + window + 1]

        if highs[i] == local_high_slice.max():
            swing_highs.append(highs[i])
        if lows[i] == local_low_slice.min():
            swing_lows.append(lows[i])

    return swing_highs, swing_lows


def _cluster_into_zones(prices, zone_width_pct=0.3):
    """
    Merge nearby prices into zones. Two prices are in the same zone if
    they're within `zone_width_pct`% of each other. Returns a list of
    zones: [{"low": ..., "high": ..., "center": ..., "touches": n}, ...]
    """
    if not prices:
        return []

    prices = sorted(prices)
    zones = []
    current_cluster = [prices[0]]

    for p in prices[1:]:
        cluster_center = sum(current_cluster) / len(current_cluster)
        if abs(p - cluster_center) / cluster_center * 100 <= zone_width_pct:
            current_cluster.append(p)
        else:
            zones.append(current_cluster)
            current_cluster = [p]
    zones.append(current_cluster)

    return [
        {
            "low": min(cluster),
            "high": max(cluster),
            "center": round(sum(cluster) / len(cluster), 2),
            "touches": len(cluster),
        }
        for cluster in zones
    ]


def detect_zones(df, lookback=150, swing_window=5, zone_width_pct=0.3):
    """
    Detect support and resistance zones from recent price action.
    Returns {"support_zones": [...], "resistance_zones": [...]}
    Zones with more touches are more significant.
    """
    window_df = df.iloc[-lookback:].reset_index(drop=True)
    swing_highs, swing_lows = _find_swing_points(window_df, window=swing_window)

    resistance_zones = _cluster_into_zones(swing_highs, zone_width_pct)
    support_zones = _cluster_into_zones(swing_lows, zone_width_pct)

    # Strongest (most-touched) zones first
    resistance_zones.sort(key=lambda z: -z["touches"])
    support_zones.sort(key=lambda z: -z["touches"])

    return {"support_zones": support_zones, "resistance_zones": resistance_zones}


def nearest_levels(df, current_price=None, lookback=150, swing_window=5, zone_width_pct=0.3):
    """
    Return the nearest support (below current price) and nearest resistance
    (above current price), plus how close price currently is to each
    (as a percentage). This is what the strategy engine actually uses.
    """
    zones = detect_zones(df, lookback, swing_window, zone_width_pct)
    price = current_price if current_price is not None else df["close"].iloc[-1]

    supports_below = [z for z in zones["support_zones"] if z["high"] <= price]
    resistances_above = [z for z in zones["resistance_zones"] if z["low"] >= price]

    nearest_support = max(supports_below, key=lambda z: z["high"]) if supports_below else None
    nearest_resistance = min(resistances_above, key=lambda z: z["low"]) if resistances_above else None

    support_distance_pct = (
        (price - nearest_support["high"]) / price * 100 if nearest_support else None
    )
    resistance_distance_pct = (
        (nearest_resistance["low"] - price) / price * 100 if nearest_resistance else None
    )

    return {
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "support_distance_pct": round(support_distance_pct, 3) if support_distance_pct is not None else None,
        "resistance_distance_pct": round(resistance_distance_pct, 3) if resistance_distance_pct is not None else None,
    }
