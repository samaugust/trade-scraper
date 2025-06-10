from bs4 import BeautifulSoup
from state import save_state
from trade_parser import reconcile_trade_from_url

# Extract only new trade update links from messages after the last seen message ID
def extract_new_trade_update_links(html: str, last_seen_id: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    all_messages = soup.find_all("li")

    new_trade_urls = []
    found_anchor = False

    for li in all_messages:
        msg_id = li.get("id", "").split("-")[-1]

        if not found_anchor:
            if msg_id == last_seen_id:
                found_anchor = True
            continue  # skip until anchor found

        # Only process messages after the anchor
        link = li.find("a", href=True)
        if link:
            href = link["href"]
            new_trade_urls.append((msg_id, href))

    return new_trade_urls

# Main coroutine to check for updates
async def check_trade_updates(state, context):
    print("[CHECKPOINT] check_trade_updates() entered")

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

    new_updates = extract_new_trade_update_links(html, last_seen_id)

    if not new_updates:
        print("[INFO] No new trade updates to process.")
        return

    for msg_id, trade_url in new_updates:
        if trade_url in state.get("active_trades", {}):
            await reconcile_trade_from_url(trade_url, html, state)
        else:
            print(f"[INFO] Ignoring update for trade not in active_trades: {trade_url}")

    # Update last seen ID to the latest processed one
    state["last_trade_updates_message_id"] = new_updates[-1][0]
    save_state(state)
    print(f"[INFO] Updated last_trade_updates_message_id to {new_updates[-1][0]}")
