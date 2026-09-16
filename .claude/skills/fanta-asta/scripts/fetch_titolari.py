"""Titolari attesi da fanta.soccer probabili formazioni -> data/titolari.csv

Colonne: id, nome, ruolo, squadra, modulo, allenatore, titolare (1) / panchina (0), giornata_testo
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import DATA_DIR, ensure_dirs, fetch, norm_name

URL = "https://www.fanta.soccer/it/seriea/probabiliformazioni/"


def parse(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for table in soup.select("table#table-probabili-formazioni"):
        teams = [a.get_text(strip=True) for a in table.select("thead a")]
        if len(teams) != 2:
            continue
        body = table.find("tbody")
        info_tds = body.find_all("tr", recursive=False)[0].find_all("td", recursive=False)
        moduli = []
        for td in info_tds:
            txt = td.get_text(" ", strip=True)
            mod = re.search(r"Modulo:\s*([\d-]+)", txt)
            alle = re.search(r"All\.\s*(.+)$", txt)
            moduli.append((mod.group(1) if mod else "", alle.group(1).strip() if alle else ""))
        data_txt = body.find_all("tr", recursive=False)[1].get_text(" ", strip=True)
        halves = body.find_all("tr", recursive=False)[2].find_all("td", recursive=False)
        for team, (modulo, allenatore), half in zip(teams, moduli, halves):
            inner = half.find("table")
            for tr in inner.find_all("tr"):
                a = tr.find("a")
                ruolo_td = tr.find("td", class_="ruolo-calciatore")
                if a and ruolo_td:
                    rows.append(_row(a, ruolo_td.get_text(strip=True), team, modulo, allenatore, 1, data_txt))
            panchina = half.find(string=re.compile(r"Panchina"))
            if panchina:
                cell = panchina.find_parent("tr")
                for a in cell.find_all("a") if cell else []:
                    m = re.match(r"\((P|D|C|A)\)\s*(.+)", a.get_text(" ", strip=True))
                    if m:
                        rows.append(_row(a, m.group(1), team, modulo, allenatore, 0, data_txt, m.group(2)))
    return pd.DataFrame(rows)


def _row(a, ruolo, team, modulo, allenatore, titolare, data_txt, nome=None) -> dict:
    nome = nome or a.get_text(strip=True)
    pid = re.search(r"/seriea/(\d+)/", a.get("href", ""))
    return {
        "id": pid.group(1) if pid else "",
        "nome": nome,
        "chiave": norm_name(nome),
        "ruolo": ruolo,
        "squadra": team,
        "modulo": modulo,
        "allenatore": allenatore,
        "titolare": titolare,
        "giornata_testo": data_txt,
    }


def main() -> None:
    ensure_dirs()
    df = parse(fetch(URL, "probabili_formazioni", max_age_hours=6))
    out = DATA_DIR / "titolari.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    n_teams = df["squadra"].nunique()
    print(f"scritto {out}: {int(df['titolare'].sum())} titolari, {n_teams} squadre")
    if n_teams < 20:
        print("ATTENZIONE: meno di 20 squadre, la pagina probabili formazioni è parziale")


if __name__ == "__main__":
    main()
