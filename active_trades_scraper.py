from bs4 import BeautifulSoup
from config import FOLLOWED_TRADERS
from state import save_state
from trade_parser import update_active_trades_from_urls
from utils import play_notification, record_event

EMOJI_MAP = {
    "🟢": "futures_long",
    "🔴": "futures_short",
    "🔵": "spot",
}

async def scrape_and_parse_active_trades(state: dict, context, events_counter) -> list[dict]:
    print("[CHECKPOINT] active_trades_scraper.py entered")
    active_trades_page = context.pages[0]
    container = await active_trades_page.query_selector("ol[aria-label^='Messages']")
    html = await container.inner_html()
    soup = BeautifulSoup(html, "html.parser")
    trade_blocks = soup.find_all("li", class_="messageListItem__5126c")

    # Collect all current trade URLs from the channel
    current_trade_urls = set()
    for block in trade_blocks:
        content_div = block.find("div", class_="messageContent_c19a55")
        if not content_div:
            continue
            
        # Get all trade URLs
        links = content_div.find_all("a", href=True)
        for link_tag in links:
            trade_url = link_tag["href"]
            current_trade_urls.add(trade_url)
    
    # Get previously seen URLs (ALL URLs, not just processed ones)
    previous_seen_urls = set(state.get("all_seen_urls", []))
    
    # Find new trade URLs (ones we haven't seen before in any capacity)
    new_trade_urls = current_trade_urls - previous_seen_urls
    
    # Update the list of all seen URLs (this handles removals too)
    state["all_seen_urls"] = list(current_trade_urls)
    save_state(state)
    
    # Check if there are any new trades
    if not new_trade_urls:
        print("[INFO] No new trades detected in #active-trades.")
        return

    print(f"[INFO] Found {len(new_trade_urls)} new trade URL(s) to evaluate")

    trade_urls = []
    for block in trade_blocks:
        content_div = block.find("div", class_="messageContent_c19a55")
        if not content_div:
            continue

        # Try to identify the trader name
        header = content_div.find(["strong", "em"])
        if not header:
            continue
        trader = header.get_text(strip=True)

        # Only continue if the trader is in the follow list
        if trader not in FOLLOWED_TRADERS:
            continue

        # Get all links (assume each one is a trade)
        links = content_div.find_all("a", href=True)
        for link_tag in links:
            trade_url = link_tag["href"]

            # Only process new URLs
            if trade_url not in new_trade_urls:
                continue  # Skip URLs we've already seen
            
            # Safety check: Skip if already in active_trades (prevents duplicates)
            if trade_url in state.get("active_trades", {}):
                print(f"[WARNING] URL marked as new but already in active_trades, skipping duplicate: {trade_url}")
                continue

            # Look for emoji containers near this link
            parent = link_tag.find_parent("li")
            if not parent:
                continue

            emojis = [img.get("aria-label", "") for img in parent.find_all("img", {"aria-label": True})]
            trade_type = None
            filled = False

            for e in emojis:
                if e == ":ChromaCheck2:":
                    filled = True
                elif e in EMOJI_MAP:
                    trade_type = EMOJI_MAP[e]

            if filled or trade_type is None or trade_type == "spot":
                continue  # filtered out

            trade_urls.append(trade_url)
    
    new_trades_count = len(trade_urls)
    if new_trades_count > 0:
        await update_active_trades_from_urls(trade_urls, state, context, "CREATE", events_counter)
        record_event(events_counter, "actionable_new_trades", new_trades_count)
        print(f"[ALERT] {new_trades_count} new trades added")
    else:
        record_event(events_counter, "non-actionable_new_trades")
        print("[INFO] Changes detected in #active-trades, but no actionable trades found")

    play_notification("Submarine")
