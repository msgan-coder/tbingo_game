import logging
import sqlite3
import os
import random
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK WEB SERVER (To stop Render Timeout) ---
server = Flask('')

@server.route('/')
def home():
    return "Bingo Bot is Online and Live!"

def run_flask():
    # Render uses the PORT environment variable; default to 10000
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003949842028 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10

# Global Game State
game_active = False
called_numbers = []

logging.basicConfig(level=logging.INFO)

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

def get_bingo_board():
    b = [n for n in sorted(called_numbers) if 1 <= n <= 15]
    i = [n for n in sorted(called_numbers) if 16 <= n <= 30]
    n = [n for n in sorted(called_numbers) if 31 <= n <= 45]
    g = [n for n in sorted(called_numbers) if 46 <= n <= 60]
    o = [n for n in sorted(called_numbers) if 61 <= n <= 75]
    return (f"✨ **B**: {', '.join(map(str, b))}\n"
            f"✨ **I**: {', '.join(map(str, i))}\n"
            f"✨ **N**: {', '.join(map(str, n))}\n"
            f"✨ **G**: {', '.join(map(str, g))}\n"
            f"✨ **O**: {', '.join(map(str, o))}")

# --- BOT ACTIONS ---
async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 Game Over! All numbers called.")
        return

    num = random.randint(1, 75)
    while num in called_numbers: 
        num = random.randint(1, 75)
    
    called_numbers.append(num)
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID, 
        text=f"🔔 **NEW NUMBER: {letter}-{num}**\n\n{get_bingo_board()}", 
        parse_mode="Markdown"
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect("bingo.db")
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()

    if count == 0:
        await update.message.reply_text("❌ No players have paid yet!")
        return

    game_active = True
    called_numbers = []
    pot = count * ENTRY_FEE
    
    # Updated Prize rules including 3 Lines
    rules = (f"🚀 **BINGO START!**\n\n"
             f"💰 **Pot: {pot} ETB**\n"
             f"🏆 1 Line: {pot * 0.10:.1f} ETB\n"
             f"🏆 2 Lines: {pot * 0.15:.1f} ETB\n"
             f"🏆 3 Lines: {pot * 0.20:.1f} ETB\n"
             f"🏆 Full House: {pot * 0.25:.1f} ETB\n\n"
             f"🚫 Chat Locked! Watch the board.")
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")
    context.job_queue.run_repeating(auto_caller, interval=5, first=5, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")

    if data[0] == "app":
        user_id, username = int(data[1]), data[2]
        conn = sqlite3.connect("bingo.db")
        conn.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, username))
        conn.commit()
        conn.close()
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]])
        await context.bot.send_message(chat_id=user_id, text="✅ Payment Verified! Access your card below:", reply_markup=kb)
        await query.edit_message_reply_markup(reply_markup=None)

    elif data[0] == "win":
        username = data[2]
        game_active = False
        called_numbers = []
        # Stop the caller
        for job in context.job_queue.get_jobs_by_name("bingo_job"): 
            job.schedule_removal()
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=f"🎊 **WINNER: @{username}**\n\n⚠️ Round Finished. All previous payments have EXPIRED. Pay 10 ETB for the next round!"
        )
        
        # Reset Database (Expire payments)
        conn = sqlite3.connect("bingo.db")
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()
        await query.edit_message_reply_markup(reply_markup=None)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{user.username}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID, 
        photo=photo_id, 
        caption=f"💰 Payment from: @{user.username}", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Admin is checking your payment. Please wait for confirmation.")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_message(
        chat_id=ADMIN_ID, 
        text=f"🏆 **BINGO CLAIM!** @{user.username} says they won!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm Win", callback_data=f"win_{user.id}_{user.username}")]]))

# --- MAIN EXECUTION ---
def main():
    init_db()
    
    # 1. Start Flask web server in a separate thread
    keep_alive()
    
    # 2. Start Telegram Bot
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    
    print("Bot is polling and Flask is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
