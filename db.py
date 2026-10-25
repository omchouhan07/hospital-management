"""Database connection + schema setup."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "hospital.db"
SCHEMA_FILE = BASE_DIR / "schema.sql"


def connect(path=DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()


@contextmanager
def transaction(conn):
    """Sab theek to commit, error aaya to rollback."""
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
