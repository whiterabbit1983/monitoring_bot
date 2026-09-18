import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message, User

from app.db import repo
from app.monitor.telethon_monitor import parse_reference

log = logging.getLogger("bot")
router = Router()

HELP_TEXT = (
    "Команды:\n"
    "/start — запуск\n"
    "/help — справка\n"
    "/list — отслеживаемые каналы и группы\n"
    "/add <username|ссылка> — добавить канал/группу\n"
    "/remove <id|username> — убрать из мониторинга\n"
    "/stats — статистика\n\n"
    "Уведомления о подходящих заявках приходят ниже, с кнопками «Интересно / Не интересно»."
)


def is_admin(user: User | None, settings) -> bool:
    return bool(user) and user.id == settings.admin_telegram_id


@router.message(Command("start"))
async def cmd_start(message: Message, settings) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "Привет! Это бот-мониторинг заявок.\n"
        "Отслеживаю выбранные каналы/группы по СПб и ЛО и присылаю сюда подходящие заявки.\n\n"
        + HELP_TEXT
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(HELP_TEXT)


@router.message(Command("list"))
async def cmd_list(message: Message, settings, monitor) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    channels = await monitor.list_channels()
    if not channels:
        await message.answer("Пока ничего не отслеживается. Добавьте канал через /add.")
        return
    lines = []
    for ch in channels:
        un = f"@{ch.username}" if ch.username else "—"
        lines.append(f"• {ch.title} ({un}) — <code>{ch.id}</code>")
    await message.answer("Отслеживаемые каналы/группы:\n" + "\n".join(lines))


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, settings, monitor) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    ref = (command.args or "").strip()
    if not ref:
        await message.answer("Использование: /add @username, t.me/username или invite-ссылка")
        return
    try:
        entity, title = await monitor.resolve_and_add(ref)
    except Exception as exc:
        log.warning("add %s failed: %s", ref, exc)
        await message.answer(f"Не удалось добавить «{ref}»: {exc}")
        return
    await message.answer(f"✅ Добавлено: {title} (<code>{entity.id}</code>)\nИстория за сутки просканирована.")


@router.message(Command("remove"))
async def cmd_remove(message: Message, command: CommandObject, settings, monitor) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Использование: /remove <id|username>")
        return
    if arg.lstrip("-").isdigit():
        chat_id = int(arg)
    else:
        try:
            entity = await monitor.client.get_entity(parse_reference(arg))
            chat_id = entity.id
        except Exception as exc:
            await message.answer(f"Не удалось найти «{arg}»: {exc}")
            return
    ok = await monitor.remove_channel(chat_id)
    await message.answer(f"{'Удалено' if ok else 'Не найдено'} (chat_id={chat_id})")


@router.message(Command("stats"))
async def cmd_stats(message: Message, settings, sf) -> None:
    if not is_admin(message.from_user, settings):
        await message.answer("Доступ запрещён.")
        return
    st = await repo.get_statistics(sf)
    await message.answer(
        "📊 Статистика:\n"
        f"• Активных каналов: <b>{st['channels']}</b>\n"
        f"• Сообщений обработано: <b>{st['raw_total']}</b> (за сутки: {st['raw_24h']})\n"
        f"• Заявок найдено: <b>{st['posts_total']}</b> (за сутки: {st['posts_24h']})\n"
        f"• Оценки: 👍 {st['feedback_yes']} / 👎 {st['feedback_no']}"
    )


@router.callback_query(F.data.startswith("fb:"))
async def on_feedback(callback: CallbackQuery, settings, sf) -> None:
    if not is_admin(callback.from_user, settings):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    try:
        _, post_id_s, value = callback.data.split(":")
        post_id = int(post_id_s)
    except (ValueError, TypeError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    post = await repo.set_feedback(sf, post_id, value)
    if post is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    stamp = "👍 Интересно" if value == "yes" else "👎 Не интересно"
    new_text = (callback.message.html_text or "") + f"\n\n<i>Ваша оценка: {stamp}</i>"
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    log.info("Оценка post=%s: %s", post_id, value)