from hyperliquid_executor import (
    place_orders,
    cancel_orders,
    close_position,
    set_stop_loss_take_profit
)
from hyperliquid_clients import TRADER_TO_CLIENT
from config import RISK_PER_TRADE, HYPERLIQUID_SYMBOL_OVERRIDES
from utils import play_notification, record_event
import pprint

pp = pprint.PrettyPrinter(indent=2)

# Use symbol mapping from config
SYMBOL_MAPPING = HYPERLIQUID_SYMBOL_OVERRIDES

def convert_symbol(symbol: str) -> str:
    """
    Convert symbol from Discord format to Hyperliquid format.
    
    Args:
        symbol: Trading symbol in Discord format (e.g., "BTC/USDT")
    
    Returns:
        Symbol in Hyperliquid format (e.g., "BTC/USD")
    """
    # Check if symbol has a specific mapping
    if symbol in SYMBOL_MAPPING:
        return SYMBOL_MAPPING[symbol]
    
    # Standard conversion - replace USDT with USD
    if "/USDT" in symbol:
        return symbol.replace("/USDT", "/USD")
    
    # Handle non-slash format (e.g., "BTCUSDT" -> "BTC/USD")
    if "USDT" in symbol and "/" not in symbol:
        base = symbol.replace("USDT", "")
        return f"{base}/USD"
    
    # If already in USD format or other format, return as-is
    return symbol

async def handle_trade_update(trade_data, crud_type, trade_url, state, events_counter=None):
    """
    Handle trade updates from Discord signals.
    
    Args:
        trade_data: Parsed trade data from Discord
        crud_type: "CREATE" or "UPDATE"
        trade_url: URL of the Discord message
        state: Application state for tracking trades
    """
    # Extract trade details
    original_symbol = trade_data["symbol"]
    symbol = convert_symbol(original_symbol)
    side = trade_data["side"]
    entries = trade_data.get("entries")
    stop_loss = trade_data.get("stop_loss")
    take_profit = trade_data.get("take_profit")
    closed_price = trade_data.get("closed_price")
    trader = trade_data.get("trader")
    
    # Log symbol conversion if it occurred
    if original_symbol != symbol:
        print(f"[HYPERLIQUID] Converted symbol: {original_symbol} → {symbol}")
    
    # Get client for this trader
    client = TRADER_TO_CLIENT.get(trader)
    if client is None:
        print(f"[ERROR] No Hyperliquid client configured for trader: {trader}")
        return
    
    # Check if symbol is available on Hyperliquid
    try:
        # Attempt to fetch market info for the symbol to verify it exists
        markets = await client.fetch_markets()
        available_symbols = [market['symbol'] for market in markets]
        
        if symbol not in available_symbols:
            print(f"[WARN] Symbol {symbol} not available on Hyperliquid. Skipping trade.")
            print(f"[WARN] Original Discord symbol was: {original_symbol}")
            # Log but don't halt - gracefully skip this trade
            return
    except Exception as e:
        print(f"[WARN] Could not verify symbol availability for {symbol}: {e}")
        # Continue anyway - let the actual trade attempt fail if symbol is invalid
    
    # Handle CREATE operation (new trade)
    if crud_type == "CREATE":
        if not entries or not stop_loss:
            print(f"[WARN] Missing entry or stop loss for {symbol}, skipping order placement.")
            return
        
        print(f"[HYPERLIQUID:CREATE] Placing new trade for {symbol}")
        print(f"  Trader: {trader}")
        print(f"  Side: {side}")
        print(f"  Entries: {entries}")
        print(f"  Stop Loss: {stop_loss}")
        print(f"  Take Profit: {take_profit}")
        
        try:
            # Place limit orders at entry points
            await place_orders(client, symbol, side, entries, stop_loss, RISK_PER_TRADE)
            
            # Set stop loss and take profit if provided
            if take_profit or stop_loss:
                await set_stop_loss_take_profit(client, symbol, side, stop_loss, take_profit)
            
            print(f"[HYPERLIQUID:CREATE] Successfully created trade for {symbol}")
            
            # Record event and play notification
            if events_counter is not None:
                record_event(events_counter, "hyperliquid_new_trades")
            play_notification("Hero")  # Distinct sound for Hyperliquid new trades
            
        except Exception as e:
            print(f"[ERROR] Failed to create trade for {symbol}: {e}")
            play_notification("Basso")  # Error sound
            # Continue execution - don't halt on errors
    
    # Handle UPDATE operation (modify existing trade)
    elif crud_type == "UPDATE":
        print(f"[HYPERLIQUID:UPDATE] Checking updates for {symbol}")
        
        # Get previous trade state
        old_trade = state["active_trades"].get(trade_url)
        if not old_trade:
            print(f"[ERROR] No previous state found for {trade_url}. Cannot diff.")
            return
        
        # Calculate differences
        diffs = {
            key: (old_trade.get(key), trade_data.get(key))
            for key in ["entries", "stop_loss", "take_profit", "closed_price"]
            if old_trade.get(key) != trade_data.get(key)
        }
        
        if not diffs:
            print("[HYPERLIQUID:UPDATE] No meaningful changes detected.")
            return
        
        print("[HYPERLIQUID:UPDATE] Changes detected:")
        pp.pprint({"diffs": diffs})
        
        try:
            # Handle entry price changes
            if "entries" in diffs:
                print(f"[HYPERLIQUID] Entry prices changed for {symbol} → Replacing limit orders")
                # Cancel existing orders
                await cancel_orders(client, symbol, side)
                # Place new orders with updated entries
                await place_orders(client, symbol, side, entries, stop_loss, RISK_PER_TRADE)
            
            # Handle stop loss or take profit changes
            if "stop_loss" in diffs or "take_profit" in diffs:
                print(f"[HYPERLIQUID] Updating SL/TP for {symbol}")
                await set_stop_loss_take_profit(client, symbol, side, stop_loss, take_profit)
            
            # Handle position closure
            if "closed_price" in diffs and closed_price is not None:
                print(f"[HYPERLIQUID] Trade closed for {symbol} at {closed_price}")
                # Cancel any remaining orders
                await cancel_orders(client, symbol)
                # Close the position
                await close_position(client, symbol)
            
            print(f"[HYPERLIQUID:UPDATE] Successfully updated trade for {symbol}")
            
            # Record event and play notification for updates
            if events_counter is not None:
                record_event(events_counter, "hyperliquid_updates")
            play_notification("Pop")  # Distinct sound for Hyperliquid updates
            
        except Exception as e:
            print(f"[ERROR] Failed to update trade for {symbol}: {e}")
            play_notification("Basso")  # Error sound
            # Continue execution - don't halt on errors