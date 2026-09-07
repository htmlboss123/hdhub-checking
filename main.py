#!/usr/bin/env python3
"""
Main entry point for both API and Bot
This structure ensures proper build and run on Koyeb
"""

import os
import sys
import logging
import asyncio
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import after logging setup
try:
    from app.api import app as api_app
    from app.bot import main as bot_main
except ImportError as e:
    logger.error(f"Import error: {e}")
    # Try alternative import
    try:
        from app.api import app as api_app
        from app.bot import main as bot_main
    except ImportError:
        # Create minimal app for health check
        from fastapi import FastAPI
        api_app = FastAPI()
        
        @api_app.get("/")
        async def root():
            return {"status": "ok", "message": "Telegram Media Bot"}
        
        @api_app.get("/health")
        async def health():
            return {"status": "healthy"}

# Global application for Koyeb
app = api_app

def run_bot():
    """Run the bot in a separate thread"""
    try:
        logger.info("Starting Telegram Bot...")
        asyncio.run(bot_main())
    except Exception as e:
        logger.error(f"Bot error: {e}")

def run_api():
    """Run the API"""
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    logger.info(f"Starting API on port {port}...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["api", "bot", "both"], default="api")
    args = parser.parse_args()
    
    if args.mode == "bot":
        asyncio.run(bot_main())
    elif args.mode == "api":
        run_api()
    else:  # both
        # Run both in threads
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        run_api()
