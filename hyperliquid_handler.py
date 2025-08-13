"""
Hyperliquid trade routing and orchestration handler.
Routes trades to appropriate operations (CREATE/UPDATE/CLOSE) based on trade type.
"""

from typing import Dict, Optional
from config import FOLLOWED_TRADERS, TRADER_SUBACCOUNT_MAP, RISK_PER_TRADE
from hyperliquid_clients import get_client_for_trader, initialize_clients
from hyperliquid_executor import (
    place_orders,
    cancel_orders,
    set_stop_loss_take_profit,
    close_position,
    convert_symbol
)
from utils import play_notification

async def handle_trade_update(
    trade_data: Dict,
    crud_type: str,
    url: str,
    state: Dict,
    events_counter: Optional[Dict] = None
) -> bool:
    """
    Main handler for routing trade updates to appropriate Hyperliquid operations.
    
    Args:
        trade_data: Parsed trade data from Discord
        crud_type: Type of operation (CREATE/UPDATE/CLOSE)
        url: Discord message URL
        state: Application state dictionary
        events_counter: Counter for tracking events
        
    Returns:
        bool: True if trade was processed successfully
    """
    # Ensure clients are initialized
    if not hasattr(handle_trade_update, 'initialized'):
        print("[INFO] Initializing Hyperliquid clients...")
        await initialize_clients()
        handle_trade_update.initialized = True
    
    # Extract trader name from trade data
    trader_name = trade_data.get('trader', '').strip()
    
    # Validate trader is followed
    if trader_name not in FOLLOWED_TRADERS:
        print(f"[INFO] Skipping trade from unfollowed trader: {trader_name}")
        return False
    
    # Get client for this trader
    client, subaccount_address = await get_client_for_trader(trader_name)
    if not client:
        print(f"[ERROR] No client available for trader {trader_name}")
        return False
    
    # Get subaccount number for logging
    subaccount_num = TRADER_SUBACCOUNT_MAP.get(trader_name, "Unknown")
    
    # Extract trade parameters
    symbol = trade_data.get('symbol')
    side = trade_data.get('side')  # 'long' or 'short'
    entries = trade_data.get('entries', [])
    stop_loss = trade_data.get('stop_loss')
    take_profit = trade_data.get('take_profit')
    closed_price = trade_data.get('closed_price')
    # Allow override of risk_per_trade for testing (0 = test mode with $10 position)
    risk_per_trade = trade_data.get('risk_per_trade', RISK_PER_TRADE)
    
    # Validate required fields
    if not symbol:
        print(f"[ERROR] Missing symbol in trade data")
        return False
    
    # Check if symbol is available on Hyperliquid
    try:
        hl_symbol = await convert_symbol(symbol)
        print(f"[INFO] Processing {crud_type} for {hl_symbol} on subaccount {subaccount_num} (trader: {trader_name})")
    except Exception as e:
        print(f"[WARNING] Symbol {symbol} not available on Hyperliquid: {e}")
        return False
    
    try:
        # Route to appropriate operation
        if crud_type == "CREATE":
            success = await handle_create_trade(
                client, subaccount_address, symbol, side, entries, 
                stop_loss, take_profit, trader_name, risk_per_trade
            )
            
            if success and events_counter:
                events_counter["hyperliquid_new_trades"] += 1
                play_notification("Glass")
                
        elif crud_type == "UPDATE":
            success = await handle_update_trade(
                client, subaccount_address, symbol, side, entries,
                stop_loss, take_profit, trader_name, risk_per_trade
            )
            
            if success and events_counter:
                events_counter["hyperliquid_updates"] += 1
                play_notification("Tink")
                
        elif crud_type == "CLOSE" or closed_price:
            success = await handle_close_trade(
                client, subaccount_address, symbol, trader_name
            )
            
            if success and events_counter:
                events_counter["hyperliquid_updates"] += 1
                play_notification("Pop")
        else:
            print(f"[WARNING] Unknown crud_type: {crud_type}")
            return False
            
        return success
        
    except Exception as e:
        print(f"[ERROR] Failed to process {crud_type} trade: {e}")
        return False

async def handle_create_trade(
    client,
    subaccount_address: str,
    symbol: str,
    side: str,
    entries: list,
    stop_loss: float,
    take_profit: Optional[float],
    trader_name: str,
    risk_per_trade: float = RISK_PER_TRADE
) -> bool:
    """
    Handle CREATE operation: place entry orders, then set SL/TP.
    
    Args:
        client: CCXT Hyperliquid client
        subaccount_address: Subaccount address
        symbol: Trading symbol
        side: 'long' or 'short'
        entries: List of entry prices
        stop_loss: Stop loss price
        take_profit: Optional take profit price
        trader_name: Name of the trader
        
    Returns:
        bool: True if successful
    """
    print(f"[CREATE] Placing new {side} trade for {symbol} (trader: {trader_name})")
    
    if not entries or not stop_loss or not side:
        print(f"[ERROR] Missing required fields for CREATE: entries={entries}, stop_loss={stop_loss}, side={side}")
        return False
    
    # Place entry orders
    orders = await place_orders(
        client, symbol, side, entries, stop_loss, risk_per_trade
    )
    
    if not orders:
        print(f"[ERROR] Failed to place entry orders for {symbol}")
        return False
    
    # Set stop loss and take profit
    if stop_loss or take_profit:
        sl_order, tp_order = await set_stop_loss_take_profit(
            client, symbol, side, stop_loss, take_profit
        )
        
        if not sl_order and stop_loss:
            print(f"[WARNING] Failed to set stop loss for {symbol}")
        if not tp_order and take_profit:
            print(f"[WARNING] Failed to set take profit for {symbol}")
    
    print(f"[CREATE] Successfully created trade for {symbol}")
    return True

async def handle_update_trade(
    client,
    subaccount_address: str,
    symbol: str,
    side: str,
    entries: list,
    stop_loss: float,
    take_profit: Optional[float],
    trader_name: str,
    risk_per_trade: float = RISK_PER_TRADE
) -> bool:
    """
    Handle UPDATE operation: cancel old orders, place new ones, update SL/TP.
    
    Args:
        client: CCXT Hyperliquid client
        subaccount_address: Subaccount address
        symbol: Trading symbol
        side: 'long' or 'short'
        entries: List of entry prices
        stop_loss: Stop loss price
        take_profit: Optional take profit price
        trader_name: Name of the trader
        
    Returns:
        bool: True if successful
    """
    print(f"[UPDATE] Updating {side} trade for {symbol} (trader: {trader_name})")
    
    # Cancel all existing orders for this symbol
    canceled = await cancel_orders(client, symbol, subaccount_address)
    print(f"[UPDATE] Canceled {canceled} existing orders for {symbol}")
    
    # Place new entry orders if provided
    if entries and side and stop_loss:
        orders = await place_orders(
            client, symbol, side, entries, stop_loss, risk_per_trade
        )
        
        if not orders:
            print(f"[WARNING] Failed to place updated entry orders for {symbol}")
    
    # Update stop loss and take profit
    if (stop_loss or take_profit) and side:
        sl_order, tp_order = await set_stop_loss_take_profit(
            client, symbol, side, stop_loss, take_profit
        )
        
        if not sl_order and stop_loss:
            print(f"[WARNING] Failed to update stop loss for {symbol}")
        if not tp_order and take_profit:
            print(f"[WARNING] Failed to update take profit for {symbol}")
    
    print(f"[UPDATE] Successfully updated trade for {symbol}")
    return True

async def handle_close_trade(
    client,
    subaccount_address: str,
    symbol: str,
    trader_name: str
) -> bool:
    """
    Handle CLOSE operation: cancel all orders and close position if exists.
    
    Args:
        client: CCXT Hyperliquid client
        subaccount_address: Subaccount address
        symbol: Trading symbol
        trader_name: Name of the trader
        
    Returns:
        bool: True if successful
    """
    print(f"[CLOSE] Closing trade for {symbol} (trader: {trader_name})")
    
    # Close position (cancels orders and closes any open position)
    success = await close_position(client, symbol, subaccount_address)
    
    if success:
        print(f"[CLOSE] Successfully closed trade for {symbol}")
    else:
        print(f"[ERROR] Failed to close trade for {symbol}")
    
    return success