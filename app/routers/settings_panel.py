from __future__ import annotations

import json
import logging
from contextlib import suppress
from pathlib import Path
from typing import Optional, Tuple

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

# --- keyboards (пробуем оба варианта импорта) ---
try:
    from app.keyboards import settings_main_kb, sizes_kb, steps_kb, cfg_kb  # type: ignore
except Exception:
    from keyboards import settings_main_kb, sizes_kb, steps_kb, cfg_kb  # type: ignore

log = logging.getLogger(__name__)
router = Router()

# ==============================
#   ХРАНИЛИЩЕ НАСТРОЕК ПОЛЬЗОВАТЕЛЯ
#   1) Пробуем БД (SessionLocal + UserSettings)
#   2) Если падает/async-движок — фоллбек в JSON-файл
# ==============================

_DB_AVAILABLE = False
SessionLocal = None
UserSettings = None

# 1) Пытаемся найти SessionLocal в типичных местах
for path in ("app.db", "app.database", "db", "database", "app.core.db"):
    try:
        mod = __import__(path, fromlist=["*"])
        if hasattr(mod, "SessionLocal"):
            SessionLocal = getattr(mod, "SessionLocal")
            _DB_AVAILABLE = True
            break
        if hasattr(mod, "engine"):
            # есть engine, но нет SessionLocal — попробуем собрать сами
            from sqlalchemy.orm import sessionmaker  # type: ignore
            SessionLocal = sessionmaker(bind=mod.engine, autoflush=False, autocommit=False)  # type: ignore
            _DB_AVAILABLE = True
            break
    except Exception:
        pass

# 2) Пытаемся найти модель UserSettings
if _DB_AVAILABLE:
    for path in (
        "app.models",
        "app.database.models",
        "models",
        "database.models",
        "app.models.user_settings",
    ):
        try:
            mod_m = __import__(path, fromlist=["*"])
            if hasattr(mod_m, "UserSettings"):
                UserSettings = getattr(mod_m, "UserSettings")
                break
        except Exception:
            pass
    if UserSettings is None:
        # Модель не нашли — откатываемся
        _DB_AVAILABLE = False
        SessionLocal = None

# 3) JSON-фоллбек
SETTINGS_JSON = Path(__file__).resolve().parent.parent / "user_settings.json"

def _json_load() -> dict:
    if SETTINGS_JSON.exists():
        try:
            return json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _json_save(d: dict) -> None:
    SETTINGS_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- Утилиты Telegram ----------

async def _safe_ack(cb: CallbackQuery, text: str | None = None) -> None:
    # моментальный ACK — не ловим "query is too old"
    with suppress(TelegramBadRequest):
        await cb.answer(text=text, cache_time=1)

def _clamp_steps(v: int) -> int:
    return max(1, min(int(v), 20))

def _clamp_cfg(v: float) -> float:
    return max(1.0, min(float(v), 10.0))

def _parse_size(s: str) -> Optional[Tuple[int, int]]:
    if s == "768x1152":
        return (768, 1152)
    if s == "1024x1024":
        return (1024, 1024)
    return None

# ---------- Доступ к настройкам пользователя ----------

def _get_settings(user_id: int) -> dict:
    """
    dict: {width, height, steps, cfg_scale}
    Источник: БД (если работает) или JSON (фоллбек).
    """
    global _DB_AVAILABLE
    if _DB_AVAILABLE:
        try:
            with SessionLocal() as db:  # type: ignore
                us = db.query(UserSettings).filter_by(user_id=user_id).first()
                if not us:
                    us = UserSettings(
                        user_id=user_id,
                        width=768, height=1152,
                        steps=20, cfg_scale=4.0,
                    )
                    db.add(us)
                    db.commit()
                    db.refresh(us)
                return {
                    "width": us.width,
                    "height": us.height,
                    "steps": us.steps,
                    "cfg_scale": float(us.cfg_scale),
                }
        except Exception as e:
            # Если это async-движок/AsyncSession — падаем сюда.
            log.warning("DB access failed in _get_settings (%s). Fallback to JSON.", type(e).__name__)
            _DB_AVAILABLE = False  # не мучаемся дальше, используем JSON
            return _get_settings(user_id)

    # JSON fallback
    data = _json_load()
    return data.get(str(user_id)) or {"width": 768, "height": 1152, "steps": 20, "cfg_scale": 4.0}

def _set_settings(user_id: int, **kwargs) -> None:
    """
    Обновляет поля в источнике (БД или JSON).
    """
    global _DB_AVAILABLE
    if _DB_AVAILABLE:
        try:
            with SessionLocal() as db:  # type: ignore
                us = db.query(UserSettings).filter_by(user_id=user_id).first()
                if not us:
                    us = UserSettings(
                        user_id=user_id,
                        width=768, height=1152,
                        steps=20, cfg_scale=4.0,
                    )
                    db.add(us)
                    db.flush()
                for k, v in kwargs.items():
                    if hasattr(us, k):
                        setattr(us, k, v)
                db.commit()
            return
        except Exception as e:
            log.warning("DB access failed in _set_settings (%s). Fallback to JSON.", type(e).__name__)
            _DB_AVAILABLE = False  # переключаемся на JSON

    # JSON fallback
    data = _json_load()
    u = data.get(str(user_id)) or {"width": 768, "height": 1152, "steps": 20, "cfg_scale": 4.0}
    u.update(kwargs)
    data[str(user_id)] = u
    _json_save(data)

# ---------- Хэндлеры ----------

@router.callback_query(F.data == "settings:open")
async def settings_open(cb: CallbackQuery):
    await _safe_ack(cb)
    s = _get_settings(cb.from_user.id)
    cur = f"Текущие: {s.get('width', 512)}×{s.get('height', 512)}, steps={s.get('steps', 20)}, cfg={s.get('cfg_scale', 7.5):.1f}"
    await cb.message.edit_text(
        "⚙️ Настройки генерации\n\n"
        "• Размер: 768×1152 или 1024×1024\n"
        "• Steps: до 20\n"
        "• CFG Scale: до 10\n\n"
        f"{cur}",
        reply_markup=settings_main_kb(),
    )

@router.callback_query(F.data == "settings:size")
async def settings_size(cb: CallbackQuery):
    await _safe_ack(cb)
    await cb.message.edit_text("📐 Выбери размер:", reply_markup=sizes_kb())

@router.callback_query(F.data.startswith("size:"))
async def set_size(cb: CallbackQuery):
    await _safe_ack(cb)
    val = cb.data.split(":", 1)[1]
    parsed = _parse_size(val)
    if not parsed:
        await cb.message.edit_text("Неверный размер.", reply_markup=sizes_kb())
        return
    w, h = parsed
    _set_settings(cb.from_user.id, width=w, height=h)
    await cb.message.edit_text(f"✅ Размер сохранён: {w}×{h}", reply_markup=settings_main_kb())

@router.callback_query(F.data == "settings:steps")
async def settings_steps(cb: CallbackQuery):
    await _safe_ack(cb)
    await cb.message.edit_text("🧭 Выбери количество шагов (≤20):", reply_markup=steps_kb())

@router.callback_query(F.data.startswith("steps:"))
async def set_steps(cb: CallbackQuery):
    await _safe_ack(cb)
    raw = cb.data.split(":", 1)[1]
    try:
        steps = _clamp_steps(int(raw))
    except ValueError:
        await cb.message.edit_text("Укажи число.", reply_markup=steps_kb())
        return
    _set_settings(cb.from_user.id, steps=steps)
    await cb.message.edit_text(f"✅ Steps сохранены: {steps}", reply_markup=settings_main_kb())

@router.callback_query(F.data == "settings:cfg")
async def settings_cfg(cb: CallbackQuery):
    await _safe_ack(cb)
    await cb.message.edit_text("🎚 Выбери CFG Scale (≤10):", reply_markup=cfg_kb())

@router.callback_query(F.data.startswith("cfg:"))
async def set_cfg(cb: CallbackQuery):
    await _safe_ack(cb)
    raw = cb.data.split(":", 1)[1]
    try:
        cfg = _clamp_cfg(float(raw))
    except ValueError:
        await cb.message.edit_text("Укажи число.", reply_markup=cfg_kb())
        return
    _set_settings(cb.from_user.id, cfg_scale=cfg)
    await cb.message.edit_text(f"✅ CFG сохранён: {cfg:g}", reply_markup=settings_main_kb())

@router.callback_query(F.data == "back:settings")
async def back_settings(cb: CallbackQuery):
    await _safe_ack(cb)
    await cb.message.edit_text("⚙️ Настройки генерации", reply_markup=settings_main_kb())
