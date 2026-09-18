from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import html


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_local_time(dt, tz_name: str) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%d.%m.%Y %H:%M")


def text_snippet(text: str, limit: int) -> str:
    t = text.strip()
    if len(t) > limit:
        t = t[:limit].rstrip() + "…"
    return html.quote(t)