"""
Zeus Script Language — parser.

Grammar (informal)
──────────────────
script      := statement*
statement   := comment | blank | command
comment     := '#' <rest-of-line>
blank       := <empty line>
command     := verb argument* (INDENT property*)?
property    := key value

Verbs
─────
    set         key value          — set a session variable
    download    url [options…]     — download a URL
    push        target [options…]  — push result somewhere
    hermes      agent_id command   — send command to a Hermes agent
    wait        [seconds]          — pause execution
    echo        message…           — print a message
    run         path               — execute a sub-script
    assert      expr               — fail if expression is falsy

Properties (indented continuation lines under a verb)
───────────────────────────────────────────────────────
    key   value

String values may be quoted with single or double quotes.
Variables are expanded: ${varname} or $varname.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ZeusScriptError(Exception):
    """Raised for parse or runtime errors in a .zeus script."""
    def __init__(self, message: str, line: int = 0, path: str = ''):
        loc = f'{path}:{line}' if path else (f'line {line}' if line else '')
        super().__init__(f'{loc}: {message}' if loc else message)
        self.line = line
        self.path = path


@dataclass
class ZeusCommand:
    """A single parsed command from a .zeus script."""
    verb: str
    args: list[str] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)
    line: int = 0

    def arg(self, index: int, default: Any = None) -> Any:
        return self.args[index] if index < len(self.args) else default

    def prop(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Check props first, then positional args by index."""
        return self.props.get(key, default)


_VAR_RE = re.compile(r'\$\{(\w+)\}|\$(\w+)')
_INDENT_RE = re.compile(r'^(\s+)\S')


def _expand(s: str, variables: dict[str, str]) -> str:
    """Replace ${var} and $var with their values from `variables`."""
    def _repl(m):
        name = m.group(1) or m.group(2)
        return variables.get(name, m.group(0))
    return _VAR_RE.sub(_repl, s)


def _tokenize(raw: str) -> list[str]:
    """Split a line into tokens, respecting quotes."""
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


class ZeusScriptParser:
    """
    Parse a .zeus script file or string into a list of ZeusCommand objects.

    Usage::

        parser = ZeusScriptParser()
        commands = parser.parse_file('my_orders.zeus')

        for cmd in commands:
            print(cmd.verb, cmd.args, cmd.props)
    """

    def parse_file(self, path: str | Path) -> list[ZeusCommand]:
        p = Path(path)
        if not p.exists():
            raise ZeusScriptError(f'Script not found: {p}', path=str(p))
        text = p.read_text(encoding='utf-8')
        return self.parse_string(text, source=str(p))

    def parse_string(self, text: str, source: str = '') -> list[ZeusCommand]:
        lines = text.splitlines()
        commands: list[ZeusCommand] = []
        i = 0
        variables: dict[str, str] = {}

        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            lineno = i + 1
            i += 1

            # Skip blank lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Expand variables in the line
            expanded = _expand(stripped, variables)
            tokens = _tokenize(expanded)
            if not tokens:
                continue

            verb = tokens[0].lower()
            args = tokens[1:]
            props: dict[str, str] = {}

            # Read indented property block
            while i < len(lines):
                next_raw = lines[i]
                if not next_raw.strip() or next_raw.strip().startswith('#'):
                    i += 1
                    continue
                m = _INDENT_RE.match(next_raw)
                if not m:
                    break
                prop_line = _expand(next_raw.strip(), variables)
                prop_tokens = _tokenize(prop_line)
                if len(prop_tokens) >= 2:
                    props[prop_tokens[0].lower()] = ' '.join(prop_tokens[1:])
                elif len(prop_tokens) == 1:
                    props[prop_tokens[0].lower()] = ''
                i += 1

            cmd = ZeusCommand(verb=verb, args=args, props=props, line=lineno)

            # Handle `set` immediately so later lines can use the variable
            if verb == 'set' and len(args) >= 2:
                variables[args[0].lower()] = ' '.join(args[1:])

            commands.append(cmd)

        return commands
