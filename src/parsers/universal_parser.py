import re
import json
import httpx
import logging
import os

logger = logging.getLogger(__name__)

WB_COOKIES = os.getenv("WB_COOKIES", "") or os.getenv("x_wbaas_token", "")
WB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
if WB_COOKIES:
    WB_HEADERS["Cookie"] = WB_COOKIES


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


async def _fetch_page(url: str) -> tuple[str | None, str | None, float | None]:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=WB_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"Page fetch status {resp.status_code}")
                return None, None, None
            html = resp.text

            title = None
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()

            price = None

            ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
            if ld_match:
                try:
                    ld = json.loads(ld_match.group(1))
                    if isinstance(ld, dict) and "offers" in ld:
                        offers = ld["offers"]
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        p = offers.get("price")
                        if p:
                            price = float(p)
                except Exception:
                    pass

            if not price:
                for pattern in [
                    r'"priceU":\s*(\d+)',
                    r'"price":\s*(\d+)',
                    r'"salePriceU":\s*(\d+)',
                ]:
                    m = re.search(pattern, html)
                    if m:
                        val = int(m.group(1))
                        if val > 100:
                            price = val / 100
                        else:
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

            return title, image_url, price
    except Exception as e:
        logger.error(f"Page fetch error: {e}")
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

    title, image_url, price = await _fetch_cdn(nm_id)
    if price:
        logger.info(f"CDN price: {price}")

    if not price or not title:
        page_title, page_image, page_price = await _fetch_page(url)
        if page_price and not price:
            price = page_price
        if page_title and not title:
            title = page_title
        if page_image and not image_url:
            image_url = page_image
        if price:
            logger.info(f"Page price: {price}")

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
