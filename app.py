from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import re
from datetime import datetime, timedelta
import pytz
import logging

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== CRIAÇÃO DO APP FLASK =====
app = Flask(__name__)

# ===== CONFIGURAÇÕES DE FUSO HORÁRIO =====
br_tz = pytz.timezone('America/Sao_Paulo')
logger.info(f"🇧🇷 Fuso horário configurado: {br_tz}")

# ===== CONFIGURAÇÕES DO BOT =====
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    logger.error("🚨 TOKEN NÃO CONFIGURADO!")
else:
    logger.info("✅ TOKEN configurado com sucesso!")

TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}"

CHAT_IDS = os.environ.get("CHAT_IDS", "")
if CHAT_IDS:
    CHAT_IDS = [chat_id.strip() for chat_id in CHAT_IDS.split(",") if chat_id.strip()]
    logger.info(f"✅ Grupos configurados: {CHAT_IDS}")
else:
    CHAT_IDS = []
    logger.info("ℹ️ Nenhum grupo configurado para alertas automáticos")

# ===== ESTRUTURA DE DADOS =====
romaneios_por_grupo = {}
lock = threading.Lock()

# ===== SISTEMA ANTI-SONO =====
def manter_acordado():
    """Thread que mantém o bot acordado pingando a si mesmo"""
    logger.info("💤 SISTEMA ANTI-SONO ATIVADO - O bot não vai mais dormir!")
    
    while True:
        try:
            # Pings a cada 10 minutos
            time.sleep(600)  # 10 minutos = 600 segundos
            
            # Ping no próprio servidor
            url = "https://romaneio-bot.onrender.com/"
            response = requests.get(url, timeout=30)
            logger.info(f"⏰ Ping anti-sono: {response.status_code}")
            
        except Exception as e:
            logger.error(f"❌ Erro no anti-sono: {e}")

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

# ===== FUNÇÃO DE ALERTA =====
def enviar_alerta(romaneio, chat_id, cliente, minutos_restantes):
    """Função auxiliar para enviar alertas formatados"""
    if minutos_restantes <= 1:
        msg_alerta = f"🔥 <b>SAIR AGORA! ÚLTIMO MINUTO!</b> 🔥"
    elif minutos_restantes <= 5:
        msg_alerta = f"🔥 <b>ÚLTIMOS {minutos_restantes} MINUTOS! SAIR AGORA!</b> 🔥"
    elif minutos_restantes <= 15:
        msg_alerta = f"⚠️ <b>FALTAM {minutos_restantes} MINUTOS! PREPARAR PARA SAÍDA!</b>"
    else:
        msg_alerta = f"⚡ <b>FALTAM {minutos_restantes} MINUTOS PARA O HORÁRIO LIMITE</b>"
    
    horario_br = romaneio['horario_obj'].astimezone(br_tz).strftime('%H:%M')
    
    mensagem = (
        f"🚨 <b>ALERTA DE SAÍDA</b> 🚨\n\n"
        f"📦 <b>Cliente:</b> {cliente}\n"
        f"⏰ <b>Horário limite:</b> {horario_br} (horário BR)\n"
        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
        f"{msg_alerta}"
    )
    enviar_mensagem(chat_id, mensagem)
    logger.info(f"✅ Alerta enviado para {cliente} - faltam {minutos_restantes} min (BR)")

# ===== PROCESSAMENTO DE COMANDOS =====
def processar_comando_romaneio(texto, chat_id, message_id):
    """Processa o comando /romaneio com horário BR"""
    padrao = r'^/romaneio\s+([a-zA-Z0-9]+)\s+(\d{1,2}:\d{2})$'
    match = re.match(padrao, texto.strip())
    
    if not match:
        enviar_mensagem(chat_id, 
            "❌ <b>Formato incorreto!</b>\n\n"
            "Use: /romaneio [cliente] [horário]\n"
            "Exemplo: /romaneio honda 15:00\n\n"
            "⚠️ <i>Horário no formato BR (24h)</i>"
        )
        return
    
    cliente = match.group(1).upper()
    horario_str = match.group(2)
    
    try:
        hora, minuto = map(int, horario_str.split(':'))
        if hora < 0 or hora > 23 or minuto < 0 or minuto > 59:
            raise ValueError
        
        agora = datetime.now(br_tz)
        horario_obj = br_tz.localize(datetime(
            agora.year, agora.month, agora.day,
            hora, minuto, 0, 0
        ))
        
        if horario_obj < agora:
            horario_obj = horario_obj + timedelta(days=1)
            logger.info(f"📅 Horário {horario_str} já passou hoje, agendado para amanhã")
            
    except Exception as e:
        enviar_mensagem(chat_id, "❌ Horário inválido! Use formato HH:MM (ex: 15:00)")
        logger.error(f"Erro no horário: {e}")
        return
    
    agora = datetime.now(br_tz)
    minutos_restantes = int((horario_obj - agora).total_seconds() / 60)
    
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
    
    resposta = (
        f"✅ <b>ROMANEIO REGISTRADO</b>\n\n"
        f"📦 <b>Cliente:</b> {cliente}\n"
        f"⏰ <b>Horário limite:</b> {horario_str} (horário BR)\n"
        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
        f"⚠️ <i>Alertas serão enviados a cada 15 minutos (horário BR)</i>"
    )
    enviar_mensagem(chat_id, resposta)
    logger.info(f"✅ Romaneio registrado: {cliente} às {horario_str} BR no grupo {chat_id}")

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
        
        if text == '/start':
            enviar_mensagem(chat_id, 
                "🤖 <b>Bot de Romaneios</b>\n\n"
                "Comandos disponíveis:\n\n"
                "📝 <b>/romaneio [cliente] [horário]</b>\n"
                "Ex: /romaneio honda 15:00 (horário BR)\n\n"
                "📋 <b>/listar</b> - Ver romaneios ativos\n"
                "❌ <b>/cancelar [cliente]</b> - Cancelar romaneio\n"
                "🆘 <b>/ajuda</b> - Mostrar ajuda\n"
                "🏓 <b>/ping</b> - Testar bot\n\n"
                "🇧🇷 <i>Horários no fuso de Brasília</i>"
            )
        
        elif text == '/ping':
            enviar_mensagem(chat_id, "pong 🏓")
        
        elif text.startswith('/romaneio'):
            processar_comando_romaneio(text, chat_id, message_id)
        
        elif text == '/listar':
            with lock:
                if chat_id in romaneios_por_grupo and romaneios_por_grupo[chat_id]:
                    msg = "📋 <b>ROMANEIOS ATIVOS (horário BR)</b>\n\n"
                    for r in romaneios_por_grupo[chat_id]:
                        if r['ativo']:
                            horario_br = r['horario_obj'].astimezone(br_tz).strftime('%d/%m %H:%M')
                            msg += f"📦 {r['cliente']} - ⏰ {horario_br}\n"
                    enviar_mensagem(chat_id, msg)
                else:
                    enviar_mensagem(chat_id, "✅ Nenhum romaneio ativo no momento")
        
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
                "⚠️ Alertas automáticos a cada 15 minutos\n"
                "🇧🇷 Todos os horários são de Brasília"
            )
        
        else:
            enviar_mensagem(chat_id, f"Comando não reconhecido. Envie /ajuda para ver os comandos disponíveis.")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

# ===== THREAD DE VERIFICAÇÃO DE ALERTAS =====
def verificar_alertas():
    """Thread principal que verifica e envia alertas a cada 15 minutos"""
    logger.info("🔄 Thread de verificação de alertas iniciada (horário Brasília)")
    
    while True:
        try:
            agora = datetime.now(br_tz)
            
            with lock:
                for chat_id, romaneios in list(romaneios_por_grupo.items()):
                    for romaneio in romaneios[:]:
                        if not romaneio['ativo']:
                            continue
                        
                        horario = romaneio['horario_obj']
                        cliente = romaneio['cliente']
                        
                        if horario.tzinfo is None:
                            horario = br_tz.localize(horario)
                        
                        if agora > horario:
                            horario_br = horario.astimezone(br_tz).strftime('%H:%M')
                            mensagem = (
                                f"⛔ <b>HORÁRIO ULTRAPASSADO</b> ⛔\n\n"
                                f"📦 <b>Cliente:</b> {cliente}\n"
                                f"⏰ <b>Horário limite:</b> {horario_br} (BR)\n\n"
                                f"⚠️ O horário de saída já passou!"
                            )
                            enviar_mensagem(chat_id, mensagem)
                            romaneio['ativo'] = False
                            logger.info(f"⛔ Romaneio {cliente} ultrapassou horário {horario_br}")
                            continue
                        
                        minutos_restantes = int((horario - agora).total_seconds() / 60)
                        
                        if romaneio['alertas_enviados'] == 0 and minutos_restantes <= 60:
                            enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                            romaneio['alertas_enviados'] = minutos_restantes
                            romaneio['ultimo_alerta'] = agora
                            logger.info(f"📊 Primeiro alerta para {cliente}: faltam {minutos_restantes} min (BR)")
                        
                        elif romaneio['alertas_enviados'] > 0:
                            minutos_desde_ultimo = int((agora - romaneio['ultimo_alerta']).total_seconds() / 60)
                            
                            if minutos_desde_ultimo >= 15 and minutos_restantes > 5:
                                if abs(minutos_restantes - romaneio['alertas_enviados']) >= 10:
                                    enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                                    romaneio['alertas_enviados'] = minutos_restantes
                                    romaneio['ultimo_alerta'] = agora
                                    logger.info(f"📊 Alerta de 15 min para {cliente}: faltam {minutos_restantes} min (BR)")
                            
                            elif minutos_restantes <= 5 and romaneio['alertas_enviados'] > 5:
                                enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                                romaneio['alertas_enviados'] = minutos_restantes
                                romaneio['ultimo_alerta'] = agora
                                logger.info(f"🔥 Alerta final para {cliente}: faltam {minutos_restantes} min (BR)")
                        
        except Exception as e:
            logger.error(f"Erro na verificação de alertas: {e}")
        
        time.sleep(30)

# ===== ROTAS DO FLASK =====
@app.route("/", methods=["GET"])
def home():
    """Página inicial e endpoint de wake up"""
    agora_br = datetime.now(br_tz).strftime('%d/%m/%Y %H:%M:%S')
    
    # HTML bonitinho pra mostrar que tá vivo
    html = f"""
    <html>
        <head>
            <title>Bot de Romaneios</title>
            <meta http-equiv="refresh" content="30">
            <style>
                body {{ font-family: Arial; text-align: center; padding: 50px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
                h1 {{ font-size: 3em; margin-bottom: 20px; }}
                p {{ font-size: 1.5em; margin: 10px; }}
                .status {{ background: rgba(255,255,255,0.2); padding: 20px; border-radius: 10px; display: inline-block; }}
                .alive {{ color: #00ff00; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>🤖 Bot de Romaneios</h1>
            <div class="status">
                <p class="alive">✅ BOT VIVO E ACORDADO!</p>
                <p>🇧🇷 Horário BR: {agora_br}</p>
                <p>⏰ Monitoramento a cada 30 segundos</p>
                <p>💤 Sistema anti-sono ativo</p>
                <p>📊 Romaneios ativos: {sum(len(r) for r in romaneios_por_grupo.values())}</p>
            </div>
            <p style="margin-top: 50px; font-size: 1em;">⏰ Esta página é atualizada a cada 30 segundos para manter o bot acordado</p>
        </body>
    </html>
    """
    return html, 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        update = request.get_json()
        
        logger.info("="*50)
        logger.info("📩 MENSAGEM RECEBIDA DO TELEGRAM")
        logger.info(f"Conteúdo: {update}")
        logger.info("="*50)
        
        if update:
            threading.Thread(target=processar_mensagem, args=(update,)).start()
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"🔥 ERRO NO WEBHOOK: {e}")
        return "ok", 200

@app.route("/testar", methods=["GET"])
def testar():
    """Endpoint para verificar se o bot está vivo"""
    agora_br = datetime.now(br_tz).isoformat()
    return jsonify({
        "status": "online",
        "token_configurado": bool(TOKEN),
        "grupos_configurados": len(CHAT_IDS),
        "romaneios_ativos": sum(len(r) for r in romaneios_por_grupo.values()),
        "fuso_horario": "America/Sao_Paulo (BR)",
        "horario_atual_br": agora_br,
        "anti_sono": "ativo",
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/api/testar", methods=["POST"])
def api_testar():
    """Endpoint para testar o envio de alertas"""
    mensagem = "🧪 <b>ALERTA DE TESTE</b>\n\nSistema de notificações funcionando corretamente!\n🇧🇷 Horário BR configurado!\n💤 Anti-sono ativo!"
    
    for chat_id in CHAT_IDS:
        enviar_mensagem(chat_id, mensagem)
    
    return jsonify({
        "mensagem": "Alertas de teste enviados",
        "grupos": len(CHAT_IDS)
    }), 200

# ===== INICIALIZAÇÃO =====
if TOKEN:
    # Inicia thread de verificação de alertas
    threading.Thread(target=verificar_alertas, daemon=True).start()
    
    # Inicia thread anti-sono
    threading.Thread(target=manter_acordado, daemon=True).start()
    
    logger.info("✅ Sistema iniciado com sucesso!")
    logger.info("💤 Anti-sono ativado - bot nunca mais vai dormir!")
else:
    logger.error("🚨 BOT NÃO INICIADO - Token não configurado!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Servidor rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)
