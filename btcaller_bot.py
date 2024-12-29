from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
import requests
import asyncio
import nest_asyncio
from solders.pubkey import Pubkey

nest_asyncio.apply()

# Almacena wallets asociadas con los `chat_id`
wallets_to_monitor = {}

# Función para obtener el saldo de una wallet de Solana
def get_solana_balance(wallet_address: str) -> float:
    url = 'https://api.mainnet-beta.solana.com'
    headers = {'Content-Type': 'application/json'}
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address]
    }

    try:
        response = requests.post(url, json=params, headers=headers)
        data = response.json()

        if 'result' in data and 'value' in data['result']:
            balance = data['result']['value'] / (10 ** 9)  # Convertir lamports a SOL
            return balance
        else:
            return -1  # Indica que no se pudo obtener el saldo
    except Exception as e:
        print(f'Error al obtener el saldo: {str(e)}')
        return -1

# Función para validar si la dirección de la wallet es válida
def is_valid_solana_wallet(wallet_address: str) -> bool:
    try:
        Pubkey.from_string(wallet_address)
        return True
    except Exception:
        return False

# Función para manejar el comando /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "¡Hola! Soy BTCaller. Envíame una dirección de wallet Solana y la monitorearé cada 5 minutos.\n"
        "Usa /help para más información sobre cómo usar el bot."
    )

# Función para agregar una wallet para monitoreo
async def monitor_wallet(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text.strip()
    chat_id = update.message.chat_id

    if is_valid_solana_wallet(user_message):
        balance = get_solana_balance(user_message)
        if balance != -1:
            if chat_id not in wallets_to_monitor:
                wallets_to_monitor[chat_id] = {}
            wallets_to_monitor[chat_id][user_message] = balance
            await update.message.reply_text(
                f"La wallet `{user_message}` ha sido añadida al monitoreo.\nSaldo inicial: {balance} SOL",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("No se pudo obtener el saldo de la wallet. Inténtalo de nuevo más tarde.")
    else:
        await update.message.reply_text("La dirección proporcionada no es válida. Asegúrate de que sea una dirección de wallet Solana correcta.")

# Función para listar todas las wallets monitoreadas en un chat
async def list_wallets(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    if chat_id in wallets_to_monitor and wallets_to_monitor[chat_id]:
        message = "**Wallets Monitoreadas:**\n"
        for wallet, balance in wallets_to_monitor[chat_id].items():
            message += f"- `{wallet}`: {balance} SOL\n"
        
        # Agregar botón para eliminar todas las wallets
        keyboard = InlineKeyboardMarkup([ 
            [InlineKeyboardButton("Eliminar Todas las Wallets", callback_data="delete_all_wallets")]
        ])
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text("No hay wallets en monitoreo actualmente para este chat.")

# Función para manejar la eliminación de todas las wallets
async def delete_all_wallets(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id

    if chat_id in wallets_to_monitor:
        wallets_to_monitor.pop(chat_id, None)  # Elimina todas las wallets de este chat
        await query.answer("Todas las wallets han sido eliminadas.")
        await query.edit_message_text("✅ Todas las wallets han sido eliminadas.")
    else:
        await query.answer("No hay wallets para eliminar.")
        await query.edit_message_text("No hay wallets en monitoreo para este chat.")

# Función para mostrar ayuda
async def help_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "🚀 **Guía de Comandos** 🚀\n\n"
        "/start - Inicia el bot y muestra el mensaje de bienvenida.\n"
        "/listwallets - Muestra las wallets monitoreadas en este chat.\n"
        "Envíame una dirección de wallet Solana para añadirla al monitoreo.\n"
        "El bot te notificará si hay cambios en el saldo.\n\n"
        "¡Espero que encuentres útil este bot! 😊",
        parse_mode="Markdown"
    )

# Función para monitorear wallets periódicamente
async def monitor_wallets(context: CallbackContext):
    for chat_id, wallets in wallets_to_monitor.items():
        for wallet, last_balance in wallets.items():
            new_balance = get_solana_balance(wallet)
            if new_balance == -1:
                continue  # Si hay error al obtener el balance, pasar a la siguiente wallet

            if new_balance != last_balance:
                wallets_to_monitor[chat_id][wallet] = new_balance
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=( 
                        f"🔔 **¡Alerta de Cambio!** 🔔\n"
                        f"La wallet `{wallet}` ha cambiado su saldo.\n"
                        f"Saldo anterior: {last_balance} SOL\n"
                        f"Saldo actual: {new_balance} SOL"
                    ),
                    parse_mode="Markdown"
                )

# Función principal
async def main():
    TOKEN = "7154345115:AAGOVg6GIyqst-IQxJu2C93113_uATTyiP8"
    application = Application.builder().token(TOKEN).build()
    job_queue = application.job_queue

    # Configurar comandos del bot
    commands = [
        BotCommand("start", "Inicia el bot"),
        BotCommand("listwallets", "Lista todas las wallets monitoreadas"),
        BotCommand("help", "Muestra información sobre cómo usar el bot"),
    ]
    await application.bot.set_my_commands(commands)

    # Comandos y manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_wallet))
    application.add_handler(CommandHandler("listwallets", list_wallets))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(delete_all_wallets, pattern="^delete_all_wallets$"))

    # Iniciar monitoreo periódico
    job_queue.run_repeating(monitor_wallets, interval=30, first=10)

    print("BTCaller está funcionando y monitoreando wallets...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
