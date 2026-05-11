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

# --- GLOBAL GAME STATE ---
state = {
    "active": False,
    "paused": False,
    "numbers": [],
    "win_mode": "Full House",
    "session_id": str(int(time.time())),
    "start_time": 0,
    "approved_players": [] # List of IDs who paid for THIS round
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
    
    # Check if this user was approved for this specific session
    if uid not in state["approved_players"]:
        return jsonify({"status": "rejected", "message": "You are not an approved player for this round!"}), 403

    # (Previous Anti-cheat logic remains here...)
    return jsonify({"status": "success"})

# --- BOT HANDLERS ---

async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Rule: Do not receive screenshots after the game starts
    if state["active"]:
        await update.message.reply_text("🚫 **ጨዋታው ተጀምሯል።**\n\nአሁን ክፍያ አንቀበልም። እባክዎ አሸናፊ ተለይቶ ቀጣይ ጨዋታ ሲጀመር ይላኩ።\n(Game in progress. Send after this round ends.)")
        return

    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"pay|app|{user.id}|{user.username or 'Player'}")]]
    
    await context.bot.send_photo(ADMIN_ID, photo_id, caption=f"💰 New Payment: @{user.username}", reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("✅ ደረሰኙ ተልኳል። አድሚኑ እስኪያረጋግጥ ድረስ በትዕግስት ይጠብቁ።")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|')

    if data[0] == "pay":
        uid, name = int(data[2]), data[3]
        if uid not in state["approved_players"]:
            state["approved_players"].append(uid) # Register ID
        
        url = f"{GAME_URL_BASE}?s={state['session_id']}"
        await context.bot.send_message(uid, f"✅ **ክፍያዎ ተረጋግጧል!**\nመለያ ቁጥርዎ: `{uid}`\nካርታዎን እዚህ ይክፈቱ:", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 መጫወቻ ካርታ", web_app=WebAppInfo(url=url))]]))
        await query.edit_message_caption(caption=f"✅ Approved & Registered: @{name}")

    elif data[0] == "win":
        state["active"] = False
        state["session_id"] = "EXPIRED" # Kill the web app access
        state["approved_players"] = [] # Clear the list for next round
        
        # Next game invitation
        kb = [[InlineKeyboardButton("አዎ (Yes)", callback_data="ask_pay")]]
        await context.bot.send_message(GROUP_CHAT_ID, f"🎊 **አሸናፊ ተገኝቷል!**\n\nቀጣይ ጨዋታ መጫወት ይፈልጋሉ?", reply_markup=InlineKeyboardMarkup(kb))

    elif data[0] == "ask_pay":
        await query.message.reply_text(f"🙏 እባክዎ 10 ብር ወደ {PAYMENT_ACC} ያስተላልፉ እና ደረሰኙን በፎቶ ይላኩ።")

# (Include start_game_menu, begin_calling, auto_caller from previous version)

def main():
    global bot_app
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("play", start_game_menu))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot))
    bot_app.add_handler(CallbackQueryHandler(admin_callback))
    # ... other handlers ...
    bot_app.run_polling()

if __name__ == "__main__": main()
