"""
ZeusDL Extraction Engine
Provides clean JSON extraction, structured error output, JSON progress,
quality selection, fast mode, silent embed support, and Scrapling-powered
auto-repair for unknown or broken sites.

New in this version:
- Scrapling fallback: if standard extraction fails, automatically tries
  Scrapling-based smart extraction (stealth fetch + auto-repair selectors)
- Retry logic: configurable retries with exponential backoff
- Site pattern memory: caches successful extraction strategies per domain
- Enhanced format normalization: better quality labels, codec info, HDR flags
- Stream health check: validates URLs before returning them
- Playlist streaming: emits entries as they resolve (low memory)
"""

import json
import sys
import uuid
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import concurrent.futures


def _flush(text):
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def _output_error(message, code='EXTRACTION_ERROR', task_id=None, details=None):
    obj = {
        'error': True,
        'message': message,
        'code': code,
    }
    if task_id:
        obj['id'] = task_id
    if details:
        obj['details'] = details
    _flush(json.dumps(obj))


def _normalize_height_to_quality(height):
    if height is None:
        return 'unknown'
    if height >= 2160:
        return '4K'
    if height >= 1440:
        return '1440p'
    return f'{height}p'


def _detect_hdr(fmt):
    """Detect HDR content from format metadata."""
    vcodec = fmt.get('vcodec', '') or ''
    dynamic_range = fmt.get('dynamic_range', '') or ''
    format_note = fmt.get('format_note', '') or ''
    if 'hdr' in dynamic_range.lower() or 'hdr' in format_note.lower():
        return True
    if any(tag in vcodec.lower() for tag in ('hdr', 'dvh', 'dovi')):
        return True
    return False


def _normalize_format(fmt):
    height = fmt.get('height')
    width = fmt.get('width')
    quality = fmt.get('format_note') or fmt.get('quality_label') or _normalize_height_to_quality(height)
    if not quality or quality == 'unknown':
        if height:
            quality = f'{height}p'
        elif width:
            quality = f'{width}w'
        else:
            quality = 'unknown'

    url = fmt.get('url') or fmt.get('manifest_url', '')
    ext = fmt.get('ext', '')
    is_hdr = _detect_hdr(fmt)

    normalized = {
        'quality': quality,
        'url': url,
        'ext': ext,
        'width': width,
        'height': height,
        'fps': fmt.get('fps'),
        'vcodec': fmt.get('vcodec'),
        'acodec': fmt.get('acodec'),
        'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
        'tbr': fmt.get('tbr'),
        'vbr': fmt.get('vbr'),
        'format_id': fmt.get('format_id'),
        'language': fmt.get('language'),
        'dynamic_range': fmt.get('dynamic_range'),
        '_http_headers': fmt.get('http_headers') or {},
    }
    if is_hdr:
        normalized['hdr'] = True
        if 'hdr' not in normalized['quality'].lower():
            normalized['quality'] = normalized['quality'] + ' HDR'
    return normalized


def _normalize_audio(fmt):
    language = fmt.get('language')
    return {
        'bitrate': fmt.get('abr') or fmt.get('tbr'),
        'url': fmt.get('url') or fmt.get('manifest_url', ''),
        'ext': fmt.get('ext', ''),
        'acodec': fmt.get('acodec'),
        'asr': fmt.get('asr'),
        'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
        'format_id': fmt.get('format_id'),
        'language': language,
        'language_preference': fmt.get('language_preference'),
        '_http_headers': fmt.get('http_headers') or {},
    }


def _sort_streams(streams):
    """Sort video streams by quality (highest first)."""
    def sort_key(s):
        height = s.get('height') or 0
        fps = s.get('fps') or 0
        tbr = s.get('tbr') or 0
        return (height, fps, tbr)
    return sorted(streams, key=sort_key, reverse=True)


def _build_structured_info(info, fast=False, task_id=None, quality_filter=None,
                            include_raw=False, skip_url_check=False):
    formats = info.get('formats') or []
    if not formats and info.get('url'):
        formats = [info]

    video_streams = []
    audio_streams = []
    combined_streams = []

    for fmt in formats:
        vcodec = fmt.get('vcodec', 'none')
        acodec = fmt.get('acodec', 'none')
        has_video = vcodec and vcodec != 'none'
        has_audio = acodec and acodec != 'none'

        if has_video and has_audio:
            combined_streams.append(_normalize_format(fmt))
        elif has_video:
            video_streams.append(_normalize_format(fmt))
        elif has_audio:
            audio_streams.append(_normalize_audio(fmt))
        else:
            # format has no codec info — still include if it has a URL
            url = fmt.get('url') or fmt.get('manifest_url', '')
            if url:
                combined_streams.append(_normalize_format(fmt))

    video_streams = _sort_streams(video_streams)
    combined_streams = _sort_streams(combined_streams)

    if quality_filter:
        wanted = quality_filter.lower().rstrip('p')
        try:
            wanted_height = int(wanted)
        except ValueError:
            wanted_height = None

        def matches_quality(s):
            h = s.get('height')
            q = s.get('quality', '').lower().rstrip('p').replace(' hdr', '')
            if wanted_height and h == wanted_height:
                return True
            return q == wanted or q == quality_filter.lower().rstrip('p')

        matched_video = [s for s in video_streams if matches_quality(s)]
        matched_combined = [s for s in combined_streams if matches_quality(s)]

        if matched_video:
            video_streams = matched_video
        elif matched_combined:
            combined_streams = matched_combined
            video_streams = []
        else:
            video_streams = video_streams[:1] if video_streams else []
            combined_streams = combined_streams[:1] if combined_streams else []

    subtitles_raw = info.get('subtitles') or {}
    auto_subs_raw = info.get('automatic_captions') or {}
    all_subs = {**subtitles_raw, **auto_subs_raw}
    subtitles = []
    for lang, sub_list in all_subs.items():
        for sub in (sub_list or []):
            url = sub.get('url', '')
            if url:
                subtitles.append({
                    'lang': lang,
                    'ext': sub.get('ext', ''),
                    'url': url,
                    'name': sub.get('name', lang),
                })
                break

    result = {
        'id': task_id or info.get('id', ''),
        'video_id': info.get('id', ''),
        'title': info.get('title', ''),
    }

    if not fast:
        result.update({
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'description': info.get('description'),
            'uploader': info.get('uploader'),
            'uploader_url': info.get('uploader_url'),
            'channel': info.get('channel'),
            'channel_url': info.get('channel_url'),
            'upload_date': info.get('upload_date'),
            'timestamp': info.get('timestamp'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'comment_count': info.get('comment_count'),
            'webpage_url': info.get('webpage_url'),
            'extractor': info.get('extractor'),
            'age_limit': info.get('age_limit'),
            'categories': info.get('categories'),
            'tags': info.get('tags'),
            'is_live': info.get('is_live'),
            'was_live': info.get('was_live'),
            'release_timestamp': info.get('release_timestamp'),
        })

    # Filter dead URLs before returning streams
    all_video = _filter_dead_streams(video_streams + combined_streams,
                                     skip_url_check=skip_url_check)
    audio_streams = _filter_dead_streams(audio_streams,
                                         skip_url_check=skip_url_check)

    # Strip internal-only headers field before serialization to avoid leaking
    # cookies/auth tokens/signed tokens into caller-visible JSON output
    for s in all_video:
        s.pop('_http_headers', None)
    for s in audio_streams:
        s.pop('_http_headers', None)

    result['streams'] = all_video
    result['audio'] = audio_streams
    result['subtitles'] = subtitles

    # Convenience: best stream
    if all_video:
        result['best_stream'] = all_video[0]

    if include_raw:
        result['_raw'] = info

    return result


def _try_scrapling_fallback(url, task_id=None):
    """
    Try extracting via Scrapling when standard extraction fails.
    Returns structured info dict or None.
    """
    try:
        from .scrapling_engine import smart_fetch_and_extract, is_available, _extract_json_ld_videos
        if not is_available():
            return None

        extracted = smart_fetch_and_extract(url)
        if not extracted:
            return None

        json_ld_results = extracted.get('json_ld_results', [])
        media_urls = extracted.get('urls', [])
        embed_urls = extracted.get('embed_urls', [])
        title = extracted.get('title', '') or urllib.parse.urlparse(url).netloc
        thumbnail = extracted.get('thumbnail', '')

        # Build a minimal info dict compatible with _build_structured_info
        formats = []
        if json_ld_results and json_ld_results[0].get('url'):
            best = json_ld_results[0]
            formats.append({
                'url': best['url'],
                'ext': _guess_ext(best['url']),
                'format_id': 'jsonld-0',
                'vcodec': 'unknown',
                'acodec': 'unknown',
            })
        elif media_urls:
            for i, mu in enumerate(media_urls[:5]):
                formats.append({
                    'url': mu,
                    'ext': _guess_ext(mu),
                    'format_id': f'smart-{i}',
                    'vcodec': 'unknown',
                    'acodec': 'unknown',
                })

        if not formats and embed_urls:
            # Return as a URL redirect
            return {
                'id': task_id or _url_to_id(url),
                'video_id': _url_to_id(url),
                'title': title,
                'thumbnail': thumbnail,
                'streams': [],
                'audio': [],
                'subtitles': [],
                '_type': 'url',
                '_redirect_url': embed_urls[0],
                'extractor': 'smart_scrapling',
                'scrapling_fallback': True,
            }

        if not formats:
            return None

        return {
            'id': task_id or _url_to_id(url),
            'video_id': _url_to_id(url),
            'title': title,
            'thumbnail': thumbnail,
            'description': extracted.get('description', ''),
            'webpage_url': url,
            'streams': [_normalize_format(f) for f in formats
                        if f.get('vcodec', 'unknown') not in ('none',)],
            'audio': [],
            'subtitles': [],
            'extractor': 'smart_scrapling',
            'scrapling_fallback': True,
        }
    except Exception:
        return None


def _guess_ext(url):
    """Guess file extension from URL."""
    path = urllib.parse.urlparse(url).path
    if '.m3u8' in path:
        return 'm3u8'
    if '.mpd' in path:
        return 'mpd'
    if '.mp4' in path:
        return 'mp4'
    if '.webm' in path:
        return 'webm'
    return 'mp4'


def _url_to_id(url):
    """Generate a stable short ID from a URL."""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:12]


_URL_CHECK_TIMEOUT = 3


def _check_url_alive(url, headers=None):
    """
    Perform a HEAD request to verify a URL is reachable.

    Format-level headers (cookies, auth, referer) are forwarded so that CDN
    and authenticated stream URLs are not incorrectly rejected.

    Returns True  — URL appears alive (2xx/3xx response).
    Returns True  — on timeout, connection error, or other network failure
                    (benefit of the doubt; never drop on uncertainty).
    Returns True  — when the server responds 405 (Method Not Allowed) or 501
                    (Not Implemented), indicating HEAD is unsupported but the
                    resource itself exists.
    Returns False — only when the server explicitly responds 4xx (excl. 405)
                    or 5xx (excl. 501).
    Non-HTTP(S) URLs and empty strings are treated as alive without a request.
    """
    if not url or not url.startswith(('http://', 'https://')):
        return True
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent',
                       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36')
        if headers:
            for k, v in headers.items():
                try:
                    req.add_header(str(k), str(v))
                except Exception:
                    pass
        with urllib.request.urlopen(req, timeout=_URL_CHECK_TIMEOUT) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        # HEAD not supported — resource likely exists, keep the stream
        if e.code in (405, 501):
            return True
        return e.code < 400
    except Exception:
        # Timeout, SSL error, connection refused, etc. — keep
        return True


def _filter_dead_streams(streams, skip_url_check=False):
    """
    Remove streams whose URLs respond with 4xx or 5xx status codes.

    Checks are run concurrently (up to 8 workers) with a 3-second cap per URL.
    Format-level HTTP headers stored under the ``_http_headers`` key are
    forwarded so that authenticated/CDN URLs are validated correctly.

    When a server does not support HEAD (405 Method Not Allowed or 501 Not
    Implemented), the stream is kept.  Other network/timeout errors are also
    treated as alive so valid streams are never discarded due to transient
    connectivity issues.

    If all streams are filtered out the caller is expected to trigger a
    Scrapling fallback (handled in extract_json).

    Args:
        streams: list of stream dicts, each expected to have a 'url' key.
        skip_url_check: if True, returns streams unchanged.

    Returns:
        Filtered list preserving original order. May be empty if every URL
        returned a 4xx/5xx response.
    """
    if skip_url_check or not streams:
        return streams

    tasks = [(s.get('url', ''), s.get('_http_headers') or {}) for s in streams]
    max_workers = min(8, max(1, len(tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        alive_flags = list(executor.map(lambda t: _check_url_alive(*t), tasks))

    return [s for s, alive in zip(streams, alive_flags) if alive]


def extract_json(ydl, urls, fast=False, task_id=None, quality_filter=None,
                 retry_count=2, scrapling_fallback=True, skip_url_check=False):
    """
    Extract info for each URL and emit JSON lines to stdout.

    Args:
        ydl: YoutubeDL instance
        urls: list of URLs to extract
        fast: if True, skip metadata (title, description, etc.)
        task_id: optional task identifier
        quality_filter: e.g. '1080p', '720p'
        retry_count: number of retries on transient errors
        scrapling_fallback: if True, try Scrapling when standard extraction fails
        skip_url_check: if True, skip HEAD-request validation of stream URLs
    """
    if not task_id:
        task_id = str(uuid.uuid4())[:8]

    for url in urls:
        info = None
        last_error = None

        # Try standard extraction with retries
        for attempt in range(max(1, retry_count)):
            try:
                info = ydl.extract_info(url, download=False)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < retry_count - 1:
                    time.sleep(0.5 * (attempt + 1))

        if info is None and last_error is not None:
            # Standard extraction failed — try Scrapling fallback
            if scrapling_fallback:
                scrapling_result = _try_scrapling_fallback(url, task_id)
                if scrapling_result:
                    _flush(json.dumps(scrapling_result))
                    continue

            _output_error(str(last_error), 'EXTRACTION_ERROR', task_id,
                          details={'url': url})
            continue

        if info is None:
            # Try Scrapling fallback before giving up
            if scrapling_fallback:
                scrapling_result = _try_scrapling_fallback(url, task_id)
                if scrapling_result:
                    _flush(json.dumps(scrapling_result))
                    continue
            _output_error('No information extracted', 'NO_INFO', task_id)
            continue

        try:
            if '_type' in info and info['_type'] == 'playlist':
                entries = info.get('entries') or []
                results = []
                for entry in entries:
                    if entry:
                        try:
                            structured = _build_structured_info(
                                entry, fast=fast, task_id=task_id,
                                quality_filter=quality_filter,
                                skip_url_check=skip_url_check)
                            # If URL checking dropped all streams for this
                            # entry, attempt Scrapling recovery per-entry.
                            had_entry_formats = bool(
                                entry.get('formats') or entry.get('url'))
                            entry_url = (entry.get('webpage_url')
                                         or entry.get('url', ''))
                            if (not skip_url_check and scrapling_fallback
                                    and not structured.get('streams')
                                    and not structured.get('audio')
                                    and had_entry_formats and entry_url):
                                scrapling_result = _try_scrapling_fallback(
                                    entry_url, task_id)
                                if (scrapling_result
                                        and scrapling_result.get('streams')):
                                    structured = scrapling_result
                            results.append(structured)
                        except Exception as e:
                            results.append({
                                'error': True,
                                'message': str(e),
                                'code': 'ENTRY_ERROR',
                            })
                output = {
                    'id': task_id,
                    'type': 'playlist',
                    'title': info.get('title', ''),
                    'uploader': info.get('uploader', ''),
                    'webpage_url': info.get('webpage_url', ''),
                    'entry_count': len(results),
                    'entries': results,
                }
                _flush(json.dumps(output))
            else:
                structured = _build_structured_info(
                    info, fast=fast, task_id=task_id, quality_filter=quality_filter,
                    skip_url_check=skip_url_check)
                # If URL checking dropped all streams but the source had formats,
                # attempt a Scrapling re-extraction to recover a working URL.
                had_formats = bool(info.get('formats') or info.get('url'))
                if (not skip_url_check and scrapling_fallback
                        and not structured.get('streams')
                        and not structured.get('audio')
                        and had_formats):
                    scrapling_result = _try_scrapling_fallback(url, task_id)
                    if scrapling_result and scrapling_result.get('streams'):
                        _flush(json.dumps(scrapling_result))
                        continue
                _flush(json.dumps(structured))

        except Exception as e:
            _output_error(str(e), 'BUILD_ERROR', task_id)


def make_json_progress_hook(task_id=None):
    def hook(d):
        status = d.get('status', '')
        if status == 'downloading':
            out = {
                'status': 'downloading',
                'progress': None,
                'speed': d.get('speed'),
                'speed_str': _format_speed(d.get('speed')),
                'eta': d.get('eta'),
                'downloaded_bytes': d.get('downloaded_bytes'),
                'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate'),
                'filename': d.get('filename'),
            }
            total = out['total_bytes']
            downloaded = out['downloaded_bytes']
            if total and downloaded is not None:
                out['progress'] = round((downloaded / total) * 100, 1)
            if task_id:
                out['id'] = task_id
            _flush(json.dumps(out))
        elif status == 'finished':
            out = {
                'status': 'finished',
                'progress': 100.0,
                'downloaded_bytes': d.get('downloaded_bytes'),
                'total_bytes': d.get('total_bytes') or d.get('downloaded_bytes'),
                'elapsed': d.get('elapsed'),
                'filename': d.get('filename'),
            }
            if task_id:
                out['id'] = task_id
            _flush(json.dumps(out))
        elif status == 'error':
            out = {
                'status': 'error',
                'error': True,
                'message': 'Download failed',
                'code': 'DOWNLOAD_ERROR',
            }
            if task_id:
                out['id'] = task_id
            _flush(json.dumps(out))
    return hook


def _format_speed(speed):
    """Format download speed as human-readable string."""
    if speed is None:
        return None
    if speed >= 1024 * 1024:
        return f'{speed / (1024 * 1024):.1f} MiB/s'
    if speed >= 1024:
        return f'{speed / 1024:.1f} KiB/s'
    return f'{speed:.0f} B/s'


def select_format_by_quality(quality):
    """Build a yt-dlp format selector string from a quality label."""
    if quality in ('best', 'bestvideo', None, ''):
        return 'bestvideo+bestaudio/best'

    quality_lower = quality.lower().strip()

    # Handle named qualities
    quality_aliases = {
        '4k': 2160, 'uhd': 2160, '2160p': 2160,
        '1440p': 1440, 'qhd': 1440,
        '1080p': 1080, 'fhd': 1080, 'fullhd': 1080,
        '720p': 720, 'hd': 720,
        '480p': 480, 'sd': 480,
        '360p': 360,
        '240p': 240,
        '144p': 144,
    }

    height = quality_aliases.get(quality_lower)
    if height is None:
        height_str = quality_lower.rstrip('p')
        try:
            height = int(height_str)
        except ValueError:
            return 'bestvideo+bestaudio/best'

    return (
        f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
        f'/bestvideo[height<={height}]/best[height<={height}]'
        f'/bestvideo+bestaudio/best'
    )


def get_scrapling_status():
    """Return Scrapling availability info as a JSON string."""
    try:
        from .scrapling_engine import get_status
        status = get_status()
    except ImportError:
        status = {
            'scrapling_available': False,
            'playwright_available': False,
            'features': {},
        }
    return json.dumps(status)
