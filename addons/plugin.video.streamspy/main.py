# -*- coding: utf-8 -*-
# MikyhoKino v5 – Webshare + Hellspy
# Autor: Miky

import io, os, sys, re, json, time, threading, hashlib
import xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
import requests, requests.cookies
import unidecode
from xml.etree import ElementTree as ET
from md5crypt import md5crypt

try:
    from urllib.parse import urlencode, parse_qsl, quote_plus, quote as _quote
except ImportError:
    from urllib import urlencode, quote_plus
    from urlparse import parse_qsl
    def _quote(s, safe=''):
        return quote_plus(s, safe=safe)

try:
    from xbmc import translatePath
except ImportError:
    from xbmcvfs import translatePath

# ---------------------------------------------------------------------------
# HELPER – InfoTagVideo (Kodi 20+)
# ---------------------------------------------------------------------------
def _set_video_info(li, info):
    """Nastavi video info pres InfoTagVideo (Kodi 20+) nebo setInfo (starsi)."""
    try:
        tag = li.getVideoInfoTag()
        if 'title'    in info: tag.setTitle(info['title'])
        if 'plot'     in info: tag.setPlot(info['plot'])
        if 'year'     in info: tag.setYear(int(info['year']) if str(info['year']).isdigit() else 0)
        if 'rating'   in info: tag.setRating(float(info['rating']))
        if 'duration' in info: tag.setDuration(int(info['duration']))
        if 'episode'  in info: tag.setEpisode(int(info['episode']))
        if 'season'   in info: tag.setSeason(int(info['season']))
        if 'tvshowtitle' in info: tag.setTvShowTitle(info['tvshowtitle'])
    except AttributeError:
        li.setInfo('video', info)

# ---------------------------------------------------------------------------
# KONFIGURACE
# ---------------------------------------------------------------------------
WS_BASE  = 'https://webshare.cz'
WS_API   = WS_BASE + '/api/'
HS_BASE  = 'https://www.hellspy.to'
HS_API   = 'https://api.hellspy.to'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
WS_HEADERS = {'User-Agent': UA, 'Referer': WS_BASE}
HS_HEADERS = {'User-Agent': UA, 'Referer': HS_BASE + '/', 'Accept-Language': 'cs-CZ,cs;q=0.9'}

TMDB_URL = 'https://api.themoviedb.org/3'
TMDB_IMG = 'https://image.tmdb.org/t/p/w500'
OPENSUB_URL = 'https://api.opensubtitles.com/api/v1'
OPENSUB_UA  = 'MikyhoKino v5.0'

CACHE_TTL        = 3 * 3600
SEARCH_CACHE_TTL = 10 * 60
MAX_HISTORY      = 50
MAX_FAVORITES    = 200
RETRY_COUNT      = 2
NONE_WHAT        = '%#NONE#%'

EPISODE_RE = re.compile(r'\b(?:s\d{2}e\d{2}|\d{1,2}x\d{2})\b', re.IGNORECASE)

MOVIE_GENRES = [
    {"id": "28",    "name": "Akční"},       {"id": "12",    "name": "Dobrodružný"},
    {"id": "16",    "name": "Animovaný"},   {"id": "35",    "name": "Komedie"},
    {"id": "80",    "name": "Krimi"},       {"id": "99",    "name": "Dokumentární"},
    {"id": "18",    "name": "Drama"},       {"id": "10751", "name": "Rodinný"},
    {"id": "14",    "name": "Fantasy"},     {"id": "36",    "name": "Historický"},
    {"id": "27",    "name": "Horor"},       {"id": "878",   "name": "Sci-Fi"},
    {"id": "53",    "name": "Thriller"},    {"id": "10752", "name": "Válečný"},
    {"id": "37",    "name": "Western"},
]
TV_GENRES = [
    {"id": "10759", "name": "Akční a dobrodružný"}, {"id": "16",    "name": "Animovaný"},
    {"id": "35",    "name": "Komedie"},              {"id": "80",    "name": "Krimi"},
    {"id": "99",    "name": "Dokumentární"},         {"id": "18",    "name": "Drama"},
    {"id": "10751", "name": "Rodinný"},              {"id": "9648",  "name": "Mysteriózní"},
    {"id": "10765", "name": "Sci-Fi a Fantasy"},
]
QUALITY_FILTERS = [('all','Vše'),('cz','Jen CZ/SK'),('4k','Jen 4K'),('1080p','Jen 1080p'),('720p','Jen 720p')]
SORT_OPTIONS    = [('score','Relevance'),('size','Velikost ↓'),('date','Nejnovější'),('name','Název A-Z')]

# ---------------------------------------------------------------------------
# ADDON GLOBALS
# ---------------------------------------------------------------------------
_addon      = xbmcaddon.Addon()
_addon_id   = _addon.getAddonInfo('id')
_addon_path = translatePath(_addon.getAddonInfo('path'))
_profile    = translatePath(_addon.getAddonInfo('profile'))
_handle     = int(sys.argv[1])
_url        = sys.argv[0]
_icon       = os.path.join(_addon_path, 'icon.png')
_fanart     = os.path.join(_addon_path, 'fanart.jpg')
if not os.path.exists(_fanart):
    _fanart = _icon

_ws_session = requests.Session()
_ws_session.headers.update(WS_HEADERS)
_hs_session = requests.Session()
_hs_session.headers.update(HS_HEADERS)

# ---------------------------------------------------------------------------
# POMOCNÉ FUNKCE
# ---------------------------------------------------------------------------
def get_url(**kwargs):
    return '{0}?{1}'.format(_url, urlencode(kwargs))

def _menu_icon(name):
    p = os.path.join(_addon_path, 'resources', 'icons', name + '.png')
    return p if os.path.exists(p) else _icon

def popinfo(msg, ms=3000):
    xbmcgui.Dialog().notification(_addon.getAddonInfo('name'), msg, _icon, ms)

def poperror(msg, ms=4000):
    xbmcgui.Dialog().notification(_addon.getAddonInfo('name'), msg,
                                   xbmcgui.NOTIFICATION_ERROR, ms)

def sizelize(b):
    try:
        b = float(b)
    except Exception:
        return '0B'
    for u in ['B', 'KB', 'MB', 'GB']:
        if b < 1024.0:
            return '%.1f%s' % (b, u)
        b /= 1024.0
    return '%.1fTB' % b

def fmt_duration(secs):
    try:
        s = int(secs)
        return '%d:%02d:%02d' % (s // 3600, (s % 3600) // 60, s % 60)
    except Exception:
        return ''

def fmt_time(seconds):
    try:
        s = int(seconds)
        return '%d:%02d:%02d' % (s // 3600, (s % 3600) // 60, s % 60)
    except Exception:
        return '?'

def profile_path(fname=''):
    if not os.path.exists(_profile):
        os.makedirs(_profile)
    return os.path.join(_profile, fname) if fname else _profile

def load_json(fname, default=None):
    p = profile_path(fname)
    if os.path.exists(p):
        try:
            with io.open(p, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception:
            pass
    return default if default is not None else {}

def save_json(fname, data):
    try:
        with io.open(profile_path(fname), 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        xbmc.log('JSON save error [%s]: %s' % (fname, e), xbmc.LOGERROR)

def get_tmdb_key():
    key = _addon.getSetting('tmdb_key')
    if not key:
        xbmcgui.Dialog().ok('Chyba', 'TMDB API klíč není nastaven.\nJdi do Nastavení.')
        _addon.openSettings()
        return None
    return key

def get_min_size_bytes():
    try:
        return int(_addon.getSetting('min_size_mb') or 150) * 1024 * 1024
    except Exception:
        return 150 * 1024 * 1024

def ws_enabled():
    return _addon.getSetting('ws_enabled') != 'false'

def hs_enabled():
    return _addon.getSetting('hs_enabled') != 'false'

# ---------------------------------------------------------------------------
# CACHE
# ---------------------------------------------------------------------------
def cache_load(key, ttl=CACHE_TTL):
    db    = load_json('cache.json', {})
    entry = db.get(key)
    if entry and time.time() - entry.get('ts', 0) < ttl:
        return entry.get('data')
    return None

def cache_save(key, data):
    db = load_json('cache.json', {})
    if len(db) > 400:
        oldest = sorted(db.items(), key=lambda x: x[1].get('ts', 0))
        for k, _ in oldest[:50]:
            del db[k]
    db[key] = {'ts': time.time(), 'data': data}
    save_json('cache.json', db)

def cache_clear():
    save_json('cache.json', {})
    save_json('search_cache.json', {})
    popinfo('Cache vymazána')

def search_cache_load(key):
    return cache_load('sc_' + key, SEARCH_CACHE_TTL)

def search_cache_save(key, data):
    cache_save('sc_' + key, data)

# ---------------------------------------------------------------------------
# XML HELPER
# ---------------------------------------------------------------------------
def parse_xml(response):
    if response is None:
        return None
    try:
        return ET.fromstring(response.content)
    except Exception as e:
        xbmc.log('XML parse error: %s' % e, xbmc.LOGERROR)
        return None

def is_ok(xml):
    try:
        return xml.find('status').text == 'OK'
    except Exception:
        return False

def todict(xml, skip=[]):
    return {e.tag: (e.text if not list(e) else todict(e, skip)) for e in xml if e.tag not in skip}

# ---------------------------------------------------------------------------
# WEBSHARE API
# ---------------------------------------------------------------------------
def ws_api(fnct, data, retries=RETRY_COUNT):
    for attempt in range(retries + 1):
        try:
            r = _ws_session.post(WS_API + fnct + '/', data=data, timeout=15)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            xbmc.log('WS API [%s] attempt %d: %s' % (fnct, attempt + 1, e), xbmc.LOGWARNING)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return None

def ws_login():
    u = _addon.getSetting('wsuser')
    p = _addon.getSetting('wspass')
    xbmc.log('WS login: user="%s" pass=%s' % (u, 'OK' if p else 'PRAZDNE'), xbmc.LOGINFO)
    if not u or not p:
        xbmcgui.Dialog().ok('StreamSpy – Webshare',
            'Vyplň Webshare přihlašovací údaje v Nastavení.')
        _addon.openSettings()
        return None
    res = ws_api('salt', {'username_or_email': u})
    xml = parse_xml(res)
    if xml is None or not is_ok(xml):
        popinfo('WS: Chyba přihlášení – nelze získat salt')
        return None
    s = xml.find('salt').text
    try:
        ep = hashlib.sha1(md5crypt(p.encode('utf-8'), s.encode('utf-8'))).hexdigest()
    except Exception:
        ep = hashlib.sha1(md5crypt(p.encode('utf-8'), s.encode('utf-8')).encode('utf-8')).hexdigest()
    xml = parse_xml(ws_api('login', {'username_or_email': u, 'password': ep, 'keep_logged_in': 1}))
    if xml is not None and is_ok(xml):
        t = xml.find('token').text
        _addon.setSetting('ws_token', t)
        _addon.setSetting('ws_token_ts', str(int(time.time())))
        _addon.setSetting('vip_status', '')
        _addon.setSetting('vip_until', '')
        return t
    popinfo('WS: Přihlášení selhalo – zkontroluj jméno a heslo')
    return None

def ws_revalidate():
    t = _addon.getSetting('ws_token')
    if not t:
        return ws_login()
    # Pouzij cachovany token - neoveruj kazde prehrani, jen jednou za hodinu
    try:
        ts = int(_addon.getSetting('ws_token_ts') or 0)
        age = time.time() - ts
        if age < 3600:
            # Token je cerstvy, pouzij ho rovnou
            return t
        if age > 23 * 3600:
            # Token je stary, obnov na pozadi
            threading.Thread(target=ws_login, daemon=True).start()
            return t
    except Exception:
        pass
    # Overeni tokenu na pozadi (ne blokujici)
    def _check():
        res = ws_api('user_data', {'wst': t})
        xml = parse_xml(res)
        if xml is None or not is_ok(xml):
            ws_login()
        else:
            try:
                vip_el   = xml.find('vip')
                until_el = xml.find('vip_until')
                if vip_el   is not None: _addon.setSetting('vip_status', vip_el.text or '0')
                if until_el is not None and until_el.text: _addon.setSetting('vip_until', until_el.text)
            except Exception:
                pass
    threading.Thread(target=_check, daemon=True).start()
    return t

def get_vip_label():
    vip   = _addon.getSetting('vip_status')
    until = _addon.getSetting('vip_until')
    if vip == '1':
        return '[COLOR green]WS VIP aktivní%s[/COLOR]' % (' do %s' % until if until else '')
    elif vip == '0':
        return '[COLOR gray]WS bez VIP[/COLOR]'
    return ''

# ---------------------------------------------------------------------------
# HELLSPY API
# ---------------------------------------------------------------------------
def _parse_size(s):
    """Prevede '1.2 GB' nebo '800 MB' na byty pro razeni."""
    try:
        s = s.strip().upper()
        num = float(_re.sub(r'[^0-9.]', '', s.split()[0]))
        if 'GB' in s: return int(num * 1024**3)
        if 'MB' in s: return int(num * 1024**2)
        if 'KB' in s: return int(num * 1024)
        return int(num)
    except Exception:
        return 0

def _parse_duration(s):
    """Prevede '1:23:45' nebo '45:30' na sekundy."""
    try:
        parts = [int(x) for x in str(s).split(':')]
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return int(parts[0])
    except Exception:
        return 0

def hs_search(query, page=1):
    cache_key = 'hs_search_%s_%d' % (query, page)
    cached = cache_load(cache_key, SEARCH_CACHE_TTL)
    if cached:
        return cached

    limit  = 64
    offset = (page - 1) * limit
    params = {'query': query, 'offset': offset, 'limit': limit}
    try:
        r = _hs_session.get(HS_API + '/gw/search', params=params, timeout=15)
        if r.status_code != 200:
            xbmc.log('HS search error %d' % r.status_code, xbmc.LOGERROR)
            return []
        data = r.json()
    except Exception as e:
        xbmc.log('HS search exception: ' + str(e), xbmc.LOGERROR)
        return []

    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for k in ('items', 'results', 'data', 'videos'):
            if k in data and isinstance(data[k], list):
                items = data[k]
                break

    final = []
    seen  = set()
    for item in items:
        fid    = str(item.get('id', ''))
        fhash  = item.get('fileHash') or item.get('hash', '')
        title  = item.get('title') or item.get('name', '')
        size   = item.get('size', 0)
        dur    = item.get('duration', 0)
        thumbs = item.get('thumbs') or []
        if not fid or not fhash or fid in seen:
            continue
        seen.add(fid)
        final.append({
            'id': fid, 'hash': fhash, 'title': title,
            'size_str': sizelize(size), 'duration': fmt_duration(dur),
            'thumbs': thumbs, 'source': 'hs',
        })

    if final:
        cache_save(cache_key, final)
    return final

def hs_video_detail(file_id, file_hash):
    cache_key = 'hs_detail_%s' % file_id
    cached = cache_load(cache_key, 300)
    if cached:
        conv  = cached.get('conversions', {})
        url0  = list(conv.values())[0] if conv else ''
        exp_m = re.search(r'expires=(\d+)', url0)
        if exp_m and int(exp_m.group(1)) > time.time() + 60:
            return cached
    url = HS_API + '/gw/video/%s/%s' % (file_id, file_hash)
    try:
        r = _hs_session.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and data.get('conversions'):
                cache_save(cache_key, data)
                return data
    except Exception as e:
        xbmc.log('HS detail error: ' + str(e), xbmc.LOGERROR)
    return None

# ---------------------------------------------------------------------------
# TMDB
# ---------------------------------------------------------------------------
def tmdb_get(url):
    cached = cache_load(url)
    if cached is not None:
        return cached
    for attempt in range(RETRY_COUNT + 1):
        try:
            r = _ws_session.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            cache_save(url, data)
            return data
        except Exception as e:
            xbmc.log('TMDB error attempt %d: %s' % (attempt + 1, e), xbmc.LOGWARNING)
            if attempt < RETRY_COUNT:
                time.sleep(1.5 * (attempt + 1))
    return None

def tmdb_list(params):
    key = get_tmdb_key()
    if not key:
        xbmcplugin.endOfDirectory(_handle)
        return
    ep   = params.get('endpoint')
    page = params.get('page', '1')
    url  = '%s%s?api_key=%s&language=cs-CZ&page=%s' % (TMDB_URL, ep, key, page)
    if params.get('genre_id'): url += '&with_genres=' + params['genre_id']
    if params.get('query'):    url += '&query=' + _quote(params['query'])
    data = tmdb_get(url)
    if data is None:
        xbmcplugin.endOfDirectory(_handle)
        return

    for i in data.get('results', []):
        mtype = i.get('media_type', 'tv' if '/tv' in ep else 'movie')
        if mtype not in ('movie', 'tv'):
            continue
        t_cs   = i.get('name') or i.get('title') or ''
        t_orig = i.get('original_name') or i.get('original_title') or t_cs
        date   = i.get('first_air_date') or i.get('release_date') or ''
        year   = date.split('-')[0] if '-' in date else ''
        rating = i.get('vote_average', 0)

        if t_cs.lower() != t_orig.lower():
            search_q = ('%s|%s %s' % (t_orig, t_cs, year)).strip()
        else:
            search_q = ('%s %s' % (t_cs, year)).strip()

        label = t_cs
        if year:   label += ' [COLOR gray](%s)[/COLOR]' % year
        if rating: label += ' [COLOR gold][%.1f][/COLOR]' % rating

        poster = i.get('poster_path', '')
        fav_id = 'tmdb_%s' % i['id']
        is_fav = is_movie_favorite(fav_id)
        fav_star = '★ Odebrat z oblíbených' if is_fav else '☆ Přidat film do oblíbených'

        if mtype == 'tv':
            u = get_url(action='tmdb_seasons', tv_id=i['id'], tv_name=t_orig)
        else:
            u = get_url(action='combined_search', what=search_q)

        li = xbmcgui.ListItem(label=label)
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon,
                   'thumb':  TMDB_IMG + poster if poster else _icon,
                   'icon':   _icon, 'fanart': _fanart})
        _set_video_info(li, {
            'title': t_cs, 'plot': i.get('overview', ''),
            'year':  int(year) if year.isdigit() else 0, 'rating': rating,
        })
        li.addContextMenuItems([
            (fav_star, 'RunPlugin(%s)' % get_url(
                action='movie_fav_add', fav_id=fav_id,
                title=t_cs, search_q=search_q, poster=poster,
                year=year, mtype=mtype, tv_id=str(i.get('id','')))),
        ])
        xbmcplugin.addDirectoryItem(_handle, u, li, True)

    total = data.get('total_pages', 1)
    cur   = int(page)
    if cur < total:
        nxt = {k: v for k, v in params.items() if k != 'action'}
        nxt['page'] = str(cur + 1)
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='tmdb_list', **nxt),
            xbmcgui.ListItem(label='[COLOR yellow]>> Další stránka (%d/%d)[/COLOR]' % (cur+1, total)), True)
    xbmcplugin.endOfDirectory(_handle)

def tmdb_seasons(params):
    key   = get_tmdb_key()
    tv_id = params.get('tv_id')
    tv_name = params.get('tv_name', '')
    if not key or not tv_id:
        xbmcplugin.endOfDirectory(_handle); return
    data = tmdb_get('%s/tv/%s?api_key=%s&language=cs-CZ' % (TMDB_URL, tv_id, key))
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return
    poster = data.get('poster_path')
    for s in data.get('seasons', []):
        sn = s.get('season_number', 0)
        if sn == 0: continue
        lbl = 'Série %d' % sn
        ep_count = s.get('episode_count', 0)
        if ep_count: lbl += ' [COLOR gray](%d dílů)[/COLOR]' % ep_count
        li = xbmcgui.ListItem(label=lbl)
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon,
                   'thumb':  TMDB_IMG + poster if poster else _icon})
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='tmdb_episodes', tv_id=tv_id, tv_name=tv_name, season=sn), li, True)
    xbmcplugin.endOfDirectory(_handle)

def tmdb_episodes(params):
    key     = get_tmdb_key()
    tv_id   = params.get('tv_id')
    tv_name = params.get('tv_name', '')
    season  = params.get('season', '1')
    if not key or not tv_id:
        xbmcplugin.endOfDirectory(_handle); return
    data = tmdb_get('%s/tv/%s/season/%s?api_key=%s&language=cs-CZ' % (TMDB_URL, tv_id, season, key))
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return
    poster = data.get('poster_path')
    for e in data.get('episodes', []):
        en      = e.get('episode_number', 0)
        ep_code = 'S%02dE%02d' % (int(season), en)
        lbl     = '%s – %s' % (ep_code, e.get('name', ''))
        li      = xbmcgui.ListItem(label=lbl)
        _set_video_info(li, {'plot': e.get('overview', '')})
        still = e.get('still_path')
        li.setArt({'thumb': TMDB_IMG + still if still else (TMDB_IMG + poster if poster else _icon)})
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='combined_search', what='%s %s' % (tv_name, ep_code)), li, True)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# KOMBINOVANÉ VYHLEDÁVÁNÍ (WS + HS)
# ---------------------------------------------------------------------------
def combined_search(what, ws_offset=0, page=1):
    if not what or what == NONE_WHAT:
        xbmcplugin.endOfDirectory(_handle)
        return

    quality_filter = _addon.getSetting('default_quality') or 'all'
    sort_by        = _addon.getSetting('default_sort') or 'score'

    add_to_search_history(what)
    xbmcplugin.setPluginCategory(_handle, 'Hledám: %s' % what)

    ws_results = []
    hs_results = []

    # --- WEBSHARE ---
    if ws_enabled():
        token = ws_revalidate()
        if token:
            what_parts = what.split('|')
            alt_titles = []
            for part in what_parts:
                pc = unidecode.unidecode(part.strip().lower())
                pc = re.sub(r'[^a-z0-9 ]', ' ', pc)
                pc = ' '.join(pc.split())
                if pc:
                    alt_titles.append(pc)
            query = alt_titles[-1] if alt_titles else unidecode.unidecode(what.lower())
            ep_match = EPISODE_RE.search(query)
            query_episode = ep_match.group(0).lower() if ep_match else None
            queries_to_try = list(dict.fromkeys(alt_titles))
            if not query_episode and not any(x in query for x in ['cz','czech','dabing']):
                queries_to_try.append(query + ' cz')

            all_files = {}
            for q in queries_to_try:
                res = ws_api('search', {
                    'what': q, 'category': 'video', 'sort': 'relevance',
                    'limit': 50, 'offset': ws_offset, 'wst': token, 'maybe_removed': 'true'
                })
                xml = parse_xml(res)
                if xml is None or not is_ok(xml):
                    continue
                for file in xml.iter('file'):
                    item  = todict(file)
                    ident = item.get('ident', '')
                    if ident and ident not in all_files:
                        all_files[ident] = item

            year_str = re.search(r'\b(20\d{2}|19\d{2})\b', query)
            year_str = year_str.group(0) if year_str else None
            min_size = get_min_size_bytes()
            favs_idents = set()  # oblibene jsou filmy ne soubory (fav_id)
            watched_db  = load_watched()

            def extract_words(title):
                t = title
                if year_str: t = t.replace(year_str, '')
                t = EPISODE_RE.sub('', t)
                return [w for w in t.split() if len(w) >= 3]

            required_words_sets = [extract_words(t) for t in alt_titles if extract_words(t)]
            if not required_words_sets:
                required_words_sets = [extract_words(query)]
            required_words = required_words_sets[0] if required_words_sets else []

            for item in all_files.values():
                try:
                    size_bytes = float(item.get('size', 0))
                except Exception:
                    size_bytes = 0
                if size_bytes < min_size:
                    continue

                name_norm  = unidecode.unidecode(item.get('name', '').lower())
                name_clean = re.sub(r'[.\-_]', ' ', name_norm)
                name_up    = item.get('name', '').upper()
                name_ep    = EPISODE_RE.search(name_norm)

                if query_episode:
                    if not name_ep or name_ep.group(0).lower() != query_episode:
                        continue
                else:
                    if name_ep:
                        continue
                if year_str and year_str not in name_norm:
                    continue
                if required_words_sets:
                    passed = False
                    for rw in required_words_sets:
                        if not rw:
                            passed = True; break
                        matches = sum(1 for w in rw if w in name_clean)
                        if matches >= max(1, round(len(rw) * 0.8)):
                            passed = True; break
                    if not passed:
                        continue

                is_cz   = any(x in name_up for x in ['CZ','CZECH','DABING','SK'])
                is_4k   = any(x in name_up for x in ['4K','2160P'])
                is_1080 = any(x in name_up for x in ['1080P','FULLHD'])
                is_720  = '720P' in name_up

                if quality_filter == 'cz'    and not is_cz:   continue
                if quality_filter == '4k'    and not is_4k:   continue
                if quality_filter == '1080p' and not is_1080: continue
                if quality_filter == '720p'  and not is_720:  continue

                score = 0
                if is_cz:   score += 5000000
                if is_4k:   score += 4000000
                elif is_1080: score += 3000000
                elif is_720:  score += 2000000
                score += size_bytes / 1024 / 1024 / 10
                try: score += float(item.get('ctime', 0)) / 1000000
                except Exception: pass
                if item.get('ident') in favs_idents: score += 10000000
                if required_words:
                    match_ratio = sum(1 for w in required_words if w in name_clean) / len(required_words)
                    score += match_ratio * 1000000

                item['prio']     = score
                item['size_f']   = size_bytes
                item['name_low'] = name_norm
                item['source']   = 'ws'
                ws_results.append(item)

            if sort_by == 'size':
                ws_results.sort(key=lambda x: x['size_f'], reverse=True)
            elif sort_by == 'date':
                ws_results.sort(key=lambda x: float(x.get('ctime', 0) or 0), reverse=True)
            elif sort_by == 'name':
                ws_results.sort(key=lambda x: x['name_low'])
            else:
                ws_results.sort(key=lambda x: x['prio'], reverse=True)

    # --- HELLSPY ---
    if hs_enabled():
        # Hledej česky – vezmi poslední část za |
        hs_query = what.split('|')[-1].strip()
        hs_results = hs_search(hs_query, page=page)

    # --- ŘAZENÍ HS ---
    if hs_results:
        hs_sort = _addon.getSetting('hs_sort') or 'size'
        if hs_sort == 'size':
            hs_results.sort(key=lambda x: _parse_size(x.get('size_str', '')), reverse=True)
        elif hs_sort == 'title':
            hs_results.sort(key=lambda x: x.get('title', '').lower())
        elif hs_sort == 'duration':
            hs_results.sort(key=lambda x: _parse_duration(x.get('duration', '')), reverse=True)
        # else: 'relevance' – nechame jak prislo

    # --- ZOBRAZENÍ ---
    total_count = len(ws_results) + len(hs_results)
    if total_count == 0:
        popinfo('Nic nenalezeno pro: %s' % what)
        xbmcplugin.endOfDirectory(_handle)
        return

    xbmcplugin.setPluginCategory(_handle, '%s (%d výsledků)' % (what.split('|')[-1], total_count))
    watched_db  = load_watched()
    favs_idents = set()  # oblibene jsou filmy ne soubory (fav_id)

    xbmcplugin.setContent(_handle, 'videos')

    # Webshare výsledky
    for item in ws_results:
        ident   = item.get('ident', '')
        name    = item.get('name', '')
        is_cz   = any(x in name.upper() for x in ['CZ','CZECH','DABING','SK'])
        watched = ident in watched_db

        color  = 'gray' if watched else 'white'
        prefix = '[COLOR yellow][CZ][/COLOR] ' if is_cz else ''
        wmark  = '[COLOR gray][✓][/COLOR] ' if watched else ''
        label  = '%s%s[COLOR orange][WS][/COLOR] [COLOR gray]%s[/COLOR] [COLOR %s]%s[/COLOR]' % (
            wmark, prefix, sizelize(item.get('size', 0)), color, name.replace('.', ' '))

        play_url = get_url(action='ws_play', ident=ident, name=name)
        li = xbmcgui.ListItem(label=label, path=play_url)
        _set_video_info(li, {'title': name})
        li.setProperty('IsPlayable', 'true')
        li.setArt({'icon': _icon, 'thumb': _icon, 'fanart': _fanart})
        li.addContextMenuItems([
            ('Titulky',           'RunPlugin(%s)' % get_url(action='subtitles', ident=ident, name=name)),
            ('Oznacit shlédnute', 'RunPlugin(%s)' % get_url(action='mark_watched', ident=ident)),
            ('☆ Pridat film do oblibenych', 'RunPlugin(%s)' % get_url(
                action='movie_fav_add', fav_id='ws_%s' % ident,
                title=name.replace('.',' ').strip(), search_q=name.replace('.',' ').strip(),
                poster='', year='', mtype='movie')),
        ])
        xbmcplugin.addDirectoryItem(_handle, play_url, li, False)

    # Hellspy výsledky
    for item in hs_results:
        fid    = item['id']
        fhash  = item['hash']
        title  = item['title']
        size_s = item.get('size_str', '')
        dur    = item.get('duration', '')
        thumb  = item['thumbs'][0] if item.get('thumbs') else _icon

        hs_watched = ('hs_' + str(fid)) in watched_db
        wmark = '[COLOR gray][✓][/COLOR] ' if hs_watched else ''
        label = '%s[COLOR cyan][HS][/COLOR] [COLOR gray]%s[/COLOR] %s' % (wmark, size_s, title)
        if dur: label += ' [COLOR gray][%s][/COLOR]' % dur

        hs_play_url = get_url(action='hs_play', fid=fid, fhash=fhash, title=title)
        li = xbmcgui.ListItem(label=label, path=hs_play_url)
        _set_video_info(li, {'title': title})
        li.setProperty('IsPlayable', 'true')
        li.setArt({'icon': _icon, 'thumb': thumb, 'fanart': _fanart})
        li.addContextMenuItems([
            ('Oznacit shlédnute', 'RunPlugin(%s)' % get_url(action='mark_watched', ident='hs_' + str(fid))),
            ('☆ Pridat do oblibenych', 'RunPlugin(%s)' % get_url(
                action='movie_fav_add', fav_id='hs_%s' % fid,
                title=title, search_q=title, poster='', year='', mtype='movie')),
        ])
        xbmcplugin.addDirectoryItem(_handle, hs_play_url, li, False)

    # Stránkování
    if len(hs_results) >= 64:
        li = xbmcgui.ListItem(label='[COLOR yellow]>> Další výsledky Hellspy[/COLOR]')
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='combined_search', what=what, page=page+1), li, True)

    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# PŘEHRÁVÁNÍ WEBSHARE
# ---------------------------------------------------------------------------
def ws_play(params):
    token = ws_revalidate()
    if not token:
        xbmc.log('WS: token chybi, nelze prehrat', xbmc.LOGERROR)
        xbmcgui.Dialog().ok('StreamSpy – Webshare',
            'Nejsi prihlasen na Webshare. Jdi do Nastaveni a zadej prihlasovaci udaje.')
        _addon.openSettings()
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    ident = params.get('ident', '')
    name  = (params.get('name') or '').strip()

    link_text  = None
    last_error = 'neznama chyba'

    # Zkus primo file_link bez download_type – nejrychlejsi cesta
    data = {'ident': ident, 'wst': token}
    res  = ws_api('file_link', data)
    xml  = parse_xml(res)

    if xml is not None and is_ok(xml):
        link_el = xml.find('link')
        if link_el is not None and link_el.text and link_el.text.strip():
            link_text = link_el.text.strip()

    # Pokud selhal, zkus znovu po re-loginu
    if not link_text:
        msg_el = xml.find('message') if xml is not None else None
        last_error = msg_el.text if msg_el is not None and msg_el.text else 'API chyba'
        xbmc.log('WS file_link selhal: %s' % last_error, xbmc.LOGWARNING)

        if any(x in last_error.lower() for x in ['login','token','unauthorized','logged']):
            token = ws_login()
            if token:
                data['wst'] = token
                res  = ws_api('file_link', data)
                xml  = parse_xml(res)
                if xml is not None and is_ok(xml):
                    link_el = xml.find('link')
                    if link_el is not None and link_el.text:
                        link_text = link_el.text.strip()

    if not link_text:
        poperror('WS: Nelze prehrat: ' + last_error, 5000)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return
    if not name: name = ident
    _save_resume_name(ident, name)

    li = xbmcgui.ListItem(label=name, path=link_text)
    _set_video_info(li, {'title': name})

    resume = get_resume(ident)
    if resume and resume.get('pct', 0) > 2:
        if xbmcgui.Dialog().yesno('Pokračovat?',
                                   'Pokračovat od %d%% (%s)?' % (resume['pct'], fmt_time(resume['position'])),
                                   yeslabel='Pokračovat', nolabel='Od začátku'):
            li.setProperty('ResumeTime', str(resume['position']))
            li.setProperty('TotalTime',  str(resume['total']))

    sub_path = profile_path(re.sub(r'[<>:"/\\|?*]', '_', name) + '.srt')
    if os.path.exists(sub_path):
        li.setSubtitles([sub_path])

    xbmcplugin.setResolvedUrl(_handle, True, li)
    _start_monitor(ident, name, source='ws')

# ---------------------------------------------------------------------------
# PŘEHRÁVÁNÍ HELLSPY
# ---------------------------------------------------------------------------
def hs_play(params):
    fid   = params.get('fid', '')
    fhash = params.get('fhash', '')
    title = params.get('title', '')

    if not fhash or not fid:
        poperror('HS: Chybí ID nebo hash videa')
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    popinfo('HS: Načítám stream...', 2000)
    detail = hs_video_detail(fid, fhash)
    if not detail:
        poperror('HS: Nepodařilo se načíst detail videa')
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    convs = detail.get('conversions', {})
    if not convs:
        poperror('HS: Žádný stream dostupný')
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    keys = sorted(convs.keys(), key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
    if len(convs) > 1:
        options = ['%sp' % k if k.isdigit() else k for k in keys]
        choice  = xbmcgui.Dialog().select('Vyber kvalitu', options)
        if choice < 0:
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return
        stream_url = convs[keys[choice]]
    else:
        stream_url = list(convs.values())[0]

    if not stream_url:
        poperror('HS: Prázdný stream URL')
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return

    thumbs = detail.get('thumbs', [])
    thumb  = thumbs[0] if thumbs else _icon

    li = xbmcgui.ListItem(label=title, path=stream_url)
    _set_video_info(li, {'title': title, 'duration': detail.get('duration', 0)})
    li.setArt({'thumb': thumb, 'icon': _icon, 'fanart': _fanart})
    li.setProperty('IsPlayable', 'true')

    mark_watched('hs_' + str(fid))
    xbmcplugin.setResolvedUrl(_handle, True, li)
    _start_monitor(fid, title, source='hs', fhash=fhash)

# ---------------------------------------------------------------------------
# MONITOROVACÍ VLÁKNO (resume + auto-next)
# ---------------------------------------------------------------------------
def _get_next_episode(name):
    if not name: return None
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', name)
    if not m: m = re.search(r'(\d{1,2})[xX](\d{1,2})', name)
    if not m: return None
    season  = int(m.group(1))
    episode = int(m.group(2))
    series  = re.sub(r'[\.\-_]+$', '', name[:m.start()].strip()).strip()
    series  = re.sub(r'\s+', ' ', series).strip()
    if not series: return None
    return (series, season, episode + 1)

def _start_monitor(ident, name, source='ws', fhash=''):
    def _monitor():
        monitor = xbmc.Monitor()
        player  = xbmc.Player()

        # Cekej az 60 sekund nez zacne prehravani
        for _ in range(120):
            if monitor.abortRequested(): return
            if player.isPlayingVideo(): break
            xbmc.sleep(500)
        else:
            return

        xbmc.sleep(2000)
        dialog_shown = False
        consecutive_errors = 0

        while not monitor.abortRequested():
            if not player.isPlayingVideo():
                break
            try:
                pos = player.getTime()
                tot = player.getTotalTime()
                consecutive_errors = 0
                if tot > 60:
                    save_resume(ident, name, pos, tot)
                    remaining = tot - pos
                    if not dialog_shown and 0 < remaining <= 15:
                        if _addon.getSetting('autonext') == 'true':
                            next_ep = _get_next_episode(name)
                            if next_ep:
                                dialog_shown = True
                                ns, nseason, nepisode = next_ep
                                prev_code = 'S%02dE%02d' % (nseason, nepisode - 1)
                                next_code = 'S%02dE%02d' % (nseason, nepisode)
                                msg = 'Skoncil %s – prehrat dalsi dil %s?' % (prev_code, next_code)
                                if xbmcgui.Dialog().yesno('Dalsi dil', msg,
                                                           yeslabel='Prehrat', nolabel='Ne'):
                                    _play_next(ns, nseason, nepisode, preferred_source=source)
            except Exception as e:
                consecutive_errors += 1
                xbmc.log('Monitor error (%d): %s' % (consecutive_errors, str(e)), xbmc.LOGWARNING)
                if consecutive_errors > 10:
                    break
            xbmc.sleep(3000)

    threading.Thread(target=_monitor, daemon=True).start()

def _play_next(series, season, episode, preferred_source='ws'):
    ep_code  = 'S%02dE%02d' % (season, episode)
    search_q = '%s %s' % (series, ep_code)
    xbmc.log('AutoNext: hledám "%s" (zdroj: %s)' % (search_q, preferred_source), xbmc.LOGINFO)

    # Zkus preferovaný zdroj nejdřív
    if preferred_source == 'ws' and ws_enabled():
        token = ws_revalidate()
        if token:
            res = ws_api('search', {'what': search_q, 'category': 'video',
                                     'sort': 'largest', 'limit': 10, 'offset': 0, 'wst': token})
            xml = parse_xml(res)
            if xml is not None and is_ok(xml):
                min_size = get_min_size_bytes()
                best = None
                for f in xml.iter('file'):
                    item = todict(f)
                    size = float(item.get('size', 0) or 0)
                    if size < min_size: continue
                    n_up = item.get('name', '').upper()
                    if not any(p in n_up for p in [ep_code.upper(), '%dX%02d' % (season, episode)]):
                        continue
                    if best is None or size > float(best.get('size', 0) or 0):
                        best = item
                if best:
                    b_ident = best.get('ident', '')
                    bname   = best.get('name', ep_code)
                    data = {'ident': b_ident, 'wst': token}
                    res2 = ws_api('file_link', data)
                    xml2 = parse_xml(res2)
                    if xml2 is not None and is_ok(xml2):
                        link_el = xml2.find('link')
                        if link_el is not None and link_el.text:
                            li = xbmcgui.ListItem(label=bname, path=link_el.text.strip())
                            _set_video_info(li, {'title': bname})
                            li.setProperty('IsPlayable', 'true')
                            _save_resume_name(b_ident, bname)
                            xbmc.Player().play(link_el.text.strip(), li)
                            _start_monitor(b_ident, bname, source='ws')
                            return

    # Fallback na Hellspy
    if hs_enabled():
        results = hs_search(search_q)
        best = None
        for item in results:
            if ep_code.upper() not in item['title'].upper(): continue
            size_m = re.search(r'([\d,\.]+)\s*(GB|MB)', item.get('size_str', ''))
            size_b = 0
            if size_m:
                val = float(size_m.group(1).replace(',', '.'))
                size_b = val * (1073741824 if size_m.group(2) == 'GB' else 1048576)
            item['_size_b'] = size_b
            if best is None or size_b > best.get('_size_b', 0):
                best = item
        if best:
            detail = hs_video_detail(best['id'], best['hash'])
            if detail:
                convs = detail.get('conversions', {})
                if convs:
                    stream_url = list(convs.values())[0]
                    bname = best['title']
                    li = xbmcgui.ListItem(label=bname, path=stream_url)
                    _set_video_info(li, {'title': bname})
                    li.setProperty('IsPlayable', 'true')
                    xbmc.Player().play(stream_url, li)
                    _start_monitor(best['id'], bname, source='hs', fhash=best['hash'])
                    return

    popinfo('Další díl %s nenalezen' % ep_code)

# ---------------------------------------------------------------------------
# NOVINKY
# ---------------------------------------------------------------------------
def novinky(params):
    key    = get_tmdb_key()
    mtype  = params.get('mtype', 'movie')
    dabing = params.get('dabing', '0') == '1'
    page   = params.get('page', '1')
    if not key:
        xbmcplugin.endOfDirectory(_handle); return
    suffix = ' dabing' if dabing else ''
    ep     = '/movie/now_playing' if mtype == 'movie' else '/tv/on_the_air'
    url    = '%s%s?api_key=%s&language=cs-CZ&page=%s' % (TMDB_URL, ep, key, page)
    data   = tmdb_get(url)
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return
    for i in data.get('results', []):
        t_cs   = i.get('name') or i.get('title') or ''
        t_orig = i.get('original_name') or i.get('original_title') or t_cs
        date   = i.get('first_air_date') or i.get('release_date') or ''
        year   = date.split('-')[0] if '-' in date else ''
        rating = i.get('vote_average', 0)
        if t_cs.lower() != t_orig.lower():
            search_q = ('%s|%s %s%s' % (t_orig, t_cs, year, suffix)).strip()
        else:
            search_q = ('%s %s%s' % (t_cs, year, suffix)).strip()
        label = t_cs
        if year:   label += ' [COLOR gray](%s)[/COLOR]' % year
        if rating: label += ' [COLOR gold][%.1f][/COLOR]' % rating
        if dabing: label += ' [COLOR yellow][CZ][/COLOR]'
        li = xbmcgui.ListItem(label=label)
        poster = i.get('poster_path')
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon,
                   'thumb':  TMDB_IMG + poster if poster else _icon,
                   'icon': _icon, 'fanart': _fanart})
        fav_id_n = 'tmdb_%s' % i.get('id', search_q)
        is_fav_n = is_movie_favorite(fav_id_n)
        fav_star_n = '★ Odebrat z oblíbených' if is_fav_n else '☆ Přidat film do oblíbených'
        _set_video_info(li, {'title': t_cs, 'plot': i.get('overview', ''),
                              'year': int(year) if year.isdigit() else 0, 'rating': rating})
        li.addContextMenuItems([
            (fav_star_n, 'RunPlugin(%s)' % get_url(
                action='movie_fav_add', fav_id=fav_id_n,
                title=t_cs, search_q=search_q, poster=i.get('poster_path',''),
                year=year, mtype=mtype)),
        ])
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='combined_search', what=search_q), li, True)
    total = data.get('total_pages', 1)
    cur   = int(page)
    if cur < total:
        xbmcplugin.addDirectoryItem(
            _handle,
            get_url(action='novinky', mtype=mtype, dabing='1' if dabing else '0', page=str(cur+1)),
            xbmcgui.ListItem(label='[COLOR yellow]>> Další stránka (%d/%d)[/COLOR]' % (cur+1, total)), True)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# TITULKY
# ---------------------------------------------------------------------------
def fetch_subtitles(params):
    key  = _addon.getSetting('opensub_key')
    name = params.get('name', '')
    if not key:
        popinfo('OpenSubtitles API klíč není nastaven'); return
    try:
        q_name = re.sub(r'[\.\-_]', ' ', name)
        q_name = re.sub(r'\s+', ' ', q_name).strip()
        r = _ws_session.get(OPENSUB_URL + '/subtitles',
                             headers={'Api-Key': key, 'User-Agent': OPENSUB_UA},
                             params={'query': q_name, 'languages': 'cs,sk', 'per_page': 10},
                             timeout=10)
        r.raise_for_status()
        subs = r.json().get('data', [])
    except Exception as e:
        xbmc.log('OpenSub error: %s' % e, xbmc.LOGERROR)
        popinfo('Chyba při hledání titulků'); return
    if not subs:
        popinfo('Žádné titulky nenalezeny'); return
    choices = []
    for s in subs:
        attr = s.get('attributes', {})
        choices.append('%s | %s | ↓%d' % (attr.get('language','?'), attr.get('release','?')[:40], attr.get('download_count',0)))
    idx = xbmcgui.Dialog().select('Vyberte titulky', choices)
    if idx < 0: return
    try:
        attr    = subs[idx].get('attributes', {})
        file_id = attr.get('files', [{}])[0].get('file_id')
        r2 = _ws_session.post(OPENSUB_URL + '/download',
                               headers={'Api-Key': key, 'User-Agent': OPENSUB_UA, 'Content-Type': 'application/json'},
                               json={'file_id': file_id}, timeout=10)
        r2.raise_for_status()
        dl_url = r2.json().get('link')
        r3 = _ws_session.get(dl_url, timeout=15)
        r3.raise_for_status()
        sub_path = profile_path(re.sub(r'[<>:"/\\|?*]', '_', name) + '.srt')
        with open(sub_path, 'wb') as f:
            f.write(r3.content)
        popinfo('Titulky staženy ✓')
    except Exception as e:
        xbmc.log('OpenSub dl error: %s' % e, xbmc.LOGERROR)
        popinfo('Chyba stahování titulků')

# ---------------------------------------------------------------------------
# HISTORIE, OBLÍBENÉ, RESUME, SHLÉDNUTÉ
# ---------------------------------------------------------------------------
def add_to_search_history(query):
    h = load_json('search_history.json', [])
    if not isinstance(h, list): h = []
    h = [x for x in h if x.lower() != query.lower()]
    h.insert(0, query)
    save_json('search_history.json', h[:MAX_HISTORY])

def show_search_history():
    h = load_json('search_history.json', [])
    if not h:
        xbmcplugin.addDirectoryItem(_handle, '', xbmcgui.ListItem(label='[COLOR gray]Historie je prázdná[/COLOR]'), False)
    for q in h:
        li = xbmcgui.ListItem(label=q)
        li.setArt({'icon': _menu_icon('history')})
        li.addContextMenuItems([('Smazat ze historie', 'RunPlugin(%s)' % get_url(action='del_history', query=q))])
        xbmcplugin.addDirectoryItem(_handle, get_url(action='combined_search', what=q), li, True)
    xbmcplugin.addDirectoryItem(_handle, get_url(action='clear_history'),
                                 xbmcgui.ListItem(label='[COLOR red]Smazat celou historii[/COLOR]'), False)
    xbmcplugin.endOfDirectory(_handle)

def load_favorites():
    return load_json('favorites.json', [])

def save_favorites(favs):
    save_json('favorites.json', favs)

def movie_fav_add(params):
    """Ulozi film (z TMDB nebo vyhledavani) do oblibenych – ne soubor, ale film."""
    fav_id  = params.get('fav_id', '')   # unikatni klic – napr. tmdb_123 nebo search_Název
    title   = params.get('title', '')
    search_q= params.get('search_q', title)
    poster  = params.get('poster', '')
    year    = params.get('year', '')
    mtype   = params.get('mtype', 'movie')  # movie nebo tv

    if not fav_id or not title:
        return

    favs = load_favorites()
    if any(f.get('fav_id') == fav_id for f in favs):
        # Odeber
        save_favorites([f for f in favs if f.get('fav_id') != fav_id])
        popinfo('Odebráno z oblíbených')
    else:
        # Pridej
        if len(favs) >= MAX_FAVORITES:
            favs = favs[:MAX_FAVORITES-1]
        favs.insert(0, {
            'fav_id':   fav_id,
            'title':    title,
            'search_q': search_q,
            'poster':   poster,
            'year':     year,
            'mtype':    mtype,
            'ts':       int(time.time()),
        })
        save_favorites(favs)
        popinfo('Přidáno do oblíbených ★')
    xbmc.executebuiltin('Container.Refresh')

def is_movie_favorite(fav_id):
    return any(f.get('fav_id') == fav_id for f in load_favorites())

def show_favorites():
    favs = load_favorites()
    if not favs:
        xbmcplugin.addDirectoryItem(
            _handle, '', xbmcgui.ListItem(label='[COLOR gray]Žádné oblíbené filmy[/COLOR]'), False)
        xbmcplugin.endOfDirectory(_handle)
        return

    xbmcplugin.setContent(_handle, 'movies')
    xbmcplugin.setPluginCategory(_handle, 'Oblíbené')

    for f in favs:
        fav_id   = f.get('fav_id', '')
        title    = f.get('title', '')
        search_q = f.get('search_q', title)
        poster   = f.get('poster', '')
        year     = f.get('year', '')
        mtype    = f.get('mtype', 'movie')

        label = title
        if year: label += ' [COLOR gray](%s)[/COLOR]' % year

        li = xbmcgui.ListItem(label=label)
        _set_video_info(li, {'title': title, 'year': int(year) if year.isdigit() else 0})
        poster_url = TMDB_IMG + poster if poster else _icon
        li.setArt({'poster': poster_url, 'thumb': poster_url, 'icon': _icon, 'fanart': _fanart})

        if mtype == 'tv':
            # Seriál – jdi na výběr sezón (potřebujeme tv_id uložené)
            tv_id = f.get('tv_id', '')
            if tv_id:
                u = get_url(action='tmdb_seasons', tv_id=tv_id, tv_name=search_q)
            else:
                u = get_url(action='combined_search', what=search_q)
            is_dir = True
        else:
            u = get_url(action='combined_search', what=search_q)
            is_dir = True

        li.addContextMenuItems([
            ('★ Odebrat z oblíbených', 'RunPlugin(%s)' % get_url(
                action='movie_fav_add', fav_id=fav_id, title=title,
                search_q=search_q, poster=poster, year=year, mtype=mtype)),
        ])
        xbmcplugin.addDirectoryItem(_handle, u, li, is_dir)

    xbmcplugin.endOfDirectory(_handle)

def mark_watched(ident):
    db = load_json('watched.json', {})
    db[ident] = int(time.time())
    save_json('watched.json', db)

def load_watched():
    return load_json('watched.json', {})

def is_watched(ident):
    return ident in load_watched()

def _save_resume_name(ident, name):
    if not ident or not name or name == ident: return
    db = load_json('resume.json', {})
    entry = db.get(ident, {})
    entry['name'] = name
    entry['ts']   = entry.get('ts', int(time.time()))
    db[ident] = entry
    save_json('resume.json', db)

def save_resume(ident, name, position, total, fhash=''):
    if total < 60: return
    pct = int(position / total * 100) if total > 0 else 0
    db  = load_json('resume.json', {})
    entry = {'name': name, 'position': position, 'total': total, 'pct': pct, 'ts': int(time.time())}
    if fhash: entry['fhash'] = fhash
    db[ident] = entry
    if pct >= 90: mark_watched(ident)
    if len(db) > 100:
        oldest = sorted(db.items(), key=lambda x: x[1].get('ts', 0))
        for k, _ in oldest[:20]: del db[k]
    save_json('resume.json', db)

def get_resume(ident):
    return load_json('resume.json', {}).get(ident)

def show_resume_list():
    db = load_json('resume.json', {})
    if not db:
        xbmcplugin.addDirectoryItem(_handle, '', xbmcgui.ListItem(label='[COLOR gray]Nic k pokračování[/COLOR]'), False)
    for ident, entry in sorted(db.items(), key=lambda x: x[1].get('ts', 0), reverse=True):
        pct   = entry.get('pct', 0)
        name  = entry.get('name', ident)
        label = '%s [COLOR gray](%d%%)[/COLOR]' % (name, pct)
        li    = xbmcgui.ListItem(label=label)
        _set_video_info(li, {'title': name})
        li.setProperty('IsPlayable', 'true')
        li.setArt({'icon': _icon, 'fanart': _fanart})
        li.setProperty('ResumeTime', str(entry.get('position', 0)))
        li.setProperty('TotalTime',  str(entry.get('total', 0)))
        li.addContextMenuItems([('Smazat z pokračování', 'RunPlugin(%s)' % get_url(action='del_resume', ident=ident))])
        # Resume muze byt WS nebo HS – zkus podle toho jestli ident vypada jako cislo (HS) nebo hash (WS)
        if ident.isdigit():
            fhash = entry.get('fhash', '')
            url = get_url(action='hs_play', fid=ident, fhash=fhash, title=name)
        else:
            url = get_url(action='ws_play', ident=ident, name=name)
        xbmcplugin.addDirectoryItem(_handle, url, li, False)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# VIP INFO
# ---------------------------------------------------------------------------
def vip_info():
    token = _addon.getSetting('ws_token')
    if not token:
        popinfo('Nejsi přihlášen na Webshare'); return
    xml = parse_xml(ws_api('user_data', {'wst': token}))
    if xml is None or not is_ok(xml):
        popinfo('Nelze načíst info o účtu'); return
    username  = xml.find('username') or xml.find('login')
    vip_el    = xml.find('vip')
    until_el  = xml.find('vip_until')
    credits_el = xml.find('points')
    lines = []
    if username is not None and username.text: lines.append('Účet: %s' % username.text)
    if vip_el   is not None: lines.append('VIP: %s' % ('Aktivní ✓' if vip_el.text == '1' else 'Neaktivní'))
    if until_el is not None and until_el.text: lines.append('VIP do: %s' % until_el.text)
    if credits_el is not None and credits_el.text: lines.append('Kredity: %s' % credits_el.text)
    xbmcgui.Dialog().ok('Webshare účet', '\n'.join(lines) if lines else 'Žádné informace')

# ---------------------------------------------------------------------------
# HLAVNÍ MENU
# ---------------------------------------------------------------------------
def menu():
    token = _addon.getSetting('ws_token')
    if not token and ws_enabled():
        threading.Thread(target=ws_login, daemon=True).start()
    elif token and ws_enabled():
        threading.Thread(target=ws_revalidate, daemon=True).start()

    vip_label = get_vip_label()

    ws_tag = '[COLOR orange][WS][/COLOR]' if ws_enabled() else '[COLOR gray][WS off][/COLOR]'
    hs_tag = '[COLOR cyan][HS][/COLOR]'   if hs_enabled() else '[COLOR gray][HS off][/COLOR]'

    items = [
        (get_url(action='tmdb_sub', mode='movie'),
         '🎬  Filmy (TMDB)', True, 'movies'),
        (get_url(action='tmdb_sub', mode='tv'),
         '📺  Seriály (TMDB)', True, 'series'),
        (get_url(action='tmdb_search'),
         '🔍  Hledat (TMDB)', True, 'search_tmdb'),
        (get_url(action='search'),
         '🔍  Hledat  %s + %s' % (ws_tag, hs_tag), True, 'search_ws'),
        (get_url(action='hs_search_direct'),
         '🔍  Hledat [COLOR cyan][HS][/COLOR]', True, 'search_hs'),
        (get_url(action='search_history'),
         '🕐  Historie hledání', True, 'history'),
        (get_url(action='tmdb_list', endpoint='/trending/all/day'),
         '[COLOR orange]▶  Právě se sleduje[/COLOR]', True, 'trending'),
        (get_url(action='resume_list'),
         '[COLOR lightblue]⏩  Pokračovat ve sledování[/COLOR]', True, 'resume'),
        (get_url(action='novinky'),
         '[COLOR lime]🆕  Novinky[/COLOR]', True, 'new'),
        (get_url(action='novinky', dabing='1'),
         '[COLOR lime]🆕  Novinky dabované[/COLOR]', True, 'new_dub'),
        (get_url(action='favorites'),
         '[COLOR gold]★  Oblíbené[/COLOR]', True, 'favorites'),
        (get_url(action='cache_clear'),
         '[COLOR gray]🗑  Vymazat cache[/COLOR]', False, 'cache'),
        (get_url(action='settings'),
         '⚙  Nastavení', False, 'settings'),
    ]
    if vip_label and ws_enabled():
        items.insert(10, (get_url(action='vip_info'), vip_label, False, 'vip'))

    xbmcplugin.setContent(_handle, 'files')
    xbmcplugin.setPluginCategory(_handle, 'StreamSpy')
    for u, label, isdir, icon_name in items:
        li = xbmcgui.ListItem(label=label)
        ic = _menu_icon(icon_name)
        li.setArt({'icon': ic, 'thumb': ic, 'fanart': _fanart})
        xbmcplugin.addDirectoryItem(_handle, u, li, isdir)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# ROUTER
# ---------------------------------------------------------------------------
def router(paramstring):
    p = dict(parse_qsl(paramstring))
    a = p.get('action')

    if a == 'tmdb_sub':
        m = p.get('mode', 'movie')
        items = [
            ('/%s/popular'   % m, 'Populární'),
            ('/%s/top_rated' % m, 'Nejlépe hodnocené'),
        ]
        if m == 'movie':
            items += [('/movie/now_playing', 'Právě v kinech'), ('/movie/upcoming', 'Připravované')]
        else:
            items += [('/tv/on_the_air', 'Právě vysílané'), ('/tv/airing_today', 'Dnes vysílané')]
        items.append(('genres', 'Žánry'))
        for ep, lbl in items:
            if ep == 'genres':
                xbmcplugin.addDirectoryItem(
                    _handle, get_url(action='tmdb_genres', mode=m),
                    xbmcgui.ListItem(label=lbl), True)
            else:
                xbmcplugin.addDirectoryItem(
                    _handle, get_url(action='tmdb_list', endpoint=ep),
                    xbmcgui.ListItem(label=lbl), True)
        xbmcplugin.endOfDirectory(_handle)

    elif a == 'tmdb_genres':
        gs = MOVIE_GENRES if p.get('mode') == 'movie' else TV_GENRES
        for g in gs:
            xbmcplugin.addDirectoryItem(
                _handle,
                get_url(action='tmdb_list', endpoint='/discover/' + p.get('mode','movie'), genre_id=g['id']),
                xbmcgui.ListItem(label=g['name']), True)
        xbmcplugin.endOfDirectory(_handle)

    elif a == 'tmdb_list':        tmdb_list(p)
    elif a == 'tmdb_seasons':     tmdb_seasons(p)
    elif a == 'tmdb_episodes':    tmdb_episodes(p)

    elif a == 'tmdb_search':
        kb = xbmc.Keyboard('', 'Hledat na TMDB')
        kb.doModal()
        if kb.isConfirmed() and kb.getText():
            tmdb_list({'endpoint': '/search/multi', 'query': kb.getText()})
        else:
            xbmcplugin.endOfDirectory(_handle)

    elif a == 'hs_search_direct':
        page_hs = int(p.get('page', 1))
        query_hs = p.get('what', '')
        if not query_hs:
            kb = xbmc.Keyboard('', 'Hledat na Hellspy')
            kb.doModal()
            if not kb.isConfirmed() or not kb.getText():
                xbmcplugin.endOfDirectory(_handle)
                return
            query_hs = kb.getText()
            add_to_search_history(query_hs)
        # Razeni
        hs_sort_opts = [('relevance','Relevance'), ('size','Velikost'), ('title','Název'), ('duration','Délka')]
        sort_labels  = [x[1] for x in hs_sort_opts]
        cur_sort     = _addon.getSetting('hs_sort') or 'size'
        cur_idx      = next((i for i,x in enumerate(hs_sort_opts) if x[0]==cur_sort), 1)
        results = hs_search(query_hs, page=page_hs)
        if not results:
            popinfo('Hellspy: nic nenalezeno pro: ' + query_hs)
            xbmcplugin.endOfDirectory(_handle)
            return
        # Razeni
        if cur_sort == 'size':
            results.sort(key=lambda x: _parse_size(x.get('size_str', '')), reverse=True)
        elif cur_sort == 'title':
            results.sort(key=lambda x: x.get('title', '').lower())
        elif cur_sort == 'duration':
            results.sort(key=lambda x: _parse_duration(x.get('duration', '')), reverse=True)
        xbmcplugin.setPluginCategory(_handle, 'Hellspy: %s (%d)' % (query_hs, len(results)))
        xbmcplugin.setContent(_handle, 'videos')
        watched_db_hs = load_watched()
        for item in results:
            fid   = item['id']
            fhash = item['hash']
            title = item['title']
            size_s= item.get('size_str', '')
            dur   = item.get('duration', '')
            thumb = item['thumbs'][0] if item.get('thumbs') else _icon
            hs_watched = ('hs_' + str(fid)) in watched_db_hs
            wmark = '[COLOR gray][✓][/COLOR] ' if hs_watched else ''
            lbl   = '%s[COLOR cyan][HS][/COLOR] [COLOR gray]%s[/COLOR] %s' % (wmark, size_s, title)
            if dur: lbl += ' [COLOR gray][%s][/COLOR]' % dur
            u  = get_url(action='hs_play', fid=fid, fhash=fhash, title=title)
            li = xbmcgui.ListItem(label=lbl, path=u)
            _set_video_info(li, {'title': title})
            li.setProperty('IsPlayable', 'true')
            li.setArt({'icon': _icon, 'thumb': thumb, 'fanart': _fanart})
            li.addContextMenuItems([
                ('Oznacit shlédnute', 'RunPlugin(%s)' % get_url(action='mark_watched', ident='hs_' + str(fid))),
                ('Razeni: ' + sort_labels[cur_idx], 'RunPlugin(%s)' % get_url(
                    action='hs_sort_set', what=query_hs, page=str(page_hs))),
            ])
            xbmcplugin.addDirectoryItem(_handle, u, li, False)
        if len(results) >= 64:
            xbmcplugin.addDirectoryItem(
                _handle, get_url(action='hs_search_direct', what=query_hs, page=page_hs+1),
                xbmcgui.ListItem(label='[COLOR yellow]>> Dalsi stranka[/COLOR]'), True)
        xbmcplugin.endOfDirectory(_handle)

    elif a == 'hs_sort_set':
        hs_sort_opts = [('relevance','Relevance'), ('size','Velikost'), ('title','Název'), ('duration','Délka')]
        idx = xbmcgui.Dialog().select('Razeni Hellspy vysledku', [x[1] for x in hs_sort_opts])
        if idx >= 0:
            _addon.setSetting('hs_sort', hs_sort_opts[idx][0])
            xbmc.executebuiltin('Container.Refresh')

    elif a == 'combined_search':
        combined_search(p.get('what', ''), int(p.get('ws_offset', 0)), int(p.get('page', 1)))

    elif a == 'search':
        kb = xbmc.Keyboard('', 'Zadejte název')
        kb.doModal()
        if kb.isConfirmed() and kb.getText():
            combined_search(kb.getText())
        else:
            xbmcplugin.endOfDirectory(_handle)

    elif a == 'ws_play':          ws_play(p)
    elif a == 'hs_play':          hs_play(p)
    elif a == 'search_history':   show_search_history()
    elif a == 'del_history':
        save_json('search_history.json', [x for x in load_json('search_history.json', []) if x != p.get('query','')])
        xbmc.executebuiltin('Container.Refresh')
    elif a == 'clear_history':
        save_json('search_history.json', [])
        xbmc.executebuiltin('Container.Refresh')
    elif a == 'favorites':        show_favorites()
    elif a == 'movie_fav_add':    movie_fav_add(p)
    elif a == 'resume_list':      show_resume_list()
    elif a == 'del_resume':
        db = load_json('resume.json', {})
        db.pop(p.get('ident', ''), None)
        save_json('resume.json', db)
        xbmc.executebuiltin('Container.Refresh')
    elif a == 'novinky':          novinky(p)
    elif a == 'mark_watched':
        mark_watched(p.get('ident', ''))
        xbmc.executebuiltin('Container.Refresh')
    elif a == 'subtitles':        fetch_subtitles(p)
    elif a == 'vip_info':         vip_info()
    elif a == 'cache_clear':      cache_clear()
    elif a == 'settings':         _addon.openSettings()
    else:                         menu()

if __name__ == '__main__':
    router(sys.argv[2][1:])
