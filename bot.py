import os, sys, logging

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
logging.basicConfig(handlers=[handler], level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

import anthropic
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ["TELEGRAM_TOKEN"]
KEY = os.environ["ANTHROPIC_API_KEY"]
ADMIN = os.environ.get("ADMIN_CHAT_ID", "")

ai = anthropic.Anthropic(api_key=KEY)
MODEL = "claude-haiku-4-5"
chats = {}

SYS = """You are Neta, a helpful assistant for Russian-speaking residents of Israel.
Help them understand Bituah Leumi (National Insurance Institute of Israel).
Always reply in Russian language only.

Current year is 2026. Benefit amounts change frequently - always tell users to verify current amounts at btl.gov.il

PAGINATION RULES - follow strictly:
- Maximum 5 steps per message
- If the full answer needs more than 5 steps, show steps 1-5 and end with:
  "Нажми 'Продолжить' чтобы увидеть следующие шаги."
- When user sends "Продолжить" - continue from where you stopped
- Always complete the current step fully before stopping
- Never cut a step in the middle

FORMATTING RULES:
- No markdown symbols: no **, no ##, no ###, no ---, no *, no _
- Plain text only
- Numbered steps: 1. 2. 3.
- Dashes for sub-points: -
- No emojis

CONTENT RULES:
- Never request ID numbers, passwords or banking details
- Always remind: you do not replace official bituah leumi advice
- Use Hebrew terms with Russian translation in brackets
- Be concise and clear"""

MENU = ReplyKeyboardMarkup([
    ["Личный кабинет", "Письма"],
    ["Пособия и выплаты", "Долги"],
    ["Документы", "Коды доступа"],
    ["Сайт и приложение", "Частые ошибки"],
    ["Продолжить", "Связаться со специалистом"]
], resize_keyboard=True)

async def start(u: Update, _):
    chats.pop(u.effective_user.id, None)
    await u.message.reply_text(
        "Шалом! Я Нета — помогаю разобраться в ביטוח לאומי на русском языке.\n\nВыбери тему или напиши вопрос:",
        reply_markup=MENU
    )

async def msg(u: Update, ctx):
    uid = u.effective_user.id
    text = u.message.text

    if uid not in chats:
        chats[uid] = []

    chats[uid].append({"role": "user", "content": text})
    if len(chats[uid]) > 20:
        chats[uid] = chats[uid][-20:]

    await ctx.bot.send_chat_action(u.effective_chat.id, "typing")

    try:
        r = ai.messages.create(
            model=MODEL,
            max_tokens=1200,
            system=SYS,
            messages=chats[uid]
        )
        reply = r.content[0].text
        chats[uid].append({"role": "assistant", "content": reply})
        await u.message.reply_text(reply, reply_markup=MENU)
    except Exception as ex:
        logger.error("Error: %s", repr(ex))
        await u.message.reply_text(
            "Что-то пошло не так. Попробуй ещё раз.",
            reply_markup=MENU
        )

def main():
    logger.info("Starting Neta bot, model: %s", MODEL)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
