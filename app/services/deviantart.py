from __future__ import annotations

import os
import asyncio
import time
from typing import Any, Dict, List, Optional, Sequence

import aiohttp
from aiohttp import FormData
from sqlalchemy import select

from app.config import settings
from app.crypto import fernet_encrypt
from app.db import async_session
from app.models import ApiCredentials

DA_API = "https://www.deviantart.com/api/v1/oauth2"
DA_OAUTH = "https://www.deviantart.com/oauth2"


class DeviantArtError(RuntimeError):
    pass


def _as_bool(v: bool) -> str:
    return "true" if bool(v) else "false"


def _extend_form_array(fd: FormData, name: str, values: Optional[Sequence[str]]) -> None:
    """Добавляем массив как name[]"""
    if not values:
        return
    for x in values:
        s = str(x).strip()
        if s:
            fd.add_field(f"{name}[]", s)


def _get_da_client_credentials() -> tuple[str, str]:
    cid = (
        getattr(settings, "DEVIANTART_CLIENT_ID", None)
        or getattr(settings, "DA_CLIENT_ID", None)
        or os.getenv("DA_CLIENT_ID")
        or ""
    )
    csec = (
        getattr(settings, "DEVIANTART_CLIENT_SECRET", None)
        or getattr(settings, "DA_CLIENT_SECRET", None)
        or os.getenv("DA_CLIENT_SECRET")
        or ""
    )
    return cid.strip(), csec.strip()


class DeviantArtClient:
    def __init__(
        self,
        *,
        access_token: Optional[str],
        refresh_token: Optional[str],
        user_id: Optional[int] = None,
        timeout: float = 60.0,
    ):
        self.access_token = (access_token or "").strip()
        self.refresh_token = (refresh_token or "").strip() or None
        self.user_id = user_id
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._refresh_lock = asyncio.Lock()
        self._expires_at: Optional[float] = None

    async def aclose(self):
        return None

    # ---------------- HTTP helpers ----------------
    async def _get_json(self, url: str, headers: Dict[str, str], params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self._timeout, trust_env=False) as sess:
            async with sess.get(url, headers=headers, params=params) as r:
                text = await r.text()
                if r.status // 100 != 2:
                    raise DeviantArtError(f"GET {url} failed: {r.status} {text}")
                return await r.json()

    async def _post_form(self, url: str, headers: Dict[str, str], form: FormData) -> Dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self._timeout, trust_env=False) as sess:
            async with sess.post(url, headers=headers, data=form) as r:
                text = await r.text()
                if r.status // 100 != 2:
                    raise DeviantArtError(f"POST {url} failed: {r.status} {text}")
                return await r.json()

    # ---------------- tokens ----------------
    async def ensure_fresh(self) -> None:
        if self._expires_at and (self._expires_at - time.time() < 120):
            await self._refresh_once()
            return
        try:
            await self.whoami()
        except DeviantArtError:
            await self._refresh_once()

    async def whoami(self) -> Dict[str, Any]:
        if not self.access_token:
            raise DeviantArtError("Empty access token")
        return await self._get_json(f"{DA_API}/user/whoami", headers={"Authorization": f"Bearer {self.access_token}"})

    async def _refresh_once(self) -> None:
        async with self._refresh_lock:
            if not self.refresh_token:
                raise DeviantArtError("Refresh token missing")

            client_id, client_secret = _get_da_client_credentials()
            form = FormData()
            form.add_field("grant_type", "refresh_token")
            form.add_field("client_id", client_id)
            form.add_field("client_secret", client_secret)
            form.add_field("refresh_token", self.refresh_token)

            async with aiohttp.ClientSession(timeout=self._timeout, trust_env=False) as sess:
                async with sess.post(f"{DA_OAUTH}/token", data=form) as r:
                    js = await r.json()
                    if r.status // 100 != 2:
                        raise DeviantArtError(f"OAuth refresh failed: {js}")

            self.access_token = js.get("access_token") or ""
            self.refresh_token = js.get("refresh_token") or self.refresh_token
            expires_in = js.get("expires_in")
            self._expires_at = time.time() + float(expires_in or 3600)

            if self.user_id:
                await self._persist_tokens()

    async def _persist_tokens(self) -> None:
        async with async_session() as s:
            r = await s.execute(
                select(ApiCredentials).where(
                    ApiCredentials.user_id == self.user_id,
                    ApiCredentials.service == "deviantart",
                )
            )
            cred = r.scalar_one_or_none()
            if cred:
                cred.access_token_enc = fernet_encrypt(self.access_token)
                if self.refresh_token:
                    cred.refresh_token_enc = fernet_encrypt(self.refresh_token)
                await s.commit()

    # ---------------- API ----------------
    async def gallery_folders(self) -> Dict[str, Any]:
        await self.ensure_fresh()
        return await self._get_json(
            f"{DA_API}/gallery/folders",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"limit": 50},
        )

    async def stash_submit(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        title: str = "",
        artist_comments: str = "",
        tags: Optional[List[str]] = None,
        is_dirty: bool = False,
        is_ai_generated: bool = True,
        noai: bool = False,
    ) -> Dict[str, Any]:
        def build_form():
            fd = FormData()
            fd.add_field("file", file_bytes, filename=filename, content_type="application/octet-stream")
            fd.add_field("title", title)
            fd.add_field("artist_comments", artist_comments)
            fd.add_field("is_dirty", _as_bool(is_dirty))
            fd.add_field("is_ai_generated", _as_bool(is_ai_generated))
            fd.add_field("noai", _as_bool(noai))
            _extend_form_array(fd, "tags", tags)
            return fd

        await self.ensure_fresh()
        try:
            return await self._post_form(f"{DA_API}/stash/submit", {"Authorization": f"Bearer {self.access_token}"}, build_form())
        except DeviantArtError:
            await self._refresh_once()
            return await self._post_form(f"{DA_API}/stash/submit", {"Authorization": f"Bearer {self.access_token}"}, build_form())

    async def stash_publish(
        self,
        *,
        itemid: str,
        is_mature: bool = False,
        galleryids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        is_ai_generated: bool = True,
        noai: bool = False,
        add_watermark: bool = True,
        display_resolution: int = 3,  # по умолчанию xlarge
        feature: bool = True,
        allow_comments: bool = True,
        allow_free_download: bool = False,
    ) -> Dict[str, Any]:
        def build_form(resolution: int):
            fd = FormData()
            fd.add_field("itemid", str(itemid))
            fd.add_field("is_mature", _as_bool(is_mature))
            fd.add_field("is_ai_generated", _as_bool(is_ai_generated))
            fd.add_field("noai", _as_bool(noai))
            fd.add_field("add_watermark", _as_bool(add_watermark))

            # защита для display_resolution
            res = resolution if resolution in (0, 1, 2, 3) else 2
            fd.add_field("display_resolution", str(res))

            fd.add_field("feature", _as_bool(feature))
            fd.add_field("allow_comments", _as_bool(allow_comments))
            fd.add_field("allow_free_download", _as_bool(allow_free_download))

            # фильтрация galleryids
            if galleryids:
                clean_ids = [gid for gid in galleryids if gid and "-" in gid]
                if clean_ids:
                    _extend_form_array(fd, "galleryids", clean_ids)

            _extend_form_array(fd, "tags", tags)
            return fd

        await self.ensure_fresh()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        print(f"DEBUG publish → resolution={display_resolution}, galleryids={galleryids}, tags={tags}")

        try:
            return await self._post_form(f"{DA_API}/stash/publish", headers, build_form(display_resolution))
        except DeviantArtError as e:
            # fallback на resolution=2
            print(f"⚠️ DeviantArt publish failed with resolution={display_resolution}, retrying with 2. Error: {e}")
            await self._refresh_once()
            return await self._post_form(f"{DA_API}/stash/publish", headers, build_form(2))
