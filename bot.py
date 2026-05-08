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
GROUP_CHAT_ID = -1003949842028  # UPDATED from your screenshot
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10
COMMISSION = 0.30

# Global Game State
game_active = False
called_numbers = []
caller_task = None

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('bingo.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players 
                 (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)''')
    conn.commit()
    conn.close()

# --- FORMATTING THE BOARD ---
def get_bingo_board():
    """Organizes numbers into B-I-N-G-O columns for display"""
    b = [n for n in sorted(called_numbers) if 1 <= n <= 15]
    i = [n for n in sorted(called_numbers) if 16 <= n <= 30]
    n = [n for n in sorted(called_numbers) if 31 <= n <= 45]
    g = [n for n in sorted(called_numbers) if 46 <= n <= 60]
    o = [n for n in sorted(called_numbers) if 61 <= n <= 75]
    
    board = (
        f"✨ **B**: {', '.join(map(str, b))}\n"
        f"✨ **I**: {', '.join(map(str, i))}\n"
        f"✨ **N**: {', '.join(map(str, n))}\n"
        f"✨ **G**: {', '.join(map(str, g))}\n"
        f"✨ **O**: {', '.join(map(str, o))}"
    )
    return board

# --- CHAT LOCK ---
async def lock_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if game_active and update.effective_chat.id == GROUP_CHAT_ID:
        if update.effective_user.id != ADMIN_ID:
            try:
                await update.message.delete()
            except: pass

# --- AUTO CALLER ---
async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    while game_active and len(called_numbers) < 75:
        await asyncio.sleep(5)
        num = random.randint(1, 75)
        while num in called_numbers:
            num = random.randint(1, 75)
        
        called_numbers.append(num)
        
        # Decide the Letter
        letter = ""
        if 1 <= num <= 15: letter = "B"
        elif 16 <= num <= 30: letter = "I"
        elif 31 <= num <= 45: letter = "N"
        elif 46 <= num <= 60: letter = "G"
        elif 61 <= num <= 75: letter = "O"

        text = (
            f"🔔 **NEW NUMBER: {letter}-{num}**\n\n"
            f"{get_bingo_board()}"
        )
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode="Markdown")

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIXED: This now works for everyone who clicks /start"""
    user = update.effective_user
    text = (f"👋 Hello {user.first_name}!\n\n"
            f"🇪🇹 Welcome to Telebirr Bingo!\n"
            f"Entry Fee: {ENTRY_FEE} ETB\n"
            f"Transfer: 0931792446\n\n"
            "📸 Send a screenshot of your payment to enter the game.")
    await update.message.reply_text(text)

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, caller_task
    if update.effective_user.id != ADMIN_ID: return
    game_active = True
    rules = "🚀 **BINGO START!**\n\n1 Line | 2 Lines | Full House\n\n🚫 Chat is LOCKED."
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")
    caller_task = asyncio.create_task(auto_caller(context))

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 From: @{user.username}", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Admin is checking your payment. Stand by!")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, caller_task
    data = json.loads(update.effective_message.web_app_data.data)
    user = update.effective_user
    if data.get("action") == "claim_bingo":
        game_active = False
        if caller_task: caller_task.cancel()
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🏆 **BINGO!** @{user.username}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Winner", callback_data=f"win_{user.id}_{user.username}"),
                                               InlineKeyboardButton("❌ Fake", callback_data="resume")]]))

async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    
    if data[0] == "app":
        conn = sqlite3.connect('bingo.db')
        conn.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (int(data[1]), "user"))
        conn.commit()
        conn.close()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]])
        await context.bot.send_message(chat_id=int(data[1]), text="✅ Verified! Enter here:", reply_markup=kb)
        await query.edit_message_reply_markup(reply_markup=None)
    
    elif data[0] == "win":
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}**\nGame Over.")
        await query.edit_message_reply_markup(reply_markup=None)

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", start_game))
    app.add_handler(CallbackQueryHandler(admin_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lock_chat_handler))
    app.run_polling()
