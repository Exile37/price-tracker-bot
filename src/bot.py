import asyncio
import logging
import threading
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import BOT_TOKEN, CHECK_INTERVAL_MINUTES
from src.database.db import init_db
from src.handlers.user_handlers import router
from src.scheduler.price_checker import scheduler_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def start_web_server():
    import uvicorn
    from src.web.app import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


async def main():
    await init_db()
    logger.info("Database initialized")

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    logger.info("Web server started on port 8080")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    asyncio.create_task(scheduler_loop(CHECK_INTERVAL_MINUTES))
    logger.info(f"Scheduler started (interval: {CHECK_INTERVAL_MINUTES} min)")

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
