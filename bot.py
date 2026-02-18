import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler

# Token do bot (vem das Environment Variables do Render)
TOKEN = os.environ.get("BOT_TOKEN")

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Comando /start
def start(update, context):
    update.message.reply_text("Bot online 🚀")

dispatcher.add_handler(CommandHandler("start", start))

# Endpoint do webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Rota principal só pra teste
@app.route("/")
def home():
    return "Bot rodando 🚀"

# Inicialização correta para Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
