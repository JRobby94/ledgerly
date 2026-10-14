# Ledgerly

**Your business, briefed before breakfast.**
A Claude-connected business data server with automated daily reporting. Built on the Model Context Protocol (MCP).

Ask Claude plain-English questions about a shop's sales, inventory, and customers, and get a short report each morning without opening a dashboard.

> All data is synthetic. A seed script generates six months of fake orders for a demo online shop.

<!-- docs/demo.gif goes here -->

## What it does

| Piece | Purpose |
|---|---|
| **MCP server** (`server/`) | Exposes the shop database to Claude through safe, validated tools |
| **Skill** (`skills/daily-ledger-report/`) | Encodes the morning-report process so output is consistent every day |
| **Scheduled routine** | Runs the skill daily and delivers the report (setup below) |

Example questions Claude can now answer:
- "Why did revenue drop two days ago?"
- "Which products will run out this week?"
- "What has customer 42 bought, and what are they worth?"
- "Draft a reorder for anything under a week of stock."

## Tools

| Tool | Type | Description |
|---|---|---|
| `get_revenue` | read | Revenue, gross profit, order count grouped by day/week/month/category/product |
| `top_products` | read | Best sellers by revenue for a date range |
| `low_stock` | read | Items below reorder point, with days of stock left |
| `search_orders` | read | Filter orders by status, customer, dates |
| `customer_summary` | read | Lifetime value, first/last order, favorite category |
| `draft_reorder` | draft | Creates a draft purchase-order line. **Never places an order.** |

Resource: `ledgerly://schema` gives Claude the table layout before it queries.

## Security design

- **Claude never writes SQL.** Every tool takes typed arguments and runs parameterized queries.
- **Read-only by construction.** Query tools use a SQLite connection opened with `mode=ro`. Even a bug can't modify business data (covered by a test).
- **Draft-only actions.** The one write path inserts into a `reorder_drafts` table and never touches inventory. A human reviews and places real orders.
- **Input validation.** Dates, enums, and numeric ranges are checked before any query runs (injection attempts are in the test suite).
- **Remote mode requires an API key.** The HTTP transport refuses to start without `LEDGERLY_API_KEY`.

## Quick start

```bash
pip install -r requirements.txt
python data/seed.py          # creates data/shop.db with ~1,700 fake orders
python -m pytest tests -q    # 14 tests
```

### Connect to Claude Code (local)

```bash
claude mcp add ledgerly -- python -m server.server
```

Then ask: *"Using ledgerly, give me this week's top products and anything low on stock."*

### Connect to Claude Desktop (local)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ledgerly": {
      "command": "python",
      "args": ["-m", "server.server"],
      "cwd": "/absolute/path/to/ledgerly"
    }
  }
}
```

### Install the skill

Copy `skills/daily-ledger-report/` into your Claude skills folder (or upload it in Claude's skill settings), then ask for "the daily report".

## Run it remotely (for scheduled reports)

A scheduled task can only reach your server if it is online when the task runs, so deploy it:

```bash
LEDGERLY_TRANSPORT=streamable-http LEDGERLY_API_KEY=<long-random-string> python -m server.server
```

A `Dockerfile` is included for Railway, Fly.io, or Render. Set `LEDGERLY_API_KEY` as a secret, then add the server URL to Claude as a custom connector with an `Authorization: Bearer <key>` header.

## Project layout

```
ledgerly/
  server/            MCP server (tools, validation, DB access)
  data/seed.py       Synthetic shop data generator (with a planted revenue dip to find)
  skills/            daily-ledger-report skill
  tests/             Tool, validation, and security tests
  docs/              Architecture diagram and demo GIF
```

## Roadmap

- Weekly summary skill
- Second data source (Google Sheet or CSV) for multi-connector queries
- Delivery to Slack or email
