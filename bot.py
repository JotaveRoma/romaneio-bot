from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.environ.get("TOKEN")

def enviar_mensagem(chat_id, texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto
    }
    requests.post(url, json=payload)

@app.route("/")
def home():
    return "Bot rodando 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        texto = data["message"].get("text")

        if texto == "/start":
            enviar_mensagem(chat_id, "Bot online 🚀")

    return "ok", 200
