import asyncio
import signal
import os
from session import initialize_session
from state import load_state, save_state
from active_trades_scraper import scrape_and_parse_active_trades
from trade_updates_scraper import check_trade_updates
from config import POLL_INTERVAL_SECONDS

# Graceful shutdown flag
stop_signal = False
events_counter = { 
    "actionable_updates": 0, 
    "actionable_new_trades": 0, 
    "non-actionable_new_trades": 0, 
    "non-actionable_updates": 0,
    "hyperliquid_new_trades": 0,
    "hyperliquid_updates": 0
}
polling_loop_counter = 1

def handle_shutdown(signum, frame):
    global stop_signal
    print("[INFO] Received shutdown signal.")
    stop_signal = True

async def main():
  global stop_signal
  global polling_loop_counter

  # Setup signal handlers
  signal.signal(signal.SIGINT, handle_shutdown)
  signal.signal(signal.SIGTERM, handle_shutdown)

  os.makedirs("storage", exist_ok=True)
  state = load_state()
  context, browser, playwright = await initialize_session()

  print("[INFO] Starting polling loop...")
  try:
    while not stop_signal:

      print(f"[INFO] POLLING LOOP COUNT: {polling_loop_counter}")

      await scrape_and_parse_active_trades(state, context, events_counter)

      await check_trade_updates(state, context, events_counter)

      polling_loop_counter += 1

      await asyncio.sleep(POLL_INTERVAL_SECONDS)

  finally:
    print("[INFO] Shutting down...")
    save_state(state)
    await browser.close()
    await playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())