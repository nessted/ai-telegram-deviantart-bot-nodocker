from __future__ import annotations
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional
from app.config import settings

_f = Fernet(settings.FERNET_KEY.encode("utf-8"))

def fernet_encrypt(s: str) -> str:
    return _f.encrypt(s.encode("utf-8")).decode("utf-8")

def fernet_decrypt(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return _f.decrypt(s.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None
