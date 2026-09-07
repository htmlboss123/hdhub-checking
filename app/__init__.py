"""
Telegram Media Bot - Package Initialization
A complete solution for indexing and serving media files from Telegram channels
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from app.config import Config
from app.database import db
from app.models import MediaFile, User, DownloadRequest

__all__ = [
    'Config',
    'db',
    'MediaFile',
    'User',
    'DownloadRequest',
]
