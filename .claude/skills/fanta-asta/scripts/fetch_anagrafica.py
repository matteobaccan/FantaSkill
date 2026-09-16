"""Età e data di nascita dalle schede giocatore di fanta.soccer -> data/anagrafica.csv

Legge gli id dei giocatori da data/stats_<stagione corrente>.csv; scarica solo gli id nuovi
(la cache in data/anagrafica.csv è permanente: la data di nascita non cambia).
Circa 500 richieste la prima volta, con pausa di 0.3 s.
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from common import DATA_DIR, ensure_dirs, fetch, load_config

URL = "https://www.fanta.soccer/it/seriea/{pid}/calciatore/{slug}/"


def parse_player(html: str) -> dict:
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    eta = re.search(r"Et[àa&#0-9;]*:\s*(\d+)\s*anni", txt)
    nato = re.search(r"Nato il:\s*(\d{2}/\d{2}/\d{4})", txt)
    naz = re.search(r"Nazionalit[àa&#0-9;]*:\s*([A-Za-zÀ-ÿ ]+?)\s+Et", txt)
    return {"eta": int(eta.group(1)) if eta else None,
            "nato_il": nato.group(1) if nato else "",
            "nazionalita": naz.group(1).strip() if naz else ""}


def main() -> None:
    cfg = load_config()
    ensure_dirs()
    stats = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_corrente']}.csv", dtype={"id": str})
    out = DATA_DIR / "anagrafica.csv"
    done = pd.read_csv(out, dtype={"id": str}) if out.exists() else pd.DataFrame(columns=["id", "nome", "eta", "nato_il", "nazionalita"])
    todo = stats[~stats["id"].isin(done["id"])][["id", "nome"]].drop_duplicates("id")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if limit:
        todo = todo.head(limit)
    print(f"schede da scaricare: {len(todo)} (già in cache: {len(done)})")
    rows = []
    for i, (pid, nome) in enumerate(zip(todo["id"], todo["nome"]), start=1):
        slug = re.sub(r"[^a-z]", "", nome.lower()) or "x"
        try:
            info = parse_player(fetch(URL.format(pid=pid, slug=slug), f"player_{pid}", max_age_hours=24 * 365, delay=0.3))
        except Exception as exc:  # noqa: BLE001 - una scheda mancante non deve bloccare il resto
            print(f"  ! {nome} ({pid}): {exc}")
            info = {"eta": None, "nato_il": "", "nazionalita": ""}
        rows.append({"id": pid, "nome": nome, **info})
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}")
    df = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {len(df)} giocatori, {int(df['eta'].notna().sum())} con età")


if __name__ == "__main__":
    main()
