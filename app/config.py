import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(default="", min_length=1)
    admin_telegram_id: int = Field(default=0)

    tg_api_id: int = Field(default=0)
    tg_api_hash: str = Field(default="")
    tg_session_name: str = Field(default="tg_bot_search")
    tg_phone: str | None = Field(default=None, alias="TG_PHONE")

    db_url: str = Field(default=f"sqlite+aiosqlite:///{BASE_DIR / 'tg_bot_search.db'}")

    min_score: float = 3.0
    geo_required: bool = False
    geo_bonus: float = 2.0

    backfill_limit: int = 50
    lookback_hours: int = 24

    log_level: str = "INFO"
    local_timezone: str = "Europe/Moscow"
    notify_text_limit: int = 900

    def validate_runtime(self) -> None:
        problems = []
        if not self.bot_token:
            problems.append("BOT_TOKEN (токен бота из @BotFather)")
        if not self.admin_telegram_id:
            problems.append("ADMIN_TELEGRAM_ID (ваш id, например через @userinfobot)")
        if not self.tg_api_id or not self.tg_api_hash:
            problems.append("TG_API_ID и TG_API_HASH (с https://my.telegram.org/apps)")
        if problems:
            raise RuntimeError(
                "Не заполнены обязательные настройки: " + ", ".join(problems)
                + ". Скопируйте .env.example в .env и заполните."
            )


def session_file(settings: Settings) -> str:
    d = BASE_DIR / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / settings.tg_session_name)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)