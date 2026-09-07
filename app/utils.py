import re
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp

def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_file_quality(width: int, height: int) -> str:
    """Determine video quality from dimensions"""
    max_dim = max(width, height)
    
    if max_dim >= 3840:
        return "2160p (4K)"
    elif max_dim >= 1920:
        return "1080p (Full HD)"
    elif max_dim >= 1280:
        return "720p (HD)"
    elif max_dim >= 854:
        return "480p (SD)"
    else:
        return f"{height}p"

def extract_metadata(text: str) -> List[str]:
    """Extract tags from text"""
    if not text:
        return []
    
    tags = []
    text_lower = text.lower()
    
    # Extract year
    year_match = re.search(r'(19|20)\d{2}', text)
    if year_match:
        tags.append(year_match.group())
    
    # Quality
    qualities = ['2160p', '1080p', '720p', '480p', '4k', 'hd', 'fullhd']
    for q in qualities:
        if q in text_lower:
            tags.append(q)
    
    # Formats
    formats = ['mkv', 'mp4', 'avi', 'x264', 'h264', 'h265', 'x265', 'hevc']
    for f in formats:
        if f in text_lower:
            tags.append(f)
    
    # Languages
    languages = ['hindi', 'english', 'tamil', 'telugu', 'malayalam', 'kannada', 'bengali', 'punjabi']
    for lang in languages:
        if lang in text_lower:
            tags.append(lang)
    
    # Sources
    sources = ['web-dl', 'bluray', 'dvdrip', 'hdtv', 'webrip']
    for src in sources:
        if src in text_lower:
            tags.append(src)
    
    # Audio
    audio = ['aac', 'mp3', 'flac', 'dts', 'atmos', 'ddp']
    for a in audio:
        if a in text_lower:
            tags.append(a)
    
    return list(set(tags))

async def get_telegram_file_url(file_id: str) -> str:
    """Get file URL from Telegram API"""
    from app.config import Config
    
    try:
        from telegram import Bot
        bot = Bot(token=Config.BOT_TOKEN)
        file = await bot.get_file(file_id)
        return file.file_path
    except Exception as e:
        raise Exception(f"Failed to get file URL: {e}")

def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:196] + ext
    
    return filename

def generate_token(length: int = 32) -> str:
    """Generate random token"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
