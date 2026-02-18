import os
from flask import Flask, requesthttps://github.com/JotaveRoma/romaneio-bot/blob/main/bot.py
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler

TOKEN = os.environ.get("BOT_TOKEN")

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

def start(update, context):
    update.message.reply_text("Bot online 🚀")

dispatcher.add_handler(CommandHandler("start", start))

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "Bot rodando"

if __name__ == "__main__":
    app.run(port=10000)
