# -*- coding: utf-8 -*-
# Module: default
# Author: Miky (enhanced v4)
# License: AGPL v.3
#
# NOVINKY v4:
#  - Cache výsledků vyhledávání (10 min TTL)
#  - Thumbnaily z TMDB u každého výsledku
#  - Filtrování podle kvality (vše / jen CZ / jen 1080p / jen 4K)
#  - Automatické přihlášení na pozadí při startu
#  - Počet výsledků v titulku stránky
#  - Řazení výsledků (relevance / velikost / datum / název)
#  - Sekce "Nedávno přidané" (Webshare new uploads)
#  - Označení shlédnutých souborů (šedě)
#  - Informace o VIP stavu v menu
#  - Opravená cache search výsledků

import io, os, sys, xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
import requests.cookies, hashlib, json, unidecode, re, requests, threading, time
from md5crypt import md5crypt

# -*- coding: utf-8 -*-
# Module: default
# Author: Miky (enhanced v4)
# License: AGPL v.3
#
# NOVINKY v4:
#  - Cache výsledků vyhledávání (10 min TTL)
#  - Thumbnaily z TMDB u každého výsledku
#  - Filtrování podle kvality (vše / jen CZ / jen 1080p / jen 4K)
#  - Automatické přihlášení na pozadí při startu
#  - Počet výsledků v titulku stránky
#  - Řazení výsledků (relevance / velikost / datum / název)
#  - Sekce "Nedávno přidané" (Webshare new uploads)
#  - Označení shlédnutých souborů (šedě)
#  - Informace o VIP stavu v menu
#  - Opravená cache search výsledků

import io, os, sys, xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
import requests.cookies, hashlib, json, unidecode, re, requests, threading, time

# ---------------------------------------------------------------------------
# MD5CRYPT (inline, Python 3)
# ---------------------------------------------------------------------------
from xml.etree import ElementTree as ET

try:
    from urllib.parse import urlencode, parse_qsl, quote_plus, quote as _quote
except ImportError:
    from urllib import urlencode, quote_plus
    from urlparse import parse_qsl

try:
    from xbmc import translatePath
except ImportError:
    from xbmcvfs import translatePath

# ---------------------------------------------------------------------------
# KONFIGURACE
# ---------------------------------------------------------------------------
BASE      = 'https://webshare.cz'
API       = BASE + '/api/'
UA        = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/81.0.4044.138 Safari/537.36")
HEADERS   = {'User-Agent': UA, 'Referer': BASE}
NONE_WHAT = '%#NONE#%'

TMDB_URL = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"

OPENSUB_URL = "https://api.opensubtitles.com/api/v1"
OPENSUB_UA  = "WebshareKodi v4.0"

CACHE_TTL        = 3 * 3600   # TMDB cache 3 hodiny
SEARCH_CACHE_TTL = 10 * 60    # Search cache 10 minut
MAX_HISTORY      = 50
MAX_FAVORITES    = 200
MAX_DL_THREADS   = 2
RETRY_COUNT      = 2

_url        = sys.argv[0]
_handle     = int(sys.argv[1])
_addon      = xbmcaddon.Addon()
_addon_id   = _addon.getAddonInfo('id')
_addon_path = _addon.getAddonInfo('path')

def _menu_icon(name):
    import os
    p = os.path.join(_addon_path, 'resources', 'icons', name + '.png')
    return p if os.path.exists(p) else _icon
_session    = requests.Session()
_session.headers.update(HEADERS)
_profile    = translatePath(_addon.getAddonInfo('profile'))
_addon_path = translatePath(_addon.getAddonInfo('path'))
_icon       = os.path.join(_addon_path, 'icon.png')

_dl_threads = {}
_dl_lock    = threading.Lock()

MOVIE_GENRES = [
    {"id": "28",    "name": "Akční"},          {"id": "12",    "name": "Dobrodružný"},
    {"id": "16",    "name": "Animovaný"},       {"id": "35",    "name": "Komedie"},
    {"id": "80",    "name": "Krimi"},           {"id": "99",    "name": "Dokumentární"},
    {"id": "18",    "name": "Drama"},           {"id": "10751", "name": "Rodinný"},
    {"id": "14",    "name": "Fantasy"},         {"id": "36",    "name": "Historický"},
    {"id": "27",    "name": "Horor"},           {"id": "10402", "name": "Hudební"},
    {"id": "9648",  "name": "Mysteriózní"},     {"id": "10749", "name": "Romantický"},
    {"id": "878",   "name": "Sci-Fi"},          {"id": "53",    "name": "Thriller"},
    {"id": "10752", "name": "Válečný"},         {"id": "37",    "name": "Western"},
]
TV_GENRES = [
    {"id": "10759", "name": "Akční a dobrodružný"}, {"id": "16",    "name": "Animovaný"},
    {"id": "35",    "name": "Komedie"},              {"id": "80",    "name": "Krimi"},
    {"id": "99",    "name": "Dokumentární"},          {"id": "18",    "name": "Drama"},
    {"id": "10751", "name": "Rodinný"},              {"id": "10762", "name": "Pro děti"},
    {"id": "9648",  "name": "Mysteriózní"},           {"id": "10765", "name": "Sci-Fi a Fantasy"},
]

EPISODE_RE = re.compile(r'\b(?:s\d{2}e\d{2}|\d{1,2}x\d{2})\b')

# Filtry kvality
QUALITY_FILTERS = [
    ('all',   'Vše'),
    ('cz',    'Jen CZ/SK'),
    ('4k',    'Jen 4K'),
    ('1080p', 'Jen 1080p'),
    ('720p',  'Jen 720p'),
]

# Řazení výsledků
SORT_OPTIONS = [
    ('score',  'Relevance'),
    ('size',   'Velikost ↓'),
    ('date',   'Nejnovější'),
    ('name',   'Název A-Z'),
]

# ---------------------------------------------------------------------------
# ZÁKLADNÍ POMOCNÉ FUNKCE
# ---------------------------------------------------------------------------
def get_url(**kwargs):
    return '{0}?{1}'.format(_url, urlencode(kwargs))

def popinfo(m, duration=3000):
    xbmcgui.Dialog().notification(_addon.getAddonInfo('name'), m, _icon, duration)

def get_min_size_bytes():
    try:
        return int(_addon.getSetting('min_size_mb') or 150) * 1024 * 1024
    except (ValueError, TypeError):
        return 150 * 1024 * 1024

def get_tmdb_key():
    key = _addon.getSetting('tmdb_key')
    if not key:
        xbmcgui.Dialog().ok("Chyba", "TMDB API klíč není nastaven.\nJdi do Nastavení a vyplň ho.")
        _addon.openSettings()
        return None
    return key

def sizelize(txtsize):
    if not txtsize:
        return "0B"
    try:
        s = float(txtsize)
    except (ValueError, TypeError):
        return str(txtsize)
    for u in ['B', 'KB', 'MB', 'GB']:
        if s < 1024.0:
            return "%3.1f%s" % (s, u)
        s /= 1024.0
    return str(txtsize)

def todict(xml, skip=[]):
    return {
        e.tag: (e.text if not list(e) else todict(e, skip))
        for e in xml if e.tag not in skip
    }

def profile_path(filename):
    if not os.path.exists(_profile):
        os.makedirs(_profile)
    return os.path.join(_profile, filename)

def load_json(filename, default=None):
    p = profile_path(filename)
    if os.path.exists(p):
        try:
            with io.open(p, 'r', encoding='utf8') as f:
                return json.loads(f.read())
        except (IOError, ValueError):
            pass
    return default if default is not None else {}

def save_json(filename, data):
    try:
        with io.open(profile_path(filename), 'w', encoding='utf8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
    except IOError as e:
        xbmc.log("JSON save error [%s]: %s" % (filename, e), xbmc.LOGERROR)

# ---------------------------------------------------------------------------
# RETRY + API VOLÁNÍ
# ---------------------------------------------------------------------------
def api(fnct, data, retries=RETRY_COUNT):
    for attempt in range(retries + 1):
        try:
            r = _session.post(API + fnct + "/", data=data, timeout=15)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            xbmc.log("WS API [%s] attempt %d: %s" % (fnct, attempt + 1, e), xbmc.LOGWARNING)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return None

def tmdb_get(url, retries=RETRY_COUNT):
    cached = cache_load(url)
    if cached is not None:
        return cached
    last_status = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=10)
            last_status = r.status_code
            r.raise_for_status()
            data = r.json()
            cache_save(url, data)
            return data
        except requests.HTTPError as e:
            xbmc.log("TMDB HTTP attempt %d: %s" % (attempt + 1, e), xbmc.LOGWARNING)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
            else:
                popinfo("Chyba TMDB (%s)" % last_status)
        except requests.RequestException as e:
            xbmc.log("TMDB net error: %s" % e, xbmc.LOGERROR)
            if attempt >= retries:
                popinfo("Síťová chyba TMDB")
            else:
                time.sleep(1.5 * (attempt + 1))
        except ValueError as e:
            xbmc.log("TMDB JSON error: %s" % e, xbmc.LOGERROR)
            break
    return None

def parse_xml(response):
    if response is None:
        return None
    try:
        return ET.fromstring(response.content)
    except ET.ParseError as e:
        xbmc.log("XML parse error: %s" % e, xbmc.LOGERROR)
        return None

def is_ok(xml):
    try:
        return xml.find('status').text == 'OK'
    except AttributeError:
        return False

# ---------------------------------------------------------------------------
# TMDB CACHE (disk, TTL 3h)
# ---------------------------------------------------------------------------
def cache_load(key):
    db    = load_json('tmdb_cache.json', {})
    entry = db.get(key)
    if entry and time.time() - entry.get('ts', 0) < CACHE_TTL:
        return entry.get('data')
    return None

def cache_save(key, data):
    db = load_json('tmdb_cache.json', {})
    if len(db) > 300:
        oldest = sorted(db.items(), key=lambda x: x[1].get('ts', 0))
        for k, _ in oldest[:50]:
            del db[k]
    db[key] = {'ts': time.time(), 'data': data}
    save_json('tmdb_cache.json', db)

def cache_clear():
    save_json('tmdb_cache.json', {})
    save_json('search_cache.json', {})
    popinfo("Cache vymazána")

# ---------------------------------------------------------------------------
# SEARCH CACHE (10 minut)
# ---------------------------------------------------------------------------
def search_cache_load(key):
    db    = load_json('search_cache.json', {})
    entry = db.get(key)
    if entry and time.time() - entry.get('ts', 0) < SEARCH_CACHE_TTL:
        return entry.get('data')
    return None

def search_cache_save(key, data):
    db = load_json('search_cache.json', {})
    # Max 50 cached queries
    if len(db) > 50:
        oldest = sorted(db.items(), key=lambda x: x[1].get('ts', 0))
        for k, _ in oldest[:10]:
            del db[k]
    db[key] = {'ts': time.time(), 'data': data}
    save_json('search_cache.json', db)

# ---------------------------------------------------------------------------
# AUTENTIZACE
# ---------------------------------------------------------------------------
def login():
    u = _addon.getSetting('wsuser')
    p = _addon.getSetting('wspass')
    if not u or not p:
        _addon.openSettings()
        return None
    res = api('salt', {'username_or_email': u})
    xml = parse_xml(res)
    if xml is None or not is_ok(xml):
        popinfo("Chyba přihlášení – nelze získat salt")
        return None
    s = xml.find('salt').text
    try:
        ep = hashlib.sha1(md5crypt(p.encode('utf-8'), s.encode('utf-8'))).hexdigest()
    except Exception:
        ep = hashlib.sha1(md5crypt(p.encode('utf-8'), s.encode('utf-8')).encode('utf-8')).hexdigest()
    xml = parse_xml(api('login', {'username_or_email': u, 'password': ep, 'keep_logged_in': 1}))
    if xml is not None and is_ok(xml):
        t = xml.find('token').text
        _addon.setSetting('token', t)
        _addon.setSetting('token_ts', str(int(time.time())))
        # Vyčistíme VIP cache při novém přihlášení
        _addon.setSetting('vip_status', '')
        _addon.setSetting('vip_until', '')
        return t
    popinfo("Přihlášení selhalo – zkontroluj jméno a heslo")
    return None

def revalidate():
    t = _addon.getSetting('token')
    if not t:
        return login()
    res = api('user_data', {'wst': t})
    xml = parse_xml(res)
    if xml is not None and is_ok(xml):
        # Uložíme VIP status
        try:
            vip_el = xml.find('vip')
            if vip_el is not None:
                _addon.setSetting('vip_status', vip_el.text or '0')
            until_el = xml.find('vip_until')
            if until_el is not None and until_el.text:
                _addon.setSetting('vip_until', until_el.text)
        except Exception:
            pass
        try:
            token_ts = int(_addon.getSetting('token_ts') or 0)
            if time.time() - token_ts > 23 * 3600:
                threading.Thread(target=login, daemon=True).start()
        except Exception:
            pass
        return t
    xbmc.log("Token expiroval, přihlašuji znovu...", xbmc.LOGINFO)
    return login()

def get_vip_label():
    """Vrátí VIP status pro zobrazení v menu."""
    vip = _addon.getSetting('vip_status')
    until = _addon.getSetting('vip_until')
    if vip == '1':
        return "[COLOR green]VIP aktivní%s[/COLOR]" % (" do %s" % until if until else "")
    elif vip == '0':
        return "[COLOR gray]Bez VIP[/COLOR]"
    return ""

# ---------------------------------------------------------------------------
# SHLÉDNUTÉ (watched)
# ---------------------------------------------------------------------------
def mark_watched(ident):
    db = load_json('watched.json', {})
    db[ident] = int(time.time())
    save_json('watched.json', db)

def is_watched(ident):
    db = load_json('watched.json', {})
    return ident in db

def load_watched():
    return load_json('watched.json', {})

# ---------------------------------------------------------------------------
# LISTITEM BUILDER
# ---------------------------------------------------------------------------
def tolistitem_enhanced(file, extra_cmds=None, thumb=None, watched=False):
    n_up  = file.get('name', '').upper()
    is_cz = any(x in n_up for x in ["CZ", "CZECH", "DABING", "SK"])
    color = "gray" if watched else "white"
    prefix  = "[COLOR yellow][CZ] [/COLOR]" if is_cz else ""
    watched_mark = "[COLOR gray][✓][/COLOR] " if watched else ""
    label = "%s%s[COLOR gray]%s[/COLOR] [COLOR %s]%s[/COLOR]" % (
        watched_mark, prefix,
        sizelize(file.get('size', 0)),
        color,
        file.get('name', '').replace('.', ' '))
    li = xbmcgui.ListItem(label=label)
    li.setInfo('video', {'title': file.get('name', '')})
    li.setProperty('IsPlayable', 'true')
    # Thumbnail z TMDB pokud je k dispozici, jinak ikona addonu
    art = {'icon': _icon, 'thumb': thumb or _icon}
    if thumb:
        art['poster'] = thumb
    li.setArt(art)
    cmds = [
        ("Info o souboru", 'RunPlugin(%s)' % get_url(action='info',      ident=file.get('ident', ''))),
        ("Stáhnout",       'RunPlugin(%s)' % get_url(action='download',  ident=file.get('ident', ''), name=file.get('name', ''))),
        ("Titulky",        'RunPlugin(%s)' % get_url(action='subtitles', ident=file.get('ident', ''), name=file.get('name', ''))),
        ("Označit jako shlédnuté", 'RunPlugin(%s)' % get_url(action='mark_watched', ident=file.get('ident', ''))),
    ]
    if extra_cmds:
        cmds += extra_cmds
    li.addContextMenuItems(cmds)
    return li

# ---------------------------------------------------------------------------
# HISTOIRE HLEDÁNÍ
# ---------------------------------------------------------------------------
def add_to_search_history(query):
    h = load_json('search_history.json', [])
    if not isinstance(h, list):
        h = []
    h = [x for x in h if x.lower() != query.lower()]
    h.insert(0, query)
    save_json('search_history.json', h[:MAX_HISTORY])

def show_search_history():
    h = load_json('search_history.json', [])
    if not h:
        xbmcplugin.addDirectoryItem(
            _handle, '', xbmcgui.ListItem(label="[COLOR gray]Historie je prázdná[/COLOR]"), False)
    for q in h:
        li = xbmcgui.ListItem(label=q)
        li.addContextMenuItems([
            ("Smazat ze historie", 'RunPlugin(%s)' % get_url(action='del_history', query=q))
        ])
        xbmcplugin.addDirectoryItem(_handle, get_url(action='ws_search', what=q), li, True)
    xbmcplugin.addDirectoryItem(
        _handle, get_url(action='clear_history'),
        xbmcgui.ListItem(label="[COLOR red]Smazat celou historii[/COLOR]"), False)
    xbmcplugin.endOfDirectory(_handle)

def del_from_history(params):
    save_json('search_history.json', [x for x in load_json('search_history.json', []) if x != params.get('query', '')])
    xbmc.executebuiltin('Container.Refresh')

def clear_history(params):
    save_json('search_history.json', [])
    xbmc.executebuiltin('Container.Refresh')

# ---------------------------------------------------------------------------
# OBLÍBENÉ
# ---------------------------------------------------------------------------
def load_favorites():
    return load_json('favorites.json', [])

def save_favorites(favs):
    save_json('favorites.json', favs)

def toggle_favorite(params):
    ident = params.get('ident', '')
    name  = params.get('name', '')
    favs  = load_favorites()
    existing = [f for f in favs if f.get('ident') == ident]
    if existing:
        favs = [f for f in favs if f.get('ident') != ident]
        save_favorites(favs)
        popinfo("Odebráno z oblíbených")
    else:
        if len(favs) >= MAX_FAVORITES:
            favs = favs[:MAX_FAVORITES - 1]
        favs.insert(0, {'ident': ident, 'name': name, 'ts': int(time.time())})
        save_favorites(favs)
        popinfo("Přidáno do oblíbených ★")
    xbmc.executebuiltin('Container.Refresh')

def is_favorite(ident):
    return any(f.get('ident') == ident for f in load_favorites())

def show_favorites():
    favs = load_favorites()
    if not favs:
        xbmcplugin.addDirectoryItem(
            _handle, '', xbmcgui.ListItem(label="[COLOR gray]Žádné oblíbené[/COLOR]"), False)
    watched_db = load_watched()
    for f in favs:
        ident   = f.get('ident', '')
        name    = f.get('name', ident)
        watched = ident in watched_db
        label   = "[COLOR gray][✓][/COLOR] %s" % name if watched else name
        li      = xbmcgui.ListItem(label=label)
        li.setInfo('video', {'title': name})
        li.setProperty('IsPlayable', 'true')
        li.setArt({'icon': _icon, 'thumb': _icon})
        li.addContextMenuItems([
            ("★ Odebrat z oblíbených", 'RunPlugin(%s)' % get_url(action='fav_toggle', ident=ident, name=name)),
            ("Označit jako shlédnuté", 'RunPlugin(%s)' % get_url(action='mark_watched', ident=ident)),
        ])
        xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=ident, name=name), li, False)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# RESUME PŘEHRÁVÁNÍ
# ---------------------------------------------------------------------------
def _save_resume_name(ident, name):
    if not ident or not name or name == ident:
        return
    db = load_json('resume.json', {})
    entry = db.get(ident, {})
    entry['name'] = name
    entry['ts']   = entry.get('ts', int(time.time()))
    db[ident] = entry
    save_json('resume.json', db)

def save_resume(ident, name, position, total):
    if total < 60:
        return
    pct = int(position / total * 100) if total > 0 else 0
    db  = load_json('resume.json', {})
    db[ident] = {
        'name': name, 'position': position,
        'total': total, 'pct': pct, 'ts': int(time.time())
    }
    # Označíme jako shlédnuté pokud přehráno >90%
    if pct >= 90:
        mark_watched(ident)
    if len(db) > 100:
        oldest = sorted(db.items(), key=lambda x: x[1].get('ts', 0))
        for k, _ in oldest[:20]:
            del db[k]
    save_json('resume.json', db)

def get_resume(ident):
    return load_json('resume.json', {}).get(ident)

def del_resume(params):
    db = load_json('resume.json', {})
    db.pop(params.get('ident', ''), None)
    save_json('resume.json', db)
    xbmc.executebuiltin('Container.Refresh')

def show_resume_list():
    db = load_json('resume.json', {})
    if not db:
        xbmcplugin.addDirectoryItem(
            _handle, '', xbmcgui.ListItem(label="[COLOR gray]Nic k pokračování[/COLOR]"), False)
    items = sorted(db.items(), key=lambda x: x[1].get('ts', 0), reverse=True)
    for ident, entry in items:
        pct   = entry.get('pct', 0)
        name  = entry.get('name', ident)
        label = "%s [COLOR gray](%d%%)[/COLOR]" % (name, pct)
        li    = xbmcgui.ListItem(label=label)
        li.setInfo('video', {'title': name})
        li.setProperty('IsPlayable', 'true')
        li.setArt({'icon': _icon, 'thumb': _icon})
        li.setProperty('ResumeTime', str(entry.get('position', 0)))
        li.setProperty('TotalTime',  str(entry.get('total', 0)))
        li.addContextMenuItems([
            ("Smazat z pokračování", 'RunPlugin(%s)' % get_url(action='del_resume', ident=ident))
        ])
        xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=ident, name=name), li, False)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# VYHLEDÁVÁNÍ (WEBSHARE)
# ---------------------------------------------------------------------------
def dosearch(token, what, category, sort, limit, offset, action,
             quality_filter=None, sort_by=None, thumb_map=None):
    # Načteme výchozí hodnoty z nastavení pokud nejsou zadány
    if quality_filter is None:
        quality_filter = _addon.getSetting('default_quality') or 'all'
    if sort_by is None:
        sort_by = _addon.getSetting('default_sort') or 'score'
    if not what or what == NONE_WHAT:
        return
    if offset == 0:
        add_to_search_history(what)

    # Alternativní názvy oddělené |
    what_parts = what.split('|')
    alt_titles = []
    for part in what_parts:
        pc = unidecode.unidecode(part.strip().lower())
        pc = re.sub(r'[^a-z0-9 ]', ' ', pc)
        pc = ' '.join(pc.split())
        if pc:
            alt_titles.append(pc)

    query = alt_titles[-1] if alt_titles else unidecode.unidecode(what.lower())

    ep_match      = EPISODE_RE.search(query)
    query_episode = ep_match.group(0) if ep_match else None

    queries_to_try = list(dict.fromkeys(alt_titles))
    if not query_episode and not any(x in query for x in ['cz', 'czech', 'dabing']):
        queries_to_try.append(query + ' cz')

    # Search cache klíč
    cache_key = "%s|%s|%s" % (what, quality_filter, sort_by)

    # Zkusíme cache (jen pro první stránku)
    cached_files = None
    if offset == 0:
        cached_files = search_cache_load(cache_key)

    all_files = {}
    last_xml  = None

    if cached_files is not None:
        all_files = cached_files
        xbmc.log("Search cache HIT: %s" % what, xbmc.LOGDEBUG)
    else:
        for q in queries_to_try:
            res = api('search', {
                'what': q, 'category': category, 'sort': 'relevance',
                'limit': limit, 'offset': offset, 'wst': token, 'maybe_removed': 'true'
            })
            xml = parse_xml(res)
            if xml is None or not is_ok(xml):
                continue
            last_xml = xml
            for file in xml.iter('file'):
                item  = todict(file)
                ident = item.get('ident', '')
                if ident and ident not in all_files:
                    all_files[ident] = item

    if not all_files:
        popinfo("Žádné výsledky pro: " + what)
        xbmcplugin.endOfDirectory(_handle)
        return

    target_year   = re.search(r'\b(20\d{2}|19\d{2})\b', query)
    year_str      = target_year.group(0) if target_year else None
    min_size      = get_min_size_bytes()
    favs_idents   = {f['ident'] for f in load_favorites()}
    watched_db    = load_watched()

    def extract_words(title):
        t = title
        if year_str: t = t.replace(year_str, '')
        t = EPISODE_RE.sub('', t)
        return [w for w in t.split() if len(w) >= 3]

    required_words_sets = [extract_words(t) for t in alt_titles if extract_words(t)]
    if not required_words_sets:
        required_words_sets = [extract_words(query)]
    required_words = required_words_sets[0]

    files_list = []
    for item in all_files.values():
        try:
            size_bytes = float(item.get('size', 0))
        except (ValueError, TypeError):
            size_bytes = 0
        if size_bytes < min_size:
            continue

        name_norm  = unidecode.unidecode(item.get('name', '').lower())
        name_clean = re.sub(r'[.\-_]', ' ', name_norm)
        name_up    = item.get('name', '').upper()
        name_ep    = EPISODE_RE.search(name_norm)

        # Filtr epizod
        if query_episode:
            if not name_ep or name_ep.group(0) != query_episode:
                continue
        else:
            if name_ep:
                continue

        # Rok
        if year_str and year_str not in name_norm:
            continue

        # Title matching
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

        # Filtr kvality
        is_cz   = any(x in name_up for x in ["CZ", "CZECH", "DABING", "SK"])
        is_4k   = any(x in name_up for x in ["4K", "2160P"])
        is_1080 = any(x in name_up for x in ["1080P", "FULLHD"])
        is_720  = "720P" in name_up

        if quality_filter == 'cz'    and not is_cz:   continue
        if quality_filter == '4k'    and not is_4k:   continue
        if quality_filter == '1080p' and not is_1080: continue
        if quality_filter == '720p'  and not is_720:  continue

        # Skóre
        score = 0
        if is_cz:                      score += 5000000
        if is_4k:                      score += 4000000
        elif is_1080:                  score += 3000000
        elif is_720:                   score += 2000000
        score += size_bytes / 1024 / 1024 / 10
        try:
            score += float(item.get('ctime', 0)) / 1000000
        except (ValueError, TypeError):
            pass
        if item.get('ident') in favs_idents:
            score += 10000000
        if required_words:
            match_ratio = sum(1 for w in required_words if w in name_clean) / len(required_words)
            score += match_ratio * 1000000

        item['prio']     = score
        item['size_f']   = size_bytes
        item['name_low'] = name_norm
        try:
            item['ctime_f'] = float(item.get('ctime', 0))
        except Exception:
            item['ctime_f'] = 0
        files_list.append(item)

    # Uložíme do search cache (filtrovaný seznam)
    if offset == 0 and cached_files is None:
        cache_dict = {it['ident']: it for it in files_list}
        search_cache_save(cache_key, cache_dict)

    # Řazení
    if sort_by == 'size':
        files_list.sort(key=lambda x: x['size_f'], reverse=True)
    elif sort_by == 'date':
        files_list.sort(key=lambda x: x['ctime_f'], reverse=True)
    elif sort_by == 'name':
        files_list.sort(key=lambda x: x['name_low'])
    else:
        files_list.sort(key=lambda x: x['prio'], reverse=True)

    # Počet výsledků v titulku
    xbmcplugin.setPluginCategory(_handle, "%s (%d výsledků)" % (what.split('|')[-1], len(files_list)))


    for item in files_list:
        ident   = item.get('ident', '')
        name    = item.get('name', '')
        is_fav  = ident in favs_idents
        watched = ident in watched_db

        # Thumbnail – pokud byl předán thumb_map (z TMDB) použijeme ho
        thumb = (thumb_map or {}).get(ident) or _icon

        fav_label = "★ Odebrat z oblíbených" if is_fav else "☆ Přidat do oblíbených"
        extra = [(fav_label, 'RunPlugin(%s)' % get_url(action='fav_toggle', ident=ident, name=name))]

        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='play', ident=ident, name=name),
            tolistitem_enhanced(item, extra_cmds=extra, thumb=thumb, watched=watched), False)

        # Tlačítko oblíbených
        fav_star = "★" if is_fav else "☆"
        fav_text = "Odebrat z oblíbených" if is_fav else "Přidat do oblíbených"
        fav_li   = xbmcgui.ListItem(label="   [COLOR gold]%s[/COLOR] [COLOR gray]%s[/COLOR]" % (fav_star, fav_text))
        fav_li.setArt({'icon': _icon})
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='fav_toggle', ident=ident, name=name),
            fav_li, False)

    try:
        total = int(last_xml.find('total').text or 0) if last_xml is not None else len(files_list)
    except (AttributeError, ValueError, TypeError):
        total = len(files_list) + offset

    if offset + int(limit) < total:
        xbmcplugin.addDirectoryItem(
            _handle,
            get_url(action=action, what=what, offset=offset + int(limit),
                    quality_filter=quality_filter, sort_by=sort_by),
            xbmcgui.ListItem(label="[COLOR yellow]>> Další výsledky[/COLOR]"), True)

    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# TMDB FUNKCE
# ---------------------------------------------------------------------------
def tmdb_list(params):
    key = get_tmdb_key()
    if not key:
        xbmcplugin.endOfDirectory(_handle); return
    ep   = params.get('endpoint')
    page = params.get('page', '1')
    url  = "{0}{1}?api_key={2}&language=cs-CZ&page={3}".format(TMDB_URL, ep, key, page)
    if params.get('genre_id'): url += "&with_genres=" + params['genre_id']
    if params.get('query'):    url += "&query=" + quote_plus(params['query'])

    data = tmdb_get(url)
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return

    for i in data.get('results', []):
        mtype = i.get('media_type', ('tv' if '/tv' in ep else 'movie'))
        if mtype not in ['movie', 'tv']:
            continue
        t_cs   = i.get('name') or i.get('title') or ''
        t_orig = i.get('original_name') or i.get('original_title') or t_cs
        date   = i.get('first_air_date') or i.get('release_date') or ""
        year   = date.split('-')[0] if '-' in date else ""
        rating = i.get('vote_average', 0)

        if t_cs.lower() != t_orig.lower():
            search_query = ("%s|%s %s" % (t_orig, t_cs, year)).strip()
        else:
            search_query = ("%s %s" % (t_cs, year)).strip()

        label = t_cs
        if year:   label += " [COLOR gray](%s)[/COLOR]" % year
        if rating: label += " [COLOR gold][%.1f][/COLOR]" % rating

        u  = get_url(action='tmdb_seasons', tv_id=i['id'], tv_name=t_orig) if mtype == 'tv' \
             else get_url(action='ws_search', what=search_query)
        li = xbmcgui.ListItem(label=label)
        poster = i.get('poster_path')
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon, 'icon': _icon,
                   'thumb': TMDB_IMG + poster if poster else _icon})
        li.setInfo('video', {
            'title': t_cs, 'plot': i.get('overview', ''),
            'year': int(year) if year.isdigit() else 0,
            'rating': rating,
        })
        xbmcplugin.addDirectoryItem(_handle, u, li, True)  # vždy složka – filmy jdou na ws_search, seriály na tmdb_seasons

    total = data.get('total_pages', 1)
    cur   = int(page)
    if cur < total:
        nxt = {k: v for k, v in params.items() if k != 'action'}
        nxt['page'] = str(cur + 1)
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='tmdb_list', **nxt),
            xbmcgui.ListItem(label="[COLOR yellow]>> Další stránka (%d/%d)[/COLOR]" % (cur + 1, total)), True)

    xbmcplugin.endOfDirectory(_handle)

def tmdb_seasons(params):
    key     = get_tmdb_key()
    tv_id   = params.get('tv_id')
    tv_name = params.get('tv_name', '')
    if not key or not tv_id:
        xbmcplugin.endOfDirectory(_handle); return
    url  = "{0}/tv/{1}?api_key={2}&language=cs-CZ".format(TMDB_URL, tv_id, key)
    data = tmdb_get(url)
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return
    poster = data.get('poster_path')
    for s in data.get('seasons', []):
        sn  = s.get('season_number', 0)
        if sn == 0:
            continue
        lbl = "Série %d" % sn
        ep_count = s.get('episode_count', 0)
        if ep_count:
            lbl += " [COLOR gray](%d dílů)[/COLOR]" % ep_count
        li = xbmcgui.ListItem(label=lbl)
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon,
                   'thumb': TMDB_IMG + poster if poster else _icon})
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
    url  = "{0}/tv/{1}/season/{2}?api_key={3}&language=cs-CZ".format(TMDB_URL, tv_id, season, key)
    data = tmdb_get(url)
    if data is None:
        xbmcplugin.endOfDirectory(_handle); return
    poster = data.get('poster_path')
    for e in data.get('episodes', []):
        en  = e.get('episode_number', 0)
        ep_code = "S%02dE%02d" % (int(season), en)
        lbl = "%s – %s" % (ep_code, e.get('name', ''))
        li  = xbmcgui.ListItem(label=lbl)
        li.setInfo('video', {'plot': e.get('overview', '')})
        still = e.get('still_path')
        li.setArt({'thumb': TMDB_IMG + still if still else (TMDB_IMG + poster if poster else _icon)})
        search_q = "%s %s" % (tv_name, ep_code)
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='ws_search', what=search_q), li, True)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# TITULKY (OpenSubtitles)
# ---------------------------------------------------------------------------
def fetch_subtitles(params):
    key  = _addon.getSetting('opensub_key')
    name = params.get('name', '')
    ident = params.get('ident', '')
    if not key:
        popinfo("OpenSubtitles API klíč není nastaven"); return
    try:
        headers = {
            'Api-Key': key, 'User-Agent': OPENSUB_UA,
            'Content-Type': 'application/json'
        }
        q_name = re.sub(r'[\.\-_]', ' ', name)
        q_name = re.sub(r'\s+', ' ', q_name).strip()
        r = _session.get(
            OPENSUB_URL + "/subtitles",
            headers=headers,
            params={'query': q_name, 'languages': 'cs,sk', 'per_page': 10},
            timeout=10
        )
        r.raise_for_status()
        subs = r.json().get('data', [])
    except Exception as e:
        xbmc.log("OpenSub search error: %s" % e, xbmc.LOGERROR)
        popinfo("Chyba při hledání titulků"); return

    if not subs:
        popinfo("Žádné titulky nenalezeny"); return

    choices = []
    for s in subs:
        attr  = s.get('attributes', {})
        lang  = attr.get('language', '?')
        rel   = attr.get('release', '?')[:40]
        cnt   = attr.get('download_count', 0)
        choices.append("%s | %s | ↓%d" % (lang, rel, cnt))

    idx = xbmcgui.Dialog().select("Vyberte titulky", choices)
    if idx < 0:
        return

    try:
        attr    = subs[idx].get('attributes', {})
        file_id = attr.get('files', [{}])[0].get('file_id')
        if not file_id:
            popinfo("Chyba: file_id nenalezeno"); return
        r2 = _session.post(
            OPENSUB_URL + "/download",
            headers={'Api-Key': key, 'User-Agent': OPENSUB_UA, 'Content-Type': 'application/json'},
            json={'file_id': file_id}, timeout=10
        )
        r2.raise_for_status()
        dl_url = r2.json().get('link')
        if not dl_url:
            popinfo("Chyba stahování titulků"); return
    except Exception as e:
        xbmc.log("OpenSub download error: %s" % e, xbmc.LOGERROR)
        popinfo("Chyba stahování titulků"); return

    try:
        r3 = _session.get(dl_url, timeout=15)
        r3.raise_for_status()
        sub_path = profile_path(re.sub(r'[<>:"/\\|?*]', '_', name) + ".srt")
        with open(sub_path, 'wb') as f:
            f.write(r3.content)
        popinfo("Titulky staženy ✓")
    except Exception as e:
        xbmc.log("OpenSub file dl error: %s" % e, xbmc.LOGERROR)
        popinfo("Chyba při ukládání titulků")

# ---------------------------------------------------------------------------
# DETEKCE A PŘEHRÁNÍ DALŠÍ EPIZODY
# ---------------------------------------------------------------------------
def _play_next_episode(series, season, episode):
    """Vyhledá na Webshare další epizodu a rovnou ji přehraje."""
    token = _addon.getSetting('token')
    if not token:
        token = login()
    if not token:
        popinfo("Nelze přehrát – nejsi přihlášen")
        return

    ep_code  = "S%02dE%02d" % (season, episode)
    search_q = "%s %s" % (series, ep_code)
    xbmc.log("AutoNext: hledam '%s'" % search_q, xbmc.LOGINFO)

    # Hledáme na Webshare
    res = api('search', {
        'what': search_q, 'category': 'video',
        'sort': 'largest', 'limit': 20, 'offset': 0, 'wst': token
    })
    xml = parse_xml(res)
    if xml is None or not is_ok(xml):
        popinfo("Další díl %s nenalezen na Webshare" % ep_code)
        return

    min_size = get_min_size_bytes()
    quality_filter = _addon.getSetting('default_quality') or 'all'
    best = None

    for f in xml.iter('file'):
        item  = todict(f)
        name  = item.get('name', '')
        n_up  = name.upper()
        size  = float(item.get('size', 0) or 0)

        if size < min_size:
            continue

        # Filtr kvality z nastavení
        is_cz   = any(x in n_up for x in ['CZ', 'CZECH', 'DABING', 'SK'])
        is_4k   = any(x in n_up for x in ['4K', '2160P', 'UHD'])
        is_1080 = any(x in n_up for x in ['1080P', 'FULLHD', 'FHD'])
        is_720  = '720P' in n_up

        if quality_filter == 'cz'    and not is_cz:   continue
        if quality_filter == '4k'    and not is_4k:   continue
        if quality_filter == '1080p' and not is_1080: continue
        if quality_filter == '720p'  and not is_720:  continue

        # Epizóda musí odpovídat hledanému kódu
        ep_patterns = [
            ep_code.upper(),
            "%dx%02d" % (season, episode),
        ]
        if not any(p in n_up for p in ep_patterns):
            continue

        if best is None or size > float(best.get('size', 0) or 0):
            best = item

    if not best:
        popinfo("Další díl %s nenalezen (zkus změnit min. velikost v nastavení)" % ep_code)
        xbmc.executebuiltin('ActivateWindow(Videos,plugin://%s?%s,return)' % (
            _addon_id, 'action=ws_search&what=' + _quote(search_q)))
        return

    # Získáme přímý odkaz – stejná logika jako v play() včetně VIP
    xbmc.log("AutoNext: ziskavam odkaz pro '%s'" % best.get('name', ''), xbmc.LOGINFO)
    b_ident = best.get('ident', '')
    bname   = best.get('name', ep_code)
    tried_vip  = _addon.getSetting('tried_vip') == 'true'
    dl_types   = [None] if tried_vip else ['video_stream', None]
    link       = None
    used_vip   = False
    for dl_type in dl_types:
        data = {'ident': b_ident, 'wst': token}
        if dl_type:
            data['download_type'] = dl_type
        res2 = api('file_link', data)
        if res2 is None:
            continue
        xml2 = parse_xml(res2)
        if xml2 is None or not is_ok(xml2):
            msg_el = xml2.find('message') if xml2 is not None else None
            err = msg_el.text if msg_el is not None and msg_el.text else ''
            if any(x in err.lower() for x in ['login', 'token', 'unauthorized']):
                token = login()
                if token:
                    data['wst'] = token
                    res2 = api('file_link', data)
                    xml2 = parse_xml(res2)
                    if xml2 is None or not is_ok(xml2):
                        continue
                else:
                    continue
            else:
                continue
        link_el = xml2.find('link')
        if link_el is not None and link_el.text and link_el.text.strip():
            link     = link_el.text.strip()
            used_vip = (dl_type == 'video_stream')
            break

    if not link:
        popinfo("Nepodařilo se získat odkaz pro další díl")
        return

    _addon.setSetting('tried_vip', 'false' if used_vip else 'true')
    xbmc.log("AutoNext: prehravám '%s'" % bname, xbmc.LOGINFO)
    li = xbmcgui.ListItem(label=bname, path=link)
    li.setInfo('video', {'title': bname})
    li.setProperty('IsPlayable', 'true')
    _save_resume_name(b_ident, bname)
    xbmc.Player().play(link, li)

    # Spustíme nové monitorovací vlákno pro tento díl (aby se zeptalo na další)
    def _autonext_monitor(ident, name):
        monitor = xbmc.Monitor()
        player  = xbmc.Player()
        # Počkáme než začne přehrávání nového dílu
        for _ in range(30):
            if monitor.abortRequested(): return
            if player.isPlayingVideo(): break
            xbmc.sleep(500)
        else:
            return
        # Počkáme chvíli aby se stabilizovalo (nový soubor se načítá)
        xbmc.sleep(3000)
        dialog_shown = False
        while not monitor.abortRequested():
            if not player.isPlayingVideo():
                break
            try:
                pos = player.getTime()
                tot = player.getTotalTime()
                if tot > 60:
                    save_resume(ident, name, pos, tot)
                    remaining = tot - pos
                    if not dialog_shown and 0 < remaining <= 15:
                        if _addon.getSetting('autonext') == 'true':
                            next_ep = _get_next_episode(name)
                            if next_ep:
                                dialog_shown = True
                                ns, nseason, nepisode = next_ep
                                prev_code = "S%02dE%02d" % (nseason, nepisode - 1)
                                next_code = "S%02dE%02d" % (nseason, nepisode)
                                msg = "Skončil %s – přehrát další díl %s?" % (prev_code, next_code)
                                if xbmcgui.Dialog().yesno("Další díl", msg,
                                                           yeslabel="▶ Přehrát", nolabel="Ne"):
                                    _play_next_episode(ns, nseason, nepisode)
            except Exception:
                pass
            xbmc.sleep(2000)

    threading.Thread(target=_autonext_monitor, args=(b_ident, bname), daemon=True).start()


def _get_next_episode(name):
    """
    Z názvu souboru detekuje seriál + číslo epizody a vrátí (series, season, next_ep).
    Podporuje formáty: S01E05, 1x05, s01e05 atd.
    Vrátí None pokud nejde o seriál nebo je to poslední díl.
    """
    if not name:
        return None
    # Regex pro detekci epizody – S01E05 nebo 1x05
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', name)
    if not m:
        m = re.search(r'(\d{1,2})[xX](\d{1,2})', name)
    if not m:
        return None

    season  = int(m.group(1))
    episode = int(m.group(2))

    # Odstraníme kód epizody z názvu abychom dostali název seriálu
    series = name[:m.start()].strip()
    # Odstraníme příponu a zbytečné znaky
    series = re.sub(r'[\.\-_]+$', '', series).strip()
    series = re.sub(r'\s+', ' ', series).strip()

    if not series:
        return None

    return (series, season, episode + 1)

# ---------------------------------------------------------------------------
# PŘEHRÁVÁNÍ
# ---------------------------------------------------------------------------
def _fmt_time(seconds):
    try:
        s = int(seconds)
        return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)
    except Exception:
        return "?"

def play(params):
    token = _addon.getSetting('token')
    if not token:
        token = login()
    if not token:
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem()); return

    ident = params.get('ident', '')
    name  = (params.get('name') or '').strip()

    tried_vip = _addon.getSetting('tried_vip') == 'true'
    dl_types  = [None] if tried_vip else ['video_stream', None]

    link_text  = None
    last_error = "neznámá chyba"
    used_vip   = False
    for dl_type in dl_types:
        data = {'ident': ident, 'wst': token}
        if dl_type:
            data['download_type'] = dl_type
        res = api('file_link', data)
        if res is None:
            last_error = "API nedostupné (síťová chyba)"
            xbmc.log("file_link: zadna odpoved od API, dl_type=%s" % dl_type, xbmc.LOGERROR)
            continue
        # Logujeme celou odpověď pro snadný debug
        raw = res.content.decode('utf-8', errors='replace')
        xbmc.log("file_link [%s] odpoved: %s" % (dl_type, raw[:800]), xbmc.LOGINFO)
        xml = parse_xml(res)
        if xml is None:
            last_error = "Chyba parsování XML"
            continue
        if not is_ok(xml):
            msg_el = xml.find('message')
            if msg_el is None:
                msg_el = xml.find('status')
            last_error = (msg_el.text or "API vrátilo chybu") if msg_el is not None else "API vrátilo chybu"
            xbmc.log("file_link [%s] NOT OK: %s" % (dl_type, last_error), xbmc.LOGWARNING)
            if any(x in last_error.lower() for x in ['login', 'token', 'unauthorized', 'logged']):
                xbmc.log("Token expiroval, prihlasuju znovu...", xbmc.LOGINFO)
                token = login()
                if token:
                    data['wst'] = token
                    res = api('file_link', data)
                    if res is None:
                        continue
                    xml = parse_xml(res)
                    if xml is None or not is_ok(xml):
                        continue
                else:
                    last_error = "Přihlášení selhalo"
                    continue
            else:
                continue
        link_el = xml.find('link')
        if link_el is not None and link_el.text and link_el.text.strip():
            link_text = link_el.text.strip()
            used_vip  = (dl_type == 'video_stream')
            xbmc.log("file_link OK, odkaz ziskan (VIP=%s)" % used_vip, xbmc.LOGINFO)
            break
        last_error = "API vrátilo prázdný odkaz (soubor smazán nebo nedostatek kreditů)"

    if not link_text:
        xbmc.log("Prehravani selhalo: " + last_error, xbmc.LOGERROR)
        popinfo("Nelze přehrát: " + last_error, 5000)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem()); return

    _addon.setSetting('tried_vip', 'false' if used_vip else 'true')

    if not name:
        name = ident

    _save_resume_name(ident, name)

    li = xbmcgui.ListItem(label=name, path=link_text)
    li.setInfo('video', {'title': name})

    resume = get_resume(ident)
    if resume and resume.get('pct', 0) > 2:
        if xbmcgui.Dialog().yesno(
            "Pokračovat?",
            "Pokračovat od %d%% (%s)?" % (resume['pct'], _fmt_time(resume['position'])),
            yeslabel="Pokračovat", nolabel="Od začátku"):
            li.setProperty('ResumeTime', str(resume['position']))
            li.setProperty('TotalTime',  str(resume['total']))

    sub_path = profile_path(re.sub(r'[<>:"/\\|?*]', '_', name) + ".srt")
    if os.path.exists(sub_path):
        li.setSubtitles([sub_path])

    xbmcplugin.setResolvedUrl(_handle, True, li)

    # Monitorovací vlákno
    _monitor_name = name
    def _monitor():
        monitor = xbmc.Monitor()
        player  = xbmc.Player()
        for _ in range(30):
            if monitor.abortRequested(): return
            if player.isPlayingVideo(): break
            xbmc.sleep(500)
        else:
            return
        dialog_shown = False
        while not monitor.abortRequested():
            if not player.isPlayingVideo():
                break
            try:
                pos = player.getTime()
                tot = player.getTotalTime()
                if tot > 60:
                    save_resume(ident, _monitor_name, pos, tot)
                    # 10 sekund před koncem – zobraz dialog
                    remaining = tot - pos
                    if not dialog_shown and 0 < remaining <= 15:
                        if _addon.getSetting('autonext') == 'true':
                            next_ep = _get_next_episode(name)
                            if next_ep:
                                dialog_shown = True
                                series, season, episode = next_ep
                                prev_code = "S%02dE%02d" % (season, episode - 1)
                                next_code = "S%02dE%02d" % (season, episode)
                                msg = "Skončil %s – přehrát další díl %s?" % (prev_code, next_code)
                                if xbmcgui.Dialog().yesno("Další díl", msg,
                                                           yeslabel="▶ Přehrát", nolabel="Ne"):
                                    _play_next_episode(series, season, episode)
            except Exception:
                pass
            xbmc.sleep(2000)

    threading.Thread(target=_monitor, daemon=True).start()

# ---------------------------------------------------------------------------
# STAHOVÁNÍ
# ---------------------------------------------------------------------------
def download(params):
    folder = _addon.getSetting('dfolder')
    if not folder:
        _addon.openSettings(); return

    with _dl_lock:
        if len(_dl_threads) >= MAX_DL_THREADS:
            popinfo("Max %d stahování najednou" % MAX_DL_THREADS); return

    token = _addon.getSetting('token') or login()
    if not token: return

    res    = api('file_link', {'ident': params['ident'], 'wst': token})
    xml    = parse_xml(res)
    link_el = xml.find('link') if xml else None
    if not link_el or not link_el.text:
        popinfo("Odkaz ke stažení je prázdný"); return

    url  = link_el.text
    name = params.get('name', params['ident'])
    dest = os.path.join(folder, re.sub(r'[<>:"/\\|?*]', '_', name))

    q = loadqueue()
    q.append({'name': name, 'dest': dest, 'status': 'pending'})
    savequeue(q)
    popinfo("Stahování zahájeno: " + name)

    def _do_download():
        headers = {}
        mode    = 'wb'
        if os.path.exists(dest):
            done = os.path.getsize(dest)
            headers['Range'] = 'bytes=%d-' % done
            mode = 'ab'
        try:
            r = _session.get(url, headers=headers, stream=True, timeout=30)
            r.raise_for_status()
            with open(dest, mode) as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            q2 = loadqueue()
            for item in q2:
                if item['dest'] == dest:
                    item['status'] = 'done'
            savequeue(q2)
            popinfo("Stahování dokončeno: " + name)
        except Exception as e:
            xbmc.log("Download error: %s" % e, xbmc.LOGERROR)
            q2 = loadqueue()
            for item in q2:
                if item['dest'] == dest:
                    item['status'] = 'error'
            savequeue(q2)
            popinfo("Chyba stahování: " + name)

    t = threading.Thread(target=_do_download, daemon=True)
    t.start()
    with _dl_lock:
        _dl_threads[dest] = t

# ---------------------------------------------------------------------------
# FRONTA STAHOVÁNÍ
# ---------------------------------------------------------------------------
def loadqueue():
    return load_json('queue.json', [])

def savequeue(q):
    save_json('queue.json', q)

def queue(params):
    items = loadqueue()
    if not items:
        xbmcplugin.addDirectoryItem(
            _handle, '', xbmcgui.ListItem(label="[COLOR gray]Fronta je prázdná[/COLOR]"), False)
    for i in items:
        icon = {'done': '[COLOR green]✓[/COLOR]', 'error': '[COLOR red]✗[/COLOR]'}.get(
               i.get('status', 'pending'), '[COLOR yellow]…[/COLOR]')
        li = xbmcgui.ListItem(label="%s %s" % (icon, i['name']))
        li.addContextMenuItems([
            ("Smazat ze fronty", 'RunPlugin(%s)' % get_url(action='del_queue', dest=i.get('dest', '')))
        ])
        xbmcplugin.addDirectoryItem(_handle, '', li, False)
    xbmcplugin.addDirectoryItem(
        _handle, get_url(action='clear_queue'),
        xbmcgui.ListItem(label="[COLOR red]Vyčistit dokončené[/COLOR]"), False)
    xbmcplugin.endOfDirectory(_handle)

def del_queue_item(params):
    savequeue([x for x in loadqueue() if x.get('dest') != params.get('dest', '')])
    xbmc.executebuiltin('Container.Refresh')

def clear_queue(params):
    savequeue([x for x in loadqueue() if x.get('status') not in ('done', 'error')])
    xbmc.executebuiltin('Container.Refresh')

# ---------------------------------------------------------------------------
# WEBSHARE HISTORY + INFO
# ---------------------------------------------------------------------------
def history(params):
    token = revalidate()
    if not token:
        xbmcplugin.endOfDirectory(_handle); return
    xml = parse_xml(api('history', {'wst': token}))
    if xml is not None and is_ok(xml):
        for f in xml.iter('file'):
            ident_el = f.find('ident')
            if ident_el is None:
                continue
            d = todict(f)
            xbmcplugin.addDirectoryItem(
                _handle, get_url(action='play', ident=ident_el.text, name=d.get('name', '')),
                tolistitem_enhanced(d), False)
    xbmcplugin.endOfDirectory(_handle)

def info(params):
    token = revalidate()
    if not token: return
    xml = parse_xml(api('file_info', {'ident': params['ident'], 'wst': token}))
    if xml is not None and is_ok(xml):
        f_el = xml.find('file')
        if f_el is not None:
            f = todict(f_el)
            xbmcgui.Dialog().ok(
                f.get('name', ''),
                "Velikost: %s\nKategorie: %s" % (sizelize(f.get('size', 0)), f.get('category', '')))

# ---------------------------------------------------------------------------
# NEDÁVNO PŘIDANÉ (Webshare new)
# ---------------------------------------------------------------------------
def recently_added(params):
    token = revalidate()
    if not token:
        xbmcplugin.endOfDirectory(_handle); return

    # Webshare nevrátí výsledky pro prázdný dotaz – zkoušíme běžná slova
    queries   = ['.', 'cz', 'mkv', 'avi', 'mp4', '1080', '720']
    all_files = {}
    for q in queries:
        res = api('search', {
            'what': q, 'category': 'video', 'sort': 'recent',
            'limit': 50, 'offset': 0, 'wst': token
        })
        xml = parse_xml(res)
        if xml is None or not is_ok(xml):
            continue
        for file in xml.iter('file'):
            item  = todict(file)
            ident = item.get('ident', '')
            if ident and ident not in all_files:
                all_files[ident] = item
        if len(all_files) >= 50:
            break

    if not all_files:
        popinfo("Nepodařilo se načíst nedávno přidané")
        xbmcplugin.endOfDirectory(_handle); return

    # Seřadíme podle ctime (nejnovější první), bez size filtru
    items_sorted = sorted(
        all_files.values(),
        key=lambda x: float(x.get('ctime', 0) or 0),
        reverse=True
    )

    watched_db  = load_watched()
    favs_idents = {f['ident'] for f in load_favorites()}

    for item in items_sorted:
        ident   = item.get('ident', '')
        name    = item.get('name', '')
        is_fav  = ident in favs_idents
        watched = ident in watched_db
        fav_label = "★ Odebrat z oblíbených" if is_fav else "☆ Přidat do oblíbených"
        extra = [(fav_label, 'RunPlugin(%s)' % get_url(action='fav_toggle', ident=ident, name=name))]
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='play', ident=ident, name=name),
            tolistitem_enhanced(item, extra_cmds=extra, watched=watched), False)
        fav_star = "★" if is_fav else "☆"
        fav_text = "Odebrat z oblíbených" if is_fav else "Přidat do oblíbených"
        fav_li   = xbmcgui.ListItem(label="   [COLOR gold]%s[/COLOR] [COLOR gray]%s[/COLOR]" % (fav_star, fav_text))
        fav_li.setArt({'icon': _icon})
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='fav_toggle', ident=ident, name=name), fav_li, False)
    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# OZNAČIT JAKO SHLÉDNUTÉ
# ---------------------------------------------------------------------------
def action_mark_watched(params):
    ident = params.get('ident', '')
    if ident:
        mark_watched(ident)
        popinfo("Označeno jako shlédnuté ✓")
        xbmc.executebuiltin('Container.Refresh')

# ---------------------------------------------------------------------------
# NOVINKY (TMDB now_playing + on_the_air)
# ---------------------------------------------------------------------------
def novinky(params):
    key = get_tmdb_key()
    if not key:
        xbmcplugin.endOfDirectory(_handle); return

    dabing  = params.get('dabing') == '1'
    page    = params.get('page', '1')
    mtype   = params.get('mtype', 'movie')  # movie nebo tv

    # Zobrazíme výběr: filmy nebo seriály
    if 'mtype' not in params:
        for mt, lbl in [('movie', '🎬 Nové filmy'), ('tv', '📺 Nové seriály')]:
            li = xbmcgui.ListItem(label=lbl)
            li.setArt({'icon': _icon, 'thumb': _icon})
            xbmcplugin.addDirectoryItem(
                _handle,
                get_url(action='novinky', mtype=mt, dabing='1' if dabing else '0'),
                li, True)
        xbmcplugin.endOfDirectory(_handle)
        return

    endpoint = '/movie/now_playing' if mtype == 'movie' else '/tv/on_the_air'
    url = "{0}{1}?api_key={2}&language=cs-CZ&page={3}&region=CZ".format(
        TMDB_URL, endpoint, key, page)

    data = tmdb_get(url)
    if data is None:
        popinfo("Nepodařilo se načíst novinky z TMDB")
        xbmcplugin.endOfDirectory(_handle); return

    suffix = " dabing" if dabing else ""

    for i in data.get('results', []):
        t_cs   = i.get('name') or i.get('title') or ''
        t_orig = i.get('original_name') or i.get('original_title') or t_cs
        date   = i.get('first_air_date') or i.get('release_date') or ""
        year   = date.split('-')[0] if '-' in date else ""
        rating = i.get('vote_average', 0)

        # Search query – originální + český název + rok + případně "dabing"
        if t_cs.lower() != t_orig.lower():
            search_query = ("%s|%s %s%s" % (t_orig, t_cs, year, suffix)).strip()
        else:
            search_query = ("%s %s%s" % (t_cs, year, suffix)).strip()

        label = t_cs
        if year:   label += " [COLOR gray](%s)[/COLOR]" % year
        if rating: label += " [COLOR gold][%.1f][/COLOR]" % rating
        if dabing: label += " [COLOR yellow][CZ][/COLOR]"

        li = xbmcgui.ListItem(label=label)
        poster = i.get('poster_path')
        li.setArt({'poster': TMDB_IMG + poster if poster else _icon,
                   'thumb':  TMDB_IMG + poster if poster else _icon,
                   'icon':   _icon})
        li.setInfo('video', {
            'title': t_cs, 'plot': i.get('overview', ''),
            'year':  int(year) if year.isdigit() else 0,
            'rating': rating,
        })
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='ws_search', what=search_query), li, True)

    # Stránkování
    total = data.get('total_pages', 1)
    cur   = int(page)
    if cur < total:
        xbmcplugin.addDirectoryItem(
            _handle,
            get_url(action='novinky', mtype=mtype, dabing='1' if dabing else '0', page=str(cur + 1)),
            xbmcgui.ListItem(label="[COLOR yellow]>> Další stránka (%d/%d)[/COLOR]" % (cur + 1, total)), True)

    xbmcplugin.endOfDirectory(_handle)

# ---------------------------------------------------------------------------
# VIP INFO
# ---------------------------------------------------------------------------
def vip_info():
    token = _addon.getSetting('token')
    if not token:
        popinfo("Nejsi přihlášen"); return
    xml = parse_xml(api('user_data', {'wst': token}))
    if xml is None or not is_ok(xml):
        popinfo("Nelze načíst info o účtu"); return
    username = (xml.find('username') or xml.find('login'))
    vip_el   = xml.find('vip')
    until_el = xml.find('vip_until')
    credits_el = xml.find('points')
    lines = []
    if username is not None and username.text:
        lines.append("Účet: %s" % username.text)
    if vip_el is not None:
        lines.append("VIP: %s" % ("Aktivní ✓" if vip_el.text == '1' else "Neaktivní"))
    if until_el is not None and until_el.text:
        lines.append("VIP do: %s" % until_el.text)
    if credits_el is not None and credits_el.text:
        lines.append("Kredity: %s" % credits_el.text)
    xbmcgui.Dialog().ok("Webshare účet", "\n".join(lines) if lines else "Žádné informace")

# ---------------------------------------------------------------------------
# HLAVNÍ MENU
# ---------------------------------------------------------------------------
def menu():
    # --- KONTROLA SOUHLASU (DISCLAIMER) ---
    if _addon.getSetting('disclaimer_accepted') != 'true':
        text = ("Tento doplněk neposkytuje žádný obsah. Autor nenese odpovědnost "
                "za to, jak uživatelé využívají své účty Webshare a TMDB. "
                "Vše děláte na vlastní riziko.\n\nSouhlasíte s těmito podmínkami?")
        
        # Zobrazí dialog ANO/NE
        if xbmcgui.Dialog().yesno("Právní prohlášení", text):
            _addon.setSetting('disclaimer_accepted', 'true')
        else:
            # Pokud uživatel klikne na NE, addon se neotevře
            return
    # --------------------------------------

    # Přihlášení na pozadí při každém otevření menu
    token = _addon.getSetting('token')
    if not token:
        login()
    else:
        threading.Thread(target=revalidate, daemon=True).start()

    vip_label = get_vip_label()

    items = [
        (get_url(action='tmdb_sub', mode='movie'),  "🎬  Filmy (TMDB)",              True,  'movies'),
        (get_url(action='tmdb_sub', mode='tv'),     "📺  Seriály (TMDB)",            True,  'series'),
        (get_url(action='tmdb_search'),             "🔍  Hledat (TMDB)",             True,  'search_tmdb'),
        (get_url(action='search'),                  "🔍  Hledat (Webshare)",         True,  'search_ws'),
        (get_url(action='search_history'),          "🕐  Historie hledání",          True,  'history'),
        (get_url(action='tmdb_list', endpoint='/trending/all/day'),
                                                    "[COLOR orange]▶  Právě se sleduje[/COLOR]", True, 'trending'),
        (get_url(action='resume_list'),             "[COLOR lightblue]⏩  Pokračovat ve sledování[/COLOR]", True, 'resume'),
        (get_url(action='novinky'),                 "[COLOR lime]🆕  Novinky[/COLOR]",               True, 'new'),
        (get_url(action='novinky', dabing='1'),     "[COLOR lime]🆕  Novinky dabované[/COLOR]",      True, 'new_dub'),
        (get_url(action='favorites'),               "[COLOR gold]★  Oblíbené[/COLOR]",               True, 'favorites'),
        (get_url(action='queue'),                   "📥  Fronta stahování",          True,  'queue'),
        (get_url(action='cache_clear'),             "[COLOR gray]🗑  Vymazat cache[/COLOR]",        False, 'cache'),
        (get_url(action='settings'),                "⚙  Nastavení",                  False, 'settings'),
    ]

    if vip_label:
        items.insert(10, (get_url(action='vip_info'), vip_label, False, 'vip'))

    for u, label, isdir, icon_name in items:
        li = xbmcgui.ListItem(label=label)
        ic = _menu_icon(icon_name)
        li.setArt({'icon': ic, 'thumb': ic})
        xbmcplugin.addDirectoryItem(_handle, u, li, isdir)

    xbmcplugin.endOfDirectory(_handle)
# ---------------------------------------------------------------------------
# ROUTER
# ---------------------------------------------------------------------------
def router(paramstring):
    p = dict(parse_qsl(paramstring))
    a = p.get('action')

    if a == 'tmdb_sub':
        m = p.get('mode')
        for ep, lbl in [('popular', 'Populární'), ('top_rated', 'Nejlépe hodnocené')]:
            xbmcplugin.addDirectoryItem(
                _handle, get_url(action='tmdb_list', endpoint='/%s/%s' % (m, ep)),
                xbmcgui.ListItem(label=lbl), True)
        xbmcplugin.addDirectoryItem(
            _handle, get_url(action='tmdb_genres', mode=m),
            xbmcgui.ListItem(label="Žánry"), True)
        xbmcplugin.endOfDirectory(_handle)

    elif a == 'tmdb_genres':
        gs = MOVIE_GENRES if p.get('mode') == 'movie' else TV_GENRES
        for g in gs:
            xbmcplugin.addDirectoryItem(
                _handle,
                get_url(action='tmdb_list', endpoint='/discover/' + p.get('mode'), genre_id=g['id']),
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

    elif a == 'ws_search':
        dosearch(
            revalidate(), p.get('what'), 'video', 'relevance', 50,
            int(p.get('offset', 0)), 'ws_search',
            quality_filter=p.get('quality_filter', 'all'),
            sort_by=p.get('sort_by', 'score')
        )
    elif a == 'search':
        kb = xbmc.Keyboard('', 'Zadejte název')
        kb.doModal()
        if kb.isConfirmed() and kb.getText():
            dosearch(revalidate(), kb.getText(), 'video', 'relevance', 50, 0, 'search')
        else:
            xbmcplugin.endOfDirectory(_handle)

    elif a == 'search_history':   show_search_history()
    elif a == 'del_history':      del_from_history(p)
    elif a == 'clear_history':    clear_history(p)
    elif a == 'favorites':        show_favorites()
    elif a == 'fav_toggle':       toggle_favorite(p)
    elif a == 'resume_list':      show_resume_list()
    elif a == 'del_resume':       del_resume(p)
    elif a == 'recently_added':   recently_added(p)
    elif a == 'novinky':          novinky(p)
    elif a == 'mark_watched':     action_mark_watched(p)
    elif a == 'play':             play(p)
    elif a == 'info':             info(p)
    elif a == 'download':         download(p)
    elif a == 'subtitles':        fetch_subtitles(p)
    elif a == 'queue':            queue(p)
    elif a == 'del_queue':        del_queue_item(p)
    elif a == 'clear_queue':      clear_queue(p)
    elif a == 'history':          history(p)
    elif a == 'vip_info':         vip_info()
    elif a == 'cache_clear':      cache_clear()
    elif a == 'settings':         _addon.openSettings()
    else:                         menu()

if __name__ == '__main__':
    router(sys.argv[2][1:])
