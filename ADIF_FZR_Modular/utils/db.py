"""Store SQLite del log (Fase 1 — fondamenta).

Un file .sqlite per profilo. Le colonne che servono ad award/ricerca/dedup
sono indicizzate; tutti gli altri campi ADIF vanno in una colonna JSON `extra`,
così non si perde nulla. WAL per resistenza a crash, transazioni per scritture
atomiche, backup a rotazione. L'ADIF resta il formato di scambio.

API:
    db = LogDB(path); db.importa(qsos); db.aggiungi(qso); db.tutti(); db.conta()
    db.sostituisci(qsos); db.backup_rotante(); db.close()
    leggi_qsos(path)  -> lista dict (sola lettura, per il restore)
    info_db(path)     -> (n_qso, mtime)
"""

import os
import json
import sqlite3

COLS = [
    'call', 'qso_date', 'time_on', 'band', 'mode', 'freq',
    'dxcc', 'country', 'cont', 'cqz', 'ituz',
    'state', 'cnty', 'gridsquare', 'iota',
    'lotw_qsl_rcvd', 'lotw_qslrdate', 'qsl_rcvd', 'eqsl_qsl_rcvd',
    'station_callsign',
]
_INDICI = ['call', 'qso_date', 'band', 'mode', 'dxcc', 'state', 'gridsquare', 'cqz']


def _merge_row(r):
    """Ricostruisce il dict QSO (chiavi minuscole) da una riga del DB."""
    d = {c: r[c] for c in COLS if r[c] not in (None, '')}
    if r['extra']:
        try:
            d.update(json.loads(r['extra']))
        except Exception:
            pass
    return d


class LogDB:
    def __init__(self, path):
        self.path = path
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        try:
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        self._crea_schema()

    def _crea_schema(self):
        cols_sql = ",\n            ".join(f"{c} TEXT" for c in COLS)
        script = [
            "CREATE TABLE IF NOT EXISTS qso (\n"
            "            id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            f"            {cols_sql},\n"
            "            extra TEXT\n"
            "        );"
        ]
        for c in _INDICI:
            script.append(f"CREATE INDEX IF NOT EXISTS ix_{c} ON qso({c});")
        script.append("CREATE UNIQUE INDEX IF NOT EXISTS ux_dedup "
                      "ON qso(call, qso_date, time_on, band, mode);")
        self.con.executescript("\n".join(script))
        self.con.commit()

    @staticmethod
    def _norm(q):
        return {str(k).lower(): ('' if v is None else str(v)) for k, v in q.items()}

    def _split(self, q):
        d = self._norm(q)
        row = [d.get(c, '') for c in COLS]
        extra = {k: v for k, v in d.items() if k not in COLS and k != 'id'}
        row.append(json.dumps(extra, ensure_ascii=False) if extra else None)
        return row

    @staticmethod
    def _merge(r):
        return _merge_row(r)

    def importa(self, qsos, skip_dup=True):
        """Import massivo (transazione unica). Ritorna (inseriti, duplicati)."""
        ph = ",".join("?" * (len(COLS) + 1))
        verb = "INSERT OR IGNORE" if skip_dup else "INSERT"
        sql = f"{verb} INTO qso ({','.join(COLS)},extra) VALUES ({ph})"
        ins = 0
        n = 0
        cur = self.con.cursor()
        for q in qsos:
            cur.execute(sql, self._split(q))
            ins += cur.rowcount
            n += 1
        self.con.commit()
        return ins, n - ins

    def aggiungi(self, q, skip_dup=True):
        ph = ",".join("?" * (len(COLS) + 1))
        verb = "INSERT OR IGNORE" if skip_dup else "INSERT"
        cur = self.con.execute(
            f"{verb} INTO qso ({','.join(COLS)},extra) VALUES ({ph})", self._split(q))
        self.con.commit()
        return cur.lastrowid if cur.rowcount else None

    def svuota(self):
        self.con.execute("DELETE FROM qso")
        self.con.commit()

    def sostituisci(self, qsos):
        self.svuota()
        return self.importa(qsos)

    def tutti(self, ordine="qso_date, time_on"):
        cur = self.con.execute(f"SELECT * FROM qso ORDER BY {ordine}")
        return [_merge_row(r) for r in cur.fetchall()]

    def conta(self):
        return self.con.execute("SELECT COUNT(*) FROM qso").fetchone()[0]

    def pagina(self, limit=500, offset=0, recenti_prima=True):
        ordine = "qso_date DESC, time_on DESC" if recenti_prima else "qso_date, time_on"
        cur = self.con.execute(
            f"SELECT * FROM qso ORDER BY {ordine} LIMIT ? OFFSET ?", (limit, offset))
        return [_merge_row(r) for r in cur.fetchall()]

    def cerca(self, campo, valore):
        if campo not in COLS:
            return []
        cur = self.con.execute(
            f"SELECT * FROM qso WHERE {campo} = ? COLLATE NOCASE", (valore,))
        return [_merge_row(r) for r in cur.fetchall()]

    def backup_rotante(self, max_copie=5):
        try:
            for i in range(max_copie, 1, -1):
                src = f"{self.path}.bak{i-1}"
                if os.path.exists(src):
                    os.replace(src, f"{self.path}.bak{i}")
            dest = f"{self.path}.bak1"
            with sqlite3.connect(dest) as b:
                self.con.backup(b)
            return dest
        except Exception:
            return None

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass


def leggi_qsos(path):
    """Legge i QSO da un file .sqlite (anche un backup .bakN) in sola lettura,
    senza modificarlo. Ritorna una lista di dict (chiavi minuscole)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM qso ORDER BY qso_date, time_on").fetchall()
        return [_merge_row(r) for r in rows]
    finally:
        con.close()


def info_db(path):
    """(numero_qso, timestamp_modifica) di un file .sqlite, o (None, mtime)."""
    mtime = os.path.getmtime(path) if os.path.exists(path) else 0
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM qso").fetchone()[0]
        finally:
            con.close()
        return n, mtime
    except Exception:
        return None, mtime
