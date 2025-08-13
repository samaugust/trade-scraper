FOLLOWED_TRADERS = {
    "Victorious",
    "Perdu",
    "Osbrah"
}

POLL_INTERVAL_SECONDS = 20

SESSION = "storage/session.json"
STATE = "storage/state.json"

ACTIVE_TRADES_CHANNEL = "https://discord.com/channels/953383649930248232/1185250680391335976"

UPDATES_CHANNEL = "https://discord.com/channels/953383649930248232/1172705132853600337"

RISK_PER_TRADE = 1  # $1 risk per trade (for testing)
LEVERAGE = 10
MARGIN_MODE = "CROSS"

# Hyperliquid-specific settings
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz"  # Mainnet API URL

# Symbol mapping overrides for edge cases
# Add entries here if automatic USDT->USD conversion doesn't work
HYPERLIQUID_SYMBOL_OVERRIDES = {
    # Example: "1000PEPE/USDT": "PEPE/USD",
    # Example: "1000SHIB/USDT": "SHIB/USD",
}

# Trader to subaccount mapping (which subaccount handles which trader)
TRADER_SUBACCOUNT_MAP = {
    "Perdu": 1,       # Subaccount 1
    "Victorious": 2,  # Subaccount 2
    "Osbrah": 3,      # Subaccount 3
}