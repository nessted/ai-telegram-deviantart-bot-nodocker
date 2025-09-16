# app/web/main.py
from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import httpx
from sqlalchemy import select

from app.config import settings
from app.db import async_session, init_db
from app.models import User, ApiCredentials
from app.crypto import fernet_encrypt

# (опционально) если у тебя есть свой кодировщик/декодер state
try:
    from app.utils.oauth_state import parse_state  # type: ignore
except Exception:
    parse_state = None  # fallback

app = FastAPI(title="OAuth bridge")

SUCCESS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Connected</title></head>
<body style="font-family: system-ui, -apple-system, Segoe UI, Roboto;">
  <h2>✅ DeviantArt connected</h2>
  <p>You can return to Telegram now.</p>
</body></html>"""

def error_html(msg: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Error</title></head>
<body style="font-family: system-ui, -apple-system, Segoe UI, Roboto;">
  <h2>❌ Error</h2>
  <pre>{msg}</pre>
</body></html>"""

@app.on_event("startup")
async def _startup():
    # гарантируем, что таблицы созданы
    await init_db()

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/oauth/deviantart/callback")
async def deviantart_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    # 1) DeviantArt вернул ошибку
    if error:
        return HTMLResponse(error_html(f"{error}: {error_description or ''}"), status_code=400)

    if not code or not state:
        return HTMLResponse(error_html("Missing code or state"), status_code=400)

    # 2) извлечём tg_id из state
    tg_id: int | None = None
    if parse_state is not None:
        try:
            sdata = parse_state(state)  # твой декодер должен вернуть dict с tg_id
            tg_id = int(sdata.get("tg") or sdata.get("tg_id"))
        except Exception:
            tg_id = None

    if tg_id is None:
        # fallback формат "tg:<id>"
        if state.startswith("tg:"):
            try:
                tg_id = int(state.split(":", 1)[1])
            except Exception:
                return HTMLResponse(error_html("invalid state"), status_code=400)
        else:
            return HTMLResponse(error_html("unsupported state format"), status_code=400)

    # 3) обменяем code -> tokens
    token_url = "https://www.deviantart.com/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.DA_CLIENT_ID,
        "client_secret": settings.DA_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.DA_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(token_url, data=data)
        try:
            payload = r.json()
        except Exception:
            payload = {"status_code": r.status_code, "text": r.text}

    if (isinstance(payload, dict) and payload.get("error")) or r.status_code != 200:
        return HTMLResponse(error_html(f"token error: {payload}"), status_code=400)

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token") or ""
    if not access_token:
        return HTMLResponse(error_html(f"no access_token in response: {payload}"), status_code=400)

    # 4) найдём или создадим пользователя по tg_id
    async with async_session() as s:
        r = await s.execute(select(User).where(User.tg_id == tg_id))
        user = r.scalar_one_or_none()
        if not user:
            user = User(tg_id=tg_id, username=None)
            s.add(user)
            await s.commit()
            await s.refresh(user)

        # 5) сохраним/обновим креды DA
        access_enc = fernet_encrypt(access_token)
        refresh_enc = fernet_encrypt(refresh_token) if refresh_token else ""

        r2 = await s.execute(
            select(ApiCredentials).where(ApiCredentials.user_id == user.id, ApiCredentials.service == "deviantart")
        )
        cred = r2.scalar_one_or_none()
        if cred:
            cred.access_token_enc = access_enc
            cred.refresh_token_enc = refresh_enc
            s.add(cred)
        else:
            s.add(
                ApiCredentials(
                    user_id=user.id,
                    service="deviantart",
                    access_token_enc=access_enc,
                    refresh_token_enc=refresh_enc,
                )
            )
        await s.commit()

    # 6) уведомим пользователя в TG (не критично если не получится)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": tg_id,
                    "text": "✅ DeviantArt подключён. Можно публиковать!",
                    "parse_mode": "HTML",
                },
            )
    except Exception:
        pass

    # 7) финальная страница
    return HTMLResponse(SUCCESS_HTML, status_code=200)
