import logging, os, random, threading, asyncio, time
from flask import Flask, jsonify, request
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
app = Flask(__name__)
CORS(app)
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330
GAME_URL_BASE = "https://msgan-coder.github.io/tbingo_game/"

# --- GLOBAL STATE ---
game_active = False
called_numbers = []
game_session_id = str(int(time.time()))
bot_app = None

logging.basicConfig(level=logging.INFO)

@app.route('/')
def home(): return "BINGO SERVER ACTIVE", 200

@app.route('/get_numbers')
def get_numbers():
    # Fix: Get the numbers and strip the B-I-N-G-O letters for the circles
    clean_recent = [n.split('-')[1] if '-' in n else n for n in called_numbers[-5:][::-1]]
    return jsonify({"recent": clean_recent, "active": game_active, "session_id": game_session_id})

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    global game_active, bot_app
    data = request.json
    user_name = data.get("user", "Unknown")
    user_id = data.get("user_id")
    marked_nums = data.get("numbers", [])
    
    game_active = False # Pause calling
    
    if bot_app:
        # Use the bot's internal loop to send the message from the Flask thread
        kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win_{user_id}_{user_name}"),
               InlineKeyboardButton("❌ REJECT", callback_data=f"lose_{user_id}_{user_name}")]]
        
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(chat_id=ADMIN_ID, text=f"🧐 **VERIFY CLAIM: @{user_name}**\nNumbers: {marked_nums}", reply_markup=InlineKeyboardMarkup(kb)),
            bot_app.loop
        )
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"⚠️ **BINGO CLAIMED by @{user_name}!**\nVerifying..."),
            bot_app.loop
        )
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "bot_not_ready"}), 500

# --- BOT LOGIC ---
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active, called_numbers, game_session_id
    if update.effective_user.id != ADMIN_ID: return
    game_active = True
    called_numbers = []
    game_session_id = str(int(time.time()))
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="🚀 **GAME STARTED!**")
    context.job_queue.run_repeating(auto_caller, interval=12, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75: return
    num = random.randint(1, 75)
    while any(str(num) == (n.split('-')[1] if '-' in n else n) for n in called_numbers):
        num = random.randint(1, 75)
    letter = "B" if num <= 15 else "I" if num <= 30 else "N" if num <= 45 else "G" if num <= 60 else "O"
    full_call = f"{letter}-{num}"
    called_numbers.append(full_call)
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🔔 **{full_call}**")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    query = update.callback_query
    data = query.data.split("_")
    if data[0] == "win":
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎊 **WINNER: @{data[2]}!**")
        game_active = False
    elif data[0] == "lose":
        game_active = True
    await query.answer()

def main():
    global bot_app
    token = os.getenv("BOT_TOKEN")
    application = Application.builder().token(token).build()
    bot_app = application
    
    # Register handlers
    application.add_handler(CommandHandler("play", start_game))
    application.add_handler(CallbackQueryHandler(admin_callback))
    
    # Start Flask in a background thread
    def run_flask():
        app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
    
    threading.Thread(target=run_flask, daemon=True).start()
    application.run_polling()

if __name__ == "__main__":
    main()
