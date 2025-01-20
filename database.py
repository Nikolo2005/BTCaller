import sqlite3
from solders.pubkey import Pubkey
import requests
import re

def init_db():
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
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

def save_group(chat_id, group_name):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO groups (chat_id, group_name) VALUES (?, ?)', (chat_id, group_name))
    conn.commit()
    conn.close()

def save_wallet(chat_id, group_name, wallet_address, balance, tag=None):
    conn = sqlite3.connect('wallets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO wallets (chat_id, group_name, wallet_address, balance, tag) VALUES (?, ?, ?, ?, ?)',
                   (chat_id, group_name, wallet_address, balance, tag))
    conn.commit()
    conn.close()

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

def is_valid_solana_wallet(wallet_address: str) -> bool:
    try:
        Pubkey.from_string(wallet_address)
        return True
    except Exception:
        return False

def is_valid_group_name(group_name: str) -> bool:
    if len(group_name) > 50:
        return False
    if not re.match("^[a-zA-Z0-9_ -]*$", group_name):
        return False
    return True