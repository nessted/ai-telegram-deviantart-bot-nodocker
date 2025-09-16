# app/config.py
import os, re
from pathlib import Path
from dotenv import load_dotenv

# грузим .env по абсолютному пути и ПЕРЕЗАПИСЫВАЕМ уже существующие env
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

class Settings:
    BOT_TOKEN: str = (os.getenv("BOT_TOKEN", "") or "").strip()
    WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL") or None
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    PORT: int = int(os.getenv("PORT", "8080"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data.db")
    FERNET_KEY: str = (os.getenv("FERNET_KEY", "") or "").strip()

    # DeviantArt
    DA_CLIENT_ID: str = os.getenv("DA_CLIENT_ID", "")
    DA_CLIENT_SECRET: str = os.getenv("DA_CLIENT_SECRET", "")
    DA_REDIRECT_URI: str = os.getenv("DA_REDIRECT_URI", "http://localhost:8080/oauth/deviantart/callback")

    # OpenAI / LLM
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str | None = os.getenv("OPENAI_API_BASE") or None

    # Optional
    REDIS_URL: str | None = os.getenv("REDIS_URL") or None

    # Image Providers
    TENSORART_SD_MODEL_ID: str | None = os.getenv("TENSORART_SD_MODEL_ID")
    TENSORART_REGION_URL: str = os.getenv("TENSORART_REGION_URL", "https://ap-east-1.tensorart.cloud")
    TENSORART_APP_ID: str | None = os.getenv("TENSORART_APP_ID") or None  # ← добавь это
    TENSORART_TEMPLATE_ID: str | None = os.getenv("TENSORART_TEMPLATE_ID") or None
    REPLICATE_API_TOKEN: str | None = os.getenv("REPLICATE_API_TOKEN") or None
    REPLICATE_MODEL_VERSION: str | None = os.getenv("REPLICATE_MODEL_VERSION") or None

settings = Settings()

# (необязательно, но полезно) ранняя проверка:
if settings.BOT_TOKEN and not re.fullmatch(r"\d+:[\w-]{35}", settings.BOT_TOKEN):
    raise RuntimeError("BOT_TOKEN имеет неверный формат (уберите пробелы/комментарии).")

