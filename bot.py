import logging
import sqlite3
import os
import random
import threading
import time
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER & KEEP-ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Bingo Bot is Awake"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Pings the server every 10 minutes to prevent Render from sleeping"""
    while True:
        try:
            # Replace with your actual Render URL
            requests.get("https://tbingo-game-4.onrender.com")
        except:
            pass
        time.sleep(600)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10

# Global Game State
game_active = False
called_numbers = []
last_called = None  # Tracks the newest number for yellow highlighting

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

def get_horizontal_board():
    """Formats the board: Newest number gets an 'X'"""
    global last_called, called_numbers
    rows = {"✨ B": [], "✨ I": [], "✨ N": [], "✨ G": [], "✨ O": []}
    
    # Sort numbers into their B-I-N-G-O slots
    for n in called_numbers:
        letter = "B" if 1<=n<=15 else "I" if 16<=n<=30 else "N" if 31<=n<=45 else "G" if 46<=n<=60 else "O"
        # If it's the last called number, add the 'X' marker
        display = f"{n}X" if n == last_called else str(n)
        rows[f"✨ {letter}"].append(display)

    board_str = "📊 **CALLED NUMBERS BOARD**\n`-------------------------`\n"
    for letter, nums in rows.items():
        num_list = ", ".join(nums) if nums else "---"
        board_str += f"**{letter}** | {num_list}\n"
    return board_str

# --- HANDLERS ---

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json
    data = json.loads(update.effective_message.web_app_data.data)
    
    if data.get("action") == "claim_bingo":
        username = data.get("user", "Unknown")
        numbers = data.get("numbers", [])
        
        msg = f"🏆 **BINGO CLAIM!**\nUser: @{username}\nMarked: {', '.join(map(str, numbers))}\n\nVerify against the board!"
        kb = [[InlineKeyboardButton("✅ Confirm Winner", callback_data=f"win_{update.effective_user.id}_{username}")]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("BINGO claim sent to Admin for verification!")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 **BOARD FULL! Round Ended.**")
        return

    num = random.randint(1, 75)
    while num in called_numbers: 
        num = random.randint(1, 75)
    
    last_called = num
    called_numbers.append(num)
    
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    msg = f"🔔 **NEW NUMBER: {letter}-{last_called}**\n\n{get_horizontal_board()}"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    if update.effective_user.id != ADMIN_ID: return
    
    # Check if there are paid players
    conn = sqlite3.connect("bingo.db")
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()

    if count == 0:
        await update.message.reply_text("❌ No paid players found. Approve payments first!")
        return

    game_active = True
    called_numbers = []
    last_called = None
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **BINGO START!**\nNew numbers calling every 8s.")
    context.job_queue.run_repeating(auto_caller, interval=8, first=2, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")

    if data[0] == "app":
        user_id, username = int(data[1]), data[2]
        conn = sqlite3.connect("bingo.db")
        conn.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, username))
        conn.commit()
        conn.close()
        kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
        await context.bot.send_message(chat_id=user_id, text="✅ Approved! Click below to play.", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_caption(caption=f"✅ Approved: @{username}")

    elif data[0] == "rej":
        await query.edit_message_caption(caption="❌ Rejected")

    elif data[0] == "win":
        username = data[2]
        game_active = False
        last_called = None
        called_numbers = []
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        conn = sqlite3.connect("bingo.db")
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()

        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{username}**\n\n⚠️ Round Over. Cards expired. Pay for the next game!")
        await query.edit_message_text(text=f"✅ Round closed for @{username}.")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{user.username}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 From: @{user.username}", reply_markup=InlineKeyboardMarkup(kb))

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    application.run_polling()

if __name__ == "__main__":
    main()
