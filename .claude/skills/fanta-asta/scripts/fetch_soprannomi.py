"""Nome completo (scheda fanta.soccer) e soprannome (Wikipedia italiana) -> data/soprannomi.csv

- nome_completo: dall'<h1> della scheda giocatore già in cache (data/cache/player_<id>.html)
- soprannome: dal testo della voce di Wikipedia IT, cercando "soprannominato X", "noto/conosciuto come X",
  "detto «X»". Copertura parziale: molti giocatori non hanno un soprannome in voce.

Si legge la pagina HTML https://it.wikipedia.org/wiki/<Nome_Cognome> (segue i redirect); l'API di ricerca
(api.php) risponde 429 dopo poche richieste, quindi si usa solo se la pagina diretta non esiste.
Il testo di ogni voce è messo in cache (data/cache/wiki_*.txt): cambiare la regex non richiede nuovi download.
Uso: python fetch_soprannomi.py [limite]   (riprende da dove si era fermato)
"""
from __future__ import annotations

import re
import sys
import time
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

from common import CACHE_DIR, DATA_DIR, ensure_dirs, load_config, strip_accents

WIKI = "https://it.wikipedia.org/wiki/{title}"
API = "https://it.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (fanta-asta/1.0; strumento personale per il fantacalcio)"}
DELAY = 1.0

# "detto X" solo tra virgolette: senza virgolette cattura frasi come "detto Internazionale" (i club)
NICK_RE = re.compile(
    r"(?:(?:soprannominat[oa]|noto (?:anche )?come|conosciuto (?:anche )?come)\s+(?:anche\s+)?"
    r"(?:[«\"“']\s*(?P<q>[^»\"”'’]{2,30})\s*[»\"”'’]|(?P<u>(?:el|il|la|lo|the)?\s?[A-ZÀ-Ü][\w'’À-ü-]*(?:\s+[A-ZÀ-Ü][\w'’À-ü-]*){0,2}))"
    r"|detto\s+[«\"“']\s*(?P<d>[^»\"”'’]{2,30})\s*[»\"”'’])",
)
BAD = {"Il", "La", "Lo", "Le", "Un", "Una", "Internazionale", "Inter", "Milan", "Juventus", "Roma", "Napoli", "Serie", "Italia"}


def full_name(pid: str) -> str:
    path = CACHE_DIR / f"player_{pid}.html"
    if not path.exists():
        return ""
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else ""


def cache_path(key: str):
    return CACHE_DIR / f"wiki_{re.sub(r'[^A-Za-z0-9]+', '_', strip_accents(key))[:80]}.txt"


def page_text(session: requests.Session, title: str) -> tuple[str, str]:
    """Titolo reale e testo della voce; ('', '') se non esiste. Segue redirect e disambiguazioni semplici."""
    cp = cache_path(title)
    if cp.exists():
        raw = cp.read_text(encoding="utf-8")
        real, _, text = raw.partition("\n")
        return real, text
    r = session.get(WIKI.format(title=quote(title.replace(" ", "_"))), timeout=25, allow_redirects=True)
    time.sleep(DELAY)
    if r.status_code != 200:
        cp.write_text("\n", encoding="utf-8")
        return "", ""
    soup = BeautifulSoup(r.text, "lxml")
    real = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else title
    body = soup.select_one("#mw-content-text")
    text = " ".join(p.get_text(" ", strip=True) for p in body.find_all("p")) if body else ""
    if "calciator" not in text.lower()[:600] and "disambigua" in r.text.lower()[:20000]:
        # pagina di disambiguazione: prova il link che contiene "calciatore"
        link = next((a["href"] for a in body.find_all("a", href=True) if "calciatore" in a["href"].lower()), None) if body else None
        if link:
            cp.write_text("\n", encoding="utf-8")
            return page_text(session, link.split("/wiki/")[-1].replace("_", " "))
    if "calciator" not in text.lower()[:600]:
        text = ""  # omonimo non calciatore
    cp.write_text(f"{real}\n{text}", encoding="utf-8")
    return (real if text else ""), text


def search_title(session: requests.Session, query: str) -> str:
    try:
        r = session.get(API, params={"action": "opensearch", "search": query, "limit": 1, "format": "json"}, timeout=25)
        time.sleep(DELAY)
        if r.headers.get("content-type", "").startswith("application/json"):
            hits = r.json()[1]
            return hits[0] if hits else ""
    except Exception:  # noqa: BLE001
        pass
    return ""


def nicknames(text: str, query: str) -> str:
    out = []
    for m in NICK_RE.finditer(text):
        n = (m.group("q") or m.group("u") or m.group("d") or "").strip(" .,;:")
        if n and n not in BAD and n.lower() not in query.lower() and n not in out:
            out.append(n)
    return " / ".join(out[:2])


def candidates(nome_completo: str) -> list[str]:
    """Varianti del titolo: nome completo, primo+ultimo, primo+penultimo (Soulé Malvano -> Matías Soulé)."""
    t = nome_completo.split()
    out = [nome_completo]
    if len(t) >= 3:
        out += [f"{t[0]} {t[-1]}", f"{t[0]} {t[-2]}", f"{t[0]} {t[1]}"]
    return list(dict.fromkeys(out))


def lookup(session: requests.Session, nome_completo: str) -> tuple[str, str]:
    title = text = ""
    for cand in candidates(nome_completo):
        title, text = page_text(session, cand)
        if text:
            break
    if not text:
        alt = search_title(session, f"{nome_completo} calciatore")
        if alt:
            title, text = page_text(session, alt)
    return title, nicknames(text, nome_completo) if text else ""


def main() -> None:
    cfg = load_config()
    ensure_dirs()
    stats = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_corrente']}.csv", dtype={"id": str})
    out = DATA_DIR / "soprannomi.csv"
    cols = ["id", "nome", "nome_completo", "wikipedia", "soprannome"]
    done = pd.read_csv(out, dtype={"id": str}).fillna("") if out.exists() else pd.DataFrame(columns=cols)
    todo = stats[~stats["id"].isin(done["id"])][["id", "nome"]].drop_duplicates("id")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if limit:
        todo = todo.head(limit)
    print(f"da cercare: {len(todo)} (già fatti: {len(done)})", flush=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    rows = []
    for i, (pid, nome) in enumerate(zip(todo["id"], todo["nome"]), start=1):
        nc = full_name(pid) or nome
        try:
            title, nick = lookup(session, nc)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {nc}: {exc}", flush=True)
            title, nick = "", ""
        rows.append({"id": pid, "nome": nome, "nome_completo": nc, "wikipedia": title, "soprannome": nick})
        if nick:
            print(f"  {nc} -> {nick}", flush=True)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
            pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_csv(out, index=False, encoding="utf-8")
    df = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {len(df)} giocatori, {int((df['wikipedia'].fillna('') != '').sum())} con voce, "
          f"{int((df['soprannome'].fillna('') != '').sum())} con soprannome", flush=True)


if __name__ == "__main__":
    main()
