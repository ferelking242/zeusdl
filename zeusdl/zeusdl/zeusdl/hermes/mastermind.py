"""
Hermes Mastermind — the command-and-control hub.

The Mastermind maintains a list of known Hermes agents, dispatches orders
to them, and aggregates their status reports.

Transport options
─────────────────
1. Built-in HTTP server (default)
   Agents poll ``GET /poll/{agent_id}`` for pending orders.
   Agents report back via ``POST /report/{agent_id}``.

2. Telegram relay (optional)
   Orders are sent as Telegram messages to a bot the agents share.
   Agents filter messages by their own ID prefix.

Usage
─────
    # Start the Mastermind HTTP server
    zeusdl hermes mastermind --port 8765

    # In a .zeus script
    hermes vps1 download https://example.com/playlist

    # From the CLI
    zeusdl hermes send vps1 "download https://example.com/playlist"
    zeusdl hermes status
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


class Mastermind:
    """
    Central controller for the Hermes agent network.

    Can be used as a singleton (``Mastermind.get_instance()``) or
    instantiated directly.
    """

    _instance: Optional['Mastermind'] = None
    _lock = threading.Lock()

    def __init__(self, host: str = '0.0.0.0', port: int = 8765):
        self.host = host
        self.port = port
        self._queues: dict[str, list[str]] = defaultdict(list)
        self._reports: dict[str, list[dict]] = defaultdict(list)
        self._agents: dict[str, dict] = {}
        self._server: Optional[HTTPServer] = None
        self._q_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'Mastermind':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── Order management ──────────────────────────────────────────────────────

    def send_order(self, agent_id: str, order: str) -> None:
        """Queue an order for a specific agent."""
        with self._q_lock:
            self._queues[agent_id].append(order)
        print(f'[Mastermind] Order queued for {agent_id!r}: {order!r}')

    def broadcast_order(self, order: str) -> None:
        """Queue an order for ALL known agents."""
        with self._q_lock:
            for agent_id in self._agents:
                self._queues[agent_id].append(order)
        print(f'[Mastermind] Broadcast to {len(self._agents)} agents: {order!r}')

    def pop_order(self, agent_id: str) -> Optional[str]:
        """Pop the next order for an agent (None if empty)."""
        with self._q_lock:
            queue = self._queues.get(agent_id, [])
            return queue.pop(0) if queue else None

    def receive_report(self, agent_id: str, report: dict) -> None:
        """Accept a status report from an agent."""
        with self._q_lock:
            self._agents[agent_id] = {
                'last_seen': time.time(),
                'last_status': report.get('status', '?'),
            }
            self._reports[agent_id].append(report)

    def get_status(self) -> dict:
        """Return a snapshot of all agents and their queues."""
        with self._q_lock:
            return {
                'agents': dict(self._agents),
                'queues': {k: list(v) for k, v in self._queues.items()},
            }

    # ── HTTP server ───────────────────────────────────────────────────────────

    def start_server(self, daemon: bool = True) -> None:
        mm = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # Suppress default logging

            def do_GET(self):
                # GET /poll/{agent_id}
                if self.path.startswith('/poll/'):
                    agent_id = self.path[6:]
                    order = mm.pop_order(agent_id)
                    body = json.dumps({'order': order}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(body)
                # GET /status
                elif self.path == '/status':
                    body = json.dumps(mm.get_status()).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                # POST /order/{agent_id}  body: {"order": "..."}
                if self.path.startswith('/order/'):
                    agent_id = self.path[7:]
                    length = int(self.headers.get('Content-Length', 0))
                    data = json.loads(self.rfile.read(length))
                    mm.send_order(agent_id, data.get('order', ''))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                # POST /report/{agent_id}  body: {"status": "..."}
                elif self.path.startswith('/report/'):
                    agent_id = self.path[8:]
                    length = int(self.headers.get('Content-Length', 0))
                    report = json.loads(self.rfile.read(length))
                    mm.receive_report(agent_id, report)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                else:
                    self.send_response(404)
                    self.end_headers()

        self._server = HTTPServer((self.host, self.port), _Handler)
        print(f'[Mastermind] HTTP server listening on {self.host}:{self.port}')
        t = threading.Thread(target=self._server.serve_forever, daemon=daemon)
        t.start()

    def stop_server(self) -> None:
        if self._server:
            self._server.shutdown()


# ── CLI helpers ───────────────────────────────────────────────────────────────

def main_mastermind(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog='zeusdl hermes mastermind')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8765)
    args = p.parse_args(argv)

    mm = Mastermind(host=args.host, port=args.port)
    Mastermind._instance = mm
    mm.start_server(daemon=False)
