# -*- coding: utf-8 -*-
"""
NETA — Telegram bot for Bituah Leumi help
"""
 
import os
import sys
import logging
import base64
import anthropic
 
# UTF-8 encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
 
# ─── Логирование ───────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
 
# ─── Токены из переменных окружения ───────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
 
# ID чата куда приходят лиды (твой личный Telegram ID)
# Узнать свой ID: написать @userinfobot в Telegram
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
 
# ─── Anthropic клиент ─────────────────────────────────────────
ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
 
# ─── Состояния для сбора лида ─────────────────────────────────
LEAD_NAME, LEAD_PHONE, LEAD_QUESTION = range(3)
 
# ─── История диалогов (в памяти) ─────────────────────────────
# Формат: { user_id: [ {role, content}, ... ] }
user_histories: dict[int, list] = {}
MAX_HISTORY = 20  # максимум сообщений в истории
 
# ─── Системный промт ──────────────────────────────────────────
SYSTEM_PROMPT = """Ты — «Нета» (נטע), дружелюбный помощник по системе ביטוח לאומי (Национальный страховой институт Израиля).
 
Твоя роль — НЕ юрист, НЕ бухгалтер, НЕ официальный представитель ביטוח לאומי. Ты — «умный друг, который уже разобрался в системе» и объясняет простым русским языком, что делать, куда нажать и где найти нужный документ.
 
Ты говоришь с репатриантами и русскоязычными жителями Израиля.
 
ПРАВИЛА БЕЗОПАСНОСТИ — НЕЛЬЗЯ НАРУШАТЬ:
1. НИКОГДА не запрашивай: מספר זהות, пароли, коды доступа, банковские данные, сканы документов с личными данными.
2. Если пользователь присылает личные данные — немедленно предупреди: "⚠️ Стоп! Пожалуйста, не отправляй мне личные номера, пароли или коды. Я не могу и не должен их получать. Расскажи ситуацию словами — и я помогу разобраться."
3. В важных темах добавляй: "📌 Я помогаю разобраться. Я не заменяю ביטוח לאומי, адвоката или бухгалтера."
4. НИКОГДА не придумывай суммы пособий, даты, законы. Если не уверен — скажи об этом.
5. Всегда используй иврит для официальных терминов с русским переводом в скобках.
 
ЛОГИКА ДИАЛОГА:
- Сначала задай 1-2 уточняющих вопроса, потом давай конкретный ответ
- Давай пошаговые инструкции с ивритскими названиями кнопок
- После каждого ответа предлагай 2-3 варианта следующего шага
- Ответы конкретные, не длиннее необходимого
- Форматируй ответы с эмодзи, короткими абзацами. Используй *жирный* для важного (одна звёздочка с каждой стороны для Telegram markdown)
 
ТЕМЫ ПОМОЩИ:
- כניסה לאזור האישי — Личный кабинет: как войти, восстановить доступ, что там есть
- מכתבים והודעות — Письма: объяснять содержание писем от ביטוח לאומי
- קצבאות ותגמולים — Пособия: קצבת ילדים, דמי לידה, קצבת אבטלה, הבטחת הכנסה, קצבת נכות и др.
- חובות ותשלומים — Долги: объяснять долги, рассрочки, последствия
- מסמכים ואישורים — Документы: где и как получить справки
- קודי גישה — Коды доступа: процедуры получения, НЕ сами коды
- אתר ואפליקציה — Сайт и приложение: навигация по btl.gov.il
- טעויות נפוצות — Частые ошибки: типичные проблемы репатриантов
 
Если прислали скриншот письма или сайта — проанализируй что на нём, объясни каждую часть простым языком, скажи что нужно сделать.
 
Отвечай ТОЛЬКО на русском языке."""
 
# ─── Главное меню ─────────────────────────────────────────────
MENU_TEXT = """👋 Привет! Я *Нета* — помогаю разобраться в *ביטוח לאומי* на понятном русском языке.
 
Выбери тему или просто напиши свой вопрос 👇"""
 
def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    keyboard = [
        [KeyboardButton("🔐 כניסה לאזור האישי — Личный кабинет")],
        [KeyboardButton("📬 מכתבים — Письма и уведомления")],
        [KeyboardButton("💳 קצבאות — Пособия и выплаты")],
        [KeyboardButton("💰 חובות — Долги и платежи")],
        [KeyboardButton("📄 מסמכים — Документы и справки")],
        [KeyboardButton("🔑 קודי גישה — Коды доступа")],
        [KeyboardButton("🌐 אתר ואפליקציה — Сайт и приложение")],
        [KeyboardButton("⚠️ טעויות נפוצות — Частые ошибки")],
        [KeyboardButton("👤 Связаться со специалистом")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
 
# ─── Вспомогательные функции ──────────────────────────────────
def get_history(user_id: int) -> list:
    """Получить историю диалога пользователя."""
    return user_histories.get(user_id, [])
 
def add_to_history(user_id: int, role: str, content):
    """Добавить сообщение в историю."""
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": role, "content": content})
    # Обрезаем историю если слишком длинная
    if len(user_histories[user_id]) > MAX_HISTORY:
        user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]
 
async def ask_neta(user_id: int, user_message_content) -> str:
    """Отправить запрос к Claude и получить ответ."""
    add_to_history(user_id, "user", user_message_content)
    history = get_history(user_id)
 
    try:
        response = ai_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply = response.content[0].text
        add_to_history(user_id, "assistant", reply)
        return reply
    except Exception as e:
        logger.error("API Error: %s", str(e).encode("utf-8", errors="replace").decode("ascii", errors="replace"))
        return "⚠️ Что-то пошло не так. Попробуй ещё раз через пару секунд."
 
def escape_md(text: str) -> str:
    """Экранирование для MarkdownV2 (оставляем только базовый Markdown)."""
    return text
 
# ─── Хэндлеры команд ──────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — приветствие и главное меню."""
    user_id = update.effective_user.id
    user_histories[user_id] = []  # сбрасываем историю
 
    await update.message.reply_text(
        MENU_TEXT,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
 
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu — показать главное меню."""
    await update.message.reply_text(
        "📋 Главное меню:",
        reply_markup=get_main_menu_keyboard()
    )
 
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reset — сбросить историю диалога."""
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text(
        "🔄 История диалога сброшена. Начнём сначала!\n\n" + MENU_TEXT,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
 
# ─── Хэндлер текстовых сообщений ─────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка любого текстового сообщения."""
    user_id = update.effective_user.id
    text = update.message.text
 
    # Кнопка специалиста — запускаем сбор лида
    if "Связаться со специалистом" in text:
        await update.message.reply_text(
            "👤 Хорошо, свяжу тебя со специалистом!\n\n"
            "Специалист по *ביטוח לאומי* может помочь с:\n"
            "— обжалованием отказа (ערר)\n"
            "— разбором долгов и рассрочкой\n"
            "— сложными жизненными ситуациями\n\n"
            "Как тебя зовут?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return LEAD_NAME
 
    # Показываем «печатает...»
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
 
    # Получаем ответ от Неты
    reply = await ask_neta(user_id, text)
 
    await update.message.reply_text(
        reply,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
 
# ─── Хэндлер фото / скриншотов ───────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка скриншота или фото."""
    user_id = update.effective_user.id
 
    await update.message.reply_text(
        "📸 Вижу скриншот! Анализирую...\n\n"
        "⚠️ *Напоминание:* убедись, что на скриншоте нет твоего מספר זהות или пароля.",
        parse_mode="Markdown"
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
 
    # Скачиваем фото
    photo = update.message.photo[-1]  # берём самое большое
    photo_file = await context.bot.get_file(photo.file_id)
    photo_bytes = await photo_file.download_as_bytearray()
    photo_b64 = base64.standard_b64encode(photo_bytes).decode("utf-8")
 
    # Подпись пользователя (если есть)
    caption = update.message.caption or "Объясни что на этом скриншоте"
 
    # Запрос к Claude с изображением
    message_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": photo_b64,
            },
        },
        {
            "type": "text",
            "text": f"Пользователь прислал скриншот. Его вопрос: {caption}\n\n"
                    "Проанализируй что на скриншоте, объясни простым русским языком "
                    "каждую часть. Если это письмо от ביטוח לאומי — объясни что оно значит "
                    "и что нужно сделать. Если это страница сайта — объясни где находится "
                    "человек и что нажать дальше."
        }
    ]
 
    try:
        add_to_history(user_id, "user", message_content)
        history = get_history(user_id)
 
        response = ai_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply = response.content[0].text
        add_to_history(user_id, "assistant", reply)
 
        await update.message.reply_text(
            reply,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error("Photo error: %s", e)
        await update.message.reply_text(
            "⚠️ Не удалось обработать скриншот. Попробуй описать ситуацию текстом.",
            reply_markup=get_main_menu_keyboard()
        )
 
# ─── Сбор лида (ConversationHandler) ─────────────────────────
async def lead_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: получаем имя."""
    context.user_data["lead_name"] = update.message.text
    await update.message.reply_text(
        f"Отлично, *{update.message.text}*! 👋\n\n"
        "Напиши свой номер телефона или Telegram-ник, "
        "чтобы специалист мог с тобой связаться:",
        parse_mode="Markdown"
    )
    return LEAD_PHONE
 
async def lead_get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: получаем телефон."""
    context.user_data["lead_phone"] = update.message.text
    await update.message.reply_text(
        "Кратко опиши свою ситуацию — чтобы специалист мог подготовиться "
        "(или напиши *пропустить*):",
        parse_mode="Markdown"
    )
    return LEAD_QUESTION
 
async def lead_get_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 3: получаем вопрос, сохраняем лид."""
    name     = context.user_data.get("lead_name", "—")
    phone    = context.user_data.get("lead_phone", "—")
    question = update.message.text
    tg_user  = update.effective_user
 
    # Формируем сообщение для администратора
    lead_text = (
        f"🔔 *Новый лид!*\n\n"
        f"👤 Имя: {name}\n"
        f"📱 Контакт: {phone}\n"
        f"❓ Вопрос: {question}\n\n"
        f"Telegram: @{tg_user.username or '—'} | ID: `{tg_user.id}`"
    )
 
    # Отправляем администратору
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=lead_text,
                parse_mode="Markdown"
            )
            logger.info(f"Лид отправлен администратору: {name} / {phone}")
        except Exception as e:
            logger.error("Lead send error: %s", e)
 
    # Отвечаем пользователю
    await update.message.reply_text(
        "✅ *Отлично! Заявка отправлена.*\n\n"
        "Специалист свяжется с тобой в ближайшее время.\n\n"
        "А пока — я здесь, если появятся вопросы 👇",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END
 
async def lead_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена сбора лида."""
    await update.message.reply_text(
        "Хорошо, вернёмся к главному меню 👇",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END
 
# ─── Запуск бота ──────────────────────────────────────────────
def main():
    """Запуск бота."""
    logger.info("Starting bot...")
 
    app = Application.builder().token(TELEGRAM_TOKEN).build()
 
    # ConversationHandler для сбора лида
    lead_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("Связаться со специалистом"),
                handle_text
            )
        ],
        states={
            LEAD_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_get_name)],
            LEAD_PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_get_phone)],
            LEAD_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_get_question)],
        },
        fallbacks=[CommandHandler("cancel", lead_cancel)],
    )
 
    # Регистрируем хэндлеры
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu",  cmd_menu))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(lead_conv)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
 
    logger.info("Bot started successfully")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
 
if __name__ == "__main__":
    main()
 
