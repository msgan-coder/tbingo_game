import logging
import sqlite3
import os
import random
import threading
import requests
import json
from flask import Flask, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER ---
app = Flask(__name__)
CORS(app) 

@app.route('/get_numbers')
def get_numbers():
    global called_numbers, game_active
    return jsonify({
        "recent": called_numbers[-5:][::-1], 
        "active": game_active
    })

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/" # Ensure this matches your GitHub Pages URL

# Global State
game_active = False
called_numbers = []
last_called = None

logging.basicConfig(level=logging.INFO)

# --- HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome!** Send your payment screenshot here to join the game.")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    await update.message.reply_text("✅ Received! Admin is verifying...")

    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"pay_app_{user.id}_{user.username}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej_{user.id}_{user.username}")]]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Payment from @{user.username}", reply_markup=InlineKeyboardMarkup(kb))

# IMPORTANT: This handles the BINGO click from the WebApp
async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    data = json.loads(update.effective_message.web_app_data.data)
    
    if data.get("action") == "claim_bingo":
        game_active = False # Pause calling
        user = update.effective_user
        numbers = ", ".join(data.get("numbers", []))
        
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"⚠️ **BINGO CLAIMED by @{user.username}!**\nChecking card...")
        
        kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user.id}_{user.username}"),
               InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user.id}_{user.username}")]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧐 **VERIFY @{user.username}**\nMarked: {numbers}", reply_markup=InlineKeyboardMarkup(kb))

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active or len(called_numbers) >= 75: return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    called_numbers.append(num)
    
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    msg = f"🔔 **ROUND {len(called_numbers)}: {letter}-{num}**"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    
    game_active = True
    called_numbers = []
    
    # Send Admin Controls to your PRIVATE chat
    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
                 InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 **GAME CONTROLS**", reply_markup=InlineKeyboardMarkup(admin_kb))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!** Prepare your cards.")
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    data = query.data.split("_")
    
    if data[0] == "pay" and data[1] == "app":
        play_kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
        await context.bot.send_message(chat_id=data[2], text="✅ Approved! Click below:", reply_markup=InlineKeyboardMarkup(play_kb))
    
    elif data[1] == "pause":
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⏸ Game Paused.")
    
    elif data[1] == "resume":
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="▶️ Game Resumed.")
    
    elif data[1] == "reset":
        called_numbers = []
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ Game Reset.")

    await query.answer()

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.run_polling()

if __name__ == "__main__":
    main()
