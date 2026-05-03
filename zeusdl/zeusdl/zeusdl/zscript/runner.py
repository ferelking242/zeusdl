"""
Zeus Script Language — runner.

Executes a list of ZeusCommand objects produced by ZeusScriptParser.

Supported verbs
───────────────
    set         key value           — set session variable
    echo        message…            — print to stdout
    wait        [seconds]           — sleep N seconds (default: 1)
    download    url [options]       — bulk-download via BulkDownloader
    push        telegram|github     — push output to Telegram or GitHub
    hermes      agent_id command    — dispatch to a Hermes agent
    run         path                — execute a sub-script
    assert      condition message?  — stop with error if condition fails

Session variables
─────────────────
These are set via `set key value` and govern defaults for all commands:

    quality     1080p | 720p | 480p | 360p | best
    workers     N (concurrent download workers)
    cookies     /path/to/cookies.txt
    output      /path/to/output/dir
    sleep       N (seconds between requests, default: 1.5)
    limit       N (max videos to download, 0 = no limit)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from .parser import ZeusCommand, ZeusScriptError, ZeusScriptParser


class ZeusScriptRunner:
    """
    Execute parsed Zeus script commands.

    Usage::

        runner = ZeusScriptRunner()
        runner.run_file('my_orders.zeus')

        # Or with pre-set variables:
        runner = ZeusScriptRunner(vars={'quality': '1080p', 'workers': '4'})
        runner.run_file('my_orders.zeus')
    """

    def __init__(self, vars: Optional[dict] = None, dry_run: bool = False):
        # Bootstrap from global config
        from ..config_manager import get_config
        cfg = get_config()
        self._vars: dict[str, str] = {
            'quality':           cfg.get('defaults.quality', 'best'),
            'workers':           str(cfg.get('defaults.workers', '3')),
            'sleep':             str(cfg.get('defaults.sleep', '1.5')),
            'output':            cfg.get('defaults.output_dir', './downloads'),
            'telegram_token':    cfg.telegram_token,
            'telegram_channel':  cfg.telegram_channel,
            'github_token':      cfg.github_token,
        }
        if vars:
            self._vars.update({k.lower(): str(v) for k, v in vars.items()})
        self.dry_run = dry_run
        self._last_output_dir: Optional[str] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def run_file(self, path: str) -> None:
        parser = ZeusScriptParser()
        cmds = parser.parse_file(path)
        self._run_commands(cmds, source=path)

    def run_string(self, text: str, source: str = '<string>') -> None:
        parser = ZeusScriptParser()
        cmds = parser.parse_string(text, source=source)
        self._run_commands(cmds, source=source)

    # ── Internal dispatcher ───────────────────────────────────────────────────

    def _run_commands(self, cmds: list[ZeusCommand], source: str = '') -> None:
        for cmd in cmds:
            try:
                self._dispatch(cmd)
            except ZeusScriptError:
                raise
            except Exception as e:
                raise ZeusScriptError(
                    f'Error in {cmd.verb}: {e}',
                    line=cmd.line, path=source,
                ) from e

    def _dispatch(self, cmd: ZeusCommand) -> None:
        verb = cmd.verb
        handlers = {
            'set':      self._cmd_set,
            'echo':     self._cmd_echo,
            'wait':     self._cmd_wait,
            'sleep':    self._cmd_wait,
            'download': self._cmd_download,
            'push':     self._cmd_push,
            'hermes':   self._cmd_hermes,
            'run':      self._cmd_run,
            'assert':   self._cmd_assert,
        }
        handler = handlers.get(verb)
        if not handler:
            raise ZeusScriptError(
                f'Unknown verb "{verb}". Valid verbs: {", ".join(sorted(handlers))}',
                line=cmd.line,
            )
        handler(cmd)

    # ── Verb handlers ─────────────────────────────────────────────────────────

    def _cmd_set(self, cmd: ZeusCommand) -> None:
        if not cmd.args:
            raise ZeusScriptError('set requires a key', line=cmd.line)
        key = cmd.args[0].lower()
        value = ' '.join(cmd.args[1:]) if len(cmd.args) > 1 else ''
        self._vars[key] = value
        self._log(f'set {key} = {value!r}')

    def _cmd_echo(self, cmd: ZeusCommand) -> None:
        print(' '.join(cmd.args))

    def _cmd_wait(self, cmd: ZeusCommand) -> None:
        secs = float(cmd.args[0]) if cmd.args else 1.0
        self._log(f'wait {secs}s')
        if not self.dry_run:
            time.sleep(secs)

    def _cmd_download(self, cmd: ZeusCommand) -> None:
        url = cmd.arg(0)
        if not url:
            raise ZeusScriptError('download requires a URL', line=cmd.line)

        output_dir = (
            cmd.prop('output')
            or cmd.prop('dir')
            or self._var('output', './downloads')
        )
        quality = cmd.prop('quality') or self._var('quality', 'best')
        workers = int(cmd.prop('workers') or self._var('workers', '3'))
        cookies = cmd.prop('cookies') or self._var('cookies')
        limit_raw = cmd.prop('limit') or self._var('limit', '0')
        limit = int(limit_raw) or None
        sleep = float(cmd.prop('sleep') or self._var('sleep', '1.5'))

        self._log(
            f'download {url!r} → {output_dir} | q={quality} w={workers}'
        )
        self._last_output_dir = output_dir

        if self.dry_run:
            return

        from ..bulk_download import BulkDownloader
        dl = BulkDownloader(
            output_dir=output_dir,
            cookies=cookies,
            workers=workers,
            quality=quality,
            limit=limit,
            sleep=sleep,
        )
        dl.run(url)

    def _cmd_push(self, cmd: ZeusCommand) -> None:
        target = cmd.arg(0, '').lower()

        if target == 'telegram':
            self._push_telegram(cmd)
        elif target == 'github':
            self._push_github(cmd)
        else:
            raise ZeusScriptError(
                f'push: unknown target "{target}". Use: telegram, github',
                line=cmd.line,
            )

    def _push_telegram(self, cmd: ZeusCommand) -> None:
        from ..telebot.uploader import TelegramUploader

        channel = (
            cmd.prop('channel')
            or cmd.prop('chat')
            or self._var('telegram_channel')
        )
        bot_token = (
            cmd.prop('token')
            or cmd.prop('bot_token')
            or self._var('telegram_token')
        )
        source_dir = (
            cmd.prop('dir')
            or cmd.prop('output')
            or self._last_output_dir
            or self._var('output', './downloads')
        )
        caption = cmd.prop('message') or cmd.prop('caption') or ''
        if not channel or not bot_token:
            raise ZeusScriptError(
                'push telegram requires: channel + token '
                '(or set telegram_channel / telegram_token)',
                line=cmd.line,
            )

        self._log(f'push telegram → channel {channel} from {source_dir!r}')
        if self.dry_run:
            return

        uploader = TelegramUploader(bot_token=bot_token, channel=channel)
        uploader.upload_directory(source_dir, caption=caption)

    def _push_github(self, cmd: ZeusCommand) -> None:
        from ..github_push import GithubPusher

        token = cmd.prop('token') or self._var('github_token')
        repo = cmd.prop('repo') or self._var('github_repo')
        source_dir = (
            cmd.prop('dir')
            or self._last_output_dir
            or self._var('output', './downloads')
        )
        if not token or not repo:
            raise ZeusScriptError(
                'push github requires: token + repo '
                '(or set github_token / github_repo)',
                line=cmd.line,
            )

        self._log(f'push github → {repo} from {source_dir!r}')
        if self.dry_run:
            return

        pusher = GithubPusher(token=token, repo=repo)
        pusher.push(source_dir)

    def _cmd_hermes(self, cmd: ZeusCommand) -> None:
        from ..hermes.mastermind import Mastermind

        agent_id = cmd.arg(0)
        order_parts = cmd.args[1:] or []
        order = ' '.join(order_parts)

        if not agent_id:
            raise ZeusScriptError('hermes requires an agent_id', line=cmd.line)

        self._log(f'hermes → agent {agent_id!r}: {order!r}')
        if self.dry_run:
            return

        mm = Mastermind.get_instance()
        mm.send_order(agent_id, order)

    def _cmd_run(self, cmd: ZeusCommand) -> None:
        path = cmd.arg(0)
        if not path:
            raise ZeusScriptError('run requires a file path', line=cmd.line)
        self._log(f'run sub-script: {path!r}')
        sub = ZeusScriptRunner(vars=dict(self._vars), dry_run=self.dry_run)
        sub.run_file(path)

    def _cmd_assert(self, cmd: ZeusCommand) -> None:
        condition = cmd.arg(0, '')
        message = ' '.join(cmd.args[1:]) if len(cmd.args) > 1 else f'Assertion failed: {condition}'
        if condition.lower() in ('', 'false', '0', 'no'):
            raise ZeusScriptError(message, line=cmd.line)
        self._log(f'assert OK: {condition!r}')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _var(self, key: str, default: str = '') -> str:
        return self._vars.get(key.lower(), default)

    def _log(self, msg: str) -> None:
        tag = '[dry-run]' if self.dry_run else '[zeus]'
        print(f'{tag} {msg}')
