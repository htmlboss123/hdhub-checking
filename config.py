import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    API_ID = os.getenv('API_ID')
    API_HASH = os.getenv('API_HASH')
    
    # MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    DB_NAME = os.getenv('DB_NAME', 'telegram_media')
    
    # Admin Settings
    ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
    
    # API Settings
    API_SECRET = os.getenv('API_SECRET', 'your-super-secret-key')
    API_PORT = int(os.getenv('API_PORT', 8000))
    
    # Bot Settings
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024))  # 2GB
    SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 3600))  # 1 hour
    
    # Supported formats
    VIDEO_FORMATS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']
    SUBTITLE_FORMATS = ['.srt', '.ass', '.vtt']
    AUDIO_FORMATS = ['.mp3', '.aac', '.flac', '.wav']
    
    # File size limits for different qualities
    QUALITY_LIMITS = {
        '2160p': 8 * 1024**3,  # 8GB
        '1080p': 4 * 1024**3,   # 4GB
        '720p': 2 * 1024**3,    # 2GB
        '480p': 1 * 1024**3,    # 1GB
    }
