def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    lead_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("(?i)spetsialist|специалист"),
                handle
            )
        ],
        states={
            LEAD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)
            ],
            LEAD_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)
            ],
            LEAD_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_desc)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lead_cancel)
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))

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

if __name__ == "__main__":
    main()
