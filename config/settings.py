import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "3"))
PREMIUM_LIMIT = int(os.getenv("PREMIUM_LIMIT", "20"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
