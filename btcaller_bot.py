import asyncio
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters,
)
import nest_asyncio
import sqlite3
from solders.pubkey import Pubkey
import requests
import re

nest_asyncio.apply()

# Configuración de la base de datos SQLite
def init_db():
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    # Crear tablas si no existen
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
                        chat_id INTEGER,
                        group_name TEXT,
                        notifications_enabled INTEGER DEFAULT 1,
                        PRIMARY KEY (chat_id, group_name))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS wallets (
                        chat_id INTEGER,
                        group_name TEXT,
                        wallet_address TEXT,
                        balance REAL,
                        tag TEXT,
                        PRIMARY KEY (chat_id, group_name, wallet_address))''')
    conn.commit()
    conn.close()

# Función para guardar un grupo en la base de datos
def save_group(chat_id, group_name):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    
    # Verificar si ya existe un grupo con el mismo nombre
    cursor.execute('SELECT COUNT(*) FROM groups WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
    exists = cursor.fetchone()[0]
    
    if exists:
        print(f"El grupo '{group_name}' ya existe para chat_id {chat_id}.")
    else:
        cursor.execute('INSERT INTO groups (chat_id, group_name) VALUES (?, ?)', (chat_id, group_name))
        print(f"Grupo '{group_name}' creado para chat_id {chat_id}.")
    
    conn.commit()
    conn.close()


# Función para guardar una wallet en la base de datos
def save_wallet(chat_id, group_name, wallet_address, balance, tag=None):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO wallets (chat_id, group_name, wallet_address, balance, tag) VALUES (?, ?, ?, ?, ?)',
                   (chat_id, group_name, wallet_address, balance, tag))
    conn.commit()
    conn.close()


# Función para obtener el saldo de una wallet de Solana
def get_solana_balance(wallet_address: str) -> float:
    url = 'https://api.mainnet-beta.solana.com'
    headers = {'Content-Type': 'application/json'}
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address],
    }
    try:
        response = requests.post(url, json=params, headers=headers)
        data = response.json()
        if 'result' in data and 'value' in data['result']:
            balance = data['result']['value'] / (10**9)  # Convertir lamports a SOL
            return balance
        else:
            return -1  # Indica que no se pudo obtener el saldo
    except Exception as e:
        print(f'Error al obtener el saldo: {str(e)}')
        return -1


# Función para manejar la entrada de nombre de grupo
async def handle_group_name_input(update: Update, context: CallbackContext) -> None:
    if "awaiting_group_name" in context.user_data:
        group_name = update.message.text.strip()
        chat_id = update.message.chat_id

        # Validar el nombre del grupo
        if not is_valid_group_name(group_name):
            await update.message.reply_text(
                "⚠️ El nombre del grupo no es válido. Solo se permiten letras, números y los caracteres _ - con un máximo de 50 caracteres."
            )
            return

        # Intentar guardar el grupo y responder al usuario
        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM groups WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
        exists = cursor.fetchone()[0]
        conn.close()

        if exists:
            await update.message.reply_text(f"⚠️ El grupo '{group_name}' ya existe.")
        else:
            save_group(chat_id, group_name)
            await update.message.reply_text(f"✅ Grupo '{group_name}' creado exitosamente.")
        await list_groups(update, context)

        



# Validar nombre de grupo
def is_valid_group_name(group_name: str) -> bool:
    if len(group_name) > 50:
        return False
    if not re.match("^[a-zA-Z0-9_ -]*$", group_name):
        return False
    return True

# Función para validar si la dirección de la wallet es válida
def is_valid_solana_wallet(wallet_address: str) -> bool:
    try:
        Pubkey.from_string(wallet_address)
        return True
    except Exception:
        return False

# Función para mostrar el menú principal con una introducción atractiva
async def show_main_menu(update: Update, context: CallbackContext, message: str = None) -> None:
    welcome_message = (
        "✨ **¡Bienvenido a Billionaire Caller!** ✨\n\n"
        "💼 **Gestor de Grupos y Wallets Solana** 🚀\n\n"
        "🔹 Organiza y monitorea tus wallets en grupos personalizados.\n"
        "🔹 Recibe notificaciones automáticas sobre cambios de saldo.\n"
        "🔹 Diseñado para maximizar tu experiencia en el mundo blockchain.\n\n"
        "🔑 **Hecho por:** *Nicolás*\n"
        "📊 **Tu asistente confiable para el manejo de wallets SOL.**\n\n"
        "⬇️ Usa los botones a continuación para comenzar."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Crear Grupo", callback_data="create_group")],
        [InlineKeyboardButton("📋 Listar Grupos", callback_data="list_groups")],
    ])

    # Mostrar el mensaje inicial
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode="Markdown")


# Función para manejar el comando /start
async def start(update: Update, context: CallbackContext) -> None:
    await show_main_menu(update, context)

# Función para crear un grupo
async def create_group(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Envía el nombre del grupo que deseas crear.")
    context.user_data["awaiting_group_name"] = True


# Función para listar grupos
async def list_groups(update: Update, context: CallbackContext) -> None:
    if update.callback_query:
        query = update.callback_query
        chat_id = query.message.chat_id
    elif update.message:
        chat_id = update.message.chat_id
    else:
        return

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_name, notifications_enabled FROM groups WHERE chat_id = ?', (chat_id,))
    groups = cursor.fetchall()
    conn.close()

    if groups:
        buttons = []
        for group_name, notifications_enabled in groups:
            status = "🟢" if notifications_enabled else "🔴"
            buttons.append([
                InlineKeyboardButton(f"🗂 {group_name} ({status})", callback_data=f"view_group_{group_name}"),
                InlineKeyboardButton("❌ Eliminar", callback_data=f"delete_group_{group_name}"),
                InlineKeyboardButton(
                    "🔕 Desactivar" if notifications_enabled else "🔔 Activar",
                    callback_data=f"toggle_notifications_{group_name}"
                ),
            ])
        buttons.append([InlineKeyboardButton("🔙 Regresar", callback_data="main_menu")])
        keyboard = InlineKeyboardMarkup(buttons)

        if update.callback_query:
            await query.answer()
            await query.edit_message_text(
                "**📂 Tus grupos creados**\n\n🔹 Aquí puedes gestionar tus grupos de wallets Solana.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        elif update.message:
            await update.message.reply_text(
                "**📂 Tus grupos creados**\n\n🔹 Aquí puedes gestionar tus grupos de wallets Solana.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    else:
        message = "⚠️ No tienes grupos creados actualmente."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Regresar", callback_data="main_menu")]])
        if update.callback_query:
            await query.answer()
            await query.edit_message_text(message, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(message, reply_markup=keyboard)


async def toggle_notifications(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT notifications_enabled FROM groups WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
    current_status = cursor.fetchone()
    
    if current_status is not None:
        new_status = 0 if current_status[0] else 1
        cursor.execute('UPDATE groups SET notifications_enabled = ? WHERE chat_id = ? AND group_name = ?',
                       (new_status, chat_id, group_name))
        conn.commit()
        conn.close()
        
        status_msg = "🔔 Notificaciones activadas" if new_status else "🔕 Notificaciones desactivadas"
        await query.answer(f"{status_msg} para el grupo '{group_name}'.")
        await list_groups(update, context)
    else:
        conn.close()
        await query.answer("⚠️ El grupo no existe.")


async def main_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await show_main_menu(update, context)

# Función para eliminar wallets de un grupo
async def remove_wallet(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_address FROM wallets WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
    wallets = cursor.fetchall()
    conn.close()

    if wallets:
        await query.answer()
        await query.edit_message_text(
            f"Envía las direcciones de wallet que deseas eliminar del grupo `{group_name}`, separadas por espacios.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_wallet_removal"] = group_name
    else:
        await query.answer("No hay wallets para eliminar.")
        await query.edit_message_text("⚠️ No hay wallets en el grupo.")


# Combina manejadores de texto en una sola función
async def handle_text_input(update: Update, context: CallbackContext) -> None:
    if "awaiting_wallet_removal" in context.user_data:
        await handle_wallet_removal(update, context)
    elif "awaiting_wallet" in context.user_data:
        await handle_wallet_input(update, context)
    elif "awaiting_group_name" in context.user_data:
        await handle_group_name_input(update, context)
    elif "editing_tag_wallet" in context.user_data:
        await set_tag(update, context)
    else:
        # Mostrar el menú principal si no hay contexto pendiente
        await update.message.reply_text(
            "⚠️ No entiendo este comando o mensaje.\nPor favor, usa el menú principal para interactuar."
        )
        await show_main_menu(update, context)


# Función para manejar la eliminación de wallets
async def handle_wallet_removal(update: Update, context: CallbackContext) -> None:
    if "awaiting_wallet_removal" in context.user_data:
        group_name = context.user_data.pop("awaiting_wallet_removal", None)
        wallet_addresses = update.message.text.strip().split()
        chat_id = update.message.chat_id

        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()

        for wallet_address in wallet_addresses:
            cursor.execute('DELETE FROM wallets WHERE chat_id = ? AND group_name = ? AND wallet_address = ?',
                           (chat_id, group_name, wallet_address))

        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Wallets eliminadas del grupo `{group_name}`.")
        # Regresa a la vista del grupo
        await show_group_wallets(update, context, chat_id, group_name)
    else:
        await update.message.reply_text("No hay wallets pendientes para eliminar.")

# Función para mostrar wallets del grupo
async def show_group_wallets(update: Update, context: CallbackContext, chat_id: int, group_name: str) -> None:
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_address, balance, tag FROM wallets WHERE chat_id = ? AND group_name = ?',
                   (chat_id, group_name))
    wallets = cursor.fetchall()
    conn.close()

    if wallets:
        message = f"📂 **Grupo: {group_name}**\n\n"
        for wallet, balance, tag in wallets:
            message += (
                f"💳 **Wallet**: `{wallet}`\n"
                f"💰 **Balance**: {balance:.9f} SOL\n"
                f"🏷️ **Tag**: `{tag}`\n"
                f"🔧 `/edit_tag {wallet}`\n\n"
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Wallet(s)", callback_data=f"add_wallet_{group_name}")],
            [InlineKeyboardButton("🗑️ Eliminar Wallet(s)", callback_data=f"remove_wallet_{group_name}")],
            [InlineKeyboardButton("🔙 Regresar", callback_data="list_groups")]
        ])

        await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")
    else:
        message = f"📂 **Grupo: {group_name}**\n\n🚫 Este grupo no contiene wallets actualmente."

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Wallet", callback_data=f"add_wallet_{group_name}")],
            [InlineKeyboardButton("🔙 Regresar", callback_data="list_groups")]
        ])

        await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")



# Función para ver un grupo y mostrar la opción de agregar wallet
async def view_group(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_address, balance, tag FROM wallets WHERE chat_id = ? AND group_name = ?',
                   (chat_id, group_name))
    wallets = cursor.fetchall()
    conn.close()

    if wallets:
        message = f"📂 **Grupo: {group_name}**\n\n"
        for wallet, balance, tag in wallets:
            message += (
                f"💳 **Wallet**: `{wallet}`\n"
                f"💰 **Balance**: {balance:.9f} SOL\n"
                f"🏷️ **Tag**: `{tag}`\n"
                f"🔧 `/edit_tag {wallet}`\n\n"
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Wallet(s)", callback_data=f"add_wallet_{group_name}")],
            [InlineKeyboardButton("🗑️ Eliminar Wallet(s)", callback_data=f"remove_wallet_{group_name}")],
            [InlineKeyboardButton("🔙 Regresar", callback_data="list_groups")]
        ])

        await query.answer()
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")
    else:
        message = f"📂 **Grupo: {group_name}**\n\n🚫 Este grupo no contiene wallets actualmente."

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Wallet", callback_data=f"add_wallet_{group_name}")],
            [InlineKeyboardButton("🔙 Regresar", callback_data="list_groups")]
        ])

        await query.answer()
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

# Función para editar el tag
async def edit_tag(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args

    if len(args) < 1:
        await update.message.reply_text("⚠️ Debes proporcionar una dirección de wallet. Ejemplo: `/edit_tag <wallet_address>`")
        return

    wallet_address = args[0]

    # Verifica si la wallet existe en la base de datos
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT tag FROM wallets WHERE chat_id = ? AND wallet_address = ?', (chat_id, wallet_address))
    existing_tag = cursor.fetchone()
    conn.close()

    if existing_tag:
        # Si existe la wallet, guarda la dirección para editar el tag
        context.user_data["editing_tag_wallet"] = wallet_address
        await update.message.reply_text(f"Envía el nuevo tag para la wallet: `{wallet_address}`")
    else:
        await update.message.reply_text(f"⚠️ La wallet `{wallet_address}` no se encuentra en el sistema.")


# Función para actualizar el tag
async def set_tag(update: Update, context: CallbackContext) -> None:
    if "editing_tag_wallet" in context.user_data:
        chat_id = update.message.chat_id
        wallet_address = context.user_data.pop("editing_tag_wallet")
        new_tag = update.message.text.strip()

        # Actualiza el tag en la base de datos
        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE wallets SET tag = ? WHERE chat_id = ? AND wallet_address = ?', (new_tag, chat_id, wallet_address))

        conn.commit()
        conn.close()

        # Confirma que el tag fue actualizado y restablece el estado
        await update.message.reply_text(f"✅ El tag para la wallet `{wallet_address}` ha sido actualizado a: `{new_tag}`.")
    else:
        await update.message.reply_text("⚠️ No estás editando un tag actualmente.")


# Función para agregar una wallet al grupo
async def add_wallet(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    # Verifica si el grupo existe
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_name FROM groups WHERE chat_id = ?', (chat_id,))
    groups = cursor.fetchall()
    conn.close()

    if group_name in [group[0] for group in groups]:
        await query.answer()
        await query.edit_message_text(
            f"Envía la dirección de la wallet para agregarla al grupo `{group_name}`.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_wallet"] = group_name  # Marca que se espera una wallet
    else:
        await query.answer("El grupo no existe.")
        await query.edit_message_text("⚠️ El grupo ya no existe.")




# Función para manejar la entrada de direcciones de wallet
async def handle_wallet_input(update: Update, context: CallbackContext) -> None:
    if "awaiting_wallet" in context.user_data:
        group_name = context.user_data.pop("awaiting_wallet")
        wallet_addresses = update.message.text.strip().split()
        chat_id = update.message.chat_id

        added_wallets = []
        invalid_wallets = []
        failed_wallets = []

        for wallet_address in wallet_addresses:
            if is_valid_solana_wallet(wallet_address):
                balance = get_solana_balance(wallet_address)
                if balance != -1:
                    save_wallet(chat_id, group_name, wallet_address, balance)
                    added_wallets.append(wallet_address)
                else:
                    failed_wallets.append(wallet_address)
            else:
                invalid_wallets.append(wallet_address)

        response = ""
        if added_wallets:
            response += f"✅ **Wallets añadidas al grupo `{group_name}`**:\n" + "\n".join(f"- `{wallet}`" for wallet in added_wallets) + "\n"
        if invalid_wallets:
            response += "⚠️ **Direcciones no válidas:**\n" + "\n".join(f"- `{wallet}`" for wallet in invalid_wallets) + "\n"
        if failed_wallets:
            response += "⚠️ **Error al obtener saldo:**\n" + "\n".join(f"- `{wallet}`" for wallet in failed_wallets) + "\n"

        await update.message.reply_text(response, parse_mode="Markdown")
        # Regresa a la vista del grupo
        await show_group_wallets(update, context, chat_id, group_name)


# Función para eliminar un grupo
async def delete_group(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM groups WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
    cursor.execute('DELETE FROM wallets WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
    conn.commit()
    conn.close()

    await query.answer(f"✅ Grupo `{group_name}` eliminado.")
    await list_groups(update, context)  # Redirige a la lista de grupos


# Función para monitorear las wallets y enviar un mensaje bonito
async def monitor_wallets(application: Application) -> None:
    while True:
        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.chat_id, g.group_name, w.wallet_address, w.tag, g.notifications_enabled
            FROM wallets w
            JOIN groups g ON w.chat_id = g.chat_id AND w.group_name = g.group_name
        ''')
        wallets = cursor.fetchall()
        conn.close()

        for chat_id, group_name, wallet_address, tag, notifications_enabled in wallets:
            if notifications_enabled:  # Verifica si las notificaciones están activadas
                new_balance = get_solana_balance(wallet_address)
                if new_balance != -1:
                    conn = sqlite3.connect('wallets.db')
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT balance FROM wallets WHERE chat_id = ? AND group_name = ? AND wallet_address = ?',
                        (chat_id, group_name, wallet_address)
                    )
                    row = cursor.fetchone()
                    old_balance = row[0] if row else None
                    conn.close()

                    if old_balance is not None and abs(new_balance - old_balance) > 0.01:
                        conn = sqlite3.connect('wallets.db')
                        cursor = conn.cursor()
                        cursor.execute(
                            'UPDATE wallets SET balance = ? WHERE chat_id = ? AND group_name = ? AND wallet_address = ?',
                            (new_balance, chat_id, group_name, wallet_address)
                        )
                        conn.commit()
                        conn.close()

                        cambio_balance = new_balance - old_balance
                        if cambio_balance < -0.002039:
                            tipo_de = "Compra de token"
                        elif cambio_balance == -0.002039:
                            tipo_de = "Transferencia de Token"
                        elif cambio_balance > -0.002039:
                            tipo_de = "Venta de Token"
                        else:
                            tipo_de = "Sin Clasificación"

                        solscan_url = f"https://solscan.io/account/{wallet_address}"
                        message = f"""
                        🚨 *Cambio de saldo en la wallet* {'- 🏷️ ' + tag if tag else ''} `{wallet_address}`

💸 *Grupo:* `{group_name}`
🪙 *Saldo anterior:* {old_balance:.9f} SOL
💎 *Nuevo saldo:* {new_balance:.9f} SOL
🛑 *Tipo de cambio:* {tipo_de}

🔗 [Ver en Solscan]({solscan_url})
                        """

                        await application.bot.send_message(
                            chat_id,
                            message,
                            parse_mode="Markdown"
                        )
        await asyncio.sleep(10)




# Comando principal
async def main():
    init_db()

    application = Application.builder().token('8073566200:AAFwq06FksKMNX-5566tS5uwr6gJ9AjR1Go').build()

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


    # Inicia el monitoreo de wallets en segundo plano
    asyncio.create_task(monitor_wallets(application))

    # Inicia el polling
    await application.run_polling()

# Ejecuta la función principal usando asyncio.run()
if __name__ == '__main__':
    asyncio.run(main())
