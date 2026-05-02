"""
ZeusDL Telegram integration.

Provides two sub-features:

1. Session-string authentication
   ─────────────────────────────
   Zeus accepts a Telethon session string and uses it to connect to
   Telegram as the user.  No phone number / OTP required at runtime.

   Generate a session string once (outside Zeus):
       python3 -m zeusdl.telegram generate

2. Remote control via Telegram
   ────────────────────────────
   Once authenticated Zeus listens for messages in a special private
   conversation (with itself / Saved Messages) and executes download
   commands:

       download https://site-ma.bangbros.com/scenes?addon=5971
       status
       list

Usage
─────
   zeusdl telegram start --session-string "…"
   zeusdl telegram generate            # interactive one-time setup
"""

from .session_auth import TelegramSession, get_session, save_session

__all__ = ['TelegramSession', 'get_session', 'save_session']
