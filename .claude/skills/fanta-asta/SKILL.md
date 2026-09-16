---
name: fanta-asta
description: Use when the user wants to prepare a fantacalcio (Serie A fantasy football) auction - asta, listone, shortlist, rigoristi, infortunati, titolari, fantamedia comparisons, or an Excel/dossier of players to buy.
---

# Fanta Asta

Prepara l'asta del fantacalcio (lega Classic P/D/C/A) partendo da dati reali: statistiche di due stagioni
da fanta.soccer, titolari dalle probabili formazioni, rigoristi da fantacalcio.it, indisponibili con
tempi di rientro, età, gol subiti per squadra. Gli script producono `output/asta.xlsx` e
`output/shortlist.csv`; tu scrivi `output/dossier.md` con le scelte. `data/` e `output/` stanno nella
**radice del repo** (tre livelli sopra questa cartella), non nella cartella della skill.

**Principio:** i numeri li fanno gli script, i giudizi li fai tu leggendo l'Excel. Non stimare statistiche a memoria.

## Flusso

1. **Criteri della lega** – apri `config.json` (in questa cartella) e allinealo a ciò che chiede l'utente:
   `obiettivi` (giocatori fissi, con `ruolo` e opzionale `squadra`/`nota`), `obiettivi_squadra`
   (es. tutti i difensori titolari del Como), `squadre_evidenziate`, `squadre_offensive`,
   `boost_centrocampo`, `shortlist` (quanti nomi per ruolo), `extra_squadre_minori` (titolari in più
   per D/C/A presi fuori da `squadre_grandi`), `soglie`, `prezzi`, `budget`, `ripartizione_budget` e
   `strategia` (una frase: finisce nel foglio Legenda e guida il dossier).
   Ogni richiesta del tipo "metti X fra quelli da prendere" va in `obiettivi`, non nel dossier a mano.
   Se l'utente non dà criteri nuovi, usa il config così com'è e riassumi nel dossier i criteri attivi.
2. **Raccolta dati** – dalla cartella `scripts/`:
   ```
   pip install -r ../requirements.txt
   python run_all.py                  # completo (le età richiedono ~4 min la prima volta)
   python run_all.py --no-anagrafica  # giro veloce senza età
   python run_all.py --fresh          # ignora la cache HTML (data/cache, valida 6-12 h)
   python run_all.py --soprannomi     # aggiunge nome completo e soprannome (Wikipedia, ~20 min)
   ```
   Su Windows lancia con `PYTHONIOENCODING=utf-8` se la console è cp1252.
3. **Controlla l'output di build_excel.py** prima di leggere l'Excel:
   - `giornate giocate=N` (riga di fetch_stats) deve essere il numero di giornate già disputate;
     `fs=N+1` è normale a metà settimana (il sito accetta la giornata in programma).
   - `ATTENZIONE obiettivi non trovati` → nome scritto diversamente su fanta.soccer (cerca in
     `data/stats_<stagione>.csv`, colonna `nome`, e correggi `config.json`).
   - `meno di 20 squadre` nei titolari → una squadra non ha la probabile formazione; per lei
     `titolare_fonte` = "stima da presenze". Dillo nel dossier.
   - `con età: N` basso → anagrafica non completata, rilancia `fetch_anagrafica.py`.
4. **Leggi** `output/shortlist.csv` (tutte le liste) e, se serve, i fogli di `asta.xlsx`
   (Giocatori, Portieri, Difensori, Centrocampisti, Attaccanti, Obiettivi, Indisponibili, Rigoristi, Legenda).
5. **Scrivi `output/dossier.md`** con questa struttura, in italiano:
   - data dei dati e giornata; limiti noti (squadre stimate, obiettivi non trovati)
   - **Portiere**: 1 titolare + riserva, gol subiti a partita della squadra scorso anno
   - **Attaccanti**: le punte da ≥10 gol (scorso anno o proiezione), chi ha cambiato squadra, quinta punta
   - **Centrocampisti**: obiettivi, chi fa assist, il "bomber" (segna o tira rigori), Roma/Como
   - **Difensori**: titolari con MV ≥ 6, rigoristi/piazzati in cima, difensori Como
   - usa `da_titolare`/`pct_titolare` per distinguere il titolare fisso da chi lo è solo nelle probabili di
     questa settimana; per la stagione scorsa il riferimento è `presenze_prev`
   - il foglio Giocatori è ordinato per ruolo e nome e ha la colonna `venduto` (spunta da menu a tendina
     durante l'asta); gli altri fogli la leggono via formula sull'id e barrano la riga. Non toccare la
     colonna `id` nascosta: è la chiave delle formule
   - i fogli D/C/A hanno tre blocchi separati da una riga vuota: obiettivi, lista principale,
     "SQUADRE MINORI (titolari)"; nel dossier tieni la stessa separazione (colonna `blocco` in shortlist.csv)
   - per ogni nome: squadra, età, fascia, prezzo indicativo, un motivo in una riga, rischio (indisponibilità)
   - un obiettivo del config non titolare resta in lista: segnala il rischio panchina, non toglierlo
   - **Budget**: usa `ripartizione_budget` del config (già calcolata nel foglio Legenda) e fissa il tetto
     per i 3-4 nomi chiave dentro il loro `prezzo_indicativo`
   - **Da evitare**: colonna `stop_lungo` = sì (rientro oltre 30 giorni, o nota con crociato/mesi/operazione;
     questi partono già spuntati come venduti nell'Excel) e over 32 in fascia Top/Semi-top
   - se `asta.xlsx` è aperto in Excel lo script scrive `asta.new.xlsx`: chiedi di chiudere il file e rilancia
6. Riporta all'utente il percorso dell'Excel e del dossier e gli avvisi del punto 3.

## Fonti e insidie (verificate)

| Cosa | Fonte | Nota |
|------|-------|------|
| Statistiche | `fanta.soccer/it/statistiche/A/<stagione>/Tutti/<Stat>/Full/fs/<giornata>/` | l'ultimo numero è la giornata: per la stagione scorsa serve `fs/38`, non `fs/4`. Ruolo sempre `Tutti` (con `Portiere` la tabella è vuota). Oltre la giornata in corso la tabella è vuota: `detect_giornata` fa ricerca binaria |
| Gol subiti portieri | classifica transfermarkt (`fetch_classifica.py`) | la stat "Gol Subiti" di fanta.soccer è 0 per tutti |
| Titolari | fanta.soccer probabili formazioni | pubblicate a ridosso della giornata; squadre mancanti → stima da presenze |
| Rigoristi | `fantacalcio.it/rigoristi-serie-a` | fanta.soccer non ha la pagina |
| Indisponibili | fanta.soccer (chi) + transfermarkt (data rientro) + fantacalcio.it (nota) | fanta.soccer non riporta la durata |
| Età | schede giocatore fanta.soccer | cache permanente in `data/anagrafica.csv` |
| Titolarità stagione corrente | schede giocatore, sezione "Partite disputate" (`fetch_titolarita.py`) | IN=1 entrato dalla panchina; card con MV "-" e nessun evento = non ha giocato. Solo stagione corrente: le precedenti richiedono un postback |
| Soprannomi | Wikipedia IT via API (`fetch_soprannomi.py`) | limite ~1 richiesta/1.5 s, 429 frequenti; copertura parziale; "detto X" solo tra virgolette (altrimenti cattura i nomi dei club) |
| Marcatori | usa "Gol Segnati" fanta.soccer | `calcio.com/statistiche/.../marcatori` è protetto da verifica accesso: non scaricabile |

- I nomi differiscono tra fonti: il match è per cognome normalizzato + squadra (`common.norm_name`, `norm_team`).
  "Como 1907" e "Como" sono la stessa squadra. Un obiettivo non abbinato va cercato per nome nel CSV, non indovinato.
- Chi non ha ancora presenze nella stagione corrente (infortunato da agosto) non è nelle statistiche:
  compare solo nel foglio Indisponibili.
- Il `punteggio` ordina, non prezza: il prezzo indicativo viene dalla `fascia` (config `prezzi`).
- Nei CSV le celle vuote diventano NaN in pandas: filtra con `.fillna("")` prima di confrontare con `""`.
- Ricalcolare da zero significa `--fresh`; senza, la cache HTML evita richieste inutili ai siti.
