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
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

TOKEN = os.environ["TELEGRAM_TOKEN"]
KEY = os.environ["ANTHROPIC_API_KEY"]
ADMIN = os.environ.get("ADMIN_CHAT_ID", "")

ai = anthropic.Anthropic(api_key=KEY)
MODEL = "claude-haiku-4-5"
chats = {}

LEAD_NAME, LEAD_PHONE, LEAD_DESC = range(3)

SYS = """You are Neta, a helpful assistant for Russian-speaking residents of Israel.
Help them understand Bituah Leumi (National Insurance Institute of Israel).
Always reply in Russian language only.

Current year is 2026. Benefit amounts change frequently - always tell users to verify current amounts at btl.gov.il

TONE - very important:
- Talk like a close warm friend, not like an official
- Show empathy first: "Понимаю, это правда запутанно", "Ой, это неприятная ситуация", "Давай разберёмся вместе"
- If someone has a problem or stress - acknowledge it before giving info: "Я тебя понимаю, такие письма пугают. Давай посмотрим что там."
- Be warm, supportive, human
- Never sound cold or bureaucratic
- Short sentences, easy language

PAGINATION RULES:
- Maximum 5 steps per message
- If full answer needs more than 5 steps, show steps 1-5 and end with exactly:
  "Нажми 'Продолжить' чтобы увидеть следующие шаги."
- When user sends "Продолжить" - continue from where you stopped
- Always complete the current step fully before stopping

FORMATTING RULES:
- No markdown: no **, no ##, no ###, no ---, no *, no _
- Plain text only
- Numbered steps: 1. 2. 3.
- Dashes for sub-points: -
- No emojis unless user uses them first

SAFETY RULES:
- Never request ID numbers, passwords or banking details
- If user sends personal data - warn them kindly not to share it
- Always remind: you do not replace official bituah leumi advice
- Use Hebrew terms with Russian translation in brackets"""

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
        "Шалом! Я Нета — твой личный переводчик с бюрократического на человеческий 🤓\n\n"
        "Помогаю разобраться в ביטוח לאומי без стресса и словаря иврита.\n\n"
        "Умею объяснять:\n"
        "- письма (те самые, от которых хочется спрятаться под стол)\n"
        "- пособия (спойлер: возможно тебе положено больше чем ты думаешь)\n"
        "- личный кабинет, документы, долги, коды доступа и сайт\n\n"
        "(Важно: я самостоятельный информационный помощник и никак не связана с ביטוח לאומי, "
        "не являюсь их официальным представителем, юристом или бухгалтером. "
        "Вся информация ознакомительная — для официальных решений обращайся напрямую "
        "в ביטוח לאומי или к лицензированному специалисту.)\n\n"
        "🔒 Пожалуйста, не присылай мне личные данные — номер удостоверения личности, "
        "пароли, коды и банковские данные. Я в них не нуждаюсь и не могу их хранить безопасно.\n\n"
        "Итак — чем могу помочь? 👇",
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
        await u.message.reply_text("Что-то пошло не так. Попробуй ещё раз.", reply_markup=MENU)

# --- Сбор лидов ---

async def lead_start(u: Update, ctx):
    await u.message.reply_text(
        "Свяжу тебя со специалистом по ביטוח לאומי.\n\nСпециалист поможет с:\n- обжалованием отказа\n- долгами и рассрочкой\n- сложными ситуациями\n\nКак тебя зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    return LEAD_NAME

async def lead_name(u: Update, ctx):
    ctx.user_data["name"] = u.message.text
    await u.message.reply_text("Твой номер телефона или Telegram-ник:")
    return LEAD_PHONE

async def lead_phone(u: Update, ctx):
    ctx.user_data["phone"] = u.message.text
    await u.message.reply_text("Кратко опиши свой вопрос (или напиши 'пропустить'):")
    return LEAD_DESC

async def lead_desc(u: Update, ctx):
    tg = u.effective_user
    name = ctx.user_data.get("name", "-")
    phone = ctx.user_data.get("phone", "-")
    desc = u.message.text

    lead_msg = (
        "Новый лид!\n\n"
        f"Имя: {name}\n"
        f"Контакт: {phone}\n"
        f"Вопрос: {desc}\n"
        f"TG: @{tg.username or '-'} | ID: {tg.id}"
    )

    if ADMIN:
        try:
            await ctx.bot.send_message(ADMIN, lead_msg)
            logger.info("Lead sent: %s / %s", name, phone)
        except Exception as ex:
            logger.error("Lead send error: %s", repr(ex))

    await u.message.reply_text(
        "Заявка отправлена! Специалист свяжется с тобой в ближайшее время.",
        reply_markup=MENU
    )
    return ConversationHandler.END

async def lead_cancel(u: Update, ctx):
    await u.message.reply_text("Хорошо, возвращаемся в меню.", reply_markup=MENU)
    return ConversationHandler.END

def main():
    logger.info("Starting Neta bot, model: %s", MODEL)
    app = Application.builder().token(TOKEN).build()

    lead_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("Связаться со специалистом"), lead_start)
        ],
        states={
            LEAD_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            LEAD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)],
            LEAD_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_desc)],
        },
        fallbacks=[CommandHandler("cancel", lead_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(lead_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
