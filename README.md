# FantaSkill

Skill per [Claude Code](https://claude.com/claude-code) che prepara l'asta del fantacalcio (Serie A, lega Classic P/D/C/A)
partendo da dati reali e produce un Excel da tenere aperto durante l'asta più un dossier con i consigli.

## Cosa fa

1. Scarica le statistiche per giocatore di due stagioni da fanta.soccer (media voto, fantamedia, gol, assist, rigori, cartellini).
2. Ricava i titolari dalle probabili formazioni e le partite iniziate da titolare dalle schede giocatore.
3. Legge i rigoristi e i battitori di calci piazzati da fantacalcio.it.
4. Incrocia infortunati e squalificati (fanta.soccer) con tipo di infortunio e data di rientro (transfermarkt, fantacalcio.it).
5. Prende i gol subiti per squadra dalla classifica transfermarkt, l'età dalle schede giocatore, nome completo e soprannome (opzionale, Wikipedia).
6. Genera `output/asta.xlsx` con:
   - **Giocatori**: tutti i calciatori, ordinati per ruolo e nome, con stagione corrente e precedente affiancate, età, titolarità, rigorista, indisponibilità e rientro. Colonna `venduto` con spunta da menu a tendina: la riga si barra in tutti i fogli.
   - **Portieri, Difensori, Centrocampisti, Attaccanti**: shortlist per ruolo secondo i criteri di `config.json`, in tre blocchi (obiettivi, lista principale, titolari di squadre minori).
   - **Obiettivi, Indisponibili, Rigoristi, Legenda**.
7. Claude scrive `output/dossier.md` con portiere, punte, centrocampisti e difensori consigliati, prezzi indicativi e ripartizione del budget.

## Requisiti

- Python 3.11+ con `pip install -r .claude/skills/fanta-asta/requirements.txt` (requests, beautifulsoup4, lxml, pandas, openpyxl)
- Claude Code, per usare la skill in modo conversazionale (facoltativo: gli script funzionano anche da soli)

## Uso

Con Claude Code, dalla cartella del repo:

```
preparami l'asta del fantacalcio
```

Oppure a mano, dalla cartella `.claude/skills/fanta-asta/scripts`:

```
python run_all.py                  # tutto (le età richiedono ~4 minuti la prima volta)
python run_all.py --no-anagrafica  # giro veloce senza età
python run_all.py --fresh          # ignora la cache HTML (valida 6-12 ore)
python run_all.py --soprannomi     # aggiunge nome completo e soprannome (Wikipedia, ~10 minuti)
```

Su Windows con console cp1252 anteporre `PYTHONIOENCODING=utf-8`.

## Configurazione

Tutti i criteri stanno in `.claude/skills/fanta-asta/config.json`:

| Chiave | Significato |
|---|---|
| `stagione_corrente`, `stagione_precedente` | stagioni da confrontare |
| `budget`, `ripartizione_budget`, `strategia` | crediti totali, quota per ruolo, una frase che guida il dossier |
| `obiettivi`, `obiettivi_squadra` | giocatori fissi da prendere (per nome) o per squadra e ruolo |
| `squadre_evidenziate` | i titolari di queste squadre sono evidenziati in giallo |
| `squadre_offensive`, `boost_centrocampo` | bonus nel punteggio per attaccanti e centrocampisti di queste squadre |
| `shortlist`, `extra_squadre_minori`, `squadre_grandi` | lunghezza delle liste e blocco aggiuntivo di titolari di squadre minori |
| `soglie` | media voto minima difensori, gol minimi attaccanti, età preferita, presenze minime portieri |
| `prezzi` | intervallo di crediti per fascia (Top, Semi-top, Medio, Scommessa) e ruolo |

## Struttura

```
.claude/skills/fanta-asta/
  SKILL.md              istruzioni per Claude
  config.json           criteri della lega e dell'utente
  requirements.txt
  scripts/
    run_all.py          pipeline completa
    fetch_stats.py      statistiche per stagione (fanta.soccer)
    fetch_classifica.py gol fatti/subiti per squadra (transfermarkt)
    fetch_titolari.py   probabili formazioni (fanta.soccer)
    fetch_titolarita.py partite da titolare (schede fanta.soccer)
    fetch_rigoristi.py  rigoristi e piazzati (fantacalcio.it)
    fetch_indisponibili.py  infortunati e squalificati con rientro
    fetch_anagrafica.py età e data di nascita
    fetch_soprannomi.py nome completo e soprannome (Wikipedia)
    build_excel.py      unione dei dati, punteggio, Excel e shortlist
    common.py           download con cache, normalizzazione nomi
data/                   CSV generati (la cache HTML in data/cache non è versionata)
output/                 asta.xlsx, shortlist.csv, dossier.md
```

## Note sulle fonti

- Nell'URL delle statistiche fanta.soccer l'ultimo numero è la giornata: per una stagione chiusa serve `fs/38`.
- La statistica "Gol Subiti" di fanta.soccer è vuota: i gol subiti vengono dalla classifica.
- fanta.soccer non riporta la durata degli infortuni: la data di rientro viene da transfermarkt e fantacalcio.it.
- I nomi differiscono tra le fonti: l'abbinamento è per cognome normalizzato e squadra.
- Chi non ha ancora presenze nella stagione corrente non compare nelle statistiche e resta solo nel foglio Indisponibili.

Il punteggio serve a ordinare i giocatori, non a fissare il prezzo: il prezzo indicativo deriva dalla fascia configurata.
