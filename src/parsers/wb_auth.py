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

    url = "https://id.wb.ru/auth/v2/phone"
    payload = {"phone": f"+{phone_clean}"}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(url, json=payload, headers=WB_AUTH_HEADERS)
            data = resp.json()
            logger.info(f"WB send code status: {resp.status_code}, data: {data}")
            return {"ok": resp.status_code == 200, "data": data}
    except Exception as e:
        logger.error(f"WB send code error: {e}")
        return {"ok": False, "error": str(e)}


async def wb_confirm_code(phone: str, code: str, session_id: str = "") -> dict:
    """Confirm verification code and get tokens."""
    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not phone_clean.startswith("7") and not phone_clean.startswith("8"):
        phone_clean = "7" + phone_clean

    url = "https://id.wb.ru/auth/v2/confirm"
    payload = {
        "phone": f"+{phone_clean}",
        "code": code,
        "sessionId": session_id,
    }

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(url, json=payload, headers=WB_AUTH_HEADERS)
            data = resp.json()
            logger.info(f"WB confirm code status: {resp.status_code}")

            if resp.status_code == 200 and "token" in data:
                tokens = data.get("token", {})
                refresh = tokens.get("refresh", "")
                access = tokens.get("access", "")
                return {
                    "ok": True,
                    "refresh_token": refresh,
                    "access_token": access,
                    "data": data,
                }
            return {"ok": False, "data": data}
    except Exception as e:
        logger.error(f"WB confirm code error: {e}")
        return {"ok": False, "error": str(e)}


def build_cookie_string(refresh_token: str, access_token: str = "") -> str:
    """Build cookie string from tokens."""
    cookies = []
    if refresh_token:
        cookies.append(f"wbid-sdk-refresh={refresh_token}")
    if access_token:
        cookies.append(f"wbid-sdk-id-token={access_token}")
    cookies.append("_cp=1")
    return "; ".join(cookies)
