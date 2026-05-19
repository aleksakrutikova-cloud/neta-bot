import os
import sys
import logging

from anthropic import Anthropic

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram.constants import ChatAction

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# UTF-8
os.environ.setdefault("PYTHONUTF8", "1")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ENV
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

# Anthropic
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Conversation states
LEAD_NAME, LEAD_PHONE, LEAD_DESC = range(3)

# Memory
histories = {}
MAX_HISTORY = 20

# System prompt
SYSTEM = """
Ты — Нета, дружелюбный помощник по ביטוח לאומי (Bituah Leumi).

Ты помогаешь русскоязычным жителям Израиля:
- разобраться в письмах
- понять пособия
- пользоваться сайтом и приложением
- найти документы
- понять долги и выплаты

ПРАВИЛА:
- Никогда не запрашивай номер теудат зеут, пароли, коды или банковские данные
- Если пользователь прислал личные данные — предупреди его не делать этого
- Не придумывай законы, суммы или официальные решения
- Используй официальные термины на иврите с переводом
- Отвечай только на русском языке
- Давай пошаговые инструкции
- Используй короткие абзацы и эмодзи
"""

WELCOME = """
👋 *Шалом!*

Я *Нета* — помогаю разобраться в *ביטוח לאומי* простым русским языком.

Выбери тему ниже или просто напиши свой вопрос 👇
"""

# Menu
def menu():
    keyboard = [
        ["🔐 Личный кабинет", "📬 Письма"],
        ["💳 Пособия", "💰 Долги"],
        ["📄 Документы", "🔑 Коды доступа"],
        ["🌐 Сайт и приложение", "⚠️ Частые ошибки"],
        ["👤 Связаться со специалистом"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

# AI request
async def ask_ai(user_id: int, text: str):

    if user_id not in histories:
        histories[user_id] = []

    histories[user_id].append({
        "role": "user",
        "content": text
    })

    if len(histories[user_id]) > MAX_HISTORY:
        histories[user_id] = histories[user_id][-MAX_HISTORY:]

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=800,
            system=SYSTEM,
            messages=histories[user_id],
        )

        reply = response.content[0].text

        histories[user_id].append({
            "role": "assistant",
            "content": reply
        })

        return reply

    except Exception as e:
        logger.error("Anthropic error: %s", e)

        return (
            "⚠️ Что-то пошло не так.\n"
            "Попробуй ещё раз через пару секунд."
        )

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    histories.pop(user_id, None)

    await update.message.reply_text(
        WELCOME,
        parse_mode="Markdown",
        reply_markup=menu()
    )

# RESET
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    histories.pop(user_id, None)

    await update.message.reply_text(
        "🔄 История диалога сброшена.",
        reply_markup=menu()
    )

# Specialist start
async def specialist_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👤 Хорошо!\n\n"
        "Как тебя зовут?",
        reply_markup=ReplyKeyboardRemove()
    )

    return LEAD_NAME

# Main messages
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.effective_user.id

    # typing
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    # AI
    reply = await ask_ai(user_id, text)

    await update.message.reply_text(
        reply,
        parse_mode="Markdown",
        reply_markup=menu()
    )

# Lead name
async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["name"] = update.message.text

    await update.message.reply_text(
        "📱 Напиши свой телефон или Telegram:"
    )

    return LEAD_PHONE

# Lead phone
async def lead_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["phone"] = update.message.text

    await update.message.reply_text(
        "✍️ Кратко опиши свой вопрос:"
    )

    return LEAD_DESC

# Lead desc
async def lead_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    name = context.user_data.get("name", "-")
    phone = context.user_data.get("phone", "-")
    desc = update.message.text

    msg = (
        "🔔 Новый лид\n\n"
        f"👤 Имя: {name}\n"
        f"📱 Контакт: {phone}\n"
        f"❓ Вопрос: {desc}\n\n"
        f"Telegram: @{user.username or '-'}\n"
        f"ID: {user.id}"
    )

    if ADMIN_CHAT_ID:

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=msg
            )

        except Exception as e:
            logger.error("Lead send error: %s", e)

    await update.message.reply_text(
        "✅ Заявка отправлена.\n\n"
        "Специалист скоро свяжется с тобой 👌",
        reply_markup=menu()
    )

    return ConversationHandler.END

# Cancel
async def lead_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👌 Возвращаемся в меню",
        reply_markup=menu()
    )

    return ConversationHandler.END

# MAIN
def main():

    app = Application.builder().token(
        TELEGRAM_TOKEN
    ).build()

    # Conversation
    lead_conv = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex("(?i)специалист|specialist"),
                specialist_start
            )
        ],

        states={

            LEAD_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lead_name
                )
            ],

            LEAD_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lead_phone
                )
            ],

            LEAD_DESC: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lead_desc
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                lead_cancel
            )
        ],
    )

    # Handlers
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("reset", reset)
    )

    app.add_handler(lead_conv)

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle
        )
    )

    logger.info("Neta bot starting...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

# RUN
if __name__ == "__main__":
    main()
