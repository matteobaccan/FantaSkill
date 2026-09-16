"""Classifica con gol fatti/subiti per squadra da transfermarkt -> data/classifica_<stagione>.csv

Uso: python fetch_classifica.py <stagione es. 2025-2026>
Serve per i portieri: la statistica "Gol Subiti" di fanta.soccer restituisce 0 per tutti.
Colonne: squadra, pg, v, n, p, gf, gs, diff_reti, punti, gs_partita
"""
from __future__ import annotations

import sys

import pandas as pd
from bs4 import BeautifulSoup

from common import DATA_DIR, ensure_dirs, fetch, load_config, norm_team

URL = "https://www.transfermarkt.it/serie-a/tabelle/wettbewerb/IT1/saison_id/{anno}"


def parse(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.select("table.items tbody > tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td", recursive=False)]
        if len(tds) < 10 or ":" not in tds[7]:
            continue
        gf, gs = (int(x) for x in tds[7].split(":"))
        pg = int(tds[3])
        rows.append({"squadra": tds[2], "squadra_n": norm_team(tds[2]), "pg": pg, "v": int(tds[4]), "n": int(tds[5]), "p": int(tds[6]),
                     "gf": gf, "gs": gs, "diff_reti": int(tds[8]), "punti": int(tds[9]), "gs_partita": round(gs / pg, 2) if pg else None})
    return pd.DataFrame(rows)


def main() -> None:
    cfg = load_config()
    season = sys.argv[1] if len(sys.argv) > 1 else cfg["stagione_corrente"]
    anno = season.split("-")[0]
    ensure_dirs()
    df = parse(fetch(URL.format(anno=anno), f"classifica_tm_{season}", max_age_hours=12))
    if len(df) != 20:
        print(f"ATTENZIONE: trovate {len(df)} squadre invece di 20")
    out = DATA_DIR / f"classifica_{season}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {len(df)} squadre, giornate giocate max {df['pg'].max()}")


if __name__ == "__main__":
    main()
