# AI Character Bot → Image → DeviantArt (Local, без Docker)

Каркас бота на **aiogram 3** + мини-сервер **FastAPI** для OAuth DeviantArt.
Работает локально (long polling для Telegram по умолчанию).

## 1) Требования
- Python 3.11+
- Открытый интернет-доступ к API провайдеров
- (Опционально) публичный HTTPS-домен/туннель (ngrok, Cloudflare Tunnel) для DeviantArt OAuth callback

## 2) Установка
```bash
# Клонируйте проект или распакуйте архив
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) Настройка .env
Скопируйте `.env.example` → `.env` и заполните:
- `BOT_TOKEN` — токен Telegram-бота
- `FERNET_KEY` — сгенерируйте:
  ```bash
  python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
  ```
- `DA_CLIENT_ID`, `DA_CLIENT_SECRET` — из кабинета DeviantArt
- `DA_REDIRECT_URI` — URL `https://<ваш-хост>/oauth/deviantart/callback`.
  Для локальной машины можно поднять публичный туннель (ngrok/CF Tunnel) к порту веб-сервера (по умолчанию :8080).
- `OPENAI_API_KEY` — по желанию (иначе включится локальная заглушка для текстов)
- `TENSORART_*` или `REPLICATE_*` — по желанию

> Если не планируете DeviantArt прямо сейчас — можно оставить пустым. Публикация просто не будет доступна.

## 4) Запуск
Откройте **две** консоли (или используйте скрипты ниже):

### Вкладка A — FastAPI (OAuth callback)
```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uvicorn app.web.main:app --host 0.0.0.0 --port 8080
```

### Вкладка B — Telegram-бот (long polling)
```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m app.bot
```

> Если хотите использовать **вебхук**, пропишите `WEBHOOK_URL` в `.env`, откройте порт 8080 наружу и запустите **бот** в режиме webhook (бот сам поставит webhook на старте).

## 5) Быстрый сценарий
1. В Telegram: `/start` → кнопка **«🧬 Создать персонажа»** → выбрать стиль.
2. Бот сгенерирует: идею, заголовок, описание, теги, SD-промпт (с негативом), покажет стоимость/токены (если OpenAI).
3. Нажмите **«🖼 Сгенерировать изображение»** (нужен подключенный провайдер изображений):
   - `/add_tensorart` и пришлите свой API ключ (сохранится шифровано), или
   - добавьте Replicate токен (см. код; опционально).
4. Для публикации на DeviantArt:
   - `/connect_deviantart` → перейдите по ссылке (через публичный домен) → подтвердите доступ → вернитесь в бота.
   - Нажмите **«🚀 Опубликовать на DeviantArt»**.
5. Историю и статусы см. в сообщениях; база — `SQLite` (файл `data.db`).

## 6) Скрипты запуска
- **Linux/macOS**:
  - `scripts/start_web.sh` — поднимает FastAPI на :8080
  - `scripts/start_bot.sh` — запускает бота (long polling)
  - `scripts/start_all.sh` — запускает оба процесса в фоне (использует `&`)
- **Windows (PowerShell)**:
  - `scripts/start_web.ps1`
  - `scripts/start_bot.ps1`
  - `scripts/start_all.ps1` — стартует два процесса параллельно

## 7) Добавление личных токенов пользователей
В чате с ботом:
- `/add_openai` → отправьте `sk-...`
- `/add_tensorart` → отправьте `ta_...` или `sk_...` нужного провайдера
- `/connect_deviantart` → пройдите OAuth по ссылке
Токены каждого пользователя шифруются **Fernet** и хранятся в БД.

## 8) Обновление конфигурации
Изменили `.env`? Просто перезапустите процессы. БД сохраняется в `data.db` (SQLite).

## 9) Полезно знать
- Если `WEBHOOK_URL` пуст — используется **long polling** (проще в локальных сетях).
- В проде рекомендуются: Postgres/Redis и менеджер процессов (pm2/systemd/NSSM), но это не обязательно.
- API-схемы провайдеров меняются: при ошибках сравните параметры в `app/services/*` с их актуальной документацией.

Удачной генерации! ✨
