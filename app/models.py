from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class MediaFile(BaseModel):
    file_id: str
    file_unique_id: str
    file_name: str
    file_size: int
    file_format: str
    mime_type: str
    quality: Optional[str] = None
    resolution: Optional[str] = None
    duration: Optional[int] = None
    channel_id: int
    channel_title: str
    message_id: int
    caption: Optional[str] = None
    thumbnail_id: Optional[str] = None
    file_url: Optional[str] = None
    download_count: int = 0
    watch_count: int = 0
    is_active: bool = True
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
    tags: List[str] = []

class User(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: str
    last_name: Optional[str]
    is_admin: bool = False
    download_count: int = 0
    watch_count: int = 0
    created_at: datetime = datetime.utcnow()
    last_active: datetime = datetime.utcnow()
