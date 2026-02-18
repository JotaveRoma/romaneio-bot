from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import re
from datetime import datetime, timedelta
import logging

# Configuração de logging MAIS DETALHADA
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurações do bot
TOKEN = os.environ.get("TOKEN")
logger.info(f"TOKEN carregado: {'SIM' if TOKEN else 'NÃO'}")

if not TOKEN:
    logger.error("🚨 TOKEN NÃO CONFIGURADO!")

TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"
romaneios_por_grupo = {}
lock = threading.Lock()

def enviar_mensagem(chat_id, texto):
    """Envia mensagem para um chat específico do Telegram"""
    try:
        logger.info(f"📤 Tentando enviar mensagem para {chat_id}")
        url = f"{TELEGRAM_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ Mensagem enviada para {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao enviar mensagem: {e}")
        return False

@app.route("/")
def home():
    logger.info("🏠 Home page acessada")
    return "Bot de Romaneios rodando 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        # Pega os dados recebidos
        update = request.get_json()
        
        # LOG DETALHADO
        logger.info("="*50)
        logger.info("📩 NOVA MENSAGEM RECEBIDA!")
        logger.info(f"Conteúdo: {update}")
        logger.info("="*50)
        
        # Verifica se é uma mensagem
        message = update.get('message')
        if not message:
            logger.info("📭 Não é uma mensagem, ignorando...")
            return "ok", 200
        
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        message_id = message.get('message_id')
        
        logger.info(f"👤 Chat ID: {chat_id}")
        logger.info(f"💬 Mensagem: {text}")
        
        if not chat_id:
            logger.warning("⚠️ Chat ID não encontrado")
            return "ok", 200
        
        # RESPOSTA DE TESTE - RESPONDE QUALQUER COISA
        resposta = f"✅ Mensagem recebida!\n\nVocê disse: {text}"
        enviar_mensagem(chat_id, resposta)
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"🔥 ERRO NO WEBHOOK: {e}")
        return "ok", 200

@app.route("/testar", methods=["GET"])
def testar():
    """Endpoint para testar se o bot está vivo"""
    return jsonify({
        "status": "online",
        "token_configurado": bool(TOKEN),
        "timestamp": datetime.now().isoformat()
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Iniciando bot na porta {port}")
    app.run(host="0.0.0.0", port=port)
