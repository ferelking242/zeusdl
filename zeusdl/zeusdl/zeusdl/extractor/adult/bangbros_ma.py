"""
BangBros Member Area extractor (site-ma.bangbros.com).

Handles:
  • Individual scene pages
  • Studio/addon playlist pages  (e.g. ?addon=5971)
  • Model / performer pages
  • All-scenes listing (any page, auto-pagination)

Authentication
──────────────
The member area requires valid cookies from a logged-in session.

  zeusdl --cookies ~/bangbros_cookies.txt URL

Tip: log in at https://site-ma.bangbros.com in your browser, then
export cookies with "Get cookies.txt LOCALLY" (Chrome extension).

API
───
All data comes from https://site-api.project1service.com :

  GET /v2/releases/{id}                  — single scene
  GET /v2/releases?type=scene&...        — scene list
  GET /v2/performers                     — model list
  GET /v2/performers/{id}/releases       — model's scenes
  GET /v2/addons                         — subscribed studios
"""

import re
import urllib.parse

from ..common import InfoExtractor
from ...utils import (
    ExtractorError,
    int_or_none,
    str_or_none,
    unified_timestamp,
    url_or_none,
)

_DATA_API = 'https://site-api.project1service.com'
_AUTH_API = 'https://auth-service.project1service.com'
_SITE_URL = 'https://site-ma.bangbros.com/'

_FAKE_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)


# ── Shared helpers ──────────────────────────────────────────────────────────

def _extract_formats(videos, video_id):
    """Build yt-dlp format dicts from the Project1 API 'videos' object."""
    formats = []
    prefer = ['full', 'clip', 'mediabook']
    for vtype in sorted(videos, key=lambda t: prefer.index(t) if t in prefer else 99):
        files = (videos.get(vtype) or {}).get('files') or {}
        is_full = vtype == 'full'
        for label, info in files.items():
            urls = info.get('urls') or {}
            url = urls.get('download') or urls.get('view')
            if not url:
                continue
            height = int_or_none(re.search(r'(\d+)p', label or ''), group=1)
            formats.append({
                'url': url,
                'ext': 'mp4',
                'format_id': f'{vtype}-{label}',
                'height': height,
                'fps': int_or_none(info.get('fps')),
                'filesize': int_or_none(info.get('sizeBytes')),
                'vcodec': info.get('codec'),
                'quality': 1 if is_full else -1,
            })
    return formats


def _pick_thumbnail(result):
    for key in ('imageMasters', 'images', 'screenshots'):
        imgs = result.get(key) or []
        if imgs:
            src = imgs[0].get('src') or imgs[0].get('url') or imgs[0].get('path')
            if src:
                return src
    return None


def _result_to_info(result):
    """Convert a Project1 API release result dict to an info_dict."""
    videos = result.get('videos') or {}
    video_id = str_or_none(result.get('id')) or str_or_none(result.get('slug'))
    slug = str_or_none(result.get('slug')) or video_id

    duration = None
    for vt in videos.values():
        duration = int_or_none((vt or {}).get('length'))
        if duration:
            break

    cast = [a['name'] for a in (result.get('actors') or []) if a.get('name')]
    tags = [t['name'] for t in (result.get('tags') or []) if t.get('name') and t.get('isVisible')]

    return {
        'id': video_id or slug,
        'title': str_or_none(result.get('title')) or slug,
        'description': str_or_none(result.get('description')),
        'thumbnail': _pick_thumbnail(result),
        'timestamp': unified_timestamp(str_or_none(result.get('dateReleased'))),
        'duration': duration,
        'cast': cast or None,
        'categories': tags or None,
        'age_limit': 18,
        'webpage_url': f'https://site-ma.bangbros.com/scene/{slug}',
    }


# ── Mixin: shared API machinery ─────────────────────────────────────────────

class _BangBrosMixin:
    """Shared token/header logic for all site-ma extractors."""

    _instance_token = None

    def _get_instance_token(self, video_id):
        if self._instance_token:
            return self._instance_token
        self._download_webpage(
            _SITE_URL, video_id,
            note='Fetching BangBros instance token',
            errnote='Could not reach site-ma.bangbros.com',
        )
        for cookie in self._downloader.cookiejar:
            if cookie.name == 'instance_token':
                self._instance_token = cookie.value
                return cookie.value
        return None

    def _get_cookie(self, name):
        for c in self._downloader.cookiejar:
            if c.name == name:
                return c.value
        return None

    def _api_headers(self, instance_token):
        h = {
            'Accept': 'application/json',
            'User-Agent': _FAKE_UA,
            'Origin': 'https://site-ma.bangbros.com',
            'Referer': 'https://site-ma.bangbros.com/',
            'Instance': instance_token or '',
            'x-app-session-id': self._get_cookie('app_session_id') or '',
        }
        access = self._get_cookie('access_token_ma')
        if access:
            h['Authorization'] = access
        return h

    def _api_get(self, path, video_id, *, query=None, note='', fatal=True):
        token = self._get_instance_token(video_id)
        if not token:
            raise ExtractorError(
                'Could not get BangBros instance token. '
                'Make sure you are logged in (pass --cookies).',
                expected=True,
            )
        return self._download_json(
            f'{_DATA_API}{path}', video_id,
            note=note or f'Fetching {path}',
            headers=self._api_headers(token),
            query=query,
            fatal=fatal,
        )

    def _check_auth(self, result, video_id):
        if not result.get('canPlay', False):
            self.raise_login_required(
                'This video requires a BangBros premium account. '
                'Log in at https://site-ma.bangbros.com and export your cookies.',
                method='cookies',
            )


# ── Scene extractor ─────────────────────────────────────────────────────────

class BangBrosMASiteIE(_BangBrosMixin, InfoExtractor):
    """
    Single-scene extractor for site-ma.bangbros.com.

    Matches:
      https://site-ma.bangbros.com/scene/some-slug
      https://site-ma.bangbros.com/scene/12345/some-slug
      https://site-ma.bangbros.com/video/12345
    """

    IE_NAME = 'bangbros:site-ma'
    IE_DESC = 'BangBros member area — single scene'

    _VALID_URL = (
        r'https?://site-ma\.bangbros\.com'
        r'/(?:scene/(?P<id_slug>[\w-]+(?:/[\w-]+)?)|video/(?P<id_num>\d+))'
        r'(?:[/?#]|$)'
    )

    _TESTS = [{
        'url': 'https://site-ma.bangbros.com/scene/lets-get-fucking-weird',
        'info_dict': {
            'id': str,
            'ext': 'mp4',
            'title': str,
            'age_limit': 18,
        },
        'skip': 'Requires premium account',
    }]

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        numeric_id = mobj.group('id_num')
        slug_raw = mobj.group('id_slug') or numeric_id
        slug = slug_raw.split('/')[-1] if slug_raw else numeric_id

        if numeric_id:
            data = self._api_get(f'/v2/releases/{numeric_id}', slug,
                                 note='Fetching scene by ID')
            result = (data or {}).get('result') or data or {}
        else:
            releases = self._api_get('/v2/releases', slug,
                                     query={'slug': slug, 'type': 'scene'},
                                     note='Searching scene by slug')
            if isinstance(releases, list) and releases:
                result = releases[0].get('result') or releases[0]
            elif isinstance(releases, dict):
                result = releases.get('result') or releases
            else:
                raise ExtractorError(f'Scene not found: {slug}', expected=True)

            release_id = str_or_none(result.get('id'))
            if release_id:
                full = self._api_get(f'/v2/releases/{release_id}', slug,
                                     note='Fetching full scene data', fatal=False)
                if full:
                    result = (full or {}).get('result') or result

        if not result:
            raise ExtractorError(f'No data for {slug}', expected=True)

        self._check_auth(result, slug)

        videos = result.get('videos') or {}
        formats = _extract_formats(videos, slug)
        if not formats:
            self.raise_login_required(
                'No streams found — BangBros premium account required.',
                method='cookies',
            )

        self._sort_formats(formats)
        info = _result_to_info(result)
        info['formats'] = formats
        return info


# ── Model page extractor ─────────────────────────────────────────────────────

class BangBrosMASiteModelIE(_BangBrosMixin, InfoExtractor):
    """
    Model / performer page extractor.

    Matches:
      https://site-ma.bangbros.com/model/abella-danger
      https://site-ma.bangbros.com/models/abella-danger
    """

    IE_NAME = 'bangbros:model'
    IE_DESC = 'BangBros member area — model page (all scenes)'

    _VALID_URL = (
        r'https?://site-ma\.bangbros\.com'
        r'/models?/(?P<slug>[\w-]+)(?:[/?#]|$)'
    )

    _PAGE_SIZE = 50

    def _real_extract(self, url):
        slug = self._match_id(url)

        # Resolve performer slug → ID
        performers = self._api_get('/v2/performers', slug,
                                   query={'slug': slug, 'limit': 1},
                                   note=f'Looking up model {slug}')
        performer = None
        if isinstance(performers, list) and performers:
            performer = performers[0]
        elif isinstance(performers, dict):
            performer = (performers.get('result')
                         or performers.get('items', [None])[0]
                         or performers)

        if not performer:
            raise ExtractorError(f'Model not found: {slug}', expected=True)

        performer_id = str_or_none(performer.get('id'))
        name = str_or_none(performer.get('name')) or slug

        if not performer_id:
            raise ExtractorError(f'Could not resolve performer ID for {slug}', expected=True)

        entries = self._collect_all_releases(
            performer_id, slug,
            extra_query={'performerId': performer_id},
        )

        return self.playlist_result(entries, performer_id, name,
                                    f'All BangBros scenes by {name}')

    def _collect_all_releases(self, playlist_id, video_id, extra_query=None):
        page = 1
        while True:
            query = {
                'type': 'scene',
                'limit': self._PAGE_SIZE,
                'page': page,
            }
            if extra_query:
                query.update(extra_query)

            data = self._api_get('/v2/releases', video_id, query=query,
                                 note=f'Fetching page {page}', fatal=False)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = (data.get('result') or data.get('items')
                         or data.get('releases') or [])

            if not items:
                break

            for item in items:
                result = item.get('result') or item
                if not result:
                    continue
                release_id = str_or_none(result.get('id')) or str_or_none(result.get('slug'))
                if not release_id:
                    continue
                scene_url = f'https://site-ma.bangbros.com/scene/{result.get("slug") or release_id}'
                yield self.url_result(scene_url, BangBrosMASiteIE, video_id=release_id,
                                      video_title=str_or_none(result.get('title')))

            if len(items) < self._PAGE_SIZE:
                break
            page += 1


# ── Studio / addon playlist extractor ────────────────────────────────────────

class BangBrosMASitePlaylistIE(_BangBrosMixin, InfoExtractor):
    """
    Studio/addon scene listing.

    Matches:
      https://site-ma.bangbros.com/scenes                    ← all scenes
      https://site-ma.bangbros.com/scenes?addon=5971         ← specific studio
      https://site-ma.bangbros.com/scenes?addon=5971&page=2  ← paginated

    Auto-paginates through ALL pages, yielding every scene URL.
    """

    IE_NAME = 'bangbros:playlist'
    IE_DESC = 'BangBros member area — scene listing / studio playlist'

    _VALID_URL = (
        r'https?://site-ma\.bangbros\.com'
        r'/scenes/?(?:\?(?P<qs>[^#]*))?(?:#|$)?'
    )

    _PAGE_SIZE = 50

    def _real_extract(self, url):
        qs_raw = self._match_valid_url(url).group('qs') or ''
        qs = dict(urllib.parse.parse_qsl(qs_raw))
        addon_id = qs.get('addon') or qs.get('addOnId')

        playlist_id = f'addon-{addon_id}' if addon_id else 'scenes-all'
        title = f'BangBros Studio {addon_id}' if addon_id else 'BangBros — All Scenes'

        # Optionally resolve studio name
        if addon_id:
            addons = self._api_get('/v2/addons', playlist_id,
                                   query={'id': addon_id}, fatal=False)
            if isinstance(addons, list) and addons:
                studio_name = (addons[0].get('name')
                               or addons[0].get('title')
                               or title)
                title = f'BangBros — {studio_name}'

        entries = list(self._iter_all_scenes(addon_id, playlist_id))
        return self.playlist_result(entries, playlist_id, title)

    def _iter_all_scenes(self, addon_id, playlist_id):
        page = 1
        while True:
            query = {'type': 'scene', 'limit': self._PAGE_SIZE, 'page': page}
            if addon_id:
                query['addOnId'] = addon_id

            data = self._api_get('/v2/releases', playlist_id, query=query,
                                 note=f'Fetching scenes page {page}', fatal=False)

            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = (data.get('result') or data.get('items')
                         or data.get('releases') or [])

            if not items:
                self.to_screen(f'[bangbros:playlist] No more scenes at page {page}')
                break

            for item in items:
                result = item.get('result') or item
                if not result:
                    continue
                slug = str_or_none(result.get('slug'))
                release_id = str_or_none(result.get('id')) or slug
                if not release_id:
                    continue
                scene_url = f'https://site-ma.bangbros.com/scene/{slug or release_id}'
                yield self.url_result(
                    scene_url, BangBrosMASiteIE,
                    video_id=release_id,
                    video_title=str_or_none(result.get('title')),
                )

            self.to_screen(f'[bangbros:playlist] Got {len(items)} scenes on page {page}')
            if len(items) < self._PAGE_SIZE:
                break
            page += 1


# ── Subscribed studios listing ────────────────────────────────────────────────

class BangBrosMASiteAddonsIE(_BangBrosMixin, InfoExtractor):
    """
    List all subscribed studios and aggregate their scenes.

    Matches:
      https://site-ma.bangbros.com/addons
      https://site-ma.bangbros.com/my-studios
    """

    IE_NAME = 'bangbros:addons'
    IE_DESC = 'BangBros member area — all subscribed studios'

    _VALID_URL = (
        r'https?://site-ma\.bangbros\.com'
        r'/(?:addons|my-studios)/?(?:[?#]|$)'
    )

    def _real_extract(self, url):
        addons = self._api_get('/v2/addons', 'addons',
                               note='Fetching subscribed studios')
        if not addons:
            raise ExtractorError('No subscribed studios found', expected=True)

        entries = []
        if isinstance(addons, dict):
            addons = addons.get('result') or addons.get('items') or []

        for addon in (addons or []):
            addon_id = str_or_none(addon.get('id'))
            name = str_or_none(addon.get('name') or addon.get('title')) or addon_id
            if not addon_id:
                continue
            playlist_url = f'https://site-ma.bangbros.com/scenes?addon={addon_id}'
            self.to_screen(f'[bangbros:addons] Found studio: {name} (ID {addon_id})')
            entries.append(self.url_result(
                playlist_url, BangBrosMASitePlaylistIE,
                video_id=f'addon-{addon_id}',
                video_title=f'BangBros — {name}',
            ))

        return self.playlist_result(entries, 'bangbros-addons',
                                    'BangBros — My Studios')
