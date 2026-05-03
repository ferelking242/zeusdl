"""
Hermes Agent Self-Updater

Met à jour l'agent Hermes depuis le dépôt GitHub officiel.

Usage
─────
    zeusdl hermes update               — mettre à jour depuis GitHub
    zeusdl hermes update --check       — vérifier si une mise à jour est disponible
    zeusdl hermes update --restart     — mettre à jour et redémarrer l'agent

En Python
─────────
    from zeusdl.hermes.updater import AgentUpdater
    updater = AgentUpdater()
    if updater.check():
        updater.update()
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from typing import Optional

_GITHUB_REPO = 'ferelking242/zeusdl'
_GITHUB_BRANCH = 'main'
_API_URL = f'https://api.github.com/repos/{_GITHUB_REPO}/commits/{_GITHUB_BRANCH}'
_ARCHIVE_URL = f'https://github.com/{_GITHUB_REPO}/archive/refs/heads/{_GITHUB_BRANCH}.zip'


class AgentUpdater:
    """
    Checks for and applies updates to the ZeusDL agent from GitHub.

    Stratégie :
      1. Via pip  — si zeus a été installé avec pip, `pip install --upgrade` suffit
      2. Via git  — si le repo est cloné, `git pull` suffit
      3. Via archive zip — fallback: télécharger l'archive et réinstaller
    """

    def __init__(self, repo: str = _GITHUB_REPO, branch: str = _GITHUB_BRANCH):
        self.repo = repo
        self.branch = branch
        self._api_url = f'https://api.github.com/repos/{repo}/commits/{branch}'
        self._archive_url = f'https://github.com/{repo}/archive/refs/heads/{branch}.zip'

    def current_commit(self) -> Optional[str]:
        """Return the local git commit SHA, or None if not in a git repo."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def latest_commit(self) -> Optional[str]:
        """Fetch the latest commit SHA from GitHub."""
        try:
            req = urllib.request.Request(
                self._api_url,
                headers={'User-Agent': 'ZeusDL-Hermes-Updater/1.0'},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                return data.get('sha')
        except Exception:
            return None

    def check(self) -> bool:
        """Return True if an update is available."""
        current = self.current_commit()
        latest = self.latest_commit()
        if not latest:
            print('[updater] Could not reach GitHub.')
            return False
        if not current:
            print('[updater] Not in a git repo — update available via pip.')
            return True
        if current == latest:
            print(f'[updater] Already up to date ({current[:8]}).')
            return False
        print(f'[updater] Update available: {current[:8]} → {latest[:8]}')
        return True

    def update(self, restart: bool = False) -> bool:
        """
        Apply the update. Returns True on success.

        Tries (in order):
        1. git pull
        2. pip install --upgrade from GitHub
        """
        print(f'[updater] Updating from {self.repo}@{self.branch}…')

        # Strategy 1: git pull
        if self._try_git_pull():
            print('[updater] ✅ Updated via git pull')
            if restart:
                self._restart()
            return True

        # Strategy 2: pip install from GitHub
        if self._try_pip_upgrade():
            print('[updater] ✅ Updated via pip')
            if restart:
                self._restart()
            return True

        print('[updater] ❌ Could not update automatically.')
        print(f'[updater] Manual update: pip install "git+https://github.com/{self.repo}.git@{self.branch}#subdirectory=zeusdl"')
        return False

    def _try_git_pull(self) -> bool:
        try:
            result = subprocess.run(
                ['git', 'pull', 'origin', self.branch],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                print(result.stdout.strip())
                return True
        except Exception:
            pass
        return False

    def _try_pip_upgrade(self) -> bool:
        pip_target = (
            f'git+https://github.com/{self.repo}.git@{self.branch}'
            f'#subdirectory=zeusdl'
        )
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet', pip_target],
                capture_output=True, text=True, timeout=120,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _restart(self) -> None:
        """Restart the current process."""
        print('[updater] Restarting…')
        os.execv(sys.executable, [sys.executable] + sys.argv)


def main_hermes_update(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='zeusdl hermes update')
    p.add_argument('--check', action='store_true', help='Only check, do not update')
    p.add_argument('--restart', action='store_true', help='Restart agent after update')
    p.add_argument('--repo', default=_GITHUB_REPO, help='GitHub repo (owner/name)')
    p.add_argument('--branch', default=_GITHUB_BRANCH)
    args = p.parse_args(argv)

    updater = AgentUpdater(repo=args.repo, branch=args.branch)

    if args.check:
        available = updater.check()
        sys.exit(0 if not available else 1)
    else:
        if updater.check():
            updater.update(restart=args.restart)
        sys.exit(0)
