"""
ZeusDL Mastermind — processus principal sur Replit.

Lance simultanément :
  1. Serveur HTTP Hermes (port 8080) — reçoit les connexions des agents Colab/VPS
  2. Bot Telegram @TGBOX_HQbot — répond aux commandes dans le chat

Usage :
    python zeusdl/zeus_mastermind.py

URL publique Mastermind (à donner aux agents) :
    https://$REPLIT_DEV_DOMAIN (port 8080 auto-routé par Replit)
"""

import os
import sys
import threading
import time

# Ajouter le package zeusdl au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'zeusdl'))

from zeusdl.config_manager import get_config
from zeusdl.hermes.mastermind import Mastermind
from zeusdl.telebot.bot import ZeusBot

BOT_TOKEN = get_config().telegram_token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
MASTER_PORT = int(os.environ.get('MASTER_PORT', '8080'))

# ── URL publique Replit ────────────────────────────────────────────────────────
_REPLIT_DOMAIN = os.environ.get('REPLIT_DEV_DOMAIN', '')
if _REPLIT_DOMAIN:
    PUBLIC_URL = f'https://{_REPLIT_DOMAIN}'
else:
    PUBLIC_URL = f'http://localhost:{MASTER_PORT}'


def print_banner():
    print()
    print('╔══════════════════════════════════════════════════════════════╗')
    print('║             🏛️  ZeusDL MASTERMIND                           ║')
    print('╠══════════════════════════════════════════════════════════════╣')
    print(f'║  HTTP Mastermind : {PUBLIC_URL:<42}║')
    print(f'║  Bot Telegram    : @TGBOX_HQbot{" " * 30}║')
    print('╠══════════════════════════════════════════════════════════════╣')
    print('║  Pour connecter un agent Colab :                            ║')
    print(f'║    MASTER_URL = "{PUBLIC_URL}"  ║')
    print('╚══════════════════════════════════════════════════════════════╝')
    print()


def start_mastermind(mm: Mastermind):
    """Lance le serveur HTTP Mastermind en thread daemon."""
    mm.start_server(daemon=True)
    print(f'[Mastermind] ✅ Serveur HTTP actif sur le port {MASTER_PORT}')
    print(f'[Mastermind] 🔗 URL publique : {PUBLIC_URL}')


def make_bot_handler(mm: Mastermind):
    """Retourne le handler de commandes bot avec accès au Mastermind."""

    def on_command(cmd: str, args: str, chat_id: int):
        # ── Commandes Hermes ───────────────────────────────────────────────
        if cmd == 'agents':
            status = mm.get_status()
            agents = status.get('agents', {})
            if not agents:
                return '📭 Aucun agent connecté.'
            lines = [f'🤖 Agents ({len(agents)}) :']
            for aid, info in agents.items():
                age = time.time() - info.get('last_seen', 0)
                q = len(status.get('queues', {}).get(aid, []))
                lines.append(f'  • {aid} — {info.get("last_status","?")} (vu il y a {age:.0f}s, {q} ordre(s))')
            return '\n'.join(lines)

        if cmd == 'send':
            # /send agent_id ordre...
            parts = args.split(None, 1)
            if len(parts) < 2:
                return '❌ Usage : /send <agent_id> <ordre>'
            agent_id, order = parts
            mm.send_order(agent_id, order)
            return f'✅ Ordre envoyé à {agent_id} : {order}'

        if cmd == 'broadcast':
            # /broadcast ordre...
            if not args:
                return '❌ Usage : /broadcast <ordre>'
            mm.broadcast_order(args)
            status = mm.get_status()
            n = len(status.get('agents', {}))
            return f'📡 Ordre diffusé à {n} agent(s) : {args}'

        if cmd == 'status':
            status = mm.get_status()
            agents = status.get('agents', {})
            total_q = sum(len(v) for v in status.get('queues', {}).values())
            return (
                f'🏛 Mastermind actif\n'
                f'Agents connectés : {len(agents)}\n'
                f'Ordres en attente : {total_q}\n'
                f'URL : {PUBLIC_URL}'
            )

        # Pas géré ici → le bot utilisera son handler par défaut
        return None

    return on_command


def main():
    print_banner()

    if not BOT_TOKEN:
        print('❌ Erreur : bot token Telegram manquant.')
        print('   Exécute : python -c "from zeusdl.config_manager import ZeusConfig; ZeusConfig().set(\'telegram.bot_token\', \'TON_TOKEN\')"')
        sys.exit(1)

    # Démarrer le Mastermind HTTP
    mm = Mastermind(host='0.0.0.0', port=MASTER_PORT)
    Mastermind._instance = mm
    start_mastermind(mm)

    # Démarrer le bot Telegram
    bot = ZeusBot(token=BOT_TOKEN, on_command=make_bot_handler(mm))
    print(f'[Bot] ✅ @TGBOX_HQbot démarré — en écoute...')
    print(f'[Bot] Commandes disponibles : /start /help /download /status /agents /send /broadcast /set')
    print()

    try:
        bot.start(poll_interval=0.5)
    except KeyboardInterrupt:
        print('\n[Mastermind] Arrêt.')


if __name__ == '__main__':
    main()
