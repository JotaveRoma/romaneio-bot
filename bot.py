import os
import requests
from flask import Flask, request

TOKEN = os.environ.get("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}/"

app = Flask(__name__)

def send_message(chat_id, text):
    requests.post(
        URL + "sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        }
    )

@app.route("/", methods=["GET"])
def home():
    return "Bot rodando 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send_message(chat_id, "Bot online 🚀")

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
