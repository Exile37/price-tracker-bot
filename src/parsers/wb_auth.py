import httpx
import logging

logger = logging.getLogger(__name__)

WB_AUTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


async def wb_send_code(phone: str) -> dict:
    """Send verification code to phone number."""
    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not phone_clean.startswith("7") and not phone_clean.startswith("8"):
        phone_clean = "7" + phone_clean

    urls = [
        "https://id.wb.ru/auth/v2/phone",
        "https://passport.wb.ru/auth/v2/phone",
        "https://id.wb.ru/auth/phone",
    ]

    for url in urls:
        payload = {"phone": f"+{phone_clean}"}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.post(url, json=payload, headers=WB_AUTH_HEADERS)
                logger.info(f"WB send code [{url}]: status={resp.status_code}, body={resp.text[:200]}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return {"ok": True, "data": data}
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"WB send code error [{url}]: {e}")

    return {"ok": False, "error": "Не удалось отправить код. Попробуй позже."}


async def wb_confirm_code(phone: str, code: str, session_id: str = "") -> dict:
    """Confirm verification code and get tokens."""
    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not phone_clean.startswith("7") and not phone_clean.startswith("8"):
        phone_clean = "7" + phone_clean

    urls = [
        "https://id.wb.ru/auth/v2/confirm",
        "https://passport.wb.ru/auth/v2/confirm",
        "https://id.wb.ru/auth/confirm",
    ]

    for url in urls:
        payload = {
            "phone": f"+{phone_clean}",
            "code": code,
            "sessionId": session_id,
        }
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.post(url, json=payload, headers=WB_AUTH_HEADERS)
                logger.info(f"WB confirm [{url}]: status={resp.status_code}, body={resp.text[:200]}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        tokens = data.get("token", data.get("tokens", {}))
                        if isinstance(tokens, dict):
                            refresh = tokens.get("refresh", tokens.get("refresh_token", ""))
                            access = tokens.get("access", tokens.get("access_token", ""))
                            if refresh or access:
                                return {
                                    "ok": True,
                                    "refresh_token": refresh,
                                    "access_token": access,
                                    "data": data,
                                }
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"WB confirm error [{url}]: {e}")

    return {"ok": False, "error": "Не удалось подтвердить код. Попробуй /wb_login заново"}


def build_cookie_string(refresh_token: str, access_token: str = "") -> str:
    """Build cookie string from tokens."""
    cookies = []
    if refresh_token:
        cookies.append(f"wbid-sdk-refresh={refresh_token}")
    if access_token:
        cookies.append(f"wbid-sdk-id-token={access_token}")
    cookies.append("_cp=1")
    return "; ".join(cookies)
