from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import re
import json
from datetime import datetime, timedelta
import pytz
import logging

# ==================================================
# CONFIGURAÇÃO
# ==================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

br_tz = pytz.timezone("America/Sao_Paulo")

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise Exception("TOKEN não configurado")

TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

ARQUIVO_DADOS = "dados.json"
lock = threading.Lock()

romaneios_por_grupo = {}

# ==================================================
# TELEGRAM
# ==================================================

def enviar_mensagem(chat_id, texto):
    try:
        url = f"{TELEGRAM_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Erro Telegram: {e}")

# ==================================================
# PERSISTÊNCIA
# ==================================================

def salvar_dados():
    with lock:
        dados = {}
        for chat_id, romaneios in romaneios_por_grupo.items():
            dados[str(chat_id)] = []
            for r in romaneios:
                dados[str(chat_id)].append({
                    "cliente": r["cliente"],
                    "horario": r["horario"],
                    "horario_obj": r["horario_obj"].isoformat(),
                    "ativo": r["ativo"],
                    "ultimo_alerta": r["ultimo_alerta"].isoformat()
                })

        with open(ARQUIVO_DADOS, "w") as f:
            json.dump(dados, f)

def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        return

    with open(ARQUIVO_DADOS, "r") as f:
        dados = json.load(f)

    with lock:
        for chat_id, romaneios in dados.items():
            romaneios_por_grupo[int(chat_id)] = []
            for r in romaneios:
                romaneios_por_grupo[int(chat_id)].append({
                    "cliente": r["cliente"],
                    "horario": r["horario"],
                    "horario_obj": datetime.fromisoformat(r["horario_obj"]),
                    "ativo": r["ativo"],
                    "ultimo_alerta": datetime.fromisoformat(r["ultimo_alerta"])
                })

# ==================================================
# REGISTRAR ROMANEIO
# ==================================================

def registrar_romaneio(texto, chat_id):
    padrao = r'^/romaneio\s+([a-zA-Z0-9]+)\s+(\d{1,2}:\d{2})$'
    match = re.match(padrao, texto.strip())

    if not match:
        enviar_mensagem(chat_id, "Use: /romaneio CLIENTE HH:MM")
        return

    cliente = match.group(1).upper()
    horario_str = match.group(2)

    agora = datetime.now(br_tz)
    hora, minuto = map(int, horario_str.split(":"))

    horario_obj = br_tz.localize(datetime(
        agora.year, agora.month, agora.day,
        hora, minuto
    ))

    if horario_obj < agora:
        horario_obj += timedelta(days=1)

    romaneio = {
        "cliente": cliente,
        "horario": horario_str,
        "horario_obj": horario_obj,
        "ativo": True,
        "ultimo_alerta": agora
    }

    with lock:
        if chat_id not in romaneios_por_grupo:
            romaneios_por_grupo[chat_id] = []
        romaneios_por_grupo[chat_id].append(romaneio)

    salvar_dados()

    enviar_mensagem(chat_id,
        f"✅ <b>Romaneio registrado</b>\n\n"
        f"📦 Cliente: {cliente}\n"
        f"⏰ Horário: {horario_str}"
    )

# ==================================================
# VERIFICAÇÃO DE ALERTAS
# ==================================================

def executar_verificacao():
    agora = datetime.now(br_tz)

    with lock:
        for chat_id, romaneios in list(romaneios_por_grupo.items()):
            for romaneio in romaneios:
                if not romaneio["ativo"]:
                    continue

                horario = romaneio["horario_obj"]
                minutos = int((horario - agora).total_seconds() / 60)

                # Horário ultrapassado
                if minutos <= 0:
                    enviar_mensagem(chat_id,
                        f"⛔ <b>Horário ultrapassado</b>\n\n"
                        f"📦 Cliente: {romaneio['cliente']}"
                    )
                    romaneio["ativo"] = False

                # Alertas a cada 15 minutos na última hora
                elif minutos <= 60:
                    segundos_passados = (agora - romaneio["ultimo_alerta"]).total_seconds()

                    if segundos_passados >= 900:
                        enviar_mensagem(chat_id,
                            f"⚠️ <b>Faltam {minutos} minutos</b>\n\n"
                            f"📦 Cliente: {romaneio['cliente']}"
                        )
                        romaneio["ultimo_alerta"] = agora

        salvar_dados()

# ==================================================
# SCHEDULER LOCAL (RENDER FREE)
# ==================================================

def scheduler_background():
    while True:
        try:
            executar_verificacao()
        except Exception as e:
            logger.error(f"Erro na verificação: {e}")

        time.sleep(60)

# ==================================================
# ROTAS
# ==================================================

@app.route("/")
def home():
    return "Bot Online 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text.startswith("/romaneio"):
            registrar_romaneio(text, chat_id)

        elif text == "/listar":
            with lock:
                if chat_id in romaneios_por_grupo:
                    msg = "📋 <b>Romaneios ativos:</b>\n\n"
                    ativos = False
                    for r in romaneios_por_grupo[chat_id]:
                        if r["ativo"]:
                            ativos = True
                            msg += f"📦 {r['cliente']} - {r['horario']}\n"
                    if ativos:
                        enviar_mensagem(chat_id, msg)
                    else:
                        enviar_mensagem(chat_id, "Nenhum romaneio ativo")
                else:
                    enviar_mensagem(chat_id, "Nenhum romaneio ativo")

    return "ok", 200

@app.route("/estado")
def estado():
    return jsonify(romaneios_por_grupo), 200

# ==================================================
# INICIALIZAÇÃO
# ==================================================

carregar_dados()

threading.Thread(target=scheduler_background, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
