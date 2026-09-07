#!/usr/bin/env python3
"""
FastAPI Server for Telegram Media Bot
Provides REST API for external websites to access media files
"""

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import uvicorn
import asyncio
import json
from datetime import datetime, timedelta
import hashlib
import hmac
import aiohttp
import os
from urllib.parse import quote

from config import Config
from database import db
from utils import format_file_size, get_streaming_url

# Initialize FastAPI
app = FastAPI(
    title="Telegram Media API",
    description="API for accessing media files from Telegram channels",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- MODELS ----

class FileResponseModel(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    file_size_human: str
    format: str
    quality: Optional[str]
    resolution: Optional[str]
    download_count: int
    watch_count: int
    channel_title: str
    created_at: str
    tags: List[str]
    download_link: Optional[str]
    watch_link: Optional[str]

class SearchResponseModel(BaseModel):
    total: int
    files: List[FileResponseModel]

class DownloadRequestModel(BaseModel):
    file_id: str
    user_id: Optional[int] = None
    ip_address: Optional[str] = None

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None

# ---- AUTHENTICATION ----

def verify_api_key(api_key: str = Header(...)):
    """Verify API key for secure endpoints"""
    if api_key != Config.API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

async def verify_token(token: str):
    """Verify download/stream token"""
    request = db.validate_download_token(token)
    if not request:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    return request

# ---- API ENDPOINTS ----

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Telegram Media API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "search": "/api/v1/search?q=query",
            "file": "/api/v1/file/{file_id}",
            "download": "/api/v1/download/{token}",
            "watch": "/api/v1/watch/{token}",
            "stats": "/api/v1/stats",
            "recent": "/api/v1/recent",
            "by_quality": "/api/v1/quality/{quality}",
            "by_channel": "/api/v1/channel/{channel_id}",
            "similar": "/api/v1/similar/{file_id}"
        }
    }

@app.get("/api/v1/search", response_model=SearchResponseModel)
async def search_files(q: str, limit: int = 20, offset: int = 0, api_key: str = Depends(verify_api_key)):
    """
    Search files by name, tags, or caption
    """
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    results = db.search_files(q)
    
    # Apply pagination
    total = len(results)
    paginated = results[offset:offset + limit]
    
    files = []
    for file in paginated:
        files.append(FileResponseModel(
            file_id=file['file_id'],
            file_name=file['file_name'],
            file_size=file['file_size'],
            file_size_human=format_file_size(file['file_size']),
            format=file.get('file_format', 'Unknown'),
            quality=file.get('quality'),
            resolution=file.get('resolution'),
            download_count=file.get('download_count', 0),
            watch_count=file.get('watch_count', 0),
            channel_title=file.get('channel_title', 'Unknown'),
            created_at=file['created_at'].isoformat() if file.get('created_at') else '',
            tags=file.get('tags', []),
            download_link=f"/api/v1/create_download/{file['file_id']}",
            watch_link=f"/api/v1/create_watch/{file['file_id']}"
        ))
    
    return SearchResponseModel(total=total, files=files)

@app.get("/api/v1/file/{file_id}")
async def get_file(file_id: str, api_key: str = Depends(verify_api_key)):
    """
    Get detailed information about a specific file
    """
    file = db.get_file_by_id(file_id)
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Generate temporary download/stream links
    download_token = db.create_download_request(file_id, 0, "api_request")
    watch_token = db.create_download_request(file_id, 0, "api_request")
    
    return {
        "success": True,
        "data": {
            "file_id": file['file_id'],
            "file_name": file['file_name'],
            "file_size": file['file_size'],
            "file_size_human": format_file_size(file['file_size']),
            "format": file.get('file_format', 'Unknown'),
            "quality": file.get('quality'),
            "resolution": file.get('resolution'),
            "duration": file.get('duration'),
            "channel": {
                "id": file.get('channel_id'),
                "title": file.get('channel_title')
            },
            "message_id": file.get('message_id'),
            "caption": file.get('caption'),
            "download_count": file.get('download_count', 0),
            "watch_count": file.get('watch_count', 0),
            "tags": file.get('tags', []),
            "created_at": file['created_at'].isoformat(),
            "download_link": f"/api/v1/download/{download_token}",
            "watch_link": f"/api/v1/watch/{watch_token}"
        }
    }

@app.get("/api/v1/recent", response_model=SearchResponseModel)
async def get_recent(limit: int = 20, api_key: str = Depends(verify_api_key)):
    """
    Get most recent files
    """
    files_cursor = db.files.find({'is_active': True}).sort('created_at', -1).limit(limit)
    files = list(files_cursor)
    
    response_files = []
    for file in files:
        response_files.append(FileResponseModel(
            file_id=file['file_id'],
            file_name=file['file_name'],
            file_size=file['file_size'],
            file_size_human=format_file_size(file['file_size']),
            format=file.get('file_format', 'Unknown'),
            quality=file.get('quality'),
            resolution=file.get('resolution'),
            download_count=file.get('download_count', 0),
            watch_count=file.get('watch_count', 0),
            channel_title=file.get('channel_title', 'Unknown'),
            created_at=file['created_at'].isoformat() if file.get('created_at') else '',
            tags=file.get('tags', []),
            download_link=f"/api/v1/create_download/{file['file_id']}",
            watch_link=f"/api/v1/create_watch/{file['file_id']}"
        ))
    
    return SearchResponseModel(total=len(response_files), files=response_files)

@app.get("/api/v1/quality/{quality}")
async def get_by_quality(quality: str, limit: int = 50, api_key: str = Depends(verify_api_key)):
    """
    Get files by quality (480p, 720p, 1080p, 2160p)
    """
    files = list(db.files.find({
        'quality': {'$regex': quality, '$options': 'i'},
        'is_active': True
    }).sort('created_at', -1).limit(limit))
    
    return {
        "success": True,
        "total": len(files),
        "files": [{
            "file_id": f['file_id'],
            "file_name": f['file_name'],
            "file_size_human": format_file_size(f['file_size']),
            "quality": f.get('quality'),
            "channel": f.get('channel_title')
        } for f in files]
    }

@app.get("/api/v1/channel/{channel_id}")
async def get_by_channel(channel_id: int, limit: int = 50, api_key: str = Depends(verify_api_key)):
    """
    Get all files from a specific channel
    """
    files = db.get_files_by_channel(channel_id, limit)
    
    return {
        "success": True,
        "total": len(files),
        "files": [{
            "file_id": f['file_id'],
            "file_name": f['file_name'],
            "file_size_human": format_file_size(f['file_size']),
            "quality": f.get('quality'),
            "created_at": f['created_at'].isoformat()
        } for f in files]
    }

@app.get("/api/v1/create_download/{file_id}")
async def create_download_link(file_id: str, user_id: Optional[int] = 0, api_key: str = Depends(verify_api_key)):
    """
    Create a download token for a file
    """
    file = db.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    token = db.create_download_request(file_id, user_id, "api")
    return {
        "success": True,
        "token": token,
        "download_link": f"/api/v1/download/{token}",
        "expires_in": "24 hours"
    }

@app.get("/api/v1/create_watch/{file_id}")
async def create_watch_link(file_id: str, user_id: Optional[int] = 0, api_key: str = Depends(verify_api_key)):
    """
    Create a watch/stream token for a file
    """
    file = db.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check if it's a video file
    if not any(file['file_name'].lower().endswith(ext) for ext in Config.VIDEO_FORMATS):
        raise HTTPException(status_code=400, detail="Not a video file")
    
    token = db.create_download_request(file_id, user_id, "api")
    return {
        "success": True,
        "token": token,
        "watch_link": f"/api/v1/watch/{token}",
        "expires_in": "24 hours"
    }

@app.get("/api/v1/download/{token}")
async def download_file(token: str, request: Request):
    """
    Download a file using token
    """
    # Validate token
    req = await verify_token(token)
    file = db.get_file_by_id(req['file_id'])
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Update download count
    db.update_file_stats(file['file_id'], 'download')
    
    # Get file from Telegram
    try:
        # Using python-telegram-bot to get file
        # You need to have bot instance or use aiohttp
        file_url = await get_telegram_file_url(file['file_id'])
        
        # Redirect to Telegram's CDN for fast download
        return RedirectResponse(url=file_url)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching file: {str(e)}")

@app.get("/api/v1/watch/{token}")
async def watch_file(token: str, request: Request):
    """
    Stream a video file using token
    """
    # Validate token
    req = await verify_token(token)
    file = db.get_file_by_id(req['file_id'])
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Update watch count
    db.update_file_stats(file['file_id'], 'watch')
    
    try:
        # Get file URL from Telegram
        file_url = await get_telegram_file_url(file['file_id'])
        
        # For streaming, create an HTML page with video player
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Watch {file['file_name']}</title>
            <style>
                body {{ margin: 0; background: #000; display: flex; justify-content: center; align-items: center; height: 100vh; }}
                video {{ max-width: 100%; max-height: 100vh; }}
            </style>
        </head>
        <body>
            <video controls autoplay>
                <source src="{file_url}" type="{file.get('mime_type', 'video/mp4')}">
                Your browser does not support the video tag.
            </video>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error streaming file: {str(e)}")

@app.get("/api/v1/stats")
async def get_stats(api_key: str = Depends(verify_api_key)):
    """
    Get overall bot statistics
    """
    stats = db.get_stats()
    return {
        "success": True,
        "stats": stats
    }

@app.get("/api/v1/similar/{file_id}")
async def get_similar_files(file_id: str, limit: int = 10, api_key: str = Depends(verify_api_key)):
    """
    Find similar files based on name pattern
    """
    file = db.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Extract base name (without quality and extension)
    base_name = file['file_name'].split('.')
    if len(base_name) > 1:
        # Remove extension
        base_name = '.'.join(base_name[:-1])
        # Remove quality indicators
        for quality in ['2160p', '1080p', '720p', '480p', '4K', 'HD']:
            base_name = base_name.replace(quality, '')
        base_name = base_name.strip('.')
    else:
        base_name = file['file_name']
    
    # Search for similar files
    similar = db.search_files(base_name)
    
    # Filter out the original file
    similar = [f for f in similar if f['file_id'] != file_id]
    
    return {
        "success": True,
        "base_file": file['file_name'],
        "similar_count": len(similar),
        "files": [{
            "file_id": f['file_id'],
            "file_name": f['file_name'],
            "quality": f.get('quality'),
            "size": format_file_size(f['file_size'])
        } for f in similar[:limit]]
    }

@app.get("/api/v1/health")
async def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db.client else "disconnected"
    }

# ---- HELPER FUNCTIONS ----

async def get_telegram_file_url(file_id: str) -> str:
    """
    Get file URL from Telegram API
    """
    # This uses the bot to get the file path
    # You'll need to implement this based on your bot instance
    
    # For now, using direct approach
    # You can also store file URLs in database when first indexing
    bot = None  # You need to pass your bot instance
    
    try:
        # Using python-telegram-bot
        from telegram import Bot
        bot = Bot(token=Config.BOT_TOKEN)
        file = await bot.get_file(file_id)
        return file.file_path
    except Exception as e:
        raise Exception(f"Failed to get file URL: {e}")

# ---- RUN SERVER ----

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=Config.API_PORT,
        reload=True
    )
