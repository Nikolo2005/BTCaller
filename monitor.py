import asyncio
import sqlite3
from telegram.ext import Application
from database import get_solana_balance

async def monitor_wallets(application: Application) -> None:
    while True:
        # Obtener todas las wallets y sus estados de notificación en una sola consulta
        conn = sqlite3.connect('wallets.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.chat_id, g.group_name, w.wallet_address, w.tag, g.notifications_enabled
            FROM wallets w
            JOIN groups g ON w.chat_id = g.chat_id AND w.group_name = g.group_name
        ''')
        wallets = cursor.fetchall()
        conn.close()

        # Utilizar asyncio.gather para obtener los saldos en paralelo
        tasks = [fetch_and_update_balance(application, chat_id, group_name, wallet_address, tag, notifications_enabled) for chat_id, group_name, wallet_address, tag, notifications_enabled in wallets]
        await asyncio.gather(*tasks)

        await asyncio.sleep(10)

async def fetch_and_update_balance(application: Application, chat_id: int, group_name: str, wallet_address: str, tag: str, notifications_enabled: bool) -> None:
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

            if old_balance is not None and abs(new_balance - old_balance) > 0.01:
                cursor.execute(
                    'UPDATE wallets SET balance = ? WHERE chat_id = ? AND group_name = ? AND wallet_address = ?',
                    (new_balance, chat_id, group_name, wallet_address)
                )
                conn.commit()
                conn.close()

                cambio_balance = new_balance - old_balance
                tipo_de = classify_balance_change(cambio_balance)

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
            else:
                conn.close()

def classify_balance_change(cambio_balance: float) -> str:
    if cambio_balance < -0.002039:
        return "Compra de token"
    elif cambio_balance == -0.002039:
        return "Transferencia de Token"
    elif cambio_balance > -0.002039:
        return "Venta de Token"
    else:
        return "Sin Clasificación"