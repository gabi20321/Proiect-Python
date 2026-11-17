import os
import hashlib
import sqlite3
from collections import Counter
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
from email_validator import validate_email, EmailNotValidError

from config import AVATARS_DIR, BASE_DIR, THEME
from database import get_conn, get_all_tracks
from providers import expand_on_like_async

#domenii de email temporare interzise la inregistrare
DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com",
    "temp-mail.org", "yopmail.com", "trashmail.com", "sharklasers.com",
    "getnada.com", "maildrop.cc", "dispostable.com", "fakeinbox.com",
    "throwawaymail.com", "mohmal.com", "mailnesia.com",
}


def hash_password(password: str) -> str:#functie hash sha256 pentru parola
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def validate_real_email(raw_email: str) -> Tuple[bool, str, str]:#verificare format email si server mx
    try:
        info = validate_email(raw_email.strip(), check_deliverability=True)
        normalized = info.normalized.lower()
        domain = info.domain.lower()
        if domain in DISPOSABLE_DOMAINS or any(domain.endswith("." + d) for d in DISPOSABLE_DOMAINS):
            return False, "", "Adresele de email temporare (disposable) nu sunt permise."
        return True, normalized, ""
    except EmailNotValidError as e:
        return False, "", f"Adresa de email invalida sau domeniu inexistent: {str(e)}"


def register_user(username: str, email: str, password: str) -> Tuple[bool, str]:#creare cont utilizator nou
    clean_user = username.strip()
    if len(clean_user) < 3 or len(password) < 6:
        return False, "Utilizatorul trebuie sa aiba minim 3 caractere, iar parola minim 6."

    ok_mail, norm_email, err_msg = validate_real_email(email)
    if not ok_mail:
        return False, err_msg

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
            (clean_user, norm_email),
        ).fetchone()
        if existing:
            return (
                False,
                "Datele introduse nu pot fi utilizate. Incearca alt nume de utilizator sau autentifica-te.",
            )

        with conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (clean_user, norm_email, hash_password(password)),
            )
        return True, "Contul a fost creat cu succes!"
    except sqlite3.IntegrityError:
        return False, "Datele introduse nu pot fi utilizate."
    finally:
        conn.close()


def login_user(username: str, password: str) -> Optional[Dict[str, Any]]:#verificare nume si parola la login
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, avatar_path, created_at FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if row and row["password_hash"] == hash_password(password):
            return dict(row)
        return None
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:#preluare date cont dupa username
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_user_avatar(user_id: int, source_file_path: str) -> Tuple[bool, str]:#decupare patrata si salvare poza de profil
    if not os.path.exists(source_file_path):
        return False, "Fisierul selectat nu exista."

    ext = os.path.splitext(source_file_path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return False, "Format invalid. Sunt acceptate doar imagini PNG sau JPG."

    size_bytes = os.path.getsize(source_file_path)
    if size_bytes > 5 * 1024 * 1024:
        return False, "Imaginea depaseste limita maxima de 5 MB."

    try:
        with Image.open(source_file_path) as img:
            if img.format not in ("PNG", "JPEG", "MPO"):
                return False, "Fisierul nu este o imagine PNG/JPG valida."
            img = ImageOps.exif_transpose(img).convert("RGB")
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            cropped = img.crop((left, top, left + side, top + side))
            resized = cropped.resize((256, 256), Image.Resampling.LANCZOS)

            rel_dest = f"avatars/{user_id}.png"
            abs_dest = AVATARS_DIR / f"{user_id}.png"
            resized.save(abs_dest, format="PNG")
    except Exception:
        return False, "Eroare la procesarea imaginii."

    conn = get_conn()
    try:
        with conn:
            conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (rel_dest, user_id))
    finally:
        conn.close()

    return True, rel_dest


def build_circular_avatar_pil(user_obj: Dict[str, Any], diameter: int) -> Image.Image:#generare imagine rotunda pt avatar
    scale = 2
    big = diameter * scale
    avatar_rel = (user_obj or {}).get("avatar_path") or ""
    abs_path = BASE_DIR / avatar_rel if avatar_rel else None

    if avatar_rel and abs_path and abs_path.exists():
        try:
            base_img = Image.open(abs_path).convert("RGBA").resize((big, big), Image.Resampling.LANCZOS)
        except Exception:
            base_img = None
    else:
        base_img = None

    if base_img is None:#daca nu are poza desenam initiala numelui
        base_img = Image.new("RGBA", (big, big), THEME["bg_card"])
        draw = ImageDraw.Draw(base_img)
        username = (user_obj or {}).get("username") or "U"
        initial = username[0].upper()
        try:
            font = ImageFont.truetype("segoeui.ttf", int(big * 0.46))
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), initial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((big - tw) / 2, (big - th) / 2 - bbox[1] * 0.5),
            initial,
            fill=THEME["accent"],
            font=font,
        )

    mask = Image.new("L", (big, big), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, big - 1, big - 1), fill=255)

    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(base_img, (0, 0), mask)

    border_draw = ImageDraw.Draw(out)
    border_draw.ellipse((1, 1, big - 2, big - 2), outline=THEME["accent"], width=max(2, scale))
    return out.resize((diameter, diameter), Image.Resampling.LANCZOS)


def get_track_user_state(user_id: int, track_id: str) -> Dict[str, Any]:#citire stare like, nota si recenzie pt o piesa
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM interactions WHERE user_id = ? AND track_id = ?",
            (user_id, str(track_id)),
        ).fetchone()
        if row:
            return dict(row)
        return {"signal": 0, "rating": None, "review": "", "watchlist": 0}
    finally:
        conn.close()


def save_interaction(
    user_id: int,
    track: Dict[str, Any],
    signal: Optional[int] = None,
    rating: Optional[int] = None,
    review: Optional[str] = None,
    watchlist: Optional[int] = None,
):#salvare like, dislike, lista, nota sau recenzie in baza de date
    track_id = str(track["id"])
    current = get_track_user_state(user_id, track_id)

    new_signal = current["signal"] if signal is None else signal
    new_rating = current["rating"] if rating is None else rating
    new_review = current["review"] if review is None else review.strip()
    new_watch = current["watchlist"] if watchlist is None else watchlist

    conn = get_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO interactions (user_id, track_id, signal, rating, review, watchlist, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))
                ON CONFLICT(user_id, track_id) DO UPDATE SET
                    signal = excluded.signal,
                    rating = excluded.rating,
                    review = excluded.review,
                    watchlist = excluded.watchlist,
                    updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
                """,
                (user_id, track_id, new_signal, new_rating, new_review, new_watch),
            )

        if signal == 1:
            expand_on_like_async(track.get("artist", ""), str(track.get("artist_id", "")))
    finally:
        conn.close()


def get_user_library(user_id: int) -> Dict[str, List[Dict[str, Any]]]:#grupare piese din biblioteca utilizatorului
    all_tracks = {t["id"]: t for t in get_all_tracks()}
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM interactions WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user_id,)
        ).fetchall()
    finally:
        conn.close()

    favorites, watchlist, reviewed, excluded = [], [], [], []
    for r in rows:
        t = all_tracks.get(r["track_id"])
        if not t:
            continue
        item = t.copy()
        item["user_rating"] = r["rating"]
        item["user_review"] = r["review"]
        item["user_signal"] = r["signal"]
        item["updated_at"] = r["updated_at"]

        if r["signal"] == 1:
            favorites.append(item)
        if r["signal"] == -1:
            excluded.append(item)
        if r["watchlist"] == 1:
            watchlist.append(item)
        if r["rating"] is not None or (r["review"] and r["review"].strip()):
            reviewed.append(item)

    return {
        "favorites": favorites,
        "watchlist": watchlist,
        "reviewed": reviewed,
        "excluded": excluded,
    }


def get_user_profile_stats(user_id: int) -> Dict[str, Any]:#calcul statistici si distributie note pt profil
    lib = get_user_library(user_id)
    favs = lib["favorites"]
    rev = lib["reviewed"]

    ratings = [t["user_rating"] / 2.0 for t in rev if t.get("user_rating")]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    genres = [t.get("genre", "Pop") for t in favs if t.get("genre")]
    artists = [t.get("artist", "") for t in favs if t.get("artist")]

    top_genre = Counter(genres).most_common(1)[0][0] if genres else "-"
    top_artist = Counter(artists).most_common(1)[0][0] if artists else "-"

    star_bins = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in ratings:
        bucket = min(5, max(1, int(round(r))))
        star_bins[bucket] += 1

    return {
        "favorites_count": len(favs),
        "excluded_count": len(lib["excluded"]),
        "reviews_count": len(rev),
        "watchlist_count": len(lib["watchlist"]),
        "avg_rating": avg_rating,
        "top_genre": top_genre,
        "top_artist": top_artist,
        "star_bins": star_bins,
    }