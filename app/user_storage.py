from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Старый общий файл с настройками пользователя (оставляем как есть для совместимости других функций проекта)
USER_SETTINGS_JSON = BASE_DIR / "user_settings.json"

# НОВЫЙ файл исключительно для предпросмотра обычного постинга
POST_PREVIEW_JSON = DATA_DIR / "post_preview.json"


# ---------------- Общие данные пользователя (как было) ----------------
def read_user_data(user_id: int) -> Dict[str, Any]:
    """Чтение настроек юзера из user_settings.json (для совместимости с остальным кодом)."""
    if not USER_SETTINGS_JSON.exists():
        return {}
    try:
        data = json.loads(USER_SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
        return data.get(str(user_id), {}) or {}
    except Exception:
        return {}


def save_user_data(user_id: int, obj: Dict[str, Any]) -> None:
    """Сохранение настроек юзера в user_settings.json (для совместимости)."""
    data: Dict[str, Any] = {}
    if USER_SETTINGS_JSON.exists():
        try:
            data = json.loads(USER_SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
    data[str(user_id)] = obj
    USER_SETTINGS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- НОВАЯ система предпросмотра ----------------
def _read_preview_db() -> Dict[str, Any]:
    if not POST_PREVIEW_JSON.exists():
        return {}
    try:
        return json.loads(POST_PREVIEW_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _write_preview_db(obj: Dict[str, Any]) -> None:
    POST_PREVIEW_JSON.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def save_preview(user_id: int, preview_text: str) -> None:
    """
    Сохраняет последний предпросмотр для обычного постинга в новый файл app/data/post_preview.json.
    Формат:
    {
      "<user_id>": {
        "last_preview_text": "..."
      }
    }
    """
    db = _read_preview_db()
    user_obj = db.get(str(user_id)) or {}
    user_obj["last_preview_text"] = str(preview_text or "")
    db[str(user_id)] = user_obj
    _write_preview_db(db)


def read_preview(user_id: int) -> str:
    """
    Возвращает последний сохранённый предпросмотр обычного постинга
    из нового файла app/data/post_preview.json.
    """
    db = _read_preview_db()
    obj = db.get(str(user_id)) or {}
    return str(obj.get("last_preview_text", "❌ Предпросмотр не найден."))
