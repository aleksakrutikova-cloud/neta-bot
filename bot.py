import os
import sys
import logging
from anthropic import Anthropic
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

LEAD_NAME, LEAD_PHONE, LEAD_DESC = range(3)

histories = {}

SYSTEM = """You are Neta, a friendly assistant helping Russian-speaking residents of Israel navigate the bituah leumi system (National Insurance Institute). Reply ONLY in Russian language.

You explain in simple Russian: rights, benefits, letters, personal account, documents, access codes, website and app of bituah leumi.

RULES:
- Never ask for personal ID numbers, passwords, codes or banking details
- If user sends personal data - warn them not to do this
- On important topics add: I do not replace bituah leumi, a lawyer or accountant
- Do not invent benefit amounts or laws - if unsure, say so
- Use Hebrew for official terms with Russian translation in parentheses
- Ask clarifying questions before answering
- Give step-by-step instructions
- Use emojis for structure"""

WELCOME = """Shalom! Ya *Neta* — pomogayu razobratsya v *bituah leumi* na ponyatnom russkom yazyke.

Vyberi temu ili prosto napishi svoy vopros"""

def menu():
    return ReplyKeyboardMarkup([
        ["Lichnyy kabinet", "Pisma"],
        ["Posobiya i vyplaty", "Dolgi"],
        ["Dokumenty", "Kody dostupa"],
        ["Sayt i prilozhenie", "Chastye oshibki"],
        ["Svyazatsya so spetsialistom"],
    ], resize_keyboard=True)

async def ask(user_id, text):
    if user_id not in histories:
        histories[user_id] = []
    histories[user_id].append({"role": "user", "content": text})
    if len(histories[user_id]) > 20:
        histories[user_id] = histories[user_id][-20:]
    try:
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=SYSTEM,
            messages=histories[user_id],
        )
        reply = r.content[0].text
        histories[user_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        logger.error("API error: %s", e)
        return "Chto-to poshlo ne tak. Poprobuy eshche raz."

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    histories.pop(update.effective_user.id, None)
    await update.message.reply_text(WELCOME, reply_markup=menu(), parse_mode="Markdown")

async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    histories.pop(update.effective_user.id, None)
    await update.message.reply_text("Nachnem snachala!", reply_markup=menu())

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    if "spetsialist" in text.lower() or "специалист" in text.lower():
        await update.message.reply_text(
            "Svyazhu tebya so spetsialistom! Kak tebya zovut?",
            reply_markup=ReplyKeyboardRemove()
        )
        return LEAD_NAME

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    reply = await ask(uid, text)
    await update.message.reply_text(reply, reply_markup=menu(), parse_mode="Markdown")

async def lead_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text
    await update.message.reply_text("Tvoy telefon ili Telegram?")
    return LEAD_PHONE

async def lead_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["phone"] = update.message.text
    await update.message.reply_text("Kratko opishi svoy vopros (ili napishi - propustit):")
    return LEAD_DESC

async def lead_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg = (
        "New lead!\n\n"
        f"Name: {ctx.user_data.get('name')}\n"
        f"Contact: {ctx.user_data.get('phone')}\n"
        f"Question: {update.message.text}\n"
        f"TG: @{u.username or '-'} | {u.id}"
    )
    if ADMIN_CHAT_ID:
        try:
            await ctx.bot.send_message(ADMIN_CHAT_ID, msg)
        except Exception as e:
            logger.error("Lead error: %s", e)
    await update.message.reply_text("Zayavka otpravlena! Spetsialist svyazhetsya s toboy skoro.", reply_markup=menu())
    return ConversationHandler.END

async def lead_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("OK!", reply_markup=menu())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    lead_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle)],
        states={
            LEAD_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            LEAD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)],
            LEAD_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_desc)],
        },
        fallbacks=[CommandHandler("cancel", lead_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(lead_conv)

    logger.info("Neta bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
