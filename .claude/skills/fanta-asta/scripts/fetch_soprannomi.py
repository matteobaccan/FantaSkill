"""Nome completo (scheda fanta.soccer) e soprannome (Wikipedia italiana) -> data/soprannomi.csv

- nome_completo: dall'<h1> della scheda giocatore già in cache (data/cache/player_<id>.html)
- soprannome: dal testo della voce di Wikipedia IT, cercando "soprannominato X", "detto X",
  "noto/conosciuto come X". Copertura parziale: molti giocatori non hanno un soprannome in voce.
Wikipedia limita le richieste: 1 richiesta ogni ~1.5 s e pausa di 30 s sui 429.
Uso: python fetch_soprannomi.py [limite]
"""
from __future__ import annotations

import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from common import CACHE_DIR, DATA_DIR, ensure_dirs, load_config

API = "https://it.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "fanta-asta/1.0 (strumento personale per il fantacalcio)"}
DELAY = 1.5

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


def api(session: requests.Session, params: dict) -> dict:
    for _ in range(4):
        r = session.get(API, params={**params, "format": "json"}, timeout=25)
        if r.status_code == 429:
            time.sleep(30)
            continue
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        time.sleep(5)
    return {}


def wiki_nickname(session: requests.Session, query: str) -> tuple[str, str]:
    r = api(session, {"action": "query", "list": "search", "srsearch": f"{query} calciatore", "srlimit": 1})
    hits = r.get("query", {}).get("search", [])
    if not hits:
        return "", ""
    title = hits[0]["title"]
    cache = CACHE_DIR / f"wiki_{re.sub(r'[^A-Za-z0-9]+', '_', title)}.txt"
    if cache.exists():
        text = cache.read_text(encoding="utf-8")
    else:
        time.sleep(DELAY)
        r = api(session, {"action": "query", "prop": "extracts", "explaintext": 1, "titles": title})
        page = next(iter(r.get("query", {}).get("pages", {}).values()), {})
        text = page.get("extract", "")
        cache.write_text(text, encoding="utf-8")
    nicks = []
    for m in NICK_RE.finditer(text):
        n = (m.group("q") or m.group("u") or m.group("d") or "").strip(" .,;:")
        if n and n not in BAD and n.lower() not in query.lower() and n not in nicks:
            nicks.append(n)
    return title, " / ".join(nicks[:2])


def main() -> None:
    cfg = load_config()
    ensure_dirs()
    stats = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_corrente']}.csv", dtype={"id": str})
    out = DATA_DIR / "soprannomi.csv"
    done = pd.read_csv(out, dtype={"id": str}).fillna("") if out.exists() else pd.DataFrame(columns=["id", "nome", "nome_completo", "wikipedia", "soprannome"])
    todo = stats[~stats["id"].isin(done["id"])][["id", "nome", "squadra"]].drop_duplicates("id")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if limit:
        todo = todo.head(limit)
    print(f"da cercare: {len(todo)} (già fatti: {len(done)})", flush=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    rows = []
    for i, (pid, nome, squadra) in enumerate(zip(todo["id"], todo["nome"], todo["squadra"]), start=1):
        nc = full_name(pid) or nome
        try:
            title, nick = wiki_nickname(session, nc)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {nc}: {exc}", flush=True)
            title, nick = "", ""
        rows.append({"id": pid, "nome": nome, "nome_completo": nc, "wikipedia": title, "soprannome": nick})
        if nick:
            print(f"  {nc} -> {nick}", flush=True)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
            pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_csv(out, index=False, encoding="utf-8")
        time.sleep(DELAY)
    df = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {len(df)} giocatori, {int((df['soprannome'].fillna('') != '').sum())} con soprannome", flush=True)


if __name__ == "__main__":
    main()
