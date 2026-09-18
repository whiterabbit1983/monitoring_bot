import asyncio

from telethon import TelegramClient

from app.config import Settings, configure_logging, session_file


async def main() -> None:
    settings = Settings()
    client = TelegramClient(session_file(settings), settings.tg_api_id, settings.tg_api_hash)
    await client.start(phone=settings.tg_phone or None)
    me = await client.get_me()
    print(f"Авторизация успешна: {me.first_name} @{me.username} (id={me.id})")
    print("Сессия сохранена. Теперь можно запускать бота: python -m app.main")
    await client.disconnect()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())