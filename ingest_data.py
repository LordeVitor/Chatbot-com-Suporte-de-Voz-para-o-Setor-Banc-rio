# ingest_data.py

import os
import time
import sqlite3
import google.generativeai as genai
import PyPDF2 
from dotenv import load_dotenv
from database_manager import add_knowledge, initialize_database, DB_PATH

# --- CONFIGURAÇÕES ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY não encontrada no .env")
genai.configure(api_key=GOOGLE_API_KEY)


KNOWLEDGE_SOURCE_DIR = "documentos_para_ia" 

def clear_knowledge_base():
    """Limpa a base de conhecimento antes de inserir novos dados."""
    try:
        initialize_database() 
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_base")
        conn.commit()
        conn.close()
        print("Base de conhecimento anterior foi limpa.")
    except Exception as e:
        print(f"Erro ao limpar a base de conhecimento (pode estar vazia): {e}")

def read_pdf(file_path):
    """Extrai texto de um arquivo PDF."""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            # Verifica se o PDF é baseado em imagem
            if reader.pages and reader.pages[0].get_object().get('/Resources', {}).get('/XObject'):
                 print(f"  -> Aviso: Este PDF ({os.path.basename(file_path)}) parece conter imagens complexas ou ser um scan. A extração pode falhar ou ser incompleta.")

            text = ""
            for page_num, page in enumerate(reader.pages):
                try:
                    text += page.extract_text() + "\n" 
                except Exception as page_e:
                    print(f"  -> Erro ao extrair texto da página {page_num+1} de {file_path}. Pulando página. Erro: {page_e}")
            return text if text.strip() else None
            
    except Exception as e:
        print(f"Erro ao ler PDF {file_path}: {e}")
        return None

def read_txt(file_path):
    """Extrai texto de um arquivo TXT."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Erro ao ler TXT {file_path}: {e}")
        return None

def split_text_into_chunks(text, max_chars=1000, overlap=100):
    """Divide o texto em pedaços menores (chunks) para melhor embedding."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        
        # Encontra o melhor ponto de corte (quebra de linha ou espaço)
        # quebra em parágrafo primeiro
        best_end = text.rfind('\n\n', start, end)
        if best_end == -1 or best_end < start + (max_chars * 0.5):
             best_end = text.rfind('\n', start, end)
             if best_end == -1 or best_end < start + (max_chars * 0.5):
                 best_end = text.rfind(' ', start, end)
                 if best_end == -1 or best_end < start + (max_chars * 0.5):
                     best_end = end if end <= len(text) else len(text)

        chunk = text[start:best_end].strip()
        if chunk: 
            chunks.append(chunk)
        
        if best_end == len(text):
            break 
            
        start = best_end + 1 - overlap 
        if start < 0 or start >= len(text):
            break 

    return chunks

if __name__ == "__main__":
    print("Inicializando banco de dados...")
    initialize_database()
    
    # Limpa a base antiga para evitar duplicatas
    clear_knowledge_base()

    if not os.path.exists(KNOWLEDGE_SOURCE_DIR):
        os.makedirs(KNOWLEDGE_SOURCE_DIR)
        print(f"Pasta '{KNOWLEDGE_SOURCE_DIR}' criada.")
        print("Por favor, adicione seus arquivos .txt ou .pdf (baseados em texto) nesta pasta e rode o script novamente.")
        exit()

    print(f"Iniciando ingestão da pasta: {KNOWLEDGE_SOURCE_DIR}")
    
    for filename in os.listdir(KNOWLEDGE_SOURCE_DIR):
        file_path = os.path.join(KNOWLEDGE_SOURCE_DIR, filename)
        full_text = None
        
        if filename.lower().endswith(".pdf"):
            print(f"\nProcessando PDF: {filename}")
            full_text = read_pdf(file_path)
        elif filename.lower().endswith(".txt"):
            print(f"\nProcessando TXT: {filename}")
            full_text = read_txt(file_path)
            
        if full_text:
            text_length = len(full_text)
            print(f"Texto extraído: {text_length} caracteres.")

            # Verifica se o texto é absurdamente grande
            if text_length > 50_000_000: 
                print(f"!!! AVISO: Texto extraído de '{filename}' é muito grande ({text_length}). Pulando este arquivo para evitar MemoryError.")
                continue

            try:
                chunks = split_text_into_chunks(full_text)
                print(f"Texto dividido em {len(chunks)} chunks. Enviando para embedding...")
                
                for i, chunk in enumerate(chunks):
                    success = add_knowledge(chunk)
                    if not success:
                        print(f"Falha ao processar chunk {i+1} de {filename}")
                    time.sleep(1) # (Rate Limit)
            
            except MemoryError:
                # --- CAPTURA DE ERRO ---
                print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                print(f"!!! ERRO DE MEMÓRIA ao processar os chunks de: {filename} !!!")
                print(f"!!! Este arquivo provavelmente é um SCAN ou está corrompido. !!!")
                print(f"!!! O script irá pular este arquivo e continuar.            !!!")
                print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            except Exception as e:
                print(f"!!! Erro inesperado ao processar chunks de {filename}: {e} !!!")
                
        else:
            print(f"Ignorando arquivo não suportado, vazio ou falha na leitura: {filename}")

    print("\n--- Ingestão de Dados Concluída ---")
    print(f"Sua base de conhecimento no arquivo '{DB_PATH}' foi populada com os arquivos válidos.")