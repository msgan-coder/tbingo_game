import logging
import sqlite3
import os
import random
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK WEB SERVER ---
server = Flask('')
@server.route('/')
def home(): return "Professional Bingo Live"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003949842028 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10

game_active = False
called_numbers = []

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

def get_horizontal_board():
    """Formats the board with B-I-N-G-O horizontal rows"""
    rows = {
        "✨ B": [n for n in sorted(called_numbers) if 1 <= n <= 15],
        "✨ I": [n for n in sorted(called_numbers) if 16 <= n <= 30],
        "✨ N": [n for n in sorted(called_numbers) if 31 <= n <= 45],
        "✨ G": [n for n in sorted(called_numbers) if 46 <= n <= 60],
        "✨ O": [n for n in sorted(called_numbers) if 61 <= n <= 75]
    }
    board_str = "📊 **CALLED NUMBERS BOARD**\n`-------------------------`\n"
    for letter, nums in rows.items():
        num_list = ", ".join(map(str, nums)) if nums else "---"
        board_str += f"**{letter}** | {num_list}\n"
    return board_str

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 **FULL BOARD! Game Over.**")
        return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    called_numbers.append(num)
    
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    
    msg = f"🔔 **{letter}-{num}**\n\n{get_horizontal_board()}"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to start the game manually by Admin"""
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    
    conn = sqlite3.connect("bingo.db")
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()

    if count == 0:
        await update.message.reply_text("❌ No paid players found. Approve payments first!")
        return

    game_active = True
    called_numbers = []
    pot = count * ENTRY_FEE
    
    rules = (f"🚀 **BINGO START!**\n\n"
             f"💰 **Total Pot: {pot} ETB**\n"
             f"🏆 1 Line: {pot * 0.10:.1f} ETB\n"
             f"🏆 2 Lines: {pot * 0.15:.1f} ETB\n"
             f"🏆 3 Lines: {pot * 0.20:.1f} ETB\n"
             f"🏆 Full House: {pot * 0.25:.1f} ETB\n\n"
             f"⚠️ *The game has begun. Eyes on the board!*")
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")
    context.job_queue.run_repeating(auto_caller, interval=6, first=5, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await context.bot.send_message(chat_id=user_id, text="✅ Payment Approved! Good luck!", reply_markup=kb)
        await query.edit_message_caption(caption=f"✅ Approved for @{username}")

    elif data[0] == "rej":
        user_id = int(data[1])
        await context.bot.send_message(chat_id=user_id, text="❌ Your payment was rejected. Check your screenshot and try again.")
        await query.edit_message_caption(caption="❌ Payment Rejected")

    elif data[0] == "win":
        username = data[2]
        # Reset game
        global game_active, called_numbers
        game_active = False
        called_numbers = []
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        # Clear database for next round
        conn = sqlite3.connect("bingo.db")
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()

        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{username}**\n\n⚠️ Round Over. All previous access expired. Pay again for the next game!")
        await query.edit_message_text(text=f"✅ Win confirmed for @{username}. Pot reset.")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{user.username}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 From: @{user.username}", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Admin is verifying your payment...")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("play", start_cmd))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    application.run_polling()

if __name__ == "__main__":
    main()
