import os
import logging
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
    admin_ids = os.getenv('ADMIN_IDS', '')
    ADMIN_IDS = [int(id.strip()) for id in admin_ids.split(',') if id.strip()]
    
    # API Settings
    API_SECRET = os.getenv('API_SECRET', 'default-secret-key-change-me')
    API_PORT = int(os.getenv('API_PORT', 8000))
    
    # Bot Settings
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024))
    SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 3600))
    
    # Supported formats
    VIDEO_FORMATS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp']
    SUBTITLE_FORMATS = ['.srt', '.ass', '.vtt', '.sub', '.ssa']
    AUDIO_FORMATS = ['.mp3', '.aac', '.flac', '.wav', '.m4a', '.ogg']
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
    
    # Base URL for API
    BASE_URL = os.getenv('BASE_URL', 'https://your-domain.com')

# Validate critical config
if not Config.BOT_TOKEN:
    print("⚠️ WARNING: BOT_TOKEN not set! Bot will not function.")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL),
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
