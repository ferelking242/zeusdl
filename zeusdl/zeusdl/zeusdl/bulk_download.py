"""
ZeusDL Bulk Downloader — download every video from a playlist/listing URL.

Features
────────
• Auto-paginates through any playlist URL (BangBros, YouTube, etc.)
• Concurrent downloads (configurable --workers)
• Resumes: skips files already downloaded
• Saves a download log (JSON) for inspection / re-run
• Optional per-file subdirectory by uploader/model name

CLI usage
─────────
    zeusdl download-all URL [options]

    Options:
      --output-dir DIR       Where to save files  (default: ./downloads)
      --workers N            Concurrent download workers  (default: 3)
      --cookies FILE         Cookies file for authenticated sites
      --format QUALITY       e.g. 'best', '1080p', '720p'
      --no-resume            Re-download already existing files
      --log FILE             Path to progress JSON log
      --limit N              Stop after N videos (useful for testing)
      --retries N            Per-video retry count  (default: 3)
      --sleep SECS           Sleep between requests (default: 1.5)
      --flat-playlist        Don't recurse into sub-playlists

Python API
──────────
    from zeusdl.bulk_download import BulkDownloader

    dl = BulkDownloader(output_dir='./downloads', cookies='~/bb.txt')
    dl.run('https://site-ma.bangbros.com/scenes?addon=5971')
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


_DEFAULT_WORKERS = 3
_DEFAULT_SLEEP = 1.5
_LOG_FILE = 'zeus_download_log.json'


class BulkDownloader:
    """
    Download all videos from a URL using zeusdl as a subprocess.

    Parameters
    ----------
    output_dir : str
        Root folder where videos are saved.
    cookies : str, optional
        Path to a Netscape cookies file.
    workers : int
        Number of parallel download workers.
    quality : str
        Format/quality selector (e.g. 'best', '1080p').
    resume : bool
        If True (default), skip files that already exist.
    log_file : str
        Path to the JSON progress log.
    limit : int, optional
        Max number of videos to download (None = no limit).
    retries : int
        Per-video retry count.
    sleep : float
        Seconds to sleep between playlist-page requests.
    """

    def __init__(
        self,
        output_dir: str = './downloads',
        cookies: Optional[str] = None,
        workers: int = _DEFAULT_WORKERS,
        quality: str = 'best',
        resume: bool = True,
        log_file: Optional[str] = None,
        limit: Optional[int] = None,
        retries: int = 3,
        sleep: float = _DEFAULT_SLEEP,
    ):
        self.output_dir = Path(output_dir).resolve()
        self.cookies = cookies
        self.workers = workers
        self.quality = quality
        self.resume = resume
        self.log_file = Path(log_file) if log_file else self.output_dir / _LOG_FILE
        self.limit = limit
        self.retries = retries
        self.sleep = sleep

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._log: dict = self._load_log()

    # ── Log management ────────────────────────────────────────────────────────

    def _load_log(self) -> dict:
        if self.log_file.exists():
            try:
                return json.loads(self.log_file.read_text())
            except Exception:
                pass
        return {'downloaded': [], 'failed': [], 'skipped': []}

    def _save_log(self):
        try:
            self.log_file.write_text(json.dumps(self._log, indent=2))
        except Exception:
            pass

    def _mark(self, key: str, url: str):
        with self._lock:
            if url not in self._log[key]:
                self._log[key].append(url)
            self._save_log()

    def _is_downloaded(self, url: str) -> bool:
        return self.resume and url in self._log.get('downloaded', [])

    # ── Playlist extraction ───────────────────────────────────────────────────

    def _collect_urls(self, source_url: str) -> list[str]:
        """Use zeusdl --flat-playlist to enumerate all video URLs."""
        print(f'[bulk] Extracting URLs from: {source_url}')
        cmd = [
            sys.executable, '-m', 'zeusdl',
            '--flat-playlist',
            '--print', 'url',
            '--no-warnings',
            '--quiet',
        ]
        if self.cookies:
            cmd += ['--cookies', str(self.cookies)]
        cmd.append(source_url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            urls = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith('http')]
            print(f'[bulk] Found {len(urls)} URLs')
            return urls
        except Exception as e:
            print(f'[bulk] Error collecting URLs: {e}', file=sys.stderr)
            return []

    # ── Single video download ─────────────────────────────────────────────────

    def _download_one(self, url: str) -> bool:
        """Download a single video. Returns True on success."""
        if self._is_downloaded(url):
            print(f'[skip] {url}')
            self._mark('skipped', url)
            return True

        output_tmpl = str(self.output_dir / '%(uploader)s' / '%(title)s.%(ext)s')
        cmd = [
            sys.executable, '-m', 'zeusdl',
            '--no-playlist',
            '--no-warnings',
            '-o', output_tmpl,
        ]
        if self.cookies:
            cmd += ['--cookies', str(self.cookies)]
        if self.quality and self.quality != 'best':
            # Build format selector
            from .zeus_engine import select_format_by_quality
            fmt = select_format_by_quality(self.quality)
            cmd += ['-f', fmt]

        cmd += ['--retries', str(self.retries)]
        cmd.append(url)

        for attempt in range(1, self.retries + 1):
            try:
                proc = subprocess.run(cmd, timeout=3600)
                if proc.returncode == 0:
                    self._mark('downloaded', url)
                    return True
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
            except subprocess.TimeoutExpired:
                print(f'[bulk] Timeout on attempt {attempt}: {url}', file=sys.stderr)
            except Exception as e:
                print(f'[bulk] Error on attempt {attempt}: {e}', file=sys.stderr)

        self._mark('failed', url)
        return False

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(self, source_url: str) -> dict:
        """
        Download all videos from source_url.

        Returns a summary dict: {'total', 'ok', 'failed', 'skipped'}.
        """
        urls = self._collect_urls(source_url)
        if not urls:
            print('[bulk] No URLs found. Check the source URL and your cookies.')
            return {'total': 0, 'ok': 0, 'failed': 0, 'skipped': 0}

        if self.limit:
            urls = urls[:self.limit]
            print(f'[bulk] Limited to first {self.limit} videos')

        total = len(urls)
        ok = failed = skipped = 0
        done = 0

        print(f'[bulk] Starting download of {total} videos → {self.output_dir}')
        print(f'[bulk] Workers: {self.workers} | Quality: {self.quality}')
        print()

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._download_one, u): u for u in urls}
            for fut in as_completed(futures):
                url = futures[fut]
                done += 1
                try:
                    success = fut.result()
                    if url in self._log.get('skipped', []):
                        skipped += 1
                    elif success:
                        ok += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f'[bulk] !! {url}: {e}', file=sys.stderr)

                pct = done / total * 100
                print(f'[bulk] Progress: {done}/{total} ({pct:.1f}%) | '
                      f'OK={ok} FAIL={failed} SKIP={skipped}')
                time.sleep(self.sleep)

        summary = {'total': total, 'ok': ok, 'failed': failed, 'skipped': skipped}
        print(f'\n[bulk] ✅ Done! {ok}/{total} downloaded, {failed} failed, {skipped} skipped')
        print(f'[bulk] Log: {self.log_file}')
        return summary


# ── CLI entry point ───────────────────────────────────────────────────────────

def main_bulk_download(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        prog='zeusdl download-all',
        description='Download every video from a playlist/listing URL.',
    )
    p.add_argument('url', help='Playlist or listing URL')
    p.add_argument('--output-dir', '-o', default='./downloads',
                   help='Output directory (default: ./downloads)')
    p.add_argument('--workers', '-w', type=int, default=_DEFAULT_WORKERS,
                   help=f'Concurrent workers (default: {_DEFAULT_WORKERS})')
    p.add_argument('--cookies', default=None, help='Cookies file path')
    p.add_argument('--format', default='best', help='Quality: best, 1080p, 720p…')
    p.add_argument('--no-resume', action='store_true', help='Re-download existing files')
    p.add_argument('--log', default=None, help='Path to progress log file')
    p.add_argument('--limit', type=int, default=None, help='Max videos to download')
    p.add_argument('--retries', type=int, default=3, help='Per-video retries (default: 3)')
    p.add_argument('--sleep', type=float, default=_DEFAULT_SLEEP,
                   help=f'Sleep between requests (default: {_DEFAULT_SLEEP}s)')

    args = p.parse_args(argv)

    dl = BulkDownloader(
        output_dir=args.output_dir,
        cookies=args.cookies,
        workers=args.workers,
        quality=args.format,
        resume=not args.no_resume,
        log_file=args.log,
        limit=args.limit,
        retries=args.retries,
        sleep=args.sleep,
    )
    summary = dl.run(args.url)
    sys.exit(0 if summary['failed'] == 0 else 1)
