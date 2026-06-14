import asyncio
import logging
from aiogram import Bot
from src.parsers.universal_parser import parse_product
from src.database.db import get_active_products, update_price
from config.settings import BOT_TOKEN

logger = logging.getLogger(__name__)


async def check_prices():
    bot = Bot(token=BOT_TOKEN)
    products = await get_active_products()

    for product in products:
        try:
            result = await parse_product(product["url"])
            if "error" in result:
                logger.warning(f"Parse error for #{product['id']}: {result['error']}")
                continue

            new_price = result["price"]
            old_price = product["current_price"]
            target_price = product["target_price"]
            currency = product["currency"]

            await update_price(product["id"], new_price)

            if new_price < old_price:
                diff = old_price - new_price
                pct = (diff / old_price) * 100
                msg = (
                    f"📉 <b>Цена упала!</b>\n\n"
                    f"📦 {product['title'][:80]}\n"
                    f"💰 Было: {old_price}{currency}\n"
                    f"💰 Стало: <b>{new_price}{currency}</b>\n"
                    f"📉 −{diff:.2f}{currency} (−{pct:.1f}%)"
                )
                if target_price and new_price <= target_price:
                    msg += f"\n\n🎯 <b>Достигнута целевая цена!</b>"

                try:
                    await bot.send_message(
                        chat_id=product["user_id"],
                        text=msg,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Send message failed for user {product['user_id']}: {e}")

            elif new_price > old_price:
                diff = new_price - old_price
                pct = (diff / old_price) * 100
                msg = (
                    f"📈 <b>Цена выросла</b>\n\n"
                    f"📦 {product['title'][:80]}\n"
                    f"💰 Было: {old_price}{currency}\n"
                    f"💰 Стало: {new_price}{currency}\n"
                    f"📈 +{diff:.2f}{currency} (+{pct:.1f}%)"
                )
                try:
                    await bot.send_message(
                        chat_id=product["user_id"],
                        text=msg,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Send message failed for user {product['user_id']}: {e}")

        except Exception as e:
            logger.error(f"Error checking product #{product['id']}: {e}")

    await bot.session.close()


async def scheduler_loop(interval_minutes: int = 30):
    while True:
        logger.info("Starting price check cycle...")
        await check_prices()
        logger.info(f"Price check complete. Next check in {interval_minutes} minutes.")
        await asyncio.sleep(interval_minutes * 60)
