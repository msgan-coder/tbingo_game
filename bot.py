import logging
import sqlite3
import json
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"
ENTRY_FEE = 10
COMMISSION = 0.30

# Global list to track called numbers for the current round
called_numbers = []

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('bingo.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players 
                 (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)''')
    conn.commit()
    conn.close()

# --- PLAYER HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (f"🇪🇹 Welcome to Telebirr Bingo!\n\n"
            f"Entry Fee: {ENTRY_FEE} ETB\n"
            f"1. Transfer to: 0931792446 (Telebirr)\n"
            f"2. Send the screenshot here for verification.")
    await update.message.reply_text(text)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    photo_id = update.message.photo[-1].file_id
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"💰 NEW PAYMENT\nFrom: @{user.username}\nID: {user.id}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Verification sent to Admin. You will be notified shortly.")

# --- ADMIN HANDLERS (Buttons & Calls) ---

async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Stop the loading spinner on the button
    
    data = query.data.split("_")
    action, user_id = data[0], int(data[1])
    
    conn = sqlite3.connect('bingo.db')
    c = conn.cursor()
    
    if action == "app":
        c.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, "user"))
        conn.commit()
        
        # Send the Play Button to the PLAYER
        play_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))
        ]])
        await context.bot.send_message(
            chat_id=user_id, 
            text="✅ Your payment was verified! Click below to start your card.", 
            reply_markup=play_keyboard
        )
        
        # REMOVE buttons from Admin view and show status
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n✅ STATUS: APPROVED",
            reply_markup=None # This makes the buttons disappear
        )
        
    elif action == "rej":
        await context.bot.send_message(user_id, "❌ Your payment screenshot was rejected. Please contact admin.")
        
        # REMOVE buttons from Admin view and show status
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ STATUS: REJECTED",
            reply_markup=None # This makes the buttons disappear
        )
    
    conn.close()

async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /call to pick a random number 1-75"""
    if update.message.from_user.id != ADMIN_ID: return
    
    if len(called_numbers) >= 75:
        await update.message.reply_text("All numbers have been called! Use /reset to start over.")
        return

    num = random.randint(1, 75)
    while num in called_numbers:
        num = random.randint(1, 75)
    
    called_numbers.append(num)
    
    # Send to Admin (and you can forward this to your channel)
    msg = f"🎰 **NEW NUMBER: {num}**\n\nFull History: {', '.join(map(str, sorted(called_numbers)))}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('bingo.db')
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()
    total_pot = count * ENTRY_FEE
    profit = total_pot * COMMISSION
    winner_gets = total_pot - profit
    await update.message.reply_text(f"📊 STATS\nPlayers: {count}\nPot: {total_pot} ETB\nProfit: {profit} ETB\nWinner Prize: {winner_gets} ETB")

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets players AND called numbers"""
    if update.message.from_user.id != ADMIN_ID: return
    
    # Reset Database
    conn = sqlite3.connect('bingo.db')
    conn.execute("DELETE FROM players")
    conn.commit()
    conn.close()
    
    # Reset Local List
    global called_numbers
    called_numbers = []
    
    await update.message.reply_text("🔄 Game has been reset. Database cleared and number history wiped.")

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    print("Bingo Bot is starting...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("reset", reset_game))
    app.add_handler(CommandHandler("call", call_number)) # The random caller
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(CallbackQueryHandler(admin_button))
    
    app.run_polling()
