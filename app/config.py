import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    API_ID = os.getenv('API_ID', '')
    API_HASH = os.getenv('API_HASH', '')
    
    # MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    DB_NAME = os.getenv('DB_NAME', 'telegram_media')
    
    # Admin Settings
    ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
    
    # API Settings
    API_SECRET = os.getenv('API_SECRET', 'default-secret-key-change-me')
    API_PORT = int(os.getenv('API_PORT', 8000))
    
    # Bot Settings
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024))
    SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 3600))
    
    # Supported formats
    VIDEO_FORMATS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']
    SUBTITLE_FORMATS = ['.srt', '.ass', '.vtt']
    AUDIO_FORMATS = ['.mp3', '.aac', '.flac', '.wav']

# Validate required config
if not Config.BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required!")
