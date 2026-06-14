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


async def _parse_wildberries(url: str) -> dict | None:
    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return None

    nm_id = match.group(1)
    vol = nm_id[:4]
    part = nm_id[:6]

    title = None
    image_url = None
    for i in range(1, 20):
        basket = f"basket-{i:02d}" if i < 10 else f"basket-{i}"
        cdn_url = f"https://{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(cdn_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("imt_name", "")
                    image_url = f"https://{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
                    break
        except Exception:
            pass

    price = None
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

            for _ in range(20):
                await page.wait_for_timeout(1500)

            # Priority 1: price near h1 (main product, not recommendations)
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

            # Priority 2: buy button price
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

            # Priority 3: DOM selectors
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

            # Priority 4: regex from page text (risky - may hit recommendations)
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

            # Priority 5: API (last resort)
            if not price and api_prices:
                price = api_prices[0].get("total", 0) / 100

            await browser.close()
    except Exception:
        pass

    if not title:
        title = "Товар Wildberries"
    if price is None:
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


async def parse_product(url: str) -> dict | None:
    if "wildberries.ru" in url:
        result = await _parse_wildberries(url)
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
