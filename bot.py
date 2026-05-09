import logging
import os
import random
import threading
import json
import asyncio
from flask import Flask, jsonify, request
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER ---
app = Flask(__name__)
CORS(app) 

# Global State
game_active = False
called_numbers = []
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330 
GAME_URL = "https://msgan-coder.github.io/tbingo_game/"

logging.basicConfig(level=logging.INFO)

@app.route('/get_numbers')
def get_numbers():
    return jsonify({"recent": called_numbers[-5:][::-1], "active": game_active})

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    global game_active
    data = request.json
    user_name = data.get("user", "Unknown")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])
    
    game_active = False # Pause calling
    
    # Send to Admin
    kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{user_name}"),
           InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user_id}_{user_name}")]]
    
    # We use a dummy request to trigger the bot message from outside the bot loop
    # In production, use a queue or the bot's job_queue
    print(f"BINGO CLAIMED BY {user_name}")
    return jsonify({"status": "received"})

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 **Welcome to T-Bingo!**\n\n"
        "💰 Fee: 10 ETB | CBE: `1000141291193`\n"
        "📸 Send screenshot here for approval."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    await update.message.reply_text("✅ Received! Admin is verifying...")

    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"pay_app_{user.id}_{user.username}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej_{user.id}_{user.username}")]]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Payment from @{user.username}", reply_markup=InlineKeyboardMarkup(kb))

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    
    game_active = True
    called_numbers = []
    
    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
                 InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 **ADMIN CONTROLS**", reply_markup=InlineKeyboardMarkup(admin_kb))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!** Prepare your cards.")
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75: return

    num = random.randint(1, 75)
    while num in called_numbers: num = random.randint(1, 75)
    called_numbers.append(num)
    
    letter = "B" if num<=15 else "I" if num<=30 else "N" if num<=45 else "G" if num<=60 else "O"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 **{letter}-{num}**")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    data = query.data.split("_")
    
    if data[0] == "pay" and data[1] == "app":
        play_kb = [[InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=GAME_URL))]]
        await context.bot.send_message(chat_id=data[2], text="✅ Payment Approved! Click below to play.", reply_markup=InlineKeyboardMarkup(play_kb))
        await query.edit_message_caption(caption="✅ Approved.")
    
    elif data[0] == "adm" and data[1] == "pause":
        game_active = False
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⏸ Game Paused.")
        
    elif data[0] == "adm" and data[1] == "resume":
        game_active = True
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="▶️ Game Resumed.")

    await query.answer()

def main():
    token = os.getenv("BOT_TOKEN")
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(token).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    application.run_polling()

if __name__ == "__main__":
    main()
