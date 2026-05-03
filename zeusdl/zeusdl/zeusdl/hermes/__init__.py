"""
Hermes — ZeusDL Distributed Agent Network

"Hermes" is the messenger of Zeus in Greek mythology.
In ZeusDL, Hermes agents are lightweight workers you can deploy on any machine
(VPS, Raspberry Pi, spare laptop, Google Colab, etc.).  Each agent connects
back to the Zeus Mastermind and waits for orders.

Architecture
────────────
                         ┌───────────┐
                         │  ZEUS CLI │  (your machine)
                         │ Mastermind│
                         └─────┬─────┘
                               │ HTTP / Telegram
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Hermes 1 │    │ Hermes 2 │    │ Hermes 3 │
        │  VPS-A   │    │  VPS-B   │    │  Colab   │
        └──────────┘    └──────────┘    └──────────┘
        download 360p   download 480p   download 720p
        → push TG ch1   → push TG ch2   → push GitHub

Each Hermes agent:
  • Connects to the Mastermind via HTTP polling or Telegram
  • Receives order strings and executes them as Zeus scripts
  • Reports progress / completion back
  • Runs completely autonomously once started

Quick start (on a VPS)
──────────────────────
    pip install zeusdl
    zeusdl hermes start --master-url http://your-server:8765 --agent-id vps1

Or via Telegram:
    zeusdl hermes start --telegram-token BOT_TOKEN --agent-id vps1

Send orders from your Zeus CLI:
    zeusdl hermes send vps1 "download https://… --quality 720p"

Or in a .zeus script:
    hermes vps1 download https://site-ma.bangbros.com/scenes?addon=5971
        quality 720p
        push telegram
            channel -100123456789
"""

from .agent import HermesAgent
from .mastermind import Mastermind
from .updater import AgentUpdater

__all__ = ['HermesAgent', 'Mastermind', 'AgentUpdater']
