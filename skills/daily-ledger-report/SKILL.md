---
name: daily-ledger-report
description: Produce the Ledgerly morning business briefing from the ledgerly MCP server. Use when asked for the daily report, morning brief, or "how did the shop do yesterday".
---

# Daily Ledger Report

Build a short morning briefing for the shop owner using the `ledgerly` MCP tools. Be specific, numeric, and brief. The owner reads this on a phone before opening the shop.

## Steps

1. Read the `ledgerly://schema` resource if you haven't this session.
2. Pull data. Use yesterday as the report day unless the user names another.
   - `get_revenue` for yesterday, grouped by `day`.
   - `get_revenue` for the 7 days before yesterday (same grouping) to get a baseline average.
   - `top_products` (n=5) for yesterday, and again for the trailing 7 days.
   - `low_stock` with no threshold.
   - `search_orders` with `status="refunded"` for yesterday, and `status="pending"`.
3. Compare yesterday's revenue to the 7-day daily average. Flag it if it is more than 25% above or below.
4. For each low-stock item with under 10 days of stock left, call `draft_reorder` with roughly 30 days of demand (avg_daily_units x 30, rounded up). Never place or promise a real order.

## Output format

**Ledgerly Daily Report: {weekday, date}**

**Revenue:** ${yesterday} vs ${7-day avg}/day ({+/-}%). {N} orders, ${gross profit} gross profit.
{One sentence on the likely driver if you can name one from the data. Otherwise say the cause isn't clear from the data.}

**Top sellers:** numbered list of 5, units and revenue.

**Needs attention** (omit the section if empty):
- Low stock: product, units left, days of stock left, and the draft reorder ID you created.
- Refunds or pending orders worth a look.

**Next step:** one concrete suggestion, for example reviewing the draft reorders.

## Rules

- Under 200 words. No filler, no greeting.
- Every number comes from a tool result. Never estimate or invent figures.
- If a tool errors or returns nothing, say so in the report instead of skipping silently.
- Drafts are drafts. State clearly that no orders were placed.
