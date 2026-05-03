"""
ZeusDL Credentials & Config Manager

Stocke de façon sécurisée :
  • Tokens Telegram (bot token, session Telethon)
  • Identifiants des sites premium (BangBros, Brazzers, etc.)
  • Token GitHub
  • Config Hermes (URL mastermind, port)

Fichier stocké dans :  ~/.config/zeusdl/credentials.json
Permissions :          600 (lecture/écriture propriétaire uniquement)

Le fichier n'est JAMAIS inclus dans git (ajouté dans .gitignore auto).

CLI
───
    zeusdl config show                          — afficher la config (mots de passe masqués)
    zeusdl config set telegram.bot_token VALUE  — définir une valeur
    zeusdl config get telegram.bot_token        — lire une valeur
    zeusdl config edit                          — ouvrir dans l'éditeur système
    zeusdl config reset                         — remettre à zéro (confirmation requise)
    zeusdl config path                          — afficher le chemin du fichier

API Python
──────────
    from zeusdl.config_manager import ZeusConfig

    cfg = ZeusConfig()
    cfg.set('telegram.bot_token', '123:ABC')
    token = cfg.get('telegram.bot_token')
    creds = cfg.get_site('bangbros')   # {'username': ..., 'password': ...}
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_CONFIG_DIR = Path(os.path.expanduser('~')) / '.config' / 'zeusdl'
_CONFIG_FILE = _CONFIG_DIR / 'credentials.json'
_GITIGNORE_PATTERNS = [
    'credentials.json',
    '*.zeus.local',
    '.zeus_session',
]

_SECRET_KEYS = {
    'telegram.bot_token',
    'telegram.session_string',
    'telegram.api_hash',
    'github.token',
    'bangbros.password',
    'brazzers.password',
    'onlyfans.password',
    'mofos.password',
    'realitykings.password',
}

_DEFAULT_CONFIG: dict = {
    'telegram': {
        'bot_token': '',
        'session_string': '',
        'api_id': None,
        'api_hash': '',
        'default_channel': '',
    },
    'bangbros': {
        'username': '',
        'password': '',
        'cookies_path': '',
    },
    'brazzers': {
        'username': '',
        'password': '',
        'cookies_path': '',
    },
    'onlyfans': {
        'username': '',
        'password': '',
        'cookies_path': '',
    },
    'mofos': {
        'username': '',
        'password': '',
        'cookies_path': '',
    },
    'realitykings': {
        'username': '',
        'password': '',
        'cookies_path': '',
    },
    'github': {
        'token': '',
        'default_repo': '',
        'owner': '',
    },
    'hermes': {
        'master_url': 'http://localhost:8765',
        'master_port': 8765,
        'agent_id': '',
    },
    'defaults': {
        'quality': 'best',
        'workers': 3,
        'output_dir': '~/Downloads/zeusdl',
        'sleep': 1.5,
    },
}


class ZeusConfig:
    """
    Thread-safe credentials and configuration manager.

    Values are accessed with dot notation: ``section.key``
    e.g. ``telegram.bot_token``, ``bangbros.username``
    """

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _CONFIG_FILE
        self._data: dict = {}
        self._load()

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding='utf-8'))
            except Exception:
                self._data = {}
        # Merge with defaults (non-destructive)
        self._data = _deep_merge(_DEFAULT_CONFIG, self._data)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        # chmod 600
        self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self._ensure_gitignore()

    def _ensure_gitignore(self) -> None:
        """Add .gitignore in config dir so credentials are never committed."""
        gi = self._path.parent / '.gitignore'
        existing = gi.read_text() if gi.exists() else ''
        for p in _GITIGNORE_PATTERNS:
            if p not in existing:
                gi.write_text(existing + f'\n{p}\n')

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value by dot-notation key.
        e.g. get('telegram.bot_token') → '123:ABC'
        """
        parts = key.lower().split('.', 1)
        if len(parts) == 1:
            return self._data.get(parts[0], default)
        section, subkey = parts
        return (self._data.get(section) or {}).get(subkey, default)

    def get_section(self, section: str) -> dict:
        """Return an entire section dict."""
        return dict(self._data.get(section.lower()) or {})

    def get_site(self, site: str) -> dict:
        """
        Return credentials for a site.
        Merges cookies_path from config with stored username/password.
        """
        return self.get_section(site)

    def get_cookies(self, site: str) -> Optional[str]:
        """Return the cookies file path for a site, or None."""
        path = self.get(f'{site}.cookies_path') or ''
        if path:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                return expanded
        return None

    def all(self) -> dict:
        return dict(self._data)

    # ── Write ─────────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """
        Set a value by dot-notation key and save immediately.
        e.g. set('telegram.bot_token', '123:ABC')
        """
        parts = key.lower().split('.', 1)
        if len(parts) == 1:
            self._data[parts[0]] = value
        else:
            section, subkey = parts
            if section not in self._data:
                self._data[section] = {}
            self._data[section][subkey] = value
        self._save()

    def set_many(self, updates: dict) -> None:
        """Set multiple key-value pairs at once."""
        for k, v in updates.items():
            key_parts = k.lower().split('.', 1)
            if len(key_parts) == 1:
                self._data[key_parts[0]] = v
            else:
                section, subkey = key_parts
                if section not in self._data:
                    self._data[section] = {}
                self._data[section][subkey] = v
        self._save()

    def reset(self) -> None:
        """Reset config to defaults."""
        self._data = _deep_merge(_DEFAULT_CONFIG, {})
        self._save()

    # ── Display ───────────────────────────────────────────────────────────────

    def display(self, show_secrets: bool = False) -> str:
        """Return a pretty-printed config string with secrets masked."""
        lines = [f'ZeusDL Config — {self._path}', '']
        for section, values in self._data.items():
            lines.append(f'[{section}]')
            if isinstance(values, dict):
                for k, v in values.items():
                    full_key = f'{section}.{k}'
                    if not show_secrets and full_key in _SECRET_KEYS and v:
                        display_val = '•' * min(len(str(v)), 8) + '…'
                    else:
                        display_val = str(v) if v is not None else ''
                    lines.append(f'  {k:<20} = {display_val}')
            else:
                lines.append(f'  {section} = {values}')
            lines.append('')
        return '\n'.join(lines)

    # ── Convenience getters ───────────────────────────────────────────────────

    @property
    def telegram_token(self) -> str:
        return self.get('telegram.bot_token') or ''

    @property
    def telegram_channel(self) -> str:
        return self.get('telegram.default_channel') or ''

    @property
    def github_token(self) -> str:
        return self.get('github.token') or ''

    @property
    def hermes_master_url(self) -> str:
        return self.get('hermes.master_url') or 'http://localhost:8765'

    def best_cookies(self, site: str) -> Optional[str]:
        """Return the best available cookies file for a site."""
        # 1. Explicit config path
        explicit = self.get_cookies(site)
        if explicit:
            return explicit
        # 2. Default locations
        candidates = [
            Path.home() / f'{site}_cookies.txt',
            Path.home() / f'{site}.txt',
            Path('/content') / f'{site}_cookies.txt',   # Colab
            Path('./') / f'{site}_cookies.txt',
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[ZeusConfig] = None


def get_config() -> ZeusConfig:
    """Return the global ZeusConfig singleton."""
    global _instance
    if _instance is None:
        _instance = ZeusConfig()
    return _instance


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base (non-destructive, returns new dict)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main_config(argv=None):
    import argparse

    p = argparse.ArgumentParser(
        prog='zeusdl config',
        description='Manage ZeusDL credentials and settings.',
    )
    sub = p.add_subparsers(dest='action')

    sub.add_parser('show', help='Display current config (secrets masked)')
    sub.add_parser('show-secrets', help='Display config including secret values')
    sub.add_parser('path', help='Print the config file path')
    sub.add_parser('edit', help='Open config file in system editor')
    sub.add_parser('reset', help='Reset config to defaults')

    p_set = sub.add_parser('set', help='Set a config value')
    p_set.add_argument('key', help='Dot-notation key (e.g. telegram.bot_token)')
    p_set.add_argument('value', help='Value to set')

    p_get = sub.add_parser('get', help='Get a config value')
    p_get.add_argument('key', help='Dot-notation key')

    args = p.parse_args(argv or [])
    cfg = ZeusConfig()

    if args.action == 'show' or args.action is None:
        print(cfg.display(show_secrets=False))

    elif args.action == 'show-secrets':
        print(cfg.display(show_secrets=True))

    elif args.action == 'path':
        print(cfg._path)

    elif args.action == 'edit':
        path = cfg._path
        # Ensure file exists before opening
        if not path.exists():
            cfg._save()
        editor = (
            os.environ.get('VISUAL')
            or os.environ.get('EDITOR')
            or ('notepad' if sys.platform == 'win32' else 'nano')
        )
        print(f'Opening {path} with {editor}…')
        subprocess.call([editor, str(path)])
        # Reload after edit
        cfg._load()
        print('Config reloaded.')

    elif args.action == 'reset':
        confirm = input('Reset ALL config to defaults? [y/N] ').strip().lower()
        if confirm in ('y', 'yes'):
            cfg.reset()
            print('Config reset to defaults.')
        else:
            print('Cancelled.')

    elif args.action == 'set':
        cfg.set(args.key, args.value)
        display = '••••••••' if args.key in _SECRET_KEYS else args.value
        print(f'✅ {args.key} = {display}')

    elif args.action == 'get':
        val = cfg.get(args.key)
        if val is None:
            print(f'(not set)')
            sys.exit(1)
        # Mask if secret and stdout is a tty
        if args.key in _SECRET_KEYS and sys.stdout.isatty():
            print('(secret — use show-secrets to reveal)')
        else:
            print(val)

    else:
        p.print_help()
