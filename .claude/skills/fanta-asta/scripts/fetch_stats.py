"""Scarica le statistiche per giocatore da fanta.soccer e le unisce in un CSV per stagione.

Uso: python fetch_stats.py <stagione> [giornata]
  stagione es. 2026-2027; giornata = ultima giornata inclusa (38 per una stagione chiusa,
  'auto' = si autodetermina dal massimo delle presenze).

URL schema: /it/statistiche/A/<stagione>/Tutti/<Statistica>/Full/fs/<giornata>/
NB: il ruolo va lasciato a 'Tutti' (con 'Portiere' la tabella torna vuota).
"""
from __future__ import annotations

import re
import sys
from urllib.parse import quote

import pandas as pd
from bs4 import BeautifulSoup

from common import DATA_DIR, ensure_dirs, fetch, load_config, norm_name, to_float

BASE = "https://www.fanta.soccer/it/statistiche/A/{season}/Tutti/{stat}/Full/fs/{gw}/"

STATS = {
    "Media Voto": "mv",
    "Fantamedia": "fm",
    "Gol Segnati": "gol",
    "Assist": "assist",
    "Rigori Segnati": "rig_segnati",
    "Rigori Sbagliati": "rig_sbagliati",
    "Gol Subiti": "gol_subiti",
    "Rigori Parati": "rig_parati",
    "I più ammoniti": "ammonizioni",
    "I più espulsi": "espulsioni",
}


def parse_table(html: str, col: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        if heads and heads[0] == "Pos." and "Nome" in heads:
            table = t
            break
    if table is None:
        raise RuntimeError("tabella statistiche non trovata")
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        a = tds[1].find("a")
        name = a.get_text(strip=True) if a else tds[1].get_text(strip=True)
        m = re.search(r"\((P|D|C|A)\)", tds[1].get_text(" ", strip=True))
        pid = re.search(r"/seriea/(\d+)/", a["href"]).group(1) if a and a.has_attr("href") else ""
        rows.append({
            "id": pid,
            "nome": name,
            "ruolo": m.group(1) if m else "",
            "squadra": tds[2].get_text(strip=True),
            col: to_float(tds[3].get_text(strip=True)),
            "presenze": int(tds[4].get_text(strip=True) or 0),
        })
    return pd.DataFrame(rows)


def _rows_at(season: str, gw: int) -> int:
    html = fetch(BASE.format(season=season, stat=quote("Fantamedia"), gw=gw), f"stats_{season}_fm_{gw}")
    try:
        return len(parse_table(html, "fm"))
    except RuntimeError:
        return 0


def detect_giornata(season: str) -> int:
    """Ultima giornata per cui il sito restituisce righe: oltre la giornata in corso la tabella è vuota.
    Ricerca binaria su 1..38 (circa 6 richieste)."""
    lo, hi = 1, 38
    if _rows_at(season, hi):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _rows_at(season, mid):
            lo = mid
        else:
            hi = mid
    return lo


def fetch_season(season: str, gw: str | int) -> pd.DataFrame:
    if gw == "auto":
        gw = detect_giornata(season)
        print(f"[{season}] giornata autodeterminata: {gw}")
    merged: pd.DataFrame | None = None
    for stat, col in STATS.items():
        url = BASE.format(season=season, stat=quote(stat), gw=gw)
        df = parse_table(fetch(url, f"stats_{season}_{col}_{gw}"), col)
        print(f"[{season}] {stat}: {len(df)} righe")
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df[["id", "nome", "squadra", col]], on=["id", "nome", "squadra"], how="outer")
    assert merged is not None
    merged["giornata"] = gw                                  # parametro fs usato nell'URL
    merged["giornate_giocate"] = int(merged["presenze"].max())  # giornate effettivamente disputate
    merged["stagione"] = season
    merged["chiave"] = merged["nome"].map(norm_name)
    for c in ("gol", "assist", "rig_segnati", "rig_sbagliati", "gol_subiti", "rig_parati", "ammonizioni", "espulsioni"):
        merged[c] = merged[c].fillna(0).astype(int)
    return merged.sort_values(["ruolo", "fm"], ascending=[True, False]).reset_index(drop=True)


def main() -> None:
    cfg = load_config()
    season = sys.argv[1] if len(sys.argv) > 1 else cfg["stagione_corrente"]
    gw = sys.argv[2] if len(sys.argv) > 2 else (cfg["giornata_corrente"] if season == cfg["stagione_corrente"] else cfg["giornate_stagione"])
    ensure_dirs()
    df = fetch_season(season, gw)
    out = DATA_DIR / f"stats_{season}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out} ({len(df)} giocatori, fs={df['giornata'].iloc[0]}, giornate giocate={df['giornate_giocate'].iloc[0]})")


if __name__ == "__main__":
    main()
