import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "3"))
PREMIUM_LIMIT = int(os.getenv("PREMIUM_LIMIT", "20"))
DB_PATH = os.getenv("DB_PATH", "data/prices.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
STARS_PRICE = int(os.getenv("STARS_PRICE", "299"))
PROXY_URL = os.getenv("PROXY_URL", "")
OZON_COOKIES = os.getenv("OZON_COOKIES", "")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
