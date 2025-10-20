import requests

url = "http://127.0.0.1:8080/message/sendText/BANK_AI"

payload = {
    "number": "5519997420975",
    "options": {
        "delay": 123,
        "presence": "composing",
        "linkPreview": True,
        "quoted": {
            "key": {
                "remoteJid": "<string>",
                "fromMe": True,
                "id": "<string>",
                "participant": "<string>"
            },
            "message": { "conversation": "Teste" }
        },
        
    },
    "textMessage": { "text": "OLÁ ALUNO" }
}
headers = {
    "apikey": "997420975",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.json())