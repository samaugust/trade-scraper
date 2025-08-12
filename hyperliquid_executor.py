import asyncio
import math
from typing import List, Optional, Dict, Any

async def with_retry(func, max_retries=3):
    """
    Retry wrapper with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[ERROR] Max retries reached: {e}")
                raise
            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            print(f"[RETRY] Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
            await asyncio.sleep(wait_time)

async def calculate_position_size(entry_price: float, stop_loss: float, risk_dollars: float) -> float:
    """
    Calculate position size based on risk parameters.
    """
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit == 0:
        raise ValueError("Stop loss equals entry price — can't calculate position size")
    qty = risk_dollars / risk_per_unit
    return round(qty, 3)

async def place_orders(client, symbol: str, side: str, entries: List[float], 
                      stop_loss: float, risk_per_trade: float) -> List[Dict]:
    """
    Place limit orders at multiple entry points.
    
    Args:
        client: HyperliquidAsync client instance
        symbol: Trading symbol (e.g., "BTC/USD")
        side: "buy" or "sell"
        entries: List of entry prices
        stop_loss: Stop loss price
        risk_per_trade: Total risk amount in dollars
    
    Returns:
        List of order results
    """
    results = []
    per_entry_risk = risk_per_trade / len(entries)
    
    for entry_price in entries:
        qty = await calculate_position_size(entry_price, stop_loss, per_entry_risk)
        
        async def place_single_order():
            return await client.create_limit_order(
                symbol=symbol,
                side=side.lower(),
                amount=qty,
                price=entry_price
            )
        
        try:
            order = await with_retry(place_single_order)
            print(f"[HYPERLIQUID] Placed limit order for {symbol}: {qty} @ {entry_price}")
            results.append(order)
        except Exception as e:
            print(f"[ERROR] Failed to place order for {symbol} at {entry_price}: {e}")
    
    return results

async def cancel_orders(client, symbol: str, side: Optional[str] = None) -> None:
    """
    Cancel existing orders for a symbol.
    
    Args:
        client: HyperliquidAsync client instance
        symbol: Trading symbol
        side: Optional - filter by side ("buy" or "sell")
    """
    try:
        async def fetch_and_cancel():
            # Fetch open orders
            orders = await client.fetch_open_orders(symbol)
            
            # Filter by side if specified
            if side:
                orders = [o for o in orders if o.get('side', '').lower() == side.lower()]
            
            # Cancel each order
            for order in orders:
                order_id = order.get('id')
                if order_id:
                    await client.cancel_order(order_id, symbol)
                    print(f"[HYPERLIQUID] Canceled order {order_id} for {symbol}")
            
            return len(orders)
        
        canceled_count = await with_retry(fetch_and_cancel)
        if canceled_count == 0:
            print(f"[HYPERLIQUID] No orders to cancel for {symbol}")
    except Exception as e:
        print(f"[ERROR] Failed to cancel orders for {symbol}: {e}")

async def set_stop_loss_take_profit(client, symbol: str, side: str, 
                                   stop_loss: Optional[float] = None, 
                                   take_profit: Optional[float] = None) -> None:
    """
    Set stop loss and take profit using limit orders.
    Hyperliquid doesn't have native SL/TP, so we use stop-limit orders.
    
    Args:
        client: HyperliquidAsync client instance
        symbol: Trading symbol
        side: Position side ("buy" or "sell")
        stop_loss: Stop loss price
        take_profit: Take profit price
    """
    try:
        # Get current position to determine size
        async def setup_stops():
            positions = await client.fetch_positions([symbol])
            
            if not positions:
                print(f"[HYPERLIQUID] No position found for {symbol}, skipping SL/TP")
                return
            
            position = positions[0]
            position_size = abs(float(position.get('contracts', 0)))
            
            if position_size == 0:
                print(f"[HYPERLIQUID] Zero position size for {symbol}, skipping SL/TP")
                return
            
            # Determine opposite side for closing orders
            close_side = "sell" if side.lower() == "buy" else "buy"
            
            results = []
            
            # Place stop loss as a stop-limit order
            if stop_loss:
                sl_order = await client.create_order(
                    symbol=symbol,
                    type='stop_limit',
                    side=close_side,
                    amount=position_size,
                    price=stop_loss,
                    stopPrice=stop_loss,
                    params={'reduceOnly': True}
                )
                print(f"[HYPERLIQUID] Set stop loss for {symbol} at {stop_loss}")
                results.append(sl_order)
            
            # Place take profit as a limit order
            if take_profit:
                tp_order = await client.create_limit_order(
                    symbol=symbol,
                    side=close_side,
                    amount=position_size,
                    price=take_profit,
                    params={'reduceOnly': True}
                )
                print(f"[HYPERLIQUID] Set take profit for {symbol} at {take_profit}")
                results.append(tp_order)
            
            return results
        
        await with_retry(setup_stops)
    except Exception as e:
        print(f"[ERROR] Failed to set SL/TP for {symbol}: {e}")

async def close_position(client, symbol: str) -> None:
    """
    Close an open position.
    
    Args:
        client: HyperliquidAsync client instance
        symbol: Trading symbol
    """
    try:
        async def close():
            positions = await client.fetch_positions([symbol])
            
            if not positions:
                print(f"[HYPERLIQUID] No position to close for {symbol}")
                return
            
            position = positions[0]
            position_size = float(position.get('contracts', 0))
            position_side = position.get('side', '').lower()
            
            if abs(position_size) == 0:
                print(f"[HYPERLIQUID] No open position to close for {symbol}")
                return
            
            # Determine close side (opposite of position)
            close_side = "sell" if position_side == "long" else "buy"
            
            # Market order to close
            result = await client.create_market_order(
                symbol=symbol,
                side=close_side,
                amount=abs(position_size),
                params={'reduceOnly': True}
            )
            
            print(f"[HYPERLIQUID] Closed position for {symbol}: {result}")
            return result
        
        await with_retry(close)
    except Exception as e:
        print(f"[ERROR] Failed to close position for {symbol}: {e}")

async def get_position_info(client, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get current position information.
    
    Args:
        client: HyperliquidAsync client instance
        symbol: Trading symbol
    
    Returns:
        Position dict or None if no position
    """
    try:
        positions = await client.fetch_positions([symbol])
        if positions:
            return positions[0]
        return None
    except Exception as e:
        print(f"[ERROR] Failed to get position info for {symbol}: {e}")
        return None