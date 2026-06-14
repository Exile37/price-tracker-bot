import asyncpg
from config.settings import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def init_db():
    pool = await _get_pool()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT DEFAULT '',
            is_premium INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
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
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    """)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS premium_keys (
            id SERIAL PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            used_by BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (used_by) REFERENCES users(user_id)
        )
    """)


async def add_user(user_id: int, username: str = ""):
    pool = await _get_pool()
    await pool.execute(
        "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
        user_id, username
    )


async def get_user(user_id: int):
    pool = await _get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def get_user_product_count(user_id: int) -> int:
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*) FROM products WHERE user_id = $1 AND is_active = 1",
        user_id
    )
    return row[0]


async def add_product(user_id: int, url: str, title: str, image_url: str,
                       price: float, target_price: float = None, currency: str = "₽") -> int:
    pool = await _get_pool()
    product_id = await pool.fetchval(
        """INSERT INTO products (user_id, url, title, image_url, current_price, target_price, currency)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        user_id, url, title, image_url, price, target_price, currency
    )
    await pool.execute(
        "INSERT INTO price_history (product_id, price) VALUES ($1, $2)",
        product_id, price
    )
    return product_id


async def update_price(product_id: int, new_price: float):
    pool = await _get_pool()
    await pool.execute(
        """UPDATE products SET current_price = $1, last_checked = CURRENT_TIMESTAMP
           WHERE id = $2""",
        new_price, product_id
    )
    await pool.execute(
        "INSERT INTO price_history (product_id, price) VALUES ($1, $2)",
        product_id, new_price
    )


async def get_active_products():
    pool = await _get_pool()
    return await pool.fetch(
        "SELECT p.*, u.user_id FROM products p JOIN users u ON p.user_id = u.user_id WHERE p.is_active = 1"
    )


async def deactivate_product(product_id: int):
    pool = await _get_pool()
    await pool.execute("UPDATE products SET is_active = 0 WHERE id = $1", product_id)


async def get_user_products(user_id: int):
    pool = await _get_pool()
    return await pool.fetch(
        "SELECT * FROM products WHERE user_id = $1 AND is_active = 1 ORDER BY created_at DESC",
        user_id
    )


async def get_price_history(product_id: int, limit: int = 30):
    pool = await _get_pool()
    return await pool.fetch(
        """SELECT price, checked_at FROM price_history
           WHERE product_id = $1 ORDER BY checked_at DESC LIMIT $2""",
        product_id, limit
    )


async def set_premium(user_id: int, value: bool = True):
    pool = await _get_pool()
    await pool.execute(
        "UPDATE users SET is_premium = $1 WHERE user_id = $2",
        1 if value else 0, user_id
    )


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    pool = await _get_pool()
    try:
        await pool.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2)",
            referrer_id, referred_id
        )
        return True
    except asyncpg.UniqueViolationError:
        return False


async def get_referral_count(user_id: int) -> int:
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id
    )
    return row[0]


async def get_referrer(user_id: int) -> int | None:
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT referrer_id FROM referrals WHERE referred_id = $1", user_id
    )
    return row[0] if row else None


async def create_premium_key(key: str) -> bool:
    pool = await _get_pool()
    try:
        await pool.execute("INSERT INTO premium_keys (key) VALUES ($1)", key)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def use_premium_key(key: str, user_id: int) -> bool:
    pool = await _get_pool()
    row = await pool.fetchrow("SELECT id, used_by FROM premium_keys WHERE key = $1", key)
    if not row or row[1]:
        return False
    await pool.execute(
        "UPDATE premium_keys SET used_by = $1 WHERE id = $2",
        user_id, row[0]
    )
    return True
