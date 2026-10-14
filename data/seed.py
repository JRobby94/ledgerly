"""Generate a fake online-shop database for Ledgerly demos. All data is synthetic."""
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "shop.db"

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS reorder_drafts;

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    cost REAL NOT NULL,
    stock INTEGER NOT NULL,
    reorder_point INTEGER NOT NULL
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL,
    joined DATE NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed','refunded','cancelled','pending'))
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE reorder_drafts (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
"""

PRODUCTS = [
    ("Trailhead Daypack", "Outdoors", 64.00, 28.00),
    ("Summit Water Bottle", "Outdoors", 24.00, 8.00),
    ("Ridgeline Headlamp", "Outdoors", 39.00, 15.00),
    ("Cedar Cutting Board", "Kitchen", 48.00, 19.00),
    ("Cast Iron Skillet 10in", "Kitchen", 55.00, 24.00),
    ("Pour-Over Coffee Set", "Kitchen", 42.00, 16.00),
    ("Linen Throw Blanket", "Home", 72.00, 30.00),
    ("Soy Candle Trio", "Home", 34.00, 11.00),
    ("Ceramic Planter Set", "Home", 46.00, 17.00),
    ("Wool Beanie", "Apparel", 28.00, 9.00),
    ("Canvas Work Jacket", "Apparel", 118.00, 52.00),
    ("Merino Hiking Socks", "Apparel", 22.00, 7.00),
]
CITIES = ["Nashville", "Louisville", "Memphis", "Evansville", "Lexington", "St. Louis", "Chattanooga"]
FIRST = ["Avery", "Jordan", "Riley", "Casey", "Morgan", "Taylor", "Quinn", "Parker", "Reese", "Dakota", "Emerson", "Rowan"]
LAST = ["Hart", "Brooks", "Foster", "Reed", "Mercer", "Lowell", "Sutton", "Weaver", "Ellis", "Navarro"]


def build(days: int = 180, seed: int = 42, end: date | None = None) -> None:
    rng = random.Random(seed)
    end = end or date.today()
    start = end - timedelta(days=days)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    for i, (name, cat, price, cost) in enumerate(PRODUCTS, 1):
        stock = rng.randint(40, 160)
        conn.execute(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?)",
            (i, name, cat, price, cost, stock, rng.randint(15, 30)),
        )

    customers = []
    for i in range(1, 121):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"customer{i}@example.com"
        joined = start + timedelta(days=rng.randint(0, days))
        conn.execute(
            "INSERT INTO customers VALUES (?,?,?,?,?)",
            (i, name, email, rng.choice(CITIES), joined.isoformat()),
        )
        customers.append((i, joined))

    order_id = item_id = 0
    sold = {i: 0 for i in range(1, len(PRODUCTS) + 1)}
    for d in range(days + 1):
        day = start + timedelta(days=d)
        base = 7 + (d / days) * 4              # gentle growth trend
        if day.weekday() >= 5:
            base *= 1.35                        # weekend lift
        if day == end - timedelta(days=2):
            base *= 0.35                        # planted anomaly: sharp revenue dip
        n_orders = max(0, int(rng.gauss(base, 2)))
        eligible = [c for c, joined in customers if joined <= day]
        for _ in range(n_orders):
            if not eligible:
                break
            order_id += 1
            status = rng.choices(
                ["completed", "refunded", "cancelled", "pending"], [88, 5, 5, 2]
            )[0]
            if day < end - timedelta(days=3) and status == "pending":
                status = "completed"
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?)",
                (order_id, rng.choice(eligible), day.isoformat(), status),
            )
            for pid in rng.sample(range(1, len(PRODUCTS) + 1), rng.choice([1, 1, 2, 3])):
                qty = rng.choice([1, 1, 1, 2, 3])
                item_id += 1
                price = PRODUCTS[pid - 1][2]
                conn.execute(
                    "INSERT INTO order_items VALUES (?,?,?,?,?)",
                    (item_id, order_id, pid, qty, price),
                )
                if status == "completed":
                    sold[pid] += qty

    # Depress stock for a few products so low-stock alerts have something to show.
    for pid, stock in [(2, 9), (7, 4), (11, 12)]:
        conn.execute("UPDATE products SET stock=? WHERE id=?", (stock, pid))

    conn.commit()
    conn.close()
    print(f"Seeded {DB_PATH} — {order_id} orders, {item_id} line items, {days} days ending {end}")


if __name__ == "__main__":
    build(days=int(sys.argv[1]) if len(sys.argv) > 1 else 180)
