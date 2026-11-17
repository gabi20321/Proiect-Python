import os
from pathlib import Path
from dotenv import load_dotenv

#incarcare variabile din fisierul .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")

#cai catre baza de date si folderele de imagini
DB_PATH = BASE_DIR / "musicmeter_v2.db"
COVERS_DIR = BASE_DIR / "covers"
AVATARS_DIR = BASE_DIR / "avatars"

#creare foldere daca nu exista
COVERS_DIR.mkdir(exist_ok=True)
AVATARS_DIR.mkdir(exist_ok=True)

#culori stil 
THEME = {
    "bg_main": "#14181C",
    "bg_header": "#1B2128",
    "bg_card": "#242C36",
    "bg_card_hover": "#2E3846",
    "bg_input": "#111518",
    "border": "#364252",
    "text_main": "#F4F7FA",
    "text_sub": "#C2CEDB",
    "text_muted": "#8A99AD",
    "accent": "#00E054",
    "accent_hover": "#00B843",
    "accent_soft": "#163324",
    "danger": "#E53935",
    "danger_hover": "#C62828",
    "font": "Segoe UI",
}