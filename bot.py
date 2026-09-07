#!/usr/bin/env python3
"""
Advanced Telegram Media Bot with MongoDB Integration
Features:
- Auto-scan channels for media files
- Store metadata in MongoDB
- Admin controls
- User management
- Download tracking
- Advanced search
- Quality filtering
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from config import Config
from database import db
from utils import (
    get_file_quality,
    get_file_resolution,
    format_file_size,
    extract_metadata,
    sanitize_filename,
    generate_thumbnail,
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MediaBot:
    def __init__(self):
        self.application = None
        self.scanning = False
        self.bot_username = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Save user to database
        db.save_user({
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_admin': user.id in Config.ADMIN_IDS,
        })
        
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

**Admin Commands:**
/scan - Manually scan channels
/addchannel - Add channel to scan
/removechannel - Remove channel from scanning
/users - View users list
/broadcast - Send message to all users
/backup - Backup database
"""
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode='Markdown'
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 **Help & Commands**

**User Commands:**
/search <query> - Search for movies/shows
  Example: /search Satluj 2026
  
/quality <quality> - Filter by video quality
  Example: /quality 2160p
  
/recent - Show latest uploaded files
  
/file <file_id> - Get info about specific file
  
/stats - View bot statistics
  
/download <file_id> - Get download link
  
/watch <file_id> - Get streaming link

**Admin Commands:**
/scan - Scan all channels for new media
/addchannel <link> - Add channel to monitor
/removechannel <id> - Remove channel from monitoring
/channels - List all monitored channels
/users - Show user statistics
/broadcast <message> - Send to all users
/stats_full - Full statistics
/backup - Create database backup
/restore - Restore from backup
/cleanup - Remove duplicate/inactive files

**Supported Formats:**
Video: MP4, MKV, AVI, MOV, WMV, FLV, WEBM
Audio: MP3, AAC, FLAC, WAV
Subtitles: SRT, ASS, VTT
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command with advanced filtering"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a search query.\nExample: /search Satluj 2026")
            return
        
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
        
        # Search in database
        results = db.search_files(query)
        
        if not results:
            await update.message.reply_text("❌ No results found.")
            return
        
        # Send results in batches
        for i in range(0, min(len(results), 10)):
            file = results[i]
            await self._send_file_card(update, file)
        
        if len(results) > 10:
            await update.message.reply_text(
                f"📊 Showing first 10 results. Found {len(results)} total."
            )
    
    async def quality_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Filter files by quality"""
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
        
        # Query files with this quality
        files = list(db.files.find({
            'quality': {'$regex': quality, '$options': 'i'},
            'is_active': True
        }).sort('created_at', -1).limit(20))
        
        if not files:
            await update.message.reply_text(f"❌ No {quality} files found.")
            return
        
        for file in files[:5]:
            await self._send_file_card(update, file)
        
        if len(files) > 5:
            await update.message.reply_text(f"📊 Showing 5 of {len(files)} {quality} files.")
    
    async def recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent files"""
        files = list(db.files.find({'is_active': True}).sort('created_at', -1).limit(20))
        
        if not files:
            await update.message.reply_text("❌ No files found.")
            return
        
        await update.message.reply_text("📋 *Recent Files:*", parse_mode='Markdown')
        for file in files[:10]:
            await self._send_file_card(update, file)
    
    async def file_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get detailed info about a file"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a file ID.\nExample: /file ABC123")
            return
        
        file_id = context.args[0]
        file = db.get_file_by_id(file_id)
        
        if not file:
            await update.message.reply_text("❌ File not found.")
            return
        
        await self._send_file_info(update, file)
    
    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate download link for file"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a file ID.\nExample: /download ABC123")
            return
        
        file_id = context.args[0]
        file = db.get_file_by_id(file_id)
        
        if not file:
            await update.message.reply_text("❌ File not found.")
            return
        
        # Create download request
        token = db.create_download_request(
            file_id, 
            update.effective_user.id,
            update.effective_user.username
        )
        
        # Update download count
        db.update_file_stats(file_id, 'download')
        
        # Generate download URL (replace with your actual domain)
        download_url = f"https://your-api-domain.com/download/{token}"
        
        await update.message.reply_text(
            f"⬇️ *Download Link Generated*\n\n"
            f"📁 {file['file_name']}\n"
            f"📊 Size: {format_file_size(file['file_size'])}\n\n"
            f"🔗 [Click here to download]({download_url})\n\n"
            f"⏰ Link expires in 24 hours\n"
            f"🔒 Protected by secure token",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate streaming link for file"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a file ID.\nExample: /watch ABC123")
            return
        
        file_id = context.args[0]
        file = db.get_file_by_id(file_id)
        
        if not file:
            await update.message.reply_text("❌ File not found.")
            return
        
        # Only allow video files for streaming
        if not any(file['file_name'].lower().endswith(ext) for ext in Config.VIDEO_FORMATS):
            await update.message.reply_text("❌ This file is not a video and cannot be streamed.")
            return
        
        # Create streaming token
        token = db.create_download_request(
            file_id, 
            update.effective_user.id,
            update.effective_user.username
        )
        
        # Update watch count
        db.update_file_stats(file_id, 'watch')
        
        # Generate watch URL
        watch_url = f"https://your-api-domain.com/watch/{token}"
        
        await update.message.reply_text(
            f"▶️ *Streaming Link Generated*\n\n"
            f"📺 {file['file_name']}\n"
            f"📊 Size: {format_file_size(file['file_size'])}\n"
            f"🎯 Quality: {file.get('quality', 'Unknown')}\n\n"
            f"🔗 [Click here to watch]({watch_url})\n\n"
            f"⏰ Link expires in 24 hours",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        stats = db.get_stats()
        
        # Check if user is admin
        is_admin = update.effective_user.id in Config.ADMIN_IDS
        
        stats_msg = f"""
📊 *Bot Statistics*

📁 Total Files: {stats['total_files']}
👥 Total Users: {stats['total_users']}
⬇️ Total Downloads: {stats['total_downloads']}
👁️ Total Views: {stats['total_views']}

📂 *File Types:*
"""
        for file_type in stats['file_types']:
            stats_msg += f"  • {file_type['_id']}: {file_type['count']}\n"
        
        stats_msg += "\n📺 *Quality Distribution:*\n"
        for quality in stats['quality_distribution']:
            stats_msg += f"  • {quality['_id']}: {quality['count']}\n"
        
        if is_admin:
            stats_msg += f"\n🔧 *Admin Info:*\n"
            stats_msg += f"  • Admins: {len(Config.ADMIN_IDS)}\n"
            stats_msg += f"  • Channels: {db.settings.count_documents({'type': 'channel'})}\n"
        
        await update.message.reply_text(stats_msg, parse_mode='Markdown')
    
    # ---- ADMIN COMMANDS ----
    
    async def scan_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually scan all channels for new media"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        
        if self.scanning:
            await update.message.reply_text("⏳ Scan is already in progress...")
            return
        
        await update.message.reply_text("🔍 Starting channel scan...")
        
        self.scanning = True
        try:
            # Get channels to scan
            channels = db.settings.find({'type': 'channel'})
            total_files = 0
            
            for channel in channels:
                try:
                    # Get channel entity
                    channel_id = channel['channel_id']
                    
                    # Scan channel messages
                    files_found = await self._scan_channel(update, context, channel_id)
                    total_files += files_found
                    
                    await update.message.reply_text(
                        f"✅ Scanned channel {channel_id}: Found {files_found} new files"
                    )
                except Exception as e:
                    logger.error(f"Error scanning channel {channel_id}: {e}")
                    await update.message.reply_text(f"❌ Error scanning channel {channel_id}")
            
            await update.message.reply_text(
                f"✅ Scan complete! Found {total_files} new files."
            )
            
            # Log action
            db.log_action('scan', {'total_files': total_files})
            
        finally:
            self.scanning = False
    
    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a channel to monitor"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide channel link or ID.\n"
                "Example: /addchannel https://t.me/yourchannel\n"
                "Or: /addchannel -1001234567890"
            )
            return
        
        channel_input = context.args[0]
        
        try:
            # Parse channel ID or username
            if channel_input.startswith('https://t.me/'):
                username = channel_input.split('/')[-1]
                chat = await context.bot.get_chat(f'@{username}')
            else:
                chat = await context.bot.get_chat(int(channel_input))
            
            # Save channel to database
            db.settings.update_one(
                {'type': 'channel', 'channel_id': chat.id},
                {
                    '$set': {
                        'channel_id': chat.id,
                        'channel_username': chat.username,
                        'channel_title': chat.title,
                        'added_by': update.effective_user.id,
                        'added_at': datetime.utcnow(),
                        'is_active': True
                    }
                },
                upsert=True
            )
            
            await update.message.reply_text(
                f"✅ Channel added successfully!\n"
                f"📢 {chat.title}\n"
                f"🆔 {chat.id}"
            )
            
            # Immediately scan this channel
            await update.message.reply_text("🔍 Scanning channel for existing media...")
            files_found = await self._scan_channel(update, context, chat.id)
            await update.message.reply_text(f"✅ Found {files_found} new files.")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")
            logger.error(f"Add channel error: {e}")
    
    async def remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a channel from monitoring"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide channel ID.\n"
                "Example: /removechannel -1001234567890"
            )
            return
        
        channel_id = int(context.args[0])
        
        result = db.settings.delete_one({
            'type': 'channel',
            'channel_id': channel_id
        })
        
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Channel {channel_id} removed successfully.")
        else:
            await update.message.reply_text(f"❌ Channel {channel_id} not found.")
    
    async def list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all monitored channels"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        channels = db.settings.find({'type': 'channel'})
        
        if not channels:
            await update.message.reply_text("No channels are being monitored.")
            return
        
        msg = "📢 *Monitored Channels:*\n\n"
        for channel in channels:
            msg += f"• {channel.get('channel_title', 'Unknown')}\n"
            msg += f"  ID: `{channel['channel_id']}`\n"
            msg += f"  Username: @{channel.get('channel_username', 'N/A')}\n"
            msg += f"  Added: {channel.get('added_at', 'Unknown')}\n\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        total_users = db.users.count_documents({})
        active_users = db.users.count_documents({
            'last_active': {'$gt': datetime.utcnow().timestamp() - 86400 * 7}  # Last 7 days
        })
        
        # Get top downloaders
        top_users = list(db.users.find().sort('download_count', -1).limit(10))
        
        msg = f"""
👥 *User Statistics*

Total Users: {total_users}
Active Users (7 days): {active_users}

🏆 *Top Downloaders:*
"""
        for i, user in enumerate(top_users, 1):
            username = user.get('username', 'Unknown')
            downloads = user.get('download_count', 0)
            msg += f"  {i}. @{username}: {downloads} downloads\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send broadcast message to all users"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a message to broadcast.\n"
                "Example: /broadcast Hello everyone!"
            )
            return
        
        message = ' '.join(context.args)
        
        # Get all users
        users = db.users.find({})
        total = 0
        failed = 0
        
        status_msg = await update.message.reply_text("📢 Sending broadcast...")
        
        for user in users:
            try:
                await context.bot.send_message(
                    user['user_id'],
                    f"📢 *Broadcast Message*\n\n{message}",
                    parse_mode='Markdown'
                )
                total += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception:
                failed += 1
        
        await status_msg.edit_text(
            f"✅ Broadcast completed!\n"
            f"📤 Sent: {total} users\n"
            f"❌ Failed: {failed} users"
        )
        
        db.log_action('broadcast', {
            'message': message,
            'sent': total,
            'failed': failed
        })
    
    # ---- HELPER METHODS ----
    
    async def _scan_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: int):
        """Scan a channel for media files"""
        files_found = 0
        offset = 0
        
        try:
            while True:
                # Get messages from channel
                messages = await context.bot.get_chat_history(
                    chat_id=channel_id,
                    limit=100,
                    offset=offset
                )
                
                if not messages:
                    break
                
                for msg in messages:
                    if msg.video:
                        # Process video
                        file_id = msg.video.file_id
                        file_name = f"{msg.caption or 'video'}.mp4" if not hasattr(msg.video, 'file_name') else msg.video.file_name
                        
                        file_data = {
                            'file_id': file_id,
                            'file_unique_id': msg.video.file_unique_id,
                            'file_name': file_name,
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
                        }
                        
                        if db.save_file(file_data):
                            files_found += 1
                    
                    elif msg.document:
                        # Check if document is video or subtitle
                        file_name = msg.document.file_name or 'document'
                        file_ext = file_name.split('.')[-1].lower()
                        
                        if file_ext in Config.VIDEO_FORMATS:
                            file_data = {
                                'file_id': msg.document.file_id,
                                'file_unique_id': msg.document.file_unique_id,
                                'file_name': file_name,
                                'file_size': msg.document.file_size,
                                'file_format': f'.{file_ext}',
                                'mime_type': msg.document.mime_type,
                                'channel_id': channel_id,
                                'channel_title': msg.chat.title,
                                'message_id': msg.message_id,
                                'caption': msg.caption,
                                'quality': get_file_quality_from_name(file_name),
                                'tags': extract_metadata(msg.caption or ''),
                            }
                            
                            if db.save_file(file_data):
                                files_found += 1
                
                offset += 100
                await asyncio.sleep(0.2)  # Rate limiting
                
                if offset > 5000:  # Limit scanning to last 5000 messages
                    break
                    
        except Exception as e:
            logger.error(f"Error scanning channel: {e}")
        
        return files_found
    
    async def _send_file_card(self, update: Update, file_data: Dict):
        """Send a file information card"""
        quality = file_data.get('quality', 'Unknown')
        size = format_file_size(file_data['file_size'])
        file_id = file_data['file_id']
        
        caption = f"""
📁 **{file_data['file_name']}**
📊 Size: {size}
🎯 Quality: {quality}
📂 Format: {file_data.get('file_format', 'Unknown')}
📆 Added: {file_data['created_at'].strftime('%Y-%m-%d')}

📥 /download {file_id}
▶️ /watch {file_id}
ℹ️ /file {file_id}
"""
        
        # Add tags if available
        if file_data.get('tags'):
            tags = ', '.join(file_data['tags'][:5])
            caption += f"\n🏷️ Tags: {tags}"
        
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
            # Try to send as video
            await update.message.reply_video(
                video=file_data['file_id'],
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # Fallback to document
            await update.message.reply_document(
                document=file_data['file_id'],
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def _send_file_info(self, update: Update, file_data: Dict):
        """Send detailed file information"""
        info = f"""
📋 **File Details**

📁 **Name:** {file_data['file_name']}
📊 **Size:** {format_file_size(file_data['file_size'])}
🎯 **Quality:** {file_data.get('quality', 'Unknown')}
📂 **Format:** {file_data.get('file_format', 'Unknown')}
🆔 **File ID:** `{file_data['file_id']}`

📢 **Channel:** {file_data.get('channel_title', 'Unknown')}
🆔 **Channel ID:** {file_data['channel_id']}
📝 **Message ID:** {file_data['message_id']}

📅 **Added:** {file_data['created_at'].strftime('%Y-%m-%d %H:%M:%S')}
🔄 **Updated:** {file_data['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}

📊 **Downloads:** {file_data.get('download_count', 0)}
👁️ **Views:** {file_data.get('watch_count', 0)}

📥 /download {file_data['file_id']}
▶️ /watch {file_data['file_id']}
"""
        
        if file_data.get('tags'):
            info += f"\n🏷️ **Tags:** {', '.join(file_data['tags'])}"
        
        if file_data.get('caption'):
            info += f"\n📝 **Caption:** {file_data['caption']}"
        
        await update.message.reply_text(info, parse_mode='Markdown')
    
    # ---- CALLBACK HANDLERS ----
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # ---- MESSAGE HANDLER ----
    
    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming media messages"""
        # Only process if user is admin
        if update.effective_user.id not in Config.ADMIN_IDS:
            return
        
        # Process media from forwarded messages or direct uploads
        # This helps admins manually add files
        
        message = update.message
        
        if message.video:
            file_data = {
                'file_id': message.video.file_id,
                'file_unique_id': message.video.file_unique_id,
                'file_name': message.caption or f"video_{message.video.file_id}.mp4",
                'file_size': message.video.file_size,
                'file_format': '.mp4',
                'mime_type': 'video/mp4',
                'quality': get_file_quality(message.video.width, message.video.height),
                'resolution': f"{message.video.width}x{message.video.height}",
                'duration': message.video.duration,
                'channel_id': message.chat_id,
                'channel_title': message.chat.title,
                'message_id': message.message_id,
                'caption': message.caption,
                'thumbnail_id': message.video.thumbnail.file_id if message.video.thumbnail else None,
                'tags': extract_metadata(message.caption or ''),
            }
            
            if db.save_file(file_data):
                await update.message.reply_text("✅ File saved to database!")
    
    # ---- RUN BOT ----
    
    def run(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(Config.BOT_TOKEN).build()
        
        # Get bot username
        asyncio.run(self._set_bot_username())
        
        # Register command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("search", self.search))
        self.application.add_handler(CommandHandler("quality", self.quality_filter))
        self.application.add_handler(CommandHandler("recent", self.recent))
        self.application.add_handler(CommandHandler("file", self.file_info))
        self.application.add_handler(CommandHandler("download", self.download))
        self.application.add_handler(CommandHandler("watch", self.watch))
        self.application.add_handler(CommandHandler("stats", self.stats))
        
        # Admin commands
        self.application.add_handler(CommandHandler("scan", self.scan_channels))
        self.application.add_handler(CommandHandler("addchannel", self.add_channel))
        self.application.add_handler(CommandHandler("removechannel", self.remove_channel))
        self.application.add_handler(CommandHandler("channels", self.list_channels))
        self.application.add_handler(CommandHandler("users", self.users_list))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.VIDEO, self.handle_media))
        self.application.add_handler(MessageHandler(filters.Document.VIDEO, self.handle_media))
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Start bot
        print("🤖 Bot is running...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def _set_bot_username(self):
        """Set bot username"""
        bot_info = await self.application.bot.get_me()
        self.bot_username = bot_info.username

def main():
    bot = MediaBot()
    bot.run()

if __name__ == "__main__":
    main()
