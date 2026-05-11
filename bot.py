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
PAYMENT_ACC = "1000141291193 (CBE)"

app = Flask(__name__)
CORS(app)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, wins INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

# --- GLOBAL GAME STATE ---
state = {
    "active": False,
    "paused": False,
    "numbers": [],
    "win_mode": "Full House",
    "session_id": str(int(time.time())),
    "start_time": 0,
    "approved_players": [] 
}

# --- FLASK API ---
@app.route('/get_numbers')
def get_numbers():
    return jsonify({
        "recent": state["numbers"][-5:][::-1],
        "active": state["active"],
        "paused": state["paused"],
        "timer": max(0, int(state["start_time"] - time.time())),
        "session_id": state["session_id"]
    })

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    data = request.json
    uid = data.get("user_id")
    name = data.get("user")
    marked = data.get("numbers", [])
    
    if uid not in state["approved_players"]:
        return jsonify({"status": "rejected", "message": "You are not an approved player for this round!"}), 403

    called_raw = [n.split('-')[1] for n in state["numbers"]]
    fake_nums = [n for n in marked if n not in called_raw and n != "FREE"]
    
    if fake_nums:
        bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(chat_id=ADMIN_ID, text=f"🚫 **FAKE CLAIM**: @{name}"), 0)
        return jsonify({"status": "rejected", "message": "Anti-cheat: Numbers not called!"}), 403

    kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win|{uid}|{name}")]]
    bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(
        chat_id=ADMIN_ID, text=f"🏆 **VALID {state['win_mode']} CLAIM**\nPlayer: @{name}", reply_markup=InlineKeyboardMarkup(kb)
    ), 0)
    return jsonify({"status": "success"})

# --- BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to T-Bingo!\n\nPlease send your payment screenshot (10 ETB) to join the game.")

async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state["active"]:
        await update.message.reply_text("🚫 **ጨዋታው ተጀምሯል።**\n\nአሁን ክፍያ አንቀበልም። እባክዎ አሸናፊ ተለይቶ ቀጣይ ጨዋታ ሲጀመር ይላኩ።")
        return

    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"pay|app|{user.id}|{user.username or 'Player'}")]]
    
    await context.bot.send_photo(ADMIN_ID, photo_id, caption=f"💰 New Payment: @{user.username}", reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("✅ ደረሰኙ ተልኳል። አድሚኑ እስኪያረጋግጥ ድረስ በትዕግስት ይጠብቁ።")

async def start_game_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = [
        [InlineKeyboardButton("1 Line", callback_data="set|1 Line"), InlineKeyboardButton("2 Lines", callback_data="set|2 Lines")],
        [InlineKeyboardButton("3 Lines", callback_data="set|3 Lines"), InlineKeyboardButton("Full House", callback_data="set|Full House")]
    ]
    await update.message.reply_text("🎯 **የጨዋታውን አይነት ይምረጡ (Select Win Mode):**", reply_markup=InlineKeyboardMarkup(kb))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')

    if data[0] == "set":
        state["win_mode"] = data[1]
        state.update({"active": False, "paused": False, "numbers": [], "session_id": str(int(time.time())), "start_time": time.time() + 30})
        msg = (f"🔔 **አዲስ የቢንጎ ጨዋታ ሊጀመር ነው!**\n\n🏆 **የማሸነፊያ ህግ:** {state['win_mode']}\n🕒 **በ30 ሰከንድ ውስጥ ይጀመራል...**")
        await context.bot.send_message(GROUP_CHAT_ID, msg)
        context.job_queue.run_once(begin_calling, 30)
        await query.edit_message_text(f"✅ Started: {state['win_mode']}")

    elif data[0] == "pay":
        uid, name = int(data[2]), data[3]
        if uid not in state["approved_players"]: state["approved_players"].append(uid)
        url = f"{GAME_URL_BASE}?s={state['session_id']}"
        await context.bot.send_message(uid, f"✅ **ተፈቅዷል!**\nየጨዋታ ሊንክ:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 መጫወቻ ካርታ", web_app=WebAppInfo(url=url))]]))
        await query.edit_message_caption(caption=f"✅ Approved: @{name}")

    elif data[0] == "win":
        uid, name = data[1], data[2]
        state["active"] = False
        state["session_id"] = "EXPIRED"
        state["approved_players"] = []
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        kb = [[InlineKeyboardButton("አዎ (Yes)", callback_data="ask_pay")]]
        await context.bot.send_message(GROUP_CHAT_ID, f"🎊 **አሸናፊ: @{name}!**\nቀጣይ መጫወት ይፈልጋሉ?", reply_markup=InlineKeyboardMarkup(kb))

    elif data[0] == "ask_pay":
        await query.message.reply_text(f"🙏 እባክዎ 10 ብር ወደ {PAYMENT_ACC} ያስተላልፉና ፎቶ ይላኩ።")

async def begin_calling(context: ContextTypes.DEFAULT_TYPE):
    state["active"] = True
    context.job_queue.run_repeating(auto_caller, interval=12, first=1, name="bingo_job")

async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    if not state["active"] or state["paused"] or len(state["numbers"]) >= 75: return
    n = random.randint(1, 75)
    while any(str(n) == x.split('-')[1] for x in state["numbers"]): n = random.randint(1, 75)
    l = "B" if n<=15 else "I" if n<=30 else "N" if n<=45 else "G" if n<=60 else "O"
    state["numbers"].append(f"{l}-{n}")
    await context.bot.send_message(GROUP_CHAT_ID, f"🎯 **{l}-{n}**")

def main():
    init_db()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("play", start_game_menu))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot))
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    print("🤖 Bot is Online...")
    bot_app.run_polling()

if __name__ == "__main__":
    main()
