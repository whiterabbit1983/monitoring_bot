import logging

from aiogram import html
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils import format_local_time, text_snippet

log = logging.getLogger("notifier")


class Notifier:
    def __init__(self, bot, admin_chat_id: int, tz_name: str, text_limit: int):
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.tz_name = tz_name
        self.text_limit = text_limit

    def _build_text(self, match, text: str, date, link: str | None) -> str:
        ts = text_snippet(text, self.text_limit)
        header = f"{match.emoji} <b>{html.quote(match.title)}</b>"
        region = "СПб / ЛО — регион упомянут" if match.has_geo else "СПб / ЛО — регион в тексте не указан"
        rows = [
            header,
            "",
            f"<blockquote>{ts}</blockquote>",
            "",
            f"🏷 Категория: <b>{html.quote(match.title)}</b>",
            f"📍 {region}",
            f"🕐 {format_local_time(date, self.tz_name)}",
        ]
        if link:
            rows.append(f"🔗 <a href=\"{link}\">Ссылка на сообщение</a>")
        else:
            rows.append("🔗 Ссылка недоступна")
        return "\n".join(rows)

    def _build_keyboard(self, post_id: int, link: str | None) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👍 Интересно", callback_data=f"fb:{post_id}:yes"),
                    InlineKeyboardButton(text="👎 Не интересно", callback_data=f"fb:{post_id}:no"),
                ],
            ]
        )
        if link:
            kb.inline_keyboard.append([InlineKeyboardButton(text="🔗 Открыть в Telegram", url=link)])
        return kb

    async def send_job_post(self, post, match, text: str, date, link: str | None) -> bool:
        try:
            await self.bot.send_message(
                self.admin_chat_id,
                self._build_text(match, text, date, link),
                reply_markup=self._build_keyboard(post.id, link),
            )
            return True
        except Exception as exc:
            log.error("Не удалось отправить уведомление (post_id=%s): %s", post.id, exc)
            return False