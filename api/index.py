import sys
import os

# Add project root to path so 'web', 'models', 'generators', 'data' are importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from web.app import app  # noqa: F401 — Vercel picks up 'app' as the WSGI handler
