import aiosqlite
import os
from config.settings import DB_PATH

_db: aiosqlite.Connection | None = None
_ABS_DB_PATH = os.path.join(os.getcwd(), DB_PATH)


async def _get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(_ABS_DB_PATH), exist_ok=True)
        _db = await aiosqlite.connect(_ABS_DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    db = await _get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            is_premium INTEGER DEFAULT 0,
            custom_limit INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            current_price REAL,
            target_price REAL,
            currency TEXT DEFAULT '₽',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS premium_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            used_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (used_by) REFERENCES users(user_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pending_urls (
            short_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()
    db = await _get_db()
    cursor = await db.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
        (user_id, username)
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_user(user_id: int):
    db = await _get_db()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
        return await cursor.fetchone()


async def get_user_product_count(user_id: int) -> int:
    db = await _get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM products WHERE user_id = ? AND is_active = 1",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0]


async def add_product(user_id: int, url: str, title: str, image_url: str,
                       price: float, target_price: float = None, currency: str = "₽") -> int:
    db = await _get_db()
    cursor = await db.execute(
        """INSERT INTO products (user_id, url, title, image_url, current_price, target_price, currency)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, url, title, image_url, price, target_price, currency)
    )
    product_id = cursor.lastrowid
    await db.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_id, price)
    )
    await db.commit()
    return product_id


async def update_price(product_id: int, new_price: float):
    db = await _get_db()
    await db.execute(
        """UPDATE products SET current_price = ?, last_checked = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_price, product_id)
    )
    await db.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_id, new_price)
    )
    await db.commit()


async def get_active_products():
    db = await _get_db()
    async with db.execute(
        "SELECT p.*, u.user_id FROM products p JOIN users u ON p.user_id = u.user_id WHERE p.is_active = 1"
    ) as cursor:
        return await cursor.fetchall()


async def deactivate_product(product_id: int):
    db = await _get_db()
    await db.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
    await db.commit()


async def get_user_products(user_id: int):
    db = await _get_db()
    async with db.execute(
        "SELECT * FROM products WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC",
        (user_id,)
    ) as cursor:
        return await cursor.fetchall()


async def get_price_history(product_id: int, limit: int = 30):
    db = await _get_db()
    async with db.execute(
        """SELECT price, checked_at FROM price_history
           WHERE product_id = ? ORDER BY checked_at DESC LIMIT ?""",
        (product_id, limit)
    ) as cursor:
        return await cursor.fetchall()


async def set_premium(user_id: int, value: bool = True):
    db = await _get_db()
    await db.execute(
        "UPDATE users SET is_premium = ? WHERE user_id = ?",
        (1 if value else 0, user_id)
    )
    await db.commit()


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, referred_id)
        )
        await db.commit()
        return True
    except Exception:
        return False


async def get_referral_count(user_id: int) -> int:
    db = await _get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0]


async def get_referrer(user_id: int) -> int | None:
    db = await _get_db()
    async with db.execute(
        "SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def create_premium_key(key: str) -> bool:
    db = await _get_db()
    try:
        await db.execute("INSERT INTO premium_keys (key) VALUES (?)", (key,))
        await db.commit()
        return True
    except Exception:
        return False


async def use_premium_key(key: str, user_id: int) -> bool:
    db = await _get_db()
    async with db.execute("SELECT id, used_by FROM premium_keys WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
        if not row or row[1]:
            return False
        await db.execute(
            "UPDATE premium_keys SET used_by = ? WHERE id = ?",
            (user_id, row[0])
        )
        await db.commit()
        return True


async def set_custom_limit(user_id: int, limit: int):
    db = await _get_db()
    await db.execute(
        "UPDATE users SET custom_limit = ? WHERE user_id = ?",
        (limit, user_id)
    )
    await db.commit()


async def get_all_users():
    db = await _get_db()
    async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
        return await cursor.fetchall()


async def get_user_count() -> int:
    db = await _get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
        return row[0]


async def get_premium_user_count() -> int:
    db = await _get_db()
    async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cursor:
        row = await cursor.fetchone()
        return row[0]


async def get_total_products() -> int:
    db = await _get_db()
    async with db.execute("SELECT COUNT(*) FROM products WHERE is_active = 1") as cursor:
        row = await cursor.fetchone()
        return row[0]


async def save_pending(short_id: str, user_id: int, data: dict):
    import json
    db = await _get_db()
    await db.execute(
        "INSERT OR REPLACE INTO pending_urls (short_id, user_id, data) VALUES (?, ?, ?)",
        (short_id, user_id, json.dumps(data))
    )
    await db.commit()


async def get_pending(short_id: str) -> dict | None:
    import json
    db = await _get_db()
    async with db.execute("SELECT data FROM pending_urls WHERE short_id = ?", (short_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            await db.execute("DELETE FROM pending_urls WHERE short_id = ?", (short_id,))
            await db.commit()
            return json.loads(row[0])
    return None
