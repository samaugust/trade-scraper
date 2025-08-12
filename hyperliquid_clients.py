import os
from dotenv import load_dotenv
from hyperliquid import HyperliquidAsync

load_dotenv()

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