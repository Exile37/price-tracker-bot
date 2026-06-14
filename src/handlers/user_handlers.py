import re
import uuid
import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    LabeledPrice, PreCheckoutQuery, SuccessfulPayment,
    BufferedInputFile
)
from aiogram.filters import CommandStart, Command

from src.parsers.universal_parser import parse_product
from src.database.db import (
    add_user, get_user, get_user_product_count, add_product,
    get_user_products, deactivate_product, get_price_history,
    add_referral, get_referral_count, set_premium, use_premium_key,
    set_custom_limit, get_all_users, get_user_count, get_premium_user_count,
    get_total_products
)
from src.chart import generate_price_chart
from config.settings import FREE_LIMIT, PREMIUM_LIMIT, ADMIN_ID, STARS_PRICE

router = Router()
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')

pending_urls: dict[str, dict] = {}


def _is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))


def _save_pending(url: str, data: dict) -> str:
    short_id = uuid.uuid4().hex[:8]
    pending_urls[short_id] = {"url": url, **data}
    return short_id


def _get_pending(short_id: str) -> dict | None:
    return pending_urls.pop(short_id, None)


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои товары", callback_data="list")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ])


def _reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои товары"), KeyboardButton(text="📊 График")],
            [KeyboardButton(text="⭐ Премиум"), KeyboardButton(text="🔗 Реферал")],
        ],
        resize_keyboard=True,
    )


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])


async def _notify_admin(text: str, bot: Bot):
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Admin notify failed: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    is_new = await add_user(user_id, message.from_user.username or "")

    if is_new and ADMIN_ID and user_id != ADMIN_ID:
        username = message.from_user.username or "нет"
        first_name = message.from_user.first_name or ""
        await _notify_admin(
            f"👤 <b>Новый пользователь!</b>\n\n"
            f"ID: <code>{user_id}</code>\n"
            f"Username: @{username}\n"
            f"Имя: {first_name}",
            message.bot
        )

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id != user_id:
                success = await add_referral(referrer_id, user_id)
                if success:
                    await message.answer("🎁 Ты был приглашён! +1 товар к лимиту.")
        except Exception:
            pass

    await message.answer(
        "🛒 <b>Price Tracker</b>\n\n"
        "Отправь ссылку на товар с Wildberries,\n"
        "а я буду следить за ценой и сообщу, когда она упадёт!\n\n"
        "Просто вставь ссылку →",
        parse_mode="HTML",
        reply_markup=_reply_kb()
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback_query: CallbackQuery):
    try:
        await callback_query.message.edit_text(
            "🛒 <b>Price Tracker</b>\n\n"
            "Вставь ссылку на товар с Wildberries →",
            parse_mode="HTML",
            reply_markup=_main_menu_kb()
        )
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback_query: CallbackQuery):
    try:
        await callback_query.message.edit_text(
            "📌 <b>Как пользоваться:</b>\n\n"
            "1. Скопируй ссылку на товар с Wildberries\n"
            "2. Отправь её мне\n"
            "3. Нажми «Следить»\n"
            "4. Я буду проверять цену каждые 30 мин\n"
            "5. Если цена упадёт — сразу сообщу!\n\n"
            "<b>Команды:</b>\n"
            "/start — главное меню",
            parse_mode="HTML",
            reply_markup=_back_kb()
        )
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data == "list")
async def cb_list(callback_query: CallbackQuery):
    products = await get_user_products(callback_query.from_user.id)
    if not products:
        try:
            await callback_query.message.edit_text(
                "У тебя пока нет отслеживаемых товаров.\n\n"
                "Отправь ссылку на товар с Wildberries.",
                reply_markup=_back_kb()
            )
        except Exception:
            pass
        await callback_query.answer()
        return

    buttons = []
    for p in products:
        price_str = f"{p['current_price']}{p['currency']}"
        text = f"{p['title'][:35]} — {price_str}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"item:{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])

    try:
        await callback_query.message.edit_text(
            "📋 <b>Мои товары:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data.startswith("item:"))
async def cb_item(callback_query: CallbackQuery):
    product_id = int(callback_query.data.split(":")[1])
    products = await get_user_products(callback_query.from_user.id)
    product = None
    for p in products:
        if p["id"] == product_id:
            product = p
            break

    if not product:
        await callback_query.message.edit_text("Товар не найден.")
        await callback_query.answer()
        return

    text = (
        f"📦 <b>{product['title'][:80]}</b>\n\n"
        f"💰 {product['current_price']}{product['currency']}\n"
    )
    if product["target_price"]:
        text += f"🎯 Цель: {product['target_price']}{product['currency']}\n"
    text += f"\n🔗 {product['url'][:60]}..."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{product_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="list")],
    ])

    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback_query: CallbackQuery):
    product_id = int(callback_query.data.split(":")[1])
    await deactivate_product(product_id)
    try:
        await callback_query.message.edit_text(
            "🗑 Товар удалён.",
            reply_markup=_back_kb()
        )
    except Exception:
        await callback_query.message.answer(
            "🗑 Товар удалён.",
            reply_markup=_back_kb()
        )
    await callback_query.answer()


@router.message(F.text == "📋 Мои товары")
async def btn_my_products(message: Message):
    products = await get_user_products(message.from_user.id)
    if not products:
        await message.answer(
            "У тебя пока нет отслеживаемых товаров.\n\nОтправь ссылку на товар с Wildberries.",
            reply_markup=_reply_kb()
        )
        return

    buttons = []
    for p in products:
        price_str = f"{p['current_price']}{p['currency']}"
        text = f"{p['title'][:35]} — {price_str}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"item:{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])

    await message.answer(
        "📋 <b>Мои товары:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: Message):
    await message.answer(
        "📌 <b>Как пользоваться:</b>\n\n"
        "1. Скопируй ссылку на товар с Wildberries\n"
        "2. Отправь её мне\n"
        "3. Нажми «Следить»\n"
        "4. Я буду проверять цену каждые 30 мин\n"
        "5. Если цена упадёт — сразу сообщу!",
        parse_mode="HTML",
        reply_markup=_reply_kb()
    )


@router.message(F.text == "📊 График")
async def btn_chart(message: Message):
    products = await get_user_products(message.from_user.id)
    if not products:
        await message.answer("Нет товаров. Сначала добавь товар.", reply_markup=_reply_kb())
        return
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"📊 {p['title'][:35]}",
            callback_data=f"chart:{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    await message.answer("Выбери товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("chart:"))
async def cb_chart(callback_query: CallbackQuery):
    product_id = int(callback_query.data.split(":")[1])
    history = await get_price_history(product_id, limit=60)

    if len(history) < 2:
        await callback_query.message.answer(
            "Недостаточно данных для графика. Подожди несколько проверок.",
            reply_markup=_reply_kb()
        )
        await callback_query.answer()
        return

    chart_buf = generate_price_chart([dict(h) for h in history])
    if not chart_buf:
        await callback_query.message.answer("Не удалось построить график.", reply_markup=_reply_kb())
        await callback_query.answer()
        return

    file = BufferedInputFile(chart_buf.getvalue(), filename="chart.png")
    await callback_query.message.answer_photo(
        photo=file,
        caption=f"📊 График цены",
        reply_markup=_reply_kb()
    )
    await callback_query.answer()


@router.message(F.text == "⭐ Премиум")
async def btn_premium(message: Message):
    user = await get_user(message.from_user.id)
    is_premium = user and user["is_premium"]
    if is_premium:
        await message.answer("⭐ У тебя уже премиум!", reply_markup=_reply_kb())
        return
    await message.answer(
        f"⭐ <b>Премиум</b>\n\n"
        f"• 20 товаров вместо 3\n"
        f"• Графики цены\n"
        f"• Приоритетная проверка\n\n"
        f"💰 <b>{STARS_PRICE} ⭐/мес</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {STARS_PRICE} ⭐", callback_data="pay_premium")],
            [InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="activate_key")],
        ])
    )


@router.callback_query(F.data == "pay_premium")
async def cb_pay_premium(callback_query: CallbackQuery):
    await callback_query.message.answer_invoice(
        title="⭐ Премиум Price Tracker",
        description="20 товаров вместо 3, графики, приоритетная проверка",
        payload="premium_subscription",
        currency="XTR",
        prices=[LabeledPrice(label="Премиум", amount=STARS_PRICE)],
    )
    await callback_query.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery):
    if pre_checkout.invoice_payload == "premium_subscription":
        await pre_checkout.answer(ok=True)
    else:
        await pre_checkout.answer(ok=False, error_message="Неизвестный платёж")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payment: SuccessfulPayment = message.successful_payment
    if payment.invoice_payload == "premium_subscription":
        user_id = message.from_user.id
        await set_premium(user_id, True)
        await message.answer(
            "⭐ <b>Премиум активирован!</b>\n\n"
            "Теперь у тебя 20 товаров и графики!",
            parse_mode="HTML",
            reply_markup=_reply_kb()
        )
        if ADMIN_ID:
            username = message.from_user.username or "нет"
            await _notify_admin(
                f"💰 <b>Новая оплата!</b>\n\n"
                f"Пользователь: @{username}\n"
                f"ID: <code>{user_id}</code>\n"
                f"Сумма: {payment.total_amount} ⭐",
                message.bot
            )


@router.callback_query(F.data == "activate_key")
async def cb_activate_key(callback_query: CallbackQuery):
    await callback_query.message.answer(
        "🔑 Отправь ключ активации (например: <code>Premium-XXXX-XXXX</code>):",
        parse_mode="HTML"
    )
    await callback_query.answer()


@router.message(F.text.startswith("Premium-"))
async def cmd_activate(message: Message):
    key = message.text.strip()
    user_id = message.from_user.id
    success = await use_premium_key(key, user_id)
    if success:
        await set_premium(user_id, True)
        await message.answer(
            "⭐ <b>Премиум активирован!</b>\n\nТеперь у тебя 20 товаров и графики!",
            parse_mode="HTML",
            reply_markup=_reply_kb()
        )
    else:
        await message.answer("❌ Неверный или уже использованный ключ.", reply_markup=_reply_kb())


@router.message(F.text == "🔗 Реферал")
async def btn_referral(message: Message):
    user_id = message.from_user.id
    count = await get_referral_count(user_id)
    link = f"https://t.me/aut0teka_bot?start=ref_{user_id}"
    await message.answer(
        f"🔗 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей — получай +1 товар к лимиту!\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено: <b>{count}</b> чел.",
        parse_mode="HTML",
        reply_markup=_reply_kb()
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users = await get_user_count()
    premium_users = await get_premium_user_count()
    total_products = await get_total_products()
    await message.answer(
        f"🔧 <b>Админ-панель</b>\n\n"
        f"👤 Пользователей: <b>{total_users}</b>\n"
        f"⭐ Премиум: <b>{premium_users}</b>\n"
        f"📦 Товаров: <b>{total_products}</b>\n\n"
        f"<b>Команды:</b>\n"
        f"/admin_users — список пользователей\n"
        f"/admin_setlimit <code>user_id кол-во</code> — задать лимит\n"
        f"/admin_addkey — создать премиум-ключ\n"
        f"/admin_broadcast <code>текст</code> — рассылка всем",
        parse_mode="HTML"
    )


@router.message(Command("admin_users"))
async def cmd_admin_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    if not users:
        await message.answer("Нет пользователей.")
        return
    lines = []
    for u in users[:30]:
        status = "⭐" if u["is_premium"] else "👤"
        custom = f" (лимит: {u['custom_limit']})" if u["custom_limit"] else ""
        username = f"@{u['username']}" if u["username"] else "нет"
        lines.append(f"{status} <code>{u['user_id']}</code> {username}{custom}")
    text = f"👥 <b>Пользователи ({len(users)}):</b>\n\n" + "\n".join(lines)
    if len(users) > 30:
        text += f"\n\n...и ещё {len(users) - 30}"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("admin_setlimit"))
async def cmd_admin_setlimit(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: /admin_setlimit <code>user_id кол-во</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
        limit = int(parts[2])
    except ValueError:
        await message.answer("Неверный формат.", parse_mode="HTML")
        return
    user = await get_user(target_id)
    if not user:
        await message.answer("Пользователь не найден.", parse_mode="HTML")
        return
    await set_custom_limit(target_id, limit)
    await message.answer(
        f"✅ Лимит для <code>{target_id}</code>: <b>{limit}</b> товаров",
        parse_mode="HTML"
    )


@router.message(Command("admin_broadcast"))
async def cmd_admin_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/admin_broadcast", "", 1).strip()
    if not text:
        await message.answer("Формат: /admin_broadcast <code>текст</code>", parse_mode="HTML")
        return
    users = await get_all_users()
    sent = 0
    failed = 0
    bot = message.bot
    for u in users:
        try:
            await bot.send_message(u["user_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await message.answer(
        f"📨 Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибки: {failed}",
        parse_mode="HTML"
    )


@router.message(Command("admin_addkey"))
async def cmd_admin_addkey(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    key = f"Premium-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    from src.database.db import create_premium_key
    await create_premium_key(key)
    await message.answer(f"🔑 Новый ключ:\n<code>{key}</code>", parse_mode="HTML")


@router.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if not _is_url(text):
        await message.answer("Отправь ссылку на товар с Wildberries.", reply_markup=_main_menu_kb())
        return

    if "wildberries.ru" not in text:
        await message.answer(
            "❌ Поддерживаются только ссылки Wildberries.\n\n"
            "Отправь ссылку вида:\n"
            "<code>https://wildberries.ru/catalog/12345678/</code>",
            parse_mode="HTML",
            reply_markup=_main_menu_kb()
        )
        return

    user = await get_user(user_id)
    is_premium = user and user["is_premium"]

    if not await _check_limit(user_id, is_premium, user):
        ref_count = await get_referral_count(user_id)
        custom = user["custom_limit"] if user else 0
        if custom:
            limit = custom
        else:
            base_limit = PREMIUM_LIMIT if is_premium else FREE_LIMIT
            limit = base_limit + ref_count
        await message.answer(
            f"⚠️ Лимит ({limit} товаров).\nУдали ненужные или пригласи друзей +1 за каждого.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои товары", callback_data="list")],
                [InlineKeyboardButton(text="🔗 Реферал", callback_data="referral")],
            ])
        )
        return

    status_msg = await message.answer("🔍 Парсю страницу...")

    result = await parse_product(text)

    if "error" in result:
        try:
            await status_msg.edit_text(
                f"❌ {result['error']}\nПопробуй другую ссылку.",
                reply_markup=_main_menu_kb()
            )
        except Exception:
            await status_msg.delete()
            await message.answer(
                f"❌ {result['error']}\nПопробуй другую ссылку.",
                reply_markup=_main_menu_kb()
            )
        return

    short_id = _save_pending(text, {
        "title": result["title"],
        "price": result["price"],
        "currency": result["currency"],
        "image": result.get("image"),
    })

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Следить", callback_data=f"track:{short_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_track")],
    ])

    image = result.get("image")

    caption = (
        f"📦 <b>{result['title'][:100]}</b>\n\n"
        f"💰 <b>{result['price']}{result['currency']}</b>"
    )

    if image:
        try:
            await status_msg.delete()
        except Exception:
            pass
        try:
            await message.answer_photo(
                photo=image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb
            )
            return
        except Exception:
            pass

    try:
        await status_msg.edit_text(caption, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer(caption, parse_mode="HTML", reply_markup=kb)


async def _check_limit(user_id: int, is_premium: bool, user=None) -> bool:
    count = await get_user_product_count(user_id)
    if user and user["custom_limit"]:
        return count < user["custom_limit"]
    ref_count = await get_referral_count(user_id)
    base_limit = PREMIUM_LIMIT if is_premium else FREE_LIMIT
    limit = base_limit + ref_count
    return count < limit


@router.callback_query(F.data.startswith("track:"))
async def cb_track(callback_query: CallbackQuery):
    short_id = callback_query.data.split(":", 1)[1]
    pending = _get_pending(short_id)

    if not pending:
        try:
            await callback_query.message.edit_text(
                "⏰ Время действия истекло. Отправь ссылку заново.",
                reply_markup=_main_menu_kb()
            )
        except Exception:
            await callback_query.message.answer(
                "⏰ Время действия истекло. Отправь ссылку заново.",
                reply_markup=_main_menu_kb()
            )
        await callback_query.answer()
        return

    product_id = await add_product(
        user_id=callback_query.from_user.id,
        url=pending["url"],
        title=pending["title"],
        image_url=pending.get("image") or "",
        price=pending["price"],
        currency=pending["currency"]
    )

    success_text = (
        f"✅ <b>Товар добавлен!</b>\n\n"
        f"📦 {pending['title'][:80]}\n"
        f"💰 {pending['price']}{pending['currency']}\n"
        f"🆔 #{product_id}\n\n"
        f"Буду проверять цену каждые 30 мин.\n"
        f"Если цена упадёт — сообщу!"
    )

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await callback_query.message.answer(
        success_text,
        parse_mode="HTML",
        reply_markup=_reply_kb()
    )
    await callback_query.answer()


@router.callback_query(F.data == "cancel_track")
async def cb_cancel_track(callback_query: CallbackQuery):
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await callback_query.message.answer(
        "❌ Отменено.",
        reply_markup=_reply_kb()
    )
    await callback_query.answer()
