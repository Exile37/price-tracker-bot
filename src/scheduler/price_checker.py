import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from src.parsers.universal_parser import parse_product
from src.database.db import get_active_products, update_price, get_user_products, get_all_users, get_user_settings, add_savings
from config.settings import BOT_TOKEN

logger = logging.getLogger(__name__)

daily_cache: dict[int, list[dict]] = {}


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
            user_id = product["user_id"]

            await update_price(product["id"], new_price)

            if new_price < old_price:
                diff = old_price - new_price
                pct = (diff / old_price) * 100

                settings = await get_user_settings(user_id)
                min_drop = settings[0] if settings and settings[0] else 5

                if user_id not in daily_cache:
                    daily_cache[user_id] = []
                daily_cache[user_id].append({
                    "title": product["title"][:50],
                    "old": old_price,
                    "new": new_price,
                    "pct": pct,
                    "currency": currency,
                    "target": target_price,
                })

                await add_savings(user_id, diff)

                if pct < min_drop:
                    continue

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
                    await bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Send message failed for {user_id}: {e}")

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
                    await bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Send message failed for {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error checking product #{product['id']}: {e}")

    await bot.session.close()


async def send_daily_summary():
    global daily_cache
    bot = Bot(token=BOT_TOKEN)

    for user_id, changes in daily_cache.items():
        if not changes:
            continue

        drops = [c for c in changes if c["new"] < c["old"]]
        rises = [c for c in changes if c["new"] > c["old"]]

        if not drops and not rises:
            continue

        lines = [f"📊 <b>Сводка за день</b>\n"]
        lines.append(f"📅 {datetime.now().strftime('%d.%m.%Y')}\n")

        if drops:
            lines.append(f"📉 <b>Снижения ({len(drops)}):</b>")
            for d in drops[:10]:
                lines.append(f"  • {d['title']} — {d['old']}{d['currency']} → <b>{d['new']}{d['currency']}</b> (−{d['pct']:.1f}%)")
            lines.append("")

        if rises:
            lines.append(f"📈 <b>Повышения ({len(rises)}):</b>")
            for r in rises[:10]:
                lines.append(f"  • {r['title']} — {r['old']}{r['currency']} → {r['new']}{r['currency']} (+{r['pct']:.1f}%)")

        try:
            await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Daily summary failed for {user_id}: {e}")

    daily_cache = {}
    await bot.session.close()


async def scheduler_loop(interval_minutes: int = 30):
    last_summary = datetime.now()

    while True:
        logger.info("Starting price check cycle...")
        await check_prices()
        logger.info(f"Price check complete. Next check in {interval_minutes} minutes.")

        now = datetime.now()
        if now.day != last_summary.day and now.hour >= 9:
            await send_daily_summary()
            last_summary = now

        await asyncio.sleep(interval_minutes * 60)
