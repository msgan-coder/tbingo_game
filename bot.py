import logging
import os
import random
import threading
import asyncio
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler, 
    ContextTypes
)

# --- CONFIGURATION ---
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330
GAME_URL_BASE = "https://msgan-coder.github.io/tbingo_game/"

app = Flask(__name__)
# Enhanced CORS to prevent browser blocks
CORS(app, resources={r"/*": {"origins": "*"}})

# --- GLOBAL STATE ---
game_active = False
called_numbers = []
game_session_id = str(int(time.time()))
bot_app = None

logging.basicConfig(level=logging.INFO)

# --- FLASK ROUTES ---

@app.route('/')
def health():
    return "Bingo Server is Live!"

@app.route('/get_numbers')
def get_numbers():
    # Returns raw numbers as a text string: "49, 14, 13, 67, 75"
    # We ignore the 't' parameter from the browser but it forces a fresh fetch
    clean_nums = [n.split('-')[1] for n in called_numbers[-5:][::-1]]
    return jsonify({
        "recent_text": ", ".join(clean_nums) if clean_nums else "Waiting...",
        "active": game_active,
        "session_id": game_session_id
    })

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    global bot_app
    data = request.json
    user_name = data.get("user", "Player")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])

    if bot_app and user_id:
        loop = bot_app.loop
        keyboard = [[
            InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win|{user_id}|{user_name}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"lose|{user_id}|{user_name}")
        ]]
        
        # Bridge Flask to the Telegram Bot Loop
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 **BINGO CLAIMED**\n\nPlayer: @{user_name}\nID: {user_id}\nNumbers: {', '.join(marked_nums)}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            ), loop
        )
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"⚠️ **BINGO!** @{user_name} is claiming a win! Verifying..."
            ), loop
        )
        return jsonify({"status": "received"}), 200
    
    return jsonify({"status": "error", "reason": "bot_not_ready"}), 500

# --- BOT COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 Welcome to T-Bingo!\n\n"
        "Fee: 10 ETB\n"
        "CBE: 1000141291193\n\n"
        "📸 Send payment screenshot to join."
    )
    await update.message.reply_text(welcome)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo: return
    
    photo_id = update.message.photo[-1].file_id
    await update.message.reply_text("✅ Payment sent! Admin will verify soon.")

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"pay|app|{user.id}|{user.username or 'player'}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"pay|rej|{user.id}|{user.username or 'player'}")
    ]]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"Payment from @{user.username}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, game_session_id
    if update.effective_user.id != ADMIN_ID: return

    game_active = True
    called_numbers = []
    game_session_id = str(int(time.time()))

    admin_keyboard = [
        [InlineKeyboardButton("⏸ Pause", callback_data="adm|pause"),
         InlineKeyboardButton("▶ Resume", callback_data="adm|resume")],
        [InlineKeyboardButton("♻ Reset Game", callback_data="adm|reset")]
    ]

    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 ADMIN CONTROLS", reply_markup=InlineKeyboardMarkup(admin_keyboard))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!**")

    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75: return

    num = random.randint(1, 75)
    while any(str(num) == n.split('-')[1] for n in called_numbers):
        num = random.randint(1, 75)

    letter = "B" if num <= 15 else "I" if num <= 30 else "N" if num <= 45 else "G" if num <= 60 else "O"
    full_call = f"{letter}-{num}"
    called_numbers.append(full_call)
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 {full_call}")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")

    if data[0] == "pay" and data[1] == "app":
        user_id = int(data[2])
        url = f"{GAME_URL_BASE}?s={game_session_id}"
        await context.bot.send_message(
            chat_id=user_id, 
            text="✅ Approved!", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=url))]])
        )
        await query.edit_message_caption("✅ Approved.")

    elif data[0] == "adm":
        if data[1] == "pause": game_active = False
        elif data[1] == "resume": game_active = True
        elif data[1] == "reset":
            called_numbers = []
            game_active = False
            for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="♻️ Game has been reset by Admin.")

    elif data[0] == "win":
        username = data[2]
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{username}** 🎊\nGame Over.")
        await query.edit_message_text(text=f"✅ Confirmed Win for @{username}")

    elif data[0] == "lose":
        game_active = True
        await query.edit_message_text(text="❌ Claim rejected. Game resumed.")

# --- MAIN ---

def main():
    global bot_app
    token = os.getenv("BOT_TOKEN")
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    
    application = Application.builder().token(token).build()
    bot_app = application

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))

    application.run_polling()

if __name__ == "__main__":
    main()
