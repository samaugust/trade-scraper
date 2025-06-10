from bs4 import BeautifulSoup
from config import FOLLOWED_TRADERS
from state import save_state
from trade_parser import hydrate_active_trades_from_urls
import hashlib

EMOJI_MAP = {
    "🟢": "futures_long",
    "🔴": "futures_short",
    "🔵": "spot",
}

def compute_hash_from_html(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()

async def scrape_and_parse_active_trades(state: dict, context) -> list[dict]:
    active_trades_page = context.pages[0]
    container = await active_trades_page.query_selector("ol[aria-label^='Messages']")
    html = await container.inner_html()

    new_hash = compute_hash_from_html(html)
    last_hash = state.get("last_active_trades_hash")

    if new_hash == last_hash:
        print("[INFO] No change detected in #active-trades.")
        return

    state["last_active_trades_hash"] = new_hash
    save_state(state)

    soup = BeautifulSoup(html, "html.parser")
    trade_urls = []

    trade_blocks = soup.find_all("li", class_="messageListItem__5126c")

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

            if trade_url in state["active_trades"]:
                continue  # already tracked

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
    if len(trade_urls) > 0:
        await hydrate_active_trades_from_urls(trade_urls, state, context)
