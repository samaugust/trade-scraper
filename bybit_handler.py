from order_executor import (
    cancel_existing_limit_orders,
    place_limit_order,
    close_position,
    set_trading_stop
)
from bybit_clients import TRADER_TO_CLIENT
from config import RISK_PER_TRADE
import pprint

pp = pprint.PrettyPrinter(indent=2)

async def handle_trade_update(trade_data, crud_type, trade_url, state):
    symbol = trade_data["symbol"]
    side = trade_data["side"]
    entries = trade_data.get("entries")
    stop_loss = trade_data.get("stop_loss")
    take_profit = trade_data.get("take_profit")
    closed_price = trade_data.get("closed_price")
    trader = trade_data.get("trader")

    client = TRADER_TO_CLIENT.get(trader)
    if client is None:
        print(f"[ERROR] No Bybit client configured for trader: {trader}")
        return

    if crud_type == "CREATE":
        if not entries or not stop_loss:
            print(f"[WARN] Missing entry or stop loss for {symbol}, skipping order placement.")
            return
        print(f"[BYBIT:CREATE] Placing new trade for {symbol}")
        await place_limit_order(client, symbol, side, entries, stop_loss, RISK_PER_TRADE)
        if take_profit or stop_loss:
            await set_trading_stop(client, symbol, stop_loss, take_profit)

    elif crud_type == "UPDATE":
        print(f"[BYBIT:UPDATE] Checking updates for {symbol}")
        old_trade = state["active_trades"].get(trade_url)
        if not old_trade:
            print(f"[ERROR] No previous state found for {trade_url}. Cannot diff.")
            return

        diffs = {
            key: (old_trade.get(key), trade_data.get(key))
            for key in ["entries", "stop_loss", "take_profit", "closed_price"]
            if old_trade.get(key) != trade_data.get(key)
        }

        if not diffs:
            print("[BYBIT:UPDATE] No meaningful changes detected.")
            return

        pp.pprint({ "diffs": diffs })

        if "entries" in diffs:
            print(f"[BYBIT] Entry prices changed for {symbol} → Replacing limit orders")
            await cancel_existing_limit_orders(client, symbol, side)
            await place_limit_order(client, symbol, side, entries, stop_loss, RISK_PER_TRADE)

        if "stop_loss" in diffs or "take_profit" in diffs:
            print(f"[BYBIT] Updating SL/TP for {symbol}")
            await set_trading_stop(client, symbol, stop_loss, take_profit)

        if "closed_price" in diffs:
            print(f"[BYBIT] Closed price updated for {symbol}, checking position")
            await close_position(client, symbol, side)
