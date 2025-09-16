from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

CUSTOM_JSON = Path(__file__).resolve().parent / "user_settings_custom.json"

def read_custom_data(user_id: int) -> Dict[str, Any]:
    """Чтение данных кастомных постов из user_settings_custom.json"""
    if not CUSTOM_JSON.exists():
        return {}
    try:
        data = json.loads(CUSTOM_JSON.read_text(encoding="utf-8") or "{}")
        return data.get(str(user_id), {}) or {}
    except Exception:
        return {}
...

def save_custom_data(user_id: int, obj: Dict[str, Any]) -> None:
    """Сохранение данных кастомных постов в user_settings_custom.json"""
    data: Dict[str, Any] = {}
    if CUSTOM_JSON.exists():
        try:
            data = json.loads(CUSTOM_JSON.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
    data[str(user_id)] = obj
    CUSTOM_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def save_custom_preview(user_id: int, preview_text: str) -> None:
    """Сохраняет последний предпросмотр кастомного поста"""
    obj = read_custom_data(user_id)
    obj["last_preview_text"] = preview_text
    save_custom_data(user_id, obj)

def read_custom_preview(user_id: int) -> str:
    """
    Возвращает последний сохранённый предпросмотр для кастомных постов
    из user_settings_custom.json (ключ last_preview_text).
    """
    data = read_custom_data(user_id)
    return str(data.get("last_preview_text", "❌ Предпросмотр не найден."))
