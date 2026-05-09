import logging
import os
import random
import threading
import json
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
bot_app = None # Global placeholder for the telegram app

@app.route('/get_numbers')
def get_numbers():
    return jsonify({"recent": called_numbers[-5:][::-1], "active": game_active})

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    global game_active, bot_app
    data = request.json
    user_name = data.get("user", "Unknown")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])
    
    game_active = False # Pause the game while admin verifies
    
    # Send verification request to Admin
    kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{user_name}"),
           InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user_id}_{user_name}")]]
    
    # Use the bot to notify group and admin
    loop = bot_app.loop
    loop.create_task(bot_app.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"⚠️ **BINGO CLAIMED by @{user_name}!**\nChecking card..."))
    loop.create_task(bot_app.bot.send_message(chat_id=ADMIN_ID, text=f"🧐 **VERIFY @{user_name}**\nNumbers: {marked_nums}", reply_markup=InlineKeyboardMarkup(kb)))
    
    return jsonify({"status": "received"})

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome to T-Bingo!** Send your payment screenshot here for approval.")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id 
    await update.message.reply_text("✅ Screenshot received! Please wait for approval.")
    
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"pay_app_{user.id}_{user.username}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej_{user.id}_{user.username}")]]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Payment from @{user.username}", reply_markup=InlineKeyboardMarkup(kb))

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers
    if update.effective_user.id != ADMIN_ID: return
    game_active, called_numbers = True, []
    
    # Admin Controls to Private Chat
    admin_kb = [[InlineKeyboardButton("⏸ Pause", callback_data="adm_pause"), InlineKeyboardButton("▶️ Resume", callback_data="adm_resume")],
                [InlineKeyboardButton("♻️ Reset", callback_data="adm_reset")]]
    
    await context.bot.send_message(chat_id=ADMIN_ID, text="🕹 **ADMIN CONTROL PANEL**", reply_markup=InlineKeyboardMarkup(admin_kb))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!**")
    
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active: return
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
        await context.bot.send_message(chat_id=data[2], text="✅ Approved!", reply_markup=InlineKeyboardMarkup(play_kb))
    elif data[0] == "win":
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}!**")
    elif data[0] == "adm" and data[1] == "pause":
        game_active = False
    elif data[0] == "adm" and data[1] == "resume":
        game_active = True
    
    await query.answer()

def main():
    global bot_app
    threading.Thread(target=run_flask, daemon=True).start()
    bot_app = Application.builder().token(os.getenv("BOT_TOKEN")).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("play", start_game))
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    bot_app.run_polling()

if __name__ == "__main__":
    main()
