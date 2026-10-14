"""Database access for Ledgerly.

Two connection types, on purpose:
  * read-only (SQLite URI mode=ro) for every query tool, so the model can never mutate business data
  * a narrow write connection used only to insert rows into `reorder_drafts`
All SQL is parameterized; the model never supplies SQL text.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("LEDGERLY_DB", Path(__file__).parent.parent / "data" / "shop.db"))


@contextmanager
def read_conn():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def draft_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
