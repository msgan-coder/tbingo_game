import logging
import os
import random
import threading
import json
import asyncio
import time
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
game_session_id = str(int(time.time())) 
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330 
GAME_URL_BASE = "https://msgan-coder.github.io/tbingo_game/"

bot_app = None

logging.basicConfig(level=logging.INFO)

@app.route('/get_numbers')
def get_numbers():
    clean_recent = []
    for item in called_numbers[-5:][::-1]:
        clean_recent.append(item.split('-')[1] if '-' in item else item)
        
    return jsonify({
        "recent": clean_recent, 
        "active": game_active,
        "session_id": game_session_id
    })

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    global game_active, bot_app
    data = request.json
    user_name = data.get("user", "Unknown")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])
    
    # Pause calling while verifying
    game_active = False 
    
    if bot_app:
        loop = bot_app.loop
        kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{user_name}"),
               InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user_id}_{user_name}")]]
        
        # Admin Notification
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"🧐 **VERIFY CLAIM: @{user_name}**\nNumbers: {marked_nums}",
                reply_markup=InlineKeyboardMarkup(kb)
            ), loop
        )
        # Group Notification
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"⚠️ **BINGO CLAIMED by @{user_name}!**\nVerifying..."), loop
        )
    
    return jsonify({"status": "received"})

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = "👋 **Welcome to T-Bingo!**\n\nFee: 10 ETB | CBE: `1000141291193`\n📸 Send screenshot here."
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    await update.message.reply_text("✅ Admin is verifying your payment...")

    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"pay_app_{user.id}_{user.username}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej_{user.id}_{user.username}")]]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Payment from @{user.username}", reply_markup=InlineKeyboardMarkup(kb))

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, game_session_id
    if update.effective_user.id != ADMIN_ID: return
    
    game_active = True
    called_numbers = []
    game_session_id = str(int(time.time())) 
    
    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), 
                 InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 ADMIN CONTROLS", reply_markup=InlineKeyboardMarkup(admin_kb))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!**")
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75: return

    num = random.randint(1, 75)
    while any(str(num) == n.split('-')[1] if '-' in n else n == str(num) for n in called_numbers):
        num = random.randint(1, 75)
    
    letter = "B" if num <= 15 else "I" if num <= 30 else "N" if num <= 45 else "G" if num <= 60 else "O"
    full_call = f"{letter}-{num}"
    called_numbers.append(full_call)
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 **{full_call}**")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    query = update.callback_query
    data = query.data.split("_")
    
    if data[0] == "pay" and data[1] == "app":
        url = f"{GAME_URL_BASE}?s={game_session_id}"
        await context.bot.send_message(chat_id=data[2], text="✅ Approved!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play", web_app=WebAppInfo(url=url))]]))
        await query.edit_message_caption(caption="✅ Approved.")
    
    elif data[1] == "pause": game_active = False
    elif data[1] == "resume": game_active = True
    elif data[1] == "reset": 
        called_numbers = []
        game_active = False

    elif data[0] == "win":
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}!**")
        game_active = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        await query.edit_message_text(text=f"✅ Confirmed: @{data[2]}")
    
    elif data[0] == "lose":
        game_active = True
        await query.delete_message()

    await query.answer()

def main():
    global bot_app
    token = os.getenv("BOT_TOKEN")
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(token).build()
    bot_app = application 
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.run_polling()

if __name__ == "__main__":
    main()
