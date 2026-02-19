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
import traceback

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

# ===== DICIONÁRIO MONITORADO =====
class DictMonitorado(dict):
    """Subclasse de dict que monitora chamadas ao método clear"""
    def clear(self):
        logger.error("="*60)
        logger.error("🚨🚨🚨 CLEAR DETECTADO NO DICIONÁRIO PRINCIPAL!")
        logger.error(f"Conteúdo antes: {dict(self)}")
        logger.error("Stack trace:")
        for line in traceback.format_stack():
            logger.error(f"  {line.strip()}")
        logger.error("="*60)
        super().clear()

# ===== ESTRUTURA DE DADOS =====
romaneios_por_grupo = DictMonitorado()
lock = threading.Lock()

# ===== PERSISTÊNCIA EM ARQUIVO =====
ARQUIVO_DADOS = "dados.json"

def salvar_dados():
    """Salva os romaneios em arquivo"""
    try:
        with lock:
            dados_para_salvar = {}
            for chat_id, romaneios in romaneios_por_grupo.items():
                dados_para_salvar[str(chat_id)] = []
                for r in romaneios:
                    dados_para_salvar[str(chat_id)].append({
                        'cliente': r['cliente'],
                        'horario': r['horario'],
                        'horario_obj': r['horario_obj'].isoformat() if r['horario_obj'] else None,
                        'chat_id': r['chat_id'],
                        'message_id': r['message_id'],
                        'criado_em': r['criado_em'].isoformat(),
                        'ultimo_alerta': r['ultimo_alerta'].isoformat(),
                        'alertas_enviados': r['alertas_enviados'],
                        'ativo': r['ativo']
                    })
            
            with open(ARQUIVO_DADOS, 'w') as f:
                json.dump(dados_para_salvar, f, indent=2)
            logger.info("💾 Dados salvos em arquivo")
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}")

def carregar_dados():
    """Carrega os romaneios do arquivo"""
    global romaneios_por_grupo
    try:
        if os.path.exists(ARQUIVO_DADOS):
            with open(ARQUIVO_DADOS, 'r') as f:
                dados_carregados = json.load(f)
            
            with lock:
                romaneios_por_grupo.clear()
                for chat_id_str, romaneios in dados_carregados.items():
                    chat_id = int(chat_id_str)
                    romaneios_por_grupo[chat_id] = []
                    for r in romaneios:
                        # Converte strings ISO para datetime com timezone
                        horario_obj = None
                        if r['horario_obj']:
                            horario_obj = datetime.fromisoformat(r['horario_obj'])
                            if horario_obj.tzinfo is None:
                                horario_obj = br_tz.localize(horario_obj)
                        
                        criado_em = datetime.fromisoformat(r['criado_em'])
                        if criado_em.tzinfo is None:
                            criado_em = br_tz.localize(criado_em)
                        
                        ultimo_alerta = datetime.fromisoformat(r['ultimo_alerta'])
                        if ultimo_alerta.tzinfo is None:
                            ultimo_alerta = br_tz.localize(ultimo_alerta)
                        
                        romaneios_por_grupo[chat_id].append({
                            'cliente': r['cliente'],
                            'horario': r['horario'],
                            'horario_obj': horario_obj,
                            'chat_id': r['chat_id'],
                            'message_id': r['message_id'],
                            'criado_em': criado_em,
                            'ultimo_alerta': ultimo_alerta,
                            'alertas_enviados': r['alertas_enviados'],
                            'ativo': r['ativo']
                        })
            logger.info(f"📂 Dados carregados: {len(romaneios_por_grupo)} chats")
            return True
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        return False

# ===== SISTEMA DE PROTEÇÃO CONTRA RESET MELHORADO =====
def proteger_dicionario(func):
    """Decorador que protege o dicionário contra resets acidentais"""
    def wrapper(*args, **kwargs):
        global romaneios_por_grupo
        # Salva o estado antes
        with lock:
            estado_anterior = dict(romaneios_por_grupo) if romaneios_por_grupo else {}
            id_anterior = id(romaneios_por_grupo)
            tamanho_anterior = len(romaneios_por_grupo)
            logger.info(f"🛡️ [PROTECTOR] {func.__name__} - Antes: {tamanho_anterior} chats, ID: {id_anterior}")
        
        try:
            resultado = func(*args, **kwargs)
            
            # Verifica mudanças
            with lock:
                id_atual = id(romaneios_por_grupo)
                tamanho_atual = len(romaneios_por_grupo)
                
                # CASO 1: ID mudou (dicionário foi recriado)
                if id_atual != id_anterior:
                    logger.error(f"🚨🚨🚨 DICIONÁRIO RECRIADO em {func.__name__}!")
                    logger.error(f"ID anterior: {id_anterior}, ID novo: {id_atual}")
                    if estado_anterior:
                        logger.error(f"Restaurando {len(estado_anterior)} chats perdidos")
                        romaneios_por_grupo.clear()
                        romaneios_por_grupo.update(estado_anterior)
                        logger.info(f"✅ Restauração concluída. Agora: {len(romaneios_por_grupo)} chats")
                
                # CASO 2: ID é o mesmo mas perdeu todos os dados
                elif tamanho_atual == 0 and tamanho_anterior > 0:
                    logger.error(f"🚨 TODOS OS DADOS PERDIDOS em {func.__name__}!")
                    logger.error(f"Tinha {tamanho_anterior} chats, agora tem 0")
                    if estado_anterior:
                        logger.error(f"Restaurando {len(estado_anterior)} chats")
                        romaneios_por_grupo.clear()
                        romaneios_por_grupo.update(estado_anterior)
                        logger.info(f"✅ Restauração concluída. Agora: {len(romaneios_por_grupo)} chats")
                
                # CASO 3: Perdeu alguns dados
                elif tamanho_atual < tamanho_anterior:
                    logger.warning(f"⚠️ Perda parcial de dados em {func.__name__}")
                    logger.warning(f"Tinha {tamanho_anterior}, agora tem {tamanho_atual}")
                    perdidos = set(estado_anterior.keys()) - set(romaneios_por_grupo.keys())
                    logger.warning(f"Chats perdidos: {perdidos}")
                
                # CASO 4: Tudo normal
                elif tamanho_atual > tamanho_anterior:
                    logger.info(f"📊 {func.__name__}: {tamanho_anterior} -> {tamanho_atual} chats (crescimento)")
                
            return resultado
        except Exception as e:
            logger.error(f"Erro em {func.__name__}: {e}")
            logger.error(traceback.format_exc())
            raise
    return wrapper

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
    logger.info(f"🔥 FUNÇÃO ENVIAR_ALERTA CHAMADA para {cliente} - minutos: {minutos_restantes}")
    
    if minutos_restantes <= 1:
        msg_alerta = f"🔥 <b>SAIR AGORA! ÚLTIMO MINUTO!</b> 🔥"
    elif minutos_restantes <= 5:
        msg_alerta = f"🔥 <b>ÚLTIMOS {minutos_restantes} MINUTOS! SAIR AGORA!</b> 🔥"
    elif minutos_restantes <= 15:
        msg_alerta = f"⚠️ <b>FALTAM {minutos_restantes} MINUTOS! PREPARAR PARA SAÍDA!</b>"
    else:
        msg_alerta = f"⚡ <b>FALTAM {minutos_restantes} MINUTOS PARA O HORÁRIO LIMITE</b>"
    
    # Formata o horário em BR para exibição
    horario_br = romaneio['horario_obj'].astimezone(br_tz).strftime('%H:%M')
    
    mensagem = (
        f"🚨 <b>ALERTA DE SAÍDA</b> 🚨\n\n"
        f"📦 <b>Cliente:</b> {cliente}\n"
        f"⏰ <b>Horário limite:</b> {horario_br} (horário BR)\n"
        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
        f"{msg_alerta}"
    )
    
    resultado = enviar_mensagem(chat_id, mensagem)
    logger.info(f"✅ Resultado do envio: {resultado}")
    return resultado

# ===== PROCESSAMENTO DE COMANDOS =====
@proteger_dicionario
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
        
        # Obtém data/hora atual no fuso BR
        agora = datetime.now(br_tz)
        logger.info(f"📅 Agora em BR: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Cria o horário do romaneio no fuso BR
        horario_obj = br_tz.localize(datetime(
            agora.year, agora.month, agora.day,
            hora, minuto, 0, 0
        ))
        
        # Se já passou, agenda para amanhã (mantendo horário BR)
        if horario_obj < agora:
            horario_obj = horario_obj + timedelta(days=1)
            logger.info(f"📅 Horário {horario_str} já passou hoje, agendado para amanhã {horario_obj.strftime('%d/%m %H:%M')}")
            
    except Exception as e:
        enviar_mensagem(chat_id, "❌ Horário inválido! Use formato HH:MM (ex: 15:00)")
        logger.error(f"Erro no horário: {e}")
        return
    
    # Calcula minutos restantes no fuso BR
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
        logger.info(f"📦 Romaneio adicionado. Chat {chat_id} agora tem {len(romaneios_por_grupo[chat_id])} romaneios")
        logger.info(f"🔍 ESTADO PÓS-REGISTRO: chats ativos = {list(romaneios_por_grupo.keys())}")
        logger.info(f"🆔 ID do dicionário após registro: {id(romaneios_por_grupo)}")
    
    # Mensagem de confirmação com horário BR
    resposta = (
        f"✅ <b>ROMANEIO REGISTRADO</b>\n\n"
        f"📦 <b>Cliente:</b> {cliente}\n"
        f"⏰ <b>Horário limite:</b> {horario_str} (horário BR)\n"
        f"⏳ <b>Tempo restante:</b> {minutos_restantes} minutos\n\n"
        f"⚠️ <i>Alertas serão enviados a cada 15 minutos (horário BR)</i>\n"
        f"🗑️ <i>Será removido automaticamente após o horário</i>"
    )
    enviar_mensagem(chat_id, resposta)
    logger.info(f"✅ Romaneio registrado: {cliente} às {horario_str} BR no grupo {chat_id}")
    
    # Salva dados após registro
    salvar_dados()

@proteger_dicionario
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
        logger.info(f"🔍 CHAT_ID recebido: {chat_id} (tipo: {type(chat_id)})")
        
        with lock:
            logger.info(f"🔍 ESTADO ANTES DO PROCESSAMENTO: chats = {list(romaneios_por_grupo.keys())}")
            logger.info(f"🆔 ID do dicionário antes: {id(romaneios_por_grupo)}")
        
        if text == '/start':
            enviar_mensagem(chat_id, 
                "🤖 <b>Bot de Romaneios</b>\n\n"
                "Comandos disponíveis:\n\n"
                "📝 <b>/romaneio [cliente] [horário]</b>\n"
                "Ex: /romaneio honda 15:00 (horário BR)\n\n"
                "📋 <b>/listar</b> - Ver romaneios ativos\n"
                "❌ <b>/cancelar [cliente]</b> - Cancelar romaneio\n"
                "🧹 <b>/limpar</b> - Limpar romaneios antigos\n"
                "🔍 <b>/debug</b> - Ver informações de debug\n"
                "🆘 <b>/ajuda</b> - Mostrar ajuda\n"
                "🏓 <b>/ping</b> - Testar bot\n\n"
                "🇧🇷 <i>Horários no fuso de Brasília</i>"
            )
        
        elif text == '/ping':
            enviar_mensagem(chat_id, "pong 🏓")
        
        elif text == '/debug':
            with lock:
                msg = "🔍 <b>DEBUG INFO</b>\n\n"
                msg += f"TOTAL CHATS: {len(romaneios_por_grupo)}\n"
                msg += f"ID DO DICIONÁRIO: {id(romaneios_por_grupo)}\n"
                for cid, roms in romaneios_por_grupo.items():
                    msg += f"\nCHAT - {cid}:\n"
                    for r in roms:
                        status = "🟢 ATIVO" if r['ativo'] else "🔴 INATIVO"
                        horario_br = r['horario_obj'].astimezone(br_tz).strftime('%d/%m %H:%M')
                        msg += f"{r['cliente']} - {horario_br} - {status} - ALERTAS: {r['alertas_enviados']}\n"
                enviar_mensagem(chat_id, msg)
        
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
        
        elif text == '/limpar':
            with lock:
                if chat_id in romaneios_por_grupo:
                    romaneios_por_grupo[chat_id] = [r for r in romaneios_por_grupo[chat_id] if r['ativo']]
                    if not romaneios_por_grupo[chat_id]:
                        del romaneios_por_grupo[chat_id]
                    enviar_mensagem(chat_id, "🧹 Romaneios antigos limpos com sucesso!")
                    salvar_dados()
                else:
                    enviar_mensagem(chat_id, "✅ Nenhum romaneio para limpar")
        
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
                            salvar_dados()
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
                "4️⃣ <b>Limpar antigos:</b>\n"
                "/limpar\n\n"
                "5️⃣ <b>Debug:</b>\n"
                "/debug\n\n"
                "6️⃣ <b>Testar:</b>\n"
                "/ping\n\n"
                "⚠️ Alertas automáticos a cada 15 minutos\n"
                "🇧🇷 Todos os horários são de Brasília"
            )
        
        else:
            enviar_mensagem(chat_id, f"Comando não reconhecido. Envie /ajuda para ver os comandos disponíveis.")
        
        with lock:
            logger.info(f"🔍 ESTADO DEPOIS DO PROCESSAMENTO: chats = {list(romaneios_por_grupo.keys())}")
            logger.info(f"🆔 ID do dicionário depois: {id(romaneios_por_grupo)}")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        logger.error(traceback.format_exc())

# ===== THREAD DE VERIFICAÇÃO DE ALERTAS =====
def verificar_alertas():
    """Thread principal que verifica e envia alertas"""
    logger.info("🔄 Thread de verificação de alertas iniciada")
    contador = 0
    
    while True:
        try:
            contador += 1
            agora = datetime.now(br_tz)
            
            # USA O LOCK DIRETAMENTE SEM CÓPIAS COMPLICADAS
            with lock:
                total_chats = len(romaneios_por_grupo)
                logger.info(f"📊 [VERIFICAÇÃO #{contador}] {agora.strftime('%H:%M:%S')} - Total chats: {total_chats}")
                
                if total_chats == 0:
                    logger.info("💤 Nenhum romaneio ativo")
                else:
                    # ITERA SOBRE O DICIONÁRIO ORIGINAL (COM LOCK)
                    for chat_id, romaneios in list(romaneios_por_grupo.items()):
                        logger.info(f"📋 Chat {chat_id} tem {len(romaneios)} romaneios")
                        
                        for romaneio in romaneios[:]:  # Cópia da lista
                            if not romaneio['ativo']:
                                continue
                            
                            horario = romaneio['horario_obj']
                            cliente = romaneio['cliente']
                            
                            # Garantir timezone
                            if horario.tzinfo is None:
                                horario = br_tz.localize(horario)
                            
                            minutos_restantes = int((horario - agora).total_seconds() / 60)
                            
                            # LOG SIMPLES
                            logger.info(f"  → {cliente}: faltam {minutos_restantes} min, alertas: {romaneio['alertas_enviados']}")
                            
                            # Se passou do horário
                            if agora > horario:
                                logger.info(f"  ⛔ {cliente} PASSOU DO HORÁRIO!")
                                mensagem = (
                                    f"⛔ <b>HORÁRIO ULTRAPASSADO</b> ⛔\n\n"
                                    f"📦 <b>Cliente:</b> {cliente}\n"
                                    f"⏰ <b>Horário limite:</b> {horario.strftime('%H:%M')} (BR)\n\n"
                                    f"⚠️ O horário de saída já passou!"
                                )
                                enviar_mensagem(chat_id, mensagem)
                                romaneio['ativo'] = False
                                salvar_dados()
                                continue
                            
                            # Primeiro alerta
                            if romaneio['alertas_enviados'] == 0 and minutos_restantes <= 60:
                                logger.info(f"  🚨 ENVIANDO PRIMEIRO ALERTA para {cliente}")
                                enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                                romaneio['alertas_enviados'] = minutos_restantes
                                romaneio['ultimo_alerta'] = agora
                                salvar_dados()
                            
                            # Alertas subsequentes
                            elif romaneio['alertas_enviados'] > 0:
                                minutos_desde_ultimo = int((agora - romaneio['ultimo_alerta']).total_seconds() / 60)
                                
                                # A cada 15 minutos
                                if minutos_desde_ultimo >= 15 and minutos_restantes > 5:
                                    logger.info(f"  🚨 ENVIANDO ALERTA DE 15 MIN para {cliente}")
                                    enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                                    romaneio['alertas_enviados'] = minutos_restantes
                                    romaneio['ultimo_alerta'] = agora
                                    salvar_dados()
                                
                                # Alerta final
                                elif minutos_restantes <= 5 and romaneio['alertas_enviados'] > 5:
                                    logger.info(f"  🔥 ENVIANDO ALERTA FINAL para {cliente}")
                                    enviar_alerta(romaneio, chat_id, cliente, minutos_restantes)
                                    romaneio['alertas_enviados'] = minutos_restantes
                                    romaneio['ultimo_alerta'] = agora
                                    salvar_dados()
            
        except Exception as e:
            logger.error(f"🔥 ERRO NA VERIFICAÇÃO: {e}")
            logger.error(traceback.format_exc())
        
        # Aguarda 30 segundos
        time.sleep(30)

# ===== ROTA PARA FORÇAR VERIFICAÇÃO MANUAL =====
@app.route("/forcar_verificacao", methods=["GET"])
def forcar_verificacao():
    """Força uma verificação manual dos alertas"""
    def verificar_agora():
        logger.info("🔴 VERIFICAÇÃO MANUAL FORÇADA INICIADA")
        agora = datetime.now(br_tz)
        
        with lock:
            logger.info(f"🆔 ID do dicionário (manual): {id(romaneios_por_grupo)}")
            logger.info(f"📊 Chats ativos (manual): {list(romaneios_por_grupo.keys())}")
            
            for chat_id, romaneios in list(romaneios_por_grupo.items()):
                for romaneio in romaneios[:]:
                    if not romaneio['ativo']:
                        continue
                    
                    horario = romaneio['horario_obj']
                    cliente = romaneio['cliente']
                    minutos_restantes = int((horario - agora).total_seconds() / 60)
                    
                    logger.info(f"🔍 MANUAL: {cliente} - Horário: {horario.strftime('%H:%M')} - Faltam: {minutos_restantes} min - Alertas: {romaneio['alertas_enviados']}")
        
        logger.info("✅ VERIFICAÇÃO MANUAL FINALIZADA")
    
    threading.Thread(target=verificar_agora).start()
    return "Verificação manual iniciada! Verifique os logs.", 200

# ===== ROTA PARA DEBUG DO ESTADO =====
@app.route("/estado", methods=["GET"])
def estado():
    """Mostra o estado atual dos romaneios"""
    with lock:
        info = {
            "total_chats": len(romaneios_por_grupo),
            "id_dicionario": id(romaneios_por_grupo),
            "chats": {}
        }
        for chat_id, romaneios in romaneios_por_grupo.items():
            info["chats"][str(chat_id)] = [
                {
                    "cliente": r["cliente"],
                    "horario": r["horario_obj"].astimezone(br_tz).strftime("%d/%m %H:%M"),
                    "ativo": r["ativo"],
                    "alertas_enviados": r["alertas_enviados"],
                    "minutos_restantes": int((r["horario_obj"] - datetime.now(br_tz)).total_seconds() / 60)
                }
                for r in romaneios
            ]
    return jsonify(info), 200

# ===== ROTA PARA MONITORAR INTEGRIDADE =====
@app.route("/integridade", methods=["GET"])
def integridade():
    """Endpoint para monitorar a integridade do dicionário"""
    with lock:
        return jsonify({
            "dicionario_existe": 'romaneios_por_grupo' in globals(),
            "tipo": str(type(romaneios_por_grupo)),
            "id": id(romaneios_por_grupo),
            "total_chats": len(romaneios_por_grupo),
            "chats": list(romaneios_por_grupo.keys())
        }), 200

# ===== ROTAS DO FLASK =====
@app.route("/")
def home():
    agora_br = datetime.now(br_tz).strftime('%d/%m/%Y %H:%M:%S')
    return f"🤖 Bot de Romaneios rodando! 🚀\n🇧🇷 Horário BR: {agora_br}", 200

@app.route("/webhook", methods=["POST"])
@proteger_dicionario
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    try:
        update = request.get_json()
        
        logger.info("="*50)
        logger.info("📩 MENSAGEM RECEBIDA DO TELEGRAM")
        logger.info(f"Conteúdo: {update}")
        
        with lock:
            logger.info(f"🔍 ESTADO NO WEBHOOK ANTES: chats = {list(romaneios_por_grupo.keys())}")
            logger.info(f"🆔 ID do dicionário no webhook: {id(romaneios_por_grupo)}")
        
        logger.info("="*50)
        
        if update:
            threading.Thread(target=processar_mensagem, args=(update,)).start()
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"🔥 ERRO NO WEBHOOK: {e}")
        logger.error(traceback.format_exc())
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
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/api/testar", methods=["POST"])
def api_testar():
    """Endpoint para testar o envio de alertas"""
    mensagem = "🧪 <b>ALERTA DE TESTE</b>\n\nSistema de notificações funcionando corretamente!\n🇧🇷 Horário BR configurado!"
    
    for chat_id in CHAT_IDS:
        enviar_mensagem(chat_id, mensagem)
    
    return jsonify({
        "mensagem": "Alertas de teste enviados",
        "grupos": len(CHAT_IDS)
    }), 200

# ===== INICIALIZAÇÃO =====
if TOKEN:
    # Carrega dados salvos
    carregar_dados()
    
    # Inicia thread que SALVA dados a cada 30 segundos
    def autosalvar():
        while True:
            time.sleep(30)
            salvar_dados()
    
    threading.Thread(target=autosalvar, daemon=True).start()
    threading.Thread(target=verificar_alertas, daemon=True).start()
    
    logger.info("✅ Sistema iniciado com sucesso!")
    with lock:
        logger.info(f"🆔 ID inicial do dicionário: {id(romaneios_por_grupo)}")
        logger.info(f"📊 Chats carregados: {len(romaneios_por_grupo)}")
else:
    logger.error("🚨 BOT NÃO INICIADO - Token não configurado!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Servidor rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)
