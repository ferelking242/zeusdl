"""
ZeusDL Script Language — .zeus files

Lets you write a batch of Zeus commands in a human-readable script file and
run them with a single command:

    zeusdl run my_orders.zeus

File format: ``zeus`` (plain text, UTF-8).

Example (my_orders.zeus)
────────────────────────

    # Download all BangBros scenes at 1080p and push to Telegram
    set quality 1080p
    set workers 4
    set cookies ~/bangbros.txt
    set output ~/Videos/BangBros

    download https://site-ma.bangbros.com/scenes?addon=5971

    push telegram
        channel  -1001234567890
        message  "BangBros 1080p batch done ✓"

    push github
        token    ghp_xxxxxxxxxxxxxxxxxxxx
        repo     my-bangbros-collection
        dir      ~/Videos/BangBros

See `ZeusScriptParser` and `ZeusScriptRunner` for the full command reference.
"""

from .parser import ZeusScriptParser, ZeusScriptError
from .runner import ZeusScriptRunner

__all__ = ['ZeusScriptParser', 'ZeusScriptError', 'ZeusScriptRunner']
