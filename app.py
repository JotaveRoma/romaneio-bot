from flask import Flask, request
import requests
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TOKEN = os.environ.get("TOKEN")
logger.info(f"TOKEN carregado: {bool(TOKEN)}")

if TOKEN:
    TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"
else:
    TELEGRAM_URL = None

@app.route("/")
def home():
    return "Bot rodando", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Recebe atualizações do Telegram"""
    try:
        # Log BRUTO de tudo que chegar
        data = request.get_json()
        logger.info("="*50)
        logger.info("RECEBIDO:")
        logger.info(data)
        logger.info("="*50)
        
        # Tenta responder qualquer coisa
        if data and TELEGRAM_URL:
            message = data.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            if chat_id:
                # Responde com eco
                text = message.get('text', 'sem texto')
                resposta = f"Eco: {text}"
                
                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": resposta
                })
                logger.info(f"Resposta enviada para {chat_id}")
        
        return "ok", 200
    except Exception as e:
        logger.error(f"ERRO: {e}")
        return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
