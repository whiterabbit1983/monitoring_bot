import logging
from datetime import datetime

from app.classification.classifier import classify
from app.db import repo

log = logging.getLogger("job_service")


class JobService:
    def __init__(self, settings, session_factory, notifier):
        self.settings = settings
        self.sf = session_factory
        self.notifier = notifier

    async def handle_message(
        self,
        *,
        channel_id: int,
        message_id: int,
        sender_id: int | None,
        text: str,
        date: datetime,
        link: str | None,
    ) -> None:
        text = (text or "").strip()
        if not text:
            return

        raw = await repo.insert_raw_message(
            self.sf,
            channel_id=channel_id,
            message_id=message_id,
            sender_id=sender_id,
            text=text,
            date=date,
            link=link,
        )
        if raw is None:
            return

        matches = classify(
            text,
            min_score=self.settings.min_score,
            geo_required=self.settings.geo_required,
            geo_bonus=self.settings.geo_bonus,
        )
        if not matches:
            return

        for match in matches:
            post = await repo.create_job_post(self.sf, raw.id, match)
            if post is None:
                continue
            sent = await self.notifier.send_job_post(post, match, text, date, link)
            if sent:
                await repo.set_post_notified(self.sf, post.id)
                log.info(
                    "Заявка: category=%s score=%s channel=%s msg=%s",
                    match.category_id, match.score, channel_id, message_id,
                )