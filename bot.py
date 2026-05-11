import logging
import os
import random
import asyncio
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler, 
    ContextTypes
)

# --- CONFIGURATION ---
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330
GAME_URL_BASE = "https://msgan-coder.github.io/tbingo_game/"
TOKEN = os.getenv("BOT_TOKEN")
# Koyeb provides the URL via an environment variable or you can hardcode it
KOYEB_URL = os.getenv("KOYEB_PUBLIC_URL") # Example: https://your-app-name.koyeb.app

app = Flask(__name__)
CORS(app)

# --- GLOBAL STATE ---
game_active = False
called_numbers = []
game_session_id = str(int(time.time()))
application = None

logging.basicConfig(level=logging.INFO)

# --- WEBHOOK ROUTE (Telegram hits this) ---
@app.route(f'/{TOKEN}', methods=['POST'])
async def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "OK", 200

# --- GAME ROUTES ---
@app.route('/')
def health():
    return "Bingo Server Live on Koyeb!", 200

@app.route('/get_numbers')
def get_numbers():
    clean_nums = [n.split('-')[1] for n in called_numbers[-5:][::-1]]
    return jsonify({
        "recent_text": ", ".join(clean_nums) if clean_nums else "Waiting...",
        "active": game_active,
        "session_id": game_session_id
    })

@app.route('/claim_bingo', methods=['POST'])
async def claim_bingo():
    data = request.json
    user_name = data.get("user", "Player")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])

    if user_id:
        keyboard = [[
            InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win|{user_id}|{user_name}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"lose|{user_id}|{user_name}")
        ]]
        
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 **BINGO CLAIMED**\n\nPlayer: @{user_name}\nNumbers: {', '.join(marked_nums)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await application.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"⚠️ **BINGO!** @{user_name} is claiming a win!"
        )
    return jsonify({"status": "received"}), 200

# --- BOT LOGIC (Reused from your script) ---
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, game_session_id
    if update.effective_user.id != ADMIN_ID: return
    game_active = True
    called_numbers = []
    game_session_id = str(int(time.time()))
    
    # Start auto-caller job
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")
    await update.message.reply_text("🚀 **GAME STARTED!**")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75: return
    num = random.randint(1, 75)
    while any(str(num) == n.split('-')[1] for n in called_numbers):
        num = random.randint(1, 75)
    letter = "B" if num <= 15 else "I" if num <= 30 else "N" if num <= 45 else "G" if num <= 60 else "O"
    full_call = f"{letter}-{num}"
    called_numbers.append(full_call)
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 {full_call}")

# --- INITIALIZATION ---
async def setup_bot():
    global application
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback)) # (Same as before)
    
    await application.initialize()
    await application.start()
    
    # Tell Telegram where to send updates
    await application.bot.set_webhook(url=f"{KOYEB_URL}/{TOKEN}")
    return application

# Run everything
if __name__ == "__main__":
    # Note: Use an ASGI server like Uvicorn for production webhooks
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_bot())
    uvicorn.run(app, host="0.0.0.0", port=8000)
