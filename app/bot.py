#!/usr/bin/env python3
"""
Complete Telegram Bot with All Commands
"""

import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

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

from app.config import Config, logger
from app.database import db
from app.utils import format_file_size, get_file_quality, extract_metadata

class TelegramBot:
    def __init__(self):
        self.application = None
        self.bot_username = None
        self.scanning = False
    
    # ---- USER COMMANDS ----
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        try:
            db.save_user({
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_admin': user.id in Config.ADMIN_IDS,
            })
        except Exception as e:
            logger.error(f"Save user error: {e}")
            await self._send_error_log(context, user.id, f"User save failed: {e}")
        
        welcome_msg = f"""
🎬 **Welcome to Media Bot!** 

Hi {user.first_name}! I can help you find and download media files.

**📚 User Commands:**
/search <query> - Search for files
/quality <480p|720p|1080p|2160p> - Filter by quality
/recent - Show recent files
/file <file_id> - Get file info
/download <file_id> - Get download link
/watch <file_id> - Get watch link
/stats - View bot statistics
/help - Show this message

**🔧 Admin Commands:**
/addchannel - Add channel for monitoring
/removechannel - Remove channel
/channels - List all channels
/scan - Scan channels
/users - View users
/broadcast - Send message to all users
/backup - Create backup
/cleanup - Cleanup files
/stats_full - Full admin dashboard

**👨‍💻 Developer:**
/errors - View recent errors
/logs - View bot logs
/status - Bot status
"""
        
        keyboard = [
            [
                InlineKeyboardButton("🔍 Search", callback_data="help_search"),
                InlineKeyboardButton("📥 Download", callback_data="help_download")
            ],
            [
                InlineKeyboardButton("▶️ Watch", callback_data="help_watch"),
                InlineKeyboardButton("📊 Stats", callback_data="help_stats")
            ]
        ]
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.start(update, context)
    
    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a search query.\n\n"
                "Example: `/search Satluj 2026`\n"
                "Example: `/search movie name`",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args)
        status_msg = await update.message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
        
        try:
            results = db.search_files(query)
            
            if not results:
                await status_msg.edit_text("❌ No results found.")
                return
            
            await status_msg.edit_text(f"✅ Found {len(results)} results:")
            
            for file in results[:10]:
                await self._send_file_card(update, file, context)
            
            if len(results) > 10:
                await update.message.reply_text(
                    f"📊 Showing 10 of {len(results)} results.\n"
                    f"Use `/search {query}` with more specific query."
                )
            
            # Log search
            db.log_action('search', {
                'user_id': update.effective_user.id,
                'query': query,
                'results': len(results)
            })
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text("❌ Error searching files. Please try again.")
            await self._send_error_log(context, update.effective_user.id, f"Search error: {e}")
    
    async def quality_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            qualities = ['2160p', '1080p', '720p', '480p']
            keyboard = [
                [InlineKeyboardButton(q, callback_data=f'quality_{q}') for q in qualities]
            ]
            await update.message.reply_text(
                "📺 Select quality:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        quality = context.args[0].lower()
        valid_qualities = ['480p', '720p', '1080p', '2160p', '4k', 'hd', 'fullhd']
        
        if quality not in valid_qualities:
            await update.message.reply_text(
                f"❌ Invalid quality. Choose from: {', '.join(valid_qualities)}"
            )
            return
        
        try:
            files = db.get_files_by_quality(quality, 20)
            
            if not files:
                await update.message.reply_text(f"❌ No {quality} files found.")
                return
            
            await update.message.reply_text(f"✅ Found {len(files)} {quality} files:")
            
            for file in files[:5]:
                await self._send_file_card(update, file, context)
            
            if len(files) > 5:
                await update.message.reply_text(f"📊 Showing 5 of {len(files)} {quality} files.")
                
        except Exception as e:
            logger.error(f"Quality filter error: {e}")
            await update.message.reply_text("❌ Error filtering files.")
            await self._send_error_log(context, update.effective_user.id, f"Quality error: {e}")
    
    async def recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            files = db.search_files('', 15, 0)
            
            if not files:
                await update.message.reply_text("❌ No files found.")
                return
            
            await update.message.reply_text("📋 *Recent Files:*", parse_mode='Markdown')
            
            for file in files[:10]:
                await self._send_file_card(update, file, context)
                
        except Exception as e:
            logger.error(f"Recent error: {e}")
            await update.message.reply_text("❌ Error loading recent files.")
            await self._send_error_log(context, update.effective_user.id, f"Recent error: {e}")
    
    async def file_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a file ID.\n\n"
                "Example: `/file ABC123...`",
                parse_mode='Markdown'
            )
            return
        
        file_id = context.args[0]
        
        try:
            file = db.get_file_by_id(file_id)
            
            if not file:
                await update.message.reply_text("❌ File not found.")
                return
            
            info = f"""
📋 **File Details**

📁 **Name:** {file.get('file_name', 'Unknown')}
📊 **Size:** {format_file_size(file.get('file_size', 0))}
🎯 **Quality:** {file.get('quality', 'Unknown')}
📂 **Format:** {file.get('file_format', 'Unknown')}
🆔 **File ID:** `{file['file_id'][:20]}...`

📢 **Channel:** {file.get('channel_title', 'Unknown')}
📅 **Added:** {file.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M')}

📊 **Downloads:** {file.get('download_count', 0)}
👁️ **Views:** {file.get('watch_count', 0)}

🏷️ **Tags:** {', '.join(file.get('tags', [])) if file.get('tags') else 'None'}

📥 /download {file['file_id'][:10]}...
▶️ /watch {file['file_id'][:10]}...
"""
            keyboard = [
                [
                    InlineKeyboardButton("⬇️ Download", callback_data=f"download_{file['file_id']}"),
                    InlineKeyboardButton("▶️ Watch", callback_data=f"watch_{file['file_id']}")
                ]
            ]
            
            await update.message.reply_text(
                info,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"File info error: {e}")
            await update.message.reply_text("❌ Error getting file info.")
            await self._send_error_log(context, update.effective_user.id, f"File info error: {e}")
    
    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a file ID.\n\n"
                "Example: `/download ABC123...`",
                parse_mode='Markdown'
            )
            return
        
        file_id = context.args[0]
        
        try:
            file = db.get_file_by_id(file_id)
            if not file:
                await update.message.reply_text("❌ File not found.")
                return
            
            token = db.create_download_request(
                file_id, 
                update.effective_user.id,
                update.effective_user.username
            )
            
            if not token:
                await update.message.reply_text("❌ Failed to create download link.")
                return
            
            db.update_file_stats(file_id, 'download')
            
            download_url = f"{Config.BASE_URL}/api/v1/download/{token}"
            
            await update.message.reply_text(
                f"⬇️ *Download Link Generated*\n\n"
                f"📁 {file.get('file_name', 'Unknown')}\n"
                f"📊 Size: {format_file_size(file.get('file_size', 0))}\n"
                f"🎯 Quality: {file.get('quality', 'Unknown')}\n\n"
                f"🔗 [Click here to download]({download_url})\n\n"
                f"⏰ Link expires in 24 hours\n"
                f"🔒 Secure download",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await update.message.reply_text("❌ Error generating download link.")
            await self._send_error_log(context, update.effective_user.id, f"Download error: {e}")
    
    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a file ID.\n\n"
                "Example: `/watch ABC123...`",
                parse_mode='Markdown'
            )
            return
        
        file_id = context.args[0]
        
        try:
            file = db.get_file_by_id(file_id)
            if not file:
                await update.message.reply_text("❌ File not found.")
                return
            
            if not any(file.get('file_name', '').lower().endswith(ext) for ext in Config.VIDEO_FORMATS):
                await update.message.reply_text("❌ This file is not a video and cannot be streamed.")
                return
            
            token = db.create_download_request(
                file_id, 
                update.effective_user.id,
                update.effective_user.username
            )
            
            if not token:
                await update.message.reply_text("❌ Failed to create watch link.")
                return
            
            db.update_file_stats(file_id, 'watch')
            
            watch_url = f"{Config.BASE_URL}/api/v1/watch/{token}"
            
            await update.message.reply_text(
                f"▶️ *Watch Link Generated*\n\n"
                f"📺 {file.get('file_name', 'Unknown')}\n"
                f"📊 Size: {format_file_size(file.get('file_size', 0))}\n"
                f"🎯 Quality: {file.get('quality', 'Unknown')}\n\n"
                f"🔗 [Click here to watch]({watch_url})\n\n"
                f"⏰ Link expires in 24 hours",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Watch error: {e}")
            await update.message.reply_text("❌ Error generating watch link.")
            await self._send_error_log(context, update.effective_user.id, f"Watch error: {e}")
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            stats = db.get_stats()
            
            stats_msg = f"""
📊 *Bot Statistics*

📁 **Files:** {stats.get('total_files', 0)}
👥 **Users:** {stats.get('total_users', 0)}
⬇️ **Downloads:** {stats.get('total_downloads', 0)}
👁️ **Views:** {stats.get('total_views', 0)}
📢 **Channels:** {stats.get('total_channels', 0)}

🏷️ **File Types:**
"""
            for ft in stats.get('file_types', []):
                stats_msg += f"  • {ft['_id']}: {ft['count']}\n"
            
            stats_msg += "\n🎯 **Quality Distribution:**\n"
            for q in stats.get('quality_distribution', []):
                stats_msg += f"  • {q['_id']}: {q['count']}\n"
            
            await update.message.reply_text(stats_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text("❌ Error loading statistics.")
            await self._send_error_log(context, update.effective_user.id, f"Stats error: {e}")
    
    # ---- ADMIN COMMANDS ----
    
    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a channel to monitor"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 **Add Channel**\n\n"
                "Usage: `/addchannel <channel_link_or_id>`\n\n"
                "Examples:\n"
                "• `/addchannel https://t.me/yourchannel`\n"
                "• `/addchannel -1001234567890`\n"
                "• `/addchannel @yourchannel`\n\n"
                "⚠️ Make sure the bot is an admin of the channel!",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[0]
        status_msg = await update.message.reply_text("🔍 Checking channel...")
        
        try:
            # Parse channel input
            if channel_input.startswith('https://t.me/'):
                username = channel_input.split('/')[-1]
                chat = await context.bot.get_chat(f'@{username}')
            elif channel_input.startswith('@'):
                chat = await context.bot.get_chat(channel_input)
            else:
                chat = await context.bot.get_chat(int(channel_input))
            
            # Check if already exists
            existing = db.settings.find_one({
                'type': 'channel',
                'channel_id': chat.id
            })
            
            if existing:
                await status_msg.edit_text(
                    f"⚠️ Channel already exists!\n\n"
                    f"📢 {chat.title}\n"
                    f"🆔 {chat.id}"
                )
                return
            
            # Save channel
            channel_data = {
                'type': 'channel',
                'channel_id': chat.id,
                'channel_username': chat.username,
                'channel_title': chat.title,
                'channel_link': f"https://t.me/{chat.username}" if chat.username else None,
                'added_by': update.effective_user.id,
                'added_at': datetime.utcnow(),
                'is_active': True,
                'last_scanned': None,
                'total_files': 0
            }
            
            db.settings.insert_one(channel_data)
            
            await status_msg.edit_text(
                f"✅ **Channel Added!**\n\n"
                f"📢 {chat.title}\n"
                f"🆔 {chat.id}\n\n"
                f"🔄 Starting scan..."
            )
            
            # Scan the channel
            files_found = await self._scan_single_channel(context, chat.id, status_msg)
            
            db.settings.update_one(
                {'channel_id': chat.id},
                {'$set': {'total_files': files_found, 'last_scanned': datetime.utcnow()}}
            )
            
            await status_msg.edit_text(
                f"✅ **Channel Added & Scanned!**\n\n"
                f"📢 {chat.title}\n"
                f"📁 Found: {files_found} files\n"
                f"🆔 {chat.id}"
            )
            
            db.log_action('add_channel', {
                'channel_id': chat.id,
                'channel_title': chat.title,
                'added_by': update.effective_user.id
            })
            
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
            await self._send_error_log(context, update.effective_user.id, f"Add channel error: {e}")
    
    async def scan_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually scan all channels"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        if self.scanning:
            await update.message.reply_text("⏳ Scan already in progress...")
            return
        
        status_msg = await update.message.reply_text("🔍 Starting full scan...")
        self.scanning = True
        
        try:
            channels = list(db.settings.find({'type': 'channel', 'is_active': True}))
            
            if not channels:
                await status_msg.edit_text("📢 No channels to scan.")
                self.scanning = False
                return
            
            total_files = 0
            
            for idx, channel in enumerate(channels, 1):
                await status_msg.edit_text(
                    f"🔍 Scanning: {channel.get('channel_title', 'Unknown')}\n"
                    f"📊 Progress: {idx}/{len(channels)}\n"
                    f"📁 Found: {total_files} files"
                )
                
                try:
                    files_found = await self._scan_single_channel(context, channel['channel_id'], status_msg)
                    total_files += files_found
                    
                    db.settings.update_one(
                        {'channel_id': channel['channel_id']},
                        {'$set': {'total_files': files_found, 'last_scanned': datetime.utcnow()}}
                    )
                except Exception as e:
                    logger.error(f"Scan error for channel {channel['channel_id']}: {e}")
            
            await status_msg.edit_text(
                f"✅ Scan Complete!\n\n"
                f"📊 Scanned: {len(channels)} channels\n"
                f"📁 Found: {total_files} files"
            )
            
            db.log_action('manual_scan', {
                'channels': len(channels),
                'files': total_files
            })
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await status_msg.edit_text(f"❌ Scan error: {str(e)}")
            await self._send_error_log(context, update.effective_user.id, f"Scan error: {e}")
        
        finally:
            self.scanning = False
    
    # ---- HELPER METHODS ----
    
    async def _scan_single_channel(self, context: ContextTypes.DEFAULT_TYPE, channel_id: int, status_msg=None):
        """Scan a single channel for media files"""
        files_found = 0
        offset = 0
        
        try:
            while offset < 5000:
                messages = await context.bot.get_chat_history(
                    chat_id=channel_id,
                    limit=100,
                    offset=offset
                )
                
                if not messages:
                    break
                
                for msg in messages:
                    # Process videos
                    if msg.video:
                        file_data = {
                            'file_id': msg.video.file_id,
                            'file_unique_id': msg.video.file_unique_id,
                            'file_name': msg.caption or f"video_{msg.video.file_id}.mp4",
                            'file_size': msg.video.file_size,
                            'file_format': '.mp4',
                            'mime_type': 'video/mp4',
                            'quality': get_file_quality(msg.video.width, msg.video.height),
                            'resolution': f"{msg.video.width}x{msg.video.height}",
                            'duration': msg.video.duration,
                            'channel_id': channel_id,
                            'channel_title': msg.chat.title,
                            'message_id': msg.message_id,
                            'caption': msg.caption,
                            'thumbnail_id': msg.video.thumbnail.file_id if msg.video.thumbnail else None,
                            'tags': extract_metadata(msg.caption or ''),
                            'is_active': True,
                            'download_count': 0,
                            'watch_count': 0
                        }
                        if db.save_file(file_data):
                            files_found += 1
                    
                    # Process documents
                    elif msg.document:
                        file_name = msg.document.file_name or 'document'
                        file_ext = os.path.splitext(file_name)[1].lower()
                        
                        if file_ext in Config.VIDEO_FORMATS or file_ext in Config.SUBTITLE_FORMATS:
                            file_data = {
                                'file_id': msg.document.file_id,
                                'file_unique_id': msg.document.file_unique_id,
                                'file_name': file_name,
                                'file_size': msg.document.file_size,
                                'file_format': file_ext,
                                'mime_type': msg.document.mime_type,
                                'channel_id': channel_id,
                                'channel_title': msg.chat.title,
                                'message_id': msg.message_id,
                                'caption': msg.caption,
                                'quality': get_file_quality(msg.document.mime_type or ''),
                                'tags': extract_metadata(msg.caption or ''),
                                'is_active': True,
                                'download_count': 0,
                                'watch_count': 0
                            }
                            if db.save_file(file_data):
                                files_found += 1
                
                offset += 100
                await asyncio.sleep(0.1)
                
                if offset > 5000:
                    break
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            raise
        
        return files_found
    
    async def _send_file_card(self, update: Update, file_data: Dict, context: ContextTypes.DEFAULT_TYPE):
        """Send file information card"""
        try:
            file_id = file_data['file_id']
            file_name = file_data.get('file_name', 'Unknown')
            file_size = file_data.get('file_size', 0)
            quality = file_data.get('quality', 'Unknown')
            
            caption = f"""
📁 **{file_name}**
📊 Size: {format_file_size(file_size)}
🎯 Quality: {quality}
📆 Added: {file_data.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d')}

📥 /download {file_id[:10]}...
▶️ /watch {file_id[:10]}...
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("⬇️ Download", callback_data=f"download_{file_id}"),
                    InlineKeyboardButton("▶️ Watch", callback_data=f"watch_{file_id}")
                ],
                [
                    InlineKeyboardButton("ℹ️ Info", callback_data=f"info_{file_id}")
                ]
            ]
            
            try:
                await update.message.reply_document(
                    document=file_id,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await update.message.reply_text(
                    caption,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error(f"Send file card error: {e}")
    
    async def _send_error_log(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, error: str):
        """Send error to admin"""
        try:
            for admin_id in Config.ADMIN_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"⚠️ **Error Report**\n\n"
                    f"User: {user_id}\n"
                    f"Error: {error}\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Failed to send error log: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in Config.ADMIN_IDS

# ---- MAIN ----

async def main():
    """Main bot function"""
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    
    bot = TelegramBot()
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("search", bot.search))
    application.add_handler(CommandHandler("quality", bot.quality_filter))
    application.add_handler(CommandHandler("recent", bot.recent))
    application.add_handler(CommandHandler("file", bot.file_info))
    application.add_handler(CommandHandler("download", bot.download))
    application.add_handler(CommandHandler("watch", bot.watch))
    application.add_handler(CommandHandler("stats", bot.stats))
    
    # Admin commands
    application.add_handler(CommandHandler("addchannel", bot.add_channel))
    application.add_handler(CommandHandler("scan", bot.scan_channels))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(bot._handle_callback))
    
    logger.info("🤖 Bot started!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    while True:
        await asyncio.sleep(60)

async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('download_'):
        file_id = data.replace('download_', '')
        context.args = [file_id]
        await self.download(update, context)
    elif data.startswith('watch_'):
        file_id = data.replace('watch_', '')
        context.args = [file_id]
        await self.watch(update, context)
    elif data.startswith('info_'):
        file_id = data.replace('info_', '')
        context.args = [file_id]
        await self.file_info(update, context)
    elif data.startswith('quality_'):
        quality = data.replace('quality_', '')
        context.args = [quality]
        await self.quality_filter(update, context)
    elif data == 'help_search':
        await query.message.reply_text(
            "🔍 **Search Command**\n\n"
            "Usage: `/search <query>`\n\n"
            "Examples:\n"
            "• `/search Satluj`\n"
            "• `/search movie 2024`\n"
            "• `/search 2160p`",
            parse_mode='Markdown'
        )
    elif data == 'help_download':
        await query.message.reply_text(
            "📥 **Download Command**\n\n"
            "Usage: `/download <file_id>`\n\n"
            "First find a file using `/search`, then use its ID to download.",
            parse_mode='Markdown'
        )
    elif data == 'help_watch':
        await query.message.reply_text(
            "▶️ **Watch Command**\n\n"
            "Usage: `/watch <file_id>`\n\n"
            "Works for video files only. Get the file ID from search results.",
            parse_mode='Markdown'
        )
    elif data == 'help_stats':
        await query.message.reply_text(
            "📊 **Statistics**\n\n"
            "Shows bot usage statistics including:\n"
            "• Total files\n"
            "• Total users\n"
            "• Downloads and views\n"
            "• File types distribution",
            parse_mode='Markdown'
        )

if __name__ == "__main__":
    asyncio.run(main())
