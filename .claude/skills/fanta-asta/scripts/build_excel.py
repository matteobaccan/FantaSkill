"""Unisce i CSV di data/ in output/asta.xlsx e output/shortlist.csv.

Fogli: Giocatori, Portieri, Difensori, Centrocampisti, Attaccanti, Obiettivi, Indisponibili,
       Rigoristi, Legenda.
Il punteggio è trasparente (vedi foglio Legenda) e serve a ordinare, non a fissare prezzi:
il prezzo indicativo deriva dalla fascia (config.json -> prezzi).
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from common import DATA_DIR, OUTPUT_DIR, ensure_dirs, load_config, norm_name, norm_team, strip_accents

FILL_EVIDENZA = PatternFill("solid", fgColor="FFF2CC")   # titolari delle squadre evidenziate
FILL_OBIETTIVO = PatternFill("solid", fgColor="C6EFCE")  # obiettivi da config
FILL_INDISP = PatternFill("solid", fgColor="F8CBAD")     # indisponibili
FONT_HEAD = Font(bold=True, color="FFFFFF")
FILL_HEAD = PatternFill("solid", fgColor="305496")
FONT_VENDUTO = Font(strike=True, color="808080")
SPUNTA = "✔"
SHEET_GIOCATORI = "Giocatori"

ROLE_ORDER = {"P": 0, "D": 1, "C": 2, "A": 3}
ROLE_NAME = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}


# ----------------------------------------------------------------------------- caricamento
def load_all(cfg: dict) -> dict[str, pd.DataFrame]:
    cur = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_corrente']}.csv", dtype={"id": str})
    prev = pd.read_csv(DATA_DIR / f"stats_{cfg['stagione_precedente']}.csv", dtype={"id": str})
    tit = pd.read_csv(DATA_DIR / "titolari.csv", dtype={"id": str})
    rig = pd.read_csv(DATA_DIR / "rigoristi.csv")
    ind = pd.read_csv(DATA_DIR / "indisponibili.csv").fillna("")
    ana_path = DATA_DIR / "anagrafica.csv"
    ana = pd.read_csv(ana_path, dtype={"id": str}) if ana_path.exists() else pd.DataFrame(columns=["id", "eta", "nato_il"])
    cla = {}
    for k, season in (("cur", cfg["stagione_corrente"]), ("prev", cfg["stagione_precedente"])):
        path = DATA_DIR / f"classifica_{season}.csv"
        cla[k] = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["squadra_n", "pg", "gf", "gs", "gs_partita"])
    tp = DATA_DIR / "titolarita.csv"
    titolarita = pd.read_csv(tp, dtype={"id": str}) if tp.exists() else pd.DataFrame(columns=["id", "da_titolare", "subentrato", "sostituito", "pct_titolare"])
    sp = DATA_DIR / "soprannomi.csv"
    sopr = pd.read_csv(sp, dtype={"id": str}).fillna("") if sp.exists() else pd.DataFrame(columns=["id", "nome_completo", "soprannome"])
    return {"cur": cur, "prev": prev, "tit": tit, "rig": rig, "ind": ind, "ana": ana, "cla": cla, "titolarita": titolarita, "sopr": sopr}


def merge_seasons(cur: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
    stat_cols = ["mv", "fm", "presenze", "gol", "assist", "rig_segnati", "rig_sbagliati", "gol_subiti", "rig_parati", "ammonizioni", "espulsioni"]
    p = prev[["id", "chiave", "squadra"] + stat_cols].rename(columns={c: f"{c}_prev" for c in stat_cols}).rename(columns={"squadra": "squadra_prev"})
    # 1) stesso id fanta.soccer (match sicuro)
    df = cur.merge(p, on="id", how="left", suffixes=("", "_dup"))
    df = df.drop(columns=[c for c in df.columns if c.endswith("_dup")])
    # 2) fallback per chiave+squadra sui non abbinati (id mancante)
    missing = df["fm_prev"].isna() & (df["id"] == "")
    if missing.any():
        p2 = p.drop(columns=["id"]).drop_duplicates(["chiave", "squadra_prev"])
        fb = df.loc[missing, ["chiave", "squadra"]].merge(p2, left_on=["chiave", "squadra"], right_on=["chiave", "squadra_prev"], how="left")
        for c in p2.columns:
            if c != "chiave":
                df.loc[missing, c] = fb[c].values
    df["cambiato_squadra"] = (df["squadra_prev"].notna() & (df["squadra_prev"].fillna("").map(norm_team) != df["squadra"].map(norm_team))).astype(int)
    df["delta_fm"] = (df["fm"] - df["fm_prev"]).round(2)
    return df


def add_titolari(df: pd.DataFrame, tit: pd.DataFrame, giornata: int) -> pd.DataFrame:
    t = tit[tit["titolare"] == 1][["chiave", "squadra", "modulo"]].drop_duplicates(["chiave", "squadra"])
    t["squadra_n"] = t["squadra"].map(norm_team)
    df["squadra_n"] = df["squadra"].map(norm_team)
    df = df.merge(t[["chiave", "squadra_n", "modulo"]].assign(titolare_prob=1), on=["chiave", "squadra_n"], how="left")
    teams_with_lineup = set(t["squadra_n"])
    df["titolare_prob"] = df["titolare_prob"].fillna(0).astype(int)
    # fallback: squadra senza probabile formazione -> titolare chi ha giocato quasi tutte le partite
    played = df.groupby("squadra_n")["presenze"].transform("max")
    base = df["da_titolare"] if "da_titolare" in df and df["da_titolare"].notna().any() else df["presenze"]
    stima = (~df["squadra_n"].isin(teams_with_lineup)) & (base.fillna(0) >= (played - 1).clip(lower=1))
    df["titolare"] = ((df["titolare_prob"] == 1) | stima).astype(int)
    df["titolare_fonte"] = ""
    df.loc[df["titolare_prob"] == 1, "titolare_fonte"] = "probabili formazioni"
    df.loc[stima, "titolare_fonte"] = "stima da presenze"
    return df


def add_rigoristi(df: pd.DataFrame, rig: pd.DataFrame) -> pd.DataFrame:
    rig = rig.assign(squadra_n=rig["squadra"].map(norm_team))
    for tipo, col in (("rigori", "rigorista"), ("piazzati", "piazzati")):
        r = rig[rig["tipo"] == tipo][["chiave", "squadra_n", "ordine"]].drop_duplicates(["chiave", "squadra_n"]).rename(columns={"ordine": col})
        df = df.merge(r, on=["chiave", "squadra_n"], how="left")
        df[col] = df[col].fillna(0).astype(int)
    return df


def add_indisponibili(df: pd.DataFrame, ind: pd.DataFrame) -> pd.DataFrame:
    i = ind.assign(squadra_n=ind["squadra"].map(norm_team))
    i = i[["chiave", "squadra_n", "tipo", "infortunio", "rientro_data", "rientro_nota"]].drop_duplicates(["chiave", "squadra_n"])
    i = i.rename(columns={"tipo": "indisponibile"})
    df = df.merge(i, on=["chiave", "squadra_n"], how="left")
    for c in ("indisponibile", "infortunio", "rientro_data", "rientro_nota"):
        df[c] = df[c].fillna("")
    df["giorni_stop"] = df["rientro_data"].map(_days_to)
    lungo_txt = df["rientro_nota"].str.contains(STOP_LUNGO_RE, case=False, regex=True)
    df["stop_lungo"] = (((df["giorni_stop"] > 30) | (df["giorni_stop"].isna() & lungo_txt)) & (df["indisponibile"] != "")).map({True: "sì", False: ""})
    return df


# testo che indica uno stop lungo quando manca la data di rientro
STOP_LUNGO_RE = r"crociato|mesi|lungo|ottobre|novembre|dicembre|gennaio|febbraio|marzo|aprile|maggio|fine stagione|operat"


def _days_to(s: str):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    if not m:
        return None
    d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return (d - dt.date.today()).days


def add_classifica(df: pd.DataFrame, cla: dict) -> pd.DataFrame:
    """Gol subiti della squadra (stagione corrente) e della squadra dell'anno scorso (stagione precedente)."""
    cur = cla["cur"][["squadra_n", "gs", "pg", "gs_partita"]].rename(columns={"gs": "gs_squadra", "pg": "pg_squadra", "gs_partita": "gs_partita_squadra"})
    df = df.merge(cur, on="squadra_n", how="left")
    prev = cla["prev"][["squadra_n", "gs", "pg", "gs_partita"]].rename(columns={"squadra_n": "squadra_prev_n", "gs": "gs_squadra_prev", "pg": "pg_squadra_prev", "gs_partita": "gs_partita_squadra_prev"})
    df["squadra_prev_n"] = df["squadra_prev"].fillna(df["squadra"]).map(norm_team)
    df = df.merge(prev, on="squadra_prev_n", how="left").drop(columns="squadra_prev_n")
    return df


def add_titolarita(df: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    """Partite da titolare nella stagione corrente (dalle schede giocatore)."""
    cols = ["id", "da_titolare", "subentrato", "sostituito", "pct_titolare"]
    if t.empty:
        for c in cols[1:]:
            df[c] = None
        return df
    return df.merge(t[cols].drop_duplicates("id"), on="id", how="left")


def add_soprannomi(df: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    if s.empty:
        df["nome_completo"] = ""
        df["soprannome"] = ""
        return df
    df = df.merge(s[["id", "nome_completo", "soprannome"]].drop_duplicates("id"), on="id", how="left")
    df["nome_completo"] = df["nome_completo"].fillna("")
    df["soprannome"] = df["soprannome"].fillna("")
    return df


def add_anagrafica(df: pd.DataFrame, ana: pd.DataFrame) -> pd.DataFrame:
    if ana.empty:
        df["eta"] = None
        df["nato_il"] = ""
        return df
    return df.merge(ana[["id", "eta", "nato_il"]].drop_duplicates("id"), on="id", how="left")


def add_obiettivi(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df["obiettivo"] = ""
    for o in cfg.get("obiettivi", []):
        k = norm_name(o["nome"])
        mask = (df["chiave"] == k) & (df["ruolo"] == o.get("ruolo", df["ruolo"]))
        if o.get("squadra"):
            mask &= df["squadra_n"] == norm_team(o["squadra"])
        df.loc[mask, "obiettivo"] = o.get("nota", "obiettivo")
    for o in cfg.get("obiettivi_squadra", []):
        mask = (df["squadra_n"] == norm_team(o["squadra"])) & (df["ruolo"] == o["ruolo"])
        if o.get("solo_titolari"):
            mask &= df["titolare"] == 1
        df.loc[mask & (df["obiettivo"] == ""), "obiettivo"] = o.get("nota", "obiettivo")
    return df


# ----------------------------------------------------------------------------- punteggio
def add_score(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    s = cfg["soglie"]
    off = {norm_team(t) for t in cfg["squadre_offensive"]}
    boost_c = {norm_team(t) for t in cfg["boost_centrocampo"]}
    pc = df["presenze"].fillna(0)
    pp = df["presenze_prev"].fillna(0)
    fmc = df["fm"].fillna(0)
    fmp = df["fm_prev"].fillna(0)
    peso_cur = 3.0  # la stagione in corso pesa il triplo per partita: è la forma attuale
    df["fm_ponderata"] = ((fmp * pp + fmc * pc * peso_cur) / (pp + pc * peso_cur).replace(0, pd.NA)).astype(float).round(2)
    bonus = pd.Series(0.0, index=df.index)
    bonus += 0.5 * df["titolare"]
    bonus += df["rigorista"].map({1: 0.5, 2: 0.2}).fillna(0)
    bonus += 0.1 * (df["piazzati"] == 1)
    bonus += 0.3 * (df["squadra_n"].isin(off) & df["ruolo"].isin(["C", "A"]))
    bonus += 0.3 * (df["squadra_n"].isin(boost_c) & (df["ruolo"] == "C"))
    eta = df["eta"]
    bonus += 0.2 * (eta <= s["eta_max_preferita"]).fillna(False)
    bonus -= 0.3 * (eta >= 32).fillna(False)
    giorni = df["giorni_stop"]
    bonus -= 0.5 * (df["stop_lungo"] == "sì")
    bonus -= 0.2 * (df["indisponibile"] != "")
    bonus -= 0.3 * (pp.between(1, 10) & (pc <= 1))  # poco impiegato: rischio panchina
    df["bonus"] = bonus.round(2)
    df["punteggio"] = (df["fm_ponderata"].fillna(0) + df["bonus"]).round(2)
    return df


def add_fascia_prezzo(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df["fascia"] = ""
    df["prezzo_indicativo"] = ""
    prezzi = cfg["prezzi"]
    for ruolo, g in df.groupby("ruolo"):
        g = g.sort_values("punteggio", ascending=False)
        n = len(g)
        cut = [int(n * 0.06), int(n * 0.16), int(n * 0.35)]
        for pos, idx in enumerate(g.index):
            f = "Top" if pos < cut[0] else "Semi-top" if pos < cut[1] else "Medio" if pos < cut[2] else "Scommessa"
            lo, hi = prezzi[ruolo][f]
            df.at[idx, "fascia"] = f
            df.at[idx, "prezzo_indicativo"] = f"{lo}-{hi}"
    return df


# ----------------------------------------------------------------------------- shortlist
def shortlist(df: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s = cfg["soglie"]
    n = cfg["shortlist"]
    gws = cfg["giornate_stagione"]
    out = {}

    p = df[(df["ruolo"] == "P") & (df["presenze_prev"] >= s["presenze_min_portiere"])].copy()
    p = p.sort_values(["gs_partita_squadra_prev", "punteggio"], ascending=[True, False])
    out["P"] = p

    d = df[(df["ruolo"] == "D") & (df["titolare"] == 1) & ((df["mv_prev"] >= s["mv_min_difensori"]) | (df["mv"] >= s["mv_min_difensori"]))].copy()
    d["ordine_rig"] = d["rigorista"].replace(0, 9)
    d = d.sort_values(["obiettivo", "ordine_rig", "punteggio"], ascending=[False, True, False]).drop(columns="ordine_rig")
    out["D"] = d

    c = df[(df["ruolo"] == "C") & ((df["titolare"] == 1) | (df["obiettivo"] != ""))].copy()
    c["assist_tot"] = c["assist_prev"].fillna(0) + c["assist"].fillna(0)
    c["bomber"] = ((c["gol_prev"].fillna(0) >= s["gol_min_centrocampista_bomber"]) | (c["rigorista"].between(1, 2))).map({True: "sì", False: ""})
    c = c.sort_values(["obiettivo", "assist_tot", "punteggio"], ascending=[False, False, False])
    out["C"] = c

    a = df[df["ruolo"] == "A"].copy()
    a["gol_proiettati"] = (a["gol"] / a["presenze"].replace(0, pd.NA) * gws).astype(float).round(1)
    a["gol_tot_prev"] = a["gol_prev"].fillna(0)
    giornata = int(df["giornate_giocate"].max()) if "giornate_giocate" in df else int(df["presenze"].max())
    campione_ok = a["presenze"] >= max(3, giornata - 1)
    keep = (a["gol_tot_prev"] >= s["gol_min_attaccanti"]) | ((a["gol_proiettati"] >= s["gol_min_attaccanti"]) & campione_ok) | (a["obiettivo"] != "")
    a = a[keep].sort_values(["obiettivo", "gol_tot_prev", "punteggio"], ascending=[False, False, False])
    out["A"] = a

    # taglio alla lunghezza richiesta (gli obiettivi sono già in testa)
    out = {r: g.head(n[r]) for r, g in out.items()}
    # blocco aggiuntivo: titolari di squadre minori non già in lista
    grandi = {norm_team(t) for t in cfg.get("squadre_grandi", [])}
    for r, k in cfg.get("extra_squadre_minori", {}).items():
        base = df[(df["ruolo"] == r) & (df["titolare"] == 1) & (~df["squadra_n"].isin(grandi)) & (~df["chiave"].isin(out[r]["chiave"]))].copy()
        if r == "C":
            base["assist_tot"] = base["assist_prev"].fillna(0) + base["assist"].fillna(0)
            base["bomber"] = ((base["gol_prev"].fillna(0) >= s["gol_min_centrocampista_bomber"]) | (base["rigorista"].between(1, 2))).map({True: "sì", False: ""})
        if r == "A":
            base["gol_proiettati"] = (base["gol"] / base["presenze"].replace(0, pd.NA) * gws).astype(float).round(1)
            base["gol_tot_prev"] = base["gol_prev"].fillna(0)
        base = base.sort_values("punteggio", ascending=False).head(int(k))
        base["blocco"] = "squadre minori"
        out[r] = pd.concat([out[r].assign(blocco="principale"), base], ignore_index=True)
    for r in out:
        if "blocco" not in out[r]:
            out[r] = out[r].assign(blocco="principale")
    return out


def with_separators(g: pd.DataFrame) -> pd.DataFrame:
    """Riga vuota dopo gli obiettivi e prima del blocco squadre minori (con etichetta)."""
    blank = pd.DataFrame([{c: None for c in g.columns}])
    parts = []
    ob = g[(g["blocco"] == "principale") & (g["obiettivo"].fillna("") != "")]
    rest = g[(g["blocco"] == "principale") & (g["obiettivo"].fillna("") == "")]
    minori = g[g["blocco"] == "squadre minori"]
    if len(ob):
        parts += [ob, blank]
    parts.append(rest)
    if len(minori):
        label = blank.copy()
        label["nome"] = "SQUADRE MINORI (titolari)"
        parts += [blank, label, minori]
    return pd.concat(parts, ignore_index=True)


# ----------------------------------------------------------------------------- excel
COLS_MAIN = ["nome", "soprannome", "nome_completo", "ruolo", "squadra", "eta", "titolare", "da_titolare", "pct_titolare", "presenze", "gol", "assist", "presenze_prev", "gol_prev", "assist_prev",
             "titolare_fonte", "obiettivo", "fascia", "prezzo_indicativo", "punteggio",
             "fm", "mv", "rig_segnati", "fm_prev", "mv_prev", "rig_segnati_prev", "delta_fm", "fm_ponderata", "bonus", "squadra_prev", "cambiato_squadra", "rigorista", "piazzati",
             "indisponibile", "infortunio", "rientro_data", "giorni_stop", "stop_lungo", "rientro_nota", "gs_partita_squadra", "gs_partita_squadra_prev",
             "rig_parati_prev", "ammonizioni_prev", "espulsioni_prev", "id"]


def write_sheet(writer, name: str, df: pd.DataFrame, cfg: dict, cols: list[str] | None = None) -> None:
    """Scrive un foglio giocatori. Prima colonna 'venduto': nel foglio Giocatori è una spunta da menu a
    tendina; negli altri fogli è una formula che legge la spunta dal foglio Giocatori tramite l'id.
    Le righe con venduto non vuoto vengono barrate (formattazione condizionale)."""
    cols = [c for c in (cols or COLS_MAIN) if c in df.columns and c != "id"] + ["id"]
    df = df[cols].copy()
    # gli indisponibili con stop lungo partono già spuntati come venduti (fuori dall'asta)
    prevenduti = (df["stop_lungo"] == "sì") if (name == SHEET_GIOCATORI and "stop_lungo" in df) else pd.Series(False, index=df.index)
    df.insert(0, "venduto", prevenduti.map({True: SPUNTA, False: ""}))
    cols = ["venduto"] + cols
    df.to_excel(writer, sheet_name=name, index=False)
    ws = writer.sheets[name]
    ev = {norm_team(t) for t in cfg["squadre_evidenziate"]}
    ci = {c: i + 1 for i, c in enumerate(cols)}
    n = len(df) + 1
    last_col = get_column_letter(len(cols))
    id_col = get_column_letter(ci["id"])
    if name == SHEET_GIOCATORI:
        dv = DataValidation(type="list", formula1=f'"{SPUNTA}"', allow_blank=True, showDropDown=False)
        ws.add_data_validation(dv)
        dv.add(f"A2:A{n}")
        ws.column_dimensions["A"].width = 9
    else:
        g_id = writer.sheets[SHEET_GIOCATORI]._fanta_id_col
        for r in range(2, n + 1):
            ws.cell(row=r, column=1).value = (
                f'=IF(${id_col}{r}="","",IFERROR(INDEX({SHEET_GIOCATORI}!$A:$A,'
                f'MATCH(${id_col}{r},{SHEET_GIOCATORI}!${g_id}:${g_id},0)),""))'
            )
        ws.column_dimensions["A"].width = 9
    ws.conditional_formatting.add(f"A2:{last_col}{n}", FormulaRule(formula=['$A2<>""'], font=FONT_VENDUTO))
    ws._fanta_id_col = id_col
    ws.column_dimensions[id_col].hidden = True
    for cell in ws[1]:
        cell.font, cell.fill = FONT_HEAD, FILL_HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r, (_, row) in enumerate(df.iterrows(), start=2):
        fill = None
        if pd.isna(row.get("ruolo", None)) and pd.isna(row.get("squadra", None)):
            continue  # riga separatrice
        if row.get("indisponibile"):
            fill = FILL_INDISP
        elif row.get("obiettivo"):
            fill = FILL_OBIETTIVO
        elif row.get("titolare") == 1 and norm_team(str(row.get("squadra", ""))) in ev:
            fill = FILL_EVIDENZA
        if fill:
            for c in range(1, len(cols) + 1):
                ws.cell(row=r, column=c).fill = fill
        if row.get("obiettivo") or str(row.get("nome", "")).startswith("SQUADRE MINORI"):
            ws.cell(row=r, column=ci["nome"]).font = Font(bold=True)
    for i, c in enumerate(cols, start=1):
        if c in ("venduto", "id"):
            continue
        width = 48 if c == "rientro_nota" else 22 if c in ("infortunio", "titolare_fonte", "obiettivo", "nome_completo") else max(8, min(16, len(c) + 2))
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions


def legenda(cfg: dict, giornata: int, n_tot: int) -> pd.DataFrame:
    s = cfg["soglie"]
    rows = [
        ("Generato il", dt.date.today().isoformat()),
        ("Stagione corrente / giornate giocate", f"{cfg['stagione_corrente']} / {giornata} (le statistiche fanta.soccer coprono le giornate disputate)"),
        ("Budget per ruolo", ", ".join(f"{r}: {int(cfg['budget'] * q)} crediti ({int(q * 100)}%)" for r, q in cfg["ripartizione_budget"].items())),
        ("stop_lungo", "sì se rientro oltre 30 giorni o, senza data, se la nota parla di crociato/mesi/operazione/mese lontano"),
        ("Stagione di confronto", f"{cfg['stagione_precedente']} (38 giornate)"),
        ("Giocatori totali", n_tot),
        ("Fonte statistiche", "fanta.soccer /it/statistiche (Media Voto, Fantamedia, Gol, Assist, Rigori, Gol subiti, cartellini)"),
        ("Fonte titolari", "fanta.soccer probabili formazioni; se una squadra non ha la formazione pubblicata -> stima da presenze (titolare_fonte)"),
        ("Fonte rigoristi", "fantacalcio.it/rigoristi-serie-a (rigorista = ordine nella gerarchia, 1 = primo tiratore)"),
        ("Fonte indisponibili", "fanta.soccer infortunati (chi) + transfermarkt (tipo e data rientro) + fantacalcio.it (nota testuale)"),
        ("Fonte età", "schede giocatore fanta.soccer"),
        ("da_titolare / pct_titolare", "partite iniziate dall'inizio nella stagione corrente (schede fanta.soccer, sezione Partite disputate) e quota sulle giornate giocate; "
                                       "per la stagione scorsa il riferimento resta presenze_prev"),
        ("soprannome / nome_completo", "nome completo dalla scheda fanta.soccer; soprannome cercato nella voce di Wikipedia italiana (copertura parziale)"),
        ("fm_ponderata", "media pesata di fantamedia: partite stagione corrente peso 3, partite stagione scorsa peso 1"),
        ("bonus", "+0.5 titolare, +0.5 rigorista 1° (+0.2 se 2°), +0.1 calci piazzati, +0.3 C/A di squadra offensiva, "
                  "+0.3 C di Roma/Como, +0.2 età <= %d, -0.3 età >= 32, -0.2 indisponibile, -0.5 stop lungo (>30 gg o crociato), "
                  "-0.3 poco impiegato" % s["eta_max_preferita"]),
        ("punteggio", "fm_ponderata + bonus: serve a ordinare, non è un prezzo"),
        ("fascia", "per ruolo, in base al rank del punteggio: Top 6%, Semi-top 16%, Medio 35%, resto Scommessa"),
        ("prezzo_indicativo", "intervallo di crediti per fascia (config.json -> prezzi, budget %d)" % cfg["budget"]),
        ("Colori", "giallo = titolare delle squadre evidenziate (%s); verde = obiettivo da config; rosso = indisponibile" % ", ".join(cfg["squadre_evidenziate"])),
        ("Foglio Portieri", "presenze scorso anno >= %d, ordinati per gol subiti a partita della squadra nel %s (fonte classifica transfermarkt: la statistica per portiere di fanta.soccer è vuota)" % (s["presenze_min_portiere"], cfg["stagione_precedente"])),
        ("Foglio Difensori", "titolari con media voto >= %.1f (scorsa o attuale), rigoristi in cima; max %d" % (s["mv_min_difensori"], cfg["shortlist"]["D"])),
        ("Foglio Centrocampisti", "titolari ordinati per punteggio e assist; 'bomber' = >= %d gol scorso anno o rigorista; max %d" % (s["gol_min_centrocampista_bomber"], cfg["shortlist"]["C"])),
        ("Foglio Attaccanti", ">= %d gol scorso anno, oppure proiezione su 38 giornate >= %d se ha giocato quasi tutte le partite; cambiato_squadra = 1 se ha cambiato club; max %d" % (s["gol_min_attaccanti"], s["gol_min_attaccanti"], cfg["shortlist"]["A"])),
        ("Foglio Centrocampisti (ordine)", "obiettivi in testa, poi assist totali (scorsa + attuale), poi punteggio"),
        ("Blocco SQUADRE MINORI", "in D/C/A, dopo una riga vuota: %s titolari di squadre fuori da [%s], non già in lista, per punteggio" % (
            "/".join(str(v) for v in cfg.get("extra_squadre_minori", {}).values()), ", ".join(cfg.get("squadre_grandi", [])))),
        ("Righe vuote nelle shortlist", "separano gli obiettivi dal resto della lista e la lista dal blocco squadre minori"),
        ("Colonna venduto", "nel foglio Giocatori (ordinato per ruolo e nome) scegli la spunta dal menu a tendina quando un giocatore viene venduto all'asta; "
                            "gli altri fogli la leggono via formula e la riga viene barrata ovunque. Gli infortunati con stop_lungo = sì partono già spuntati"),
        ("Strategia", cfg.get("strategia", "")),
        ("Limite noto", "i giocatori senza presenze nella stagione corrente (es. infortunati da inizio anno) non compaiono nelle statistiche fanta.soccer e sono elencati solo nel foglio Indisponibili"),
    ]
    return pd.DataFrame(rows, columns=["voce", "descrizione"])


def main() -> None:
    cfg = load_config()
    ensure_dirs()
    d = load_all(cfg)
    giornata = int(d["cur"]["giornate_giocate"].iloc[0]) if "giornate_giocate" in d["cur"] else int(d["cur"]["presenze"].max())
    df = merge_seasons(d["cur"], d["prev"])
    df = add_titolarita(df, d["titolarita"])
    df = add_titolari(df, d["tit"], giornata)
    df = add_rigoristi(df, d["rig"])
    df = add_indisponibili(df, d["ind"])
    df = add_classifica(df, d["cla"])
    df = add_anagrafica(df, d["ana"])
    df = add_soprannomi(df, d["sopr"])
    df = add_obiettivi(df, cfg)
    df = add_score(df, cfg)
    df = add_fascia_prezzo(df, cfg)
    df["_r"] = df["ruolo"].map(ROLE_ORDER)
    df["_n"] = df["nome"].map(lambda x: strip_accents(str(x)).lower())
    df = df.sort_values(["_r", "_n"]).drop(columns=["_r", "_n"]).reset_index(drop=True)

    sl = shortlist(df, cfg)
    out = OUTPUT_DIR / "asta.xlsx"
    try:
        out.open("ab").close()  # verifica che non sia aperto in Excel
    except PermissionError:
        out = OUTPUT_DIR / "asta.new.xlsx"
        print(f"ATTENZIONE: asta.xlsx è aperto in Excel, scrivo {out.name}. Chiudi Excel e rilancia per aggiornare asta.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        write_sheet(w, "Giocatori", df, cfg)
        write_sheet(w, "Portieri", sl["P"], cfg, ["nome", "soprannome", "squadra", "eta", "titolare", "da_titolare", "pct_titolare", "presenze", "presenze_prev", "squadra_prev", "gs_partita_squadra_prev", "gs_squadra_prev",
                                                   "gs_partita_squadra", "gs_squadra", "rig_parati_prev", "mv_prev", "fm_prev", "mv", "fm", "fascia", "prezzo_indicativo", "punteggio", "indisponibile", "rientro_data", "stop_lungo"])
        write_sheet(w, "Difensori", with_separators(sl["D"]), cfg, ["nome", "soprannome", "squadra", "eta", "titolare", "da_titolare", "pct_titolare", "presenze", "gol", "assist", "presenze_prev", "gol_prev", "assist_prev", "obiettivo", "rigorista", "piazzati",
                                                    "mv", "mv_prev", "fm", "fm_prev", "titolare_fonte", "fascia", "prezzo_indicativo", "punteggio", "indisponibile", "rientro_data", "stop_lungo"])
        write_sheet(w, "Centrocampisti", with_separators(sl["C"]), cfg, ["nome", "soprannome", "squadra", "eta", "titolare", "da_titolare", "pct_titolare", "presenze", "gol", "assist", "presenze_prev", "gol_prev", "assist_prev", "assist_tot", "obiettivo", "bomber",
                                                         "rigorista", "piazzati", "fm", "fm_prev", "mv", "mv_prev", "titolare_fonte", "fascia", "prezzo_indicativo", "punteggio", "indisponibile", "rientro_data", "stop_lungo"])
        write_sheet(w, "Attaccanti", with_separators(sl["A"]), cfg, ["nome", "soprannome", "squadra", "eta", "titolare", "da_titolare", "pct_titolare", "presenze", "gol", "assist", "presenze_prev", "gol_prev", "assist_prev", "gol_proiettati", "obiettivo", "squadra_prev",
                                                     "cambiato_squadra", "rigorista", "fm", "fm_prev", "fascia", "prezzo_indicativo", "punteggio", "indisponibile", "rientro_data", "stop_lungo"])
        write_sheet(w, "Obiettivi", df[df["obiettivo"] != ""], cfg)
        ind_cols = ["squadra", "nome", "ruolo", "tipo", "infortunio", "rientro_data", "rientro_nota", "fonti"]
        d["ind"][ind_cols].to_excel(w, sheet_name="Indisponibili", index=False)
        d["rig"].pivot_table(index="squadra", columns=["tipo", "ordine"], values="nome", aggfunc="first").to_excel(w, sheet_name="Rigoristi")
        legenda(cfg, giornata, len(df)).to_excel(w, sheet_name="Legenda", index=False)
        for name in ("Indisponibili", "Legenda"):
            ws = w.sheets[name]
            ws.column_dimensions["B"].width = 30
            ws.column_dimensions["G" if name == "Indisponibili" else "B"].width = 90
    pd.concat([g.assign(lista=ROLE_NAME[r]) for r, g in sl.items()])[["lista", "blocco"] + [c for c in COLS_MAIN if c != "id"]].to_csv(OUTPUT_DIR / "shortlist.csv", index=False, encoding="utf-8")
    df.to_csv(DATA_DIR / "giocatori_uniti.csv", index=False, encoding="utf-8")

    print(f"scritto {out}")
    print(f"giocatori: {len(df)} | con stagione scorsa: {int(df['fm_prev'].notna().sum())} | titolari: {int(df['titolare'].sum())} "
          f"(stimati: {int((df['titolare_fonte'] == 'stima da presenze').sum())}) | rigoristi 1°: {int((df['rigorista'] == 1).sum())} | "
          f"indisponibili: {int((df['indisponibile'] != '').sum())} | con età: {int(df['eta'].notna().sum())}")
    for r, g in sl.items():
        minori = g[g["blocco"] == "squadre minori"]
        print(f"  {ROLE_NAME[r]}: {int((g['blocco'] == 'principale').sum())} principali + {len(minori)} squadre minori -> {', '.join(g['nome'].head(6))}… | minori: {', '.join(minori['nome'].head(5))}…")
    obj = df[df["obiettivo"] != ""]["nome"].tolist()
    print(f"  obiettivi trovati: {obj}")
    wanted = [norm_name(o["nome"]) for o in cfg["obiettivi"]]
    missing = [o["nome"] for o in cfg["obiettivi"] if norm_name(o["nome"]) not in set(df.loc[df["obiettivo"] != "", "chiave"])]
    if missing:
        print(f"  ATTENZIONE obiettivi non trovati nei dati: {missing}")


if __name__ == "__main__":
    main()
