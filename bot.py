import os, sys, logging

# Fix encoding BEFORE anything else
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Fix logging encoding
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

SYS = "You are Neta, a helpful assistant for Russian-speaking residents of Israel. Help them understand Bituah Leumi (National Insurance). Always reply in Russian. Be warm and friendly. Give step by step instructions. Never ask for passwords or ID numbers."

MENU = ReplyKeyboardMarkup([
    ["Lichnyy kabinet", "Pisma"],
    ["Posobiya", "Dolgi"],
    ["Dokumenty", "Kody dostupa"],
    ["Sayt i prilozhenie", "Oshibki"],
    ["Specialist"]
], resize_keyboard=True)

async def start(u: Update, _):
    chats.pop(u.effective_user.id, None)
    await u.message.reply_text(
        "Shalom! Ya Neta - pomogayu s bituah leumi na russkom.\nNapishi vopros ili viberi temu:",
        reply_markup=MENU
    )

async def msg(u: Update, ctx):
    uid = u.effective_user.id
    text = u.message.text

    if uid not in chats:
        chats[uid] = []

    chats[uid].append({"role": "user", "content": text})
    if len(chats[uid]) > 10:
        chats[uid] = chats[uid][-10:]

    await ctx.bot.send_chat_action(u.effective_chat.id, "typing")

    try:
        r = ai.messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYS,
            messages=chats[uid]
        )
        reply = r.content[0].text
        chats[uid].append({"role": "assistant", "content": reply})
        await u.message.reply_text(reply, reply_markup=MENU)
    except Exception as ex:
        err = repr(ex)
        logger.error("Error calling AI: %s", err)
        await u.message.reply_text(
            "Oshibka. Poprobuy napisat /start i zadaj vopros zanovo.",
            reply_markup=MENU
        )

def main():
    logger.info("Starting Neta bot with model: %s", MODEL)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
