"""Gestione profili come "un log = un profilo".

Ogni profilo porta con se' il percorso del suo log ufficiale (log_path) e il
marker di sync incrementale LoTW (last_qsl). Un log secondario e' semplicemente
un profilo CLONATO dal principale, a cui si assegna un ADIF diverso.

Questo modulo e' PURO (niente GUI): risoluzione della cartella dati con
fallback, migrazione del JSON profili esistente, clonazione. La GUI
(main_window) si limita a usare queste funzioni.

Cartella dati: si preferisce la cartella del programma (portabile, come vuole
l'utente); se non scrivibile (es. installazione in Program Files) si ripiega su
%APPDATA%\\ADIF_FZR (Windows) o ~/.adif_fzr (altrove).
"""

import os
import sys
import json
import shutil
import copy


def cartella_programma():
    """Cartella dove 'vive' il programma. Con PyInstaller (frozen) e' quella
    dell'eseguibile, NON _MEIPASS (che e' temporanea e in sola lettura)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # in sviluppo: cartella del pacchetto (una sopra utils/)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _scrivibile(cartella):
    try:
        os.makedirs(cartella, exist_ok=True)
        test = os.path.join(cartella, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return True
    except Exception:
        return False


def cartella_fallback():
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "ADIF_FZR")
    return os.path.join(os.path.expanduser("~"), ".adif_fzr")


def cartella_dati(program_dir=None):
    """Ritorna la cartella dati scrivibile: prima la cartella programma, poi
    il fallback. program_dir override utile per i test."""
    prog = program_dir or cartella_programma()
    if _scrivibile(prog):
        return prog
    fb = cartella_fallback()
    _scrivibile(fb)   # tenta di crearla
    return fb


def percorso_profili(program_dir=None):
    """Percorso del file profili nella cartella dati."""
    return os.path.join(cartella_dati(program_dir), "adif_fzr_profili.json")


def migra_profili(nuovo_path, vecchio_path=None):
    """Se il file profili non esiste ancora nella nuova posizione ma esiste il
    vecchio (~/.adif_fzr_profili.json), lo copia. Ritorna True se ha migrato."""
    if vecchio_path is None:
        vecchio_path = os.path.join(os.path.expanduser("~"),
                                    ".adif_fzr_profili.json")
    try:
        if not os.path.exists(nuovo_path) and os.path.exists(vecchio_path):
            os.makedirs(os.path.dirname(nuovo_path), exist_ok=True)
            shutil.copy2(vecchio_path, nuovo_path)
            return True
    except Exception:
        pass
    return False


def _profili_dict(profili):
    """Normalizza in dict {nome: profilo}. Accetta anche una lista di profili
    con chiave 'nome'."""
    if isinstance(profili, dict):
        return dict(profili)
    out = {}
    for p in (profili or []):
        n = str(p.get("nome", "")).strip()
        if n:
            out[n] = p
    return out


def _nome_univoco(base, esistenti):
    """Genera un nome non ancora presente: 'X (copia)', 'X (copia 2)', ..."""
    cand = f"{base} (copia)"
    i = 2
    while cand in esistenti:
        cand = f"{base} (copia {i})"
        i += 1
    return cand


def assicura_campi(profilo):
    """Garantisce che il profilo abbia i campi log_path e last_qsl."""
    profilo.setdefault("log_path", "")
    profilo.setdefault("last_qsl", "")
    return profilo


def clona_profilo(profili, nome_sorgente, nuovo_nome=None):
    """Clona il profilo 'nome_sorgente' come nuovo profilo (log secondario).
    Copia identita' e credenziali, ma AZZERA log_path e last_qsl: il nuovo
    log va assegnato a mano ed e' un log diverso, quindi il sync riparte.
    Ritorna (profili_aggiornati, nuovo_nome). Solleva KeyError se la sorgente
    non esiste."""
    d = _profili_dict(profili)
    if nome_sorgente not in d:
        raise KeyError(nome_sorgente)

    nuovo = copy.deepcopy(d[nome_sorgente])
    if not nuovo_nome:
        nuovo_nome = _nome_univoco(nome_sorgente, set(d.keys()))
    elif nuovo_nome in d:
        nuovo_nome = _nome_univoco(nuovo_nome, set(d.keys()))

    nuovo["nome"] = nuovo_nome
    nuovo["log_path"] = ""     # nuovo log da assegnare
    nuovo["last_qsl"] = ""     # sync LoTW indipendente
    assicura_campi(nuovo)
    d[nuovo_nome] = nuovo
    return d, nuovo_nome


def salva_profili(path, profili):
    d = _profili_dict(profili)
    for p in d.values():
        assicura_campi(p)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def carica_profili(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = _profili_dict(json.load(f))
    except Exception:
        return {}
    for p in d.values():
        assicura_campi(p)
    return d
