import os
from dotenv import load_dotenv
from pybit.unified_trading import AsyncHTTP

load_dotenv()

TRADER_TO_CLIENT = {
    "Perdu": AsyncHTTP(
        api_key=os.getenv("BYBIT_API_KEY"),
        api_secret=os.getenv("BYBIT_API_SECRET")
    ),
    "$Silla": AsyncHTTP(
        api_key=os.getenv("BYBIT_API_KEY_2"),
        api_secret=os.getenv("BYBIT_API_SECRET_2")
    ),
}
