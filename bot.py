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
        "timer": max(0, int(state["start_time"] - time.time()))
    })

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    data = request.json
    uid, name, marked = data.get("user_id"), data.get("user"), data.get("numbers", [])
    
    # ANTI-CHEAT: Check if marked numbers were actually called
    fake_nums = [n for n in marked if n not in [num.split('-')[1] for num in state["numbers"]] and n != "FREE"]
    
    if fake_nums:
        # AUTO-KICK LOGIC (Notification to Admin)
        msg = f"🚫 **FAKE CLAIM DETECTED**\nUser: @{name}\nMarked invalid: {fake_nums}\nAction: Recommended Kick."
        send_to_telegram(ADMIN_ID, msg)
        return jsonify({"status": "rejected", "message": "Anti-cheat triggered!"}), 403

    # If valid, alert admin
    kb = [[InlineKeyboardButton("✅ CONFIRM WIN", callback_data=f"win|{uid}|{name}")]]
    send_to_telegram(ADMIN_ID, f"🏆 **VALID BINGO!**\nPlayer: @{name}\nVerify quickly!", kb)
    return jsonify({"status": "success"})

def send_to_telegram(chat_id, text, reply_markup=None):
    asyncio.run_coroutine_threadsafe(bot_app.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup), bot_app.loop)

# --- BOT LOGIC ---
async def start_game_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    state["start_time"] = time.time() + 30 # 30 second countdown
    state["numbers"] = []
    await context.bot.send_message(GROUP_CHAT_ID, "🕒 **BINGO STARTING IN 30 SECONDS!**\nGet your cards ready!")
    context.job_queue.run_once(begin_calling, 30)

async def begin_calling(context: ContextTypes.DEFAULT_TYPE):
    state["active"] = True
    context.job_queue.run_repeating(auto_caller, interval=10, name="bingo_job")
    await context.bot.send_message(GROUP_CHAT_ID, "🔔 **GAME ON! First number coming...**")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    if not state["active"] or len(state["numbers"]) >= 75: return
    n = random.randint(1, 75)
    while any(str(n) == x.split('-')[1] for x in state["numbers"]): n = random.randint(1, 75)
    l = "B" if n<=15 else "I" if n<=30 else "N" if n<=45 else "G" if n<=60 else "O"
    state["numbers"].append(f"{l}-{n}")
    await context.bot.send_message(GROUP_CHAT_ID, f"🎯 **{l}-{n}**")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('users.db')
    users = conn.execute("SELECT username, wins FROM players ORDER BY wins DESC LIMIT 10").fetchall()
    conn.close()
    text = "📊 **TOP PLAYERS**\n" + "\n".join([f"{i+1}. {u[0]} - {u[1]} wins" for i, u in enumerate(users)])
    await update.message.reply_text(text)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|')
    if data[0] == "win":
        uid, name = data[1], data[2]
        state["active"] = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        conn = sqlite3.connect('users.db')
        conn.execute("INSERT OR IGNORE INTO players (user_id, username) VALUES (?,?)", (uid, name))
        conn.execute("UPDATE players SET wins = wins + 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        
        await context.bot.send_message(GROUP_CHAT_ID, f"🎊 **CONGRATULATIONS @{name}!**\nYou won the prize! 💰")
        await query.edit_message_text("✅ Win recorded in Database.")

def main():
    global bot_app
    init_db()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("play", start_game_flow))
    bot_app.add_handler(CommandHandler("top", leaderboard))
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    bot_app.run_polling()

if __name__ == "__main__": main()
