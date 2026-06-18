import re
import uuid
import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    WebAppInfo,
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
    get_total_products, save_pending, get_pending,
    set_user_setting, get_user_settings, add_savings,
    create_promocode, use_promocode, get_analytics,
    block_user, unblock_user, is_blocked, save_wb_tokens, get_wb_tokens
)
from src.chart import generate_price_chart
from config.settings import FREE_LIMIT, PREMIUM_LIMIT, ADMIN_ID, STARS_PRICE, WEBAPP_URL

router = Router()
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')


def _is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))


async def _save_pending(url: str, data: dict, user_id: int) -> str:
    short_id = uuid.uuid4().hex[:8]
    await save_pending(short_id, user_id, {**data, "url": url})
    return short_id


async def _get_pending(short_id: str) -> dict | None:
    return await get_pending(short_id)


async def _peek_pending(short_id: str) -> dict | None:
    import json
    from src.database.db import _get_db
    db = await _get_db()
    async with db.execute("SELECT data FROM pending_urls WHERE short_id = ?", (short_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return json.loads(row[0])
    return None


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои товары", callback_data="list")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ])


def _reply_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📱 Мой кабинет")],
        [KeyboardButton(text="📋 Мои товары"), KeyboardButton(text="📊 График")],
        [KeyboardButton(text="⭐ Премиум"), KeyboardButton(text="🔗 Реферал")],
        [KeyboardButton(text="💰 Пополнение звёзд")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@router.message(F.text == "📱 Мой кабинет")
async def btn_cabinet(message: Message):
    if WEBAPP_URL:
        url = f"{WEBAPP_URL}?user_id={message.from_user.id}"
        await message.answer(
            "📱 Открываю мини-приложение...",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Мой кабинет", web_app=WebAppInfo(url=url))],
                    [KeyboardButton(text="📋 Мои товары"), KeyboardButton(text="📊 График")],
                    [KeyboardButton(text="⭐ Премиум"), KeyboardButton(text="🔗 Реферал")],
                    [KeyboardButton(text="💰 Пополнение звёзд")],
                ],
                resize_keyboard=True,
            )
        )
    else:
        await message.answer("Мини-приложение ещё не настроено.")


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


@router.message(F.text == "💰 Пополнение звёзд")
async def btn_topup_stars(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Перейти к пополнению", url="https://t.me/revolut_stars_bot?start=ref_951494385")],
    ])
    await message.answer(
        "💰 <b>Пополнение звёзд</b>\n\n"
        "Нажми кнопку ниже, чтобы перейти к пополнению:",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "settings")
async def cb_settings(callback_query: CallbackQuery):
    settings = await get_user_settings(callback_query.from_user.id)
    min_drop = settings[0] if settings else 5
    interval = settings[1] if settings else 30

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📉 Мин. падение: {min_drop}%", callback_data="set_drop")],
        [InlineKeyboardButton(text=f"⏰ Интервал: {interval} мин", callback_data="set_interval")],
        [InlineKeyboardButton(text="🎁 Активировать промокод", callback_data="use_promo")],
        [InlineKeyboardButton(text="📊 Моя аналитика", callback_data="analytics")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])
    try:
        await callback_query.message.edit_text(
            "⚙️ <b>Настройки</b>\n\n"
            f"📉 Мин. падение для уведомления: <b>{min_drop}%</b>\n"
            f"⏰ Интервал проверки: <b>{interval} мин</b>",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        await callback_query.message.answer(
            "⚙️ <b>Настройки</b>",
            parse_mode="HTML",
            reply_markup=kb
        )
    await callback_query.answer()


@router.callback_query(F.data == "set_drop")
async def cb_set_drop(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1%", callback_data="drop:1"),
         InlineKeyboardButton(text="3%", callback_data="drop:3"),
         InlineKeyboardButton(text="5%", callback_data="drop:5")],
        [InlineKeyboardButton(text="10%", callback_data="drop:10"),
         InlineKeyboardButton(text="15%", callback_data="drop:15"),
         InlineKeyboardButton(text="20%", callback_data="drop:20")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")],
    ])
    await callback_query.message.edit_text(
        "📉 Выбери минимальное падение цены для уведомления:",
        reply_markup=kb
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("drop:"))
async def cb_drop_selected(callback_query: CallbackQuery):
    pct = int(callback_query.data.split(":")[1])
    await set_user_setting(callback_query.from_user.id, "min_drop_pct", pct)
    await callback_query.message.edit_text(
        f"✅ Уведомлять при падении > <b>{pct}%</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")]
        ])
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_interval")
async def cb_set_interval(callback_query: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15 мин", callback_data="interval:15"),
         InlineKeyboardButton(text="30 мин", callback_data="interval:30"),
         InlineKeyboardButton(text="1 час", callback_data="interval:60")],
        [InlineKeyboardButton(text="3 часа", callback_data="interval:180"),
         InlineKeyboardButton(text="6 часов", callback_data="interval:360")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")],
    ])
    await callback_query.message.edit_text(
        "⏰ Выбери интервал проверки цен:",
        reply_markup=kb
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("interval:"))
async def cb_interval_selected(callback_query: CallbackQuery):
    mins = int(callback_query.data.split(":")[1])
    await set_user_setting(callback_query.from_user.id, "check_interval", mins)
    h = mins // 60
    m = mins % 60
    text = f"{h} ч {m} мин" if h else f"{m} мин"
    await callback_query.message.edit_text(
        f"✅ Интервал проверки: <b>{text}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")]
        ])
    )
    await callback_query.answer()


@router.callback_query(F.data == "use_promo")
async def cb_use_promo(callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "🎁 Отправь промокод:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")]
        ])
    )
    await callback_query.answer()


@router.message(F.text.startswith("PROMO-"))
async def handle_promocode(message: Message):
    code = message.text.strip().upper()
    result = await use_promocode(code, message.from_user.id)
    if result:
        bonus = result["bonus_products"]
        if bonus:
            user = await get_user(message.from_user.id)
            current = user["custom_limit"] if user else 0
            await set_user_setting(message.from_user.id, "custom_limit", current + bonus)
            await message.answer(
                f"🎉 Промокод активирован!\n\n"
                f"📦 +{bonus} товаров к лимиту",
                reply_markup=_reply_kb()
            )
        else:
            await message.answer("🎉 Промокод активирован!", reply_markup=_reply_kb())
    else:
        await message.answer("❌ Неверный или уже использованный промокод.", reply_markup=_reply_kb())


@router.callback_query(F.data == "analytics")
async def cb_analytics(callback_query: CallbackQuery):
    a = await get_analytics(callback_query.from_user.id)
    settings = await get_user_settings(callback_query.from_user.id)
    saved = settings[2] if settings else 0

    text = (
        f"📊 <b>Моя аналитика</b>\n\n"
        f"📦 Товаров: <b>{a['total']}</b>\n"
        f"📉 Подешевело: <b>{a['drops']}</b>\n"
        f"📈 Подорожало: <b>{a['rises']}</b>\n"
        f"💰 Сэкономлено: <b>{saved:.0f}₽</b>"
    )
    await callback_query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")]
        ])
    )
    await callback_query.answer()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users = await get_user_count()
    premium_users = await get_premium_user_count()
    total_products = await get_total_products()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Пользователи ({total_users})", callback_data="adm_users")],
        [InlineKeyboardButton(text=f"⭐ Премиум ({premium_users})", callback_data="adm_premium")],
        [InlineKeyboardButton(text=f"📦 Товаров ({total_products})", callback_data="adm_products")],
        [InlineKeyboardButton(text="🎁 Создать промокод", callback_data="adm_promo")],
        [InlineKeyboardButton(text="🔑 Создать ключ", callback_data="adm_key")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="adm_broadcast")],
    ])
    await message.answer(
        f"🔧 <b>Админ-панель</b>\n\n"
        f"👤 Пользователей: <b>{total_users}</b>\n"
        f"⭐ Премиум: <b>{premium_users}</b>\n"
        f"📦 Товаров: <b>{total_products}</b>",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "adm_users")
async def cb_adm_users(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    users = await get_all_users()
    buttons = []
    for u in users[:8]:
        username = f"@{u['username']}" if u["username"] else str(u["user_id"])
        status = "⭐" if u["is_premium"] else ("🚫" if u["is_blocked"] else "👤")
        buttons.append([InlineKeyboardButton(
            text=f"{status} {username}",
            callback_data=f"adm_user:{u['user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    text = f"👥 <b>Пользователи ({len(users)}):</b>\n\nВыбери пользователя:"
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        await callback_query.message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback_query.answer()


@router.callback_query(F.data.startswith("adm_user:"))
async def cb_adm_user(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    uid = int(callback_query.data.split(":")[1])
    user = await get_user(uid)
    if not user:
        await callback_query.answer("Пользователь не найден")
        return
    username = f"@{user['username']}" if user["username"] else str(uid)
    status = "⭐ Премиум" if user["is_premium"] else ("🚫 Заблокирован" if user["is_blocked"] else "👤 Обычный")
    limit = user["custom_limit"] if user["custom_limit"] else "по умолчанию"

    blocked = user["is_blocked"] == 1
    prem_btn = "❌ Снять премиум" if user["is_premium"] else "⭐ Выдать премиум"
    block_btn = "✅ Разблокировать" if blocked else "🚫 Заблокировать"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=prem_btn, callback_data=f"adm_toggle_prem:{uid}")],
        [InlineKeyboardButton(text=block_btn, callback_data=f"adm_toggle_block:{uid}")],
        [InlineKeyboardButton(text="📦 Лимит товаров", callback_data=f"adm_setlimit:{uid}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="adm_users")],
    ])
    await callback_query.message.edit_text(
        f"👤 <b>{username}</b>\n\n"
        f"🆔 <code>{uid}</code>\n"
        f"Статус: {status}\n"
        f"Лимит: {limit}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("adm_toggle_prem:"))
async def cb_adm_toggle_prem(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    uid = int(callback_query.data.split(":")[1])
    user = await get_user(uid)
    new_state = not user["is_premium"]
    await set_premium(uid, new_state)
    status = "выдан" if new_state else "снят"
    await callback_query.answer(f"Премиум {status}!")
    await cb_adm_user(callback_query)


@router.callback_query(F.data.startswith("adm_toggle_block:"))
async def cb_adm_toggle_block(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    uid = int(callback_query.data.split(":")[1])
    user = await get_user(uid)
    blocked = user["is_blocked"] == 1
    if blocked:
        await unblock_user(uid)
        await callback_query.answer("Пользователь разблокирован!")
    else:
        await block_user(uid)
        await callback_query.answer("Пользователь заблокирован!")
    await cb_adm_user(callback_query)


@router.callback_query(F.data.startswith("adm_setlimit:"))
async def cb_adm_setlimit(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    uid = int(callback_query.data.split(":")[1])
    buttons = []
    for n in [3, 5, 10, 15, 20, 50]:
        buttons.append([InlineKeyboardButton(text=f"{n} товаров", callback_data=f"adm_limit:{uid}:{n}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm_user:{uid}")])
    await callback_query.message.edit_text(
        "📦 Выбери лимит товаров:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("adm_limit:"))
async def cb_adm_limit(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    uid = int(parts[1])
    limit = int(parts[2])
    await set_custom_limit(uid, limit)
    await callback_query.answer(f"Лимит установлен: {limit}")
    await cb_adm_user(callback_query)


@router.callback_query(F.data == "adm_premium")
async def cb_adm_premium(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    users = await get_all_users()
    premium = [u for u in users if u["is_premium"]]
    lines = []
    for u in premium[:15]:
        username = f"@{u['username']}" if u["username"] else str(u["user_id"])
        lines.append(f"⭐ {username}")
    text = f"⭐ <b>Премиум ({len(premium)}):</b>\n\n" + ("\n".join(lines) if lines else "Нет")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])
    await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback_query.answer()


@router.callback_query(F.data == "adm_products")
async def cb_adm_products(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    total = await get_total_products()
    await callback_query.message.edit_text(
        f"📦 Всего товаров: <b>{total}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
        ])
    )
    await callback_query.answer()


@router.callback_query(F.data == "adm_back")
async def cb_adm_back(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    total_users = await get_user_count()
    premium_users = await get_premium_user_count()
    total_products = await get_total_products()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Пользователи ({total_users})", callback_data="adm_users")],
        [InlineKeyboardButton(text=f"⭐ Премиум ({premium_users})", callback_data="adm_premium")],
        [InlineKeyboardButton(text=f"📦 Товаров ({total_products})", callback_data="adm_products")],
        [InlineKeyboardButton(text="🎁 Создать промокод", callback_data="adm_promo")],
        [InlineKeyboardButton(text="🔑 Создать ключ", callback_data="adm_key")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="adm_broadcast")],
    ])
    await callback_query.message.edit_text(
        f"🔧 <b>Админ-панель</b>\n\n"
        f"👤 Пользователей: <b>{total_users}</b>\n"
        f"⭐ Премиум: <b>{premium_users}</b>\n"
        f"📦 Товаров: <b>{total_products}</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback_query.answer()


@router.callback_query(F.data == "adm_key")
async def cb_adm_key(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    key = f"Premium-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    from src.database.db import create_premium_key
    await create_premium_key(key)
    await callback_query.message.edit_text(
        f"🔑 <b>Новый ключ:</b>\n<code>{key}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
        ])
    )
    await callback_query.answer()


@router.callback_query(F.data == "adm_promo")
async def cb_adm_promo(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "🎁 Отправь промокод в формате:\n<code>PROMO-XXXX 5</code>\n\n(код + бонус товаров)",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
        ])
    )
    await callback_query.answer()


@router.message(Command("admin_promo"))
async def cmd_admin_promo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Формат: /admin_promo <code>КОД БОНУС</code>", parse_mode="HTML")
        return
    code = parts[1].upper()
    bonus = int(parts[2])
    success = await create_promocode(code, bonus_products=bonus)
    if success:
        await message.answer(f"🎁 Промокод создан:\n<code>{code}</code>\n📦 Бонус: +{bonus} товаров", parse_mode="HTML")
    else:
        await message.answer("❌ Промокод уже существует.", parse_mode="HTML")


@router.callback_query(F.data == "adm_broadcast")
async def cb_adm_broadcast(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "📨 Отправь текст для рассылки:\n<code>/sendall Текст сообщения</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
        ])
    )
    await callback_query.answer()


@router.message(Command("sendall"))
async def cmd_sendall(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/sendall", "", 1).strip()
    if not text:
        await message.answer("Формат: /sendall <code>текст</code>", parse_mode="HTML")
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


@router.message(Command("admin_addkey"))
async def cmd_admin_addkey(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    key = f"Premium-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
    from src.database.db import create_premium_key
    await create_premium_key(key)
    await message.answer(f"🔑 Новый ключ:\n<code>{key}</code>", parse_mode="HTML")


@router.message(Command("admin_promo"))
async def cmd_admin_promo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Формат: /admin_promo <code>КОД БОНУС</code>\nБонус = кол-во товаров", parse_mode="HTML")
        return
    code = parts[1].upper()
    bonus = int(parts[2])
    success = await create_promocode(code, bonus_products=bonus)
    if success:
        await message.answer(f"🎁 Промокод создан:\n<code>{code}</code>\n📦 Бонус: +{bonus} товаров", parse_mode="HTML")
    else:
        await message.answer("❌ Промокод уже существует.", parse_mode="HTML")


from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


class WBCookiesState(StatesGroup):
    waiting_cookies = State()


@router.message(Command("wb_cookies"))
async def cmd_wb_cookies(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(WBCookiesState.waiting_cookies)
    await message.answer(
        "🍪 Отправь куки Wildberries.\n\n"
        "Как получить:\n"
        "1. Открой wildberries.ru в браузере\n"
        "2. F12 → Application → Cookies\n"
        "3. Скопируй все куки в формате:\n"
        "<code>x_wbaas_token=значение; _wbauid=значение; _cp=1</code>",
        parse_mode="HTML"
    )


@router.message(WBCookiesState.waiting_cookies)
async def wb_cookies_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    cookies = message.text.strip()
    if len(cookies) < 10:
        await message.answer("❌ Куки слишком короткие. Попробуй /wb_cookies заново")
        await state.clear()
        return

    from src.parsers.universal_parser import WB_HEADERS
    from config.settings import ADMIN_ID as AID
    await save_wb_tokens(AID, "manual", "", "", cookies)
    await state.clear()

    WB_HEADERS["Cookie"] = cookies

    await message.answer(
        "✅ <b>Куки сохранены!</b>\n\n"
        "Попробуй отправить ссылку на товар.",
        parse_mode="HTML",
        reply_markup=_reply_kb()
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if await is_blocked(user_id):
        return

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

    short_id = await _save_pending(text, {
        "title": result["title"],
        "price": result["price"],
        "currency": result["currency"],
        "image": result.get("image"),
    }, user_id)

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
    pending = await _peek_pending(short_id)

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

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Указать целевую цену", callback_data=f"target:{short_id}")],
        [InlineKeyboardButton(text="✅ Без цели", callback_data=f"track_now:{short_id}")],
    ])

    try:
        await callback_query.message.edit_text(
            f"💰 <b>{pending['title'][:80]}</b>\n\n"
            f"Текущая цена: <b>{pending['price']}{pending['currency']}</b>\n\n"
            "Хочешь установить целевую цену?\n"
            "Я сообщу когда цена достигнет значения.",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        await callback_query.message.answer(
            f"💰 <b>{pending['title'][:80]}</b>\n\n"
            f"Текущая цена: <b>{pending['price']}{pending['currency']}</b>\n\n"
            "Хочешь установить целевую цену?",
            parse_mode="HTML",
            reply_markup=kb
        )
    await callback_query.answer()


@router.callback_query(F.data.startswith("target:"))
async def cb_target_price(callback_query: CallbackQuery):
    short_id = callback_query.data.split(":", 1)[1]
    pending = await _get_pending(short_id)

    if not pending:
        await callback_query.message.edit_text("⏰ Время действия истекло.", reply_markup=_main_menu_kb())
        await callback_query.answer()
        return

    await save_pending(short_id, callback_query.from_user.id, {**pending, "_awaiting_target": True})

    await callback_query.message.edit_text(
        f"🎯 Введи целевую цену для:\n"
        f"<b>{pending['title'][:60]}</b>\n\n"
        f"Текущая: {pending['price']}{pending['currency']}\n\n"
        "Напиши число (например: <code>500</code>) или «нет» чтобы пропустить:",
        parse_mode="HTML"
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("track_now:"))
async def cb_track_now(callback_query: CallbackQuery):
    short_id = callback_query.data.split(":", 1)[1]
    pending = await _get_pending(short_id)

    if not pending:
        await callback_query.message.edit_text("⏰ Время действия истекло.", reply_markup=_main_menu_kb())
        await callback_query.answer()
        return

    product_id = await add_product(
        user_id=callback_query.from_user.id,
        url=pending["url"],
        title=pending["title"],
        image_url=pending.get("image") or "",
        price=pending["price"],
        currency=pending["currency"],
        target_price=pending.get("target_price"),
    )

    success_text = (
        f"✅ <b>Товар добавлен!</b>\n\n"
        f"📦 {pending['title'][:80]}\n"
        f"💰 {pending['price']}{pending['currency']}\n"
        f"🆔 #{product_id}\n\n"
    )
    if pending.get("target_price"):
        success_text += f"🎯 Цель: {pending['target_price']}{pending['currency']}\n\n"
    success_text += "Буду проверять цену каждые 30 мин.\nЕсли цена упадёт — сообщу!"

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await callback_query.message.answer(success_text, parse_mode="HTML", reply_markup=_reply_kb())
    await callback_query.answer()


@router.message(F.text.regexp(r"^\d+([.,]\d+)?$"))
async def handle_target_price(message: Message):
    user_id = message.from_user.id
    target = message.text.replace(",", ".").strip()
    try:
        target_val = float(target)
    except ValueError:
        return

    import json
    db = await __import__('src.database.db', fromlist=['_get_db'])._get_db()
    async with db.execute(
        "SELECT short_id, data FROM pending_urls WHERE user_id = ? AND data LIKE '%_awaiting_target%'",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row:
        short_id, data_str = row
        data = json.loads(data_str)
        await db.execute("DELETE FROM pending_urls WHERE short_id = ?", (short_id,))
        await db.commit()

        product_id = await add_product(
            user_id=user_id,
            url=data["url"],
            title=data["title"],
            image_url=data.get("image") or "",
            price=data["price"],
            currency=data["currency"],
            target_price=target_val,
        )

        success_text = (
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📦 {data['title'][:80]}\n"
            f"💰 {data['price']}{data['currency']}\n"
            f"🎯 Цель: {target_val}{data['currency']}\n"
            f"🆔 #{product_id}\n\n"
            "Буду проверять цену каждые 30 мин.\n"
            "Как только цена достигнет цели — сообщу!"
        )

        await message.answer(success_text, parse_mode="HTML", reply_markup=_reply_kb())


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
