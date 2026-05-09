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

# --- FLASK SERVER ---
app = Flask(__name__)
CORS(app) 

@app.route('/')
def home():
    return "Bingo Engine Status: ONLINE"

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

# --- LOGIC ---
def get_horizontal_board():
    global last_called, called_numbers
    if not called_numbers:
        return "📊 **BOARD IS CURRENTLY EMPTY**"
        
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

# --- HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome to T-Bingo!**\n\n"
        "💰 **Entry Fee:** 10 ETB\n"
        "🔢 **Account (CBE):** `1000141291193`\n\n"
        "📸 Send your payment screenshot here. After approval, I will send you your **Play Button**."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    await update.message.reply_text("✅ Screenshot received! Waiting for Admin approval...")

    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"pay_app_{user.id}_{user.username}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej_{user.id}_{user.username}")
    ]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"💰 **Verification**\nFrom: @{user.username}\nID: `{user.id}`",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    await query.answer()

    data = query.data.split("_")

    if data[1] == "app":
        target_id = data[2]
        # SEND THE PLAY BUTTON TO THE USER
        play_kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
        await context.bot.send_message(
            chat_id=target_id, 
            text="✅ **Payment Approved!**\nUse the button below to join the game. This button is valid for 1 game.",
            reply_markup=InlineKeyboardMarkup(play_kb)
        )
        await query.edit_message_caption(caption="✅ Approved and Button Sent.")

    elif data[1] == "rej":
        await context.bot.send_message(chat_id=data[2], text="❌ Payment rejected. Please send a valid screenshot.")
        await query.edit_message_caption(caption="❌ Rejected.")

    # Win/Loss logic
    elif data[0] == "win":
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}** 🏆")
        await query.edit_message_text(text=f"✅ Winner Confirmed.")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active: return
    if len(called_numbers) >= 75:
        game_active = False
        return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    last_called = num
    called_numbers.append(num)
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 **{letter}-{num}**\n{get_horizontal_board()}", parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    game_active = True
    called_numbers = []
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **BINGO STARTING!**\nSend screenshots to the bot to get your play button!")
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app_tg = Application.builder().token(TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_command))
    app_tg.add_handler(CommandHandler("play", start_game))
    app_tg.add_handler(CallbackQueryHandler(admin_callback))
    app_tg.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
