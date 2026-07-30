# Architecture Decision Records (ADRs)

## ADR-001: Execution Fill Matching & Single-Position Constraint

### Status
Accepted

### Context
When checking whether an open position has closed on Bybit / live exchange, estimating exit prices from `take_profit` or `stop_loss` targets leads to inaccurate PnL, missing slippage accounting, and false win/loss classification.

To obtain the true realized exit price, the system queries Bybit execution fills (`exchange.fetch_my_trades()`).

### Decision
1. **Single Position Constraint**: The bot operates as a single-position state machine (`open_position` dict in memory and `logs/bot_state.json`). Only one position is active at any time.
2. **Timestamp + Side Filter**: Position entry records `entry_timestamp` (in milliseconds). When closing, `fetch_my_trades(symbol, since=entry_timestamp)` filters for fills occurring after `entry_timestamp` on the opposing side (`sell` for LONG, `buy` for SHORT).
3. **VWAP Aggregation**: Multiple partial fills are aggregated into a single Volume-Weighted Average Price (VWAP) exit price:
   $$\text{VWAP Exit Price} = \frac{\sum (\text{fill\_price}_i \times \text{fill\_qty}_i)}{\sum \text{fill\_qty}_i}$$

### Future Considerations for Multi-Position / Scaling
If the system is upgraded to support scaling in/out, hedging, or concurrent multi-position trading, fill matching should be enhanced to use explicit `clientOrderId` tagging (e.g., `btc_trader_{trade_id}_tp`) and direct order ID matching to eliminate potential timestamp overlap across concurrent trades.
