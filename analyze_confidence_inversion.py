"""
Replay backtest trades through strategy.evaluate() to capture the full
signal breakdown (confidence score, patterns, indicators, reasons) for
each trade.  Then bucket by confidence range and compare compositions.
"""
import pandas as pd
import json

import config
from strategies import strategy
from strategies import trading_style

# Use the daily profile (matches original backtest)
trading_style.apply_profile("daily", config)

# Load the same historical data the backtest used
data = pd.read_csv("historical_data.csv", parse_dates=["timestamp"])
data = data.sort_values("timestamp").reset_index(drop=True)

# Load recorded trades
trades = pd.read_csv("backtest_trades.csv", parse_dates=["entry_time", "exit_time"])

print(f"Loaded {len(data)} candles, {len(trades)} trades")
print(f"Config: MIN_CONFIDENCE_TO_TRADE={config.MIN_CONFIDENCE_TO_TRADE}")
print()

# For each trade, find the candle index that matches the entry_time,
# then replay strategy.evaluate() with the window up to that candle
# to get the full signal breakdown.
results = []
min_window = 50

for idx, trade in trades.iterrows():
    entry_time = trade["entry_time"]
    
    # Find the candle index in historical data
    match_indices = data.index[data["timestamp"] == entry_time].tolist()
    if not match_indices:
        # Try fuzzy match (within 1 minute)
        for i, row in data.iterrows():
            if abs((row["timestamp"] - entry_time).total_seconds()) < 60:
                match_indices = [i]
                break
    
    if not match_indices:
        print(f"  WARNING: Could not find candle for trade at {entry_time}")
        continue
    
    candle_idx = match_indices[0]
    if candle_idx < min_window:
        continue
    
    # Replay: give strategy the same window it would have seen
    window = data.iloc[:candle_idx + 1]
    signal = strategy.evaluate(window)
    
    results.append({
        "trade_idx": idx,
        "entry_time": str(entry_time),
        "side": trade["side"],
        "entry_price": trade["entry"],
        "outcome": trade["outcome"],
        "pnl_usdt": trade["pnl_usdt"],
        "confidence": signal["confidence"],
        "action": signal["action"],
        "reasons": signal["reasons"],
        "bull_case": signal.get("bull_case", []),
        "bear_case": signal.get("bear_case", []),
        "details": signal.get("details", {}),
    })

print(f"Successfully replayed {len(results)} / {len(trades)} trades\n")

# Convert to DataFrame for analysis
df = pd.DataFrame(results)

# ── Bucket analysis ────────────────────────────────────────────────────
buckets = {
    "60-69": (60, 69),
    "70-79": (70, 79),
    "80-89": (80, 89),
    "90+": (90, 100),
}

print("=" * 80)
print("CONFIDENCE BUCKET ANALYSIS")
print("=" * 80)

for label, (lo, hi) in buckets.items():
    subset = df[(df["confidence"] >= lo) & (df["confidence"] <= hi)]
    if len(subset) == 0:
        print(f"\n[{label}] No trades in this bucket")
        continue
    
    wins = subset[subset["outcome"] == "win"]
    losses = subset[subset["outcome"] == "loss"]
    win_rate = len(wins) / len(subset) * 100 if len(subset) > 0 else 0
    avg_pnl = subset["pnl_usdt"].mean()
    
    print(f"\n{'=' * 80}")
    print(f"[{label}] {len(subset)} trades | Win rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L) | Avg PnL: ${avg_pnl:.2f}")
    print(f"{'=' * 80}")
    
    # Count which signals/reasons appear most often
    all_reasons_wins = []
    all_reasons_losses = []
    all_patterns_wins = []
    all_patterns_losses = []
    
    for _, row in subset.iterrows():
        reasons = row["reasons"] if isinstance(row["reasons"], list) else []
        bull_case = row["bull_case"] if isinstance(row["bull_case"], list) else []
        bear_case = row["bear_case"] if isinstance(row["bear_case"], list) else []
        details = row["details"] if isinstance(row["details"], dict) else {}
        
        # Normalize reasons to shorter keys
        reason_keys = []
        for r in reasons:
            if "EMA9 crossed above" in r:
                reason_keys.append("EMA_CROSS_BULL")
            elif "EMA9 crossed below" in r:
                reason_keys.append("EMA_CROSS_BEAR")
            elif "EMA9 above EMA21" in r:
                reason_keys.append("EMA_TREND_BULL")
            elif "EMA9 below EMA21" in r:
                reason_keys.append("EMA_TREND_BEAR")
            elif "RSI oversold" in r:
                reason_keys.append("RSI_OVERSOLD")
            elif "RSI overbought" in r:
                reason_keys.append("RSI_OVERBOUGHT")
            elif "MACD bullish" in r:
                reason_keys.append("MACD_CROSS_BULL")
            elif "MACD bearish" in r:
                reason_keys.append("MACD_CROSS_BEAR")
            elif "Volume is significantly" in r:
                reason_keys.append("VOLUME_CONFIRM")
            elif "Fibonacci" in r and "bounce" in r.lower():
                reason_keys.append("FIB_BOUNCE_BULL")
            elif "Fibonacci" in r and "reject" in r.lower():
                reason_keys.append("FIB_REJECT_BEAR")
            elif "Fibonacci" in r:
                reason_keys.append("FIB_NEAR")
            elif "ADX" in r and "very strong" in r:
                reason_keys.append("ADX_VERY_STRONG")
            elif "ADX" in r and "strong enough" in r:
                reason_keys.append("ADX_STRONG")
            elif "ADX" in r and "weak" in r:
                reason_keys.append("ADX_WEAK_DAMPEN")
            elif "Strong bullish pattern" in r:
                reason_keys.append("PATTERN_STRONG_BULL")
            elif "Strong bearish pattern" in r:
                reason_keys.append("PATTERN_STRONG_BEAR")
            elif "Bullish candlestick" in r:
                reason_keys.append("PATTERN_MED_BULL")
            elif "Bearish candlestick" in r:
                reason_keys.append("PATTERN_MED_BEAR")
            elif "Minor bullish" in r:
                reason_keys.append("PATTERN_WEAK_BULL")
            elif "Minor bearish" in r:
                reason_keys.append("PATTERN_WEAK_BEAR")
            elif "Spinning top" in r:
                reason_keys.append("INDECISION_SPIN")
            elif "Doji" in r:
                reason_keys.append("INDECISION_DOJI")
            elif "Market shows" in r:
                # Extract trend info
                if "strong uptrend" in r:
                    reason_keys.append("MARKET_STRONG_UP")
                elif "weak uptrend" in r:
                    reason_keys.append("MARKET_WEAK_UP")
                elif "strong downtrend" in r:
                    reason_keys.append("MARKET_STRONG_DOWN")
                elif "weak downtrend" in r:
                    reason_keys.append("MARKET_WEAK_DOWN")
        
        # Get specific candlestick pattern names
        patterns_str = details.get("candlestick_patterns", None)
        pattern_list = [p.strip() for p in patterns_str.split(",")] if patterns_str else []
        
        if row["outcome"] == "win":
            all_reasons_wins.extend(reason_keys)
            all_patterns_wins.extend(pattern_list)
        else:
            all_reasons_losses.extend(reason_keys)
            all_patterns_losses.extend(pattern_list)
    
    # Count reason frequencies
    from collections import Counter
    
    print(f"\n  Signal composition (ALL trades in bucket):")
    all_reasons = all_reasons_wins + all_reasons_losses
    for reason, count in Counter(all_reasons).most_common(15):
        pct = count / len(subset) * 100
        print(f"    {reason:30s}  {count:3d} ({pct:5.1f}% of trades)")
    
    if all_patterns_wins or all_patterns_losses:
        all_patterns = all_patterns_wins + all_patterns_losses
        print(f"\n  Candlestick patterns detected:")
        for pat, count in Counter(all_patterns).most_common(10):
            pct = count / len(subset) * 100
            print(f"    {pat:30s}  {count:3d} ({pct:5.1f}% of trades)")
    
    # Reason breakdown: wins vs losses
    print(f"\n  Signal breakdown by outcome:")
    print(f"  {'Signal':<30s}  {'In Wins':>10s}  {'In Losses':>10s}  {'Loss Ratio':>12s}")
    all_unique_reasons = set(all_reasons_wins + all_reasons_losses)
    win_counter = Counter(all_reasons_wins)
    loss_counter = Counter(all_reasons_losses)
    for reason in sorted(all_unique_reasons):
        w = win_counter.get(reason, 0)
        l = loss_counter.get(reason, 0)
        loss_ratio = l / (w + l) * 100 if (w + l) > 0 else 0
        print(f"  {reason:<30s}  {w:>10d}  {l:>10d}  {loss_ratio:>10.1f}%")

    # Show ADX values
    adx_values = [r["details"].get("adx", None) for _, r in subset.iterrows() if isinstance(r["details"], dict)]
    adx_values = [v for v in adx_values if v is not None]
    if adx_values:
        print(f"\n  ADX stats: min={min(adx_values):.1f}, max={max(adx_values):.1f}, avg={sum(adx_values)/len(adx_values):.1f}")

    # Show RSI values
    rsi_values = [r["details"].get("rsi", None) for _, r in subset.iterrows() if isinstance(r["details"], dict)]
    rsi_values = [v for v in rsi_values if v is not None]
    if rsi_values:
        print(f"  RSI stats: min={min(rsi_values):.1f}, max={max(rsi_values):.1f}, avg={sum(rsi_values)/len(rsi_values):.1f}")


# ── Specific 70-79 deep dive: show each trade ──────────────────────────
print("\n\n" + "=" * 80)
print("DEEP DIVE: 70-79 CONFIDENCE TRADES (individual breakdown)")
print("=" * 80)

subset_70 = df[(df["confidence"] >= 70) & (df["confidence"] <= 79)]
for _, row in subset_70.iterrows():
    print(f"\n  {'─' * 76}")
    print(f"  Trade #{row['trade_idx']} | {row['entry_time']} | {row['side']} @ ${row['entry_price']:.2f}")
    print(f"  Confidence: {row['confidence']} | Outcome: {row['outcome']} | PnL: ${row['pnl_usdt']:.2f}")
    details = row["details"] if isinstance(row["details"], dict) else {}
    print(f"  ADX: {details.get('adx', '?')} | RSI: {details.get('rsi', '?')} | Trend: {details.get('trend_direction', '?')}")
    print(f"  EMA fast: {details.get('ema_fast', '?')} | EMA slow: {details.get('ema_slow', '?')}")
    print(f"  Patterns: {details.get('candlestick_patterns', 'None')}")
    print(f"  Fib level: {details.get('fib_level', 'None')} | Fib signal: {details.get('fib_signal', 'None')}")
    print(f"  Reasons:")
    reasons = row["reasons"] if isinstance(row["reasons"], list) else []
    for r in reasons:
        print(f"    • {r}")

# ── Specific 90+ deep dive: show each trade ──────────────────────────
print("\n\n" + "=" * 80)
print("DEEP DIVE: 90+ CONFIDENCE TRADES (individual breakdown)")
print("=" * 80)

subset_90 = df[df["confidence"] >= 90]
for _, row in subset_90.iterrows():
    print(f"\n  {'─' * 76}")
    print(f"  Trade #{row['trade_idx']} | {row['entry_time']} | {row['side']} @ ${row['entry_price']:.2f}")
    print(f"  Confidence: {row['confidence']} | Outcome: {row['outcome']} | PnL: ${row['pnl_usdt']:.2f}")
    details = row["details"] if isinstance(row["details"], dict) else {}
    print(f"  ADX: {details.get('adx', '?')} | RSI: {details.get('rsi', '?')} | Trend: {details.get('trend_direction', '?')}")
    print(f"  EMA fast: {details.get('ema_fast', '?')} | EMA slow: {details.get('ema_slow', '?')}")
    print(f"  Patterns: {details.get('candlestick_patterns', 'None')}")
    print(f"  Fib level: {details.get('fib_level', 'None')} | Fib signal: {details.get('fib_signal', 'None')}")
    print(f"  Reasons:")
    reasons = row["reasons"] if isinstance(row["reasons"], list) else []
    for r in reasons:
        print(f"    • {r}")

# ── Save full results for further analysis ──────────────────────────
# Convert non-serializable objects for JSON output
output = []
for r in results:
    row = dict(r)
    row["details"] = dict(row["details"]) if row["details"] else {}
    output.append(row)

with open("confidence_analysis.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n\nFull results saved to confidence_analysis.json")

# ── Summary statistics ─────────────────────────────────────────────────
print("\n\n" + "=" * 80)
print("SCORING ARITHMETIC DEEP DIVE")
print("=" * 80)
print("""
The confidence score is computed as:
  confidence = min(100, abs(bullish_score - bearish_score))

Possible score contributions:
  Strong candlestick pattern (morning_star, three_white_soldiers, etc):  +30
  Medium candlestick pattern (hammer, engulfing, marubozu, etc):         +20
  Weak candlestick pattern (harami):                                     +10
  EMA crossover (just happened):                                         +20
  EMA trend (already established):                                       +10
  RSI extreme (oversold <30 or overbought >70):                          +15
  MACD crossover (just happened):                                        +15
  Volume confirmation (>1.3x average):                                   +10
  Fibonacci bounce/rejection (at 61.8%/50%):                             +25
  Fibonacci bounce/rejection (at other levels):                          +15
  ADX >= 35 (very strong trend):                                         +10
  ADX >= 25 (strong trend):                                              +5
  ADX < 20 (weak trend):                                                 *= 0.6 (dampener!)

Common combinations that land in 70-79 range:
  20 (medium pattern) + 20 (EMA crossover) + 15 (MACD crossover) + 15 (Fib) = 70
  20 (medium pattern) + 10 (EMA trend) + 15 (RSI) + 15 (MACD) + 10 (volume) + 5 (ADX) = 75
  30 (strong pattern) + 20 (EMA crossover) + 15 (MACD) + 10 (volume) = 75
  ... but with ADX dampener (* 0.6) applied before ADX bonus, many scores get pushed around
""")

# ── Check how many signals stack in each bucket ──────────────────────
print("\n" + "=" * 80)
print("SIGNAL COUNT PER BUCKET")
print("=" * 80)
for label, (lo, hi) in buckets.items():
    subset = df[(df["confidence"] >= lo) & (df["confidence"] <= hi)]
    if len(subset) == 0:
        continue
    signal_counts = []
    for _, row in subset.iterrows():
        reasons = row["reasons"] if isinstance(row["reasons"], list) else []
        # Count actual signal reasons (exclude market context line)
        signal_reasons = [r for r in reasons if not r.startswith("Market shows")]
        signal_counts.append(len(signal_reasons))
    avg_signals = sum(signal_counts) / len(signal_counts)
    print(f"  [{label}] avg {avg_signals:.1f} signals per trade (range: {min(signal_counts)}-{max(signal_counts)})")
