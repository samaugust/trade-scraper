import math

def calculate_position_size(entry_price, stop_loss, risk_dollars):
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit == 0:
        raise ValueError("Stop loss equals entry price — can't calculate position size")
    qty = risk_dollars / risk_per_unit
    return round(qty, 3)

async def cancel_existing_limit_orders(client, symbol, side):
    try:
        orders = await client.get_open_orders(category="linear", symbol=symbol)
        for order in orders["result"]["list"]:
            if order["orderType"] == "Limit" and not order["reduceOnly"] and order["side"] == side.upper():
                await client.cancel_order(category="linear", symbol=symbol, orderId=order["orderId"])
                print(f"[BYBIT] Canceled old limit order {order['orderId']} at {order['price']}")
    except Exception as e:
        print(f"[ERROR] Failed to cancel existing limit orders for {symbol}: {e}")

async def place_limit_order(client, symbol, side, entries, stop_loss, risk_per_trade):
    results = []
    per_entry_risk = risk_per_trade / len(entries)
    for entry_price in entries:
        qty = calculate_position_size(entry_price, stop_loss, per_entry_risk)
        try:
            order = await client.place_order(
                category="linear",
                symbol=symbol,
                side=side.upper(),
                order_type="Limit",
                qty=qty,
                price=entry_price,
                time_in_force="GoodTillCancel",
                reduce_only=False,
                is_leverage=True
            )
            print(f"[BYBIT] Placed limit order: {order}")
            results.append(order)
        except Exception as e:
            print(f"[ERROR] Failed to place limit order for {symbol} at {entry_price}: {e}")
    return results

async def set_trading_stop(client, symbol, stop_loss=None, take_profit=None):
    try:
        result = await client.set_trading_stop(
            category="linear",
            symbol=symbol,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_trigger_by="MarkPrice",
            tp_trigger_by="MarkPrice"
        )
        print(f"[BYBIT] Updated SL/TP for {symbol}: {result}")
    except Exception as e:
        print(f"[ERROR] Failed to update SL/TP for {symbol}: {e}")

async def close_position(client, symbol, side):
    try:
        response = await client.get_positions(category="linear", symbol=symbol)
        position = response["result"]["list"][0]
        size = float(position["size"])
        if size > 0:
            opposite_side = "BUY" if side.strip().upper() == "SELL" else "SELL"
            result = await client.place_order(
                category="linear",
                symbol=symbol,
                side=opposite_side,
                order_type="Market",
                qty=size,
                reduce_only=True
            )
            print(f"[BYBIT] Closed position: {result}")
        else:
            print(f"[BYBIT] No open position to close for {symbol}")
    except Exception as e:
        print(f"[ERROR] Failed to close position on {symbol}: {e}")
