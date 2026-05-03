"""
ZeusBot — bot Telegram per-user pour contrôler ZeusDL à distance.

Chaque utilisateur utilise son propre bot créé via @BotFather.
Aucun serveur centralisé — le token reste chez toi.

Commandes :
    /start ou /help     — aide
    /download <URL>     — lancer un téléchargement
    /status             — état de la file
    /agents             — liste des agents Hermes connectés
    /send <id> <ordre>  — envoyer un ordre à un agent Hermes
    /broadcast <ordre>  — envoyer un ordre à TOUS les agents
    /set cle valeur     — définir une variable (quality, workers, output...)
    /push telegram      — uploader les vidéos vers Telegram
    /push github        — pousser vers GitHub
    /run <script>       — exécuter un script Zeus inline
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

_HELP_TEXT = (
    "ZeusDL Bot @TGBOX_HQbot\n"
    "\n"
    "Commandes :\n"
    "  /download URL       Telecharger des videos\n"
    "  /status             Etat de la file\n"
    "  /agents             Agents Hermes connectes\n"
    "  /send ID ordre      Envoyer un ordre a un agent\n"
    "  /broadcast ordre    Diffuser a tous les agents\n"
    "  /set cle valeur     Definir une variable\n"
    "  /push telegram      Upload vers Telegram\n"
    "  /push github        Push vers GitHub\n"
    "  /run script         Executer un script Zeus\n"
    "  /help               Cette aide\n"
    "\n"
    "Exemples :\n"
    "  /download https://site-ma.bangbros.com/scenes?addon=5971\n"
    "  /set quality 1080p\n"
    "  /send colab-1 download https://site-ma.bangbros.com/scenes\n"
)


class ZeusBot:
    """
    Bot Telegram long-polling pour le controle distant de ZeusDL.

    Parameters
    ----------
    token : str
        Token du bot Telegram (de @BotFather).
    allowed_users : list[int], optional
        IDs Telegram autorises. Vide = tout le monde.
    on_command : callable, optional
        on_command(cmd, args, chat_id) -> str | None
        Handler custom. Retourne une reponse ou None pour le handler par defaut.
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

    def start(self, poll_interval: float = 0.5) -> None:
        """Demarrer le bot (boucle bloquante)."""
        me = self._api_get('getMe')
        name = me.get('result', {}).get('username', '?')
        print(f'[ZeusBot] @{name} demarre — en ecoute...')
        self._running = True
        while self._running:
            try:
                self._poll()
            except KeyboardInterrupt:
                print('\n[ZeusBot] Arret.')
                break
            except Exception as e:
                print(f'[ZeusBot] Erreur poll: {e}', file=sys.stderr)
                time.sleep(5)

    def stop(self) -> None:
        self._running = False

    def send(self, chat_id: int, text: str) -> None:
        """Envoyer un message texte brut (sans Markdown) a un chat."""
        # On utilise du texte brut — pas de parse_mode pour eviter les erreurs silencieuses
        self._api_post('sendMessage', {
            'chat_id': chat_id,
            'text': text[:4096],
        })

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Long-poll Telegram pour les nouveaux messages."""
        data = self._api_post('getUpdates', {
            'offset': self._offset,
            'timeout': 25,
            'allowed_updates': ['message'],
        })
        for update in (data.get('result') or []):
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
            self.send(chat_id, 'Acces refuse.')
            return

        if not text.startswith('/'):
            self.send(chat_id, 'Envoie /help pour voir les commandes disponibles.')
            return

        # Extraire commande et arguments
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower().split('@')[0]  # ignorer @bot_name si present
        args = parts[1] if len(parts) > 1 else ''

        print(f'[ZeusBot] /{cmd} {args[:60]} (user={user_id})')

        try:
            reply = self._dispatch(cmd, args, chat_id)
            if reply:
                self.send(chat_id, reply)
        except Exception as e:
            self.send(chat_id, f'Erreur : {e}')

    def _dispatch(self, cmd: str, args: str, chat_id: int) -> Optional[str]:
        # Handler custom en priorite (Mastermind, etc.)
        if self.on_command:
            result = self.on_command(cmd, args, chat_id)
            if result is not None:
                return result

        handlers = {
            'help':      lambda: _HELP_TEXT,
            'start':     lambda: _HELP_TEXT,
            'status':    self._cmd_status,
            'set':       lambda: self._cmd_set(args),
            'download':  lambda: self._cmd_download(args, chat_id),
            'push':      lambda: self._cmd_push(args, chat_id),
            'run':       lambda: self._cmd_run(args, chat_id),
            'getid':     lambda: self._cmd_getid(chat_id),
            'myid':      lambda: self._cmd_getid(chat_id),
        }
        handler = handlers.get(cmd)
        if not handler:
            return f'Commande inconnue : /{cmd}\nEnvoie /help'
        return handler()

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _cmd_getid(self, chat_id: int) -> str:
        """Retourne l'ID du chat courant — utile pour configurer un canal."""
        return f'ID de ce chat : {chat_id}\nCopie ce nombre et mets-le comme CHANNEL dans Colab.'

    def _cmd_status(self) -> str:
        if not self._jobs:
            return 'File vide. Aucun telechargement en cours.'
        lines = ['File de telechargement :']
        for j in self._jobs[-5:]:
            lines.append(f"  {j.get('status','?')} - {j.get('url','?')[:60]}")
        return '\n'.join(lines)

    def _cmd_set(self, args: str) -> str:
        parts = args.split(None, 1)
        if len(parts) < 2:
            return 'Usage : /set cle valeur\nEx: /set quality 1080p'
        k, v = parts[0].lower(), parts[1]
        self._vars[k] = v
        return f'OK : {k} = {v}'

    def _cmd_download(self, url: str, chat_id: int) -> Optional[str]:
        if not url:
            return 'Usage : /download <URL>'
        job = {'url': url, 'status': 'en attente', 'chat_id': chat_id}
        self._jobs.append(job)

        def _run():
            job['status'] = 'telechargement...'
            self.send(chat_id, f'Telechargement lance :\n{url}')
            try:
                from ..bulk_download import BulkDownloader
                output_dir = self._vars.get('output', './downloads')
                dl = BulkDownloader(
                    output_dir=output_dir,
                    quality=self._vars.get('quality', 'best'),
                    workers=int(self._vars.get('workers', '2')),
                )
                result = dl.run(url)
                job['status'] = 'termine'
                self._last_output = output_dir
                self.send(chat_id,
                    f'Termine !\n'
                    f'{result["ok"]} videos OK\n'
                    f'{result["failed"]} echecs\n'
                    f'Dossier : {output_dir}')
            except Exception as e:
                job['status'] = 'erreur'
                self.send(chat_id, f'Erreur : {e}')

        threading.Thread(target=_run, daemon=True).start()
        return None  # reponse deja envoyee dans le thread

    def _cmd_push(self, args: str, chat_id: int) -> str:
        parts = args.split(None, 1)
        target = parts[0].lower() if parts else ''
        rest = parts[1] if len(parts) > 1 else ''

        if target == 'telegram':
            chan = rest or self._vars.get('telegram_channel', '')
            tok = self._vars.get('telegram_token', self.token)
            if not chan:
                return 'Usage : /push telegram <channel_id>\nou /set telegram_channel -100xxx'
            source = self._last_output or self._vars.get('output', './downloads')
            from .uploader import TelegramUploader
            uploader = TelegramUploader(bot_token=tok, channel=chan)
            result = uploader.upload_directory(source)
            return f'{result["ok"]} videos envoyes vers {chan}'

        if target == 'github':
            repo = rest or self._vars.get('github_repo', '')
            token = self._vars.get('github_token', '')
            if not repo or not token:
                return (
                    'Configure d\'abord :\n'
                    '/set github_token ghp_...\n'
                    '/set github_repo mon-repo'
                )
            source = self._last_output or self._vars.get('output', './downloads')
            from ..github_push import GithubPusher
            GithubPusher(token=token, repo=repo).push(source)
            return f'Push GitHub termine : {repo}'

        return 'Usage : /push telegram|github'

    def _cmd_run(self, script: str, chat_id: int) -> str:
        if not script:
            return 'Usage : /run <script zeus>'
        self.send(chat_id, 'Execution du script...')
        try:
            from ..zscript.runner import ZeusScriptRunner
            ZeusScriptRunner(vars=dict(self._vars)).run_string(script)
            return 'Script termine.'
        except Exception as e:
            return f'Erreur script : {e}'

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _api_get(self, method: str) -> dict:
        req = urllib.request.Request(
            f'{self._base}/{method}',
            headers={'User-Agent': 'ZeusDL-Bot/1.0'},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def _api_post(self, method: str, data: dict) -> dict:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f'{self._base}/{method}',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'ZeusDL-Bot/1.0',
            },
        )
        # Timeout plus long pour le long-poll (timeout=25 dans le payload + marge)
        timeout = 35 if method == 'getUpdates' else 15
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err = json.loads(raw)
            except Exception:
                err = {'description': raw.decode(errors='replace')}
            print(f'[ZeusBot] API error {method}: {err.get("description","")}',
                  file=sys.stderr)
            return {}
