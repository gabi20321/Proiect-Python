import sqlite3
import json
import time
from typing import Optional, List, Dict, Any
from config import DB_PATH

#schema tabelelor din baza de date sqlite
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS http_cache (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    avatar_path TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M', 'now'))
);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    artist_id TEXT,
    album TEXT NOT NULL DEFAULT 'Single',
    release_year INTEGER DEFAULT 2018,
    duration_sec INTEGER DEFAULT 180,
    bpm REAL DEFAULT 120.0,
    gain REAL DEFAULT -8.0,
    rank INTEGER DEFAULT 50000,
    genre TEXT DEFAULT 'Pop',
    tags TEXT DEFAULT '[]',
    isrc TEXT,
    cover_path TEXT,
    enriched INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    signal INTEGER DEFAULT 0,
    rating INTEGER DEFAULT NULL,
    review TEXT DEFAULT '',
    watchlist INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    UNIQUE(user_id, track_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);
"""


def get_conn() -> sqlite3.Connection:#deschidere conexiune cu baza de date
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():#creare tabele la pornirea aplicatiei
    conn = get_conn()
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute("DROP TABLE IF EXISTS activity_log;")
            conn.execute("DROP TABLE IF EXISTS pending_registrations;")
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "avatar_path" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT DEFAULT ''")
    finally:
        conn.close()


init_db()


def cache_get(key: str) -> Optional[Any]:#citire raspuns api din cache daca nu a expirat
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT payload, expires_at FROM http_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row and row["expires_at"] > time.time():
            return json.loads(row["payload"])
        return None
    finally:
        conn.close()


def cache_set(key: str, data: Any, ttl_seconds: int = 86400 * 7):#salvare raspuns api in cache
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO http_cache (cache_key, payload, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(data), time.time() + ttl_seconds),
            )
    finally:
        conn.close()


def upsert_track(track: Dict[str, Any]):#inserare sau actualizare piesa in baza de date
    conn = get_conn()
    try:
        with conn:
            tags_str = (
                json.dumps(track.get("tags", []))
                if isinstance(track.get("tags"), list)
                else track.get("tags", "[]")
            )
            conn.execute(
                """
                INSERT INTO tracks (id, title, artist, artist_id, album, release_year, duration_sec,
                                    bpm, gain, rank, genre, tags, isrc, cover_path, enriched)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    release_year = CASE WHEN excluded.release_year != 2018 THEN excluded.release_year ELSE tracks.release_year END,
                    bpm = CASE WHEN excluded.bpm != 120.0 THEN excluded.bpm ELSE tracks.bpm END,
                    gain = CASE WHEN excluded.gain != -8.0 THEN excluded.gain ELSE tracks.gain END,
                    rank = CASE WHEN excluded.rank != 50000 THEN excluded.rank ELSE tracks.rank END,
                    genre = CASE WHEN excluded.genre != 'Pop' THEN excluded.genre ELSE tracks.genre END,
                    tags = CASE WHEN excluded.tags != '[]' THEN excluded.tags ELSE tracks.tags END,
                    isrc = COALESCE(excluded.isrc, tracks.isrc),
                    cover_path = CASE WHEN excluded.cover_path != '' THEN excluded.cover_path ELSE tracks.cover_path END,
                    enriched = MAX(tracks.enriched, excluded.enriched)
                """,
                (
                    str(track["id"]),
                    track.get("title", "Unknown"),
                    track.get("artist", "Unknown"),
                    str(track.get("artist_id", "")),
                    track.get("album", "Single"),
                    int(track.get("release_year", 2018)),
                    int(track.get("duration_sec", 180)),
                    float(track.get("bpm", 120.0)),
                    float(track.get("gain", -8.0)),
                    int(track.get("rank", 50000)),
                    track.get("genre", "Pop"),
                    tags_str,
                    track.get("isrc"),
                    track.get("cover_path", ""),
                    int(track.get("enriched", 0)),
                ),
            )
    finally:
        conn.close()


def get_all_tracks() -> List[Dict[str, Any]]:#luam toate piesele ordonate dupa popularitate
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM tracks ORDER BY rank DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except Exception:
                d["tags"] = []
            result.append(d)
        return result
    finally:
        conn.close()


def search_local_tracks(query: str) -> List[Dict[str, Any]]:#cautare piese in baza de date locala
    conn = get_conn()
    try:
        q = f"%{query.strip()}%"
        rows = conn.execute(
            "SELECT * FROM tracks WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? ORDER BY rank DESC LIMIT 60",
            (q, q, q, q),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except Exception:
                d["tags"] = []
            result.append(d)
        return result
    finally:
        conn.close()