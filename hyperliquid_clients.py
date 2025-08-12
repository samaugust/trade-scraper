import os
from dotenv import load_dotenv
from hyperliquid import HyperliquidAsync

load_dotenv()

# Environment Variables Required (in .env file):
# 
# For each subaccount (1, 2, 3), you need:
# HYPERLIQUID_ACCOUNT_ADDRESS_[1-3] - Master wallet address (same for all)
# HYPERLIQUID_API_WALLET_[1-3]      - Unique API wallet address for this subaccount
# HYPERLIQUID_PRIVATE_KEY_[1-3]     - Private key for the API wallet
# HYPERLIQUID_SUBACCOUNT_[1-3]      - Subaccount address (optional, uses master if not set)
#
# Example:
# HYPERLIQUID_ACCOUNT_ADDRESS_1=0xYourMasterWalletAddress
# HYPERLIQUID_API_WALLET_1=0xAPIWalletAddressForSubaccount1
# HYPERLIQUID_PRIVATE_KEY_1=0xPrivateKeyForAPIWallet1
# HYPERLIQUID_SUBACCOUNT_1=0xSubaccount1Address

def create_client(subaccount_num):
    """Create a Hyperliquid client for a specific subaccount."""
    master_address = os.getenv(f"HYPERLIQUID_ACCOUNT_ADDRESS_{subaccount_num}")
    private_key = os.getenv(f"HYPERLIQUID_PRIVATE_KEY_{subaccount_num}")
    subaccount_address = os.getenv(f"HYPERLIQUID_SUBACCOUNT_{subaccount_num}")
    
    if not master_address or not private_key:
        raise ValueError(f"Missing credentials for subaccount {subaccount_num}")
    
    config = {
        'account_address': master_address,
        'private_key': private_key,
    }
    
    # Add vault_address if subaccount is specified
    if subaccount_address:
        config['vault_address'] = subaccount_address
    
    try:
        return HyperliquidAsync(config)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Hyperliquid client for subaccount {subaccount_num}: {e}")
        raise

# Initialize clients for each trader
try:
    client_1 = create_client(1)
    client_2 = create_client(2)
    client_3 = create_client(3)
    
    # Map traders to their respective clients
    TRADER_TO_CLIENT = {
        "Perdu": client_1,
        "Victorious": client_2,
        "Osbrah": client_3,
    }
    
    print("[INFO] Hyperliquid clients initialized successfully")
    
except Exception as e:
    print(f"[CRITICAL] Failed to initialize Hyperliquid clients: {e}")
    TRADER_TO_CLIENT = {}