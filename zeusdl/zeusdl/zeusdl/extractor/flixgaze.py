import re

from .common import InfoExtractor
from ..utils import (
    clean_html,
    int_or_none,
    traverse_obj,
    urljoin,
)


class FlixGazeIE(InfoExtractor):
    """Extractor for FlixGaze — a WordPress-based movie & TV streaming site.

    Video player: JWPlayer loaded from vjs.milkystream.net.
    Stream URL pattern: {domainId}/{pathId}/{videoId}.m3u8
    Variables are injected as inline JS constants on every video page.
    """

    IE_NAME = 'flixgaze'
    IE_DESC = 'FlixGaze (Movies & TV Series)'
    _VALID_URL = r'https?://(?:www\.)?flixgaze\.com/(?!(?:movie/?|tv-series/?|genre/|search)$)(?P<id>[^?#]+?)(?:\.html)?/?$'

    _TESTS = [
        {
            'url': 'https://www.flixgaze.com/the-boys/season-5-episode-1-fifteen-inches-of-sheer-dynamite.html',
            'info_dict': {
                'id': 'the-boys/season-5-episode-1-fifteen-inches-of-sheer-dynamite',
                'ext': 'mp4',
                'title': str,
            },
        },
        {
            'url': 'https://www.flixgaze.com/movie/the-super-mario-galaxy-movie-2026.html',
            'info_dict': {
                'id': 'movie/the-super-mario-galaxy-movie-2026',
                'ext': 'mp4',
                'title': str,
            },
        },
    ]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)

        # Extract the JWPlayer variables injected as inline constants.
        # Example: const pathId="theboys5/episode1", domainId="https://...", videoId="abc123", posterId="...";
        inline_script = self._search_regex(
            r'const\s+pathId\s*=\s*["\']([^"\']+)["\'].*?domainId\s*=\s*["\']([^"\']+)["\'].*?videoId\s*=\s*["\']([^"\']+)["\'](?:.*?posterId\s*=\s*["\']([^"\']+)["\'])?',
            webpage,
            'player variables',
            group=(1, 2, 3, 4),
            default=(None, None, None, None),
            flags=re.DOTALL,
        )

        path_id, domain_id, video_hash, poster_id = inline_script

        if not (path_id and domain_id and video_hash):
            self.report_warning(
                f'Could not find player variables for {url} — page may require JavaScript or have changed structure.')
            raise self.raise_no_formats('No playable formats found', expected=True)

        m3u8_url = f'{domain_id}/{path_id}/{video_hash}.m3u8'
        vtt_url = f'{domain_id}/{path_id}/{video_hash}.vtt'

        title = (
            self._html_search_meta(['og:title', 'twitter:title'], webpage)
            or self._html_search_regex(r'<h1[^>]*>([^<]+)</h1>', webpage, 'title', default=None)
            or video_id
        )

        description = (
            self._html_search_meta(['og:description', 'description'], webpage)
            or self._html_search_regex(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', webpage, 'description', default=None)
        )

        thumbnail = poster_id or self._html_search_meta(['og:image', 'twitter:image'], webpage)

        formats = self._extract_m3u8_formats(
            m3u8_url,
            video_id,
            ext='mp4',
            entry_protocol='m3u8_native',
            m3u8_id='hls',
            fatal=False,
            headers={
                'Referer': 'https://www.flixgaze.com/',
                'Origin': 'https://www.flixgaze.com',
            },
        )

        if not formats:
            formats = [{
                'url': m3u8_url,
                'ext': 'mp4',
                'format_id': 'hls',
                'protocol': 'm3u8_native',
                'http_headers': {
                    'Referer': 'https://www.flixgaze.com/',
                    'Origin': 'https://www.flixgaze.com',
                },
            }]

        subtitles = {}
        if vtt_url:
            subtitles['en'] = [{'url': vtt_url, 'ext': 'vtt'}]

        return {
            'id': video_id,
            'title': clean_html(title),
            'description': clean_html(description) if description else None,
            'thumbnail': thumbnail,
            'formats': formats,
            'subtitles': subtitles,
            'age_limit': 0,
            'http_headers': {
                'Referer': 'https://www.flixgaze.com/',
                'Origin': 'https://www.flixgaze.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }


class FlixGazeListIE(InfoExtractor):
    """Extract playlists from FlixGaze listing pages (movies, TV series, genres)."""

    IE_NAME = 'flixgaze:list'
    IE_DESC = 'FlixGaze listing pages'
    _VALID_URL = r'https?://(?:www\.)?flixgaze\.com/(?P<id>(?:movie|tv-series|genre/[^/?#]+))(?:/(?P<page>\d+))?/?$'

    _TESTS = [
        {
            'url': 'https://www.flixgaze.com/movie',
            'info_dict': {
                'id': 'movie',
                'title': 'Movies',
            },
            'playlist_mincount': 5,
        },
        {
            'url': 'https://www.flixgaze.com/tv-series',
            'info_dict': {
                'id': 'tv-series',
                'title': 'TV Series',
            },
            'playlist_mincount': 5,
        },
    ]

    def _real_extract(self, url):
        list_id = self._match_id(url)
        base_url = f'https://www.flixgaze.com/{list_id}'
        entries = []
        page = 1

        while True:
            page_url = base_url if page == 1 else f'{base_url}/page/{page}'
            webpage = self._download_webpage(page_url, list_id, note=f'Downloading page {page}', fatal=page == 1)
            if not webpage:
                break

            found = False
            for mobj in re.finditer(
                r'<a[^>]+href=["\'](?P<url>https?://(?:www\.)?flixgaze\.com/[^"\']+\.html)["\']',
                webpage,
            ):
                entry_url = mobj.group('url')
                if entry_url not in [e.get('url') for e in entries]:
                    entries.append(self.url_result(entry_url, ie=FlixGazeIE.ie_key()))
                    found = True

            if not found or not self._search_regex(
                r'<a[^>]+rel=["\']next["\']|class=["\'][^"\']*next[^"\']*["\']',
                webpage, 'next page', default=None
            ):
                break
            page += 1

        title_map = {
            'movie': 'Movies',
            'tv-series': 'TV Series',
        }
        title = title_map.get(list_id, list_id.replace('genre/', 'Genre: ').replace('-', ' ').title())

        return self.playlist_result(entries, list_id, title)


class FlixGazeSearchIE(InfoExtractor):
    """Handle search queries on FlixGaze."""

    IE_NAME = 'flixgaze:search'
    IE_DESC = 'FlixGaze search'
    _VALID_URL = r'flixgazesearch:(?P<query>.+)'

    def _real_extract(self, url):
        query = self._match_id(url)
        search_url = f'https://www.flixgaze.com/?s={query.replace(" ", "+")}'
        webpage = self._download_webpage(search_url, query, note=f'Searching FlixGaze for "{query}"')

        entries = []
        for mobj in re.finditer(
            r'<a[^>]+href=["\'](?P<url>https?://(?:www\.)?flixgaze\.com/[^"\']+\.html)["\']',
            webpage,
        ):
            entry_url = mobj.group('url')
            if entry_url not in [e.get('url') for e in entries]:
                entries.append(self.url_result(entry_url, ie=FlixGazeIE.ie_key()))

        return self.playlist_result(entries, query, f'FlixGaze search: {query}')
