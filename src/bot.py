import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import BOT_TOKEN, CHECK_INTERVAL_MINUTES
from src.database.db import init_db
from src.handlers.user_handlers import router
from src.scheduler.price_checker import scheduler_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    asyncio.create_task(scheduler_loop(CHECK_INTERVAL_MINUTES))
    logger.info(f"Scheduler started (interval: {CHECK_INTERVAL_MINUTES} min)")

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
