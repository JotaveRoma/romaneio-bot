from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.environ.get("TOKEN")

@app.route("/")
def home():
    return "Bot rodando 🚀", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    return "ok", 200
