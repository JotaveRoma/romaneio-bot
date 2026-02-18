from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import re
from datetime import datetime, timedelta
import logging

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ===== CONFIGURAÇÕES =====
# Token do bot (configurado nas variáveis de ambiente do Render)
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    logger.error("🚨 TOKEN NÃO CONFIGURADO!")
else:
    logger.info("✅ TOKEN configurado com sucesso!")

# URL da API do Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

# IDs dos grupos para alertas automáticos (opcional)
CHAT_IDS = os.environ.get("CHAT_IDS", "")
if CHAT_IDS:
    CHAT_IDS = [chat_id.strip() for chat_id in CHAT_IDS.split(",") if chat_id.strip()]
    logger.info(f"✅ Grupos configurados: {CHAT_IDS}")
else:
    CHAT_IDS = []
    logger.info("ℹ️ Nenhum grupo configurado para alertas automáticos")

# ===== ESTRUTURA DE DADOS =====
# Dicionário para armazenar os romaneios por grupo
# Estrutura: { chat_id: [romaneios] }
romaneios_por_grupo = {}
lock = threading.Lock()

# ===== FUNÇÕES DO TELEGRAM =====
def enviar_mensagem(chat_id, texto):
    """Envia mensagem para um chat específico do Telegram"""
    try:
        logger.info(f"📤 Enviando mensagem para {chat_id}")
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

def enviar_para_todos(texto):
    """Envia mensagem para todos os grupos configurados em CHAT_IDS"""
    if not CHAT_IDS:
        logger.warning("⚠️ Nenhum grupo configurado em CHAT_IDS")
        return
    
    for chat_id in CHAT_IDS:
        enviar_mensagem(chat_id, texto)

# ===== PROCESSAMENTO DE COMANDOS =====
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
        
        agora = datetime.now()
        horario_obj = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        
        # Se já passou, agenda para amanhã
        if horario_obj < agora:
            horario_obj = horario_obj + timedelta(days=1)
            
    except Exception as e:
        enviar_mensagem(chat_id, "❌ Horário inválido! Use formato HH:MM (ex: 15:00)")
        logger.error(f"Erro no horário: {e}")
        return
    
    # Calcular tempo até o horário
    agora = datetime.now()
    minutos_restantes = int((horario_obj - agora).total_seconds() / 60)
    
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
    
    logger.info(f"✅ Romaneio registrado: {cliente} às {horario_str} no grupo {chat_id}")

def processar_mensagem(update):
    """Processa uma mensagem recebida"""
    try:
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        message_id = message.get('message_id')
        
        if not chat_id or not text:
            return
        
        logger.info(f"📨 Mensagem de {chat_id}: {text}")
        
        # Comando /start
        if text == '/start':
            enviar_mensagem(chat_id, 
                "🤖 <b>Bot de Romaneios</b>\n\n"
                "Comandos disponíveis:\n\n"
                "📝 <b>/romaneio [cliente] [horário]</b>\n"
                "Ex: /romaneio honda 15:00\n\n"
                "📋 <b>/listar</b> - Ver romaneios ativos\n"
                "❌ <b>/cancelar [cliente]</b> - Cancelar romaneio\n"
                "🆘 <b>/ajuda</b> - Mostrar ajuda\n"
                "🏓 <b>/ping</b> - Testar bot"
            )
        
        # Comando /ping (teste)
        elif text == '/ping':
            enviar_mensagem(chat_id, "pong 🏓")
        
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
                return
            
            with lock:
                encontrou = False
                if chat_id in romaneios_por_grupo:
                    for r in romaneios_por_grupo[chat_id]:
                        if r['cliente'] == cliente and r['ativo']:
                            r['ativo'] = False
                            enviar_mensagem(chat_id, f"✅ Romaneio da {cliente} cancelado!")
                            encontrou = True
                            break
                if not encontrou:
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
                "4️⃣ <b>Testar:</b>\n"
                "/ping\n\n"
                "⚠️ Alertas automáticos a cada 15 minutos"
            )
        
        # Mensagem não reconhecida (só para teste)
        else:
            enviar_mensagem(chat_id, f"Comando não reconhecido. Envie /ajuda para ver os comandos disponíveis.")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

# ===== THREAD DE VERIFICAÇÃO DE ALERTAS =====
def verificar_alertas():
    """Thread principal que verifica e envia alertas"""
    logger.info("🔄 Thread de verificação de alertas iniciada")
    
    while True:
        try:
            agora = datetime.now()
            
            with lock:
                for chat_id, romaneios in list(romaneios_por_grupo.items()):
                    for romaneio in romaneios[:]:  # Cópia para iteração segura
                        if not romaneio['ativo']:
                            continue
                        
                        horario = romaneio['horario_obj']
                        cliente = romaneio['cliente']
                        
                        # Se já passou do horário
                        if agora > horario:
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
                        
                        # Alertas nos minutos específicos
                        minutos_para_alerta = [60, 45, 30, 15, 5, 1]
                        
                        for minutos in minutos_para_alerta:
                            if minutos_restantes <= minutos and romaneio['alertas_enviados'] < minutos:
                                # Evita enviar múltiplos alertas no mesmo minuto
                                tempo_desde_ultimo = (agora - romaneio['ultimo_alerta']).total_seconds() / 60
                                if tempo_desde_ultimo >= 1:
                                    if minutos_restantes <= 1:
                                        msg_alerta = f"🔥 <b>SAIR AGORA! ÚLTIMO MINUTO!</b> 🔥"
                                    elif minutos_restantes <= 5:
                                        msg_alerta = f"🔥 <b>ÚLTIMOS {minutos_restantes} MINUTOS! SAIR AGORA!</b> 🔥"
                                    elif minutos_restantes <= 15:
                                        msg_alerta = f"⚠️ <b>FALTAM {minutos_restantes} MINUTOS! PREPARAR PARA SAÍDA!</b>"
                                    else:
                                        msg_alerta = f"⚡ <b>FALTAM {minutos_restantes} MINUTOS</b>"
                                    
                                    mensagem = (
                                        f"🚨 <b>ALERTA DE SAÍDA</b> 🚨\n\n"
                                        f"📦 <b>Cliente:</b> {cliente}\n"
                                        f"⏰ <b>Horário limite:</b> {romaneio['horario']}\n"
                                        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
                                        f"{msg_alerta}"
                                    )
                                    enviar_mensagem(chat_id, mensagem)
                                    romaneio['ultimo_alerta'] = agora
                                    romaneio['alertas_enviados'] = minutos
                                    break
                        
        except Exception as e:
            logger.error(f"Erro na verificação de alertas: {e}")
        
        time.sleep(15)  # Verifica a cada 15 segundos

# ===== ROTAS DO FLASK =====
@app.route("/")
def home():
    return "🤖 Bot de Romaneios rodando! 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        # Pega os dados recebidos
        update = request.get_json()
        
        # Log da mensagem recebida
        logger.info("="*50)
        logger.info("📩 MENSAGEM RECEBIDA DO TELEGRAM")
        logger.info(f"Conteúdo: {update}")
        logger.info("="*50)
        
        # Processa a mensagem em uma thread separada para não travar o webhook
        if update:
            threading.Thread(target=processar_mensagem, args=(update,)).start()
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"🔥 ERRO NO WEBHOOK: {e}")
        return "ok", 200

@app.route("/testar", methods=["GET"])
def testar():
    """Endpoint para verificar se o bot está vivo"""
    return jsonify({
        "status": "online",
        "token_configurado": bool(TOKEN),
        "grupos_configurados": len(CHAT_IDS),
        "romaneios_ativos": sum(len(r) for r in romaneios_por_grupo.values()),
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/api/testar", methods=["POST"])
def api_testar():
    """Endpoint para testar o envio de alertas"""
    mensagem = "🧪 <b>ALERTA DE TESTE</b>\n\nSistema de notificações funcionando corretamente!"
    
    # Envia para todos os grupos configurados
    for chat_id in CHAT_IDS:
        enviar_mensagem(chat_id, mensagem)
    
    return jsonify({
        "mensagem": "Alertas de teste enviados",
        "grupos": len(CHAT_IDS)
    }), 200

# ===== INICIALIZAÇÃO =====
# Inicia a thread de verificação se o token estiver configurado
if TOKEN:
    threading.Thread(target=verificar_alertas, daemon=True).start()
    logger.info("✅ Sistema iniciado com sucesso!")
else:
    logger.error("🚨 BOT NÃO INICIADO - Token não configurado!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Servidor rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)
