"""
ZeusDL Telegram Bot — per-user bot client.

Each user provides their own Telegram bot token (created via @BotFather).
Zeus does NOT use a centralised bot — the token is yours and stays local.

Features
────────
• Upload video files to a Telegram channel or chat
• Send progress notifications
• Accept remote download commands via the bot
• Works with any Telegram channel/group the bot is an admin of

Setup
─────
1. Create a bot: talk to @BotFather on Telegram → /newbot
2. Copy the bot token (looks like 123456789:ABCdef…)
3. Add the bot as admin to your channel/group
4. Use the token in your .zeus script or CLI:

   push telegram
       token  123456789:ABCdef…
       channel  -1001234567890

CLI usage
─────────
   zeusdl telebot --token TOKEN --channel CHANNEL_ID upload ./downloads
   zeusdl telebot --token TOKEN start          # start command listener
"""

from .uploader import TelegramUploader
from .bot import ZeusBot

__all__ = ['TelegramUploader', 'ZeusBot']
