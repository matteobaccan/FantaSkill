"""Infortunati e squalificati con durata -> data/indisponibili.csv

Fonti (in ordine):
 1. fanta.soccer /it/seriea/infortunati/  -> CHI è infortunato/squalificato (nessuna durata)
 2. transfermarkt verletztespieler        -> tipo infortunio + data di rientro ("fino ca.")
 3. fantacalcio.it /infortunati-serie-a   -> descrizione testuale con rientro stimato

Colonne: squadra, nome, chiave, ruolo, tipo (infortunato|squalificato), infortunio, rientro_data,
         rientro_nota, fonti
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import DATA_DIR, ensure_dirs, fetch, norm_name, norm_team, surname_key

URL_FS = "https://www.fanta.soccer/it/seriea/infortunati/"
URL_TM = "https://www.transfermarkt.it/serie-a/verletztespieler/wettbewerb/IT1"
URL_FC = "https://www.fantacalcio.it/infortunati-serie-a"


def parse_fantasoccer(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for table in soup.select("table.table-standings"):
        th = table.find("th")
        if not th:
            continue
        team = th.get_text(" ", strip=True)
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            label = tds[0].get_text(strip=True).lower()
            tipo = "squalificato" if "squalific" in label else "infortunato"
            for a in tds[1].find_all("a"):
                after = a.next_sibling or ""
                m = re.search(r"\((P|D|C|A)\)", str(after))
                name = a.get_text(strip=True)
                rows.append({"squadra": team, "nome": name, "chiave": norm_name(name),
                             "ruolo": m.group(1) if m else "", "tipo": tipo,
                             "infortunio": "", "rientro_data": "", "rientro_nota": "", "fonti": "fanta.soccer"})
    return rows


def parse_transfermarkt(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.items")
    rows = []
    if not table:
        return rows
    for tr in table.select("tbody > tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 4:
            continue
        name = tds[0].find("img")["title"] if tds[0].find("img") else tds[0].get_text("|", strip=True).split("|")[0]
        team_img = tds[1].find("img")
        team = team_img["title"] if team_img else tds[1].get_text(strip=True)
        rows.append({"squadra_tm": team, "squadra_norm": norm_team(team), "chiave": surname_key(name),
                     "nome_tm": name, "infortunio": tds[2].get_text(strip=True),
                     "rientro_data": tds[3].get_text(strip=True)})
    return rows


def parse_fantacalcio_it(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for card in soup.select("div.team-card"):
        team = card.select_one(".team-name").get_text(strip=True)
        for li in card.select("li"):
            name_el = li.select_one(".item-name")
            desc_el = li.select_one(".item-description")
            if not name_el:
                continue
            rows.append({"squadra": team, "squadra_norm": norm_team(team), "nome": name_el.get_text(strip=True),
                         "chiave": norm_name(name_el.get_text(strip=True)),
                         "rientro_nota": desc_el.get_text(" ", strip=True) if desc_el else ""})
    return rows


def main() -> None:
    ensure_dirs()
    base = parse_fantasoccer(fetch(URL_FS, "infortunati_fantasoccer", max_age_hours=6))
    tm = parse_transfermarkt(fetch(URL_TM, "infortunati_transfermarkt", max_age_hours=12))
    fc = parse_fantacalcio_it(fetch(URL_FC, "infortunati_fantacalcio_it", max_age_hours=12))
    tm_idx = {(r["squadra_norm"], r["chiave"]): r for r in tm}
    fc_idx = {(r["squadra_norm"], r["chiave"]): r for r in fc}

    for r in base:
        key = (norm_team(r["squadra"]), r["chiave"])
        hit = tm_idx.pop(key, None)
        if hit:
            r["infortunio"], r["rientro_data"] = hit["infortunio"], hit["rientro_data"]
            r["fonti"] += "+transfermarkt"
        hit = fc_idx.pop(key, None)
        if hit:
            r["rientro_nota"] = hit["rientro_nota"]
            r["fonti"] += "+fantacalcio.it"

    # infortunati noti alle altre fonti ma non a fanta.soccer: li aggiungo comunque
    for key, r in tm_idx.items():
        nota = fc_idx.pop(key, {}).get("rientro_nota", "")
        base.append({"squadra": r["squadra_tm"], "nome": r["nome_tm"], "chiave": r["chiave"], "ruolo": "",
                     "tipo": "infortunato", "infortunio": r["infortunio"], "rientro_data": r["rientro_data"],
                     "rientro_nota": nota, "fonti": "transfermarkt" + ("+fantacalcio.it" if nota else "")})
    for key, r in fc_idx.items():
        base.append({"squadra": r["squadra"], "nome": r["nome"], "chiave": key[1], "ruolo": "", "tipo": "infortunato",
                     "infortunio": "", "rientro_data": "", "rientro_nota": r["rientro_nota"], "fonti": "fantacalcio.it"})

    df = pd.DataFrame(base)
    out = DATA_DIR / "indisponibili.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    con_data = int((df["rientro_data"] != "").sum())
    con_nota = int((df["rientro_nota"] != "").sum())
    print(f"scritto {out}: {len(df)} indisponibili, {con_data} con data rientro, {con_nota} con nota rientro")


if __name__ == "__main__":
    main()
