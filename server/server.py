"""Ledgerly MCP server: lets Claude answer plain-English questions about a shop's data.

Run locally (stdio):      python -m server.server
Run remotely (HTTP):      LEDGERLY_TRANSPORT=streamable-http LEDGERLY_API_KEY=... python -m server.server
"""
import os
import re
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

from . import db

mcp = FastMCP("ledgerly", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GROUPS = {"day": "o.order_date", "week": "strftime('%Y-W%W', o.order_date)", "month": "strftime('%Y-%m', o.order_date)",
          "category": "p.category", "product": "p.name"}
STATUSES = {"completed", "refunded", "cancelled", "pending"}


def _date(value: str, field: str) -> str:
    if not DATE_RE.match(value):
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}")
    datetime.strptime(value, "%Y-%m-%d")  # rejects impossible dates like 2026-02-31
    return value


def _range(start: str | None, end: str | None, default_days: int = 30) -> tuple[str, str]:
    e = _date(end, "end") if end else date.today().isoformat()
    s = _date(start, "start") if start else (date.fromisoformat(e) - timedelta(days=default_days - 1)).isoformat()
    if s > e:
        raise ValueError("start must be on or before end")
    return s, e


@mcp.tool()
def get_revenue(start: str | None = None, end: str | None = None, group_by: str = "day") -> list[dict]:
    """Revenue, order count and gross profit for completed orders in a date range.

    Args:
        start: First day, YYYY-MM-DD (default: 30 days before end).
        end: Last day inclusive, YYYY-MM-DD (default: today).
        group_by: One of day, week, month, category, product.
    """
    if group_by not in GROUPS:
        raise ValueError(f"group_by must be one of {sorted(GROUPS)}")
    s, e = _range(start, end)
    key = GROUPS[group_by]
    return db.rows(
        f"""SELECT {key} AS bucket,
                   ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
                   ROUND(SUM(oi.quantity * (oi.unit_price - p.cost)), 2) AS gross_profit,
                   COUNT(DISTINCT o.id) AS orders
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN products p ON p.id = oi.product_id
            WHERE o.status = 'completed' AND o.order_date BETWEEN ? AND ?
            GROUP BY bucket ORDER BY bucket""",
        (s, e),
    )


@mcp.tool()
def top_products(n: int = 5, start: str | None = None, end: str | None = None) -> list[dict]:
    """Best-selling products by revenue for completed orders in a date range.

    Args:
        n: How many products to return (1-25).
        start: First day, YYYY-MM-DD (default: 30 days before end).
        end: Last day inclusive, YYYY-MM-DD (default: today).
    """
    if not 1 <= n <= 25:
        raise ValueError("n must be between 1 and 25")
    s, e = _range(start, end)
    return db.rows(
        """SELECT p.id, p.name, p.category,
                  SUM(oi.quantity) AS units,
                  ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           JOIN products p ON p.id = oi.product_id
           WHERE o.status = 'completed' AND o.order_date BETWEEN ? AND ?
           GROUP BY p.id ORDER BY revenue DESC LIMIT ?""",
        (s, e, n),
    )


@mcp.tool()
def low_stock(threshold: int | None = None) -> list[dict]:
    """Products at or below a stock level, with average daily sales over the last 30 days.

    Args:
        threshold: Stock level to flag. Default: each product's own reorder point.
    """
    if threshold is not None and not 0 <= threshold <= 100000:
        raise ValueError("threshold must be between 0 and 100000")
    since = (date.today() - timedelta(days=30)).isoformat()
    return db.rows(
        """SELECT p.id, p.name, p.stock, p.reorder_point,
                  ROUND(COALESCE(SUM(CASE WHEN o.status='completed' AND o.order_date >= ? THEN oi.quantity END), 0) / 30.0, 2)
                      AS avg_daily_units,
                  CASE WHEN COALESCE(SUM(CASE WHEN o.status='completed' AND o.order_date >= ? THEN oi.quantity END), 0) > 0
                       THEN ROUND(p.stock / (SUM(CASE WHEN o.status='completed' AND o.order_date >= ? THEN oi.quantity END) / 30.0), 1)
                  END AS days_of_stock_left
           FROM products p
           LEFT JOIN order_items oi ON oi.product_id = p.id
           LEFT JOIN orders o ON o.id = oi.order_id
           GROUP BY p.id
           HAVING p.stock <= COALESCE(?, p.reorder_point)
           ORDER BY p.stock ASC""",
        (since, since, since, threshold),
    )


@mcp.tool()
def search_orders(status: str | None = None, customer: str | None = None,
                  start: str | None = None, end: str | None = None, limit: int = 20) -> list[dict]:
    """Find orders by status, customer name/email fragment, and/or date range.

    Args:
        status: completed, refunded, cancelled, or pending.
        customer: Case-insensitive fragment of customer name or email.
        start: First day, YYYY-MM-DD. end: Last day inclusive, YYYY-MM-DD.
        limit: Max rows (1-100).
    """
    if status and status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    clauses, params = [], []
    if status:
        clauses.append("o.status = ?"); params.append(status)
    if customer:
        clauses.append("(c.name LIKE ? OR c.email LIKE ?)"); params += [f"%{customer}%"] * 2
    if start:
        clauses.append("o.order_date >= ?"); params.append(_date(start, "start"))
    if end:
        clauses.append("o.order_date <= ?"); params.append(_date(end, "end"))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return db.rows(
        f"""SELECT o.id, o.order_date, o.status, c.name AS customer,
                   ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_items oi ON oi.order_id = o.id
            {where}
            GROUP BY o.id ORDER BY o.order_date DESC, o.id DESC LIMIT ?""",
        (*params, limit),
    )


@mcp.tool()
def customer_summary(customer_id: int) -> dict:
    """Lifetime value, order count, first/last order, and favorite category for one customer."""
    info = db.rows("SELECT id, name, email, city, joined FROM customers WHERE id = ?", (customer_id,))
    if not info:
        raise ValueError(f"No customer with id {customer_id}")
    stats = db.rows(
        """SELECT COUNT(DISTINCT o.id) AS orders,
                  ROUND(COALESCE(SUM(oi.quantity * oi.unit_price), 0), 2) AS lifetime_value,
                  MIN(o.order_date) AS first_order, MAX(o.order_date) AS last_order
           FROM orders o JOIN order_items oi ON oi.order_id = o.id
           WHERE o.customer_id = ? AND o.status = 'completed'""",
        (customer_id,),
    )[0]
    fav = db.rows(
        """SELECT p.category, SUM(oi.quantity) AS units
           FROM orders o JOIN order_items oi ON oi.order_id = o.id JOIN products p ON p.id = oi.product_id
           WHERE o.customer_id = ? AND o.status = 'completed'
           GROUP BY p.category ORDER BY units DESC LIMIT 1""",
        (customer_id,),
    )
    return {**info[0], **stats, "favorite_category": fav[0]["category"] if fav else None}


@mcp.tool()
def draft_reorder(product_id: int, quantity: int) -> dict:
    """Create a DRAFT purchase-order line for a product. Draft only: nothing is ordered or sent.

    Args:
        product_id: Product to restock.
        quantity: Units to reorder (1-1000).
    """
    if not 1 <= quantity <= 1000:
        raise ValueError("quantity must be between 1 and 1000")
    prod = db.rows("SELECT id, name, stock FROM products WHERE id = ?", (product_id,))
    if not prod:
        raise ValueError(f"No product with id {product_id}")
    now = datetime.now().isoformat(timespec="seconds")
    with db.draft_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reorder_drafts (product_id, quantity, created_at) VALUES (?,?,?)",
            (product_id, quantity, now),
        )
    return {"draft_id": cur.lastrowid, "product": prod[0]["name"], "quantity": quantity,
            "current_stock": prod[0]["stock"], "status": "draft",
            "note": "Draft only. A human must review and place the real order."}


@mcp.resource("ledgerly://schema")
def schema() -> str:
    """Table and column reference so Claude understands the data before querying."""
    return """Ledgerly shop database (synthetic data)
products(id, name, category, price, cost, stock, reorder_point)
customers(id, name, email, city, joined)
orders(id, customer_id, order_date, status: completed|refunded|cancelled|pending)
order_items(id, order_id, product_id, quantity, unit_price)
reorder_drafts(id, product_id, quantity, created_at, status)
Revenue figures count completed orders only. Dates are YYYY-MM-DD."""


def main() -> None:
    transport = os.environ.get("LEDGERLY_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
        return
    # Remote mode: require an API key so a public URL is never open.
    key = os.environ.get("LEDGERLY_API_KEY")
    if not key:
        raise SystemExit("LEDGERLY_API_KEY is required for remote transport")
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class ApiKeyAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization") != f"Bearer {key}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app = mcp.streamable_http_app()
    app.add_middleware(ApiKeyAuth)
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
