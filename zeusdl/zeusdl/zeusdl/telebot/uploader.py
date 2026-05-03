"""
Telegram uploader — sends video files to a Telegram channel via the Bot API.

Uses pure stdlib urllib (no extra deps) for small files and falls back to
multipart streaming for large ones.  Telegram's Bot API supports files up to
2 GB via sendVideo; larger files need the MTProto path (Telethon).
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_TG_API = 'https://api.telegram.org/bot{token}'
_VIDEO_EXTS = {'.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.m4v'}
_MAX_API_SIZE = 50 * 1024 * 1024   # 50 MB — Telegram Bot API limit for sendVideo


class TelegramUploader:
    """
    Upload video files to a Telegram channel using a bot token.

    Parameters
    ----------
    bot_token : str
        Your bot token from @BotFather.
    channel : str | int
        Channel/chat ID (e.g. ``-1001234567890``) or username (``@mychannel``).
    caption_template : str
        Python format string for the caption. Available keys: title, filename.
    """

    def __init__(
        self,
        bot_token: str,
        channel: str | int,
        caption_template: str = '{title}',
        notify: bool = True,
    ):
        self.bot_token = bot_token
        self.channel = str(channel)
        self.caption_template = caption_template
        self.notify = notify
        self._base = _TG_API.format(token=bot_token)

    # ── Public ────────────────────────────────────────────────────────────────

    def upload_directory(self, directory: str, caption: str = '') -> dict:
        """Upload every video file in `directory` (non-recursive) to Telegram."""
        d = Path(directory).resolve()
        if not d.is_dir():
            raise ValueError(f'Not a directory: {d}')

        video_files = sorted([
            f for f in d.rglob('*')
            if f.suffix.lower() in _VIDEO_EXTS and f.is_file()
        ])

        total = len(video_files)
        ok = failed = 0
        print(f'[telebot] Uploading {total} video(s) from {d} → {self.channel}')

        for i, vf in enumerate(video_files, 1):
            print(f'[telebot] [{i}/{total}] {vf.name}')
            try:
                self.upload_file(vf, caption=caption or vf.stem)
                ok += 1
            except Exception as e:
                print(f'[telebot] ✗ {vf.name}: {e}', file=sys.stderr)
                failed += 1

        print(f'[telebot] Done: {ok} uploaded, {failed} failed')
        return {'ok': ok, 'failed': failed, 'total': total}

    def upload_file(self, path: str | Path, caption: str = '') -> dict:
        """Upload a single video file to Telegram."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f'File not found: {p}')

        size = p.stat().st_size
        cap = caption or p.stem
        if len(cap) > 1024:
            cap = cap[:1021] + '...'

        if size <= _MAX_API_SIZE:
            return self._send_video_multipart(p, caption=cap)
        else:
            print(
                f'[telebot] File too large for Bot API ({size / 1e6:.0f} MB > 50 MB). '
                'Sending as document link or use Telethon for large files.',
                file=sys.stderr,
            )
            return self.send_message(
                f'⚠️ File too large to upload directly: {p.name} ({size / 1e6:.0f} MB)\n'
                f'Caption: {cap}'
            )

    def send_message(self, text: str) -> dict:
        """Send a plain text message to the channel."""
        return self._api('sendMessage', {
            'chat_id': self.channel,
            'text': text[:4096],
            'disable_notification': not self.notify,
        })

    # ── Internal ──────────────────────────────────────────────────────────────

    def _api(self, method: str, data: dict) -> dict:
        url = f'{self._base}/{method}'
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err = json.loads(raw)
            except Exception:
                err = {'description': raw.decode(errors='replace')}
            raise RuntimeError(f'Telegram API error {e.code}: {err.get("description", "")}')

    def _send_video_multipart(self, path: Path, caption: str) -> dict:
        """Send video via multipart/form-data (supports files up to 50 MB)."""
        url = f'{self._base}/sendVideo'
        boundary = '----ZeusDLBoundary'
        mime = mimetypes.guess_type(str(path))[0] or 'video/mp4'

        parts = []

        def _field(name: str, value: str) -> bytes:
            return (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n'
            ).encode()

        parts.append(_field('chat_id', self.channel))
        parts.append(_field('caption', caption))
        parts.append(_field('disable_notification', str(not self.notify).lower()))
        parts.append(_field('supports_streaming', 'true'))

        # File part header
        parts.append((
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="video"; filename="{path.name}"\r\n'
            f'Content-Type: {mime}\r\n\r\n'
        ).encode())

        body = b''.join(parts) + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()

        req = urllib.request.Request(
            url, data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err = json.loads(raw)
            except Exception:
                err = {'description': raw.decode(errors='replace')}
            raise RuntimeError(
                f'Telegram upload error {e.code}: {err.get("description", "")}'
            )
