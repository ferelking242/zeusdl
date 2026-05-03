"""
Hermes Agent — runs on a remote machine and executes Zeus orders.

Install on a VPS / Colab / spare machine:

    pip install zeusdl
    zeusdl hermes start --master-url http://your-ip:8765 --agent-id vps1

The agent will:
  1. Poll the Mastermind every few seconds for new orders
  2. Execute each order as a Zeus script
  3. Report progress and completion back to the Mastermind

Alternatively, pass ``--telegram-token`` and the agent will receive orders
via a shared Telegram bot instead of HTTP polling.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Optional


class HermesAgent:
    """
    Lightweight Zeus agent — polls for orders and executes them.

    Parameters
    ----------
    agent_id : str
        Unique name for this agent (e.g. 'vps1', 'colab-gpu', 'home-pc').
    master_url : str
        Base URL of the Mastermind HTTP server.
    poll_interval : float
        Seconds between poll requests.
    """

    def __init__(
        self,
        agent_id: str,
        master_url: str,
        poll_interval: float = 3.0,
    ):
        self.agent_id = agent_id
        self.master_url = master_url.rstrip('/')
        self.poll_interval = poll_interval
        self._running = False
        self._current_order: Optional[str] = None
        self._vars: dict[str, str] = {}

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the agent (blocking poll loop)."""
        print(f'[Hermes:{self.agent_id}] Started. Connecting to {self.master_url}')
        self._running = True
        while self._running:
            try:
                order = self._poll()
                if order:
                    self._execute(order)
                else:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                print(f'\n[Hermes:{self.agent_id}] Stopped by user.')
                break
            except Exception as e:
                print(f'[Hermes:{self.agent_id}] Error: {e}', file=sys.stderr)
                time.sleep(self.poll_interval * 2)

    def stop(self) -> None:
        self._running = False

    def set_var(self, key: str, value: str) -> None:
        self._vars[key.lower()] = value

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self) -> Optional[str]:
        url = f'{self.master_url}/poll/{self.agent_id}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Hermes/1.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                return data.get('order')
        except Exception:
            return None

    def _report(self, status: str, details: str = '') -> None:
        url = f'{self.master_url}/report/{self.agent_id}'
        body = json.dumps({
            'agent_id': self.agent_id,
            'status': status,
            'details': details,
            'ts': time.time(),
        }).encode()
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={'Content-Type': 'application/json'},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    # ── Execution ─────────────────────────────────────────────────────────────

    def _execute(self, order: str) -> None:
        """Execute an order string as a Zeus script."""
        self._current_order = order
        print(f'[Hermes:{self.agent_id}] Executing: {order!r}')
        self._report('running', order)

        try:
            from ..zscript.runner import ZeusScriptRunner
            runner = ZeusScriptRunner(vars=dict(self._vars))
            runner.run_string(order, source=f'hermes:{self.agent_id}')
            self._report('done', order)
            print(f'[Hermes:{self.agent_id}] ✅ Order complete.')
        except Exception as e:
            self._report('error', str(e))
            print(f'[Hermes:{self.agent_id}] ❌ Order failed: {e}', file=sys.stderr)
        finally:
            self._current_order = None


# ── CLI entry points ──────────────────────────────────────────────────────────

def main_hermes_start(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='zeusdl hermes start')
    p.add_argument('--agent-id', required=True, help='Unique agent name')
    p.add_argument('--master-url', required=True,
                   help='Mastermind base URL (e.g. http://1.2.3.4:8765)')
    p.add_argument('--poll', type=float, default=3.0, help='Poll interval in seconds')
    p.add_argument('--set', action='append', metavar='KEY=VALUE',
                   help='Set a session variable (can be repeated)')
    args = p.parse_args(argv)

    agent = HermesAgent(
        agent_id=args.agent_id,
        master_url=args.master_url,
        poll_interval=args.poll,
    )

    for kv in (args.set or []):
        if '=' in kv:
            k, v = kv.split('=', 1)
            agent.set_var(k, v)

    agent.start()


def main_hermes_send(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='zeusdl hermes send')
    p.add_argument('agent_id', help='Target agent ID')
    p.add_argument('order', nargs='+', help='Order string')
    p.add_argument('--master-url', default='http://localhost:8765')
    args = p.parse_args(argv)

    order = ' '.join(args.order)
    url = f'{args.master_url}/order/{args.agent_id}'
    body = json.dumps({'order': order}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    print(f'✅ Order sent to {args.agent_id}: {order!r}')
    return result


def main_hermes_status(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='zeusdl hermes status')
    p.add_argument('--master-url', default='http://localhost:8765')
    args = p.parse_args(argv)

    url = f'{args.master_url}/status'
    with urllib.request.urlopen(url, timeout=5) as r:
        status = json.loads(r.read())

    agents = status.get('agents', {})
    queues = status.get('queues', {})

    print(f'Hermes Network — {len(agents)} agent(s)')
    print()
    for aid, info in agents.items():
        last = info.get('last_status', '?')
        age = time.time() - info.get('last_seen', 0)
        qlen = len(queues.get(aid, []))
        print(f'  {aid}: {last} (last seen {age:.0f}s ago, {qlen} orders queued)')
    if not agents:
        print('  (no agents registered)')
