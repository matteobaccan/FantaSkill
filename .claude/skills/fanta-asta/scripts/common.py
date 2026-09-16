"""Utilità condivise: download con cache, normalizzazione nomi, percorsi."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import sys

import requests

# console Windows in cp1252: evita UnicodeEncodeError stampando nomi con accenti
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent.parent
ROOT = SKILL_DIR.parent.parent.parent  # radice del repo (…/.claude/skills/fanta-asta -> repo)
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = ROOT / "output"
CONFIG_PATH = SKILL_DIR / "config.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def fetch(url: str, cache_key: str, max_age_hours: float = 12, delay: float = 0.4) -> str:
    """Scarica una pagina; riusa la copia in data/cache se più recente di max_age_hours."""
    ensure_dirs()
    path = CACHE_DIR / f"{cache_key}.html"
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
        return path.read_text(encoding="utf-8", errors="ignore")
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    if "/it/errore/" in resp.url or "/it/notfound/" in resp.url:
        raise RuntimeError(f"fanta.soccer ha risposto con una pagina di errore per {url}")
    path.write_text(resp.text, encoding="utf-8")
    time.sleep(delay)
    return resp.text


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_team(s: str) -> str:
    """Nome squadra confrontabile tra fonti (Hellas Verona -> verona, ecc.)."""
    s = strip_accents(s or "").lower().strip()
    s = re.sub(r"\b(hellas|fc|ac|us|ssc|as|calcio|1913|1909|1907)\b", " ", s)
    return re.sub(r"[^a-z]", "", s)


def norm_name(s: str) -> str:
    """Cognome normalizzato: 'Hien I.' -> 'hien', 'De Ketelaere' -> 'deketelaere'."""
    s = strip_accents(s or "").lower()
    s = re.sub(r"\([a-z]\)", " ", s)          # ruolo tra parentesi
    s = re.sub(r"\b[a-z]\.\s*", " ", s)        # iniziali puntate
    s = re.sub(r"[^a-z ]", " ", s)
    return "".join(s.split())


def surname_key(full_name: str) -> str:
    """Per nomi completi (transfermarkt): usa l'ultimo token come cognome."""
    parts = strip_accents(full_name).replace("-", " ").split()
    return norm_name(parts[-1]) if parts else ""


def to_float(s: str) -> float | None:
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
