import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from app.routers import da_gallery
from app.config import settings
from app.db import init_db
from app.routers import start, profile, generation, publish
from app.services.queue import start_workers
from app.routers import da_diag
from app.routers import settings_panel
from app.routers import autopost


# Если хочешь — можно убрать, т.к. .env уже грузится в app/config.py
# from dotenv import load_dotenv
# load_dotenv()

# Создаём один экземпляр бота с корректным способом задания parse_mode (aiogram 3.7+)
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# Диспетчер и роутеры
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(start.router)
dp.include_router(profile.router)
dp.include_router(settings_panel.router)
dp.include_router(generation.router)
dp.include_router(publish.router)
dp.include_router(da_diag.router) 
dp.include_router(da_gallery.router)
dp.include_router(autopost.router)

async def main():
    # Инициализация БД и фоновых воркеров
    await init_db()
    start_workers(3)

    if settings.WEBHOOK_URL:
        # ------ РЕЖИМ ВЕБХУКА ------
        # Регистрируем aiohttp-приложение через AppRunner/TCPSite (без web.run_app!)
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        # Ставим вебхук (и очищаем очередь апдейтов)
        await bot.set_webhook(
            url=settings.WEBHOOK_URL + settings.WEBHOOK_PATH,
            drop_pending_updates=True,
        )

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=settings.PORT)
        await site.start()

        # Держим процесс живым
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            await bot.session.close()

    else:
        # ------ РЕЖИМ LONG POLLING (дефолт и твой текущий сценарий) ------
        await bot.delete_webhook(drop_pending_updates=True)
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
            )
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
