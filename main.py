import asyncio
import logging
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import nest_asyncio
from dotenv import load_dotenv
from handlers import (
    start, create_group, list_groups, view_group, delete_group, add_wallet, 
    remove_wallet, main_menu, handle_text_input, edit_tag, toggle_notifications, error_handler
)
from monitor import monitor_wallets
from database import init_db

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

nest_asyncio.apply()

# Configura el registro de errores
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def main():
    # Inicializar la base de datos
    init_db()

    # Obtener el token del bot de Telegram desde la variable de entorno
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("El token del bot de Telegram no está definido en la variable de entorno TELEGRAM_BOT_TOKEN")

    # Crear la aplicación de Telegram
    application = Application.builder().token(token).build()

    # Añadir manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(create_group, pattern="create_group"))
    application.add_handler(CallbackQueryHandler(list_groups, pattern="list_groups"))
    application.add_handler(CallbackQueryHandler(view_group, pattern="view_group_"))
    application.add_handler(CallbackQueryHandler(delete_group, pattern="delete_group_"))
    application.add_handler(CallbackQueryHandler(add_wallet, pattern="add_wallet_"))
    application.add_handler(CallbackQueryHandler(remove_wallet, pattern="remove_wallet_"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    application.add_handler(CommandHandler("edit_tag", edit_tag))
    application.add_handler(CallbackQueryHandler(toggle_notifications, pattern=r'^toggle_notifications_'))
    application.add_error_handler(error_handler)

    # Inicia el monitoreo de wallets en segundo plano
    asyncio.create_task(monitor_wallets(application))

    # Inicia el polling
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())