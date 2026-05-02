"""
Global bandwidth limiter for the download queue.

Because the actual I/O happens inside child processes (zeusdl subprocesses),
enforcement works by computing a *per-worker rate cap* that is passed to each
subprocess via the ``-r`` flag.

Per-worker cap algorithm
────────────────────────
The per-worker cap is derived from the *configured maximum* worker count
(``max_concurrent``), **not** from the number of currently active workers::

    per_task_bytes_per_sec = global_bytes_per_sec // max_concurrent

Using the static maximum is the only way to guarantee the global ceiling is
never breached: each subprocess receives its ``-r`` limit once at launch and
keeps it for the entire lifetime of the download.  If we divided by the current
active count instead, an early-starting worker would get a large share, then a
later-starting sibling would get a smaller share — but the early worker's
subprocess still holds the original, oversized ``-r`` value, allowing the
aggregate to exceed the cap.

With a static allocation the worst-case aggregate is
``per_task * max_concurrent = global_bps``, which is exactly the ceiling.

Token bucket
────────────
A ``TokenBucket`` is also maintained and exposed via ``GlobalRateLimiter.consume()``.
It provides a second enforcement path for any in-process I/O (e.g., future
workers that read bytes directly rather than via subprocess).  For the current
subprocess-based architecture the ``-r`` flag is the primary enforcement; the
token bucket is available as infrastructure for callers that perform in-process
streaming.

Accepted bandwidth string formats (case-insensitive)
─────────────────────────────────────────────────────
    10M  /  10MB  /  10MiB   → megabytes per second
    500K /  500KB /  500KiB  → kilobytes per second
    1G   /  1GB   /  1GiB    → gigabytes per second
    1024 /  1024B             → bytes per second
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional


# ---------------------------------------------------------------------------
# Bandwidth string helpers
# ---------------------------------------------------------------------------

_UNIT_RE = re.compile(
    r"^\s*(?P<value>[\d.]+)\s*(?P<unit>[KMGT]i?B?|B)?\s*$",
    re.IGNORECASE,
)

_UNIT_MAP = {
    "":    1,
    "b":   1,
    "k":   1_000,
    "kb":  1_000,
    "kib": 1_024,
    "m":   1_000_000,
    "mb":  1_000_000,
    "mib": 1_048_576,
    "g":   1_000_000_000,
    "gb":  1_000_000_000,
    "gib": 1_073_741_824,
    "t":   1_000_000_000_000,
    "tb":  1_000_000_000_000,
    "tib": 1_099_511_627_776,
}


def parse_bandwidth(spec: str) -> int:
    """Parse a human-readable bandwidth string to bytes per second.

    Examples::

        parse_bandwidth("10M")    → 10_000_000
        parse_bandwidth("512KiB") → 524_288
        parse_bandwidth("1.5G")   → 1_500_000_000
        parse_bandwidth("2048")   → 2048

    Raises ``ValueError`` on invalid input (unparseable string, unknown unit,
    or a value that is zero or negative).
    """
    m = _UNIT_RE.match(spec)
    if not m:
        raise ValueError(f"Cannot parse bandwidth spec: {spec!r}")
    value = float(m.group("value"))
    unit = (m.group("unit") or "").lower()
    multiplier = _UNIT_MAP.get(unit)
    if multiplier is None:
        raise ValueError(f"Unknown bandwidth unit: {unit!r}")
    result = int(value * multiplier)
    if result <= 0:
        raise ValueError(
            f"Bandwidth must be a positive value; got {spec!r} which evaluates to {result} B/s"
        )
    return result


def format_rate(bytes_per_sec: int) -> str:
    """Return a yt-dlp ``-r`` compatible rate string for *bytes_per_sec*.

    yt-dlp accepts ``K`` (×1000) and ``M`` (×1000000) suffixes.
    We always emit the most compact representation that stays accurate
    to within one byte per second.
    """
    if bytes_per_sec <= 0:
        return "1"  # floor to 1 B/s rather than breaking the flag
    if bytes_per_sec >= 1_000_000 and bytes_per_sec % 1_000_000 == 0:
        return f"{bytes_per_sec // 1_000_000}M"
    if bytes_per_sec >= 1_000 and bytes_per_sec % 1_000 == 0:
        return f"{bytes_per_sec // 1_000}K"
    return str(bytes_per_sec)


# ---------------------------------------------------------------------------
# Token-bucket implementation
# ---------------------------------------------------------------------------

class TokenBucket:
    """Thread-safe token-bucket rate limiter.

    *capacity* — maximum burst size in bytes.
    *rate*     — sustained rate in bytes per second.

    Call :meth:`consume` to request *n* bytes.  The call blocks until enough
    tokens are available (i.e. until the elapsed time has refilled the bucket
    sufficiently).  This makes it suitable for shared use across threads
    without busy-waiting.
    """

    def __init__(self, rate: int, capacity: Optional[int] = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be a positive integer (bytes/sec)")
        self._rate: int = rate
        self._capacity: int = capacity if capacity is not None else rate  # 1-second burst
        self._tokens: float = float(self._capacity)
        self._last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def rate(self) -> int:
        return self._rate

    @rate.setter
    def rate(self, new_rate: int) -> None:
        with self._lock:
            if new_rate <= 0:
                raise ValueError("rate must be > 0")
            self._rate = new_rate
            self._capacity = new_rate  # keep burst == 1-second window

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def consume(self, n: int) -> None:
        """Block until *n* bytes worth of tokens are available, then consume them."""
        if n <= 0:
            return
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # How long until we have enough?
                deficit = n - self._tokens
                wait = deficit / self._rate

            time.sleep(min(wait, 0.05))  # cap sleep to allow rate changes to take effect

    def _refill(self) -> None:
        """Add tokens proportional to elapsed time (call with lock held)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)


# ---------------------------------------------------------------------------
# Global rate limiter
# ---------------------------------------------------------------------------

class GlobalRateLimiter:
    """Shared bandwidth cap enforced across all concurrent download workers.

    The limiter offers two complementary mechanisms:

    1. **Subprocess ``-r`` flag** — :meth:`per_task_rate_arg` returns the
       ``-r`` value to pass to each zeusdl subprocess so that, collectively,
       they cannot exceed the global cap even before any bytes are read.

    2. **In-process token bucket** — :meth:`consume` can be called from
       worker threads that read bytes directly, providing a second line of
       enforcement (used when workers perform in-process I/O).

    Parameters
    ----------
    max_bandwidth:
        Human-readable bandwidth ceiling, e.g. ``"10M"``, ``"500K"``,
        ``"1.5G"``.  ``None`` means unlimited.
    max_concurrent:
        Maximum number of concurrent download workers.  Used to derive the
        per-task cap.
    """

    def __init__(
        self,
        max_bandwidth: Optional[str],
        max_concurrent: int = 1,
    ) -> None:
        self._max_concurrent = max(1, max_concurrent)
        self._global_bps: Optional[int] = None
        self._bucket: Optional[TokenBucket] = None

        if max_bandwidth:
            self._global_bps = parse_bandwidth(max_bandwidth)
            self._bucket = TokenBucket(self._global_bps)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """``True`` when a global cap is configured."""
        return self._global_bps is not None

    @property
    def global_bps(self) -> Optional[int]:
        """Global ceiling in bytes per second, or ``None`` if unlimited."""
        return self._global_bps

    def per_task_rate_arg(self, max_concurrent: int) -> Optional[str]:
        """Return a yt-dlp ``-r`` argument value for one task.

        The argument is derived by dividing the global cap across
        *max_concurrent* — the **maximum** number of simultaneous workers
        configured for the queue, not the current active count.

        Using the static maximum is the only way to guarantee the global cap
        is never exceeded: if we divided by the current active count, an early
        worker would get a large share, and later workers would inherit a
        smaller share, but the early worker's subprocess keeps its original
        (too-large) ``-r`` value — allowing the aggregate to exceed the cap.

        With ``global_bps / max_concurrent``, every worker always gets the
        same share.  When fewer than ``max_concurrent`` workers are running
        the total bandwidth is proportionally less than the cap — a safe
        under-use, not an over-use.

        Returns ``None`` when no global cap is set (callers should then fall
        back to the per-task ``limit_rate`` if any).
        """
        if self._global_bps is None:
            return None
        workers = max(1, max_concurrent)
        return format_rate(max(1, self._global_bps // workers))

    def consume(self, n: int) -> None:
        """Block until *n* bytes are permitted by the global token bucket.

        No-op when no global cap is configured.
        """
        if self._bucket is not None:
            self._bucket.consume(n)

    def update_rate(self, new_bandwidth: Optional[str]) -> None:
        """Hot-update the global bandwidth cap at runtime.

        Pass ``None`` to remove the cap entirely.
        """
        if new_bandwidth is None:
            self._global_bps = None
            self._bucket = None
        else:
            bps = parse_bandwidth(new_bandwidth)
            self._global_bps = bps
            if self._bucket is not None:
                self._bucket.rate = bps
            else:
                self._bucket = TokenBucket(bps)
