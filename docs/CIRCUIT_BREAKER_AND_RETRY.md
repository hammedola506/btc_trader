# Exchange API Circuit Breaker, Retry Policy & Order Reconciliation Architecture

## 1. Overview
This document details the production hardening architecture for the BTC/USDT trading bot, specifically focusing on API fault tolerance, circuit breaker mechanisms, order execution idempotency, and position reconciliation.

---

## 2. Circuit Breaker Architecture
- **Purpose**: Prevents flooded API calls, IP bans (HTTP 429), or infinite execution loops during sustained exchange outages or network disconnects.
- **Configurable Thresholds**:
  - `MAX_CONSECUTIVE_API_ERRORS` (Default: `5`): Maximum allowable consecutive unhandled API errors in the main trading loop before tripping.
  - `CIRCUIT_BREAKER_COOLDOWN_SEC` (Default: `300` seconds / 5 minutes): Minimum cooldown period before manual or automatic bot resumption.
- **Behavior Upon Tripping**:
  1. Sets `SHARED_STATE["status"] = "stopped"`.
  2. Sets `SHARED_STATE["circuit_breaker_tripped"] = True`.
  3. Logs a `CRITICAL` alert: `CIRCUIT_BREAKER TRIGGERED: Exceeded 5 consecutive API/system errors. Safely halting trading operations.`
  4. Exits the background trading thread cleanly without leaving open orphan loop states.
- **Restart Procedure**:
  - **Manual Web Dashboard Restart**: Operators can click "Start Bot" in the Web Dashboard UI after resolving network/API key issues, which resets `consecutive_errors = 0` and clears `circuit_breaker_tripped`.

---

## 3. CCXT API Retry Policy
All network API interactions are wrapped with `data_fetcher.retry_api_call()` using exponential backoff (initial delay: 1.0s, doubling per attempt up to `max_retries=3`).

### Protected Read-Only & Configuration Endpoints
The following endpoints use automatic transient retry backoff:
1. `fetch_ohlcv`: Retried on `NetworkError`, `RequestTimeout`, `RateLimitExceeded`, `DDoSProtection`.
2. `fetch_balance`: Retried on transient CCXT errors.
3. `fetch_positions`: Retried on transient CCXT errors.
4. `fetch_my_trades`: Retried on transient CCXT errors.
5. `fetch_open_orders`: Retried on transient CCXT errors.
6. `set_leverage_and_margin`: Retried on transient CCXT errors.

### Non-Transient Failures (Fast Fail)
The following fatal errors are **never retried** and fail fast immediately:
- `ccxt.AuthenticationError`
- `ccxt.PermissionDenied`
- `ccxt.InvalidOrder`
- `ccxt.BadRequest`
- `ccxt.InsufficientFunds`
- `ccxt.InvalidNonce`

---

## 4. Duplicate Order Prevention & Position Reconciliation

### Why Order Placement is Handled Differently
Unlike read-only queries (such as `fetch_ohlcv`), market order creation (`create_order`) is **non-idempotent by default**. If a network timeout occurs after Bybit receives and fills the order but before the HTTP response reaches the bot:
1. Blindly re-issuing `create_order` would place a **second, duplicate position** on the exchange.
2. This creates unintended double leverage and severe capital risk.

### Reconciliation Strategy (`_check_existing_position`)
To solve duplicate order risk:
1. **`clientOrderId` / `orderLinkId`**: Every market order generates a deterministic client order identifier (`btc_<uuid>`). Bybit links this identifier to the order.
2. **Pre-Order Reconciliation**: Before calling `create_order`, `executor.place_order()` executes `_check_existing_position(symbol, target_side)` to verify whether an active position or open order already exists. If found, entry is aborted.
3. **Post-Timeout Reconciliation**: If a `ccxt.NetworkError` or `ccxt.RequestTimeout` occurs during `create_order()`, the executor **does not blindly re-submit**. It immediately executes `_check_existing_position(symbol, target_side)`:
   - If Bybit opened the position during the timeout, `place_order()` detects the position, logs `RECONCILIATION SUCCESSFUL`, and returns the position object.
   - A new order is submitted **only** if reconciliation confirms zero positions exist on Bybit.

---

## 5. Summary of Protection Matrix

| Endpoint | Retry Protected | Reconciliation Guarded | Circuit Breaker Protected |
|---|---|---|---|
| `fetch_ohlcv` | YES | N/A | YES |
| `fetch_balance` | YES | N/A | YES |
| `fetch_positions` | YES | N/A | YES |
| `fetch_my_trades` | YES | N/A | YES |
| `fetch_open_orders` | YES | N/A | YES |
| `set_leverage` | YES | N/A | YES |
| `create_order` | Guarded | **YES** | YES |
