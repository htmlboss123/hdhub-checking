#!/usr/bin/env python3
import os
import sys
import logging
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import Config
from app.database import db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is running!\n\nUse /help for commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 Commands:\n/start - Start\n/help - Help\n/stats - Stats")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    await update.message.reply_text(f"📊 Stats:\nFiles: {stats['total_files']}\nUsers: {stats['total_users']}")

async def main():
    """Main bot function"""
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Bot cannot start.")
        return
    
    try:
        application = Application.builder().token(Config.BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats))
        
        logger.info("🤖 Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Keep running
        while True:
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
