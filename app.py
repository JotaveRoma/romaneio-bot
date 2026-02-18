from flask import Flask, request
import requests
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TOKEN = os.environ.get("TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

@app.route("/")
def home():
    return "✅ Bot OK", 200

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """Aceita POST e GET para debug"""
    
    # Se for GET, mostra instruções
    if request.method == "GET":
        return """
        <h2>Webhook do Telegram</h2>
        <p>Este endpoint deve receber POST.</p>
        <p>Status: ✅ Funcionando</p>
        """, 200
    
    # Se for POST, processa
    try:
        data = request.get_json()
        logger.info(f"📩 RECEBIDO: {data}")
        
        # Responde qualquer coisa
        if data and 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            
            # Envia resposta
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"Eco: {text}"
            })
        
        return "ok", 200
    except Exception as e:
        logger.error(f"ERRO: {e}")
        return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
