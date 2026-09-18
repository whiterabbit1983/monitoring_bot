import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import Channel, JobPost, RawMessage
from app.utils import utcnow

log = logging.getLogger("repo")


async def get_active_channels(sf) -> list[Channel]:
    async with sf() as s:
        res = await s.execute(select(Channel).where(Channel.is_active).order_by(Channel.added_at))
        return list(res.scalars().all())


async def upsert_channel(sf, chat_id: int, *, username: str | None, title: str | None) -> Channel:
    async with sf() as s:
        row = await s.get(Channel, chat_id)
        if row is None:
            row = Channel(id=chat_id, username=username, title=title, is_active=True)
            s.add(row)
        else:
            row.username = username
            row.title = title
            row.is_active = True
        await s.commit()
        await s.refresh(row)
        return row


async def deactivate_channel(sf, chat_id: int) -> bool:
    async with sf() as s:
        row = await s.get(Channel, chat_id)
        if row is None:
            return False
        row.is_active = False
        await s.commit()
        return True


async def insert_raw_message(
    sf,
    *,
    channel_id: int,
    message_id: int,
    sender_id: int | None,
    text: str,
    date: datetime,
    link: str | None,
) -> RawMessage | None:
    async with sf() as s:
        row = RawMessage(
            channel_id=channel_id,
            message_id=message_id,
            sender_id=sender_id,
            text=text,
            date=date,
            link=link,
        )
        ch = await s.get(Channel, channel_id)
        if ch is not None:
            ch.last_message_id = message_id
            ch.last_checked_at = utcnow()
        s.add(row)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return None
        await s.refresh(row)
        return row


async def create_job_post(sf, raw_message_id: int, match) -> JobPost | None:
    async with sf() as s:
        row = JobPost(
            raw_message_id=raw_message_id,
            category=match.category_id,
            score=match.score,
            matched={"patterns": match.matched_patterns, "geo": match.has_geo},
            status="new",
        )
        s.add(row)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return None
        await s.refresh(row)
        return row


async def set_post_notified(sf, post_id: int) -> None:
    async with sf() as s:
        row = await s.get(JobPost, post_id)
        if row is not None:
            row.notified_at = utcnow()
            await s.commit()


async def set_feedback(sf, post_id: int, value: str) -> JobPost | None:
    async with sf() as s:
        row = await s.get(JobPost, post_id)
        if row is None:
            return None
        row.feedback = value
        row.feedback_at = utcnow()
        await s.commit()
        await s.refresh(row)
        return row


async def get_statistics(sf) -> dict:
    now = utcnow()
    day_ago = now - timedelta(hours=24)
    async with sf() as s:
        channels = (await s.execute(select(func.count()).select_from(Channel).where(Channel.is_active))).scalar()
        raw_total = (await s.execute(select(func.count()).select_from(RawMessage))).scalar()
        raw_24h = (
            await s.execute(select(func.count()).select_from(RawMessage).where(RawMessage.created_at >= day_ago))
        ).scalar()
        posts_total = (await s.execute(select(func.count()).select_from(JobPost))).scalar()
        posts_24h = (
            await s.execute(select(func.count()).select_from(JobPost).where(JobPost.created_at >= day_ago))
        ).scalar()
        fb_yes = (
            await s.execute(select(func.count()).select_from(JobPost).where(JobPost.feedback == "yes"))
        ).scalar()
        fb_no = (
            await s.execute(select(func.count()).select_from(JobPost).where(JobPost.feedback == "no"))
        ).scalar()
    return {
        "channels": channels,
        "raw_total": raw_total,
        "raw_24h": raw_24h,
        "posts_total": posts_total,
        "posts_24h": posts_24h,
        "feedback_yes": fb_yes,
        "feedback_no": fb_no,
    }