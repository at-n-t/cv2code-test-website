import sys
import os

# Add project root to path so 'web' package imports correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app  # noqa: F401  — Vercel picks up 'app' as the WSGI handler
