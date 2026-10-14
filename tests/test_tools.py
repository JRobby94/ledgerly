import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))


@pytest.fixture(scope="session", autouse=True)
def seeded(tmp_path_factory):
    import seed
    path = tmp_path_factory.mktemp("db") / "test.db"
    seed.DB_PATH = path
    seed.build(days=90, seed=7)
    os.environ["LEDGERLY_DB"] = str(path)
    from server import db
    db.DB_PATH = path
    return path


def test_revenue_by_day_has_rows():
    from server.server import get_revenue
    rows = get_revenue(group_by="day")
    assert rows and all(r["revenue"] > 0 for r in rows)


def test_revenue_excludes_non_completed(seeded):
    from server.server import get_revenue
    total = sum(r["revenue"] for r in get_revenue(start="2000-01-01", group_by="month"))
    conn = sqlite3.connect(seeded)
    all_status = conn.execute("SELECT SUM(quantity*unit_price) FROM order_items").fetchone()[0]
    assert total < all_status


def test_top_products_sorted_and_limited():
    from server.server import top_products
    rows = top_products(n=3, start="2000-01-01")
    assert len(rows) == 3
    assert rows[0]["revenue"] >= rows[1]["revenue"] >= rows[2]["revenue"]


def test_low_stock_flags_planted_items():
    from server.server import low_stock
    names = {r["name"] for r in low_stock()}
    assert "Linen Throw Blanket" in names


def test_search_orders_filters():
    from server.server import search_orders
    rows = search_orders(status="refunded", limit=5)
    assert len(rows) <= 5 and all(r["status"] == "refunded" for r in rows)


def test_customer_summary_and_missing():
    from server.server import customer_summary
    assert customer_summary(1)["id"] == 1
    with pytest.raises(ValueError):
        customer_summary(99999)


@pytest.mark.parametrize("bad", ["2026-13-01", "yesterday", "2026-02-31", "'; DROP TABLE orders;--"])
def test_bad_dates_rejected(bad):
    from server.server import get_revenue
    with pytest.raises(ValueError):
        get_revenue(start=bad)


def test_bad_group_by_rejected():
    from server.server import get_revenue
    with pytest.raises(ValueError):
        get_revenue(group_by="1; DROP TABLE orders")


def test_sql_injection_in_customer_filter_is_inert(seeded):
    from server.server import search_orders
    search_orders(customer="x' OR '1'='1")
    conn = sqlite3.connect(seeded)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] > 0


def test_draft_reorder_only_writes_drafts(seeded):
    from server.server import draft_reorder
    before = sqlite3.connect(seeded).execute("SELECT stock FROM products WHERE id=2").fetchone()[0]
    result = draft_reorder(2, 50)
    assert result["status"] == "draft"
    after = sqlite3.connect(seeded).execute("SELECT stock FROM products WHERE id=2").fetchone()[0]
    assert before == after  # drafting never changes inventory
    with pytest.raises(ValueError):
        draft_reorder(2, 0)


def test_read_connection_cannot_write():
    from server import db
    with db.read_conn() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM orders")
