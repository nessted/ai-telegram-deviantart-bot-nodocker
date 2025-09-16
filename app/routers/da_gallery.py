from __future__ import annotations

import html
from typing import Dict, List, Set

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.db import async_session
from app.models import User, ApiCredentials
from app.crypto import fernet_decrypt
from app.services.deviantart import DeviantArtClient
from app.services.gallery_prefs import get_galleries, set_galleries
from app.services.autopost_store import ap_set_gallery_ids, ap_get  # для автопоста
from app.user_storage import read_preview  # НОВАЯ система предпросмотра (app/data/post_preview.json)
from app.routers.publish import _prepub_kb as _normal_prepub_kb  # клавиатура обычного предпросмотра

router = Router()


class GalleryStates(StatesGroup):
    picking = State()


def _safe_ack(cb: CallbackQuery):
    try:
        return cb.answer()
    except TelegramBadRequest:
        return None


async def _get_user(tg_id: int, username: str | None) -> User:
    async with async_session() as s:
        r = await s.execute(select(User).where(User.tg_id == tg_id))
        u = r.scalar_one_or_none()
        if not u:
            u = User(tg_id=tg_id, username=username)
            s.add(u)
            await s.commit()
            await s.refresh(u)
        return u


async def _get_da_client_for_user(user_id: int) -> DeviantArtClient | None:
    async with async_session() as s:
        r = await s.execute(
            select(ApiCredentials).where(
                ApiCredentials.user_id == user_id,
                ApiCredentials.service == "deviantart",
            )
        )
        cred = r.scalar_one_or_none()
    if not cred:
        return None
    access = fernet_decrypt(cred.access_token_enc)
    refresh = fernet_decrypt(getattr(cred, "refresh_token_enc", "") or "") if getattr(cred, "refresh_token_enc", None) else None
    return DeviantArtClient(access_token=access, refresh_token=refresh)


def _kb(items: List[tuple[str, str, bool]], offset: int, limit: int, has_more: bool, mode: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for fid, name, selected in items:
        mark = "✅ " if selected else "⬜️ "
        rows.append([InlineKeyboardButton(text=mark + name, callback_data=f"da:toggle:{fid}")])
    nav: List[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"da:page:{max(0, offset - limit)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"da:page:{offset + limit}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="💾 Сохранить выбор", callback_data=f"da:save:{mode}")])
    rows.append([InlineKeyboardButton(text="↩️ Вернуться на страницу предпросмотра", callback_data=f"da:back_preview:{mode}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _preview_actions_kb_custom() -> InlineKeyboardMarkup:
    """Клавиатура предпросмотра для автопоста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗂 Выбрать галерею", callback_data="custom:pick_gallery")],
        [InlineKeyboardButton(text="🚀 Опубликовать на DeviantArt", callback_data="autopost:do_publish")],
        [InlineKeyboardButton(text="🏠 На главную", callback_data="back:menu")],
    ])


async def _show_autopost_preview(cb: CallbackQuery) -> None:
    store = ap_get(cb.from_user.id)
    preview = store.get("last_preview") or ""

    if not preview:
        imgs = store.get("images") or []
        pack = store.get("pack") or {}
        title = pack.get("title") or "Adoptable"
        desc = (pack.get("description") or "")[:2000]
        tags = " ".join((pack.get("hashtags") or [])[:30])
        preview = (
            "<b>DeviantArt — предпросмотр кастомного поста</b>\n"
            f"<b>Кадров в пачке:</b> {len(imgs)}\n"
            f"<b>Title:</b> {html.escape(title)}\n\n"
            "<b>Description:</b>\n"
            f"<code>{html.escape(desc)}</code>\n\n"
            f"<b>Hashtags:</b> {tags}"
        )

    try:
        await cb.message.edit_text(preview, reply_markup=_preview_actions_kb_custom())
    except TelegramBadRequest:
        await cb.message.answer(preview, reply_markup=_preview_actions_kb_custom())


async def _show_normal_preview(cb: CallbackQuery) -> None:
    """Возврат к последнему предпросмотру обычного постинга (из нового JSON)."""
    preview = read_preview(cb.from_user.id)
    try:
        await cb.message.edit_text(preview, reply_markup=_normal_prepub_kb())
    except TelegramBadRequest:
        await cb.message.answer(preview, reply_markup=_normal_prepub_kb())


@router.callback_query(F.data.in_(["da:pick_gallery", "custom:pick_gallery"]))
async def pick_gallery(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    user = await _get_user(cb.from_user.id, cb.from_user.username)
    client = await _get_da_client_for_user(user.id)
    if not client:
        await cb.message.answer("❌ DeviantArt не подключён.")
        return

    try:
        folders = await client.gallery_folders()
    finally:
        await client.aclose()

    mode = "custom" if cb.data.startswith("custom:") else "normal"
    await state.set_state(GalleryStates.picking)
    await state.update_data(mode=mode, raw_results=folders, offset=0, limit=10)

    prefs = get_galleries(user.id)
    selected: Set[str] = set(prefs.get("ids", []))
    names = dict(zip(prefs.get("ids", []), prefs.get("names", [])))
    await state.update_data(sel=selected, names=names)

    await _render_page(cb, state)


async def _render_page(cb: CallbackQuery, state: FSMContext):
    sd = await state.get_data()
    folders = sd.get("raw_results") or {}
    results = folders.get("results", [])
    has_more = bool(folders.get("has_more"))
    offset = int(sd.get("offset") or 0)
    limit = int(sd.get("limit") or 10)

    selected: Set[str] = set(sd.get("sel") or set())
    items: List[tuple[str, str, bool]] = []
    for it in results[offset:offset + limit]:
        fid = it["folderid"]
        name = it["name"]
        items.append((fid, name, fid in selected))

    kb = _kb(items, offset=offset, limit=limit, has_more=has_more, mode=str(sd.get("mode")))
    head = "🗂 Выберите галереи DeviantArt (мультивыбор)."
    if selected:
        head += f"\nВыбрано: {len(selected)}"
    try:
        await cb.message.edit_text(head, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(head, reply_markup=kb)


@router.callback_query(GalleryStates.picking, F.data.startswith("da:page:"))
async def page(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    offset = int(cb.data.split(":")[-1])
    await state.update_data(offset=offset)
    await _render_page(cb, state)


@router.callback_query(GalleryStates.picking, F.data.startswith("da:toggle:"))
async def toggle(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    fid = cb.data.split(":")[-1]
    sd = await state.get_data()
    selected: Set[str] = set(sd.get("sel") or set())
    names: Dict[str, str] = dict(sd.get("names") or {})

    if cb.message and cb.message.reply_markup:
        for row in cb.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data == f"da:toggle:{fid}":
                    clean = (btn.text or "").replace("✅ ", "").replace("⬜️ ", "")
                    names[fid] = clean

    if fid in selected:
        selected.remove(fid)
    else:
        selected.add(fid)

    await state.update_data(sel=selected, names=names)
    await _render_page(cb, state)


@router.callback_query(GalleryStates.picking, F.data.startswith("da:save:"))
async def save(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    sd = await state.get_data()
    mode = str(sd.get("mode"))
    selected: List[str] = list(sd.get("sel") or [])
    names_map: Dict[str, str] = dict(sd.get("names") or {})
    names = [names_map.get(fid, fid) for fid in selected]

    user = await _get_user(cb.from_user.id, cb.from_user.username)
    set_galleries(user.id, selected, names)

    await state.clear()

    if mode == "custom":
        ap_set_gallery_ids(user.id, selected)
        await _show_autopost_preview(cb)
    else:
        await _show_normal_preview(cb)


@router.callback_query(GalleryStates.picking, F.data.startswith("da:back_preview:"))
async def back_preview(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    sd = await state.get_data()
    mode = str(sd.get("mode"))
    await state.clear()

    if mode == "custom":
        await _show_autopost_preview(cb)
    else:
        await _show_normal_preview(cb)
