# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a cryptocurrency trading copy bot that monitors Discord channels for trade signals and automatically executes trades on Hyperliquid exchange. The system scrapes trading signals from followed traders in Discord channels and replicates them using the Hyperliquid API.

## Hyperliquid Integration (Clean Implementation Needed)

### Current State (2025-08-13)
- All previous Hyperliquid implementation files have been deleted for a clean restart
- Discord scraping system remains intact and working
- Configuration and credentials are preserved in .env
- See `tasks/prd-hyperliquid-clean-implementation.md` for implementation requirements

### Implementation Details

#### Authentication Structure
Each of 3 subaccounts requires:
- Master wallet address (same for all subaccounts)
- API wallet private key (unique per subaccount)
- Subaccount address for trading operations

#### Symbol Format
- Discord format: `BTC/USDT`
- Hyperliquid format: `BTC/USDC:USDC` (perpetual futures)
- Conversion handled in `hyperliquid_handler.py`

#### Key Technical Details
- **CCXT Library**: Using `ccxt.async_support.hyperliquid` for API operations
- **Subaccount Trading**: Pass `vaultAddress` in params for all operations
- **Position Info**: CCXT's `fetch_positions()` doesn't work with subaccounts - use direct API call to `clearinghouseState` endpoint
- **Order Fetching**: Use `fetch_orders()` instead of `fetch_open_orders()` for subaccounts, then filter by status
- **Stop Loss/Take Profit**: Implemented as trigger orders using `type='limit'` with `triggerPrice` and `triggerType` params
  - IMPORTANT: Use `type='limit'` NOT `type='market'` for trigger orders to avoid immediate execution
  - Orders wait dormant until trigger price is hit, then execute as market orders

#### Trader Mapping
- Subaccount 1: Perdu
- Subaccount 2: Victorious  
- Subaccount 3: Osbrah

### Environment Variables Required
```
# For each subaccount (1, 2, 3):
HYPERLIQUID_ACCOUNT_ADDRESS_[1-3]  # Master wallet address
HYPERLIQUID_PRIVATE_KEY_[1-3]      # API wallet private key
HYPERLIQUID_SUBACCOUNT_[1-3]       # Subaccount address
```

## Architecture

### Core Components
- **main.py**: Entry point with polling loop that orchestrates scraping and trade execution
- **session.py**: Playwright browser session management for Discord channel access
- **state.py**: Persistent state management (active trades, message tracking)
- **config.py**: Configuration including followed traders, channels, and risk parameters

### Scrapers
- **active_trades_scraper.py**: Monitors #active-trades Discord channel for new trade signals
- **trade_updates_scraper.py**: Monitors #trade-updates channel for modifications to existing trades

### Trade Processing
- **trade_parser.py**: Extracts trade data (symbol, entries, stop loss, take profit) from Discord message HTML
- **hyperliquid_handler.py**: (TO BE IMPLEMENTED) Routes trade updates to appropriate Hyperliquid operations (CREATE/UPDATE/CLOSE)
- **hyperliquid_executor.py**: (TO BE IMPLEMENTED) Hyperliquid API operations with proper error handling and retries
- **hyperliquid_clients.py**: (TO BE IMPLEMENTED) Client initialization with subaccount configuration

### Utilities
- **utils.py**: Notification sounds and event logging

## Key Data Flow

1. Browser sessions maintain persistent connections to Discord channels
2. Scrapers detect changes via content hashing and message ID tracking
3. Trade parser extracts structured data from Discord HTML
4. Hyperliquid handler determines action type (CREATE/UPDATE/CLOSE) and routes accordingly
5. Executor performs actual trading operations via Hyperliquid API
6. State is persisted after each operation

## Known Issues & Workarounds

### CCXT Library Limitations with Hyperliquid Subaccounts
1. **fetch_positions() doesn't work**: Use direct API call to clearinghouseState endpoint (implemented in get_position_info)
2. **fetch_open_orders() doesn't work**: Must use direct Hyperliquid API - see critical solution below
3. **fetch_orders() returns stale/ghost orders**: Returns orders that are already canceled and can't be found

### CRITICAL: Fetching Orders for Subaccounts
**Problem**: CCXT's `fetch_orders()` and `fetch_open_orders()` don't properly query subaccount orders. They return stale/ghost orders instead of actual open orders.

**Solution**: Use direct Hyperliquid API call with subaccount address as `user` parameter:
```python
url = "https://api.hyperliquid.xyz/info"
payload = {
    "type": "openOrders",
    "user": subaccount_address  # NOT vaultAddress - use subaccount as user
}
```

**Key Distinction**:
- When PLACING/CANCELING orders: Use `vaultAddress` parameter
- When FETCHING orders: Query with subaccount address as `user`

### Stop Loss / Take Profit Implementation
- **CRITICAL**: Must use `type='limit'` with trigger params, NOT `type='market'`
- Trigger orders remain dormant until price hits trigger level
- Both SL and TP execute as market orders when triggered for immediate fill
- No pre-calculation of slippage needed - use exact trader-specified prices
- SL/TP can be set even when main orders are pending (not filled yet)

### Order Cancellation
- Don't rely on order ID tracking - fetch current orders directly
- Use the direct API method above to get actual open orders
- Cancel each order individually - `cancel_all_orders()` is not implemented in CCXT
- Ignore "already canceled" errors - these are expected for stale orders

### Important Implementation Notes
1. **DO NOT overcomplicate with session management** - CCXT handles async properly
2. **DO NOT track order IDs manually** - fetch them fresh each time
3. **DO NOT use clientOrderId** - Hyperliquid doesn't support it via CCXT
4. **DO NOT revert working code** - always test incrementally
5. **ALWAYS use the direct API for fetching subaccount orders** - this is the key fix

## Development Commands

### Setup and Running
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install playwright beautifulsoup4 ccxt python-dotenv aiohttp

# Install Playwright browsers
playwright install

# Run the application
python main.py
```

### Configuration
- Create `.env` file with Hyperliquid API credentials (see Environment Variables section)
- Risk per trade: Configured in config.py (default $1, minimum $10 for Hyperliquid)
- Leverage: Auto-managed by exchange

### Storage
- `storage/session.json`: Playwright browser session state
- `storage/state.json`: Application state (trades, message tracking)

## Important Notes

- System uses non-headless browser for Discord authentication
- Trades are filtered by followed traders and trade type (excludes spot, filled trades)
- Risk management: configurable risk per trade (minimum $10 due to Hyperliquid requirements)
- Supports multiple trader accounts with separate API credentials
- Graceful shutdown handling preserves state
- Orders on Hyperliquid must meet minimum value of $10