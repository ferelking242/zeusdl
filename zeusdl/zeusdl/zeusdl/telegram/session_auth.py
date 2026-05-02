"""
Telegram session-string authentication for ZeusDL.

A Telethon StringSession encodes the full authentication state in a
single base64-like string — no database, no extra files.

How to generate one (one-time, outside Zeus):

    pip install telethon
    python3 - << 'EOF'
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    api_id   = int(input("api_id: "))
    api_hash = input("api_hash: ")
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("Session string:", client.session.save())
    EOF

Then pass the printed string to Zeus:
    zeusdl telegram start --session-string "…" --api-id … --api-hash …

Or store it in the Zeus config:
    zeusdl telegram save-session --session-string "…" --api-id … --api-hash …
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Optional

_SESSION_PATH = Path(os.path.expanduser('~')) / '.config' / 'zeusdl' / 'telegram_session.json'
_telethon_available = False

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    _telethon_available = True
except ImportError:
    pass


def _require_telethon():
    if not _telethon_available:
        print(
            '[ZeusDL Telegram] Telethon is not installed.\n'
            'Install it with:  pip install telethon\n'
            'Or add the optional dep:  pip install "zeusdl[telegram]"',
            file=sys.stderr,
        )
        sys.exit(1)


# ── Storage ──────────────────────────────────────────────────────────────────

def save_session(session_string: str, api_id: int, api_hash: str) -> None:
    """Persist the session string to disk (chmod 600)."""
    _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {'session_string': session_string, 'api_id': api_id, 'api_hash': api_hash}
    _SESSION_PATH.write_text(json.dumps(data, indent=2))
    _SESSION_PATH.chmod(0o600)
    print(f'[ZeusDL Telegram] Session saved to {_SESSION_PATH}')


def get_session() -> Optional[dict]:
    """Load stored session from disk, or None if not saved."""
    if not _SESSION_PATH.exists():
        return None
    try:
        return json.loads(_SESSION_PATH.read_text())
    except Exception:
        return None


# ── Main TelegramSession class ────────────────────────────────────────────────

class TelegramSession:
    """
    Wraps a Telethon client authenticated via a StringSession.

    Usage
    -----
        ts = TelegramSession(session_string="…", api_id=123, api_hash="abc")
        ts.start()
        me = ts.client.get_me()
        print(me.username)
        ts.stop()

    Or as a context manager:
        with TelegramSession.from_config() as ts:
            me = ts.client.get_me()
    """

    def __init__(self, session_string: str, api_id: int, api_hash: str):
        _require_telethon()
        self._session_string = session_string
        self._api_id = int(api_id)
        self._api_hash = api_hash
        self.client: Optional['TelegramClient'] = None
        self._loop = None

    @classmethod
    def from_config(cls) -> 'TelegramSession':
        """Load credentials from saved config and return a TelegramSession."""
        cfg = get_session()
        if not cfg:
            raise RuntimeError(
                'No Telegram session found. Run:\n'
                '  zeusdl telegram save-session --session-string "…" --api-id … --api-hash …'
            )
        return cls(
            session_string=cfg['session_string'],
            api_id=cfg['api_id'],
            api_hash=cfg['api_hash'],
        )

    @classmethod
    def from_string(cls, session_string: str, api_id: int, api_hash: str) -> 'TelegramSession':
        return cls(session_string, api_id, api_hash)

    def start(self) -> 'TelegramSession':
        """Connect and authenticate. Returns self for chaining."""
        _require_telethon()
        from telethon.sessions import StringSession
        self.client = TelegramClient(
            StringSession(self._session_string),
            self._api_id,
            self._api_hash,
        )
        self.client.start()
        me = self.client.get_me()
        name = getattr(me, 'username', None) or getattr(me, 'first_name', '?')
        print(f'[ZeusDL Telegram] Authenticated as @{name}')
        return self

    def stop(self):
        if self.client:
            self.client.disconnect()
            self.client = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()

    # ── Remote control ────────────────────────────────────────────────────────

    def run_bot(self, on_command=None):
        """
        Listen for messages in Saved Messages (self-chat) and execute
        download commands.

        on_command(cmd: str, args: str) → called for each command.
        Default handler prints commands and ignores them.
        """
        _require_telethon()
        from telethon import events

        if self.client is None:
            self.start()

        print('[ZeusDL Telegram] Listening for commands in Saved Messages…')
        print('[ZeusDL Telegram] Send commands to yourself (Saved Messages):')
        print('    download <URL>')
        print('    status')
        print('    list')
        print('    stop')

        @self.client.on(events.NewMessage(outgoing=True, from_users='me'))
        async def _handler(event):
            text = event.raw_text.strip()
            if not text:
                return

            parts = text.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ''

            if cmd == 'stop':
                await event.reply('ZeusDL stopping…')
                self.client.disconnect()
                return

            if on_command:
                try:
                    result = on_command(cmd, args)
                    if result:
                        await event.reply(str(result)[:4000])
                except Exception as e:
                    await event.reply(f'Error: {e}')
            else:
                await event.reply(f'Received: {cmd} {args}')

        self.client.run_until_disconnected()


# ── One-time session generation helper ───────────────────────────────────────

def generate_session_interactive():
    """
    Interactive helper to generate a Telethon session string.
    Requires telethon to be installed.
    """
    _require_telethon()
    from telethon.sessions import StringSession

    print('=== ZeusDL Telegram — Session Generator ===')
    print('Get your API credentials at https://my.telegram.org/auth\n')
    api_id = int(input('api_id   : '))
    api_hash = input('api_hash : ').strip()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    print('\n✅ Session string (save this — you won\'t see it again):')
    print(session_string)
    print()

    save = input('Save to ~/.config/zeusdl/telegram_session.json? [Y/n] ').strip().lower()
    if save in ('', 'y', 'yes'):
        save_session(session_string, api_id, api_hash)

    return session_string
