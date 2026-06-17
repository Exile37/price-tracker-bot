import re
import httpx
import logging

logger = logging.getLogger(__name__)

WB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


async def _fetch_from_api(nm_id: str) -> tuple[str | None, str | None, float | None]:
    """Fetch product info from WB detail API."""
    api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm_id}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                products = data.get("data", {}).get("products", [])
                if products:
                    product = products[0]
                    title = product.get("name", "")
                    brand = product.get("brand", "")
                    full_title = f"{brand} {title}".strip() if brand else title

                    image_id = product.get("id", nm_id)
                    vol = product.get("vol", int(nm_id) // 100000)
                    image_url = f"https://basket-{(vol % 23) + 1:02d}.wbbasket.ru/vol{vol}/part{image_id}/{image_id}/images/big/1.jpg"

                    sizes = product.get("sizes", [])
                    if sizes:
                        price_info = sizes[0].get("price", {})
                        total = price_info.get("total", 0)
                        if total > 0:
                            return full_title, image_url, total / 100
                    return full_title, image_url, None
    except Exception as e:
        logger.error(f"API fetch error: {e}")
    return None, None, None


async def _fetch_from_cdn(nm_id: str) -> tuple[str | None, str | None, float | None]:
    """Fetch from WB CDN (card.json + price-history.json)."""
    nm = int(nm_id)
    vol = nm // 100000
    part = nm // 1000

    basket_num = (vol % 23) + 1
    host = f"basket-{basket_num:02d}.wbbasket.ru"

    title = None
    image_url = None
    price = None

    card_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            resp = await client.get(card_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("imt_name", "")
                image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
    except Exception as e:
        logger.error(f"CDN card fetch error: {e}")

    history_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/price-history.json"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(history_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                history = data if isinstance(data, list) else data.get("history", [])
                if history:
                    latest = history[-1]
                    price_obj = latest.get("price", {})
                    if isinstance(price_obj, dict):
                        rub = price_obj.get("RUB", 0)
                        if rub and rub > 0:
                            price = rub / 100
    except Exception as e:
        logger.error(f"CDN price fetch error: {e}")

    return title, image_url, price


async def parse_product(url: str) -> dict | None:
    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return {"error": "Поддерживаются только ссылки Wildberries"}

    nm_id = match.group(1)
    logger.info(f"WB parsing nm_id={nm_id}")

    title, image_url, price = await _fetch_from_api(nm_id)

    if not price:
        cdn_title, cdn_image, cdn_price = await _fetch_from_cdn(nm_id)
        if cdn_price:
            price = cdn_price
        if not title and cdn_title:
            title = cdn_title
        if not image_url and cdn_image:
            image_url = cdn_image

    if not title:
        title = "Товар Wildberries"
    if price is None:
        return {"error": "Не удалось получить цену"}

    return {
        "title": title,
        "price": price,
        "currency": "₽",
        "image": image_url,
    }
