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
    "win_mode": "Full House", # Default
    "session_id": str(int(time.time())),
    "start_time": 0
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
    uid, name, marked = data.get("user_id"), data.get("user"), data.get("numbers", [])
    called_raw = [n.split('-')[1] for n in state["numbers"]]
    fake_nums = [n for n in marked if n not in called_raw and n != "FREE"]
    
    if fake_nums:
        bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(chat_id=ADMIN_ID, text=f"🚫 **FAKE CLAIM**: @{name}"), 0)
        return jsonify({"status": "rejected", "message": "Anti-cheat triggered!"}), 403

    kb = [[InlineKeyboardButton("🏆 CONFIRM WIN", callback_data=f"win|{uid}|{name}")]]
    bot_app.job_queue.run_once(lambda ctx: ctx.bot.send_message(
        chat_id=ADMIN_ID, text=f"🏆 **VALID {state['win_mode']} CLAIM**\nPlayer: @{name}", reply_markup=InlineKeyboardMarkup(kb)
    ), 0)
    return jsonify({"status": "success"})

# --- ADMIN COMMANDS ---

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
        
        msg = (f"🔔 **አዲስ የቢንጎ ጨዋታ ሊጀመር ነው!**\n\n"
               f"🏆 **የማሸነፊያ ህግ:** {state['win_mode']}\n"
               f"🕒 **የመጀመሪያ ቁጥር በ30 ሰከንድ ውስጥ ይወጣል...**\n\n"
               f"📜 **ህግ:** {state['win_mode']} የሞላ ቀድሞ 'BINGO' ይላል።")
        await context.bot.send_message(GROUP_CHAT_ID, msg)
        context.job_queue.run_once(begin_calling, 30)
        await query.edit_message_text(f"✅ Game started with mode: {state['win_mode']}")

    elif data[0] == "pay":
        action, uid, name = data[1], int(data[2]), data[3]
        if action == "app":
            url = f"{GAME_URL_BASE}?s={state['session_id']}"
            await context.bot.send_message(uid, f"✅ **ክፍያዎ ተረጋግጧል!**\nለመጫወት ከታች ያለውን ይጫኑ:", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 መጫወቻ ካርታ", web_app=WebAppInfo(url=url))]]))
            await query.edit_message_caption(caption=f"✅ Approved: @{name}")

    elif data[0] == "win":
        uid, name = data[1], data[2]
        state["active"] = False
        for job in context.job_queue.get_jobs_by_name("bingo_job"): job.schedule_removal()
        
        # Reset Logic & Next Game Invitation
        kb = [[InlineKeyboardButton("አዎ (Yes)", callback_data="next_yes"), InlineKeyboardButton("አይ (No)", callback_data="next_no")]]
        await context.bot.send_message(GROUP_CHAT_ID, f"🎊 **አሸናፊ: @{name}!** 💰\n\nቀጣይ ጨዋታ መጫወት ይፈልጋሉ?", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_text(f"✅ Winner confirmed: @{name}")

    elif data == ["next_yes"]:
        await query.message.reply_text(f"🙏 እባክዎ 10 ብር ወደ {PAYMENT_ACC} ያስተላልፉ እና ደረሰኙን ለቦቱ በፎቶ ይላኩ።")

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
    global bot_app
    init_db()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("play", start_game_menu))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot)) # (Same as previous handle_payment_screenshot)
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    bot_app.run_polling()

# (Include start_command and handle_payment_screenshot from the previous version here)
if __name__ == "__main__": main()
