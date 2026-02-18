import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.getenv("BOT_TOKEN")

scheduler = AsyncIOScheduler()
scheduler.start()

conn = sqlite3.connect("romaneios.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS romaneios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    horario TEXT,
    data TEXT,
    grupo_id INTEGER
)
""")
conn.commit()


def calcular_data(hora_str):
    agora = datetime.now()
    hora = datetime.strptime(hora_str, "%H:%M").time()
    data_final = datetime.combine(agora.date(), hora)

    if data_final < agora:
        data_final += timedelta(days=1)

    return data_final


async def romaneio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = [admin.user.id for admin in admins]

    if user.id not in admin_ids:
        await update.message.reply_text("❌ Você não tem permissão para cadastrar.")
        return

    try:
        nome = context.args[0]
        hora = context.args[1]
    except:
        await update.message.reply_text("Uso correto: /romaneio Nome 15:00")
        return

    data_final = calcular_data(hora)

    cursor.execute(
        "INSERT INTO romaneios (nome, horario, data, grupo_id) VALUES (?, ?, ?, ?)",
        (nome, hora, data_final.strftime("%Y-%m-%d %H:%M:%S"), chat.id),
    )
    conn.commit()

    await update.message.reply_text(
        f"📦 Romaneio {nome}\n⏰ Saída máxima: {hora}\n📅 Data: {data_final.strftime('%d/%m %H:%M')}"
    )

    agendar_alertas(nome, data_final, chat.id)


def agendar_alertas(nome, data_final, grupo_id):
    alertas = [60, 30, 10]

    for minutos in alertas:
        horario_alerta = data_final - timedelta(minutes=minutos)
        scheduler.add_job(
            enviar_alerta,
            "date",
            run_date=horario_alerta,
            args=[nome, minutos, grupo_id],
        )

    scheduler.add_job(
        enviar_atraso,
        "date",
        run_date=data_final + timedelta(minutes=1),
        args=[nome, grupo_id],
    )


async def enviar_alerta(nome, minutos, grupo_id):
    texto = f"⚠️ Romaneio {nome} sai em {minutos} minutos!"
    await app.bot.send_message(chat_id=grupo_id, text=texto)


async def enviar_atraso(nome, grupo_id):
    texto = f"❌ Romaneio {nome} está ATRASADO!"
    await app.bot.send_message(chat_id=grupo_id, text=texto)


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("romaneio", romaneio))

print("Bot rodando...")
app.run_polling()
