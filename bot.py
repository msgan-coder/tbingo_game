import logging
import sqlite3
import os
import random
import threading
import time
import requests
import json
from flask import Flask, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER ---
app = Flask(__name__)
CORS(app) 

@app.route('/')
def home():
    return "Bingo Engine Status: ONLINE"

@app.route('/get_numbers')
def get_numbers():
    global called_numbers, game_active
    # Returns an empty list if reset has been hit
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
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"

# Global State
game_active = False
called_numbers = []
last_called = None

logging.basicConfig(level=logging.INFO)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

# --- LOGIC ---

def get_horizontal_board():
    global last_called, called_numbers
    if not called_numbers:
        return "📊 **BOARD IS CURRENTLY EMPTY**"
        
    rows = {"✨ B": [], "✨ I": [], "✨ N": [], "✨ G": [], "✨ O": []}
    for n in sorted(called_numbers):
        letter = "B" if 1<=n<=15 else "I" if 16<=n<=30 else "N" if 31<=n<=45 else "G" if 46<=n<=60 else "O"
        display = f"[{n}]" if n == last_called else str(n)
        rows[f"✨ {letter}"].append(display)
    
    board_str = "📊 **OFFICIAL CALL BOARD**\n`-------------------------`\n"
    for letter, nums in rows.items():
        num_list = ", ".join(nums) if nums else "---"
        board_str += f"**{letter}** | {num_list}\n"
    return board_str

# --- HANDLERS ---

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get("action") == "claim_bingo":
            username = data.get("user", "Unknown")
            numbers = data.get("numbers", [])
            user_id = update.effective_user.id
            
            game_active = False 
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID, 
                text=f"⏸ **GAME PAUSED**\n\n@{username} has clicked BINGO! Checking card now..."
            )

            kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{username}"),
                   InlineKeyboardButton("❌ REJECT CLAIM", callback_data=f"lose_{user_id}_{username}")]]
            
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"🧐 **VERIFICATION REQUEST**\n\nPlayer: @{username}\nMarked: {', '.join(map(str, numbers))}\n\nCheck against board!",
                reply_markup=InlineKeyboardMarkup(kb)
            )
    except Exception as e:
        logging.error(f"WebApp Data Error: {e}")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 **FULL BOARD! Game over!**")
        return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    
    last_called = num
    called_numbers.append(num)
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    
    msg = f"🔔 **ROUND {len(called_numbers)}: {letter}-{num}**\n\n{get_horizontal_board()}"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    if update.effective_user.id != ADMIN_ID: return
    
    game_active = True
    called_numbers = []
    last_called = None
    
    rules = (
        "🚀 **BINGO GAME BEGINNING!**\n\n"
        "🏠 **HOUSE RULES:**\n"
        "1. First to get a full line (Horizontal, Vertical, or Diagonal) wins!\n"
        "2. You must click the BINGO button to claim.\n"
        "3. Admin decision is final.\n\n"
        "🎮 **Click the 'Play Bingo' button below to get your card!**"
    )
    
    group_kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
    
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID, 
        text=rules, 
        reply_markup=InlineKeyboardMarkup(group_kb)
    )

    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
                 InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Full Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 **ADMIN CONTROL PANEL**", reply_markup=InlineKeyboardMarkup(admin_kb))
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    await query.answer()

    data = query.data.split("_")

    if data[0] == "win":
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WE HAVE A WINNER!**\nCongratulations @{data[2]}! 🏆")
        await query.edit_message_text(text=f"✅ Victory Confirmed for @{data[2]}")

    elif data[0] == "lose":
        game_active = True 
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"❌ @{data[2]}'s claim was invalid.\n▶️ **RESUMING GAME...**")
        await query.edit_message_text(text=f"❌ Claim Rejected for @{data[2]}")

    elif data[1] == "pause":
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⏸ **GAME PAUSED BY ADMIN**")
    
    elif data[1] == "resume":
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="▶️ **GAME RESUMED**")

    elif data[1] == "reset":
        # --- AUTOMATIC ERASE LOGIC ---
        game_active = False
        called_numbers = [] # Clears all called numbers
        last_called = None  # Clears last number reference
        
        # Stops the automatic number calling job
        for job in context.job_queue.get_jobs_by_name("bingo_job"): 
            job.schedule_removal()
            
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ **GAME RESET BY ADMIN.**\nAll numbers have been erased from the board.")
        await query.edit_message_text(text="♻️ Game State Erased & Reset Successful.")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
