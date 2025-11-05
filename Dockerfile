# Dockerfile

FROM python:3.9-slim

#conteiner flask
WORKDIR /app


COPY requirements.txt .


RUN pip install --no-cache-dir -r requirements.txt


COPY . .


CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--timeout", "180", "chatbot:app"]