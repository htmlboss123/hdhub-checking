#!/usr/bin/env python3
import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from app.config import Config
from app.database import db
from app.utils import format_file_size, get_file_quality, extract_metadata

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MediaBot:
    def __init__(self):
        self.application = None
        self.bot_username = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Save user to database
        try:
            db.save_user({
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_admin': user.id in Config.ADMIN_IDS,
            })
        except Exception as e:
            logger.error(f"Failed to save user: {e}")
        
        welcome_msg = f"""
🎬 **Welcome to Media Bot!** 

I can help you manage and search media files from Telegram channels.

**Features:**
✅ Auto-index media files from channels
✅ Advanced search by name, quality, format
✅ Fast download with tracking
✅ Watch media online
✅ Admin dashboard

**Commands:**
/search [query] - Search for files
/quality [480p|720p|1080p|2160p] - Filter by quality
/recent - Show recent files
/stats - View bot statistics
/help - Show this message
"""
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode='Markdown'
        )
    
    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a search query.\nExample: /search Satluj 2026")
            return
        
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
        
        try:
            results = db.search_files(query)
            
            if not results:
                await update.message.reply_text("❌ No results found.")
                return
            
            for file in results[:5]:
                await self._send_file_card(update, file)
            
            if len(results) > 5:
                await update.message.reply_text(
                    f"📊 Showing first 5 results. Found {len(results)} total."
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
            await update.message.reply_text("❌ Error searching files. Please try again.")
    
    async def _send_file_card(self, update: Update, file_data: Dict):
        """Send a file information card"""
        try:
            file_id = file_data['file_id']
            file_name = file_data.get('file_name', 'Unknown')
            file_size = file_data.get('file_size', 0)
            quality = file_data.get('quality', 'Unknown')
            
            caption = f"""
📁 **{file_name}**
📊 Size: {format_file_size(file_size)}
🎯 Quality: {quality}
📆 Added: {file_data.get('created_at', datetime.now()).strftime('%Y-%m-%d')}

📥 /download {file_id[:10]}...
▶️ /watch {file_id[:10]}...
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("⬇️ Download", callback_data=f"download_{file_id}"),
                    InlineKeyboardButton("▶️ Watch", callback_data=f"watch_{file_id}")
                ]
            ]
            
            try:
                await update.message.reply_document(
                    document=file_id,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Failed to send file card: {e}")
                # Send as text if file can't be sent
                await update.message.reply_text(
                    f"📁 {file_name}\nSize: {format_file_size(file_size)}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.error(f"Error in _send_file_card: {e}")
    
    async def recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent files"""
        try:
            files = list(db.files.find({'is_active': True}).sort('created_at', -1).limit(10))
            
            if not files:
                await update.message.reply_text("❌ No files found.")
                return
            
            await update.message.reply_text("📋 *Recent Files:*", parse_mode='Markdown')
            for file in files[:5]:
                await self._send_file_card(update, file)
        except Exception as e:
            logger.error(f"Recent error: {e}")
            await update.message.reply_text("❌ Error loading recent files.")
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        try:
            stats = db.get_stats()
            
            stats_msg = f"""
📊 *Bot Statistics*

📁 Total Files: {stats.get('total_files', 0)}
👥 Total Users: {stats.get('total_users', 0)}
⬇️ Total Downloads: {stats.get('total_downloads', 0)}
👁️ Total Views: {stats.get('total_views', 0)}
"""
            await update.message.reply_text(stats_msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text("❌ Error loading statistics.")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        try:
            if query.data.startswith('download_'):
                file_id = query.data.replace('download_', '')
                await query.message.reply_text(
                    f"⬇️ Download link generated!\n"
                    f"Use: /download {file_id[:10]}"
                )
            elif query.data.startswith('watch_'):
                file_id = query.data.replace('watch_', '')
                await query.message.reply_text(
                    f"▶️ Watch link generated!\n"
                    f"Use: /watch {file_id[:10]}"
                )
        except Exception as e:
            logger.error(f"Button callback error: {e}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ An error occurred. Please try again later."
            )

async def main():
    """Main bot function"""
    try:
        # Initialize bot
        bot = MediaBot()
        
        # Create application
        application = Application.builder().token(Config.BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("search", bot.search))
        application.add_handler(CommandHandler("recent", bot.recent))
        application.add_handler(CommandHandler("stats", bot.stats))
        application.add_handler(CommandHandler("help", bot.start))
        application.add_handler(CallbackQueryHandler(bot.button_callback))
        application.add_error_handler(bot.error_handler)
        
        # Start bot
        logger.info("🤖 Bot started successfully!")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Bot failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
