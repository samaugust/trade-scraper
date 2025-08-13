"""
Hyperliquid async trade execution operations.
Handles order placement, cancellation, and position management with direct API integration where needed.
"""

import asyncio
import aiohttp
from typing import List, Dict, Optional, Tuple
from config import HYPERLIQUID_API_URL, HYPERLIQUID_SYMBOL_OVERRIDES

async def convert_symbol(symbol: str) -> str:
    """
    Convert Discord symbol format to Hyperliquid format.
    
    Args:
        symbol: Symbol in Discord format (e.g., "BTC/USDT")
        
    Returns:
        Symbol in Hyperliquid format (e.g., "BTC/USDC:USDC")
    """
    # Check for overrides first
    if symbol in HYPERLIQUID_SYMBOL_OVERRIDES:
        return HYPERLIQUID_SYMBOL_OVERRIDES[symbol]
    
    # Standard conversion: replace /USDT with /USDC:USDC for perpetuals
    if symbol.endswith("/USDT"):
        base = symbol.replace("/USDT", "")
        return f"{base}/USDC:USDC"
    
    return symbol

async def with_retry(func, max_retries: int = 3):
    """
    Execute a function with exponential backoff retry logic.
    
    Args:
        func: Async function to execute
        max_retries: Maximum number of retry attempts
        
    Returns:
        Result from the function
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            error_msg = str(e).lower()
            
            # Don't retry for certain errors
            if "already canceled" in error_msg or "not found" in error_msg or "does not exist" in error_msg:
                print(f"[INFO] Ignoring expected error: {e}")
                return None
            
            if attempt == max_retries - 1:
                print(f"[ERROR] Max retries reached: {e}")
                raise
            
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"[WARNING] Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)

async def place_orders(
    client,
    symbol: str,
    side: str,
    entries: List[float],
    stop_loss: float,
    risk_per_trade: float = 10.0
) -> List[Dict]:
    """
    Place multiple entry orders concurrently.
    
    Args:
        client: CCXT Hyperliquid client
        symbol: Trading symbol (will be converted to Hyperliquid format)
        side: 'long' or 'short'
        entries: List of entry prices
        stop_loss: Stop loss price
        risk_per_trade: Risk amount per trade in USD (minimum $10)
        
    Returns:
        List of placed order responses
    """
    # Convert symbol format
    hl_symbol = await convert_symbol(symbol)
    
    # Convert side to buy/sell
    order_side = 'buy' if side == 'long' else 'sell'
    
    # Calculate position size
    avg_entry = sum(entries) / len(entries)
    
    # For testing or when risk_per_trade is 0, use fixed $10 position value
    if risk_per_trade == 0 or risk_per_trade is None:
        # Testing mode: use fixed $10 position value
        position_size = 10.0 / avg_entry
        print(f"[TEST MODE] Using fixed $10 position value")
    else:
        # Production mode: calculate based on risk amount and stop loss distance
        if stop_loss and avg_entry:
            stop_distance = abs(avg_entry - stop_loss) / avg_entry
            if stop_distance > 0:
                # Position value = risk / stop_distance
                position_value = risk_per_trade / stop_distance
                # Position size = position value / avg_entry
                position_size = position_value / avg_entry
                
                # Ensure minimum order value of $10 for Hyperliquid
                min_size = 10.0 / avg_entry
                if position_size * avg_entry < 10.0:
                    print(f"[WARNING] Calculated position value ${position_size * avg_entry:.2f} below $10 minimum, using minimum size")
                    position_size = min_size
            else:
                # If no stop distance, use minimum for Hyperliquid ($10 order value)
                position_size = 10.0 / avg_entry
        else:
            # Fallback to minimum order size if no stop loss provided
            position_size = 10.0 / avg_entry
    
    print(f"[INFO] Placing {len(entries)} {order_side} orders for {hl_symbol} with size {position_size}")
    
    # Create order placement tasks
    order_tasks = []
    for entry_price in entries:
        async def place_single_order(price):
            return await with_retry(
                lambda: client.create_limit_order(
                    symbol=hl_symbol,
                    side=order_side,
                    amount=position_size,
                    price=price
                )
            )
        
        order_tasks.append(place_single_order(entry_price))
    
    # Execute all orders concurrently
    orders = await asyncio.gather(*order_tasks, return_exceptions=True)
    
    # Filter out exceptions and None values
    successful_orders = [
        order for order in orders 
        if order and not isinstance(order, Exception)
    ]
    
    # Log any failures
    for i, order in enumerate(orders):
        if isinstance(order, Exception):
            print(f"[ERROR] Failed to place order at {entries[i]}: {order}")
    
    print(f"[INFO] Successfully placed {len(successful_orders)}/{len(entries)} orders")
    return successful_orders

async def get_open_orders(client, symbol: str, subaccount_address: str) -> List[Dict]:  # noqa: ARG001
    """
    Fetch open orders for a symbol using direct API (CCXT's fetch_orders doesn't work for subaccounts).
    
    Args:
        client: CCXT Hyperliquid client (not used for this operation)
        symbol: Trading symbol
        subaccount_address: Subaccount address to query
        
    Returns:
        List of open orders
    """
    hl_symbol = await convert_symbol(symbol)
    
    print(f"[INFO] Fetching open orders for {hl_symbol} on subaccount {subaccount_address}")
    
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {
            "type": "openOrders",
            "user": subaccount_address  # Use subaccount as user, NOT vaultAddress
        }
        
        try:
            async with session.post(f"{HYPERLIQUID_API_URL}/info", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Filter orders for the specific symbol
                    symbol_orders = []
                    if data and isinstance(data, list):
                        # Extract base symbol from hl_symbol (e.g., "BTC" from "BTC/USDC:USDC")
                        base_symbol = hl_symbol.split('/')[0]
                        
                        for order in data:
                            # Check if order belongs to this symbol
                            # Hyperliquid returns coin field which should match our base symbol
                            if order.get('coin', '').upper() == base_symbol.upper():
                                symbol_orders.append(order)
                    
                    print(f"[INFO] Found {len(symbol_orders)} open orders for {hl_symbol}")
                    return symbol_orders
                else:
                    error_text = await response.text()
                    print(f"[ERROR] Failed to fetch orders: {response.status} - {error_text}")
                    return []
        except Exception as e:
            print(f"[ERROR] Failed to fetch open orders: {e}")
            return []

async def cancel_orders(client, symbol: str, subaccount_address: str, side: Optional[str] = None) -> int:
    """
    Cancel all orders for a symbol, optionally filtered by side.
    
    Args:
        client: CCXT Hyperliquid client
        symbol: Trading symbol
        subaccount_address: Subaccount address
        side: Optional - 'long'/'short' to filter orders by side
        
    Returns:
        Number of orders canceled
    """
    # First fetch open orders using direct API
    open_orders = await get_open_orders(client, symbol, subaccount_address)
    
    if not open_orders:
        print(f"[INFO] No open orders to cancel for {symbol}")
        return 0
    
    # Filter by side if specified
    if side:
        order_side = 'buy' if side == 'long' else 'sell'
        filtered_orders = [
            order for order in open_orders 
            if order.get('side', '').lower() == order_side.lower()
        ]
    else:
        filtered_orders = open_orders
    
    if not filtered_orders:
        print(f"[INFO] No {side} orders to cancel for {symbol}")
        return 0
    
    print(f"[INFO] Canceling {len(filtered_orders)} orders for {symbol}")
    
    # Cancel each order
    canceled_count = 0
    for order in filtered_orders:
        try:
            order_id = order.get('oid') or order.get('id')
            if order_id:
                hl_symbol = await convert_symbol(symbol)
                await with_retry(
                    lambda: client.cancel_order(order_id, symbol=hl_symbol)
                )
                canceled_count += 1
        except Exception as e:
            print(f"[WARNING] Failed to cancel order {order_id}: {e}")
    
    print(f"[INFO] Canceled {canceled_count}/{len(filtered_orders)} orders")
    return canceled_count

async def set_stop_loss_take_profit(
    client,
    symbol: str,
    side: str,
    stop_loss: float,
    take_profit: Optional[float] = None,
    position_size: Optional[float] = None
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Set stop loss and take profit orders using trigger orders.
    CRITICAL: Use type='limit' with trigger parameters, NOT type='market'.
    
    Args:
        client: CCXT Hyperliquid client
        symbol: Trading symbol
        side: 'long' or 'short'
        stop_loss: Stop loss price
        take_profit: Optional take profit price
        position_size: Optional position size (if not provided, uses minimum)
        
    Returns:
        Tuple of (stop_loss_order, take_profit_order)
    """
    hl_symbol = await convert_symbol(symbol)
    
    # For stop loss: opposite side of position
    sl_side = 'sell' if side == 'long' else 'buy'
    
    # Use provided position size or calculate minimum
    if not position_size:
        # Use minimum order value of $10
        avg_price = (stop_loss + (take_profit or stop_loss)) / 2
        position_size = 10.0 / avg_price
    
    sl_order = None
    tp_order = None
    
    # Place stop loss
    if stop_loss:
        print(f"[INFO] Setting stop loss at {stop_loss} for {hl_symbol}")
        print(f"[DEBUG] SL params: side={sl_side}, amount={position_size}, price={stop_loss}")
        print(f"[DEBUG] SL trigger type: {'tp' if side == 'short' else 'sl'}")
        try:
            sl_order = await with_retry(
                lambda: client.create_order(
                    symbol=hl_symbol,
                    type='limit',  # CRITICAL: Use limit, not market
                    side=sl_side,
                    amount=position_size,
                    price=stop_loss,  # Limit price when triggered
                    params={
                        'triggerPrice': stop_loss,
                        'triggerType': 'tp' if side == 'short' else 'sl',  # tp for shorts, sl for longs
                        'reduceOnly': True
                    }
                )
            )
            print(f"[INFO] Stop loss order placed successfully: {sl_order.get('id', 'no ID')}")
        except Exception as e:
            print(f"[ERROR] Failed to set stop loss: {e}")
    
    # Place take profit
    if take_profit:
        print(f"[INFO] Setting take profit at {take_profit} for {hl_symbol}")
        print(f"[DEBUG] TP params: side={sl_side}, amount={position_size}, price={take_profit}")
        print(f"[DEBUG] TP trigger type: {'sl' if side == 'short' else 'tp'}")
        try:
            tp_order = await with_retry(
                lambda: client.create_order(
                    symbol=hl_symbol,
                    type='limit',  # CRITICAL: Use limit, not market
                    side=sl_side,  # Same side as stop loss (opposite of position)
                    amount=position_size,
                    price=take_profit,  # Limit price when triggered
                    params={
                        'triggerPrice': take_profit,
                        'triggerType': 'sl' if side == 'short' else 'tp',  # sl for shorts, tp for longs
                        'reduceOnly': True
                    }
                )
            )
            print(f"[INFO] Take profit order placed successfully: {tp_order.get('id', 'no ID')}")
        except Exception as e:
            print(f"[ERROR] Failed to set take profit: {e}")
    
    return sl_order, tp_order

async def close_position(client, symbol: str, subaccount_address: str) -> bool:
    """
    Close a position by canceling all orders and closing any open position.
    
    Args:
        client: CCXT Hyperliquid client
        symbol: Trading symbol
        subaccount_address: Subaccount address
        
    Returns:
        True if successful, False otherwise
    """
    hl_symbol = await convert_symbol(symbol)
    
    print(f"[INFO] Closing position for {hl_symbol}")
    
    # First, cancel all orders for this symbol
    await cancel_orders(client, symbol, subaccount_address)
    
    # Get position info to check if there's an open position
    position_info = await get_position_info(client, symbol, subaccount_address)
    
    if position_info and position_info.get('szi', 0) != 0:
        # There's an open position, close it
        position_size = abs(float(position_info['szi']))
        side = 'sell' if float(position_info['szi']) > 0 else 'buy'
        
        print(f"[INFO] Closing position: {position_size} {hl_symbol} with {side} order")
        
        try:
            # Get current market price for slippage calculation
            ticker = await client.fetch_ticker(hl_symbol)
            current_price = ticker['last']
            
            # Calculate slippage price (20% tolerance to ensure fill)
            # IMPORTANT: This is NOT a limit price - the order executes at market price
            # This parameter only prevents execution if price is worse than this threshold
            # Set high tolerance (20%) to ensure position closes even in volatile conditions
            if side == 'buy':
                # Buying to close short - allow up to 20% above market
                slippage_price = current_price * 1.20
            else:
                # Selling to close long - allow down to 20% below market
                slippage_price = current_price * 0.80
            
            await with_retry(
                lambda: client.create_market_order(
                    symbol=hl_symbol,
                    side=side,
                    amount=position_size,
                    price=slippage_price,  # Required for Hyperliquid market orders
                    params={'reduceOnly': True}
                )
            )
            print(f"[INFO] Position closed successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to close position: {e}")
            return False
    else:
        print(f"[INFO] No open position to close for {hl_symbol}")
        return True

async def get_position_info(client, symbol: str, subaccount_address: str) -> Optional[Dict]:  # noqa: ARG001
    """
    Get position information using direct API (CCXT's fetch_positions doesn't work for subaccounts).
    
    Args:
        client: CCXT Hyperliquid client (not used for this operation)
        symbol: Trading symbol
        subaccount_address: Subaccount address
        
    Returns:
        Position information dict or None
    """
    hl_symbol = await convert_symbol(symbol)
    base_symbol = hl_symbol.split('/')[0]
    
    print(f"[INFO] Fetching position info for {hl_symbol} on subaccount {subaccount_address}")
    
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        payload = {
            "type": "clearinghouseState",
            "user": subaccount_address
        }
        
        try:
            async with session.post(f"{HYPERLIQUID_API_URL}/info", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Find position for our symbol
                    if data and 'assetPositions' in data:
                        for position in data['assetPositions']:
                            if position.get('position', {}).get('coin', '').upper() == base_symbol.upper():
                                print(f"[INFO] Found position for {hl_symbol}")
                                return position.get('position')
                    
                    print(f"[INFO] No position found for {hl_symbol}")
                    return None
                else:
                    error_text = await response.text()
                    print(f"[ERROR] Failed to fetch position: {response.status} - {error_text}")
                    return None
        except Exception as e:
            print(f"[ERROR] Failed to fetch position info: {e}")
            return None