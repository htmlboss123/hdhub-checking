import re
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Optional
import asyncio
import aiohttp

def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
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

def get_file_quality_from_name(filename: str) -> Optional[str]:
    """Extract quality from filename"""
    quality_patterns = {
        '2160p': ['2160p', '4k', '4K', 'ultrahd'],
        '1080p': ['1080p', 'fullhd', 'fhd'],
        '720p': ['720p', 'hd', 'hdtv'],
        '480p': ['480p', 'sd', 'dvdrip'],
        '360p': ['360p'],
        '240p': ['240p']
    }
    
    filename_lower = filename.lower()
    for quality, patterns in quality_patterns.items():
        for pattern in patterns:
            if pattern in filename_lower:
                return quality
    
    return None

def get_file_resolution(filename: str) -> Optional[str]:
    """Extract resolution from filename"""
    # Try to find patterns like 1920x1080
    pattern = r'(\d{3,4})x(\d{3,4})'
    match = re.search(pattern, filename)
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    return None

def extract_metadata(text: str) -> List[str]:
    """Extract tags from text"""
    tags = []
    
    # Extract year
    year_match = re.search(r'(19|20)\d{2}', text)
    if year_match:
        tags.append(year_match.group())
    
    # Extract quality
    quality = get_file_quality_from_name(text)
    if quality:
        tags.append(quality)
    
    # Extract format
    formats = ['mkv', 'mp4', 'avi', 'x264', 'h264', 'h265', 'x265']
    for fmt in formats:
        if fmt in text.lower():
            tags.append(fmt)
    
    # Extract audio
    audio_formats = ['aac', 'mp3', 'flac', 'dts', 'atmos']
    for audio in audio_formats:
        if audio in text.lower():
            tags.append(audio)
    
    # Extract common tags
    common_tags = ['hindi', 'english', 'tamil', 'telugu', 'malayalam', 'kannada', 'web-dl', 'bluray', 'dvdrip']
    for tag in common_tags:
        if tag in text.lower():
            tags.append(tag)
    
    return list(set(tags))  # Remove duplicates

def generate_file_hash(file_id: str, salt: str = "telegram_media") -> str:
    """Generate unique hash for file"""
    return hashlib.md5(f"{file_id}{salt}".encode()).hexdigest()

def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename"""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove excessive spaces
    filename = re.sub(r'\s+', ' ', filename)
    # Remove leading/trailing spaces
    filename = filename.strip()
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:196] + ext
    
    return filename

def get_streaming_url(file_url: str) -> str:
    """Generate streaming URL with appropriate headers"""
    # This is for building streaming links
    # You can add custom parameters for your video player
    return file_url

async def download_file(url: str, save_path: str, chunk_size: int = 8192):
    """Download file with progress"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Progress callback would go here
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        # yield progress
    
    return save_path

def is_video_file(filename: str) -> bool:
    """Check if file is a video"""
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp']
    return any(filename.lower().endswith(ext) for ext in video_extensions)

def is_subtitle_file(filename: str) -> bool:
    """Check if file is a subtitle"""
    subtitle_extensions = ['.srt', '.ass', '.vtt', '.sub', '.ssa']
    return any(filename.lower().endswith(ext) for ext in subtitle_extensions)

def format_duration(seconds: int) -> str:
    """Format duration in HH:MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
