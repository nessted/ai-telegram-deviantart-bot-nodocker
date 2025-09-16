from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

SETTINGS_JSON = Path(__file__).resolve().parent / "user_settings.json"


def set_da_galleries(user_id: int, ids: List[str], names: List[str]) -> None:
    """Сохраняем выбранные галереи для обычных постов"""
    data: Dict[str, Dict] = {}
    if SETTINGS_JSON.exists():
        try:
            data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
    data[str(user_id)] = {"ids": ids, "names": names}
    SETTINGS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_da_galleries(user_id: int) -> Dict[str, List[str]]:
    """Загружаем галереи для обычных постов"""
    if SETTINGS_JSON.exists():
        try:
            data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
            return data.get(str(user_id), {})
        except Exception:
            return {}
    return {}
