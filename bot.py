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

# --- FLASK SERVER & LIVE API ---
app = Flask(__name__)
CORS(app) 

@app.route('/')
def home():
    return "Professional Bingo Engine is Online"

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

def keep_alive():
    while True:
        try:
            requests.get("https://tbingo-game-4.onrender.com")
        except:
            pass
        time.sleep(600)

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

def verify_claim(player_numbers):
    try:
        marked = []
        for n in player_numbers:
            if str(n).upper() == "FREE":
                marked.append("FREE")
            elif str(n).isdigit():
                marked.append(int(n))
        
        actual_marked = [n for n in marked if isinstance(n, int)]
        if len(marked) < 5:
            return False, "Not enough numbers for a Bingo."

        invalid_nums = [n for n in actual_marked if n not in called_numbers]
        if invalid_nums:
            return False, f"Numbers not called yet: {', '.join(map(str, invalid_nums))}"

        return True, "VALID BINGO DETECTED ✅"
    except Exception as e:
        return False, f"Error verifying: {e}"

# --- HANDLERS ---

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    data = json.loads(update.effective_message.web_app_data.data)
    
    if data.get("action") == "claim_bingo":
        username = data.get("user", "Unknown")
        numbers = data.get("numbers", [])
        user_id = update.effective_user.id
        game_active = False 

        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=f"⏸ **GAME PAUSED**\n\n@{username} is claiming a BINGO! Admin checking..."
        )

        is_valid, reason = verify_claim(numbers)
        status_emoji = "✅" if is_valid else "⚠️"
        admin_msg = (
            f"🧐 **VERIFICATION**\nPlayer: @{username}\nStatus: {status_emoji} {reason}\n"
            f"Marked: {', '.join(map(str, numbers))}\nLast called: {last_called}"
        )
        
        kb = [[InlineKeyboardButton("🏆 CONFIRM", callback_data=f"win_{user_id}_{username}"),
               InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user_id}_{username}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(kb))

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 **Game over!**")
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
    
    kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
           InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
          [InlineKeyboardButton("♻️ Reset Game", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **BINGO STARTED!**", reply_markup=InlineKeyboardMarkup(kb))
    context.job_queue.run_repeating(auto_caller, interval=10, first=1, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("You are not the Admin!", show_alert=True)
        return
        
    await query.answer()
    data = query.data.split("_")

    # Win/Loss Handling
    if data[0] == "win":
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}!** 🏆")
        await query.edit_message_text(text=f"✅ Confirmed @{data[2]}")

    elif data[0] == "lose":
        game_active = True 
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"❌ @{data[2]} invalid claim. ▶️ Resuming...")
        await query.edit_message_text(text=f"❌ Rejected @{data[2]}")

    # Control Panel Handling
    elif data[1] == "pause":
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⏸ **GAME PAUSED BY ADMIN**")
    
    elif data[1] == "resume":
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="▶️ **GAME RESUMED**")

    elif data[1] == "reset":
        game_active = False
        called_numbers = []
        last_called = None
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ **GAME RESET BY ADMIN.** Previous data cleared.")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    time.sleep(2)
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    print("Bingo Bot with Admin Panel is LIVE")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
