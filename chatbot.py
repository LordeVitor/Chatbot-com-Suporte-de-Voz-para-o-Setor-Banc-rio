# chatbot.py 

import os
import requests
import google.generativeai as genai
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Carrega .env
load_dotenv()

# Importa todas as funções para base de dados
from database_manager import (
    initialize_database, load_user_data, add_new_user,
    update_user_name, get_user_status, set_user_status,
    initialize_settings, get_setting, set_setting, DB_PATH  
)
from validator import is_valid_name

# --- 1. CONFIGURAÇÃO E INICIALIZAÇÃO ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("AUTHENTICATION_API_KEY")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME")

# Inicializa a base de dados e as configurações ao iniciar
initialize_database()
initialize_settings()
user_data = load_user_data()

# Configuração da IA
genai.configure(api_key=GOOGLE_API_KEY)

# Definição das Personalidades da IA
PERSONA_SALES = """Você é DUDA, uma assistente virtual especialista em produtos financeiros do Bank AI. Seu único objetivo é atender os clientes para vender produtos de crédito e ofertas personalizadas. REGRAS E DIRETRIZES ESTRITAS: 1. Foco Total: Responda exclusivamente sobre produtos bancários, crédito, finanças pessoais e serviços do Bank AI. 2. Redirecionamento: Se o cliente perguntar sobre qualquer outro assunto (como política, desporto, receitas, piadas, ou a sua natureza como IA), recuse educadamente e redirecione a conversa de volta para os produtos financeiros. Exemplo: "Como assistente do Bank AI, o meu foco é ajudá-lo com as suas necessidades financeiras. Gostaria de simular um crédito ou conhecer as nossas ofertas?" 3. Proatividade: Sempre que apropriado, sugira proativamente produtos do banco que possam ser úteis para o cliente. 4. Nunca saia do personagem: Você é DUDA, do Bank AI. Não é um modelo de linguagem genérico."""
PERSONA_STANDARD = """Você é DUDA, uma assistente virtual do Bank AI. Sua função é ajudar os clientes com dúvidas gerais sobre os serviços do banco de forma educada e prestativa."""

app = Flask(__name__)

# --- 2. FUNÇÕES DE IA E WHATSAPP ---

def get_gemini_response(user_message, system_instruction):
    """Gera uma resposta da IA usando uma instrução de sistema para definir a persona."""
    print(f"Instrução de Sistema Ativa: '{system_instruction[:70]}...'")
    print(f"Enviando para Gemini: '{user_message}'")
    
    try:
        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            system_instruction=system_instruction
        )
        chat = model.start_chat(history=[])
        response = chat.send_message(user_message)
        ai_response = response.text.strip()
        print(f"Resposta do Gemini: '{ai_response}'")
        return ai_response
    except Exception as e:
        print(f"!!!!!!!!!! ERRO NA API DO GOOGLE !!!!!!!!!!")
        print(f"Tipo de Erro: {type(e).__name__}")
        print(f"Mensagem de Erro Detalhada: {e}")
        return "Desculpe, ocorreu um erro ao contatar a IA."

def send_whatsapp_message(number, text):
    """Envia uma mensagem de texto via Evolution API."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"
    payload = {"number": number, "textMessage": {"text": text}}
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print(f"Mensagem enviada para {number}.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO ao enviar mensagem para {number}: {e}")

# --- 3. WEBHOOK (PONTO DE ENTRADA DAS MENSAGENS) ---
@app.route('/webhook', methods=['POST'])
def webhook_listener():
    # Determina qual persona usar com base na configuração do BD
    current_mode = get_setting('chatbot_mode', 'standard')
    active_persona = PERSONA_SALES if current_mode == 'sales' else PERSONA_STANDARD # se precisar colocar mais personas, use elif 
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "reason": "JSON inválido"}), 400

        print(f"--- Webhook Recebido: Evento '{data.get('event')}' ---")
        event_data = data.get('data', {})
        key_data = event_data.get('key', {})
        
        if (data.get('event') == 'messages.upsert' and not key_data.get('fromMe')):
            message_data = event_data.get('message', {})
            sender_number = key_data.get('remoteJid')
            
            if not sender_number or not message_data:
                return jsonify({"status": "ok", "reason": "Ignorando evento com dados em falta"}), 200

            push_name = event_data.get('pushName')
            user_message = message_data.get('conversation') or \
                           message_data.get('extendedTextMessage', {}).get('text')
            
            if user_message:
                user_status = get_user_status(sender_number)

                if user_status == 'pending_name':
                    update_user_name(sender_number, user_message)
                    user_data[sender_number] = user_message
                    send_whatsapp_message(sender_number, f"Obrigado, {user_message}! Guardei o seu nome. Em que mais posso ajudar?")
                
                elif sender_number not in user_data:
                    print(f"\n--- Novo Utilizador! {sender_number} ---")
                    if is_valid_name(push_name):
                        add_new_user(sender_number, push_name)
                        user_data[sender_number] = push_name
                        welcome_message = f"Olá, {push_name}! Vi que é seu primeiro contato. Respondendo à sua pergunta:"
                        ai_response = get_gemini_response(user_message, active_persona)
                        full_response = f"{welcome_message}\n\n{ai_response}"
                        send_whatsapp_message(sender_number, full_response)
                    else:
                        add_new_user(sender_number, status='pending_name')
                        user_data[sender_number] = None
                        # instrução para pedir o nome ao cliente ativo.
                        ask_name_instruction = "Antes de responder, por favor, pergunte educadamente o nome do utilizador. " + active_persona
                        ai_response = get_gemini_response(user_message, ask_name_instruction)
                        send_whatsapp_message(sender_number, ai_response)
                
                else:
                    name = user_data.get(sender_number, sender_number)
                    print(f"\n--- Mensagem de {name} ---")
                    ai_response = get_gemini_response(user_message, active_persona)
                    send_whatsapp_message(sender_number, ai_response)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"!!!!!!!!!! ERRO INESPERADO NO WEBHOOK !!!!!!!!!!\n{error_trace}")
        return jsonify({"status": "error", "reason": "Internal Server Error", "trace": str(e)}), 500

    return jsonify({'status': 'ok'}), 200

# --- 4. ENDPOINTS DE GESTÃO E ENVIO ---

@app.route('/get-users', methods=['GET'])
def get_users():
    all_users = load_user_data()
    return jsonify(all_users), 200

@app.route('/send-to-specific', methods=['POST'])
def send_to_specific():
    data = request.json
    numbers, message = data.get('numbers'), data.get('message')
    if not numbers or not message:
        return jsonify({"status": "error", "reason": "'numbers' e 'message' são obrigatórios."}), 400
    for number in numbers:
        send_whatsapp_message(number, message)
    return jsonify({"status": "success", "recipients_count": len(numbers)}), 200

@app.route('/broadcast', methods=['POST'])
def broadcast():
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({"status": "error", "reason": "'message' é obrigatória."}), 400
    all_users = load_user_data()
    for number in all_users.keys():
        send_whatsapp_message(number, message)
    return jsonify({"status": "success", "recipients_count": len(all_users)}), 200

@app.route('/personalized-broadcast', methods=['POST'])
def personalized_broadcast():
    data = request.json
    template = data.get('template')
    if not template or '{name}' not in template:
        return jsonify({"status": "error", "reason": "O 'template' deve conter '{name}'."}), 400
    all_users = load_user_data()
    for number, name in all_users.items():
        user_name = name if name else number 
        personalized_message = template.format(name=user_name)
        send_whatsapp_message(number, personalized_message)
    return jsonify({"status": "success", "recipients_count": len(all_users)}), 200

@app.route('/view-db', methods=['GET'])
def view_database():
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH) 
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        conn.close()
        users_list = [dict(row) for row in rows]
        return jsonify(users_list), 200
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 500

# --- 5. ENDPOINTS DE CONTROLE DA IA ---

@app.route('/mode', methods=['GET'])
def get_mode():
    current_mode = get_setting('chatbot_mode', 'standard')
    return jsonify({"current_mode": current_mode}), 200

@app.route('/mode', methods=['POST'])
def set_mode():
    data = request.json
    new_mode = data.get('mode')
    if new_mode not in ['sales', 'standard']: # lembrar de adicionar o endpoint da nova persona aqui se for adicionar. 
        return jsonify({"status": "error", "reason": "Modo inválido. Use 'sales' ou 'standard'."}), 400 # atualizar aq tbm. 
    set_setting('chatbot_mode', new_mode)
    print(f"--- MODO DO CHATBOT ALTERADO PARA: {new_mode.upper()} ---")
    return jsonify({"status": "success", "new_mode": new_mode}), 200