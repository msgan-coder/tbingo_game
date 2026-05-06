import logging
import sqlite3
import json
import os  # CRITICAL: This was missing!
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
# Pulls the secret token from Render's Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5431140655
GAME_URL = "https://msgan-coder.github.io/tbingo_game/" 
ENTRY_FEE = 10 
COMMISSION = 0.30  # 30% profit for admin

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
    if not update.message.photo:
        return
        
    photo_id = update.message.photo[-1].file_id
    
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]
    ]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"💰 NEW PAYMENT\nFrom: @{user.username}\nID: {user.id}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Verification sent to Admin. You will be notified shortly.")

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_data = update.effective_message.web_app_data.data
    data = json.loads(raw_data)
    user = update.message.from_user

    if data.get("action") == "claim_bingo":
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🏆 BINGO CLAIMED!\n\nUser: @{user.username}\nID: {user.id}\nNumbers: {data.get('numbers')}"
        )
        await update.message.reply_text("Your Bingo claim has been sent to the Admin! Please wait.")

# --- ADMIN HANDLERS ---
async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, user_id = data[0], int(data[1])

    conn = sqlite3.connect('bingo.db')
    c = conn.cursor()

    if action == "app":
        c.execute("INSERT OR REPLACE INTO players VALUES (?, ?, 'PAID')", (user_id, "user"))
        conn.commit()
        play_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))
        ]])
        await context.bot.send_message(user_id, "✅ Verified! Click below to enter the game.", reply_markup=play_keyboard)
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ APPROVED")
    
    elif action == "rej":
        await context.bot.send_message(user_id, "❌ Payment rejected. Screenshot invalid.")
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ REJECTED")
    
    conn.close()
    await query.answer()

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect('bingo.db')
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()
    
    total_pot = count * ENTRY_FEE
    profit = total_pot * COMMISSION
    winner_gets = total_pot - profit
    
    await update.message.reply_text(
        f"📊 GAME STATS\nPlayers: {count}\nPot: {total_pot} ETB\nProfit: {profit} ETB\nWinner: {winner_gets} ETB"
    )

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('bingo.db')
    conn.execute("DELETE FROM players")
    conn.commit()
    conn.close()
    await update.message.reply_text("🔄 Game has been reset.")

# --- MAIN RUNNER ---
if __name__ == '__main__':
    init_db()
    print("Bingo Bot is starting...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("reset", reset_game))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(CallbackQueryHandler(admin_button))
    
    app.run_polling()
