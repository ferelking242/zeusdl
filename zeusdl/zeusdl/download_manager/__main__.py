"""
Command-line interface for the ZeusDL download queue manager.

Usage
─────
    python -m zeusdl.download_manager [options] URL [URL ...]

Options
    -j, --max-concurrent N      Maximum simultaneous downloads (default: 3)
    -B, --max-bandwidth RATE    Global bandwidth ceiling shared across all
                                concurrent workers, e.g. 10M, 500K, 1.5G.
                                Accepts the same unit suffixes as --rate-limit.
                                When unset, bandwidth is unlimited.
    -r, --rate-limit RATE       Per-task bandwidth cap passed directly to
                                zeusdl via -r.  Applies on top of (and
                                independently from) the global cap; the
                                stricter of the two limits wins.
    -f, --format SPEC           zeusdl format specifier (default: bestvideo+bestaudio/best)
    -o, --output-dir DIR        Directory where downloaded files are saved (default: .)
    -s, --session FILE          Session file for queue persistence across runs
        --retries N             Retry count per task (default: 10)
    -q, --quiet                 Suppress progress output

Examples
    # Cap total bandwidth at 10 MB/s across up to 3 concurrent downloads:
    python -m zeusdl.download_manager -B 10M URL1 URL2 URL3

    # Cap total bandwidth at 5 MB/s, each task additionally capped at 2 MB/s:
    python -m zeusdl.download_manager -B 5M -r 2M URL1 URL2 URL3
"""

from __future__ import annotations

import argparse
import sys

from .queue_manager import DownloadQueueManager
from .rate_limiter import parse_bandwidth
from .task import DownloadTask


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m zeusdl.download_manager",
        description="ZeusDL download queue with global bandwidth control.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "urls",
        metavar="URL",
        nargs="+",
        help="One or more URLs to download.",
    )
    p.add_argument(
        "-j", "--max-concurrent",
        metavar="N",
        type=int,
        default=3,
        help="Maximum simultaneous downloads (default: %(default)s).",
    )
    p.add_argument(
        "-B", "--max-bandwidth",
        metavar="RATE",
        default=None,
        help=(
            "Global bandwidth ceiling shared across all concurrent workers. "
            "Accepts K / M / G suffixes, e.g. 10M for 10 MB/s. "
            "Default: unlimited."
        ),
    )
    p.add_argument(
        "-r", "--rate-limit",
        metavar="RATE",
        default=None,
        help=(
            "Per-task bandwidth cap forwarded to zeusdl via -r. "
            "Applied independently of --max-bandwidth; the stricter limit wins."
        ),
    )
    p.add_argument(
        "-f", "--format",
        metavar="SPEC",
        default="bestvideo+bestaudio/best",
        help="zeusdl format specifier (default: %(default)s).",
    )
    p.add_argument(
        "-o", "--output-dir",
        metavar="DIR",
        default=".",
        help="Directory to save downloaded files (default: current directory).",
    )
    p.add_argument(
        "-s", "--session",
        metavar="FILE",
        default=None,
        help="JSON file for queue persistence across restarts.",
    )
    p.add_argument(
        "--retries",
        metavar="N",
        type=int,
        default=10,
        help="Retry count per failed task (default: %(default)s).",
    )
    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-task progress output.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate --max-bandwidth early so the user gets a clear error message.
    if args.max_bandwidth is not None:
        try:
            parse_bandwidth(args.max_bandwidth)
        except ValueError as exc:
            parser.error(f"--max-bandwidth: {exc}")

    # Validate --rate-limit early.
    if args.rate_limit is not None:
        try:
            parse_bandwidth(args.rate_limit)
        except ValueError as exc:
            parser.error(f"--rate-limit: {exc}")

    manager = DownloadQueueManager(
        max_concurrent=args.max_concurrent,
        session_file=args.session,
        max_bandwidth=args.max_bandwidth,
    )

    for url in args.urls:
        task = DownloadTask(
            url=url,
            output_dir=args.output_dir,
            format_spec=args.format,
            limit_rate=args.rate_limit,
            retries=args.retries,
        )
        manager.add(task)

    manager.start()
    try:
        manager.wait()
    except KeyboardInterrupt:
        print("\n[queue] Interrupted — stopping downloads.", file=sys.stderr)
        manager.stop()
        return 130

    errors = [
        t for t in manager.list_tasks()
        if t.state.value == "error"
    ]
    if errors:
        for t in errors:
            print(f"[queue] FAILED {t.task_id}: {t.error_message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
