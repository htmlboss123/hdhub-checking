"""
Telegram Media Bot Package
"""

__version__ = "1.0.0"
__author__ = "Your Name"

# Lazy imports to avoid circular dependencies
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config
from app.database import db

__all__ = [
    'Config',
    'db',
]
