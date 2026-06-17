import re
import httpx
import logging

logger = logging.getLogger(__name__)

WB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


def _wb_calc_vol_part(nm_id: str) -> tuple[int, int]:
    nm = int(nm_id)
    vol = nm // 100000
    part = nm // 1000
    return vol, part


def _wb_basket_host(vol: int) -> str:
    if vol <= 143:
        return "basket-01.wbbasket.ru"
    elif vol <= 287:
        return "basket-02.wbbasket.ru"
    elif vol <= 431:
        return "basket-03.wbbasket.ru"
    elif vol <= 719:
        return "basket-04.wbbasket.ru"
    elif vol <= 1007:
        return "basket-05.wbbasket.ru"
    elif vol <= 1061:
        return "basket-06.wbbasket.ru"
    elif vol <= 1115:
        return "basket-07.wbbasket.ru"
    elif vol <= 1169:
        return "basket-08.wbbasket.ru"
    elif vol <= 1313:
        return "basket-09.wbbasket.ru"
    elif vol <= 1601:
        return "basket-10.wbbasket.ru"
    elif vol <= 1655:
        return "basket-11.wbbasket.ru"
    elif vol <= 1919:
        return "basket-12.wbbasket.ru"
    elif vol <= 2045:
        return "basket-13.wbbasket.ru"
    elif vol <= 2189:
        return "basket-14.wbbasket.ru"
    elif vol <= 2407:
        return "basket-15.wbbasket.ru"
    elif vol <= 2625:
        return "basket-16.wbbasket.ru"
    elif vol <= 2843:
        return "basket-17.wbbasket.ru"
    elif vol <= 3061:
        return "basket-18.wbbasket.ru"
    elif vol <= 3279:
        return "basket-19.wbbasket.ru"
    elif vol <= 3497:
        return "basket-20.wbbasket.ru"
    elif vol <= 3715:
        return "basket-21.wbbasket.ru"
    elif vol <= 3933:
        return "basket-22.wbbasket.ru"
    else:
        return "basket-23.wbbasket.ru"


async def _fetch_card_info(nm_id: str) -> tuple[str | None, str | None]:
    vol, part = _wb_calc_vol_part(nm_id)
    host = _wb_basket_host(vol)
    cdn_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(cdn_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("imt_name", "")
                image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
                return title, image_url
    except Exception as e:
        logger.error(f"CDN card error: {e}")
    return None, None


async def _fetch_price(nm_id: str) -> float | None:
    vol, part = _wb_calc_vol_part(nm_id)
    host = _wb_basket_host(vol)
    history_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/price-history.json"

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
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
                            return rub / 100
    except Exception as e:
        logger.error(f"CDN price error: {e}")
    return None


async def _fetch_api(nm_id: str) -> tuple[str | None, str | None, float | None]:
    from config.settings import PROXY_URL
    api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm_id}"
    proxies = PROXY_URL if PROXY_URL else None

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, proxy=proxies) as client:
            resp = await client.get(api_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                products = data.get("data", {}).get("products", [])
                if products:
                    product = products[0]
                    title = f"{product.get('brand', '')} {product.get('name', '')}".strip()

                    vol = product.get("vol", int(nm_id) // 100000)
                    part = product.get("part", int(nm_id) // 1000)
                    host = _wb_basket_host(vol)
                    image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"

                    sizes = product.get("sizes", [])
                    if sizes:
                        total = sizes[0].get("price", {}).get("total", 0)
                        if total > 0:
                            return title, image_url, total / 100
                    return title, image_url, None
    except Exception as e:
        logger.error(f"API error: {e}")
    return None, None, None


async def parse_product(url: str) -> dict | None:
    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return {"error": "Поддерживаются только ссылки Wildberries"}

    nm_id = match.group(1)
    logger.info(f"WB parsing nm_id={nm_id}")

    title, image_url = await _fetch_card_info(nm_id)
    price = await _fetch_price(nm_id)

    if not price:
        api_title, api_image, api_price = await _fetch_api(nm_id)
        if api_price:
            price = api_price
        if not title and api_title:
            title = api_title
        if not image_url and api_image:
            image_url = api_image

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
