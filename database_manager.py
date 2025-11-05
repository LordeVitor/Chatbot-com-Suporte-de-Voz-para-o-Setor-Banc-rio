# database_manager.py

import sqlite3
import os
import time
import json 
import numpy as np
import google.generativeai as genai 

DB_PATH = '/app/data/users.db'

# ---  FUNÇÃO PARA GERAR EMBEDDINGS (VETORES) ---
def get_embedding(text_chunk):
    """Gera o embedding (vetor) para um pedaço de texto."""
    try:
        
        result = genai.embed_content(
            model="models/text-embedding-004", # Modelo de embedding do Google
            content=text_chunk,
            task_type="RETRIEVAL_DOCUMENT" 
        )
        return result['embedding']
    except Exception as e:
        print(f"!!! ERRO ao gerar embedding: {e} !!!")
        return None

def initialize_database():
    """Cria a pasta e a base de dados com as tabelas se não existirem."""
    try:
        db_dir = os.path.dirname(DB_PATH)
        os.makedirs(db_dir, exist_ok=True) 

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        

        # --- KNOWLEDGE BASE (BASE DE CONTEXTO) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_chunk TEXT NOT NULL,
                embedding BLOB NOT NULL 
            )
        ''')
        print("Tabela 'knowledge_base' inicializada com sucesso.")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                number TEXT PRIMARY KEY,
                name TEXT,
                status TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_number TEXT,
                role TEXT,
                message TEXT,
                timestamp INTEGER
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_number_timestamp 
            ON chat_history (user_number, timestamp)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS received_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                user_number TEXT,
                file_path TEXT,
                mime_type TEXT,
                caption TEXT,
                timestamp INTEGER
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_file_user_number 
            ON received_files (user_number)
        ''')
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'pending_file_path' not in columns:
                print("Adicionando coluna 'pending_file_path' à tabela 'users'...")
                cursor.execute("ALTER TABLE users ADD COLUMN pending_file_path TEXT")
        except Exception as e:
            print(f"Erro ao tentar adicionar coluna 'pending_file_path': {e}")


        conn.commit()
        conn.close()
        print("Tabela 'users' inicializada com sucesso.")
        print("Tabela 'chat_history' inicializada com sucesso.")
        print("Tabela 'received_files' inicializada com sucesso.")
    except Exception as e:
        print(f"!!! ERRO CRÍTICO ao inicializar as tabelas: {e} !!!")


# --- FUNÇÃO PARA ADICIONAR CONHECIMENTO ---
def add_knowledge(text_chunk):
    """Gera um embedding e o armazena na base de conhecimento."""
    vector = get_embedding(text_chunk)
    if vector:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            # Serializa o vetor (lista) para JSON (string) para salvar no SQLite
            vector_json = json.dumps(vector)
            cursor.execute("INSERT INTO knowledge_base (text_chunk, embedding) VALUES (?, ?)",
                           (text_chunk, vector_json))
            conn.commit()
            conn.close()
            print(f"Chunk de conhecimento adicionado: {text_chunk[:40]}...")
            return True
        except Exception as e:
            print(f"!!! ERRO ao salvar chunk no DB: {e} !!!")
            return False

# --- FUNÇÃO DE BUSCA (O RAG) ---
def get_relevant_knowledge(user_query, top_k=3):
    """Encontra os 'top_k' chunks de texto mais relevantes para a pergunta do usuário."""
    try:
        # 1. Gera o embedding para a *pergunta* do usuário
        query_vector_result = genai.embed_content(
            model="models/text-embedding-004",
            content=user_query,
            task_type="RETRIEVAL_QUERY" 
        )
        query_vector = np.array(query_vector_result['embedding'])

        # 2. Busca todos os chunks e vetores do banco
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT text_chunk, embedding FROM knowledge_base")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("Base de conhecimento está vazia. Nenhuma busca RAG realizada.")
            return []

        similarities = []
        for row in rows:
            text_chunk = row[0]
            doc_vector = np.array(json.loads(row[1]))
            
            # 3. Calcula a Similaridade de Cosseno
            similarity = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector))
            similarities.append((similarity, text_chunk))

        # 4. Ordena pela maior similaridade
        similarities.sort(key=lambda x: x[0], reverse=True)

        # 5. Retorna os 'top_k' textos mais relevantes
        relevant_chunks = [chunk for similarity, chunk in similarities[:top_k] if similarity > 0.5] 
        
        if relevant_chunks:
            print(f"RAG: Encontrados {len(relevant_chunks)} chunks relevantes para a query.")
        else:
            print("RAG: Nenhum chunk relevante encontrado.")
            
        return relevant_chunks

    except Exception as e:
        print(f"!!! ERRO durante a busca RAG: {e} !!!")
        return []


# --- FUNÇÕES DE GESTÃO DE UTILIZADORES ---

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

# --- Funções de Configurações ---

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

# --- FUNÇÕES DE HISTÓRICO DE CHAT ---

def add_message_to_history(user_number, role, message):
    """Adiciona uma mensagem (do 'user' ou 'model') ao histórico."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        current_timestamp = int(time.time())
        cursor.execute(
            "INSERT INTO chat_history (user_number, role, message, timestamp) VALUES (?, ?, ?, ?)",
            (user_number, role, message, current_timestamp)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"!!! ERRO ao salvar mensagem no histórico: {e} !!!")

def get_chat_history(user_number, limit=20):
    """
    Busca as últimas 'limit' mensagens e as formata para a API do Gemini.
    O Gemini espera o formato: [{"role": "user", "parts": ["..."]}, {"role": "model", "parts": ["..."]}]
    """
    history_list = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        query = """
            SELECT role, message FROM (
                SELECT role, message, timestamp FROM chat_history 
                WHERE user_number = ? 
                ORDER BY timestamp DESC
                LIMIT ?
            ) AS sub
            ORDER BY timestamp ASC 
        """
        cursor.execute(query, (user_number, limit))
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            history_list.append({
                "role": row[0],
                "parts": [row[1]]
            })
            
        print(f"Histórico de {user_number} carregado com {len(history_list)} mensagens.")
        return history_list
        
    except Exception as e:
        print(f"!!! ERRO ao buscar histórico do chat: {e} !!!")
        return []
    


# --- FUNÇÃO PARA REGISTAR ARQUIVOS ---
def add_received_file(message_id, user_number, file_path, mime_type, caption):
    """Adiciona o registo de um arquivo recebido na base de dados."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        current_timestamp = int(time.time())
        cursor.execute(
            """INSERT INTO received_files 
               (message_id, user_number, file_path, mime_type, caption, timestamp) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (message_id, user_number, file_path, mime_type, caption, current_timestamp)
        )
        conn.commit()
        conn.close()
        print(f"Arquivo registado na base de dados: {file_path}")
        return True
    except sqlite3.IntegrityError:
        print(f"Aviso: A mensagem com ID {message_id} já foi processada.")
        return False
    except Exception as e:
        print(f"!!! ERRO ao registar arquivo na base de dados: {e} !!!")
        return False




def get_pending_file(number):
    """Busca o caminho do arquivo pendente para um usuário."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT pending_file_path FROM users WHERE number = ?", (number,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else None
    except Exception as e:
        print(f"!!! ERRO ao obter pending_file para {number}: {e} !!!")
        return None

def set_pending_file(number, file_path):
    """Define ou limpa o caminho do arquivo pendente para um usuário."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET pending_file_path = ? WHERE number = ?", (file_path, number))
        conn.commit()
        conn.close()
        if file_path:
             print(f"Definido arquivo pendente para {number}: {file_path}")
        else:
             print(f"Limpando arquivo pendente para {number}.")
        return True
    except Exception as e:
        print(f"!!! ERRO ao definir pending_file para {number}: {e} !!!")
        return False