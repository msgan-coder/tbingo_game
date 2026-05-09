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

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)")
    conn.commit()
    conn.close()

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
        "💰 **Entry Fee:** 10 ETB per game.\n"
        "🏦 **Bank:** CBE (Commercial Bank of Ethiopia)\n"
        "🔢 **Account:** `1000141291193`\n\n"
        "📸 Please send a screenshot of your transfer here for Admin verification."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    
    await update.message.reply_text("✅ Screenshot received! Please wait while the Admin verifies your payment.")

    kb = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"pay_approve_{user.id}_{user.username}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"pay_reject_{user.id}_{user.username}")
        ]
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"💰 **New Payment Verification**\nFrom: @{user.username}\nID: `{user.id}`\nFee: 10 ETB",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get("action") == "claim_bingo":
            username = data.get("user", "Unknown")
            numbers = data.get("numbers", [])
            user_id = update.effective_user.id
            game_active = False 
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID, 
                text=f"⏸ **GAME PAUSED**\n\n@{username} has clicked BINGO! Checking card now..."
            )

            kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{username}"),
                   InlineKeyboardButton("❌ REJECT CLAIM", callback_data=f"lose_{user_id}_{username}")]]
            
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"🧐 **VERIFICATION REQUEST**\n\nPlayer: @{username}\nMarked: {', '.join(map(str, numbers))}\n\nCheck against board!",
                reply_markup=InlineKeyboardMarkup(kb)
            )
    except Exception as e:
        logging.error(f"WebApp Data Error: {e}")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, last_called, game_active
    if not game_active: return

    if len(called_numbers) >= 75:
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🏁 **FULL BOARD! Game over!**")
        return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    
    last_called = num
    called_numbers.append(num)
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    
    msg = f"🔔 **ROUND {len(called_numbers)}: {letter}-{num}**\n\n{get_horizontal_board()}"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    if update.effective_user.id != ADMIN_ID: return
    
    game_active = True
    called_numbers = []
    last_called = None
    
    rules = (
        "🚀 **NEW BINGO GAME STARTING!**\n\n"
        "💳 **ENTRY FEE:** 10 ETB\n"
        "🏦 **CBE:** `1000141291193`\n"
        "📩 Send screenshots to the BOT privately for approval.\n\n"
        "🎮 **Once approved, the bot will send you your play button!**"
    )
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")

    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
                 InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Full Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 **ADMIN CONTROL PANEL**", reply_markup=InlineKeyboardMarkup(admin_kb))
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, last_called
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    await query.answer()

    data = query.data.split("_")

    # Handle Payment Approval
    if data[0] == "pay":
        target_id = data[2]
        target_name = data[3]
        if data[1] == "approve":
            # --- FIX: Send the Play Button directly to the player ---
            play_kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
            await context.bot.send_message(
                chat_id=target_id, 
                text="✅ **Payment Approved!**\nClick the button below to get your card. Good luck!",
                reply_markup=InlineKeyboardMarkup(play_kb),
                parse_mode="Markdown"
            )
            await query.edit_message_caption(caption=f"✅ Payment Approved for @{target_name}")
        elif data[1] == "reject":
            await context.bot.send_message(chat_id=target_id, text="❌ **Payment Rejected.** Please send a valid screenshot of the 10 ETB transfer.")
            await query.edit_message_caption(caption=f"❌ Payment Rejected for @{target_name}")

    # Handle Win/Loss Verification
    elif data[0] == "win":
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WE HAVE A WINNER!**\nCongratulations @{data[2]}! 🏆")
        await query.edit_message_text(text=f"✅ Victory Confirmed for @{data[2]}")

    elif data[0] == "lose":
        game_active = True 
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"❌ @{data[2]}'s claim was invalid.\n▶️ **RESUMING GAME...**")
        await query.edit_message_text(text=f"❌ Claim Rejected for @{data[2]}")

    # Admin Control Panel
    elif data[1] == "pause":
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⏸ **GAME PAUSED BY ADMIN**")
    
    elif data[1] == "resume":
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="▶️ **GAME RESUMED**")

    elif data[1] == "reset":
        game_active = False
        called_numbers = []
        last_called = None
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ **GAME RESET BY ADMIN.**\nBoard cleared. Please pay 10 ETB for the next round!")
        await query.edit_message_text(text="♻️ Reset Successful.")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
