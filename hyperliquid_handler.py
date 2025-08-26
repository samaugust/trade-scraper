"""
Hyperliquid trade routing and orchestration handler.
Routes trades to appropriate operations (CREATE/UPDATE/CLOSE) based on trade type.
"""

from typing import Dict, Optional
from config import FOLLOWED_TRADERS, TRADER_SUBACCOUNT_MAP, RISK_PER_TRADE
from hyperliquid_clients import get_client_for_trader
from hyperliquid_executor import (
    place_orders,
    cancel_orders,
    set_stop_loss_take_profit,
    close_position,
    get_position_info,
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
    take_profit = trade_data.get('take_profit')  # Single TP for backward compatibility
    take_profit_list = trade_data.get('take_profit_list', [])  # List of all TPs
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
            # Use TP list if available, otherwise fall back to single TP
            tp_to_use = take_profit_list if take_profit_list else ([take_profit] if take_profit else [])
            success = await handle_create_trade(
                client, subaccount_address, symbol, side, entries, 
                stop_loss, tp_to_use, trader_name, risk_per_trade
            )
            
            if success and events_counter:
                events_counter["hyperliquid_new_trades"] += 1
                play_notification("Glass")
                
        elif crud_type == "UPDATE":
            tp_to_use = take_profit_list if take_profit_list else ([take_profit] if take_profit else [])
            success = await handle_update_trade(
                client, subaccount_address, symbol, side, entries,
                stop_loss, tp_to_use, trader_name, risk_per_trade
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
    take_profit_list: list,  # Changed to list
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
    
    try:
        # Place entry orders
        orders = await place_orders(
            client, symbol, side, entries, stop_loss, risk_per_trade
        )
        
        if not orders:
            print(f"[ERROR] Failed to place entry orders for {symbol}")
            return False
    
        # Calculate total position size from placed orders
        total_position_size = 0
        for order in orders:
            if order and isinstance(order, dict):
                # Debug: see what fields are in the order
                print(f"[DEBUG] Order fields: {order.keys() if hasattr(order, 'keys') else 'not a dict'}")
                
                # Try different possible fields for amount
                amount = order.get('amount') or order.get('filled') or order.get('remaining')
                if amount is not None:
                    total_position_size += float(amount)
                else:
                    print(f"[WARNING] Order has no amount field: {order}")
        
        if total_position_size == 0:
            print(f"[WARNING] Could not determine position size from orders, using fallback")
            # Fallback: The place_orders function places the SAME size for EACH entry
            # So we need to multiply by the number of entries to get total position
            if entries and stop_loss and len(orders) > 0:
                avg_entry = sum(entries) / len(entries)
                num_orders_placed = len(orders)  # Actual number of orders placed
                
                # Calculate what size was used per order (same logic as place_orders)
                if risk_per_trade == 0 or risk_per_trade is None:
                    # Test mode: $10 position value per order
                    size_per_order = 10.0 / avg_entry
                else:
                    # Production: calculate from risk
                    stop_distance = abs(avg_entry - stop_loss) / avg_entry
                    if stop_distance > 0:
                        position_value = risk_per_trade / stop_distance
                        size_per_order = position_value / avg_entry
                        # Ensure minimum
                        min_size = 10.0 / avg_entry
                        size_per_order = max(size_per_order, min_size)
                    else:
                        size_per_order = 10.0 / avg_entry
                
                # Total position is size per order * number of orders
                total_position_size = size_per_order * num_orders_placed
                print(f"[DEBUG] Fallback: {num_orders_placed} orders × {size_per_order:.2f} = {total_position_size:.2f} total")
        
        print(f"[INFO] Total position size: {total_position_size}")
        
        # Set stop loss and take profits with the actual position size
        if (stop_loss or take_profit_list) and total_position_size > 0:
            sl_order, tp_orders = await set_stop_loss_take_profit(
                client, symbol, side, stop_loss, take_profit_list, total_position_size
            )
            
            if not sl_order and stop_loss:
                print(f"[WARNING] Failed to set stop loss for {symbol}")
            else:
                print(f"[SUCCESS] Stop loss order: {sl_order.get('id', 'unknown') if sl_order else 'None'}")
            
            if tp_orders:
                print(f"[SUCCESS] Placed {len(tp_orders)} take profit orders")
                for i, tp_order in enumerate(tp_orders):
                    if tp_order:
                        print(f"  TP {i+1}: {tp_order.get('id', 'unknown')}")
            elif take_profit_list:
                print(f"[WARNING] Failed to set take profit orders for {symbol}")
        
        print(f"[CREATE] Successfully created trade for {symbol}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Exception in handle_create_trade: {e}")
        import traceback
        traceback.print_exc()
        return False

async def handle_update_trade(
    client,
    subaccount_address: str,
    symbol: str,
    side: str,
    entries: list,
    stop_loss: float,
    take_profit_list: list,  # Changed to list
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
    total_position_size = 0
    if entries and side and stop_loss:
        orders = await place_orders(
            client, symbol, side, entries, stop_loss, risk_per_trade
        )
        
        if orders:
            for order in orders:
                if order and isinstance(order, dict):
                    amount = order.get('amount')
                    if amount is not None:
                        total_position_size += float(amount)
            print(f"[INFO] Total position size: {total_position_size}")
        else:
            print(f"[WARNING] Failed to place updated entry orders for {symbol}")
    
    # If no new orders placed, try to get existing position size
    if total_position_size == 0:
        position_info = await get_position_info(client, symbol, subaccount_address)
        if position_info and position_info.get('szi'):
            total_position_size = abs(float(position_info['szi']))
            print(f"[INFO] Using existing position size: {total_position_size}")
    
    # Update stop loss and take profit with actual position size
    if (stop_loss or take_profit_list) and side and total_position_size > 0:
        sl_order, tp_orders = await set_stop_loss_take_profit(
            client, symbol, side, stop_loss, take_profit_list, total_position_size
        )
        
        if not sl_order and stop_loss:
            print(f"[WARNING] Failed to update stop loss for {symbol}")
        
        if tp_orders:
            print(f"[SUCCESS] Updated {len(tp_orders)} take profit orders")
        elif take_profit_list:
            print(f"[WARNING] Failed to update take profit orders for {symbol}")
    
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