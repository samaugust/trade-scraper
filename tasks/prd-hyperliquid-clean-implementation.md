# PRD: Hyperliquid Clean Implementation

## Introduction/Overview

This document outlines requirements for a clean, ground-up implementation of Hyperliquid trade execution for the Discord trade copying bot. The current implementation has become complex and difficult to maintain due to accumulated workarounds and fixes. This PRD defines a simplified, correct implementation that properly handles CCXT limitations with Hyperliquid subaccounts while maintaining all existing functionality.

The core issue being solved is that CCXT's Hyperliquid integration doesn't properly support subaccount operations, particularly fetching open orders. This implementation will use CCXT where it works and direct API calls where necessary, with clear documentation of when each approach is used.

## Goals

1. Create a clean, maintainable implementation of Hyperliquid trade execution
2. Properly handle all CCXT limitations with documented workarounds
3. Ensure reliable order placement, fetching, and cancellation for subaccounts
4. Implement concurrent operations without blocking
5. Provide clear code that a junior developer can understand and modify
6. Document the critical distinction between vaultAddress (for placing/canceling) and user (for fetching)
7. Eliminate complexity from previous iterations while maintaining full functionality

## User Stories

1. **As a trader**, I want my trades to execute on the correct Hyperliquid subaccount so that I can segregate strategies and risk
2. **As a trader**, I want order updates to cancel old orders and place new ones atomically so that I don't have conflicting orders
3. **As a trader**, I want stop loss and take profit orders to be set even when my entry orders haven't filled yet
4. **As a system operator**, I want clear logs showing what operations are happening on which subaccount
5. **As a developer**, I want to understand why certain API patterns are used so I can maintain and extend the code
6. **As a developer**, I want the code to be simple and direct without unnecessary abstractions

## Functional Requirements

### Core Order Operations
1. The system must place limit orders on the correct subaccount using vaultAddress parameter
2. The system must place multiple entry orders concurrently using asyncio.gather()
3. The system must fetch open orders using direct API with user parameter (NOT vaultAddress)
4. The system must cancel orders individually (cancel_all_orders not supported)
5. The system must ignore "already canceled" errors when canceling stale orders
6. The system must set stop loss and take profit as trigger orders using type='limit'
7. The system must NEVER use type='market' for trigger orders (causes immediate execution)
8. The system must handle SL/TP for pending orders (not just filled positions)

### Subaccount Management
9. The system must support 3 fixed subaccounts mapped to specific traders
10. The system must use the correct subaccount address when fetching orders (as user)
11. The system must use the correct subaccount address when placing/canceling (as vaultAddress)
12. The system must log which subaccount is being used for each operation

### Symbol Conversion
13. The system must convert Discord format (BTC/USDT) to Hyperliquid format (BTC/USDC:USDC)
14. The system must support configurable symbol overrides for edge cases
15. The system must gracefully skip unavailable symbols with clear logging

### Order Fetching (Critical Requirement)
16. The system must NOT use CCXT's fetch_orders() for subaccounts (returns stale data)
17. The system must use direct Hyperliquid API call to fetch open orders:
    ```python
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "openOrders", "user": subaccount_address}
    ```
18. The system must properly parse the API response into CCXT-compatible format

### Position Information
19. The system must fetch position info using direct API (CCXT's fetch_positions doesn't work)
20. The system must use clearinghouseState endpoint for position data

### Error Handling
21. The system must implement retry logic with exponential backoff (max 3 attempts)
22. The system must continue processing other trades if one fails
23. The system must log all errors without crashing the main loop
24. The system must handle rate limits gracefully

### State Management
25. The system must NOT track order IDs between operations
26. The system must fetch fresh order data for each operation
27. The system must integrate with existing state.json for trade tracking

## Non-Goals (Out of Scope)

1. This implementation will NOT modify Discord scraping components
2. This implementation will NOT implement position sizing calculations (use fixed 0.0001 BTC)
3. This implementation will NOT handle partial fills
4. This implementation will NOT support spot trading
5. This implementation will NOT include unit tests
6. This implementation will NOT optimize for high-frequency trading
7. This implementation will NOT use client order IDs (not supported by Hyperliquid via CCXT)
8. This implementation will NOT implement custom session management (CCXT handles async properly)
9. This implementation will NOT track orders in memory or state

## Design Considerations

### File Structure
```
hyperliquid_executor.py    # Core async operations with direct API integration
hyperliquid_handler.py      # Routes trades to appropriate operations
hyperliquid_clients.py      # Client initialization with subaccount config
```

### Critical API Pattern
```python
# PLACING/CANCELING - use vaultAddress
params = {'vaultAddress': subaccount_address}
await client.create_limit_order(...)
await client.cancel_order(...)

# FETCHING - use direct API with user
async with aiohttp.ClientSession() as session:
    payload = {"type": "openOrders", "user": subaccount_address}
    response = await session.post("https://api.hyperliquid.xyz/info", json=payload)
```

### Function Signatures
```python
async def place_orders(client, symbol, side, entries, stop_loss, risk_per_trade)
async def cancel_orders(client, symbol, side=None)  # Must use direct API
async def get_open_orders(client, symbol)  # Direct API implementation
async def set_stop_loss_take_profit(client, symbol, side, stop_loss, take_profit)
async def close_position(client, symbol)
async def get_position_info(client, symbol)  # Direct API implementation
```

## Technical Considerations

### Dependencies
- `ccxt` with async support (existing)
- `aiohttp` for direct API calls (existing)
- No new dependencies required

### Key Implementation Details
1. **DO NOT** use fetch_orders() for subaccounts - always use direct API
2. **DO NOT** track order IDs - fetch fresh each time
3. **DO NOT** use market orders for SL/TP - use limit with trigger params
4. **DO NOT** create custom session management - let aiohttp handle it
5. **ALWAYS** distinguish between vaultAddress (operations) and user (queries)
6. **ALWAYS** handle "already canceled" errors gracefully
7. **ALWAYS** use asyncio.gather() for concurrent operations

### Error Response Patterns
```python
# Expected errors to ignore
"already canceled"  # Order was already canceled
"not found"        # Order doesn't exist
"does not exist"   # Order already gone

# Real errors to retry
"rate limit"       # Too many requests
"timeout"          # Network timeout
"connection"       # Connection error
```

## Success Metrics

1. **Reliability**: 100% of orders placed on correct subaccount
2. **Accuracy**: 100% of order fetches return current open orders (not stale)
3. **Completeness**: 100% of order updates cancel old orders before placing new
4. **Performance**: All concurrent operations complete without blocking
5. **Maintainability**: Code is clear enough for junior developer to modify
6. **Robustness**: System continues operating despite individual operation failures
7. **Correctness**: SL/TP orders work for both pending and filled orders

## Implementation Notes

### Order Lifecycle
1. **CREATE**: Place entry orders → Set SL/TP (even if entries pending)
2. **UPDATE**: Fetch current orders → Cancel old → Place new → Update SL/TP
3. **CLOSE**: Cancel all orders → Close position if exists

### Common Pitfalls to Avoid
1. Using fetch_orders() for subaccounts (returns stale/ghost orders)
2. Confusing vaultAddress with user parameter
3. Using type='market' for trigger orders
4. Tracking order IDs instead of fetching fresh
5. Over-engineering with sessions or connection pools
6. Reverting working code without understanding the issue
7. Not testing with actual subaccounts

### Testing Checklist
- [ ] Orders placed on correct subaccount
- [ ] Orders can be fetched after placement
- [ ] Orders can be canceled successfully
- [ ] SL/TP set correctly for pending orders
- [ ] Updates cancel old orders first
- [ ] Multiple entries placed concurrently
- [ ] System continues after individual failures

## Open Questions

None - all critical issues have been identified and solved:
- CCXT limitations are documented with workarounds
- Direct API usage is clearly defined
- Parameter usage (vaultAddress vs user) is explicit
- All edge cases have been addressed