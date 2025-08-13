# PRD: Hyperliquid Async Trade Execution Implementation

## Introduction/Overview

This feature implements Hyperliquid's async API for non-blocking, concurrent trade operations in a Discord trade copying bot. The implementation uses Hyperliquid's CCXT integration with custom direct API calls where needed to properly handle subaccount operations.

## Goals

1. Implement async trade execution on Hyperliquid exchange
2. Enable concurrent execution of multiple trade operations without blocking
3. Support multiple Hyperliquid subaccounts (3 initially, expandable)
4. Integrate with existing Discord trade signal scraping
5. Implement proper error handling and retry logic for failed operations

## User Stories

1. **As a trader**, I want my bot to execute trades on Hyperliquid so that I can benefit from better liquidity and lower fees
2. **As a trader**, I want trades to execute concurrently so that multiple signals can be processed simultaneously without delays
3. **As a system operator**, I want to use multiple subaccounts so that I can segregate risk across different trading strategies
4. **As a system operator**, I want failed trades to retry automatically so that temporary API issues don't cause missed opportunities
5. **As a trader**, I want the system to gracefully handle unavailable symbols so that one bad signal doesn't crash the entire bot

## Functional Requirements

### Core Trading Operations
1. The system must support async placement of limit orders with multiple entry points
2. The system must support async stop loss and take profit order management using trigger orders
3. The system must calculate position sizes based on risk parameters
4. The system must support async order updates/modifications for existing positions
5. The system must support async position closing operations
6. The system must cancel and replace existing orders when updates are received

### Account Management
7. The system must support 3 Hyperliquid subaccounts with separate API wallets
8. The system must allow dynamic addition of new subaccounts via configuration
9. The system must store credentials securely (master address, subaccount address, private key per subaccount)

### Symbol Mapping
10. The system must convert Discord's SYMBOL/USDT format to Hyperliquid's SYMBOL/USDC:USDC format
11. The system must maintain a configurable symbol mapping for edge cases
12. The system must gracefully skip trades for unavailable symbols and log the event

### Order Management
13. **CRITICAL**: The system must use direct Hyperliquid API to fetch orders for subaccounts
14. The system must handle CCXT limitations with subaccounts gracefully
15. The system must properly distinguish between placing orders (use vaultAddress) and fetching orders (use user address)

### Error Handling
16. The system must implement exponential backoff retry logic for failed API calls (max 3 retries)
17. The system must log all errors without halting the main execution loop
18. The system must maintain the existing notification system (sounds and event logging)

### Integration
19. The system must integrate with existing state management (state.py)
20. The system must integrate with existing trade parser output format
21. The system must maintain compatibility with existing configuration structure

## Non-Goals (Out of Scope)

1. This implementation will NOT modify Discord scraping logic
2. This implementation will NOT include UI/dashboard development
3. This implementation will NOT implement advanced trading strategies
4. This implementation will NOT include historical trade analysis
5. This implementation will NOT support testnet environments
6. This implementation will NOT include unit tests
7. This implementation will NOT modify the main polling loop structure

## Design Considerations

### File Structure
- `hyperliquid_executor.py`: Core async execution logic
- `hyperliquid_clients.py`: Client initialization and management
- `hyperliquid_handler.py`: Trade routing and orchestration
- Minimal changes to `main.py` - only import statements and handler initialization

### CCXT Integration with Direct API Fallback
- Use CCXT's `hyperliquid` for most operations
- Use direct Hyperliquid API for fetching subaccount orders
- Implement proper async patterns without overcomplicating

### Authentication Structure
Each subaccount requires:
- `account_address`: Master wallet address (same for all subaccounts)
- `subaccount_address`: Unique subaccount address for trading
- `private_key`: Private key for the API wallet

### Configuration
- Store credentials as:
  - `HYPERLIQUID_ACCOUNT_ADDRESS_[1-3]`
  - `HYPERLIQUID_PRIVATE_KEY_[1-3]`
  - `HYPERLIQUID_SUBACCOUNT_[1-3]`
- Maintain existing risk parameters and leverage settings

## Technical Considerations

### Dependencies
- `ccxt` with async support for Hyperliquid
- `aiohttp` for direct API calls
- No additional dependencies required

### Critical API Patterns
```python
# For placing/canceling orders - use vaultAddress
params = {'vaultAddress': subaccount_address}
await client.create_limit_order(symbol, side, amount, price, params)

# For fetching orders - use direct API with user
payload = {
    "type": "openOrders",
    "user": subaccount_address  # NOT vaultAddress
}
response = await session.post("https://api.hyperliquid.xyz/info", json=payload)
```

### Symbol Format Conversion
- Convert: `symbol.replace("/USDT", "/USDC:USDC")`
- Fallback to exact mapping dictionary for special cases

### Stop Loss / Take Profit
- Use `type='limit'` with trigger parameters
- Never use `type='market'` for trigger orders
- Orders remain dormant until triggered

### Concurrency
- CCXT handles async operations properly
- No need for custom session management
- Natural throttling through async execution

## Success Metrics

1. All trades execute on Hyperliquid successfully
2. Proper handling of subaccount orders (fetch and cancel)
3. Successful handling of 3+ concurrent trade signals
4. 95%+ success rate for trade execution with retry logic
5. Graceful handling of unavailable symbols without system crashes

## Implementation Notes

### Key Learnings from Development
1. **CCXT fetch_orders() doesn't work for subaccounts** - must use direct API
2. **Different parameters for different operations** - vaultAddress vs user
3. **Don't overcomplicate** - CCXT handles async properly without custom sessions
4. **Test incrementally** - never revert working code wholesale
5. **Position size vs risk** - use fixed position sizes for testing

### Retry Logic
```python
async def with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Common Pitfalls to Avoid

1. Using CCXT's fetch_orders() for subaccounts - it returns stale data
2. Using clientOrderId - not supported by Hyperliquid via CCXT
3. Tracking order IDs manually - fetch fresh each time
4. Using type='market' for SL/TP - causes immediate execution
5. Overengineering session management - CCXT handles it