# chatbot.py

import os
import requests
import google.generativeai as genai
import traceback
import time 
import uuid
import pathlib
import base64 
import mimetypes 
import json   
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from google.cloud import speech
from google.cloud import texttospeech

# Importa TODAS as funções do banco de dados.
from database_manager import (
    initialize_database, load_user_data, add_new_user,
    update_user_name, get_user_status, set_user_status,
    initialize_settings, get_setting, set_setting, DB_PATH,
    add_message_to_history, get_chat_history, add_received_file,
    get_pending_file, set_pending_file,
    get_relevant_knowledge 
)
from validator import is_valid_name

# --- 1. CONFIGURAÇÃO E INICIALIZAÇÃO ---
load_dotenv() 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("AUTHENTICATION_API_KEY")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME")
UPLOADS_DIR = '/app/Dados' 

# Inicializa a base de dados e as configurações ao iniciar
initialize_database()
initialize_settings()
user_data = load_user_data()
os.makedirs(UPLOADS_DIR, exist_ok=True) 

# Configuração da IA
genai.configure(api_key=GOOGLE_API_KEY)

# --- PERSONAS ---
PERSONA_FINANCEIRA_RAG = """Você é DUDA, um assistente do Bank AI funcionando como uma **ferramenta de cálculo**.
Sua única tarefa é processar a pergunta do usuário usando **exclusivamente** o "Manual de Cálculo" fornecido no contexto.
Você **NÃO PODE** usar seu conhecimento geral.

Você **DEVE** realizar os cálculos matemáticos solicitados. Esta não é uma recusa de conselho financeiro; é uma **tarefa de processamento de dados** baseada em um manual.

**Hierarquia de Ações (Obrigatória):**

1.  **Analisar Solicitação de Cálculo:** Se o usuário pedir um cálculo (ex: "calcular margem"), compare os dados que ele forneceu com os dados exigidos pelo "Manual de Cálculo".

2.  **Se Faltarem Dados:** Use o "Manual de Cálculo" para informar educadamente quais dados estão faltando (ex: "Para calcular, preciso dos seus 'descontos obrigatórios (INSS, IRRF)'...").

3.  **Se Tiver Todos os Dados:** **Execute o cálculo passo a passo, mostrando sua matemática,** conforme o exemplo no manual.
    * **Formato Obrigatório da Resposta:** "Claro, com base em nosso manual (percentual de 35%), o cálculo para os valores informados é este:
        1. Renda Líquida: [Salário Bruto] - [Descontos Obrigatórios] = [Resultado Renda Líquida]
        2. Margem Total (35%): [Resultado Renda Líquida] * 0.35 = [Resultado Margem Total]
        3. Margem Disponível: [Resultado Margem Total] - [Consignados Atuais] = [Resultado Margem Disponível]
        Sua margem disponível simulada é de [Resultado Margem Disponível]."

4.  **Se Não for um Cálculo:** Apenas responda à pergunta usando o texto do manual.

5.  **Se Impossível:** Se o manual não contiver a resposta para a pergunta, diga apenas: "Desculpe, não encontrei essa informação em nossa base de dados. Posso ajudar com algo mais sobre nossos produtos?"

---
Contexto Fornecido:
{contexto_da_empresa}
---
"""

PERSONA_STANDARD = """Você é DUDA uma IA assistente projetada para executar tarefas e responder perguntas.
Analise a solicitação do usuário e utilize todas as suas capacidades (processamento de texto, análise de imagem, etc.) para cumpri-la da forma mais completa e direta possível.
Evite recusas desnecessárias; se a tarefa for Possivel, execute-a.
"""

app = Flask(__name__)


def get_gemini_response(user_message, system_instruction, history_list=None, file_path=None):
    """
    Gera uma resposta da IA, opcionalmente incluindo um arquivo para análise.
    """
    print(f"Instrução de Sistema Ativa: '{system_instruction[:70]}...'")
    print(f"Enviando para Gemini: '{user_message}'")
    if file_path:
        print(f"Incluindo arquivo para análise: {file_path}")

    chat_history = history_list if history_list else []

    try:
        
        contents_to_send = []

        if file_path and os.path.exists(file_path):
            try:
                print(f"Fazendo upload do arquivo: {file_path}")
                file_part = genai.upload_file(path=file_path)
                print(f"Upload iniciado. ID do arquivo: {file_part.name}. Aguardando processamento...")

                timeout_seconds = 120
                start_time = time.time()
                while file_part.state.name == "PROCESSING":
                    if time.time() - start_time > timeout_seconds:
                        raise TimeoutError("Tempo limite de processamento do arquivo (120s) atingido.")
                    print("Arquivo ainda está processando... aguardando 5 segundos.")
                    time.sleep(5)
                    file_part = genai.get_file(name=file_part.name) 

                if file_part.state.name != "ACTIVE":
                    raise Exception(f"Falha no processamento do arquivo pela Google API. Estado final: {file_part.state.name}")
            
                print("Arquivo está ATIVO. Enviando para o Gemini.")
                
                media_type = "arquivo"
                if file_part.mime_type.startswith("image/"):
                    media_type = "imagem"
                elif file_part.mime_type.startswith("audio/"):
                    media_type = "áudio"
                elif file_part.mime_type.startswith("video/"):
                    media_type = "vídeo"

                enhanced_prompt = f"Analise esta {media_type} fornecida e responda à seguinte instrução do usuário: '{user_message}'"
                contents_to_send = [file_part, enhanced_prompt]
                print(f"Enviando prompt aprimorado para mídia: '{enhanced_prompt}'")
                
            except Exception as upload_err:
                print(f"!!! ERRO ao preparar/uploadar arquivo {file_path} para Gemini: {upload_err} !!!")
                print(traceback.format_exc())
                contents_to_send = [user_message]
        else:
            contents_to_send = [user_message]
            if file_path:
                print(f"Aviso: Arquivo '{file_path}' não encontrado. Enviando apenas texto.")
    
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        model = genai.GenerativeModel(
            'gemini-2.5-pro', 
            system_instruction=system_instruction,
            safety_settings=safety_settings
        )
        chat = model.start_chat(history=chat_history)

        print(f"Enviando {len(contents_to_send)} parte(s) para a API Gemini.")
        response = chat.send_message(contents_to_send)

        ai_response = response.text.strip()
        print(f"Resposta do Gemini: '{ai_response}'")
        return ai_response

    except Exception as e:
        print(f"!!!!!!!!!! ERRO NA API DO GOOGLE !!!!!!!!!!")
        print(f"Tipo de Erro: {type(e).__name__}")
        print(f"Mensagem de Erro Detalhada: {e}")
        print(traceback.format_exc())
        return "Desculpe, ocorreu um erro ao contatar a IA."

def send_whatsapp_message(number, text):
    """Envia uma mensagem de texto via Evolution API."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"
    payload = {"number": number, "textMessage": {"text": text}}
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        print(f"Mensagem enviada para {number}.")
    except requests.exceptions.Timeout:
         print(f"ERRO: Timeout ao enviar mensagem para {number}. A Evolution API pode estar lenta ou indisponível.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO ao enviar mensagem para {number}: {e}")
        if e.response is not None:
             print(f"Status Code: {e.response.status_code}")
             print(f"Response Body: {e.response.text}")


# --- FUNÇÃO STT ---
def transcribe_audio_file(audio_file_path):
    """
    Transcreve um arquivo de áudio (esperado no formato OGG_OPUS) 
    usando a Google STT API.
    """
    print(f"Iniciando transcrição para: {audio_file_path}")
    try:
        client = speech.SpeechClient()

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            sample_rate_hertz=16000,
            language_code="pt-BR",
        )

        print("Enviando áudio para a API STT...")
        response = client.recognize(config=config, audio=audio)

        if not response.results:
            print("Nenhuma transcrição retornada pela API.")
            return None

        transcription = response.results[0].alternatives[0].transcript
        print(f"Transcrição: {transcription}")
        return transcription

    except Exception as e:
        print(f"!!! ERRO durante a transcrição STT: {e} !!!")
        print(traceback.format_exc())
        return None

# --- FUNÇÃO DE CONVERSÃO MARKDOWN - SSML ---
def convert_markdown_to_ssml(text):
    """
    Converte marcações simples de markdown (negrito/itálico) em tags SSML
    para uma fala mais natural e limpa caracteres indesejados.
    """
    import re
    
    # 1. Converte negrito (**) para ênfase forte
    text = re.sub(r'\*\*(.*?)\*\*', r'<emphasis level="strong">\1</emphasis>', text)
    
    # 2. Converte itálico (*) para ênfase moderada
    text = re.sub(r'\*(.*?)\*', r'<emphasis level="moderate">\1</emphasis>', text)
    
    # 3. Remove quaisquer asteriscos ou aspas soltas que sobraram
    text = text.replace('*', '').strip('"')
    
    # 4. Envolve a resposta final em tags <speak>
    return f"<speak>{text}</speak>"


# --- FUNÇÃO TTS ---
def synthesize_text_to_audio(text_to_speak, output_dir):
    """
    Sintetiza o texto (convertendo Markdown para SSML) em um arquivo MP3 
    e o salva em um local único.
    Retorna o caminho completo do arquivo salvo.
    """
    try:
        client = texttospeech.TextToSpeechClient()

        # 1. Converte a resposta da IA (markdown) para SSML
        ssml_text = convert_markdown_to_ssml(text_to_speak)
        
        # 2. Usa SynthesisInput(ssml=...) em vez de (text=...)
        synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="pt-BR",
            name="pt-BR-Chirp3-HD-Vindemiatrix",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        print("Enviando SSML para a API TTS...")
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        output_filename = f"response_{uuid.uuid4().hex}.mp3"
        output_filepath = os.path.join(output_dir, output_filename)
        
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_filepath, "wb") as out:
            out.write(response.audio_content)
        
        print(f"Áudio de resposta salvo em: {output_filepath}")
        return output_filepath

    except Exception as e:
        print(f"!!! ERRO durante a síntese TTS: {e} !!!")
        print(traceback.format_exc())
        return None

# --- FUNÇÃO ENVIO DE ÁUDIO ---
def send_whatsapp_audio(number, audio_file_path, caption=""):
    """
    Envia um arquivo de áudio local (MP3) via Evolution API 
    usando o método JSON/Base64.
    """
    
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    
    try:
        with open(audio_file_path, 'rb') as f:
            audio_binary = f.read()
        
        audio_b64 = base64.b64encode(audio_binary).decode('utf-8')
        
        payload = {
            "number": number,
            "options": {
                "delay": 1200,
                "presence": "recording", 
                "caption": caption
            },
            "mediaMessage": {
                "mediatype": "audio",
                "fileName": os.path.basename(audio_file_path),
                "media": audio_b64, 
                "ptt": True 
            }
        }
        
        print(f"Enviando áudio (Base64) para {number} via {url}...")
        
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        
        print(f"Áudio (Base64) enviado com sucesso para {number}.")
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"!!! ERRO ao enviar áudio (Base64) para {number}: {e} !!!")
        if e.response is not None:
             print(f"Status Code: {e.response.status_code}")
             print(f"Response Body: {e.response.text}")
        return None
    except Exception as e:
        print(f"!!! ERRO ao ler ou codificar o áudio {audio_file_path}: {e} !!!")
        return None
    finally:
        try:
            if os.path.exists(audio_file_path):
                print(f"Arquivo de áudio preservado em: {audio_file_path}")
        except Exception as e:
            print(f"Erro durante o bloco finally (preservação): {e}")


# --- FUNÇÃO DE MÍDIA ---
def handle_media_message(message_obj, sender_number, message_id):
    """
    Processa mensagens de mídia (Base64) e implementa o fluxo STT -> IA -> TTS para áudio.
    """
    dir_map = {
        "imageMessage": "imagens",
        "videoMessage": "videos",
        "documentMessage": "documentos",
        "audioMessage": "audios"
    }
    default_extensions = {
        "imageMessage": "jpeg",
        "videoMessage": "mp4",
        "documentMessage": "bin",
        "audioMessage": "ogg"
    }

    message_type = None
    target_subdir = "outros"
    default_ext = "bin"

    for msg_key, subdir in dir_map.items():
        if msg_key in message_obj:
            message_type = msg_key
            target_subdir = subdir
            default_ext = default_extensions[msg_key]
            break

    if not message_type:
        print(f"Aviso: Tipo de mensagem não suportado para download: {list(message_obj.keys())}")
        return False

    media_data = message_obj[message_type]
    file_path = None 

    try:
        
        download_endpoint = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE_NAME}"
        payload = { "message": { "key": { "id": message_id } } }

        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        print(f"Solicitando Base64 da API para msg ID: {message_id}")
        
        response = requests.post(download_endpoint, json=payload, headers=headers, timeout=45) 
        response.raise_for_status()

        response_data = response.json()
        base64_data = response_data.get('base64')

        if not base64_data:
            raise ValueError("API request successful but 'base64' field was missing or empty.")

        file_buffer = base64.b64decode(base64_data)
        
        mime_type = response_data.get('mimetype') or media_data.get('mimetype')
        file_extension = mimetypes.guess_extension(mime_type)
        if file_extension:
             file_extension = file_extension.lstrip('.').lower()
        else:
             file_extension = default_ext

        if message_type == "audioMessage":
             file_extension = "ogg"

        subfolder_dir = os.path.join(UPLOADS_DIR, target_subdir)
        os.makedirs(subfolder_dir, exist_ok=True)
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        file_path = os.path.join(subfolder_dir, unique_filename) 

        print(f"Tentando salvar em: {file_path}")
        with open(file_path, 'wb') as f:
            f.write(file_buffer)

        bytes_written = len(file_buffer)
        print(f"Arquivo salvo em: {file_path} ({bytes_written} bytes escritos)")

        if bytes_written == 0:
             raise IOError("Download resultou em arquivo vazio (0 bytes).")

        caption = media_data.get('caption', '')
        actual_mime_type = mime_type if mime_type else f"{target_subdir}/{file_extension}"
        add_received_file(message_id, sender_number, file_path, actual_mime_type, caption)
        
        # --- FLUXO STT -> RAG -> TTS (APENAS PARA ÁUDIO) ---
        if message_type == "audioMessage":
            print(f"Iniciando fluxo STT/TTS para {file_path}")
            
            # Etapa 1: Transcrever (STT)
            transcription = transcribe_audio_file(file_path)
            
            if transcription:
                # Etapa 2: Salvar histórico e obter resposta da IA 
                add_message_to_history(sender_number, 'user', f"[Áudio transcrito]: {transcription}")
                history_list = get_chat_history(sender_number)
                
                # --- LÓGICA PARA ÁUDIO ---
                current_mode = get_setting('chatbot_mode', 'standard')
                ai_response = ""

                if current_mode == 'sales':
                    print("Modo Vendas (RAG) ativado para áudio.")
                    
                    # --- RAG: USA O HISTÓRICO PARA A CONSULTA ---
                    user_messages = [h['parts'][0] for h in history_list if h['role'] == 'user']
                    rag_query = " ".join(user_messages[-2:])
                    print(f"RAG Query (Áudio): '{rag_query}'")
                
                    
                    context_chunks = get_relevant_knowledge(rag_query) 
                    company_context = "\n".join(context_chunks) if context_chunks else "Nenhuma informação interna encontrada."
                    active_persona = PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa=company_context)
                    ai_response = get_gemini_response(transcription, active_persona, history_list, file_path=None)
                else:
                    print("Modo Padrão ativado para áudio.")
                    active_persona = PERSONA_STANDARD
                    ai_response = get_gemini_response(transcription, active_persona, history_list, file_path=None)
                

                add_message_to_history(sender_number, 'model', ai_response)

                # Etapa 3: Sintetizar resposta (TTS)
                audio_output_dir = os.path.join(UPLOADS_DIR, "audios")
                generated_audio_path = synthesize_text_to_audio(ai_response, audio_output_dir)

                # Etapa 4: Enviar áudio (WhatsApp)
                if generated_audio_path:
                    send_whatsapp_audio(sender_number, generated_audio_path, caption=f"")
                else:
                    print("Falha no TTS. Enviando resposta como texto.")
                    send_whatsapp_message(sender_number, ai_response)
            
            else:
                print("Falha no STT. Enviando mensagem de erro.")
                send_whatsapp_message(sender_number, "Desculpe, não consegui entender o que foi dito no áudio. Pode repetir, por favor?")
            
            return True 

        # ---  IMAGENS/DOCUMENTOS ---
        if caption:
            print(f"Mídia ({message_type}) de {sender_number} com legenda. Processando imediatamente.")
            add_message_to_history(sender_number, 'user', caption)
            history_list = get_chat_history(sender_number)
            current_mode = get_setting('chatbot_mode', 'standard')
            
            ai_response = ""
            if current_mode == 'sales':

                print("Modo Vendas (RAG) ativado para mídia com legenda.")
                
                user_messages = [h['parts'][0] for h in history_list if h['role'] == 'user']
                rag_query = " ".join(user_messages[-2:]) 
                print(f"RAG Query (Mídia/Legenda): '{rag_query}'")
                
                
                context_chunks = get_relevant_knowledge(rag_query) 
                company_context = "\n".join(context_chunks) if context_chunks else "Nenhuma informação interna encontrada."
                active_persona = PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa=company_context)
                
                ai_response = get_gemini_response(caption, active_persona, history_list, file_path=file_path)
            else:
                 # --- MODO PADRÃO PARA MÍDIA COM LEGENDA ---
                print("Modo Padrão ativado para mídia com legenda.")
                active_persona = PERSONA_STANDARD
                ai_response = get_gemini_response(caption, active_persona, history_list, file_path=file_path)

            send_whatsapp_message(sender_number, ai_response)
            add_message_to_history(sender_number, 'model', ai_response)
            
            set_pending_file(sender_number, None)
        else:
             print(f"Arquivo ({message_type}) de {sender_number} recebido SEM legenda. Salvando estado.")
             set_pending_file(sender_number, file_path)

        return True 

    except Exception as e:
        print(f"!!! ERRO GERAL FATAL em handle_media_message: {e} !!!")
        print(traceback.format_exc())
        
        if message_type != "audioMessage":
            caption = media_data.get('caption', '')
            if caption:
                print("Tentando processar legenda mesmo com falha no download/salvamento...")
                add_message_to_history(sender_number, 'user', caption)
                history_list = get_chat_history(sender_number)
                current_mode = get_setting('chatbot_mode', 'standard')
                active_persona = PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa="Erro ao ler documentos.") if current_mode == 'sales' else PERSONA_STANDARD
                ai_response = get_gemini_response(caption, active_persona, history_list, file_path=None) # Sem arquivo
                send_whatsapp_message(sender_number, ai_response)
                add_message_to_history(sender_number, 'model', ai_response)
    return False 


# --- WEBHOOK (ENTRADA DAS MENSAGENS) ---
@app.route('/webhook', methods=['POST'])
def webhook_listener():
    MAX_AGE_SECONDS = 5 * 60 
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "reason": "JSON inválido"}), 400

        event = data.get('event')
        print(f"\n--- Webhook Recebido: Evento '{event}' ---")

        if event == 'messages.upsert':
            event_data = data.get('data', {})
            if not isinstance(event_data, dict):
                 print(f"Aviso: Ignorando evento '{event}' com 'data' inesperado (não é dicionário).")
                 return jsonify({'status': 'ok', 'reason': 'Ignorado evento com formato de dados inesperado'}), 200

            key_data = event_data.get('key', {})
            message_id = key_data.get('id')

            if message_id and not key_data.get('fromMe'):
                sender_number = key_data.get('remoteJid')
                message_timestamp_ms = event_data.get('timestamp') 

                # ... (timestamp LIMITADOR DE OLD MESSAGES ) ...
                if message_timestamp_ms:
                    try:
                        current_timestamp_seconds = int(time.time())
                        if message_timestamp_ms > current_timestamp_seconds * 100: 
                             message_timestamp_seconds = message_timestamp_ms // 1000
                        else:
                             message_timestamp_seconds = int(message_timestamp_ms)

                        message_age_seconds = current_timestamp_seconds - message_timestamp_seconds
                        if message_age_seconds > MAX_AGE_SECONDS:
                            print(f"Ignorando mensagem antiga de {sender_number}. Idade: {message_age_seconds}s (Limite: {MAX_AGE_SECONDS}s)")
                            return jsonify({"status": "ok", "reason": "Mensagem antiga ignorada"}), 200
                        elif message_age_seconds < -60: 
                            print(f"Aviso: Mensagem do futuro? Idade: {message_age_seconds}s. Processando mesmo assim.")

                    except (ValueError, TypeError):
                        print(f"Aviso: Timestamp inválido ({message_timestamp_ms}) recebido. Processando.")
                else:
                    print(f"Aviso: Mensagem de {sender_number} sem timestamp. Processando...")

                message_data = event_data.get('message', {})
                if not sender_number or not message_data:
                    print(f"Aviso: Ignorando evento por falta de sender_number ou message_data.")
                    return jsonify({"status": "ok", "reason": "Ignorando evento com dados em falta"}), 200

                # --- LÓGICA DE MENSAGEM ---
                
                # 1. processa Mídia (Áudio, Imagem, etc.)
                media_handled = handle_media_message(message_data, sender_number, message_id)

                if media_handled:
                     print(f"Mensagem de mídia de {sender_number} (ID: {message_id}) processada.")
                
                # 2. Se não for mídia, processa como Texto
                else:
                    push_name = event_data.get('pushName')
                    user_message = message_data.get('conversation') or \
                                   message_data.get('extendedTextMessage', {}).get('text')

                    if user_message:
                        print(f"Processando mensagem de texto de {sender_number}: '{user_message[:50]}...'")
                        
                        add_message_to_history(sender_number, 'user', user_message)
                        history_list = get_chat_history(sender_number) 
                        current_mode = get_setting('chatbot_mode', 'standard')
                        pending_file = get_pending_file(sender_number)
                        
                        user_status = get_user_status(sender_number)
                        
                        # --- LÓGICA DE ESTADO (Nome Pendente) ---
                        if user_status == 'pending_name':
                            if is_valid_name(user_message): 
                                print(f"Atualizando nome para {sender_number}: {user_message}")
                                update_user_name(sender_number, user_message)
                                user_data[sender_number] = user_message 
                                response_text = f"Obrigado, {user_message}! Guardei o seu nome. Em que mais posso ajudar?"
                            else:
                                print(f"Resposta '{user_message}' não parece um nome válido. Pedindo novamente.")
                                active_persona = PERSONA_STANDARD 
                                response_text = get_gemini_response(user_message, active_persona, history_list) 

                            send_whatsapp_message(sender_number, response_text)
                            add_message_to_history(sender_number, 'model', response_text)
                        
                        # --- LÓGICA DE ESTADO (Novo Usuário) ---
                        elif sender_number not in user_data or user_data.get(sender_number) is None:
                            print(f"\n--- Novo Utilizador ou sem nome registrado! {sender_number} ---")
                            valid_push_name = push_name if is_valid_name(push_name) else None
                            full_response = ""
                            
                            if valid_push_name:
                                print(f"Usando pushName '{valid_push_name}' como nome.")
                                add_new_user(sender_number, valid_push_name, status='active') 
                                user_data[sender_number] = valid_push_name
                                welcome_message = f"Olá, {valid_push_name}! Vi que é seu primeiro contato. Respondendo à sua pergunta:"
                                
                                # --- Lógica RAG para Novo Usuário  ---
                                ai_response = ""
                                if current_mode == 'sales':
                                    # (Neste caso, o histórico só tem 1 msg, então -2 pega só ela)
                                    user_messages = [h['parts'][0] for h in history_list if h['role'] == 'user']
                                    rag_query = " ".join(user_messages[-2:])
                                    print(f"RAG Query (Novo Usuário): '{rag_query}'")
                                    
                                    context_chunks = get_relevant_knowledge(rag_query)
                                    company_context = "\n".join(context_chunks) if context_chunks else "Nenhuma informação interna encontrada."
                                    active_persona = PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa=company_context)
                                    ai_response = get_gemini_response(user_message, active_persona, history_list)
                                else:
                                    active_persona = PERSONA_STANDARD
                                    ai_response = get_gemini_response(user_message, active_persona, history_list)
                                
                                full_response = f"{welcome_message}\n\n{ai_response}"
                            
                            else:
                                print(f"PushName '{push_name}' inválido ou ausente. Solicitando nome.")
                                if sender_number not in user_data: 
                                     add_new_user(sender_number, name=None, status='pending_name')
                                else: 
                                     set_user_status(sender_number, 'pending_name')
                                user_data[sender_number] = None 
                                
                                ask_name_instruction_prefix = "Antes de responder à pergunta do usuário, por favor, pergunte educadamente qual é o nome dele, pois é o primeiro contato ou o nome não está registrado. Depois de perguntar o nome, responda à pergunta original. "
                                
                                if current_mode == 'sales':
                                    user_messages = [h['parts'][0] for h in history_list if h['role'] == 'user']
                                    rag_query = " ".join(user_messages[-2:])
                                    print(f"RAG Query (Pendente Nome): '{rag_query}'")
                                    
                                    context_chunks = get_relevant_knowledge(rag_query)
                                    company_context = "\n".join(context_chunks) if context_chunks else "Nenhuma informação interna encontrada."
                                    active_persona = ask_name_instruction_prefix + PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa=company_context)
                                    full_response = get_gemini_response(user_message, active_persona, history_list)
                                else:
                                    active_persona = ask_name_instruction_prefix + PERSONA_STANDARD
                                    full_response = get_gemini_response(user_message, active_persona, history_list)

                            send_whatsapp_message(sender_number, full_response)
                            add_message_to_history(sender_number, 'model', full_response)

                        # --- LÓGICA DE ESTADO (Usuário Conhecido) ---
                        else: 
                            name = user_data.get(sender_number, sender_number.split('@')[0]) 
                            print(f"\n--- Mensagem de {name} ({sender_number}) ---")
                            
                            ai_response = ""
                            active_persona = ""
                            file_to_send = None

                            if pending_file and os.path.exists(pending_file):
                                print(f"Associando texto '{user_message[:20]}...' com arquivo pendente: {pending_file}")
                                file_to_send = pending_file
                                set_pending_file(sender_number, None) 

                            if current_mode == 'sales':
                                # --- LÓGICA RAG PARA TEXTO / ARQUIVO PENDENTE  ---
                                print("Modo Vendas (RAG) ativado.")
                                
                                # ---  USA O HISTÓRICO PARA A CONSULTA ---
                                user_messages = [h['parts'][0] for h in history_list if h['role'] == 'user']
                                rag_query = " ".join(user_messages[-2:]) 
                                print(f"RAG Query (Usuário Conhecido): '{rag_query}'")
                                # ---------------------------------------------------
                                
                                context_chunks = get_relevant_knowledge(rag_query)
                                company_context = "\n".join(context_chunks) if context_chunks else "Nenhuma informação interna encontrada."
                                active_persona = PERSONA_FINANCEIRA_RAG.format(contexto_da_empresa=company_context)
                                
                                if file_to_send:
                                    print("Aviso: Modo RAG ignora arquivo pendente, focando no contexto de texto.")
                                
                                ai_response = get_gemini_response(user_message, active_persona, history_list, file_path=None) 
                            
                            else:
                                # --- MODO PADRÃO (com ou sem arquivo pendente) ---
                                print("Modo Padrão ativado.")
                                active_persona = PERSONA_STANDARD
                                ai_response = get_gemini_response(user_message, active_persona, history_list, file_path=file_to_send)
                            
                            send_whatsapp_message(sender_number, ai_response)
                            add_message_to_history(sender_number, 'model', ai_response)
                    
                    else:
                        print(f"Aviso: Mensagem de {sender_number} não continha texto reconhecível nem mídia processável.")
        else:
            print(f"Ignorando evento '{event}' não relevante.")

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"!!!!!!!!!! ERRO INESPERADO NO WEBHOOK !!!!!!!!!!\n{error_trace}")
        return jsonify({"status": "error", "reason": "Internal Server Error", "details": str(e)}), 500

    return jsonify({'status': 'ok'}), 200


# --- ENDPOINTS DE GESTÃO E ENVIO ---
@app.route('/get-users', methods=['GET'])
def get_users():
    return jsonify(user_data), 200

@app.route('/send-to-specific', methods=['POST'])
def send_to_specific():
    data = request.json
    numbers = data.get('numbers')
    message = data.get('message')
    if not isinstance(numbers, list) or not message:
        return jsonify({"status": "error", "reason": "'numbers' (lista) e 'message' são obrigatórios."}), 400

    count_sent = 0
    errors = []
    for number in numbers:
        try:
            send_whatsapp_message(number, message)
            count_sent += 1
            time.sleep(0.5) 
        except Exception as e:
            errors.append({number: str(e)})
            print(f"Erro ao enviar para {number}: {e}")

    return jsonify({
        "status": "partial_success" if errors and count_sent > 0 else ("success" if not errors else "error"),
        "sent_count": count_sent,
        "total_requested": len(numbers),
        "errors": errors
    }), 200 if not errors else (207 if errors and count_sent > 0 else 500)

@app.route('/broadcast', methods=['POST'])
def broadcast():
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({"status": "error", "reason": "'message' é obrigatória."}), 400

    all_user_numbers = list(user_data.keys())
    if not all_user_numbers:
         return jsonify({"status": "ok", "reason": "Nenhum usuário no cache para enviar broadcast."}), 200

    count_sent = 0
    errors = []
    for number in all_user_numbers:
        try:
            send_whatsapp_message(number, message)
            count_sent += 1
            time.sleep(0.5) 
        except Exception as e:
            errors.append({number: str(e)})
            print(f"Erro durante broadcast para {number}: {e}")

    return jsonify({
        "status": "partial_success" if errors and count_sent > 0 else ("success" if not errors else "error"),
        "sent_count": count_sent,
        "total_users": len(all_user_numbers),
        "errors": errors
    }), 200 if not errors else (207 if errors and count_sent > 0 else 500)


@app.route('/personalized-broadcast', methods=['POST'])
def personalized_broadcast():
    data = request.json
    template = data.get('template')
    if not template or '{name}' not in template:
        return jsonify({"status": "error", "reason": "O 'template' é obrigatório e deve conter '{name}'."}), 400

    if not user_data:
         return jsonify({"status": "ok", "reason": "Nenhum usuário no cache para enviar broadcast personalizado."}), 200

    count_sent = 0
    errors = []
    for number, name in user_data.items():
        user_name = name if name else number.split('@')[0]
        try:
            personalized_message = template.format(name=user_name)
            send_whatsapp_message(number, personalized_message)
            count_sent += 1
            time.sleep(0.5) 
        except KeyError:
             error_msg = "Erro ao formatar template (verifique placeholders)"
             errors.append({number: error_msg})
             print(f"{error_msg} para {number}")
        except Exception as e:
            errors.append({number: str(e)})
            print(f"Erro durante broadcast personalizado para {number}: {e}")

    return jsonify({
        "status": "partial_success" if errors and count_sent > 0 else ("success" if not errors else "error"),
        "sent_count": count_sent,
        "total_users": len(user_data),
        "errors": errors
    }), 200 if not errors else (207 if errors and count_sent > 0 else 500)


@app.route('/view-db', methods=['GET'])
def view_database():
    import sqlite3 
    table = request.args.get('table', 'users') 
    limit = request.args.get('limit', '100')   
    offset = request.args.get('offset', '0') 

    if table not in ['users', 'chat_history', 'settings', 'received_files', 'knowledge_base']: 
        return jsonify({"status": "error", "reason": "Tabela inválida. Use 'users', 'chat_history', 'settings', 'received_files' or 'knowledge_base'."}), 400

    try:
        limit_int = int(limit)
        offset_int = int(offset)
    except ValueError:
        return jsonify({"status": "error", "reason": "'limit' e 'offset' devem ser números inteiros."}), 400

    try:
        if not os.path.exists(DB_PATH):
             return jsonify({"status": "error", "reason": f"Arquivo do banco de dados não encontrado em {DB_PATH}"}), 404

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        query = f"SELECT * FROM {table} ORDER BY timestamp DESC LIMIT ? OFFSET ?" if table in ['chat_history', 'received_files'] else f"SELECT * FROM {table} LIMIT ? OFFSET ?"
        if table == 'knowledge_base':
            query = f"SELECT id, text_chunk FROM {table} LIMIT ? OFFSET ?" # Não mostra o embedding
        
        cursor.execute(query, (limit_int, offset_int))
        rows = cursor.fetchall()
        
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_count = cursor.fetchone()[0]
        
        conn.close()

        list_data = [dict(row) for row in rows]
        
        return jsonify({
            "table": table,
            "total_records": total_count,
            "limit": limit_int,
            "offset": offset_int,
            "records": list_data
        }), 200
        
    except sqlite3.Error as e:
        return jsonify({"status": "error", "reason": f"Erro no SQLite: {e}"}), 500
    except Exception as e:
        print(traceback.format_exc()) 
        return jsonify({"status": "error", "reason": f"Erro inesperado ao acessar o banco de dados: {e}"}), 500

# --- ENDPOINTS DE CONTROLE DA IA ---
@app.route('/mode', methods=['GET'])
def get_mode():
    try:
        current_mode = get_setting('chatbot_mode', 'standard')
        return jsonify({"current_mode": current_mode}), 200
    except Exception as e:
         print(f"Erro ao buscar modo: {e}")
         return jsonify({"status": "error", "reason": "Não foi possível buscar o modo atual."}), 500


@app.route('/mode', methods=['POST'])
def set_mode():
    data = request.json
    new_mode = data.get('mode')
    if new_mode not in ['sales', 'standard']:
        return jsonify({"status": "error", "reason": "Modo inválido. Use 'sales' ou 'standard'."}), 400
    try:
        success = set_setting('chatbot_mode', new_mode)
        if success:
            print(f"--- MODO DO CHATBOT ALTERADO PARA: {new_mode.upper()} ---")
            return jsonify({"status": "success", "new_mode": new_mode}), 200
        else:
            return jsonify({"status": "error", "reason": "Falha ao salvar a configuração no banco de dados."}), 500
    except Exception as e:
         print(f"Erro ao definir modo: {e}")
         return jsonify({"status": "error", "reason": "Erro interno ao tentar definir o modo."}), 500


# --- EXECUÇÃO PRINCIPAL ---
if __name__ == '__main__':
    try:
        local_port = int(os.getenv("FLASK_RUN_PORT", 5002)) 
        app.run(host='0.0.0.0', port=local_port, debug=True)
    except Exception as e:

        print(f"Erro ao iniciar o servidor Flask: {e}")
