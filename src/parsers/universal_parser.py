import re
import json
import httpx
import logging
import os
from urllib.parse import quote

logger = logging.getLogger(__name__)

SCRAPER_KEY = os.getenv("SCRAPER_API_KEY", "")
WB_COOKIES = ""


async def _get_wb_cookies() -> str:
    global WB_COOKIES
    if WB_COOKIES:
        return WB_COOKIES

    try:
        from src.database.db import get_wb_tokens
        from config.settings import ADMIN_ID
        tokens = await get_wb_tokens(ADMIN_ID)
        if tokens and tokens[3]:
            WB_COOKIES = tokens[3]
            return WB_COOKIES
    except Exception as e:
        logger.error(f"Failed to load WB tokens: {e}")

    env_cookies = os.getenv("WB_COOKIES", "") or os.getenv("x_wbaas_token", "")
    if env_cookies:
        if "x_wbaas_token=" not in env_cookies:
            WB_COOKIES = f"x_wbaas_token={env_cookies}"
        else:
            WB_COOKIES = env_cookies

    return WB_COOKIES


WB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


def _update_headers(cookies: str):
    if cookies:
        WB_HEADERS["Cookie"] = cookies


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


async def _scraper_get(url: str) -> httpx.Response | None:
    if not SCRAPER_KEY:
        return None
    scraper_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={quote(url)}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url)
            if resp.status_code == 200:
                return resp
    except Exception as e:
        logger.error(f"ScraperAPI error: {e}")
    return None


async def _fetch_api_v2(nm_id: str) -> tuple[str | None, str | None, float | None]:
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
            else:
                logger.warning(f"API v2 status {resp.status_code}")
    except Exception as e:
        logger.error(f"API v2 error: {e}")
    return None, None, None


async def _fetch_search_scraper(nm_id: str) -> tuple[str | None, str | None, float | None]:
    search_url = f"https://search.wb.ru/exactmatch/ru/common/v7/search?appType=1&curr=rub&dest=-1257786&spp=30&query={nm_id}&resultset=catalog&sort=popular&page=1"
    resp = await _scraper_get(search_url)
    if resp:
        try:
            data = resp.json()
            products = data.get("data", {}).get("products", [])
            if not products:
                products = data.get("products", [])
            if not products:
                sr = data.get("search_result", {})
                products = sr.get("products", []) if isinstance(sr, dict) else []
            logger.info(f"Search found {len(products)} products")

            if products:
                for product in products:
                    pid = str(product.get("id", product.get("nmId", "")))
                    if pid == nm_id:
                        title = f"{product.get('brand', product.get('supplier', ''))} {product.get('name', product.get('title', ''))}".strip()
                        vol = product.get("vol", int(nm_id) // 100000)
                        part = product.get("part", int(nm_id) // 1000)
                        host = _wb_basket_host(vol)
                        image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"

                        sizes = product.get("sizes", [])
                        if sizes:
                            price_info = sizes[0].get("price", {})
                            total = price_info.get("total", price_info.get("basic", 0))
                            if total and total > 0:
                                return title, image_url, total / 100

                        sale = product.get("salePriceU", product.get("sale", 0))
                        if sale and sale > 100:
                            return title, image_url, sale / 100

                        return title, image_url, None

                product = products[0]
                title = f"{product.get('brand', product.get('supplier', ''))} {product.get('name', product.get('title', ''))}".strip()
                vol = product.get("vol", int(nm_id) // 100000)
                part = product.get("part", int(nm_id) // 1000)
                host = _wb_basket_host(vol)
                image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"

                sizes = product.get("sizes", [])
                if sizes:
                    price_info = sizes[0].get("price", {})
                    total = price_info.get("total", price_info.get("basic", 0))
                    if total and total > 0:
                        return title, image_url, total / 100

                sale = product.get("salePriceU", product.get("sale", 0))
                if sale and sale > 100:
                    return title, image_url, sale / 100

                return title, image_url, None
        except Exception as e:
            logger.error(f"Search scraper parse error: {e}")
    return None, None, None


async def _fetch_page_scraper(url: str) -> tuple[str | None, str | None, float | None]:
    resp = await _scraper_get(url)
    if resp:
        try:
            html = resp.text

            title = None
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()

            price = None

            for pattern in [
                r'"priceU":\s*(\d+)',
                r'"price":\s*"?(\d+)',
                r'"salePriceU":\s*(\d+)',
                r'"sale":\s*"?(\d+)',
            ]:
                m = re.search(pattern, html)
                if m:
                    val = int(m.group(1))
                    if val > 100:
                        price = val / 100
                    elif val > 0:
                        price = float(val)
                    break

            if not price:
                price_match = re.search(r'(\d[\d\s]*)\s*₽', html)
                if price_match:
                    price_str = price_match.group(1).replace(' ', '')
                    try:
                        price = float(price_str)
                    except ValueError:
                        pass

            image_url = None
            og_match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
            if og_match:
                image_url = og_match.group(1)

            return title, image_url, price
        except Exception as e:
            logger.error(f"Page scraper parse error: {e}")
    return None, None, None


async def _fetch_cdn(nm_id: str) -> tuple[str | None, str | None, float | None]:
    vol, part = _wb_calc_vol_part(nm_id)
    host = _wb_basket_host(vol)
    cdn_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"

    title = None
    image_url = None
    price = None

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.get(cdn_url, headers=WB_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("imt_name", "")
                image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
    except Exception:
        pass

    history_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/price-history.json"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
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
    except Exception:
        pass

    return title, image_url, price


async def parse_product(url: str) -> dict | None:
    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return {"error": "Поддерживаются только ссылки Wildberries"}

    nm_id = match.group(1)
    logger.info(f"WB parsing nm_id={nm_id}")

    cookies = await _get_wb_cookies()
    if cookies:
        _update_headers(cookies)

    title, image_url, price = await _fetch_cdn(nm_id)
    if price:
        logger.info(f"CDN price: {price}")

    if not price:
        api_title, api_image, api_price = await _fetch_api_v2(nm_id)
        if api_price:
            price = api_price
            logger.info(f"API v2 price: {price}")
        if not title and api_title:
            title = api_title
        if not image_url and api_image:
            image_url = api_image

    if not price and SCRAPER_KEY:
        s_title, s_image, s_price = await _fetch_search_scraper(nm_id)
        if s_price:
            price = s_price
            logger.info(f"Search scraper price: {price}")
        if not title and s_title:
            title = s_title
        if not image_url and s_image:
            image_url = s_image

    if not price and SCRAPER_KEY:
        p_title, p_image, p_price = await _fetch_page_scraper(url)
        if p_price:
            price = p_price
            logger.info(f"Page scraper price: {price}")
        if not title and p_title:
            title = p_title
        if not image_url and p_image:
            image_url = p_image

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
