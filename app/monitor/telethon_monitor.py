import asyncio
import logging
from datetime import timedelta

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat

from app.config import session_file
from app.db import repo
from app.services.job_service import JobService
from app.utils import utcnow

log = logging.getLogger("monitor")


def parse_reference(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if "t.me/" in s:
        s = s.split("t.me/", 1)[1]
    s = s.lstrip("/@").split("?", 1)[0].rstrip("/")
    return s


def build_link(chat_id: int, message_id: int, username: str | None) -> str | None:
    if username:
        return f"https://t.me/{username}/{message_id}"
    s = str(chat_id)
    if s.startswith("-100"):
        return f"https://t.me/c/{s[4:]}/{message_id}"
    return None


class TelegramMonitor:
    def __init__(self, settings, session_factory, job_service: JobService):
        self.settings = settings
        self.sf = session_factory
        self.job_service = job_service
        self.client = TelegramClient(
            session_file(settings),
            settings.tg_api_id,
            settings.tg_api_hash,
            connection_retries=10,
            retry_delay=2,
            flood_sleep_threshold=60,
        )
        self.watched: dict[int, dict] = {}

    async def start(self) -> None:
        await self.client.start(phone=self.settings.tg_phone or None)
        me = await self.client.get_me()
        log.info("Telethon аккаунт: %s (id=%s)", me.first_name, me.id)
        await self.rehydrate()
        self.client.add_event_handler(self._on_new_message, events.NewMessage())
        await self._backfill_all()
        asyncio.create_task(self._periodic_rehydrate())
        log.info("Мониторинг запущен, каналов: %s", len(self.watched))

    async def stop(self) -> None:
        await self.client.disconnect()

    async def rehydrate(self) -> None:
        channels = await repo.get_active_channels(self.sf)
        self.watched = {
            c.id: {"username": c.username, "title": c.title or str(c.id)} for c in channels
        }

    async def _periodic_rehydrate(self) -> None:
        while True:
            await asyncio.sleep(600)
            try:
                await self.rehydrate()
            except Exception as exc:
                log.warning("rehydrate failed: %s", exc)

    async def _on_new_message(self, event) -> None:
        chat_id = event.chat_id
        info = self.watched.get(chat_id)
        if not info:
            return
        msg = event.message
        text = getattr(msg, "message", None)
        if not text or not text.strip():
            return
        link = build_link(chat_id, msg.id, info["username"])
        await self.job_service.handle_message(
            channel_id=chat_id,
            message_id=msg.id,
            sender_id=msg.sender_id,
            text=text.strip(),
            date=msg.date,
            link=link,
        )

    async def resolve_and_add(self, ref: str):
        parsed = parse_reference(ref)
        if not parsed:
            raise ValueError("Пустая ссылка")
        entity = await self.client.get_entity(parsed)
        if not isinstance(entity, (Channel, Chat)):
            raise ValueError("Это не канал и не группа")
        is_invite_link = parsed.startswith("+") or "joinchat" in parsed
        if is_invite_link:
            try:
                await self.client.join_channel(entity)
                log.info("Присоединились к %s (%s)", getattr(entity, "title", entity.id), entity.id)
            except Exception as exc:
                log.warning("Не удалось вступить по invite-ссылке: %s", exc)
        title = getattr(entity, "title", None) or f"chat {entity.id}"
        username = getattr(entity, "username", None)
        await repo.upsert_channel(self.sf, entity.id, username=username, title=title)
        await self.rehydrate()
        await self._backfill_channel(entity.id)
        return entity, title

    async def remove_channel(self, chat_id: int) -> bool:
        ok = await repo.deactivate_channel(self.sf, chat_id)
        await self.rehydrate()
        return ok

    async def list_channels(self):
        return await repo.get_active_channels(self.sf)

    async def _backfill_all(self) -> None:
        for chat_id in list(self.watched.keys()):
            try:
                await self._backfill_channel(chat_id)
            except Exception as exc:
                log.warning("Backfill канала %s не удался: %s", chat_id, exc)

    async def _backfill_channel(self, chat_id: int) -> None:
        limit = self.settings.backfill_limit
        if limit <= 0:
            return
        cutoff = utcnow() - timedelta(hours=self.settings.lookback_hours)
        info = self.watched.get(chat_id)
        username = info["username"] if info else None
        try:
            msgs = await self.client.get_messages(chat_id, limit=limit)
        except Exception as exc:
            log.warning("Не удалось получить историю %s: %s", chat_id, exc)
            return
        for msg in reversed(msgs):
            if msg.date is None or msg.date.replace(tzinfo=None) < cutoff:
                continue
            text = getattr(msg, "message", None)
            if not text or not text.strip():
                continue
            link = build_link(chat_id, msg.id, username)
            await self.job_service.handle_message(
                channel_id=chat_id,
                message_id=msg.id,
                sender_id=msg.sender_id,
                text=text.strip(),
                date=msg.date,
                link=link,
            )
        log.info("Backfill %s завершён (%s сообщений)", chat_id, len(msgs))