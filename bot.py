import logging
import sqlite3
import json
import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003949842028 # Confirmed from your screenshot
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10

# Global Game State
game_active = False
called_numbers = []

logging.basicConfig(level=logging.INFO)

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

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 Game Over!")
        return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    called_numbers.append(num)
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, 
                                   text=f"🔔 **NEW NUMBER: {letter}-{num}**\n\n{get_bingo_board()}", 
                                   parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect("bingo.db")
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()

    if count == 0:
        await update.message.reply_text("❌ No players have paid yet!")
        return

    # FIX: Set global variables BEFORE starting logic
    game_active = True
    called_numbers = []
    
    pot = count * ENTRY_FEE
    rules = (f"🚀 **BINGO START!**\n\n"
             f"💰 **Pot: {pot} ETB**\n"
             f"🏆 1 Line: {pot * 0.10:.1f} ETB\n"
             f"🏆 2 Lines: {pot * 0.15:.1f} ETB\n"
             f"🏆 3 Lines: {pot * 0.20:.1f} ETB\n"
             f"🏆 Full House: {pot * 0.25:.1f} ETB\n\n"
             f"🚫 Chat Locked!")
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
        await context.bot.send_message(chat_id=user_id, text="✅ Payment Verified!", reply_markup=kb)
        await query.edit_message_reply_markup(reply_markup=None)

    elif data[0] == "win":
        username = data[2]
        game_active = False
        called_numbers = []
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{username}**\n⚠️ Payments expired. Pay again for next round!")
        
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
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 From: @{user.username}", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Admin is checking payment...")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🏆 **BINGO CLAIM!** @{user.username}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm Win", callback_data=f"win_{user.id}_{user.username}")]]))

def main():
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    application.run_polling()

if __name__ == "__main__":
    main()
