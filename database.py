from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import hashlib
import json

from config import Config
from models import MediaFile, User, DownloadRequest

class Database:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db: Database = self.client[Config.DB_NAME]
        self._init_collections()
        
    def _init_collections(self):
        """Initialize collections and indexes"""
        # Collections
        self.files: Collection = self.db['media_files']
        self.users: Collection = self.db['users']
        self.downloads: Collection = self.db['download_requests']
        self.logs: Collection = self.db['bot_logs']
        self.settings: Collection = self.db['bot_settings']
        
        # Indexes for fast queries
        self.files.create_index([('file_id', 1)], unique=True)
        self.files.create_index([('file_name', 1)])
        self.files.create_index([('channel_id', 1)])
        self.files.create_index([('tags', 1)])
        self.files.create_index([('quality', 1)])
        self.files.create_index([('created_at', -1)])
        self.files.create_index([('is_active', 1)])
        
        self.users.create_index([('user_id', 1)], unique=True)
        self.downloads.create_index([('file_id', 1)])
        self.downloads.create_index([('user_id', 1)])
        self.downloads.create_index([('created_at', -1)])
        
    # ---- FILE OPERATIONS ----
    
    def save_file(self, file_data: Dict) -> bool:
        """Save or update file in database"""
        try:
            # Check if file exists
            existing = self.files.find_one({'file_id': file_data['file_id']})
            
            if existing:
                file_data['updated_at'] = datetime.utcnow()
                self.files.update_one(
                    {'file_id': file_data['file_id']},
                    {'$set': file_data}
                )
            else:
                file_data['created_at'] = datetime.utcnow()
                file_data['updated_at'] = datetime.utcnow()
                self.files.insert_one(file_data)
            
            return True
        except Exception as e:
            self.log_error(f"Save file error: {str(e)}")
            return False
    
    def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file by ID"""
        return self.files.find_one({'file_id': file_id})
    
    def get_files_by_channel(self, channel_id: int, limit: int = 50) -> List[Dict]:
        """Get all files from a channel"""
        cursor = self.files.find(
            {'channel_id': channel_id, 'is_active': True}
        ).sort('created_at', -1).limit(limit)
        return list(cursor)
    
    def search_files(self, query: str, limit: int = 20) -> List[Dict]:
        """Search files by name or tags"""
        search_query = {
            '$or': [
                {'file_name': {'$regex': query, '$options': 'i'}},
                {'tags': {'$regex': query, '$options': 'i'}},
                {'caption': {'$regex': query, '$options': 'i'}},
                {'quality': {'$regex': query, '$options': 'i'}}
            ],
            'is_active': True
        }
        cursor = self.files.find(search_query).sort('created_at', -1).limit(limit)
        return list(cursor)
    
    def update_file_stats(self, file_id: str, action: str):
        """Update download or watch count"""
        field = 'download_count' if action == 'download' else 'watch_count'
        self.files.update_one(
            {'file_id': file_id},
            {'$inc': {field: 1}}
        )
    
    def get_file_by_name_pattern(self, pattern: str) -> List[Dict]:
        """Get files matching pattern (like 'Satluj.2026.2160p')"""
        regex_pattern = pattern.replace('.', '\\.')
        return list(self.files.find({
            'file_name': {'$regex': regex_pattern, '$options': 'i'},
            'is_active': True
        }).sort('created_at', -1))
    
    # ---- USER OPERATIONS ----
    
    def save_user(self, user_data: Dict) -> bool:
        """Save or update user"""
        try:
            self.users.update_one(
                {'user_id': user_data['user_id']},
                {'$set': user_data, '$currentDate': {'last_active': True}},
                upsert=True
            )
            return True
        except Exception as e:
            self.log_error(f"Save user error: {str(e)}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return self.users.find_one({'user_id': user_id})
    
    def get_admins(self) -> List[Dict]:
        """Get all admin users"""
        return list(self.users.find({'is_admin': True}))
    
    # ---- DOWNLOAD OPERATIONS ----
    
    def create_download_request(self, file_id: str, user_id: int, ip: str = None) -> str:
        """Create download request and return token"""
        token = hashlib.md5(f"{file_id}{user_id}{datetime.utcnow()}".encode()).hexdigest()
        
        request = {
            'file_id': file_id,
            'user_id': user_id,
            'ip_address': ip,
            'token': token,
            'status': 'pending',
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=24)
        }
        
        self.downloads.insert_one(request)
        return token
    
    def validate_download_token(self, token: str) -> Optional[Dict]:
        """Validate download token"""
        request = self.downloads.find_one({
            'token': token,
            'expires_at': {'$gt': datetime.utcnow()},
            'status': 'pending'
        })
        
        if request:
            self.downloads.update_one(
                {'token': token},
                {'$set': {'status': 'completed'}}
            )
            return request
        return None
    
    # ---- LOGGING ----
    
    def log_error(self, message: str):
        """Log error messages"""
        self.logs.insert_one({
            'type': 'error',
            'message': message,
            'timestamp': datetime.utcnow()
        })
    
    def log_action(self, action: str, details: Dict):
        """Log bot actions"""
        self.logs.insert_one({
            'type': 'action',
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow()
        })
    
    # ---- STATISTICS ----
    
    def get_stats(self) -> Dict:
        """Get overall statistics"""
        stats = {
            'total_files': self.files.count_documents({'is_active': True}),
            'total_users': self.users.count_documents({}),
            'total_downloads': sum([d['download_count'] for d in self.files.find({}, {'download_count': 1})]),
            'total_views': sum([d['watch_count'] for d in self.files.find({}, {'watch_count': 1})]),
            'file_types': list(self.files.aggregate([
                {'$group': {'_id': '$file_format', 'count': {'$sum': 1}}}
            ])),
            'quality_distribution': list(self.files.aggregate([
                {'$group': {'_id': '$quality', 'count': {'$sum': 1}}}
            ]))
        }
        return stats

# Singleton instance
db = Database()
