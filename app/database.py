import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import hashlib
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from app.config import logger, Config

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.files = None
        self.users = None
        self.downloads = None
        self.settings = None
        self.logs = None
        self.errors = None
        
        try:
            if Config.MONGO_URI:
                self.client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
                self.db = self.client[Config.DB_NAME]
                self.client.server_info()
                self._init_collections()
                logger.info(f"✅ Connected to MongoDB: {Config.DB_NAME}")
        except Exception as e:
            logger.error(f"⚠️ MongoDB connection failed: {e}")
            self.db = None
    
    def _init_collections(self):
        if not self.db:
            return
        self.files = self.db['media_files']
        self.users = self.db['users']
        self.downloads = self.db['download_requests']
        self.logs = self.db['bot_logs']
        self.settings = self.db['bot_settings']
        self.errors = self.db['error_logs']
        
        # Create indexes
        try:
            self.files.create_index([('file_id', 1)], unique=True)
            self.files.create_index([('file_name', 1)])
            self.files.create_index([('channel_id', 1)])
            self.files.create_index([('quality', 1)])
            self.files.create_index([('created_at', -1)])
            self.files.create_index([('search_text', 'text')])
            
            self.users.create_index([('user_id', 1)], unique=True)
            self.downloads.create_index([('created_at', -1)])
            self.downloads.create_index([('token', 1)], unique=True)
            self.errors.create_index([('created_at', -1)])
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    # ---- FILE OPERATIONS ----
    
    def save_file(self, file_data: Dict) -> bool:
        if not self.db or not self.files:
            return False
        try:
            # Add search text
            search_text = f"{file_data.get('file_name', '')} {file_data.get('caption', '')} {' '.join(file_data.get('tags', []))}"
            file_data['search_text'] = search_text.lower()
            
            existing = self.files.find_one({'file_id': file_data['file_id']})
            if existing:
                self.files.update_one(
                    {'file_id': file_data['file_id']},
                    {'$set': file_data, '$currentDate': {'updated_at': True}}
                )
            else:
                file_data['created_at'] = datetime.utcnow()
                file_data['updated_at'] = datetime.utcnow()
                self.files.insert_one(file_data)
            return True
        except Exception as e:
            logger.error(f"Save file error: {e}")
            self.log_error('save_file', str(e), file_data)
            return False
    
    def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        if not self.db or not self.files:
            return None
        try:
            return self.files.find_one({'file_id': file_id})
        except Exception as e:
            logger.error(f"Get file error: {e}")
            return None
    
    def search_files(self, query: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        if not self.db or not self.files:
            return []
        try:
            # Search by text index or regex
            search_query = {
                '$or': [
                    {'search_text': {'$regex': query.lower(), '$options': 'i'}},
                    {'file_name': {'$regex': query, '$options': 'i'}},
                    {'tags': {'$regex': query, '$options': 'i'}},
                    {'caption': {'$regex': query, '$options': 'i'}}
                ],
                'is_active': True
            }
            cursor = self.files.find(search_query).sort('created_at', -1).skip(offset).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def search_by_file_name(self, file_name: str) -> List[Dict]:
        """Search files by exact file name pattern"""
        if not self.db or not self.files:
            return []
        try:
            # Use regex for flexible matching
            pattern = file_name.replace('.', '\\.')
            cursor = self.files.find({
                'file_name': {'$regex': pattern, '$options': 'i'},
                'is_active': True
            }).sort('created_at', -1)
            return list(cursor)
        except Exception as e:
            logger.error(f"Search by file name error: {e}")
            return []
    
    def get_files_by_quality(self, quality: str, limit: int = 50) -> List[Dict]:
        if not self.db or not self.files:
            return []
        try:
            cursor = self.files.find({
                'quality': {'$regex': quality, '$options': 'i'},
                'is_active': True
            }).sort('created_at', -1).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Get by quality error: {e}")
            return []
    
    def get_file_by_name_exact(self, file_name: str) -> Optional[Dict]:
        """Get file by exact file name"""
        if not self.db or not self.files:
            return None
        try:
            return self.files.find_one({'file_name': file_name, 'is_active': True})
        except Exception as e:
            logger.error(f"Get by name error: {e}")
            return None
    
    def update_file_stats(self, file_id: str, action: str):
        if not self.db or not self.files:
            return
        field = 'download_count' if action == 'download' else 'watch_count'
        try:
            self.files.update_one(
                {'file_id': file_id},
                {'$inc': {field: 1}}
            )
        except Exception as e:
            logger.error(f"Update stats error: {e}")
    
    # ---- USER OPERATIONS ----
    
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
        except Exception as e:
            logger.error(f"Save user error: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        if not self.db or not self.users:
            return None
        try:
            return self.users.find_one({'user_id': user_id})
        except Exception as e:
            logger.error(f"Get user error: {e}")
            return None
    
    # ---- DOWNLOAD TOKENS ----
    
    def create_download_request(self, file_id: str, user_id: int, ip: str = None) -> str:
        if not self.db or not self.downloads:
            return ""
        try:
            token = hashlib.md5(f"{file_id}{user_id}{datetime.utcnow()}{os.urandom(8)}".encode()).hexdigest()
            
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
        except Exception as e:
            logger.error(f"Create download request error: {e}")
            return ""
    
    def validate_download_token(self, token: str) -> Optional[Dict]:
        if not self.db or not self.downloads:
            return None
        try:
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
        except Exception as e:
            logger.error(f"Validate token error: {e}")
            return None
    
    # ---- ERROR LOGGING ----
    
    def log_error(self, error_type: str, message: str, details: Dict = None):
        if not self.db or not self.errors:
            return
        try:
            self.errors.insert_one({
                'type': error_type,
                'message': message,
                'details': details or {},
                'created_at': datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Log error failed: {e}")
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        if not self.db or not self.errors:
            return []
        try:
            cursor = self.errors.find().sort('created_at', -1).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Get errors error: {e}")
            return []
    
    # ---- STATISTICS ----
    
    def get_stats(self) -> Dict:
        if not self.db:
            return {
                'total_files': 0,
                'total_users': 0,
                'total_downloads': 0,
                'total_views': 0,
                'total_channels': 0,
                'file_types': [],
                'quality_distribution': []
            }
        try:
            stats = {
                'total_files': self.files.count_documents({'is_active': True}) if self.files else 0,
                'total_users': self.users.count_documents({}) if self.users else 0,
                'total_downloads': 0,
                'total_views': 0,
                'total_channels': self.settings.count_documents({'type': 'channel'}) if self.settings else 0,
                'file_types': [],
                'quality_distribution': []
            }
            
            if self.files:
                # Get downloads count
                pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$download_count'}}}]
                result = list(self.files.aggregate(pipeline))
                if result:
                    stats['total_downloads'] = result[0]['total']
                
                # Get views count
                pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$watch_count'}}}]
                result = list(self.files.aggregate(pipeline))
                if result:
                    stats['total_views'] = result[0]['total']
                
                # File types distribution
                pipeline = [{'$group': {'_id': '$file_format', 'count': {'$sum': 1}}}]
                stats['file_types'] = list(self.files.aggregate(pipeline))
                
                # Quality distribution
                pipeline = [{'$group': {'_id': '$quality', 'count': {'$sum': 1}}}]
                stats['quality_distribution'] = list(self.files.aggregate(pipeline))
            
            return stats
        except Exception as e:
            logger.error(f"Get stats error: {e}")
            return {'total_files': 0, 'total_users': 0, 'total_downloads': 0, 'total_views': 0}

# Singleton
db = Database()
