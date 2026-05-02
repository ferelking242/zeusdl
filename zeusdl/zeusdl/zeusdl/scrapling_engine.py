"""
ZeusDL Scrapling Engine
Integrates Scrapling for stealth page fetching, auto-repair element detection,
and intelligent media extraction from unknown or broken sites.

Scrapling auto-repairs broken selectors when site HTML changes — meaning Zeus
can keep working even after a site updates its layout.
"""

import re
import json
import urllib.parse

_scrapling_available = False
_playwright_available = False

try:
    from scrapling import Adaptor
    from scrapling.fetchers import Fetcher
    _scrapling_available = True
    try:
        from scrapling.fetchers import PlayWrightFetcher, StealthyFetcher
        _playwright_available = True
    except ImportError:
        pass
except ImportError:
    pass


# Common video URL patterns to search for
_VIDEO_URL_PATTERNS = [
    r'https?://[^\s\'"<>]+\.(?:mp4|webm|ogg|ogv|avi|mov|mkv|flv|m4v|3gp)[^\s\'"<>]*',
    r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
    r'https?://[^\s\'"<>]+\.mpd[^\s\'"<>]*',
    r'https?://[^\s\'"<>]+\.f4m[^\s\'"<>]*',
]

# Player-specific patterns
_PLAYER_PATTERNS = {
    'jwplayer': [
        r'jwplayer\s*\([^)]+\)\s*\.setup\s*\(\s*(\{.+?\})\s*\)',
        r'["\']?file["\']?\s*:\s*["\']([^"\']+\.(?:mp4|m3u8|webm|mpd)[^"\']*)["\']',
    ],
    'videojs': [
        r'videojs\s*\([^)]+\)[^;]+src\s*:\s*["\']([^"\']+)["\']',
        r'<source[^>]+src=["\']([^"\']+\.(?:mp4|m3u8|webm)[^"\']*)["\']',
    ],
    'html5': [
        r'<video[^>]*>\s*<source[^>]+src=["\']([^"\']+)["\']',
        r'<video[^>]+src=["\']([^"\']+)["\']',
    ],
    'hls': [
        r'["\']?(?:hls|stream|src|source|file|video_url|videoUrl)["\']?\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    ],
    'dash': [
        r'["\']?(?:dash|mpd|manifest)["\']?\s*[=:]\s*["\']([^"\']+\.mpd[^"\']*)["\']',
    ],
    'og_video': [
        r'<meta[^>]+property=["\']og:video["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video["\']',
    ],
}

# Selectors for common video player elements (Scrapling auto-repairs these)
_VIDEO_SELECTORS = [
    'video',
    'video source',
    'iframe[src*="player"]',
    'iframe[src*="embed"]',
    'iframe[src*="video"]',
    'div[data-video-url]',
    'div[data-src]',
    'div[data-url]',
    '[data-hls]',
    '[data-m3u8]',
    '[data-mp4]',
    '[data-stream]',
]

# JSON-LD types that contain video
_JSONLD_VIDEO_TYPES = {'VideoObject', 'Movie', 'TVEpisode', 'TVSeries', 'BroadcastEvent'}


def is_available():
    """Check if Scrapling is installed and available."""
    return _scrapling_available


def is_playwright_available():
    """Check if Scrapling's Playwright fetcher is available (for JS-heavy sites)."""
    return _playwright_available


def _extract_urls_from_text(text):
    """Extract all media URLs from raw text using regex patterns."""
    found = set()
    for pattern in _VIDEO_URL_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            url = match.group(0).rstrip('.,;\'"\n\r\t ')
            found.add(url)
    return list(found)


def _extract_player_urls(text):
    """Extract URLs from known player embed patterns."""
    found = set()
    for player, patterns in _PLAYER_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
                url = match.group(1).strip()
                if url.startswith('http'):
                    found.add(url)
                elif url.startswith('//'):
                    found.add('https:' + url)
    return list(found)


def _extract_json_ld_videos(text):
    """Extract video information from JSON-LD structured data."""
    results = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                              text, re.IGNORECASE | re.DOTALL):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and data.get('@graph'):
                items = data['@graph']
            else:
                items = [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get('@type', '')
                if item_type in _JSONLD_VIDEO_TYPES or 'Video' in str(item_type):
                    info = {}
                    content_url = item.get('contentUrl') or item.get('url')
                    embed_url = item.get('embedUrl')
                    if content_url:
                        info['url'] = content_url
                    elif embed_url:
                        info['url'] = embed_url
                        info['_type'] = 'url'
                    if info.get('url'):
                        info['title'] = item.get('name', '')
                        info['description'] = item.get('description', '')
                        info['thumbnail'] = (item.get('thumbnailUrl') or
                                             (item.get('thumbnail', {}) or {}).get('url', ''))
                        duration = item.get('duration')
                        if duration:
                            info['duration'] = _parse_iso8601_duration(duration)
                        results.append(info)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return results


def _parse_iso8601_duration(duration_str):
    """Parse ISO 8601 duration string to seconds."""
    if not duration_str:
        return None
    pattern = re.compile(
        r'P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?',
        re.IGNORECASE
    )
    m = pattern.match(duration_str)
    if not m:
        return None
    years, months, days, hours, minutes, seconds = m.groups()
    total = (int(years or 0) * 365 * 24 * 3600 +
             int(months or 0) * 30 * 24 * 3600 +
             int(days or 0) * 24 * 3600 +
             int(hours or 0) * 3600 +
             int(minutes or 0) * 60 +
             float(seconds or 0))
    return int(total) if total else None


def _extract_title_from_html(text):
    """Extract page title from HTML."""
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                         text, re.IGNORECASE)
    if og_title:
        return og_title.group(1).strip()

    title_tag = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
    if title_tag:
        return title_tag.group(1).strip()

    return None


def _extract_thumbnail_from_html(text):
    """Extract thumbnail from Open Graph or other meta tags."""
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                         text, re.IGNORECASE)
    if og_image:
        return og_image.group(1).strip()

    twitter_image = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                              text, re.IGNORECASE)
    if twitter_image:
        return twitter_image.group(1).strip()

    return None


def fetch_page_with_scrapling(url, use_stealth=False, use_playwright=False, headers=None):
    """
    Fetch a page using Scrapling with optional stealth/Playwright mode.

    Returns:
        tuple: (html_content, adaptor) where adaptor is a Scrapling Adaptor instance
               for smart element selection, or (None, None) on failure.
    """
    if not _scrapling_available:
        return None, None

    fetch_headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36'),
    }
    if headers:
        fetch_headers.update(headers)

    try:
        if use_playwright and _playwright_available:
            fetcher = StealthyFetcher()
            page = fetcher.fetch(url, headless=True, network_idle=True)
            if page and page.status == 200:
                return page.content, Adaptor(page.content, url=url)
        elif use_stealth and _playwright_available:
            fetcher = PlayWrightFetcher()
            page = fetcher.fetch(url, headless=True)
            if page and page.status == 200:
                return page.content, Adaptor(page.content, url=url)
        else:
            fetcher = Fetcher()
            page = fetcher.get(url, headers=fetch_headers)
            if page and page.status == 200:
                return page.content, Adaptor(page.content, url=url)
    except Exception:
        pass

    return None, None


def extract_media_from_page(url, html_content, adaptor=None):
    """
    Smart extraction of all media URLs from a page.

    Uses Scrapling adaptors when available for auto-repair CSS selector matching,
    falls back to regex-based extraction otherwise.

    Returns:
        dict with keys: urls, title, thumbnail, description, json_ld_results
    """
    result = {
        'urls': [],
        'title': None,
        'thumbnail': None,
        'description': None,
        'json_ld_results': [],
        'embed_urls': [],
    }

    if not html_content:
        return result

    # --- Title and thumbnail ---
    result['title'] = _extract_title_from_html(html_content)
    result['thumbnail'] = _extract_thumbnail_from_html(html_content)

    # --- JSON-LD structured data (most reliable) ---
    result['json_ld_results'] = _extract_json_ld_videos(html_content)

    # --- Scrapling-based DOM extraction (auto-repair) ---
    if adaptor and _scrapling_available:
        try:
            # Try each video selector with auto-repair
            for selector in _VIDEO_SELECTORS:
                try:
                    elements = adaptor.css(selector)
                    for el in (elements or []):
                        for attr in ('src', 'data-src', 'data-url', 'data-video-url',
                                     'data-hls', 'data-m3u8', 'data-mp4', 'data-stream',
                                     'data-manifest', 'data-file'):
                            val = el.attrib.get(attr, '')
                            if val and val.startswith('http'):
                                result['urls'].append(val)
                except Exception:
                    continue

            # Extract iframes for embed detection
            try:
                iframes = adaptor.css('iframe')
                for iframe in (iframes or []):
                    src = iframe.attrib.get('src', '')
                    if src and any(kw in src for kw in ('player', 'embed', 'video', 'watch', 'stream')):
                        result['embed_urls'].append(src if src.startswith('http') else
                                                    urllib.parse.urljoin(url, src))
            except Exception:
                pass

        except Exception:
            pass

    # --- Regex-based extraction (always runs as supplement) ---
    player_urls = _extract_player_urls(html_content)
    result['urls'].extend(player_urls)

    direct_urls = _extract_urls_from_text(html_content)
    result['urls'].extend(direct_urls)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for u in result['urls']:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    result['urls'] = deduped

    return result


def smart_fetch_and_extract(url, headers=None, try_stealth=True):
    """
    Main entry point: fetch a page and extract all media info.

    Tries multiple fetch strategies:
    1. Normal Scrapling Fetcher (fast)
    2. Playwright-based (if JS rendering needed and available)

    Returns:
        dict with all extracted media information
    """
    if not _scrapling_available:
        return None

    # First try: normal fetch
    html, adaptor = fetch_page_with_scrapling(url, headers=headers)

    # Second try: stealth/playwright if normal fetch failed or yielded no results
    if not html and try_stealth and _playwright_available:
        html, adaptor = fetch_page_with_scrapling(url, use_stealth=True, headers=headers)

    if not html:
        return None

    extracted = extract_media_from_page(url, html, adaptor)
    extracted['source_url'] = url
    extracted['fetched_with_scrapling'] = True

    return extracted


def repair_and_extract(url, broken_selector, page_html, fallback_patterns=None):
    """
    Auto-repair a broken CSS selector using Scrapling's fuzzy matching.
    When a site changes its HTML, Scrapling can still find the right element.

    Args:
        url: Page URL
        broken_selector: The CSS selector that was previously working
        page_html: Current HTML content of the page
        fallback_patterns: List of regex patterns to try if Scrapling fails

    Returns:
        list of found values, or empty list
    """
    if not _scrapling_available or not page_html:
        return []

    found = []
    try:
        adaptor = Adaptor(page_html, url=url, auto_match=True)
        # Scrapling's auto_match=True enables fuzzy element finding
        elements = adaptor.css(broken_selector, auto_match=True)
        for el in (elements or []):
            for attr in ('src', 'href', 'data-src', 'data-url', 'content'):
                val = el.attrib.get(attr, '')
                if val:
                    found.append(val)
            if not found:
                text = el.text
                if text and text.strip():
                    found.append(text.strip())
    except Exception:
        pass

    # Fallback to regex patterns if Scrapling auto-match failed
    if not found and fallback_patterns:
        for pattern in fallback_patterns:
            matches = re.findall(pattern, page_html, re.IGNORECASE)
            found.extend(matches)

    return found


def get_status():
    """Return status info about Scrapling availability."""
    return {
        'scrapling_available': _scrapling_available,
        'playwright_available': _playwright_available,
        'features': {
            'stealth_fetch': _playwright_available,
            'auto_repair': _scrapling_available,
            'smart_extract': _scrapling_available,
        },
    }
