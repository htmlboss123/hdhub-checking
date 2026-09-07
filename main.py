#!/usr/bin/env python3
"""
Telegram Media Bot - Main Entry Point
This file is the single entry point for both API and Bot
"""

import os
import sys
import logging
import asyncio
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI imports
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Create FastAPI app
app = FastAPI(
    title="Telegram Media Bot API",
    description="API for serving Telegram media files",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/")
@app.get("/health")
async def health_check():
    """Health check endpoint for Koyeb"""
    return {
        "status": "healthy",
        "service": "Telegram Media Bot",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version
    }

@app.get("/api/v1/status")
async def api_status():
    """API status endpoint"""
    return {
        "status": "running",
        "message": "API is operational",
        "endpoints": [
            "/",
            "/health",
            "/api/v1/status"
        ]
    }

# Import bot only when needed (lazy import)
def get_bot_application():
    """Lazy import bot to avoid startup issues"""
    try:
        # Check if app is a package
        import app
        from app.bot import main as bot_main
        return bot_main
    except ImportError as e:
        logger.warning(f"Bot module not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to import bot: {e}")
        return None

# Run bot in background if needed
async def start_bot():
    """Start the Telegram bot in background"""
    try:
        from app.bot import main as bot_main
        logger.info("Starting Telegram Bot...")
        await bot_main()
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

# For uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
