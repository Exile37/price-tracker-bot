import re
import json
import uuid
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse


async def fetch_page(url: str, use_browser: bool = False) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text
    except Exception:
        if use_browser:
            return await _fetch_with_playwright(url)
        return None


async def _fetch_with_playwright(url: str) -> str | None:
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        return None


def _wb_get_vol_part(nm_id: str) -> tuple[str, str]:
    vol = int(nm_id[:len(nm_id) // 2 if len(nm_id) > 5 else 4])
    part = int(nm_id[:len(nm_id) - 3 if len(nm_id) > 5 else 6])
    return str(vol), str(part)


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


async def _wb_get_card_info(nm_id: str) -> tuple[str | None, str | None]:
    vol, part = _wb_get_vol_part(nm_id)
    host = _wb_basket_host(int(vol))
    cdn_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(cdn_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("imt_name", "")
                seller = data.get("selling", "")
                brand = data.get("nm_id", "")
                image_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
                return title, image_url
    except Exception:
        pass
    return None, None


async def _wb_get_prices(nm_id: str) -> float | None:
    import logging
    log = logging.getLogger(__name__)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://card.wb.ru/cards/v2/detail",
                params={"appType": "1", "curr": "rub", "nm": nm_id},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Origin": "https://www.wildberries.ru",
                    "Referer": "https://www.wildberries.ru/",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                products = data.get("data", {}).get("products", [])
                for prod in products:
                    if str(prod.get("id")) == nm_id:
                        sizes = prod.get("sizes", [])
                        for size in sizes:
                            for price_info in size.get("price", []):
                                if isinstance(price_info, dict):
                                    total = price_info.get("total", 0)
                                    if total > 0:
                                        return total / 100
    except Exception:
        pass

    try:
        vol, part = _wb_get_vol_part(nm_id)
        host = _wb_basket_host(int(vol))
        api_url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/price-history.json"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
            log.info(f"WB price-history status={resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    log.info(f"WB price-history type: {type(data).__name__}")

                    history = data if isinstance(data, list) else data.get("history", [])
                    if history:
                        latest = history[-1]
                        price_obj = latest.get("price", {})
                        if isinstance(price_obj, dict):
                            rub = price_obj.get("RUB", 0)
                            if rub and rub > 0:
                                log.info(f"WB price from history: {rub}")
                                return rub / 100
                        elif isinstance(price_obj, (int, float)) and price_obj > 0:
                            return price_obj / 100

                    if isinstance(data, dict):
                        top_price = data.get("price")
                        if isinstance(top_price, (int, float)) and top_price > 0:
                            return top_price / 100
                        for key in ["salePriceU", "sale", "currentPrice", "priceU"]:
                            val = data.get(key)
                            if val and isinstance(val, (int, float)) and val > 0:
                                return val / 100 if val > 100 else val
                except Exception as e:
                    log.error(f"WB price-history parse error: {e}")
    except Exception as e:
        log.error(f"WB price-history request error: {e}")

    return None


async def _wb_scrape_price(url: str, nm_id: str) -> float | None:
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU",
            )
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            api_prices = []

            async def on_response(response):
                try:
                    u = response.url
                    if ("cards" in u and "detail" in u) or "u-card" in u:
                        d = await response.json()
                        for prod in d.get("products", []):
                            if str(prod.get("id")) == nm_id:
                                for s in prod.get("sizes", []):
                                    for pi in s.get("price", []):
                                        if isinstance(pi, dict) and pi.get("name") == "rur":
                                            api_prices.append(pi)
                except Exception:
                    pass

            page.on("response", on_response)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            for _ in range(15):
                await page.wait_for_timeout(1500)

            price = None

            try:
                price = await page.evaluate("""
                    () => {
                        const h1 = document.querySelector('h1');
                        if (!h1) return null;
                        const parent = h1.closest('[class*=productPage]') || h1.parentElement.parentElement.parentElement;
                        if (!parent) return null;
                        const els = parent.querySelectorAll('ins, span, div');
                        for (const el of els) {
                            const text = (el.innerText || '').trim();
                            if (/^\\d[\\d\\s]*₽$/.test(text) && text.length < 20) {
                                return text.replace(/[^\\d]/g, '');
                            }
                        }
                        return null;
                    }
                """)
                if price:
                    price = float(price)
            except Exception:
                pass

            if not price:
                try:
                    price = await page.evaluate("""
                        () => {
                            const btns = document.querySelectorAll('button');
                            for (const btn of btns) {
                                const text = (btn.innerText || '').trim();
                                if (/^\\d[\\d\\s]*₽$/.test(text) && text.length < 20) {
                                    return text.replace(/[^\\d]/g, '');
                                }
                            }
                            return null;
                        }
                    """)
                    if price:
                        price = float(price)
                except Exception:
                    pass

            if not price:
                selectors = [
                    ".price-block__final-price",
                    ".price__lower-price",
                    ".product-page__price-now",
                    "ins.price__lower-price",
                    ".price-block__wallet-price",
                    ".product-page__price",
                    "[data-price]",
                ]
                for sel in selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = await el.inner_text()
                            nums = re.findall(r"(\d[\d\s]*\d)", txt)
                            if nums:
                                price = float(nums[0].replace(" ", ""))
                                break
                    except Exception:
                        pass

            if not price:
                try:
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")
                    text = soup.get_text()
                    found = re.findall(r"(\d[\d\s]*\d)\s*₽", text)
                    if found:
                        price = float(found[0].replace(" ", ""))
                except Exception:
                    pass

            if not price and api_prices:
                price = api_prices[0].get("total", 0) / 100

            await browser.close()
            return price
    except Exception:
        return None


async def _parse_wildberries(url: str) -> dict | None:
    import logging
    log = logging.getLogger(__name__)

    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return None

    nm_id = match.group(1)
    log.info(f"WB parsing nm_id={nm_id}")

    title, image_url = await _wb_get_card_info(nm_id)
    log.info(f"WB card: title={title[:50] if title else None}, image={'yes' if image_url else 'no'}")

    price = await _wb_get_prices(nm_id)
    log.info(f"WB API price: {price}")

    if not price:
        log.info("WB API failed, trying Playwright scrape...")
        price = await _wb_scrape_price(url, nm_id)
        log.info(f"WB scrape price: {price}")

    if not title:
        title = "Товар Wildberries"
    if price is None:
        log.warning(f"WB: all methods failed for nm_id={nm_id}")
        return None

    return {
        "title": title,
        "price": price,
        "currency": "₽",
        "image": image_url,
    }


def _extract_json_ld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") == "Product":
                return data
            if isinstance(data, dict) and "@graph" in data:
                for item in data["@graph"]:
                    if item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_og_tags(soup: BeautifulSoup) -> dict | None:
    title = soup.find("meta", property="og:title")
    image = soup.find("meta", property="og:image")
    if title:
        return {
            "title": title.get("content", ""),
            "image": image.get("content", "") if image else None,
        }
    return None


def _extract_price_from_json_ld(data: dict) -> tuple[float | None, str]:
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = offers.get("price") or offers.get("lowPrice")
    currency = offers.get("priceCurrency", "RUB")

    if price:
        try:
            return float(price), currency
        except (ValueError, TypeError):
            pass
    return None, currency


def _extract_price_from_text(html: str) -> tuple[float | None, str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text()

    patterns = [
        r'(\d[\d\s]*[\d,\.])\s*(?:₽|руб|RUB|USD|\$|€)',
        r'(?:₽|руб|RUB|USD|\$|€)\s*(\d[\d\s]*[\d,\.])',
        r'(?:price|цена|стоимость)[^\d]*?(\d[\d\s]*[\d,\.])',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(" ", "").replace(",", ".")
            try:
                return float(raw), "RUB"
            except ValueError:
                continue
    return None, "RUB"


def _extract_title(soup: BeautifulSoup, json_ld: dict | None, og: dict | None) -> str:
    if json_ld and json_ld.get("name"):
        return json_ld["name"]
    if og and og.get("title"):
        return og["title"]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:200]
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)[:200]
    return "Без названия"


def _extract_image(soup: BeautifulSoup, json_ld: dict | None, og: dict | None) -> str | None:
    if json_ld and json_ld.get("image"):
        img = json_ld["image"]
        if isinstance(img, str):
            return img
        if isinstance(img, list) and img:
            return img[0]
    if og and og.get("image"):
        return og["image"]
    img_tag = soup.find("img", {"itemprop": "image"})
    if img_tag:
        return img_tag.get("src")
    return None


PLATFORM_PARSERS = {
    "ozon.ru": {
        "selectors": {
            "price": ".pdp-order-price__current, span[data-v-6c9881e2]",
        }
    },
    "aliexpress.com": {
        "selectors": {
            "price": ".snow-price_SnowPrice__mainS, .product-price-value",
        }
    },
    "amazon.com": {
        "selectors": {
            "price": "#priceblock_ourprice, .a-price .a-offscreen, #corePrice_feature_div .a-offscreen",
        }
    },
    "ebay.com": {
        "selectors": {
            "price": ".x-bin-price__content, .x-price-primary",
        }
    },
    "avito.ru": {
        "selectors": {
            "price": "[data-marker='item-price'], .price-value-main",
        }
    },
    "citilink.ru": {
        "selectors": {
            "price": ".ProductPrice_price__2S07M, [data-meta-price]",
        }
    },
    "dns-shop.ru": {
        "selectors": {
            "price": ".product-buy__price, .product-buy__price_type_current",
        }
    },
}


def _parse_platform(soup: BeautifulSoup, domain: str) -> float | None:
    for platform, config in PLATFORM_PARSERS.items():
        if platform in domain:
            for selector in config["selectors"]["price"]:
                el = soup.select_one(selector)
                if el:
                    raw = re.sub(r"[^\d,\.]", "", el.get_text())
                    raw = raw.replace(",", ".")
                    try:
                        return float(raw)
                    except ValueError:
                        continue
    return None


async def _parse_ozon(url: str) -> dict | None:
    import logging
    log = logging.getLogger(__name__)

    match = re.search(r"ozon\.ru/product/.*?-(\d+)/?", url)
    if not match:
        match = re.search(r"ozon\.ru/product/(\d+)", url)
    if not match:
        return None

    product_id = match.group(1)
    log.info(f"Ozon parsing product_id={product_id}")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                f"https://api.ozon.ru/composer-api.bx/page/json/v2",
                params={"url": f"/product/{product_id}"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "x-requested-with": "XMLHttpRequest",
                },
            )
            log.info(f"Ozon API status={resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                widget = data.get("widgetStates", {})
                for key, val in widget.items():
                    if "description" in key.lower() or "detail" in key.lower():
                        try:
                            w = json.loads(val) if isinstance(val, str) else val
                            title = w.get("title") or w.get("name", "")
                            price_raw = w.get("price") or w.get("actionPrice") or w.get("oldPrice", "")
                            if price_raw:
                                price_str = re.sub(r"[^\d,\.]", "", str(price_raw)).replace(",", ".")
                                price = float(price_str) if price_str else None
                                if price and price > 0:
                                    image = w.get("image") or w.get("imageUrl", "")
                                    log.info(f"Ozon widget price: {price}")
                                    return {"title": title or "Товар Ozon", "price": price, "currency": "₽", "image": image}
                        except Exception:
                            pass
    except Exception as e:
        log.error(f"Ozon API error: {e}")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.ozon.ru/composer-api.bx/page/json/v2",
                params={"url": url.replace("https://ozon.ru", "").replace("https://www.ozon.ru", "")},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "x-requested-with": "XMLHttpRequest",
                },
            )
            log.info(f"Ozon page API status={resp.status_code}")
            if resp.status_code == 200:
                text = resp.text
                price_match = re.search(r'"price":\s*"?(\d[\d\s]*\d)"?', text)
                title_match = re.search(r'"title":\s*"([^"]{5,200})"', text)
                if price_match:
                    price = float(price_match.group(1).replace(" ", ""))
                    title = title_match.group(1) if title_match else "Товар Ozon"
                    log.info(f"Ozon regex price: {price}")
                    return {"title": title, "price": price, "currency": "₽", "image": None}
    except Exception as e:
        log.error(f"Ozon page API error: {e}")

    return None


async def _parse_yandex_market(url: str) -> dict | None:
    import logging
    log = logging.getLogger(__name__)

    match = re.search(r"market\.yandex\.ru/product/(\d+)", url)
    if not match:
        match = re.search(r"market\.yandex\.ru/(\d+)", url)
    if not match:
        return None

    product_id = match.group(1)
    log.info(f"Yandex Market parsing product_id={product_id}")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                f"https://market.yandex.ru/api/resolveProductOffer",
                params={"productId": product_id},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Referer": "https://market.yandex.ru/",
                },
            )
            log.info(f"Yandex Market API status={resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                offer = data.get("offer") or data.get("product", {})
                title = offer.get("title") or offer.get("name", "")
                price_data = offer.get("price") or offer.get("price", {})
                if isinstance(price_data, dict):
                    price_val = price_data.get("value") or price_data.get("price", 0)
                else:
                    price_val = price_data
                if price_val and float(price_val) > 0:
                    image = offer.get("image") or offer.get("picture", "")
                    log.info(f"Yandex Market API price: {price_val}")
                    return {"title": title or "Товар Яндекс Маркет", "price": float(price_val), "currency": "₽", "image": image}
    except Exception as e:
        log.error(f"Yandex Market API error: {e}")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
            })
            log.info(f"Yandex Market page status={resp.status_code}")
            if resp.status_code == 200:
                text = resp.text
                price_patterns = [
                    r'"price":\s*\{[^}]*"value":\s*"?(\d[\d\s]*\d)"?',
                    r'data-auto="price"[^>]*>(\d[\d\s]*\d)',
                    r'"currentPrice":\s*"?(\d[\d\s]*\d)"?',
                ]
                for pattern in price_patterns:
                    m = re.search(pattern, text)
                    if m:
                        price = float(m.group(1).replace(" ", ""))
                        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', text)
                        title = title_match.group(1).strip() if title_match else "Товар Яндекс Маркет"
                        log.info(f"Yandex Market regex price: {price}")
                        return {"title": title[:200], "price": price, "currency": "₽", "image": None}
    except Exception as e:
        log.error(f"Yandex Market page error: {e}")

    return None


async def parse_product(url: str) -> dict | None:
    if "wildberries.ru" in url:
        result = await _parse_wildberries(url)
        if result:
            return result

    if "ozon.ru" in url:
        result = await _parse_ozon(url)
        if result:
            return result

    if "market.yandex.ru" in url or "market.yandex.ua" in url:
        result = await _parse_yandex_market(url)
        if result:
            return result

    html = await fetch_page(url)
    if not html:
        return {"error": "Не удалось загрузить страницу"}

    soup = BeautifulSoup(html, "lxml")
    json_ld = _extract_json_ld(soup)
    og = _extract_og_tags(soup)

    title = _extract_title(soup, json_ld, og)
    image = _extract_image(soup, json_ld, og)

    price = None
    currency = "RUB"

    if json_ld:
        price, currency = _extract_price_from_json_ld(json_ld)

    if price is None:
        domain = urlparse(url).netloc.lower()
        price = _parse_platform(soup, domain)

    if price is None:
        price, currency = _extract_price_from_text(html)

    if price is None:
        html = await fetch_page(url, use_browser=True)
        if html:
            soup = BeautifulSoup(html, "lxml")
            json_ld = _extract_json_ld(soup)
            if json_ld:
                price, currency = _extract_price_from_json_ld(json_ld)
            if price is None:
                domain = urlparse(url).netloc.lower()
                price = _parse_platform(soup, domain)
            if price is None:
                price, currency = _extract_price_from_text(html)

    if price is None:
        return {"error": "Не удалось извлечь цену"}

    currency_symbols = {"RUB": "₽", "USD": "$", "EUR": "€", "BYN": "Br", "KZT": "₸"}
    currency_symbol = currency_symbols.get(currency, currency)

    return {
        "title": title,
        "price": price,
        "currency": currency_symbol,
        "image": image,
    }
