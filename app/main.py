import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot import handlers
from app.config import Settings, configure_logging
from app.db.base import Base, create_engine, create_session_factory
from app.monitor.telethon_monitor import TelegramMonitor
from app.services.job_service import JobService
from app.services.notifier import Notifier

log = logging.getLogger("main")

BOT_COMMANDS = [
    BotCommand(command="start", description="Запуск"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="list", description="Отслеживаемые каналы"),
    BotCommand(command="add", description="Добавить канал/группу"),
    BotCommand(command="remove", description="Убрать канал/группу"),
    BotCommand(command="stats", description="Статистика"),
]


def build_dispatcher(settings, session_factory, monitor) -> Dispatcher:
    dp = Dispatcher()
    dp["settings"] = settings
    dp["sf"] = session_factory
    dp["monitor"] = monitor
    dp.include_router(handlers.router)
    return dp


async def worker_monitor(monitor: TelegramMonitor) -> None:
    await monitor.client.run_until_disconnected()


async def main() -> None:
    settings = Settings()
    settings.validate_runtime()
    configure_logging(settings.log_level)

    engine = create_engine(settings.db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    notifier = Notifier(bot, settings.admin_telegram_id, settings.local_timezone, settings.notify_text_limit)
    job_service = JobService(settings, session_factory, notifier)
    monitor = TelegramMonitor(settings, session_factory, job_service)

    try:
        await monitor.start()
        await bot.set_my_commands(BOT_COMMANDS)
        dp = build_dispatcher(settings, session_factory, monitor)
        await asyncio.gather(
            dp.start_polling(bot),
            worker_monitor(monitor),
        )
    finally:
        await monitor.stop()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено.")