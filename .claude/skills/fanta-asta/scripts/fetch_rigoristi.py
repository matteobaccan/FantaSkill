"""Rigoristi e battitori di calci piazzati da fantacalcio.it -> data/rigoristi.csv

Colonne: squadra, tipo (rigori|piazzati), ordine (1 = primo tiratore), nome, chiave
"""
from __future__ import annotations

import pandas as pd
from bs4 import BeautifulSoup

from common import DATA_DIR, ensure_dirs, fetch, norm_name

URL = "https://www.fantacalcio.it/rigoristi-serie-a"


def parse(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for card in soup.select("div.team-card"):
        team = card.select_one(".team-name").get_text(strip=True)
        for col in card.select("div.col"):
            header = col.find("header").get_text(strip=True).lower()
            tipo = "rigori" if "rigor" in header else "piazzati"
            for i, li in enumerate(col.select("ol li"), start=1):
                name = li.get_text(" ", strip=True)
                rows.append({"squadra": team, "tipo": tipo, "ordine": i, "nome": name, "chiave": norm_name(name)})
    return pd.DataFrame(rows)


def main() -> None:
    ensure_dirs()
    df = parse(fetch(URL, "rigoristi_fantacalcio_it", max_age_hours=24))
    out = DATA_DIR / "rigoristi.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {df['squadra'].nunique()} squadre, {len(df)} righe")


if __name__ == "__main__":
    main()
