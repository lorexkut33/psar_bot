import logging
import os
from datetime import datetime, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from dotenv import load_dotenv
load_dotenv()

import os
TOKEN = os.getenv("BOT_TOKEN")


# ================== НАСТРОЙКИ ==================

TOKEN = os.getenv("BOT_TOKEN")
# ================== ЛОГИ ==================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("PsarBot")

# ================== ХРАНИЛИЩЕ ==================

muted_users = {}  # user_id: {chat_id, until, name}

# ================== ПРАВА ==================

# 🔒 Запрещаем ТОЛЬКО отправку сообщений и медиа
MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)


# 🔓 Возвращаем ВСЕ стандартные права
UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_send_polls=True,

)


# ================== ВСПОМОГАТЕЛЬНОЕ ==================

def parse_time(time_str: str) -> int:
    if time_str.endswith("d"):
        return int(time_str[:-1]) * 86400
    if time_str.endswith("h"):
        return int(time_str[:-1]) * 3600
    if time_str.endswith("m"):
        return int(time_str[:-1]) * 60
    return int(time_str)

# ================== КОМАНДЫ ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐕 Я Псарь с намордником 🤐\n\n"
        "Команды:\n"
        "— Ответом на сообщение:\n"
        "  /block 5m\n"
        "  /unblock\n\n"
        "— /muted — список замученных"
    )

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("🐕 Только для групп")
        return

    member = await chat.get_member(user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("🐕 Только администратор может надевать намордник")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("🐕 Используй команду ОТВЕТОМ на сообщение")
        return

    if not context.args:
        await update.message.reply_text("❌ Укажи время: 30 | 5m | 2h | 1d")
        return

    target = update.message.reply_to_message.from_user

    if target.id == context.bot.id:
        await update.message.reply_text("🐕 Я вне юрисдикции")
        return

    if target.id == user.id:
        await update.message.reply_text("🐕 Самоистязание запрещено")
        return

    try:
        duration = parse_time(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени")
        return

    until = datetime.utcnow() + timedelta(seconds=duration)

    await context.bot.restrict_chat_member(
        chat_id=chat.id,
        user_id=target.id,
        permissions=MUTE_PERMISSIONS,
        until_date=until,
    )

    name = target.username or target.first_name

    muted_users[target.id] = {
        "chat_id": chat.id,
        "until": until,
        "name": name,
    }

    context.job_queue.run_once(
        auto_unblock,
        when=duration,
        data={"chat_id": chat.id, "user_id": target.id},
    )

    logger.info(
        f"MUTE | admin={user.id} target={target.id} "
        f"time={duration}s chat={chat.id}"
    )

    await update.message.reply_text(
        f"🐕 @{name} в наморднике 🤐\n"
        f"⏱ На {context.args[0]}"
    )

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not update.message.reply_to_message:
        await update.message.reply_text("🐕 Ответь на сообщение пользователя")
        return

    member = await chat.get_member(user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("🐕 Только администратор")
        return

    target = update.message.reply_to_message.from_user

    await context.bot.restrict_chat_member(
        chat_id=chat.id,
        user_id=target.id,
        permissions=UNMUTE_PERMISSIONS,
    )

    muted_users.pop(target.id, None)

    logger.info(
        f"UNMUTE | admin={user.id} target={target.id} chat={chat.id}"
    )

    await update.message.reply_text(
        f"🐕 @{target.username or target.first_name} свободен 🐕"
    )

async def muted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.utcnow()

    items = [
        f"👤 @{v['name']} — осталось {(v['until'] - now).seconds // 60} мин"
        for v in muted_users.values()
        if v["chat_id"] == chat_id and v["until"] > now
    ]

    if not items:
        await update.message.reply_text("🐕 В намордниках никого нет")
        return

    await update.message.reply_text("🐕 В намордниках:\n\n" + "\n".join(items))

# ================== АВТОРАЗМУТ ==================

async def auto_unblock(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=UNMUTE_PERMISSIONS,
        )
        muted_users.pop(user_id, None)
        logger.info(f"AUTO-UNMUTE | user={user_id} chat={chat_id}")
    except Exception as e:
        logger.error(f"AUTO-UNMUTE ERROR | {e}")

# ================== ЗАПУСК ==================

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("muted", muted))

    logger.info("🐕 Псарь запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
