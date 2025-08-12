import re
from bs4 import BeautifulSoup
from state import save_state
from hyperliquid_handler import handle_trade_update

def extract_trade_fields_from_text(text: str) -> dict:
    trader_match = re.search(r"(.*?)APP", text)
    symbol_match = re.search(r"([A-Z]{2,10}/USDT)", text, re.IGNORECASE)
    stop_match = re.search(r"(stop|sl)[/ ]?(loss)?[:\s]+[$]?\s*([\d.]+)", text, re.IGNORECASE)
    tp_match = re.search(r"(take profit|tp)[:\s]+[$]?\s*([\d.]+)", text, re.IGNORECASE)
    close_match = re.search(r"closed\s*(price)?[:\s]+[$]?\s*([\d.]+)", text)
    entry_matches = re.findall(r"entry\s*\d*[:\s]+\$?([\d.]+)", text, re.IGNORECASE)

    trader = trader_match.group(1).strip() if trader_match else "Unknown"
    direction = "long" if "long" in text.lower() else "short" if "short" in text.lower() else None
    symbol = symbol_match.group(1).upper() if symbol_match else None
    stop = float(stop_match.group(3)) if stop_match else None
    tp = float(tp_match.group(2)) if tp_match else None
    closed = float(close_match.group(2)) if close_match else None
    entries = list(map(float, entry_matches)) if entry_matches else []
    avg_entry = sum(entries) / len(entries) if entries else None
    multi_entry = len(entries) > 1

    if not all([symbol, stop, tp, direction, avg_entry]):
        print("[DEBUG] Failed to parse trade content:")
        print(text)
        return None

    return {
        "trader": trader,
        "symbol": symbol,
        "direction": direction,
        "entries": entries,
        "avg_entry": avg_entry,
        "stop loss": stop,
        "take profit": tp,
        "closed price": closed,
        "multi_entry": multi_entry
    }

async def update_active_trades_from_urls(urls: list[str], state, context, crud_type, events_counter=None):
    active_trades = state.get("active_trades", {})

    for url in urls:
        print(f"[{crud_type}] Visiting trade URL: {url}")
        page = await context.new_page()
        await page.goto(url)

        try:
            # ✅ Extract the message ID from the URL
            message_id = url.split("/")[-1]

            # ✅ Wait for and select the exact <li> element for this message
            selector = f"li[id*='{message_id}']"
            await page.wait_for_selector(selector, timeout=15000)
            message_element = await page.query_selector(selector)
            html = await message_element.inner_html()

            trade_data = parse_trade_html(html)

            if trade_data:
                await handle_trade_update(trade_data, crud_type, url, state, events_counter)
                active_trades[url] = trade_data
                print(f"[{crud_type}] Trade processed: {url}")
            else:
                print(f"[{crud_type}] Could not parse trade content at: {url}")
        except Exception as e:
            print(f"[{crud_type}] Error while processing {url}: {e}")
        finally:
            await page.close()

    state["active_trades"] = active_trades
    save_state(state)
    print(f"[{crud_type}] All trades processed. State saved.")


def parse_trade_html(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    
    trade = extract_trade_fields_from_text(text)

    return trade

# async def reconcile_trade_from_url(trade_url: str, html, state: dict) -> None:
#     soup = BeautifulSoup(html, "html.parser")
#     trade_block = None

#     # Look for the message block that actually contains the trade (using the URL's ID)
#     trade_id = trade_url.split("/")[-1]
#     for li in soup.select("li.messageListItem__5126c"):
#         if li.get("id", "").endswith(trade_id):
#             trade_block = li
#             break

#     if not trade_block:
#         print(f"[WARNING] Could not locate trade block for {trade_url}")
#         return

#     text = trade_block.get_text(separator=" ").lower()

#     trade = extract_trade_fields_from_text(text)

#     state["active_trades"][trade_url] = trade
#     print(f"[INFO] Updated trade in state: {trade_url}")
