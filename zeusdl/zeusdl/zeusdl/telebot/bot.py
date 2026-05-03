"""
ZeusBot — per-user Telegram bot that accepts download commands.

The user creates their own bot via @BotFather and provides the token.
This is NOT a centralised bot — every user runs their own instance.

Commands understood by the bot (send them in a chat with the bot):
    /download <URL>              — queue a download
    /status                      — show queue status
    /push telegram <channel_id>  — push last output to a Telegram channel
    /push github <repo>          — push last output to GitHub
    /run <script content>        — run a Zeus script inline
    /set <key> <value>           — set a session variable
    /help                        — show help

Usage
─────
    zeusdl telebot --token 123:ABC start

Requires: pip install pyTelegramBotAPI
(Optional — falls back to polling via plain urllib if not installed)
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

_HELP_TEXT = """
🤖 *ZeusDL Bot* — Your personal download assistant

Commands:
  /download <URL> — Download videos from a URL
  /status         — Show current download status
  /set key value  — Set a variable (quality, workers, output, …)
  /run <script>   — Run a Zeus script (inline)
  /push telegram  — Upload last downloads to Telegram
  /push github    — Push last downloads to GitHub
  /help           — Show this help

Examples:
  /download https://site-ma.bangbros.com/scenes?addon=5971
  /set quality 1080p
  /set workers 4
"""


class ZeusBot:
    """
    Lightweight Telegram bot (long-polling) for remote ZeusDL control.

    Each user runs their own bot — no centralised server.

    Parameters
    ----------
    token : str
        Telegram bot token from @BotFather.
    allowed_users : list[int], optional
        Telegram user IDs allowed to send commands.
        If empty, accepts commands from any user (not recommended in production).
    on_command : callable, optional
        ``on_command(cmd: str, args: str, chat_id: int) → str | None``
        Custom command handler. Return a reply string or None.
    """

    def __init__(
        self,
        token: str,
        allowed_users: Optional[list[int]] = None,
        on_command: Optional[Callable] = None,
    ):
        self.token = token
        self.allowed_users = set(allowed_users or [])
        self.on_command = on_command
        self._base = f'https://api.telegram.org/bot{token}'
        self._offset = 0
        self._running = False
        self._vars: dict[str, str] = {}
        self._last_output: Optional[str] = None
        self._jobs: list[dict] = []

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self, poll_interval: float = 1.0) -> None:
        """Start the bot (blocking long-poll loop)."""
        me = self._api('getMe', {})
        name = me.get('result', {}).get('username', '?')
        print(f'[ZeusBot] Started as @{name}')
        print(f'[ZeusBot] Listening for commands…')
        self._running = True
        while self._running:
            try:
                self._poll()
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print('\n[ZeusBot] Stopped.')
                break
            except Exception as e:
                print(f'[ZeusBot] Poll error: {e}', file=sys.stderr)
                time.sleep(5)

    def stop(self) -> None:
        self._running = False

    def send(self, chat_id: int, text: str) -> None:
        """Send a message to a chat."""
        self._api('sendMessage', {
            'chat_id': chat_id,
            'text': text[:4096],
            'parse_mode': 'Markdown',
        })

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        updates = self._api('getUpdates', {
            'offset': self._offset,
            'timeout': 30,
            'allowed_updates': ['message'],
        })
        for update in (updates.get('result') or []):
            self._offset = update['update_id'] + 1
            msg = update.get('message') or {}
            if msg:
                self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        chat_id = msg['chat']['id']
        user_id = msg.get('from', {}).get('id', 0)
        text = (msg.get('text') or '').strip()

        if not text:
            return

        if self.allowed_users and user_id not in self.allowed_users:
            self.send(chat_id, '⛔ Unauthorized.')
            return

        if not text.startswith('/'):
            self.send(chat_id, '❓ Send /help to see available commands.')
            return

        parts = text[1:].split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''

        reply = self._dispatch(cmd, args, chat_id)
        if reply:
            self.send(chat_id, reply)

    def _dispatch(self, cmd: str, args: str, chat_id: int) -> Optional[str]:
        if self.on_command:
            result = self.on_command(cmd, args, chat_id)
            if result is not None:
                return result

        handlers = {
            'help':     lambda: _HELP_TEXT,
            'start':    lambda: _HELP_TEXT,
            'status':   self._cmd_status,
            'set':      lambda: self._cmd_set(args),
            'download': lambda: self._cmd_download(args, chat_id),
            'push':     lambda: self._cmd_push(args, chat_id),
            'run':      lambda: self._cmd_run(args, chat_id),
        }
        handler = handlers.get(cmd)
        if not handler:
            return f'❓ Unknown command /{cmd}. Send /help.'
        return handler()

    # ── Command handlers ──────────────────────────────────────────────────────

    def _cmd_status(self) -> str:
        if not self._jobs:
            return '✅ No active downloads. Queue is empty.'
        lines = ['📋 Download queue:']
        for j in self._jobs[-5:]:
            status = j.get('status', '?')
            url = j.get('url', '?')[:60]
            lines.append(f"  {status} — {url}")
        return '\n'.join(lines)

    def _cmd_set(self, args: str) -> str:
        parts = args.split(None, 1)
        if len(parts) < 2:
            return '❌ Usage: /set key value'
        k, v = parts[0].lower(), parts[1]
        self._vars[k] = v
        return f'✅ Set `{k}` = `{v}`'

    def _cmd_download(self, url: str, chat_id: int) -> str:
        if not url:
            return '❌ Usage: /download <URL>'
        job = {'url': url, 'status': '⏳ queued', 'chat_id': chat_id}
        self._jobs.append(job)

        def _run():
            job['status'] = '⬇️ downloading'
            self.send(chat_id, f'⬇️ Starting download:\n`{url}`')
            try:
                from ..bulk_download import BulkDownloader
                output_dir = self._vars.get('output', './downloads')
                dl = BulkDownloader(
                    output_dir=output_dir,
                    quality=self._vars.get('quality', 'best'),
                    workers=int(self._vars.get('workers', '2')),
                )
                result = dl.run(url)
                job['status'] = '✅ done'
                self._last_output = output_dir
                self.send(chat_id,
                    f'✅ Download complete!\n'
                    f'  {result["ok"]} videos downloaded\n'
                    f'  {result["failed"]} failed\n'
                    f'  Saved to: `{output_dir}`')
            except Exception as e:
                job['status'] = '❌ error'
                self.send(chat_id, f'❌ Download error: {e}')

        threading.Thread(target=_run, daemon=True).start()
        return None  # Reply already sent in thread

    def _cmd_push(self, args: str, chat_id: int) -> str:
        parts = args.split(None, 1)
        target = parts[0].lower() if parts else ''
        rest = parts[1] if len(parts) > 1 else ''

        if target == 'telegram':
            chan = rest or self._vars.get('telegram_channel', '')
            tok = self._vars.get('telegram_token', self.token)
            if not chan:
                return '❌ Usage: /push telegram <channel_id>'
            source = self._last_output or self._vars.get('output', './downloads')
            from .uploader import TelegramUploader
            uploader = TelegramUploader(bot_token=tok, channel=chan)
            result = uploader.upload_directory(source)
            return f'✅ Pushed {result["ok"]} videos to Telegram channel `{chan}`'

        if target == 'github':
            repo = rest or self._vars.get('github_repo', '')
            token = self._vars.get('github_token', '')
            if not repo or not token:
                return '❌ Set github_repo and github_token first:\n/set github_token ghp_…\n/set github_repo my-repo'
            source = self._last_output or self._vars.get('output', './downloads')
            from ..github_push import GithubPusher
            pusher = GithubPusher(token=token, repo=repo)
            pusher.push(source)
            return f'✅ Pushed to GitHub repo `{repo}`'

        return '❌ Usage: /push telegram|github'

    def _cmd_run(self, script: str, chat_id: int) -> str:
        if not script:
            return '❌ Usage: /run <zeus script text>'
        self.send(chat_id, '▶️ Running script…')
        try:
            from ..zscript.runner import ZeusScriptRunner
            runner = ZeusScriptRunner(vars=dict(self._vars))
            runner.run_string(script)
            return '✅ Script finished.'
        except Exception as e:
            return f'❌ Script error: {e}'

    # ── HTTP helper ───────────────────────────────────────────────────────────

    def _api(self, method: str, data: dict) -> dict:
        url = f'{self._base}/{method}'
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
