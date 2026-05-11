import logging, os, random, threading, asyncio, time, sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIG ---
ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003988432330
GAME_URL_BASE = "https://msgan-coder.github.io/tbingo_game/" 
TOKEN = "8697522885:AAECWwZLHYhyswGameQESeSNgJW2quJr0es"

app = Flask(__name__)
CORS(app)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players 
                 (user_id INTEGER PRIMARY KEY, username TEXT, wins INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

# --- GLOBAL GAME STATE ---
state = {
    "active": False,
    "paused": False,
    "numbers": [],
    "session_id": str(int(time.time())),
    "start_time": 0
}

# --- FLASK API ---
@app.route('/get_numbers')
def get_numbers():
    return jsonify({
        "recent": state["numbers"][-5:][::-1],
        "all": state["numbers"],
        "active": state["active"],
        "paused": state["paused"],
        "timer": max(0, int(state["start_time"] - time.time())),
        "session_id": state["session_id"]
    })

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    data = request.json
    uid, name, marked = data.get("user_id"), data.get("user"), data.get("numbers", [])
    called_raw = [n.split('-')[1] for n in state["numbers"]]
    fake_nums = [n for n in marked if n not in called_raw and n != "FREE"]
    
    if fake_nums:
        msg = f"🚫 **FAKE CLAIM**\nUser: @{name}\nInvalid: {fake_nums}"
        bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(chat_id=ADMIN_ID, text=msg), 0)
        return jsonify({"status": "rejected", "message": "Anti-cheat triggered!"}), 403

    kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win|{uid}|{name}")]]
    bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(
        chat_id=ADMIN_ID, text=f"🏆 **VALID BINGO CLAIM**\nPlayer: @{name}", reply_markup=InlineKeyboardMarkup(kb)
    ), 0)
    return jsonify({"status": "success"})

# --- BOT COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to T-Bingo!\n\nPlease send your payment screenshot (10 ETB) to join the game.")

async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo: return
    
    photo_id = update.message.photo[-1].file_id
    # The callback_data MUST start with 'pay|' for the approval logic to work
    keyboard = [[
        InlineKeyboardButton("✅ APPROVE", callback_data=f"pay|app|{user.id}|{user.username or 'Player'}"),
        InlineKeyboardButton("❌ REJECT", callback_data=f"pay|rej|{user.id}|{user.username or 'Player'}")
    ]]

    await context.bot.send_photo(
        chat_id=ADMIN_ID, 
        photo=photo_id, 
        caption=f"💰 **New Payment**\nFrom: @{user.username} ({user.id})", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Screenshot received! Please wait for admin approval.")

async def start_game_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    state.update({"active": False, "paused": False, "numbers": [], "session_id": str(int(time.time())), "start_time": time.time() + 30})
    await context.bot.send_message(GROUP_CHAT_ID, "🕒 **BINGO STARTING IN 30 SECONDS!**")
    context.job_queue.run_once(begin_calling, 30)

async def pause_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    state["paused"] = True
    await update.message.reply_text("⏸ **Game Paused.**")

async def resume_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    state["paused"] = False
    await update.message.reply_text("▶️ **Game Resumed.**")

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    state["active"] = False
    for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
    await update.message.reply_text("🔄 **Game Reset.**")

# --- CORE GAME LOGIC ---

async def begin_calling(context: ContextTypes.DEFAULT_TYPE):
    state["active"] = True
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")
    await context.bot.send_message(GROUP_CHAT_ID, "🔔 **GAME ON!**")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    if not state["active"] or state["paused"] or len(state["numbers"]) >= 75: return
    n = random.randint(1, 75)
    while any(str(n) == x.split('-')[1] for x in state["numbers"]): n = random.randint(1, 75)
    l = "B" if n<=15 else "I" if n<=30 else "N" if n<=45 else "G" if n<=60 else "O"
    state["numbers"].append(f"{l}-{n}")
    await context.bot.send_message(GROUP_CHAT_ID, f"🎯 **{l}-{n}**")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')

    # 1. Handle Payment (Approve/Reject)
    if data[0] == "pay":
        action, uid, name = data[1], int(data[2]), data[3]
        if action == "app":
            url = f"{GAME_URL_BASE}?s={state['session_id']}"
            await context.bot.send_message(
                chat_id=uid, 
                text=f"✅ **Payment Approved!**\nWelcome {name}. Tap below to open your card:", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Open Bingo Card", web_app=WebAppInfo(url=url))]])
            )
            await query.edit_message_caption(caption=f"✅ Approved: @{name}")
        else:
            await context.bot.send_message(chat_id=uid, text="❌ Payment Rejected. Please contact admin.")
            await query.edit_message_caption(caption=f"❌ Rejected: @{name}")

    # 2. Handle Win Confirmation
    elif data[0] == "win":
        uid, name = data[1], data[2]
        state["active"] = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        conn = sqlite3.connect('users.db')
        conn.execute("INSERT OR IGNORE INTO players (user_id, username) VALUES (?,?)", (uid, name))
        conn.execute("UPDATE players SET wins = wins + 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        await context.bot.send_message(GROUP_CHAT_ID, f"🎊 **WINNER: @{name}!**")
        await query.edit_message_text(f"✅ Win Recorded for @{name}")

def main():
    global bot_app
    init_db()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, use_reloader=False), daemon=True).start()
    bot_app = Application.builder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("play", start_game_flow))
    bot_app.add_handler(CommandHandler("pause", pause_game))
    bot_app.add_handler(CommandHandler("resume", resume_game))
    bot_app.add_handler(CommandHandler("reset", reset_game))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot))
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    
    print("🤖 Bot started. Ready for payments and /play.")
    bot_app.run_polling()

if __name__ == "__main__": main()
