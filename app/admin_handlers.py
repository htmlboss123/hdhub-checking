#!/usr/bin/env python3
"""
Admin Handlers for Telegram Media Bot
Complete admin panel with full control over the bot
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import io
import csv
import zipfile
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.config import Config
from app.database import db
from app.utils import format_file_size, get_file_quality, extract_metadata

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AdminHandlers:
    """
    All admin-related handlers for the bot
    """
    
    def __init__(self):
        self.scanning = False
        self.backup_in_progress = False
    
    # ============================================
    # VERIFICATION & AUTHENTICATION
    # ============================================
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in Config.ADMIN_IDS
    
    async def require_admin(self, update: Update) -> bool:
        """Decorator-like function to check admin status"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text(
                "🚫 **Access Denied**\n\nYou are not authorized to use admin commands.\n\n"
                "This incident has been logged.",
                parse_mode='Markdown'
            )
            db.log_action('unauthorized_access', {
                'user_id': update.effective_user.id,
                'username': update.effective_user.username,
                'command': update.message.text
            })
            return False
        return True
    
    # ============================================
    # CHANNEL MANAGEMENT
    # ============================================
    
    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a channel to monitor"""
        if not await self.require_admin(update):
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 **Add Channel**\n\n"
                "Usage: `/addchannel <channel_link_or_id>`\n\n"
                "Examples:\n"
                "• `/addchannel https://t.me/yourchannel`\n"
                "• `/addchannel -1001234567890`\n"
                "• `/addchannel @yourchannel`\n\n"
                "⚠️ Make sure the bot is a member of the channel!",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[0]
        
        try:
            status_msg = await update.message.reply_text("🔍 Checking channel...")
            
            # Parse channel input
            if channel_input.startswith('https://t.me/'):
                username = channel_input.split('/')[-1]
                chat = await context.bot.get_chat(f'@{username}')
            elif channel_input.startswith('@'):
                chat = await context.bot.get_chat(channel_input)
            else:
                chat = await context.bot.get_chat(int(channel_input))
            
            # Check if channel already exists
            existing = db.settings.find_one({
                'type': 'channel',
                'channel_id': chat.id
            })
            
            if existing:
                await status_msg.edit_text(
                    f"⚠️ Channel already exists!\n\n"
                    f"📢 {chat.title}\n"
                    f"🆔 {chat.id}\n"
                    f"📅 Added: {existing.get('added_at', 'Unknown')}"
                )
                return
            
            # Save channel to database
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
                'total_files': 0,
                'status': 'active'
            }
            
            db.settings.insert_one(channel_data)
            
            await status_msg.edit_text(
                f"✅ **Channel Added Successfully!**\n\n"
                f"📢 **Title:** {chat.title}\n"
                f"🆔 **ID:** {chat.id}\n"
                f"🔗 **Link:** {channel_data['channel_link'] or 'Private'}\n\n"
                f"🔄 Starting initial scan..."
            )
            
            # Immediately scan this channel
            files_found = await self._scan_single_channel(context, chat.id, status_msg)
            
            # Update channel stats
            db.settings.update_one(
                {'channel_id': chat.id},
                {'$set': {
                    'total_files': files_found,
                    'last_scanned': datetime.utcnow()
                }}
            )
            
            await status_msg.edit_text(
                f"✅ **Channel Added & Scanned!**\n\n"
                f"📢 {chat.title}\n"
                f"📁 Found: {files_found} media files\n"
                f"🆔 Channel ID: {chat.id}\n\n"
                f"Use `/channels` to view all monitored channels."
            )
            
            db.log_action('add_channel', {
                'channel_id': chat.id,
                'channel_title': chat.title,
                'added_by': update.effective_user.id
            })
            
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            await update.message.reply_text(
                f"❌ **Error Adding Channel**\n\n"
                f"Please make sure:\n"
                f"• The channel exists\n"
                f"• The bot is a member\n"
                f"• The channel ID/link is correct\n\n"
                f"Error: {str(e)}"
            )
    
    async def remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a channel from monitoring"""
        if not await self.require_admin(update):
            return
        
        if not context.args:
            await update.message.reply_text(
                "🗑️ **Remove Channel**\n\n"
                "Usage: `/removechannel <channel_id>`\n\n"
                "Example: `/removechannel -1001234567890`\n\n"
                "To see all channel IDs, use `/channels`",
                parse_mode='Markdown'
            )
            return
        
        try:
            channel_id = int(context.args[0])
            
            # Check if channel exists
            channel = db.settings.find_one({
                'type': 'channel',
                'channel_id': channel_id
            })
            
            if not channel:
                await update.message.reply_text(
                    f"❌ Channel {channel_id} not found in monitoring list."
                )
                return
            
            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Remove", callback_data=f"confirm_remove_{channel_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_remove")
                ]
            ]
            
            await update.message.reply_text(
                f"⚠️ **Confirm Channel Removal**\n\n"
                f"📢 **Title:** {channel.get('channel_title', 'Unknown')}\n"
                f"🆔 **ID:** {channel_id}\n"
                f"📁 **Files:** {channel.get('total_files', 0)}\n"
                f"📅 **Added:** {channel.get('added_at', 'Unknown')}\n\n"
                f"⚠️ This will also remove all files indexed from this channel.\n"
                f"This action cannot be undone!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid channel ID. Please provide a numeric ID.\n"
                "Example: `/removechannel -1001234567890`"
            )
        except Exception as e:
            logger.error(f"Remove channel error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def confirm_remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm channel removal"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.message.reply_text("🚫 Unauthorized.")
            return
        
        channel_id = int(query.data.replace('confirm_remove_', ''))
        
        try:
            # Delete channel from settings
            result = db.settings.delete_one({
                'type': 'channel',
                'channel_id': channel_id
            })
            
            if result.deleted_count > 0:
                # Optionally delete all files from this channel
                files_deleted = db.files.delete_many({'channel_id': channel_id})
                
                await query.message.edit_text(
                    f"✅ **Channel Removed Successfully**\n\n"
                    f"🗑️ Removed from monitoring\n"
                    f"📁 Deleted {files_deleted.deleted_count} indexed files\n"
                    f"🆔 Channel ID: {channel_id}"
                )
                
                db.log_action('remove_channel', {
                    'channel_id': channel_id,
                    'deleted_by': query.from_user.id,
                    'files_deleted': files_deleted.deleted_count
                })
            else:
                await query.message.edit_text(f"❌ Channel {channel_id} not found.")
                
        except Exception as e:
            logger.error(f"Confirm remove error: {e}")
            await query.message.edit_text(f"❌ Error: {str(e)}")
    
    async def cancel_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel channel removal"""
        query = update.callback_query
        await query.answer()
        await query.message.edit_text("✅ Channel removal cancelled.")
    
    async def list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all monitored channels"""
        if not await self.require_admin(update):
            return
        
        try:
            channels = list(db.settings.find({'type': 'channel'}).sort('added_at', -1))
            
            if not channels:
                await update.message.reply_text(
                    "📢 **No Channels Monitored**\n\n"
                    "Use `/addchannel` to add a channel for monitoring.",
                    parse_mode='Markdown'
                )
                return
            
            msg = "📢 **Monitored Channels**\n\n"
            total_files = 0
            
            for idx, channel in enumerate(channels, 1):
                title = channel.get('channel_title', 'Unknown')
                channel_id = channel['channel_id']
                files_count = channel.get('total_files', 0)
                total_files += files_count
                status = "🟢 Active" if channel.get('is_active', True) else "🔴 Inactive"
                last_scanned = channel.get('last_scanned')
                last_scanned_str = last_scanned.strftime('%Y-%m-%d %H:%M') if last_scanned else 'Never'
                
                msg += f"**{idx}. {title}**\n"
                msg += f"  🆔 `{channel_id}`\n"
                msg += f"  📁 {files_count} files\n"
                msg += f"  📅 Last: {last_scanned_str}\n"
                msg += f"  {status}\n\n"
            
            msg += f"📊 **Total Files:** {total_files}\n"
            msg += f"📢 **Total Channels:** {len(channels)}"
            
            # Send in multiple messages if too long
            if len(msg) > 4000:
                parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(msg, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"List channels error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    # ============================================
    # SCANNING FUNCTIONS
    # ============================================
    
    async def scan_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually scan all channels"""
        if not await self.require_admin(update):
            return
        
        if self.scanning:
            await update.message.reply_text(
                "⏳ **Scan Already In Progress**\n\n"
                "Please wait for the current scan to complete."
            )
            return
        
        status_msg = await update.message.reply_text(
            "🔍 **Starting Full Scan...**\n\n"
            "⏳ Scanning all channels for new media files..."
        )
        
        self.scanning = True
        total_files = 0
        channels_scanned = 0
        
        try:
            channels = list(db.settings.find({'type': 'channel', 'is_active': True}))
            
            if not channels:
                await status_msg.edit_text(
                    "📢 **No Active Channels**\n\n"
                    "Add channels using `/addchannel`"
                )
                self.scanning = False
                return
            
            for idx, channel in enumerate(channels, 1):
                channel_id = channel['channel_id']
                channel_title = channel.get('channel_title', f'Channel {channel_id}')
                
                await status_msg.edit_text(
                    f"🔍 **Scanning...**\n\n"
                    f"📢 Channel: {channel_title}\n"
                    f"📊 Progress: {idx}/{len(channels)}\n"
                    f"📁 Found: {total_files} files so far\n"
                    f"⏳ Please wait..."
                )
                
                try:
                    files_found = await self._scan_single_channel(context, channel_id, status_msg)
                    total_files += files_found
                    channels_scanned += 1
                    
                    # Update channel stats
                    db.settings.update_one(
                        {'channel_id': channel_id},
                        {'$set': {
                            'total_files': files_found,
                            'last_scanned': datetime.utcnow()
                        }}
                    )
                    
                except Exception as e:
                    logger.error(f"Error scanning channel {channel_id}: {e}")
                    await status_msg.edit_text(
                        f"⚠️ **Error scanning {channel_title}**\n"
                        f"Error: {str(e)}\n\n"
                        f"Continuing with next channel..."
                    )
                    await asyncio.sleep(2)
            
            await status_msg.edit_text(
                f"✅ **Scan Complete!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Channels Scanned: {channels_scanned}/{len(channels)}\n"
                f"• New Files Found: {total_files}\n"
                f"• Total Files in DB: {db.files.count_documents({'is_active': True})}\n"
                f"• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            db.log_action('manual_scan', {
                'channels_scanned': channels_scanned,
                'total_files': total_files
            })
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await status_msg.edit_text(f"❌ **Scan Error:** {str(e)}")
        
        finally:
            self.scanning = False
    
    async def _scan_single_channel(self, context: ContextTypes.DEFAULT_TYPE, channel_id: int, status_msg=None):
        """Scan a single channel for media files"""
        files_found = 0
        offset = 0
        max_messages = 5000  # Limit to avoid timeout
        
        try:
            while offset < max_messages:
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
                    
                    elif msg.document:
                        file_name = msg.document.file_name or 'document'
                        file_ext = os.path.splitext(file_name)[1].lower()
                        
                        # Check if video or subtitle
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
                    
                    # Update progress periodically
                    if files_found > 0 and files_found % 10 == 0 and status_msg:
                        try:
                            await status_msg.edit_text(
                                f"🔍 Scanning channel...\n"
                                f"📁 Found: {files_found} files\n"
                                f"📊 Processing message: {offset + len(messages)}"
                            )
                        except:
                            pass
                
                offset += 100
                await asyncio.sleep(0.1)  # Rate limiting
                
                if offset > max_messages:
                    break
            
        except Exception as e:
            logger.error(f"Scan error for channel {channel_id}: {e}")
            raise
        
        return files_found
    
    # ============================================
    # USER MANAGEMENT
    # ============================================
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        if not await self.require_admin(update):
            return
        
        try:
            total_users = db.users.count_documents({})
            
            # Active users (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = db.users.count_documents({
                'last_active': {'$gt': week_ago}
            })
            
            # Top downloaders
            top_users = list(db.users.find().sort('download_count', -1).limit(10))
            
            msg = f"""
👥 **User Statistics**

📊 **Overview:**
• Total Users: {total_users}
• Active (7 days): {active_users}
• Inactive: {total_users - active_users}

🏆 **Top Downloaders:**
"""
            if top_users:
                for i, user in enumerate(top_users, 1):
                    username = user.get('username') or user.get('first_name', 'Unknown')
                    downloads = user.get('download_count', 0)
                    msg += f"  {i}. {username}: {downloads} downloads\n"
            else:
                msg += "  No download activity yet."
            
            # Export option
            keyboard = [
                [InlineKeyboardButton("📥 Export Users CSV", callback_data="export_users")]
            ]
            
            await update.message.reply_text(
                msg,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Users list error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def export_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Export users to CSV"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.message.reply_text("🚫 Unauthorized.")
            return
        
        try:
            await query.message.reply_text("📊 Generating user export...")
            
            # Get all users
            users = list(db.users.find({}))
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['User ID', 'Username', 'First Name', 'Last Name', 'Downloads', 'Watches', 'Last Active', 'Created'])
            
            for user in users:
                writer.writerow([
                    user.get('user_id', ''),
                    user.get('username', ''),
                    user.get('first_name', ''),
                    user.get('last_name', ''),
                    user.get('download_count', 0),
                    user.get('watch_count', 0),
                    user.get('last_active', ''),
                    user.get('created_at', '')
                ])
            
            output.seek(0)
            
            # Send file
            await query.message.reply_document(
                document=InputFile(
                    io.BytesIO(output.getvalue().encode('utf-8')),
                    filename=f'users_export_{datetime.now().strftime("%Y%m%d")}.csv'
                ),
                caption=f"📊 User Export\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n👥 Total: {len(users)} users"
            )
            
        except Exception as e:
            logger.error(f"Export users error: {e}")
            await query.message.reply_text(f"❌ Error: {str(e)}")
    
    # ============================================
    # BROADCAST SYSTEM
    # ============================================
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send broadcast message to all users"""
        if not await self.require_admin(update):
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 **Broadcast Message**\n\n"
                "Usage: `/broadcast <message>`\n\n"
                "Example: `/broadcast New movies added! Check /recent`\n\n"
                "Options:\n"
                "• Reply to a message with /broadcast to forward it\n"
                "• Use /broadcast_preview to preview before sending",
                parse_mode='Markdown'
            )
            return
        
        message_text = ' '.join(context.args)
        
        # Get user count
        total_users = db.users.count_documents({})
        
        if total_users == 0:
            await update.message.reply_text("❌ No users to broadcast to.")
            return
        
        # Confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Send Now", callback_data="confirm_broadcast"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
            ]
        ]
        
        await update.message.reply_text(
            f"📢 **Broadcast Preview**\n\n"
            f"Message:\n```\n{message_text[:500]}\n```\n\n"
            f"📊 Recipients: {total_users} users\n"
            f"⚠️ This will send a message to ALL users.\n\n"
            f"Confirm to proceed.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Store for later
        context.user_data['broadcast_message'] = message_text
    
    async def confirm_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm and send broadcast"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.message.reply_text("🚫 Unauthorized.")
            return
        
        message_text = context.user_data.get('broadcast_message')
        if not message_text:
            await query.message.reply_text("❌ No broadcast message found.")
            return
        
        status_msg = await query.message.edit_text(
            "📤 **Sending Broadcast...**\n\n"
            "⏳ Please wait..."
        )
        
        try:
            users = db.users.find({})
            sent = 0
            failed = 0
            
            for user in users:
                try:
                    await context.bot.send_message(
                        user['user_id'],
                        f"📢 **Broadcast Message**\n\n{message_text}",
                        parse_mode='Markdown'
                    )
                    sent += 1
                    await asyncio.sleep(0.05)  # Rate limiting
                except Exception:
                    failed += 1
            
            await status_msg.edit_text(
                f"✅ **Broadcast Completed!**\n\n"
                f"📤 Sent: {sent} users\n"
                f"❌ Failed: {failed} users\n"
                f"📊 Total: {sent + failed} users"
            )
            
            db.log_action('broadcast', {
                'sent': sent,
                'failed': failed,
                'message': message_text[:100]
            })
            
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            await status_msg.edit_text(f"❌ **Broadcast Error:** {str(e)}")
    
    async def cancel_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel broadcast"""
        query = update.callback_query
        await query.answer()
        await query.message.edit_text("✅ Broadcast cancelled.")
    
    # ============================================
    # BACKUP SYSTEM
    # ============================================
    
    async def backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create database backup"""
        if not await self.require_admin(update):
            return
        
        if self.backup_in_progress:
            await update.message.reply_text("⏳ Backup already in progress...")
            return
        
        status_msg = await update.message.reply_text(
            "📦 **Creating Backup...**\n\n"
            "⏳ Please wait..."
        )
        
        self.backup_in_progress = True
        
        try:
            # Create backup in memory
            backup_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'version': '1.0.0',
                'data': {
                    'files': list(db.files.find({})),
                    'users': list(db.users.find({})),
                    'settings': list(db.settings.find({})),
                    'downloads': list(db.downloads.find({}))
                }
            }
            
            # Convert ObjectId to string for JSON serialization
            for collection in backup_data['data'].values():
                for item in collection:
                    if '_id' in item:
                        item['_id'] = str(item['_id'])
            
            # Create ZIP file
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add JSON data
                json_data = json.dumps(backup_data, indent=2, default=str)
                zip_file.writestr(f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json', json_data)
                
                # Add stats
                stats = db.get_stats()
                stats['timestamp'] = datetime.utcnow().isoformat()
                zip_file.writestr('stats.json', json.dumps(stats, indent=2, default=str))
            
            zip_buffer.seek(0)
            
            await status_msg.edit_text(
                f"✅ **Backup Created Successfully!**\n\n"
                f"📦 Size: {format_file_size(len(zip_buffer.getvalue()))}\n"
                f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"📁 Files: {backup_data['data']['files'] and len(backup_data['data']['files']) or 0}\n"
                f"👥 Users: {backup_data['data']['users'] and len(backup_data['data']['users']) or 0}"
            )
            
            # Send backup file
            await update.message.reply_document(
                document=InputFile(
                    zip_buffer,
                    filename=f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
                ),
                caption="📦 Database Backup"
            )
            
            db.log_action('backup_created', {
                'size': len(zip_buffer.getvalue()),
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Backup error: {e}")
            await status_msg.edit_text(f"❌ **Backup Error:** {str(e)}")
        
        finally:
            self.backup_in_progress = False
    
    # ============================================
    # STATISTICS & DASHBOARD
    # ============================================
    
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed admin statistics"""
        if not await self.require_admin(update):
            return
        
        try:
            stats = db.get_stats()
            
            # Additional stats
            total_size = 0
            size_pipeline = db.files.aggregate([
                {'$group': {'_id': None, 'total': {'$sum': '$file_size'}}}
            ])
            size_result = list(size_pipeline)
            if size_result:
                total_size = size_result[0]['total']
            
            # Channel stats
            channels = list(db.settings.find({'type': 'channel'}))
            
            # Today's activity
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_downloads = db.downloads.count_documents({
                'created_at': {'$gt': today}
            })
            
            msg = f"""
📊 **Admin Dashboard**

📁 **Files:**
• Total: {stats.get('total_files', 0)}
• Total Size: {format_file_size(total_size)}
• Avg Size: {format_file_size(total_size / stats.get('total_files', 1)) if stats.get('total_files', 0) > 0 else 'N/A'}

👥 **Users:**
• Total: {stats.get('total_users', 0)}
• Today's Downloads: {today_downloads}

📢 **Channels:**
• Monitored: {len(channels)}
• Active: {sum(1 for c in channels if c.get('is_active', True))}

📊 **Usage:**
• Total Downloads: {stats.get('total_downloads', 0)}
• Total Views: {stats.get('total_views', 0)}

🔄 **Last Scan:**
• {db.settings.find_one({'type': 'system_info'}).get('last_scan', 'Never') if db.settings.find_one({'type': 'system_info'}) else 'Never'}

💾 **Database:**
• Files Collection: {db.files.count_documents({})}
• Users Collection: {db.users.count_documents({})}
• Downloads Collection: {db.downloads.count_documents({})}
"""
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Scan Now", callback_data="admin_scan"),
                    InlineKeyboardButton("📦 Backup", callback_data="admin_backup")
                ],
                [
                    InlineKeyboardButton("👥 Users", callback_data="admin_users"),
                    InlineKeyboardButton("📢 Channels", callback_data="admin_channels")
                ],
                [
                    InlineKeyboardButton("🗑️ Cleanup", callback_data="admin_cleanup")
                ]
            ]
            
            await update.message.reply_text(
                msg,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Admin stats error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    # ============================================
    # CLEANUP FUNCTIONS
    # ============================================
    
    async def cleanup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clean up duplicate and inactive files"""
        if not await self.require_admin(update):
            return
        
        status_msg = await update.message.reply_text(
            "🧹 **Starting Cleanup...**\n\n"
            "⏳ Please wait..."
        )
        
        try:
            # Find and remove duplicates (same file_unique_id)
            duplicates = db.files.aggregate([
                {'$group': {
                    '_id': '$file_unique_id',
                    'count': {'$sum': 1},
                    'ids': {'$push': '$file_id'}
                }},
                {'$match': {'count': {'$gt': 1}}}
            ])
            
            duplicate_count = 0
            for dup in duplicates:
                # Keep first, delete rest
                ids_to_delete = dup['ids'][1:]
                result = db.files.delete_many({'file_id': {'$in': ids_to_delete}})
                duplicate_count += result.deleted_count
            
            # Find and remove inactive files older than 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            inactive = db.files.delete_many({
                'is_active': False,
                'created_at': {'$lt': thirty_days_ago}
            })
            
            await status_msg.edit_text(
                f"✅ **Cleanup Complete!**\n\n"
                f"🧹 Duplicates Removed: {duplicate_count}\n"
                f"🗑️ Inactive Files Removed: {inactive.deleted_count}\n"
                f"📊 Total Active Files: {db.files.count_documents({'is_active': True})}"
            )
            
            db.log_action('cleanup', {
                'duplicates_removed': duplicate_count,
                'inactive_removed': inactive.deleted_count
            })
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            await status_msg.edit_text(f"❌ **Cleanup Error:** {str(e)}")
    
    # ============================================
    # CALLBACK HANDLERS
    # ============================================
    
    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback queries"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.message.reply_text("🚫 Unauthorized.")
            return
        
        data = query.data
        
        if data == "admin_scan":
            await self.scan_channels(update, context)
        elif data == "admin_backup":
            await self.backup(update, context)
        elif data == "admin_users":
            await self.users_list(update, context)
        elif data == "admin_channels":
            await self.list_channels(update, context)
        elif data == "admin_cleanup":
            await self.cleanup(update, context)
        elif data.startswith("confirm_remove_"):
            await self.confirm_remove_channel(update, context)
        elif data == "cancel_remove":
            await self.cancel_remove(update, context)
        elif data == "confirm_broadcast":
            await self.confirm_broadcast(update, context)
        elif data == "cancel_broadcast":
            await self.cancel_broadcast(update, context)
        elif data == "export_users":
            await self.export_users(update, context)

# ============================================
# REGISTRATION FUNCTION
# ============================================

def register_admin_handlers(application):
    """Register all admin handlers with the application"""
    admin = AdminHandlers()
    
    # Command handlers
    application.add_handler(CommandHandler("addchannel", admin.add_channel))
    application.add_handler(CommandHandler("removechannel", admin.remove_channel))
    application.add_handler(CommandHandler("channels", admin.list_channels))
    application.add_handler(CommandHandler("scan", admin.scan_channels))
    application.add_handler(CommandHandler("users", admin.users_list))
    application.add_handler(CommandHandler("broadcast", admin.broadcast))
    application.add_handler(CommandHandler("backup", admin.backup))
    application.add_handler(CommandHandler("cleanup", admin.cleanup))
    application.add_handler(CommandHandler("stats_full", admin.admin_stats))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(admin.admin_callback, pattern="^(admin_|confirm_|cancel_|export_)"))
    application.add_handler(CallbackQueryHandler(admin.confirm_remove_channel, pattern="^confirm_remove_"))
    application.add_handler(CallbackQueryHandler(admin.cancel_remove, pattern="^cancel_remove"))
    application.add_handler(CallbackQueryHandler(admin.confirm_broadcast, pattern="^confirm_broadcast"))
    application.add_handler(CallbackQueryHandler(admin.cancel_broadcast, pattern="^cancel_broadcast"))
    
    logger.info("✅ Admin handlers registered successfully")
    return admin

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("Admin handlers module loaded.")
