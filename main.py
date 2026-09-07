#!/usr/bin/env python3
"""
Main Entry Point for Telegram Media Bot
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

# FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
app = FastAPI(
    title="Telegram Media Bot API",
    description="Complete API for Telegram media files",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import API routes
try:
    from app.api import app as api_app
    # Merge routes
    app.router.routes.extend(api_app.router.routes)
except Exception as e:
    logger.error(f"Failed to import API: {e}")

# Health check
@app.get("/")
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Telegram Media Bot",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

# Run bot
async def run_bot():
    try:
        from app.bot import main as bot_main
        await bot_main()
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Start bot in background
    if os.getenv("RUN_BOT", "true").lower() == "true":
        import threading
        thread = threading.Thread(target=lambda: asyncio.run(run_bot()))
        thread.daemon = True
        thread.start()
        logger.info("Bot started in background thread")
    
    # Start API
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
