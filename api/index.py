import sys
import os

# Add sop-chat to path so we can import its modules
sop_chat_dir = os.path.join(os.path.dirname(__file__), '..', 'sop-chat')
sys.path.insert(0, sop_chat_dir)

# Change working directory to sop-chat so relative paths (../images, ../sop-files) work
os.chdir(sop_chat_dir)

# Import the FastAPI app from sop-chat/web.py
from web import app

# Vercel uses this 'app' variable as the ASGI handler
