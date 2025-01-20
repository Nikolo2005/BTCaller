import logging
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from database import save_group, save_wallet, get_solana_balance, is_valid_solana_wallet, is_valid_group_name

logger = logging.getLogger(__name__)

async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update.callback_query:
        await update.callback_query.answer(text="Ha ocurrido un error. Por favor, inténtelo de nuevo más tarde.", show_alert=True)

async def start(update: Update, context: CallbackContext) -> None:
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

    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode="Markdown")

async def create_group(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Envía el nombre del grupo que deseas crear.")
    context.user_data["state"] = "awaiting_group_name"

async def handle_group_name_input(update: Update, context: CallbackContext) -> None:
    if context.user_data.get("state") == "awaiting_group_name":
        group_name = update.message.text.strip()
        chat_id = update.message.chat_id

        if not is_valid_group_name(group_name):
            await update.message.reply_text(
                "⚠️ El nombre del grupo no es válido. Solo se permiten letras, números y los caracteres _ - con un máximo de 50 caracteres."
            )
            return

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
        context.user_data["state"] = None

async def list_groups(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id

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

        message_text = "**📂 Tus grupos creados**\n\n🔹 Aquí puedes gestionar tus grupos de wallets Solana."
        if query.message.text != message_text:
            await query.edit_message_text(
                message_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    else:
        message = "⚠️ No tienes grupos creados actualmente."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Regresar", callback_data="main_menu")]])
        if query.message.text != message:
            await query.edit_message_text(message, reply_markup=keyboard)

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
        cursor.execute('UPDATE groups SET notifications_enabled = ? WHERE chat_id = ? AND group_name = ?', (new_status, chat_id, group_name))
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
    await start(update, context)
    
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
        context.user_data["state"] = "awaiting_wallet_removal"
        context.user_data["group_name"] = group_name
    else:
        await query.answer("No hay wallets para eliminar.")
        await query.edit_message_text("⚠️ No hay wallets en el grupo.")

async def handle_text_input(update: Update, context: CallbackContext) -> None:
    state = context.user_data.get("state")
    if state == "awaiting_wallet_removal":
        await handle_wallet_removal(update, context)
    elif state == "awaiting_wallet":
        await handle_wallet_input(update, context)
    elif state == "awaiting_group_name":
        await handle_group_name_input(update, context)
    elif state == "editing_tag_wallet":
        await set_tag(update, context)
    else:
        await update.message.reply_text(
            "⚠️ No entiendo este comando o mensaje.\nPor favor, usa el menú principal para interactuar."
        )
        await start(update, context)

async def handle_wallet_removal(update: Update, context: CallbackContext) -> None:
    if context.user_data.get("state") == "awaiting_wallet_removal":
        group_name = context.user_data.pop("group_name", None)
        wallet_addresses = update.message.text.strip().split()
        chat_id = update.message.chat_id

        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()

        for wallet_address in wallet_addresses:
            cursor.execute('DELETE FROM wallets WHERE chat_id = ? AND group_name = ? AND wallet_address = ?', (chat_id, group_name, wallet_address))

        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Wallets eliminadas del grupo `{group_name}`.")
        await show_group_wallets(update, context, chat_id, group_name)
        context.user_data["state"] = None
    else:
        await update.message.reply_text("No hay wallets pendientes para eliminar.")

async def show_group_wallets(update: Update, context: CallbackContext, chat_id: int, group_name: str) -> None:
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_address, balance, tag FROM wallets WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
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

async def view_group(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_address, balance, tag FROM wallets WHERE chat_id = ? AND group_name = ?', (chat_id, group_name))
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

        if query.message.text != message:
            await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")
    else:
        message = f"📂 **Grupo: {group_name}**\n\n🚫 Este grupo no contiene wallets actualmente."

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Wallet", callback_data=f"add_wallet_{group_name}")],
            [InlineKeyboardButton("🔙 Regresar", callback_data="list_groups")]
        ])

        if query.message.text != message:
            await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

async def edit_tag(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args

    if len(args) < 1:
        await update.message.reply_text("⚠️ Debes proporcionar una dirección de wallet. Ejemplo: `/edit_tag <wallet_address>`")
        return

    wallet_address = args[0]

    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT tag FROM wallets WHERE chat_id = ? AND wallet_address = ?', (chat_id, wallet_address))
    existing_tag = cursor.fetchone()
    conn.close()

    if existing_tag:
        context.user_data["state"] = "editing_tag_wallet"
        context.user_data["wallet_address"] = wallet_address
        await update.message.reply_text(f"Envía el nuevo tag para la wallet: `{wallet_address}`")
    else:
        await update.message.reply_text(f"⚠️ La wallet `{wallet_address}` no se encuentra en el sistema.")

async def set_tag(update: Update, context: CallbackContext) -> None:
    if context.user_data.get("state") == "editing_tag_wallet":
        chat_id = update.message.chat_id
        wallet_address = context.user_data.pop("wallet_address")
        new_tag = update.message.text.strip()

        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE wallets SET tag = ? WHERE chat_id = ? AND wallet_address = ?', (new_tag, chat_id, wallet_address))

        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ El tag para la wallet `{wallet_address}` ha sido actualizado a: `{new_tag}`.")
        context.user_data["state"] = None
    else:
        await update.message.reply_text("⚠️ No estás editando un tag actualmente.")

async def add_wallet(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    group_name = query.data.split("_", 2)[-1]

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
        context.user_data["state"] = "awaiting_wallet"
        context.user_data["group_name"] = group_name
    else:
        await query.answer("El grupo no existe.")
        await query.edit_message_text("⚠️ El grupo ya no existe.")

async def handle_wallet_input(update: Update, context: CallbackContext) -> None:
    if context.user_data.get("state") == "awaiting_wallet":
        group_name = context.user_data.pop("group_name")
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
        await show_group_wallets(update, context, chat_id, group_name)
        context.user_data["state"] = None

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
    await list_groups(update, context)