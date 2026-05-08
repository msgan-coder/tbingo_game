import logging
import sqlite3
import os
import random
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment variables")

ADMIN_ID = 5431140655
GROUP_CHAT_ID = -1003949842028
ENTRY_FEE = 10
COMMISSION = 0.30

game_active = False
called_numbers = []

logging.basicConfig(level=logging.INFO)


def init_db():
    conn = sqlite3.connect("bingo.db")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS players 
           (user_id INTEGER PRIMARY KEY, username TEXT, status TEXT)"""
    )
    conn.commit()
    conn.close()


def get_bingo_board():
    b = [n for n in sorted(called_numbers) if 1 <= n <= 15]
    i = [n for n in sorted(called_numbers) if 16 <= n <= 30]
    n = [n for n in sorted(called_numbers) if 31 <= n <= 45]
    g = [n for n in sorted(called_numbers) if 46 <= n <= 60]
    o = [n for n in sorted(called_numbers) if 61 <= n <= 75]
    return (
        f"✨ **B**: {', '.join(map(str, b))}\n"
        f"✨ **I**: {', '.join(map(str, i))}\n"
        f"✨ **N**: {', '.join(map(str, n))}\n"
        f"✨ **G**: {', '.join(map(str, g))}\n"
        f"✨ **O**: {', '.join(map(str, o))}"
    )


async def auto_caller(context: ContextTypes.DEFAULT_TYPE):
    global called_numbers, game_active
    if not game_active or len(called_numbers) >= 75:
        return
    num = random.randint(1, 75)
    while num in called_numbers:
        num = random.randint(1, 75)
    called_numbers.append(num)
    letter = (
        "B" if num <= 15 else
        "I" if num <= 30 else
        "N" if num <= 45 else
        "G" if num <= 60 else "O"
    )
    text = f"🔔 **NEW NUMBER: {letter}-{num}**\n\n{get_bingo_board()}"
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode="Markdown")


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_active
    if update.effective_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("bingo.db")
    count = conn.execute("SELECT COUNT(*) FROM players WHERE status='PAID'").fetchone()[0]
    conn.close()

    if count == 0:
        await update.message.reply_text("❌ No players have paid yet!")
        return

    game_active = True
    pot = count * ENTRY_FEE
    rules = (
        f"🚀 **GAME STARTED!**\n\n"
        f"💰 **JACKPOT: {pot * 0.70} ETB**\n"
        f"🏆 1 Line: {pot * 0.10} ETB\n"
        f"🏆 2 Lines: {pot * 0.20} ETB\n"
        f"🏆 Full House: {pot * 0.40} ETB\n\n"
        f"🚫 Chat Locked! Watch for numbers."
    )
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=rules, parse_mode="Markdown")

    # Schedule auto caller every 5 seconds
    context.job_queue.run_repeating(auto_caller, interval=5, first=5)


async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")

    if data[0] == "win":
        global game_active, called_numbers
        username = data[2]

        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=(
                f"🎊 **WINNER: @{username}**\n\n"
                f"⚠️ **ROUND OVER.** All previous payments have expired. "
                f"Please send a new 10 ETB transfer for the next game!"
            ),
            parse_mode="Markdown",
        )

        # RESET
        game_active = False
        called_numbers = []
        conn = sqlite3.connect("bingo.db")
        conn.execute("DELETE FROM players")
        conn.commit()
        conn.close()
        await query.edit_message_reply_markup(reply_markup=None)


def main():
    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("startgame", start_game))
    application.add_handler(CallbackQueryHandler(admin_button))

    # --- Webhook mode for Render free Web Service ---
    PORT = int(os.getenv("PORT", "8080"))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    )


if __name__ == "__main__":
    main()
