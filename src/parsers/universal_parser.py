import re
import json
import httpx
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def _fetch_card_info(nm_id: str) -> tuple[str | None, str | None]:
    vol = int(nm_id[:4]) if len(nm_id) > 5 else int(nm_id[:4])
    part = int(nm_id[:6]) if len(nm_id) > 5 else int(nm_id[:6])

    basket_num = vol // 100000 + 1
    basket = f"basket-{basket_num:02d}"
    cdn_url = f"https://{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(cdn_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("imt_name", "")
                image_url = f"https://{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.jpg"
                return title, image_url
    except Exception:
        pass
    return None, None


async def _fetch_price(nm_id: str) -> float | None:
    vol = int(nm_id[:4]) if len(nm_id) > 5 else int(nm_id[:4])
    part = int(nm_id[:6]) if len(nm_id) > 5 else int(nm_id[:6])

    basket_num = vol // 100000 + 1
    basket = f"basket-{basket_num:02d}"

    history_url = f"https://{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/price-history.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(history_url, headers={"User-Agent": "Mozilla/5.0"})
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
    except Exception:
        pass

    return None


async def _scrape_price(url: str, nm_id: str) -> float | None:
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

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                for _ in range(15):
                    await page.wait_for_timeout(1500)

            except Exception:
                pass

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
                selectors = [
                    ".price-block__final-price",
                    ".price__lower-price",
                    ".product-page__price-now",
                    "ins.price__lower-price",
                    ".price-block__wallet-price",
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

            await browser.close()
            return price
    except Exception:
        return None


async def parse_product(url: str) -> dict | None:
    match = re.search(r"wildberries\.ru/catalog/(\d+)", url)
    if not match:
        return {"error": "Поддерживаются только ссылки Wildberries"}

    nm_id = match.group(1)
    logger.info(f"WB parsing nm_id={nm_id}")

    title, image_url = await _fetch_card_info(nm_id)

    price = await _fetch_price(nm_id)

    if not price:
        price = await _scrape_price(url, nm_id)

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
