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
GROUP_CHAT_ID = -1003949842028 
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

def get_player_count():
    conn = sqlite3.connect('bingo.db')
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()
    return count

# --- FORMATTING THE BOARD ---
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

# --- AUTO CALLER ---
async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    while game_active and len(called_numbers) < 75:
        await asyncio.sleep(5)
        num = random.randint(1, 75)
        while num in called_numbers:
            num = random.randint(1, 75)
        
        called_numbers.append(num)
        letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"

        text = f"🔔 **NEW NUMBER: {letter}-{num}**\n\n{get_bingo_board()}"
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode="Markdown")

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (f"👋 Hello {user.first_name}!\n\n"
            f"🇪🇹 Welcome to Telebirr Bingo!\n"
            f"Entry Fee: {ENTRY_FEE} ETB\n"
            f"Transfer: 0931792446\n\n"
            "📸 Send a screenshot of your payment to enter.")
    await update.message.reply_text(text)

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, caller_task
    if update.effective_user.id != ADMIN_ID: return
    
    count = get_player_count()
    if count == 0:
        await update.message.reply_text("❌ Cannot start. No approved players yet!")
        return

    game_active = True
    rules = (f"🚀 **BINGO START!**\n\n"
             f"👥 Players: {count}\n"
             f"💰 Total Pot: {count * ENTRY_FEE} ETB\n"
             f"✨ 1 Line | 2 Lines | Full House\n\n"
             f"🚫 Chat is LOCKED. Good luck!")
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")
    caller_task = asyncio.create_task(auto_caller(context))

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{user.username}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 From: @{user.username}", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Admin is checking your payment. Stand by!")

async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    
    if data[0] == "app":
        user_id, username = int(data[1]), data[2]
        conn = sqlite3.connect('bingo.db')
        conn.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, username))
        conn.commit()
        conn.close()
        
        # Notify Group
        current_players = get_player_count()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"✅ New Player Joined: @{username}\n📊 Total Players: {current_players}")
        
        # Send Play Button to Player
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]])
        await context.bot.send_message(chat_id=user_id, text="✅ Verified! Your card is ready:", reply_markup=kb)
        await query.edit_message_reply_markup(reply_markup=None)
    
    elif data[0] == "win":
        global game_active, called_numbers
        user_id, username = int(data[1]), data[2]
        
        # Calculate Prize
        count = get_player_count()
        pot = count * ENTRY_FEE
        prize = pot * (1 - COMMISSION)

        await context.bot.send_message(chat_id=GROUP_CHAT_ID, 
            text=f"🎊 **WINNER FOUND!** 🎊\n\n👤 Winner: @{username}\n💰 Prize: {prize} ETB\n\n🔄 Game has been reset. Pay for the next round!", 
            parse_mode="Markdown")
        
        # RESET EVERYTHING
        game_active = False
        called_numbers = []
        conn = sqlite3.connect('bingo.db')
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()
        await query.edit_message_reply_markup(reply_markup=None)

    elif data[0] == "resume":
        global game_active, caller_task
        game_active = True
        caller_task = asyncio.create_task(auto_caller(context))
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="❌ False claim. The game continues!")
        await query.edit_message_reply_markup(reply_markup=None)

# --- LOCK CHAT ---
async def lock_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if game_active and update.effective_chat.id == GROUP_CHAT_ID:
        if update.effective_user.id != ADMIN_ID:
            try: await update.message.delete()
            except: pass

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, caller_task
    data = json.loads(update.effective_message.web_app_data.data)
    user = update.effective_user
    if data.get("action") == "claim_bingo":
        game_active = False
        if caller_task: caller_task.cancel()
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🏆 **BINGO!** @{user.username}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm Winner", callback_data=f"win_{user.id}_{user.username}"),
                                               InlineKeyboardButton("❌ Fake", callback_data="resume")]]))

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
