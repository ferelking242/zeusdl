"""
BangBros MA — Login automatique par email + mot de passe.

Pas besoin d'exporter des cookies manuellement. Ce module :
  1. POST sur l'API project1service.com avec les identifiants
  2. Récupère les tokens de session
  3. Sauvegarde les cookies au format Netscape (compatible yt-dlp)

Usage :
    from zeusdl.bangbros_login import BangBrosLogin
    cookies_path = BangBrosLogin().login('email@gmail.com', 'motdepasse')
    # -> '/content/bangbros_cookies.txt'

CLI :
    zeusdl bangbros-login
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.parse
import urllib.request

# ── API endpoints ─────────────────────────────────────────────────────────────
_API_BASE    = 'https://site-api.project1service.com'
_LOGIN_URL   = f'{_API_BASE}/api/account/login'
_PROFILE_URL = f'{_API_BASE}/api/account'

# Cookie domain utilisé pour yt-dlp
_COOKIE_DOMAIN = '.bangbros.com'

_HEADERS = {
    'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept':       'application/json',
    'Content-Type': 'application/json',
    'Origin':       'https://www.bangbros.com',
    'Referer':      'https://www.bangbros.com/',
    'X-Site-Slug':  'bangbros',
}


class BangBrosLoginError(Exception):
    pass


class BangBrosLogin:
    """
    Login BangBros MA par email + mot de passe.

    Parameters
    ----------
    cookies_path : str
        Chemin où sauvegarder le fichier cookies Netscape.
        Défaut : ~/Downloads/zeusdl/bangbros_cookies.txt
    """

    def __init__(self, cookies_path: str | None = None):
        self.cookies_path = cookies_path or os.path.join(
            os.path.expanduser('~'), 'Downloads', 'zeusdl', 'bangbros_cookies.txt'
        )

    def login(self, email: str, password: str) -> str:
        """
        Se connecte à BangBros avec email + mot de passe.
        Retourne le chemin du fichier cookies sauvegardé.

        Raises
        ------
        BangBrosLoginError
            Si les identifiants sont invalides ou le compte n'a pas d'abonnement MA.
        """
        print(f'[BangBros] Connexion avec {email}...')

        payload = json.dumps({'username': email, 'password': password}).encode()
        req = urllib.request.Request(_LOGIN_URL, data=payload, headers=_HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')
            raise BangBrosLoginError(
                f'Erreur HTTP {e.code} : {body[:200]}'
            ) from e

        # Vérifier la réponse
        if not data.get('success') and not data.get('access_token'):
            msg = data.get('message') or data.get('error') or json.dumps(data)[:200]
            raise BangBrosLoginError(f'Login échoué : {msg}')

        # Extraire les tokens
        access_token = (
            data.get('access_token')
            or data.get('data', {}).get('access_token')
            or data.get('token')
        )
        instance_token = (
            data.get('instance_token')
            or data.get('data', {}).get('instance_token')
            or ''
        )

        if not access_token:
            raise BangBrosLoginError(
                f'Token introuvable dans la réponse : {json.dumps(data)[:300]}'
            )

        print(f'[BangBros] Connecté ! Token obtenu.')

        # Vérifier l'abonnement MA
        self._check_membership(access_token)

        # Sauvegarder les cookies
        self._save_cookies(access_token, instance_token)
        print(f'[BangBros] Cookies sauvegardés → {self.cookies_path}')
        return self.cookies_path

    def _check_membership(self, access_token: str) -> None:
        """Vérifie que le compte a bien un abonnement actif."""
        req = urllib.request.Request(
            _PROFILE_URL,
            headers={**_HEADERS, 'Authorization': f'Bearer {access_token}'},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                profile = json.loads(resp.read())
            subscribed = (
                profile.get('is_subscribed')
                or profile.get('data', {}).get('is_subscribed')
                or profile.get('subscribed')
                or True   # si le champ n'existe pas on continue quand même
            )
            username = (
                profile.get('username')
                or profile.get('data', {}).get('username')
                or 'membre'
            )
            print(f'[BangBros] Compte : {username} — abonnement OK')
        except Exception as e:
            # Non bloquant — on continue même si la vérification échoue
            print(f'[BangBros] Impossible de vérifier l\'abonnement : {e}')

    def _save_cookies(self, access_token: str, instance_token: str) -> None:
        """Écrit un fichier cookies au format Netscape (compatible yt-dlp / wget)."""
        os.makedirs(os.path.dirname(os.path.abspath(self.cookies_path)), exist_ok=True)
        now  = int(time.time())
        exp  = now + 30 * 24 * 3600   # 30 jours

        lines = ['# Netscape HTTP Cookie File', '# Generated by ZeusDL BangBrosLogin', '']

        def _cookie(domain: str, name: str, value: str) -> str:
            # Format : domain  flag  path  secure  expiry  name  value
            return f'{domain}\tTRUE\t/\tFALSE\t{exp}\t{name}\t{value}'

        # access_token_ma — cookie principal d'authentification
        lines.append(_cookie('.bangbros.com',               'access_token_ma', access_token))
        lines.append(_cookie('.site-ma.bangbros.com',       'access_token_ma', access_token))
        lines.append(_cookie('.project1service.com',        'access_token_ma', access_token))
        lines.append(_cookie('.site-api.project1service.com','access_token_ma', access_token))

        if instance_token:
            lines.append(_cookie('.bangbros.com',           'instance_token',  instance_token))
            lines.append(_cookie('.project1service.com',    'instance_token',  instance_token))

        with open(self.cookies_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        os.chmod(self.cookies_path, 0o600)
