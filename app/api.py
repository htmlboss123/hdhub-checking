#!/usr/bin/env python3
"""
Complete REST API with file name search, download, and watch links
"""

import os
import sys
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import uvicorn

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config, logger
from app.database import db
from app.utils import format_file_size, get_telegram_file_url

# Initialize FastAPI
app = FastAPI(
    title="Telegram Media API",
    description="Complete API for Telegram media files",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- MODELS ----

class FileResponse(BaseModel):
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
    download_link: Optional[str] = None
    watch_link: Optional[str] = None

class SearchResponse(BaseModel):
    success: bool
    total: int
    files: List[FileResponse]
    message: Optional[str] = None

class DownloadResponse(BaseModel):
    success: bool
    token: str
    file_name: str
    download_link: str
    expires_in: str
    message: Optional[str] = None

class WatchResponse(BaseModel):
    success: bool
    token: str
    file_name: str
    watch_link: str
    expires_in: str
    message: Optional[str] = None

# ---- AUTHENTICATION ----

def verify_api_key(api_key: str = Header(None)):
    """Verify API key"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if api_key != Config.API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# ---- ROOT ENDPOINTS ----

@app.get("/")
@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Telegram Media API",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db.db else "disconnected"
    }

@app.get("/api/v1/")
async def api_root():
    """API Root"""
    return {
        "name": "Telegram Media API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "search": "/api/v1/search?q=filename",
            "search_by_name": "/api/v1/search/name?file_name=Satluj.2026.2160p",
            "file": "/api/v1/file/{file_id}",
            "download": "/api/v1/download/{token}",
            "watch": "/api/v1/watch/{token}",
            "quality": "/api/v1/quality/{quality}",
            "stats": "/api/v1/stats",
            "recent": "/api/v1/recent",
            "similar": "/api/v1/similar/{file_id}"
        }
    }

# ---- SEARCH ENDPOINTS ----

@app.get("/api/v1/search", response_model=SearchResponse)
async def search_files(q: str, limit: int = 20, offset: int = 0, api_key: str = Depends(verify_api_key)):
    """
    Search files by name, tags, or caption
    """
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    try:
        results = db.search_files(q, limit, offset)
        
        files = []
        for file in results:
            # Generate download and watch links
            download_token = db.create_download_request(file['file_id'], 0, "api")
            watch_token = db.create_download_request(file['file_id'], 0, "api")
            
            files.append(FileResponse(
                file_id=file['file_id'],
                file_name=file.get('file_name', 'Unknown'),
                file_size=file.get('file_size', 0),
                file_size_human=format_file_size(file.get('file_size', 0)),
                format=file.get('file_format', 'Unknown'),
                quality=file.get('quality'),
                resolution=file.get('resolution'),
                download_count=file.get('download_count', 0),
                watch_count=file.get('watch_count', 0),
                channel_title=file.get('channel_title', 'Unknown'),
                created_at=file.get('created_at', datetime.utcnow()).isoformat(),
                tags=file.get('tags', []),
                download_link=f"/api/v1/download/{download_token}" if download_token else None,
                watch_link=f"/api/v1/watch/{watch_token}" if watch_token else None
            ))
        
        return SearchResponse(
            success=True,
            total=len(results),
            files=files
        )
    except Exception as e:
        logger.error(f"Search API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/search/name", response_model=SearchResponse)
async def search_by_file_name(file_name: str, api_key: str = Depends(verify_api_key)):
    """
    Search files by exact file name pattern
    Example: /api/v1/search/name?file_name=Satluj.2026.2160p
    """
    if not file_name or len(file_name) < 2:
        raise HTTPException(status_code=400, detail="File name must be at least 2 characters")
    
    try:
        # Search by file name pattern
        results = db.search_by_file_name(file_name)
        
        if not results:
            return SearchResponse(
                success=True,
                total=0,
                files=[],
                message="No files found"
            )
        
        files = []
        for file in results:
            download_token = db.create_download_request(file['file_id'], 0, "api")
            watch_token = db.create_download_request(file['file_id'], 0, "api")
            
            files.append(FileResponse(
                file_id=file['file_id'],
                file_name=file.get('file_name', 'Unknown'),
                file_size=file.get('file_size', 0),
                file_size_human=format_file_size(file.get('file_size', 0)),
                format=file.get('file_format', 'Unknown'),
                quality=file.get('quality'),
                resolution=file.get('resolution'),
                download_count=file.get('download_count', 0),
                watch_count=file.get('watch_count', 0),
                channel_title=file.get('channel_title', 'Unknown'),
                created_at=file.get('created_at', datetime.utcnow()).isoformat(),
                tags=file.get('tags', []),
                download_link=f"/api/v1/download/{download_token}" if download_token else None,
                watch_link=f"/api/v1/watch/{watch_token}" if watch_token else None
            ))
        
        return SearchResponse(
            success=True,
            total=len(files),
            files=files,
            message=f"Found {len(files)} files matching pattern"
        )
    except Exception as e:
        logger.error(f"Search by name API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---- FILE ENDPOINTS ----

@app.get("/api/v1/file/{file_id}")
async def get_file(file_id: str, api_key: str = Depends(verify_api_key)):
    """Get file details by ID"""
    try:
        file = db.get_file_by_id(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        download_token = db.create_download_request(file_id, 0, "api")
        watch_token = db.create_download_request(file_id, 0, "api")
        
        return {
            "success": True,
            "data": {
                "file_id": file['file_id'],
                "file_name": file.get('file_name'),
                "file_size": file.get('file_size'),
                "file_size_human": format_file_size(file.get('file_size', 0)),
                "format": file.get('file_format'),
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
                "created_at": file.get('created_at', datetime.utcnow()).isoformat(),
                "download_link": f"/api/v1/download/{download_token}" if download_token else None,
                "watch_link": f"/api/v1/watch/{watch_token}" if watch_token else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get file API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---- DOWNLOAD & WATCH ENDPOINTS ----

@app.get("/api/v1/download/create/{file_id}")
async def create_download_link(file_id: str, user_id: Optional[int] = 0, api_key: str = Depends(verify_api_key)):
    """Create download link for a file"""
    try:
        file = db.get_file_by_id(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        token = db.create_download_request(file_id, user_id, "api")
        if not token:
            raise HTTPException(status_code=500, detail="Failed to create download request")
        
        return DownloadResponse(
            success=True,
            token=token,
            file_name=file.get('file_name', 'Unknown'),
            download_link=f"/api/v1/download/{token}",
            expires_in="24 hours"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create download link error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/download/{token}")
async def download_file(token: str, request: Request):
    """Download file using token"""
    try:
        # Validate token
        req = db.validate_download_token(token)
        if not req:
            raise HTTPException(status_code=404, detail="Invalid or expired token")
        
        file = db.get_file_by_id(req['file_id'])
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Update download count
        db.update_file_stats(file['file_id'], 'download')
        
        # Get file URL from Telegram
        try:
            file_url = await get_telegram_file_url(file['file_id'])
            return RedirectResponse(url=file_url)
        except Exception as e:
            logger.error(f"File URL error: {e}")
            raise HTTPException(status_code=500, detail="Failed to get file URL")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/watch/create/{file_id}")
async def create_watch_link(file_id: str, user_id: Optional[int] = 0, api_key: str = Depends(verify_api_key)):
    """Create watch/stream link for a file"""
    try:
        file = db.get_file_by_id(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if video
        if not any(file['file_name'].lower().endswith(ext) for ext in Config.VIDEO_FORMATS):
            raise HTTPException(status_code=400, detail="Not a video file")
        
        token = db.create_download_request(file_id, user_id, "api")
        if not token:
            raise HTTPException(status_code=500, detail="Failed to create watch request")
        
        return WatchResponse(
            success=True,
            token=token,
            file_name=file.get('file_name', 'Unknown'),
            watch_link=f"/api/v1/watch/{token}",
            expires_in="24 hours"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create watch link error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/watch/{token}")
async def watch_file(token: str, request: Request):
    """Stream video file using token"""
    try:
        req = db.validate_download_token(token)
        if not req:
            raise HTTPException(status_code=404, detail="Invalid or expired token")
        
        file = db.get_file_by_id(req['file_id'])
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Update watch count
        db.update_file_stats(file['file_id'], 'watch')
        
        # Get file URL
        try:
            file_url = await get_telegram_file_url(file['file_id'])
            
            # Create HTML video player
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Watch {file.get('file_name', 'Video')}</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {{ margin: 0; padding: 0; }}
                    body {{ background: #000; display: flex; justify-content: center; align-items: center; height: 100vh; }}
                    video {{ max-width: 100%; max-height: 100vh; background: #000; }}
                    .info {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); color: #fff; background: rgba(0,0,0,0.7); padding: 10px 20px; border-radius: 10px; font-family: Arial; font-size: 14px; z-index: 10; }}
                </style>
            </head>
            <body>
                <video controls autoplay playsinline>
                    <source src="{file_url}" type="{file.get('mime_type', 'video/mp4')}">
                    Your browser does not support the video tag.
                </video>
                <div class="info">📺 {file.get('file_name', 'Video')}</div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
            
        except Exception as e:
            logger.error(f"Watch error: {e}")
            raise HTTPException(status_code=500, detail="Failed to stream video")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Watch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---- OTHER ENDPOINTS ----

@app.get("/api/v1/quality/{quality}")
async def get_by_quality(quality: str, limit: int = 50, api_key: str = Depends(verify_api_key)):
    """Get files by quality"""
    try:
        files = db.get_files_by_quality(quality, limit)
        
        return {
            "success": True,
            "total": len(files),
            "quality": quality,
            "files": [{
                "file_id": f['file_id'],
                "file_name": f.get('file_name'),
                "file_size_human": format_file_size(f.get('file_size', 0)),
                "quality": f.get('quality'),
                "channel": f.get('channel_title'),
                "download_link": f"/api/v1/download/create/{f['file_id']}",
                "watch_link": f"/api/v1/watch/create/{f['file_id']}"
            } for f in files]
        }
    except Exception as e:
        logger.error(f"Quality API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/recent")
async def get_recent(limit: int = 20, api_key: str = Depends(verify_api_key)):
    """Get recent files"""
    try:
        files = db.search_files('', limit, 0)
        
        return {
            "success": True,
            "total": len(files),
            "files": [{
                "file_id": f['file_id'],
                "file_name": f.get('file_name'),
                "file_size_human": format_file_size(f.get('file_size', 0)),
                "quality": f.get('quality'),
                "created_at": f.get('created_at', datetime.utcnow()).isoformat(),
                "download_link": f"/api/v1/download/create/{f['file_id']}",
                "watch_link": f"/api/v1/watch/create/{f['file_id']}"
            } for f in files]
        }
    except Exception as e:
        logger.error(f"Recent API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/stats")
async def get_stats(api_key: str = Depends(verify_api_key)):
    """Get statistics"""
    try:
        stats = db.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/similar/{file_id}")
async def get_similar(file_id: str, limit: int = 10, api_key: str = Depends(verify_api_key)):
    """Get similar files"""
    try:
        file = db.get_file_by_id(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Extract base name
        base_name = file.get('file_name', '').split('.')
        if len(base_name) > 1:
            base_name = '.'.join(base_name[:-1])
            for quality in ['2160p', '1080p', '720p', '480p', '4K', 'HD']:
                base_name = base_name.replace(quality, '')
            base_name = base_name.strip('.')
        else:
            base_name = file.get('file_name', '')
        
        similar = db.search_by_file_name(base_name)
        similar = [f for f in similar if f['file_id'] != file_id]
        
        return {
            "success": True,
            "base_file": file.get('file_name'),
            "similar_count": len(similar),
            "files": [{
                "file_id": f['file_id'],
                "file_name": f.get('file_name'),
                "quality": f.get('quality'),
                "size": format_file_size(f.get('file_size', 0)),
                "download_link": f"/api/v1/download/create/{f['file_id']}",
                "watch_link": f"/api/v1/watch/create/{f['file_id']}"
            } for f in similar[:limit]]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similar API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---- ERROR HANDLERS ----

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "status_code": 500
        }
    )

# ---- RUN ----

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=Config.API_PORT,
        reload=False,
        log_level="info"
    )
