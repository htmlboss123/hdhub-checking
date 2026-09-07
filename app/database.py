import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import hashlib

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import Config

class Database:
    def __init__(self):
        try:
            self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db: Database = self.client[Config.DB_NAME]
            # Test connection
            self.client.server_info()
            self._init_collections()
            print(f"✅ Connected to MongoDB: {Config.DB_NAME}")
        except Exception as e:
            print(f"⚠️ MongoDB connection failed: {e}")
            # Create dummy collections for startup
            self.client = None
            self.db = None
        
    def _init_collections(self):
        """Initialize collections and indexes"""
        if not self.db:
            return
            
        self.files: Collection = self.db['media_files']
        self.users: Collection = self.db['users']
        self.downloads: Collection = self.db['download_requests']
        self.logs: Collection = self.db['bot_logs']
        self.settings: Collection = self.db['bot_settings']
        
        # Create indexes
        try:
            self.files.create_index([('file_id', 1)], unique=True)
            self.files.create_index([('file_name', 1)])
            self.files.create_index([('channel_id', 1)])
            self.files.create_index([('created_at', -1)])
        except Exception as e:
            print(f"Index creation warning: {e}")
    
    def save_file(self, file_data: Dict) -> bool:
        """Save or update file"""
        if not self.db:
            return False
        try:
            existing = self.files.find_one({'file_id': file_data['file_id']})
            if existing:
                self.files.update_one(
                    {'file_id': file_data['file_id']},
                    {'$set': file_data}
                )
            else:
                self.files.insert_one(file_data)
            return True
        except Exception as e:
            print(f"Save file error: {e}")
            return False
    
    def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file by ID"""
        if not self.db:
            return None
        return self.files.find_one({'file_id': file_id})
    
    def search_files(self, query: str, limit: int = 20) -> List[Dict]:
        """Search files"""
        if not self.db:
            return []
        try:
            search_query = {
                '$or': [
                    {'file_name': {'$regex': query, '$options': 'i'}},
                    {'tags': {'$regex': query, '$options': 'i'}},
                    {'caption': {'$regex': query, '$options': 'i'}}
                ],
                'is_active': True
            }
            cursor = self.files.find(search_query).sort('created_at', -1).limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def save_user(self, user_data: Dict) -> bool:
        """Save user"""
        if not self.db:
            return False
        try:
            self.users.update_one(
                {'user_id': user_data['user_id']},
                {'$set': user_data, '$currentDate': {'last_active': True}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Save user error: {e}")
            return False
    
    def update_file_stats(self, file_id: str, action: str):
        """Update file stats"""
        if not self.db:
            return
        field = 'download_count' if action == 'download' else 'watch_count'
        try:
            self.files.update_one(
                {'file_id': file_id},
                {'$inc': {field: 1}}
            )
        except Exception as e:
            print(f"Update stats error: {e}")
    
    def get_stats(self) -> Dict:
        """Get statistics"""
        if not self.db:
            return {
                'total_files': 0,
                'total_users': 0,
                'total_downloads': 0,
                'total_views': 0,
                'file_types': [],
                'quality_distribution': []
            }
        try:
            stats = {
                'total_files': self.files.count_documents({'is_active': True}) if self.files else 0,
                'total_users': self.users.count_documents({}) if self.users else 0,
                'total_downloads': 0,
                'total_views': 0,
                'file_types': [],
                'quality_distribution': []
            }
            # Get downloads count
            if self.files:
                pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$download_count'}}}]
                result = list(self.files.aggregate(pipeline))
                if result:
                    stats['total_downloads'] = result[0]['total']
                
                # Get views count
                pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$watch_count'}}}]
                result = list(self.files.aggregate(pipeline))
                if result:
                    stats['total_views'] = result[0]['total']
            
            return stats
        except Exception as e:
            print(f"Get stats error: {e}")
            return {'total_files': 0, 'total_users': 0, 'total_downloads': 0, 'total_views': 0}

# Singleton
db = Database()
