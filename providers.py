import time
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
import requests

from config import COVERS_DIR, LASTFM_API_KEY
from database import cache_get, cache_set, upsert_track, get_all_tracks


class TokenBucket:
    def __init__(self, rate: float, capacity: float):#initializare limitator de requesturi
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: float = 1.0):#asteapta daca s-au facut prea multe cereri pe secunda
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            if self.tokens < tokens:
                sleep_time = (tokens - self.tokens) / self.rate
                time.sleep(sleep_time)
                self.tokens = 0.0
                self.last_update = time.monotonic()
            else:
                self.tokens -= tokens


deezer_bucket = TokenBucket(rate=8.0, capacity=10.0)


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None, ttl: int = 86400 * 7) -> Optional[Dict[str, Any]]:#cerere http cu cache si retry
    cached = cache_get(url)
    if cached is not None:
        return cached

    deezer_bucket.consume()
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                cache_set(url, data, ttl)
                return data
            elif resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1.5 * (attempt + 1)))
                time.sleep(retry_after)
        except requests.RequestException:
            time.sleep(0.5 * (attempt + 1))
    return None


def download_cover_file(track_id: str, cover_url: str) -> str:#descarcare coperta in folderul covers
    if not cover_url:
        return ""
    rel_path = f"covers/{track_id}.jpg"
    abs_path = COVERS_DIR / f"{track_id}.jpg"
    if abs_path.exists():
        return rel_path
    try:
        resp = requests.get(cover_url, timeout=8)
        if resp.status_code == 200:
            abs_path.write_bytes(resp.content)
            return rel_path
    except requests.RequestException:
        pass
    return ""


#corespondenta id genuri deezer
DEEZER_GENRES = {
    132: "Pop", 116: "Rap/Hip-Hop", 152: "Rock", 113: "Dance",
    165: "R&B", 85: "Alternative", 106: "Electro", 466: "Folk",
    144: "Reggae", 129: "Jazz", 98: "Classical", 464: "Metal"
}


def enrich_track_worker(track_ids: List[str]):#extragere bpm, an si gen in fundal
    def _enrich_one(t_id: str):
        raw_id = t_id.replace("dz_", "")
        if not raw_id.isdigit():
            return
        detail = http_get_json(f"https://api.deezer.com/track/{raw_id}")
        if not detail or "id" not in detail:
            return

        bpm = float(detail.get("bpm") or 0.0)
        if bpm <= 30.0:
            bpm = 120.0
        gain = float(detail.get("gain") or -8.0)
        isrc = detail.get("isrc")
        release_date = detail.get("release_date", "2018-01-01")
        try:
            year = int(release_date.split("-")[0])
        except ValueError:
            year = 2018

        album_obj = detail.get("album", {})
        album_id = album_obj.get("id")
        genre_name = "Pop"
        tags = []

        if album_id:#extragem genul muzical din detaliile albumului
            alb_detail = http_get_json(f"https://api.deezer.com/album/{album_id}")
            if alb_detail:
                g_id = alb_detail.get("genre_id")
                genre_name = DEEZER_GENRES.get(g_id, "Pop")
                genres_data = alb_detail.get("genres", {}).get("data", [])
                tags = [g.get("name", "") for g in genres_data if g.get("name")]

        if not tags:
            tags = [genre_name]

        artist_name = detail.get("artist", {}).get("name", "Unknown")
        title_name = detail.get("title", "Unknown")
        if LASTFM_API_KEY:#adaugam taguri de pe lastfm daca exista cheie
            lfm_url = (
                f"http://ws.audioscrobbler.com/2.0/?method=track.gettoptags"
                f"&artist={urllib.parse.quote(artist_name)}&track={urllib.parse.quote(title_name)}"
                f"&api_key={LASTFM_API_KEY}&format=json"
            )
            lfm_data = http_get_json(lfm_url)
            if lfm_data and "toptags" in lfm_data:
                lfm_tags = [t["name"].title() for t in lfm_data["toptags"].get("tag", [])[:4]]
                if lfm_tags:
                    tags = list(dict.fromkeys(tags + lfm_tags))

        upsert_track({
            "id": t_id,
            "title": title_name,
            "artist": artist_name,
            "artist_id": str(detail.get("artist", {}).get("id", "")),
            "album": album_obj.get("title", "Single"),
            "release_year": year,
            "duration_sec": int(detail.get("duration", 180)),
            "bpm": bpm,
            "gain": gain,
            "rank": int(detail.get("rank", 50000)),
            "genre": genre_name,
            "tags": tags,
            "isrc": isrc,
            "cover_path": f"covers/{t_id}.jpg",
            "enriched": 1
        })

    for tid in track_ids:
        _enrich_one(tid)


def search_online_catalog(query: str, limit: int = 24) -> List[Dict[str, Any]]:#cautare piese pe deezer si descarcare coperti in paralel
    if not query.strip():
        return []

    url = f"https://api.deezer.com/search?q={urllib.parse.quote(query.strip())}&limit={limit}"
    data = http_get_json(url, ttl=3600 * 12)
    items = data.get("data", []) if data else []
    if not items:
        return []

    def _process_item(item: Dict[str, Any]) -> Dict[str, Any]:#salvare date initiale piesa
        t_id = f"dz_{item['id']}"
        album_obj = item.get("album", {})
        cover_url = album_obj.get("cover_medium") or album_obj.get("cover") or ""
        local_cover = download_cover_file(t_id, cover_url)

        track_dict = {
            "id": t_id,
            "title": item.get("title", "Unknown"),
            "artist": item.get("artist", {}).get("name", "Unknown"),
            "artist_id": str(item.get("artist", {}).get("id", "")),
            "album": album_obj.get("title", "Single"),
            "release_year": 2018,
            "duration_sec": int(item.get("duration", 180)),
            "bpm": 120.0,
            "gain": -8.0,
            "rank": int(item.get("rank", 50000)),
            "genre": "Pop",
            "tags": ["Pop"],
            "isrc": None,
            "cover_path": local_cover,
            "enriched": 0
        }
        upsert_track(track_dict)
        return track_dict

    with ThreadPoolExecutor(max_workers=8) as ex:#descarcare rapida pe mai multe fire
        results = list(ex.map(_process_item, items))

    ids_to_enrich = [r["id"] for r in results]
    threading.Thread(target=enrich_track_worker, args=(ids_to_enrich,), daemon=True).start()
    return results


def expand_on_like_async(artist_name: str, artist_id: str = ""):#aducem piese de la artisti similari cand utilizatorul da like
    def _worker():
        if artist_id and artist_id.isdigit():
            rel = http_get_json(f"https://api.deezer.com/artist/{artist_id}/related?limit=3")
            if rel and "data" in rel:
                for r_art in rel["data"][:2]:
                    name = r_art.get("name")
                    if name:
                        search_online_catalog(name, limit=6)
                        return
        if artist_name:
            search_online_catalog(artist_name, limit=8)

    threading.Thread(target=_worker, daemon=True).start()


def ensure_initial_catalog():#populare catalog de start daca baza de date este goala
    existing = get_all_tracks()
    if len(existing) == 0:
        for seed in ["Daft Punk", "The Weeknd", "Arctic Monkeys"]:
            search_online_catalog(seed, limit=8)