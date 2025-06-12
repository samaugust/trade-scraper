from bs4 import BeautifulSoup
from state import save_state
from trade_parser import update_active_trades_from_urls
from utils import play_notification, record_event
import pprint

# Extract only new trade update links from messages after the last seen message ID
def extract_new_trade_updates(html: str, last_seen_id: str):
    soup = BeautifulSoup(html, "html.parser")
    all_messages = soup.find_all("li", class_="messageListItem__5126c")

    new_trade_urls = []
    msg_ids = []
    found_anchor = False

    print(f"[DEBUG] {len(all_messages)} update messages:")
    for li in all_messages:
        msg_id = li.get("id", "").split("-")[-1]

        if not found_anchor:
            if msg_id == last_seen_id:
                found_anchor = True
            continue  # skip until anchor found

        # Only process messages after the anchor
        link = li.select_one("a[href*='discord.com/channels']")
        print(f"[INFO] Link found in new updates: {link}")
        if link:
            href = link["href"]
            print(f"{href}")
            new_trade_urls.append(href)
            msg_ids.append(msg_id)

    return new_trade_urls, msg_ids

# Main coroutine to check for updates
async def check_trade_updates(state, context, events_counter):
    print("[CHECKPOINT] trade_updates_scraper.py entered")

    last_seen_id = state.get("last_trade_updates_message_id")

    # Use existing page context for #trade-updates
    updates_page = context.pages[1]  # Assumes tab #2 is #trade_updates

    if not updates_page:
        print("[ERROR] #trade-updates page not found in context.")
        return

    # Wait for content to load
    await updates_page.wait_for_selector("li")
    html = await updates_page.content()

    # Get all new updates since last seen ID
    if last_seen_id is None:
        # First run: just set the last seen ID to the most recent message
        soup = BeautifulSoup(html, "html.parser")
        all_messages = soup.select("li.messageListItem__5126c")

        if all_messages:
            latest_id = all_messages[-1].get("id", "").split("-")[-1]
            state["last_trade_updates_message_id"] = latest_id
            save_state(state)
            print(f"[INFO] First-time init of last_trade_updates_message_id to {latest_id}")
        else:
            print("[INFO] No messages found in #trade-updates")
        return

    trade_urls, msg_ids = extract_new_trade_updates(html, last_seen_id)
   
    if not trade_urls:
        print("[INFO] No new trade updates to process.")
        return

    actionable_updates = []
    actionable_updates_count = 0
    for trade_url in trade_urls:
        if trade_url in state.get("active_trades", {}):
            actionable_updates.append(trade_url)
            actionable_updates_count += 1
        else:
            record_event(events_counter, "non-actionable_updates")
            print(f"[INFO] Ignoring update for trade not in active_trades: {trade_url}")

    await update_active_trades_from_urls(actionable_updates, state, context, "UPDATER")

    # Update last seen ID to the latest processed one
    new_last_msg_id = msg_ids[-1]
    state["last_trade_updates_message_id"] = new_last_msg_id
    save_state(state)
    record_event(events_counter, "actionable_updates", actionable_updates_count)
    print(f"[ALERT] {actionable_updates_count} actionable update(s) processed. Updated last_trade_updates_message_id to {new_last_msg_id}")
    play_notification("Glass")

