import logging
import sqlite3
import os
import random
import threading
import time
import requests
import json
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER & KEEP-ALIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Bingo Bot is Awake"

def run_flask():
    # Render binds to this port to keep the service "Live"
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Pings the server every 10 minutes to prevent Render from sleeping"""
    while True:
        try:
            # Pings itself to stay active
            requests.get("https://tbingo-game-4.onrender.com")
        except:
            pass
        time.sleep(600)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"

# Global Game State
game_active = False
called_numbers = []
last_called = None

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

def get_horizontal_board():
    """Formats the Bingo board for the group chat"""
    global last_called, called_numbers
    rows = {"✨ B": [], "✨ I": [], "✨ N": [], "✨ G": [], "✨ O": []}
    
    for n in called_numbers:
        letter = "B" if 1<=n<=15 else "I" if 16<=n<=30 else "N" if 31<=n<=45 else "G" if 46<=n<=60 else "O"
        display = f"{n}X" if n == last_called else str(n)
        rows[f"✨ {letter}"].append(display)

    board_str = "📊 **CALLED NUMBERS BOARD**\n`-------------------------`\n"
    for letter, nums in rows.items():
        num_list = ", ".join(nums) if nums else "---"
        board_str += f"**{letter}** | {num_list}\n"
    return board_str

# --- HANDLERS ---

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    data = json.loads(update.effective_message.web_app_data.data)
    
    if data.get("action") == "claim_bingo":
        username = data.get("user", "Unknown")
        numbers = data.get("numbers", [])
        user_id = update.effective_user.id

        # 1. PAUSE THE CALLER IMMEDIATELY
        game_active = False 
        
        # 2. ANNOUNCE IN THE GROUP
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=f"⏸ **CALLING PAUSED**\n\nChecking {username}'s Bingo card... Please wait for Admin approval."
        )

        # 3. SEND TO ADMIN FOR VERIFICATION
        msg = (f"🧐 **VERIFY CLAIM**\n"
               f"User: @{username}\n"
               f"Marked Numbers: {', '.join(map(str, numbers))}\n\n"
               f"Check against the group board!")
        
        kb = [[
            InlineKeyboardButton("✅ WINNER", callback_data=f"win_{user_id}_{username}"),
            InlineKeyboardButton("❌ LOSE / FAKE", callback_data=f"lose_{user_id}_{username}")
        ]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(kb))

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
    
    game_active = True
    called_numbers = []
    last_called = None
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **BINGO START!**\nNumbers calling every 8s.")
    context.job_queue.run_repeating(auto_caller, interval=8, first=2, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")

    if data[0] == "win":
        user_id, username = data[1], data[2]
        # End game and clear jobs
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        # Clear players for next round
        conn = sqlite3.connect("bingo.db")
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()

        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **CONGRATULATIONS @{username}!**\n\nYou are the winner! Round over. 🏆")
        await context.bot.send_message(chat_id=user_id, text="🥳 **BINGO CONFIRMED!** You won!")
        await query.edit_message_text(text=f"✅ Win confirmed for @{username}")

    elif data[0] == "lose":
        user_id, username = data[1], data[2]
        # RESUME THE CALLER
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"❌ @{username} did not have a Bingo.\n\n▶️ **RESUMING GAME...**")
        await context.bot.send_message(chat_id=user_id, text="❌ **REJECTED.** Your claim was not valid. Keep playing!")
        await query.edit_message_text(text=f"❌ Rejected claim from @{username}")

    elif data[0] == "app":
        user_id, username = int(data[1]), data[2]
        conn = sqlite3.connect("bingo.db")
        conn.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, username))
        conn.commit()
        conn.close()
        kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
        await context.bot.send_message(chat_id=user_id, text="✅ Payment Approved! Play now:", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_caption(caption=f"✅ Approved: @{username}")

def main():
    init_db()
    
    # Start background threads
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Wait a moment for old Render instances to disconnect
    print("Initializing Bot...")
    time.sleep(3)
    
    application = Application.builder().token(TOKEN).build()
    
    # Register Handlers
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    # Start Polling with clean start
    print("Bot is Live!")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
