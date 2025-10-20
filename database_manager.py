# database_manager.py

import sqlite3
import os

DB_PATH = '/app/data/users.db'

def initialize_database():
    """Cria a pasta e a base de dados com a tabela de utilizadores se não existirem."""
    try:
        db_dir = os.path.dirname(DB_PATH)
        os.makedirs(db_dir, exist_ok=True) # Garante que a pasta existe

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                number TEXT PRIMARY KEY,
                name TEXT,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print("Tabela 'users' inicializada com sucesso.")
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao inicializar a tabela 'users': {e} !!!")

def load_user_data():
    """
    Lê os dados da base de dados para um dicionário. Chave: número, Valor: nome.
    """
    if not os.path.exists(DB_PATH):
        initialize_database()

    user_data = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT number, name FROM users")
        rows = cursor.fetchall()
        for row in rows:
            user_data[row[0]] = row[1]
        conn.close()
        print(f"Carregados {len(user_data)} utilizadores da base de dados.")
        return user_data
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao carregar utilizadores da base de dados: {e} !!!")
        return {}

def add_new_user(number, name=None, status="active"):
    """Adiciona um novo utilizador à base de dados."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (number, name, status) VALUES (?, ?, ?)",
            (number, name, status)
        )
        conn.commit()
        conn.close()
        print(f"Novo utilizador {number} adicionado à base de dados com o nome: {name}")
        return True
    except sqlite3.IntegrityError:
        print(f"Utilizador {number} já existe na base de dados.")
        return False
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao adicionar novo utilizador: {e} !!!")
        return False

def update_user_name(number, new_name):
    """Atualiza o nome de um utilizador e define o seu estado como 'active'."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET name = ?, status = 'active' WHERE number = ?",
            (new_name, number)
        )
        conn.commit()
        conn.close()
        print(f"Nome do utilizador {number} atualizado para {new_name}.")
        return True
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao atualizar nome do utilizador: {e} !!!")
        return False

def get_user_status(number):
    """Verifica o estado de um utilizador (ex: 'pending_name')."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM users WHERE number = ?", (number,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao obter o estado do utilizador: {e} !!!")
        return None

def set_user_status(number, status):
    """Define o estado de um utilizador."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = ? WHERE number = ?", (status, number))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao definir o estado do utilizador: {e} !!!")
        return False
    
def initialize_settings():
    """Cria a tabela de configurações e garante que o modo padrão existe."""
    try:
        db_dir = os.path.dirname(DB_PATH)
        os.makedirs(db_dir, exist_ok=True) 

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Define o modo padrão como 'standard' na primeira vez
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('chatbot_mode', 'standard')")
        conn.commit()
        conn.close()
        print("Tabela 'settings' inicializada com sucesso.")
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao inicializar a tabela 'settings': {e} !!!")

def get_setting(key, default_value=None):
    """Busca o valor de uma configuração na base de dados."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default_value
    except Exception as e:
        print(f"!!! ERRO ao buscar configuração '{key}': {e} !!!")
        return default_value

def set_setting(key, value):
    """Define o valor de uma configuração na base de dados."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"!!! ERRO ao definir configuração '{key}': {e} !!!")
        return False
    