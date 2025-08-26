# state.py
import json
import os
from config import STATE


def default_state():
    return {
        "last_trade_updates_message_id": None,  # Last message ID from #trade-updates channel
        "active_trades": {},  # {url: {symbol, trader, ...}} - tracks all PROCESSED trades by URL
        "all_seen_urls": []  # All URLs currently visible in #active-trades (updated each poll)
    }

def load_state():
    if not os.path.exists(STATE):
        return default_state()
    with open(STATE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
