import os
import requests
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evolution-api:8080")
INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "BANK_AI")

def send_media(to: str, file_url: str, caption: str = ""):
    url = f"{EVOLUTION_API_URL}/message/{INSTANCE_NAME}/media"
    payload = {
        "to": to,
        "fileUrl": file_url,
        "caption": caption,
    }
    r = requests.post(url, json=payload)
    return r.json()

if __name__ == "__main__":
    print(send_media("5511999999999", "https://via.placeholder.com/150", "Teste de mídia"))
