import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from app.config import Config

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.files = None
        self.users = None
        self.downloads = None
        self.settings = None
        self.logs = None
        
        try:
            if Config.MONGO_URI:
                self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
                self.db = self.client[Config.DB_NAME]
                self.client.server_info()
                self._init_collections()
                print(f"✅ Connected to MongoDB: {Config.DB_NAME}")
        except Exception as e:
            print(f"⚠️ MongoDB connection failed: {e}")
            print("Bot will run in limited mode without database")
    
    def _init_collections(self):
        if not self.db:
            return
        self.files = self.db['media_files']
        self.users = self.db['users']
        self.downloads = self.db['download_requests']
        self.logs = self.db['bot_logs']
        self.settings = self.db['bot_settings']
    
    def get_stats(self) -> Dict:
        if not self.db:
            return {'total_files': 0, 'total_users': 0, 'total_downloads': 0, 'total_views': 0}
        try:
            return {
                'total_files': self.files.count_documents({}) if self.files else 0,
                'total_users': self.users.count_documents({}) if self.users else 0,
                'total_downloads': 0,
                'total_views': 0
            }
        except:
            return {'total_files': 0, 'total_users': 0, 'total_downloads': 0, 'total_views': 0}
    
    def search_files(self, query: str, limit: int = 20) -> List[Dict]:
        if not self.db or not self.files:
            return []
        try:
            search_query = {
                '$or': [
                    {'file_name': {'$regex': query, '$options': 'i'}},
                    {'tags': {'$regex': query, '$options': 'i'}},
                    {'caption': {'$regex': query, '$options': 'i'}}
                ]
            }
            cursor = self.files.find(search_query).sort('created_at', -1).limit(limit)
            return list(cursor)
        except:
            return []
    
    def save_user(self, user_data: Dict) -> bool:
        if not self.db or not self.users:
            return False
        try:
            self.users.update_one(
                {'user_id': user_data['user_id']},
                {'$set': user_data, '$currentDate': {'last_active': True}},
                upsert=True
            )
            return True
        except:
            return False

# Singleton
db = Database()
