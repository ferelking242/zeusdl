"""
ZeusDL Smart Extractor
Handles unknown sites that Zeus doesn't have a dedicated extractor for.

Uses Scrapling for intelligent, auto-repairing extraction:
- Stealth page fetching (anti-bot evasion)
- Auto-repair CSS selectors when HTML changes
- JSON-LD structured data extraction
- Multi-strategy media URL detection
- Caches extraction patterns for future visits
"""

import json
import re
import os
import hashlib
import time
import urllib.parse

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    int_or_none,
    url_or_none,
    traverse_obj,
    try_call,
)


class SmartExtractorIE(InfoExtractor):
    """
    Smart extractor powered by Scrapling for unknown/unsupported sites.
    Automatically detects and extracts video content using multiple strategies.
    """

    IE_NAME = 'smart'
    IE_DESC = 'Smart auto-extractor for unknown sites (powered by Scrapling)'
    _VALID_URL = r'.*'  # matches anything — used as last-resort fallback

    _PATTERN_CACHE_DIR = None
    _pattern_cache = {}

    _MEDIA_EXTENSIONS = {
        'video': ['mp4', 'webm', 'ogg', 'ogv', 'avi', 'mov', 'mkv', 'flv', 'm4v', '3gp', 'ts'],
        'audio': ['mp3', 'aac', 'wav', 'flac', 'm4a', 'opus', 'ogg'],
        'manifest': ['m3u8', 'mpd', 'f4m'],
    }

    @classmethod
    def _get_cache_path(cls):
        cache_dir = cls._PATTERN_CACHE_DIR or os.path.join(
            os.path.expanduser('~'), '.cache', 'zeusdl', 'smart_extractor')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, 'patterns.json')

    @classmethod
    def _load_pattern_cache(cls):
        if cls._pattern_cache:
            return cls._pattern_cache
        try:
            path = cls._get_cache_path()
            if os.path.exists(path):
                with open(path) as f:
                    cls._pattern_cache = json.load(f)
        except Exception:
            cls._pattern_cache = {}
        return cls._pattern_cache

    @classmethod
    def _save_pattern_cache(cls):
        try:
            path = cls._get_cache_path()
            with open(path, 'w') as f:
                json.dump(cls._pattern_cache, f, indent=2)
        except Exception:
            pass

    @classmethod
    def _get_site_key(cls, url):
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc

    @classmethod
    def _cache_successful_pattern(cls, url, pattern_info):
        cache = cls._load_pattern_cache()
        site_key = cls._get_site_key(url)
        cache[site_key] = {
            'url_pattern': pattern_info.get('url_pattern'),
            'selector': pattern_info.get('selector'),
            'strategy': pattern_info.get('strategy'),
            'last_success': int(time.time()),
            'success_count': cache.get(site_key, {}).get('success_count', 0) + 1,
        }
        cls._pattern_cache = cache
        cls._save_pattern_cache()

    @classmethod
    def _get_cached_pattern(cls, url):
        cache = cls._load_pattern_cache()
        site_key = cls._get_site_key(url)
        entry = cache.get(site_key)
        if entry:
            # Cache entries expire after 7 days
            age = int(time.time()) - entry.get('last_success', 0)
            if age < 7 * 24 * 3600:
                return entry
        return None

    def _classify_url(self, url):
        """Determine what type of media URL this is."""
        ext = determine_ext(url, default_ext='').lower()
        if ext in self._MEDIA_EXTENSIONS['manifest']:
            return 'manifest', ext
        if ext in self._MEDIA_EXTENSIONS['video']:
            return 'video', ext
        if ext in self._MEDIA_EXTENSIONS['audio']:
            return 'audio', ext
        return 'unknown', ext

    def _build_format_from_url(self, media_url, video_id, url_type='video', ext='mp4'):
        """Build a format dict from a raw media URL."""
        fmt = {
            'url': media_url,
            'format_id': hashlib.md5(media_url.encode()).hexdigest()[:8],
        }
        if url_type == 'manifest':
            if ext == 'm3u8':
                fmts, subs = self._extract_m3u8_formats_and_subtitles(
                    media_url, video_id, ext='mp4', fatal=False)
                return fmts, subs
            elif ext == 'mpd':
                fmts, subs = self._extract_mpd_formats_and_subtitles(
                    media_url, video_id, fatal=False)
                return fmts, subs
        fmt['ext'] = ext
        return [fmt], {}

    def _extract_via_scrapling(self, url):
        """Use Scrapling to fetch and extract media from the page."""
        try:
            from ..scrapling_engine import smart_fetch_and_extract, is_available
        except ImportError:
            return None

        if not is_available():
            return None

        self.report_warning(f'Using Scrapling smart extractor for unknown site: {url}')
        extracted = smart_fetch_and_extract(url)
        if not extracted:
            return None

        return extracted

    def _extract_via_webpage(self, url):
        """Fallback: use ZeusDL's built-in webpage fetching and regex parsing."""
        try:
            webpage = self._download_webpage(url, 'smart_extract', fatal=False)
            if not webpage:
                return None

            from ..scrapling_engine import extract_media_from_page
            return extract_media_from_page(url, webpage)
        except Exception:
            return None

    def _real_extract(self, url):
        video_id = self._generic_id(url)
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc

        # Check cache for previously successful pattern
        cached = self._get_cached_pattern(url)
        strategy_hint = cached.get('strategy') if cached else None

        # Try Scrapling first (preferred: stealth + auto-repair)
        extracted = self._extract_via_scrapling(url)

        # Fallback to built-in webpage fetcher
        if not extracted:
            extracted = self._extract_via_webpage(url)

        if not extracted:
            raise ExtractorError(
                f'SmartExtractor: Could not extract media from {url}. '
                'Try installing scrapling: pip install scrapling',
                expected=True)

        title = extracted.get('title') or domain
        thumbnail = extracted.get('thumbnail')
        description = extracted.get('description')

        # 1. Best case: JSON-LD with contentUrl
        json_ld_results = extracted.get('json_ld_results', [])
        if json_ld_results:
            best = json_ld_results[0]
            media_url = best.get('url')
            if media_url:
                url_type, ext = self._classify_url(media_url)
                formats, subtitles = self._build_format_from_url(media_url, video_id, url_type, ext)
                if formats:
                    self._cache_successful_pattern(url, {'strategy': 'json_ld'})
                    return {
                        'id': video_id,
                        'title': best.get('title') or title,
                        'description': best.get('description') or description,
                        'thumbnail': best.get('thumbnail') or thumbnail,
                        'duration': int_or_none(best.get('duration')),
                        'formats': formats,
                        'subtitles': subtitles,
                        'webpage_url': url,
                        'extractor': self.IE_NAME,
                    }

        # 2. Embed URLs (iframes pointing to known players)
        embed_urls = extracted.get('embed_urls', [])
        if embed_urls:
            # Return the first embed for recursive processing
            embed_url = embed_urls[0]
            self._cache_successful_pattern(url, {'strategy': 'embed', 'url_pattern': embed_url})
            return self.url_result(embed_url, video_title=title)

        # 3. Direct media URLs
        media_urls = extracted.get('urls', [])
        if not media_urls:
            raise ExtractorError(
                f'SmartExtractor: No media URLs found at {url}',
                expected=True)

        # Prioritize: manifests > video > audio > unknown
        prioritized = []
        for media_url in media_urls:
            url_type, ext = self._classify_url(media_url)
            priority = {'manifest': 0, 'video': 1, 'audio': 2, 'unknown': 3}[url_type]
            prioritized.append((priority, url_type, ext, media_url))
        prioritized.sort(key=lambda x: x[0])

        all_formats = []
        all_subtitles = {}

        for priority, url_type, ext, media_url in prioritized:
            try:
                fmts, subs = self._build_format_from_url(media_url, video_id, url_type, ext)
                all_formats.extend(fmts)
                for lang, sub_list in subs.items():
                    all_subtitles.setdefault(lang, []).extend(sub_list)
            except Exception:
                continue

        if not all_formats:
            raise ExtractorError(
                f'SmartExtractor: Found URLs but could not build formats for {url}',
                expected=True)

        self._cache_successful_pattern(url, {
            'strategy': 'direct_url',
            'url_pattern': prioritized[0][3] if prioritized else None,
        })

        return {
            'id': video_id,
            'title': title,
            'description': description,
            'thumbnail': thumbnail,
            'formats': all_formats,
            'subtitles': all_subtitles,
            'webpage_url': url,
            'extractor': self.IE_NAME,
        }
