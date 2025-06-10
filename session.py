import os
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from config import SESSION, ACTIVE_TRADES_CHANNEL, UPDATES_CHANNEL

async def save_storage(context):
    await context.storage_state(path=SESSION)
    print("[CHECKPOINT] Session storage saved.")


async def wait_for_channel_load(page, label, url, save_on_load=False, context=None):
    print(f"[CHECKPOINT] Opening tab for: {label}")
    await page.goto(url)

    print(f"[CHECKPOINT] Waiting for messages in: {label} (no timeout)...")
    await page.wait_for_selector("ol[aria-label^='Messages']", timeout=0)

    print(f"[CHECKPOINT] Channel fully loaded: {label}")
    if save_on_load and context:
        await save_storage(context)


async def initialize_session():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    print("[CHECKPOINT] Browser launched.")

    if os.path.exists(SESSION):
        context = await browser.new_context(storage_state=SESSION)
        print("[CHECKPOINT] Loaded session from storage.")
    else:
        context = await browser.new_context()
        print("[CHECKPOINT] No session found. Starting fresh.")

    active_trades_page = await context.new_page()
    await wait_for_channel_load(active_trades_page, "#active-trades", ACTIVE_TRADES_CHANNEL, save_on_load=True, context=context)

    updates_page = await context.new_page()
    await wait_for_channel_load(updates_page, "#trade-updates", UPDATES_CHANNEL)

    print("[CHECKPOINT] Both tabs loaded. Keeping browser open.")

    return context, browser, playwright
