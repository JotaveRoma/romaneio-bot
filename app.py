from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import re
from datetime import datetime, timedelta
import logging

app = Flask(__name__)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações do bot
TOKEN = os.environ.get("8266798738:AAFbrE5F14O89ifWJXeW9OSnTvD-mFZfkUw")
if not TOKEN:
    logger.error("Token do Telegram não configurado!")

# URL base da API do Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

# Dicionário para armazenar os romaneios ativos
# Estrutura: { "grupo_id": [romaneios] }
romaneios_por_grupo = {}

# Lock para thread safety
lock = threading.Lock()

def enviar_mensagem(chat_id, texto):
    """Envia mensagem para um chat específico do Telegram"""
    try:
        url = f"{TELEGRAM_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Mensagem enviada para {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return False

def processar_comando_romaneio(texto, chat_id, message_id):
    """Processa o comando /romaneio"""
    # Padrão: /romaneio [cliente] [horario]
    # Exemplo: /romaneio honda 15:00
    padrao = r'^/romaneio\s+([a-zA-Z0-9]+)\s+(\d{1,2}:\d{2})$'
    match = re.match(padrao, texto.strip())
    
    if not match:
        enviar_mensagem(chat_id, 
            "❌ <b>Formato incorreto!</b>\n\n"
            "Use: /romaneio [cliente] [horário]\n"
            "Exemplo: /romaneio honda 15:00"
        )
        return
    
    cliente = match.group(1).upper()
    horario_str = match.group(2)
    
    # Validar horário
    try:
        hora, minuto = map(int, horario_str.split(':'))
        if hora < 0 or hora > 23 or minuto < 0 or minuto > 59:
            raise ValueError
        horario_obj = datetime.now().replace(hour=hora, minute=minuto, second=0, microsecond=0)
    except:
        enviar_mensagem(chat_id, "❌ Horário inválido! Use formato HH:MM (ex: 15:00)")
        return
    
    # Calcular tempo até o horário
    agora = datetime.now()
    if horario_obj < agora:
        horario_obj = horario_obj + timedelta(days=1)  # Se já passou, considera amanhã
    
    tempo_restante = horario_obj - agora
    minutos_restantes = int(tempo_restante.total_seconds() / 60)
    
    # Criar novo romaneio
    romaneio = {
        'cliente': cliente,
        'horario': horario_str,
        'horario_obj': horario_obj,
        'chat_id': chat_id,
        'message_id': message_id,
        'criado_em': agora,
        'ultimo_alerta': agora,
        'alertas_enviados': 0,
        'ativo': True
    }
    
    with lock:
        if chat_id not in romaneios_por_grupo:
            romaneios_por_grupo[chat_id] = []
        romaneios_por_grupo[chat_id].append(romaneio)
    
    # Mensagem de confirmação
    resposta = (
        f"✅ <b>ROMANEIO REGISTRADO</b>\n\n"
        f"📦 <b>Cliente:</b> {cliente}\n"
        f"⏰ <b>Horário limite:</b> {horario_str}\n"
        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
        f"⚠️ <i>Alertas serão enviados a cada 15 minutos</i>"
    )
    enviar_mensagem(chat_id, resposta)
    
    logger.info(f"Romaneio registrado: {cliente} às {horario_str} no grupo {chat_id}")

def verificar_alertas():
    """Thread principal que verifica e envia alertas"""
    while True:
        try:
            agora = datetime.now()
            
            with lock:
                for chat_id, romaneios in romaneios_por_grupo.items():
                    for romaneio in romaneios[:]:  # Cópia para iteração segura
                        if not romaneio['ativo']:
                            continue
                        
                        horario = romaneio['horario_obj']
                        cliente = romaneio['cliente']
                        ultimo_alerta = romaneio['ultimo_alerta']
                        
                        # Se já passou do horário
                        if agora > horario:
                            # Avisar que passou do limite
                            mensagem = (
                                f"⛔ <b>HORÁRIO ULTRAPASSADO</b> ⛔\n\n"
                                f"📦 <b>Cliente:</b> {cliente}\n"
                                f"⏰ <b>Horário limite:</b> {romaneio['horario']}\n\n"
                                f"⚠️ O horário de saída já passou!"
                            )
                            enviar_mensagem(chat_id, mensagem)
                            romaneio['ativo'] = False
                            continue
                        
                        # Calcular minutos até o horário
                        minutos_restantes = int((horario - agora).total_seconds() / 60)
                        
                        # Verificar se precisa enviar alerta (a cada 15 minutos)
                        tempo_desde_ultimo = (agora - ultimo_alerta).total_seconds() / 60
                        
                        # Enviar alertas nos minutos específicos: 60, 45, 30, 15, 5
                        minutos_para_alerta = [60, 45, 30, 15, 5]
                        
                        for minutos in minutos_para_alerta:
                            if minutos_restantes <= minutos and romaneio['alertas_enviados'] < minutos:
                                # Evita enviar múltiplos alertas no mesmo minuto
                                if tempo_desde_ultimo >= 1:  # Mínimo 1 minuto entre alertas
                                    mensagem = (
                                        f"🚨 <b>ALERTA DE SAÍDA</b> 🚨\n\n"
                                        f"📦 <b>Cliente:</b> {cliente}\n"
                                        f"⏰ <b>Horário limite:</b> {romaneio['horario']}\n"
                                        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
                                    )
                                    
                                    if minutos_restantes <= 5:
                                        mensagem += "🔥 <b>ÚLTIMOS MINUTOS! SAIR AGORA!</b> 🔥"
                                    elif minutos_restantes <= 15:
                                        mensagem += "⚠️ <b>PREPARAR PARA SAÍDA IMEDIATA!</b>"
                                    else:
                                        mensagem += "⚡ <b>FIQUE ATENTO AO HORÁRIO!</b>"
                                    
                                    enviar_mensagem(chat_id, mensagem)
                                    romaneio['ultimo_alerta'] = agora
                                    romaneio['alertas_enviados'] = minutos
                                    break
                        
                        # Quando faltam 5 minutos, marca como último alerta
                        if minutos_restantes <= 5 and minutos_restantes > 0:
                            if romaneio['alertas_enviados'] < 5:
                                # Já vai ser pego pelo loop acima
                                pass
                        
        except Exception as e:
            logger.error(f"Erro na verificação de alertas: {e}")
        
        time.sleep(30)  # Verifica a cada 30 segundos

@app.route("/")
def home():
    return "Bot de Romaneios rodando 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        update = request.get_json()
        
        # Processa mensagens
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        message_id = message.get('message_id')
        
        if not chat_id or not text:
            return "ok", 200
        
        # Comando /start
        if text == '/start':
            enviar_mensagem(chat_id, 
                "🤖 <b>Bot de Romaneios</b>\n\n"
                "Comandos disponíveis:\n\n"
                "📝 <b>/romaneio [cliente] [horário]</b>\n"
                "Ex: /romaneio honda 15:00\n\n"
                "📋 <b>/listar</b> - Ver romaneios ativos\n"
                "❌ <b>/cancelar [cliente]</b> - Cancelar romaneio\n"
                "🆘 <b>/ajuda</b> - Mostrar esta mensagem"
            )
        
        # Comando /romaneio
        elif text.startswith('/romaneio'):
            processar_comando_romaneio(text, chat_id, message_id)
        
        # Comando /listar
        elif text == '/listar':
            with lock:
                if chat_id in romaneios_por_grupo and romaneios_por_grupo[chat_id]:
                    msg = "📋 <b>ROMANEIOS ATIVOS</b>\n\n"
                    for r in romaneios_por_grupo[chat_id]:
                        if r['ativo']:
                            msg += f"📦 {r['cliente']} - ⏰ {r['horario']}\n"
                    enviar_mensagem(chat_id, msg)
                else:
                    enviar_mensagem(chat_id, "✅ Nenhum romaneio ativo no momento")
        
        # Comando /cancelar
        elif text.startswith('/cancelar'):
            cliente = text.replace('/cancelar', '').strip().upper()
            if not cliente:
                enviar_mensagem(chat_id, "❌ Use: /cancelar [cliente]\nEx: /cancelar honda")
                return "ok", 200
            
            with lock:
                if chat_id in romaneios_por_grupo:
                    for r in romaneios_por_grupo[chat_id]:
                        if r['cliente'] == cliente and r['ativo']:
                            r['ativo'] = False
                            enviar_mensagem(chat_id, f"✅ Romaneio da {cliente} cancelado!")
                            break
                    else:
                        enviar_mensagem(chat_id, f"❌ Romaneio da {cliente} não encontrado")
        
        # Comando /ajuda
        elif text == '/ajuda':
            enviar_mensagem(chat_id,
                "🆘 <b>AJUDA</b>\n\n"
                "1️⃣ <b>Registrar romaneio:</b>\n"
                "/romaneio [cliente] [horário]\n"
                "Ex: /romaneio honda 15:00\n\n"
                "2️⃣ <b>Ver romaneios:</b>\n"
                "/listar\n\n"
                "3️⃣ <b>Cancelar:</b>\n"
                "/cancelar [cliente]\n\n"
                "⚠️ Alertas automáticos a cada 15 minutos"
            )
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return "ok", 200

@app.route("/status", methods=["GET"])
def status():
    """Endpoint para verificar status do bot"""
    total = 0
    ativos = 0
    with lock:
        for chat_id, romaneios in romaneios_por_grupo.items():
            total += len(romaneios)
            ativos += sum(1 for r in romaneios if r['ativo'])
    
    return jsonify({
        "status": "online",
        "grupos_ativos": len(romaneios_por_grupo),
        "romaneios_total": total,
        "romaneios_ativos": ativos
    }), 200

# Inicia a thread de verificação
if TOKEN:
    threading.Thread(target=verificar_alertas, daemon=True).start()
    logger.info("Thread de verificação iniciada")
else:
    logger.warning("Token não configurado")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
