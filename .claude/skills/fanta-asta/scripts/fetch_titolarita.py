"""Titolarità nella stagione corrente dalle schede giocatore fanta.soccer -> data/titolarita.csv

Legge le card "Partite disputate" già in cache (data/cache/player_<id>.html, scaricate da
fetch_anagrafica.py). Per ogni partita: IN = 1 se entrato dalla panchina, Out = 1 se sostituito.
Colonne: id, partite, da_titolare, subentrato, sostituito, pct_titolare (da_titolare / giornate giocate)
Solo stagione corrente: la scheda mostra la stagione in corso, le precedenti richiedono un postback.
"""
from __future__ import annotations

import pandas as pd
from bs4 import BeautifulSoup

from common import CACHE_DIR, DATA_DIR, ensure_dirs, load_config


def parse_player(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one("#partiteCalciatore")
    partite = da_tit = sub_in = sub_out = 0
    if box:
        for card in box.select("article.card"):
            nums = [d.get_text(" ", strip=True) for d in card.select("div.card-standing-number")]
            pts = [d.get_text(" ", strip=True) for d in card.select("div.card-standing-points")]
            if len(nums) < 7:
                continue
            entrato = nums[5] not in ("", "0", "-")
            uscito = nums[6] not in ("", "0", "-")
            con_voto = bool(pts) and pts[0] not in ("", "-")
            # la card esiste anche se non ha giocato: conta solo se ha un voto, è entrato/uscito o ha fatto qualcosa
            if not (con_voto or entrato or uscito or any(x not in ("", "0", "-") for x in nums[:5])):
                continue
            partite += 1
            da_tit += 0 if entrato else 1
            sub_in += 1 if entrato else 0
            sub_out += 1 if uscito else 0
    return {"partite": partite, "da_titolare": da_tit, "subentrato": sub_in, "sostituito": sub_out}


def main() -> None:
    cfg = load_config()
    ensure_dirs()
    stats = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_corrente']}.csv", dtype={"id": str})
    giornate = int(stats["giornate_giocate"].iloc[0]) if "giornate_giocate" in stats else int(stats["presenze"].max())
    rows, mancanti = [], 0
    for pid, nome in zip(stats["id"], stats["nome"]):
        path = CACHE_DIR / f"player_{pid}.html"
        if not path.exists():
            mancanti += 1
            continue
        info = parse_player(path.read_text(encoding="utf-8", errors="ignore"))
        info["pct_titolare"] = round(info["da_titolare"] / giornate, 2) if giornate else None
        rows.append({"id": pid, "nome": nome, **info})
    df = pd.DataFrame(rows)
    out = DATA_DIR / "titolarita.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"scritto {out}: {len(df)} giocatori, giornate giocate {giornate}, sempre titolari: {int((df['da_titolare'] == giornate).sum())}"
          + (f", schede mancanti: {mancanti} (lancia fetch_anagrafica.py)" if mancanti else ""))


if __name__ == "__main__":
    main()
