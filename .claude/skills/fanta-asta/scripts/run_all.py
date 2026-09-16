"""Esegue l'intera pipeline: statistiche (2 stagioni), titolari, rigoristi, indisponibili, anagrafica, Excel.

Uso: python run_all.py [--no-anagrafica] [--fresh] [--soprannomi]
  --fresh          ignora la cache HTML (ri-scarica tutto)
  --no-anagrafica  salta le schede giocatore (età): utile per un giro veloce
  --soprannomi     cerca anche nome completo e soprannome (Wikipedia, ~20 min)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from common import CACHE_DIR, load_config

HERE = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    print(f"\n=== {script} {' '.join(args)}")
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def main() -> None:
    cfg = load_config()
    if "--fresh" in sys.argv and CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.html"):
            if not f.name.startswith("player_"):  # le schede giocatore non cambiano
                f.unlink()
    run("fetch_stats.py", cfg["stagione_corrente"], str(cfg["giornata_corrente"]))
    run("fetch_stats.py", cfg["stagione_precedente"], str(cfg["giornate_stagione"]))
    run("fetch_classifica.py", cfg["stagione_corrente"])
    run("fetch_classifica.py", cfg["stagione_precedente"])
    run("fetch_titolari.py")
    run("fetch_rigoristi.py")
    run("fetch_indisponibili.py")
    if "--no-anagrafica" not in sys.argv:
        run("fetch_anagrafica.py")
    run("fetch_titolarita.py")
    if "--soprannomi" in sys.argv:  # lento (~20 min): Wikipedia limita le richieste
        run("fetch_soprannomi.py")
    run("build_excel.py")


if __name__ == "__main__":
    main()
