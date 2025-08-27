"""
Hyperliquid client management system for multiple subaccounts.
Handles initialization and mapping of traders to their respective subaccounts.
"""

import os
import ccxt.async_support as ccxt
from dotenv import load_dotenv
from config import TRADER_SUBACCOUNT_MAP

# Load environment variables
load_dotenv()

# Global client storage
clients = {}

async def initialize_clients():
    """
    Initialize CCXT Hyperliquid clients for all configured subaccounts.
    Each subaccount requires:
    - HYPERLIQUID_ACCOUNT_ADDRESS_[1-3]: Master wallet address
    - HYPERLIQUID_PRIVATE_KEY_[1-3]: API wallet private key  
    - HYPERLIQUID_SUBACCOUNT_[1-3]: Subaccount address for trading
    """
    global clients
    
    for subaccount_num in [1, 2, 3]:
        try:
            # Load credentials for this subaccount
            account_address = os.getenv(f"HYPERLIQUID_ACCOUNT_ADDRESS_{subaccount_num}")
            private_key = os.getenv(f"HYPERLIQUID_PRIVATE_KEY_{subaccount_num}")
            subaccount_address = os.getenv(f"HYPERLIQUID_SUBACCOUNT_{subaccount_num}")
            
            if not all([account_address, private_key, subaccount_address]):
                print(f"[WARNING] Missing credentials for subaccount {subaccount_num}, skipping initialization")
                continue
            
            # Create CCXT client with proper configuration
            # CCXT Hyperliquid requires walletAddress and privateKey
            client = ccxt.hyperliquid({
                'walletAddress': account_address,    # Master wallet address
                'privateKey': private_key,            # API wallet private key
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',            # Perpetual futures
                    'vaultAddress': subaccount_address  # Subaccount for trading
                }
            })
            
            # Verify client can connect to API
            if await verify_client_connection(client):
                # Store client with subaccount number as key
                clients[subaccount_num] = {
                    'client': client,
                    'subaccount_address': subaccount_address,
                    'account_address': account_address
                }
                print(f"[INFO] Initialized and verified Hyperliquid client for subaccount {subaccount_num}")
            else:
                print(f"[ERROR] Failed to verify connection for subaccount {subaccount_num}")
                await client.close()
            
        except Exception as e:
            print(f"[ERROR] Failed to initialize client for subaccount {subaccount_num}: {e}")

async def get_client_for_trader(trader_name: str):
    """
    Get the CCXT client for a specific trader based on the mapping in config.
    
    Args:
        trader_name: Name of the trader (from environment variables)
        
    Returns:
        Tuple of (client, subaccount_address) or (None, None) if not found
    """
    # Check if trader is mapped to a subaccount
    if trader_name not in TRADER_SUBACCOUNT_MAP:
        print(f"[ERROR] Trader '{trader_name}' not found in TRADER_SUBACCOUNT_MAP")
        return None, None
    
    subaccount_num = TRADER_SUBACCOUNT_MAP[trader_name]
    
    # Check if client exists for this subaccount
    if subaccount_num not in clients:
        print(f"[ERROR] No client initialized for subaccount {subaccount_num} (trader: {trader_name})")
        return None, None
    
    client_info = clients[subaccount_num]
    return client_info['client'], client_info['subaccount_address']

async def verify_client_connection(client):
    """
    Verify that a client can connect to Hyperliquid API.
    
    Args:
        client: CCXT Hyperliquid client instance
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        # Try to fetch markets as a connection test
        await client.load_markets()
        return True
    except Exception as e:
        print(f"[ERROR] Client connection verification failed: {e}")
        return False

async def close_all_clients():
    """
    Close all initialized clients properly.
    """
    global clients
    for subaccount_num, client_info in clients.items():
        try:
            await client_info['client'].close()
            print(f"[INFO] Closed client for subaccount {subaccount_num}")
        except Exception as e:
            print(f"[ERROR] Failed to close client for subaccount {subaccount_num}: {e}")
    
    clients = {}