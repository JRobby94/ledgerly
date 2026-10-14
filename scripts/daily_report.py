"""Zero-token version of the daily-ledger-report skill.

Calls the same validated Python functions the MCP server exposes as tools —
no MCP, no LLM, no network. Run this from Windows Task Scheduler or cron
instead of a Claude scheduled task when you don't need the natural-language
framing, just the report.

Usage:  python scripts/daily_report.py [YYYY-MM-DD]   # defaults to yesterday
"""
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.server import draft_reorder, get_revenue, low_stock, search_orders, top_products


def build_report(report_day: date) -> str:
    baseline_start = report_day - timedelta(days=7)
    baseline_end = report_day - timedelta(days=1)
    trailing_start = report_day - timedelta(days=6)

    today_rev = get_revenue(start=report_day.isoformat(), end=report_day.isoformat(), group_by="day")
    baseline = get_revenue(start=baseline_start.isoformat(), end=baseline_end.isoformat(), group_by="day")
    top_today = top_products(n=5, start=report_day.isoformat(), end=report_day.isoformat())
    stock = low_stock()
    refunds = search_orders(status="refunded", start=report_day.isoformat(), end=report_day.isoformat())
    pending = search_orders(status="pending")

    revenue = today_rev[0]["revenue"] if today_rev else 0
    orders = today_rev[0]["orders"] if today_rev else 0
    gross_profit = today_rev[0]["gross_profit"] if today_rev else 0
    avg = round(sum(r["revenue"] for r in baseline) / len(baseline), 2) if baseline else 0
    pct = round((revenue - avg) / avg * 100, 1) if avg else 0
    flag = " [FLAG: more than 25% off the 7-day average]" if avg and abs(pct) > 25 else ""

    drafts = []
    for item in stock:
        if item["days_of_stock_left"] is not None and item["days_of_stock_left"] < 10:
            qty = math.ceil(item["avg_daily_units"] * 30)
            result = draft_reorder(item["id"], qty)
            drafts.append((item, result["draft_id"]))

    lines = [
        f"**Ledgerly Daily Report: {report_day.strftime('%A, %Y-%m-%d')}**",
        "",
        f"**Revenue:** ${revenue} vs ${avg}/day ({pct:+.1f}%).{flag} {orders} orders, ${gross_profit} gross profit.",
        "",
        "**Top sellers:**",
    ]
    for i, p in enumerate(top_today, 1):
        lines.append(f"{i}. {p['name']} - {p['units']} units, ${p['revenue']}")

    attention = []
    for item, draft_id in drafts:
        attention.append(
            f"- Low stock: {item['name']}, {item['stock']} left, "
            f"{item['days_of_stock_left']} days of stock - draft reorder #{draft_id}"
        )
    for o in refunds:
        attention.append(f"- Refund: order #{o['id']}, {o['customer']}, ${o['total']}")
    for o in pending:
        attention.append(f"- Pending: order #{o['id']}, {o['customer']} ({o['order_date']}), ${o['total']}")

    if attention:
        lines += ["", "**Needs attention:**", *attention]

    lines += ["", "No real orders were placed - all reorders above are drafts only."]
    if drafts:
        lines += ["", f"**Next step:** Review the {len(drafts)} draft reorder(s) above."]

    return "\n".join(lines)


if __name__ == "__main__":
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)
    print(build_report(day))
