@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber atualizações do Telegram"""
    
    # === NOVO: LOG BRUTO DA REQUISIÇÃO ===
    print("\n" + "="*60)
    print("HEADERS:", dict(request.headers))
    print("DATA BRUTA:", request.get_data(as_text=True))
    print("="*60 + "\n")
    # ======================================
    
    try:
        update = request.get_json()
        logger.info("📩 MENSAGEM RECEBIDA: %s", update)
        
        if update:
            threading.Thread(target=processar_mensagem, args=(update,)).start()
        
        return "ok", 200
    except Exception as e:
        logger.error(f"🔥 ERRO: {e}")
        return "ok", 200
