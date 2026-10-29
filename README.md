# Kerala WYR — Ward Your Representative Data

Complete elected representative data for all 23,573 local body members across Kerala, scraped from [SEC Kerala](https://sec.kerala.gov.in).

## What's Included

- **`data/kerala_wyr_all_members.csv`** — All 23,573 members (17,335 GP, 3,205 Municipality, 2,267 Block, 420 Corp, 346 DP)
- **`data/reps.json`** — Compact JSON export for API/website consumption
- **`scripts/scrape_wyr_kerala.py`** — Standalone scraper (downloads all listing pages, parses, enriches)
- **`api/members.js`** — Vercel serverless API for querying member data
- **`index.html`** — Frontend to browse, search, and view member details

## Quick Start — Browse Members

Deploy to Vercel:

```bash
vercel --prod
```

Or serve locally:

```bash
npx serve .
```

Then visit the website to filter by district, body type, search by name, and click any member for full details (phone, WhatsApp link, position).

## API Endpoints (hosted on Vercel)

| Endpoint | Description |
|---|---|
| `GET /api/stats` | Total counts by district and type |
| `GET /api/districts` | List all 14 districts with counts |
| `GET /api/types` | List all 5 body types with counts |
| `GET /api/lbs?district=X&type=Y` | List local bodies for a district/type |
| `GET /api/members` | Search members (`?district=`, `?type=`, `?lb=`, `?search=`, `?limit=`, `?offset=`) |
| `GET /api/members/:id` | Member by index, phone, or name search |

Example: `/api/members?district=KASARGOD&type=Grama Panchayat&limit=10`

## Scraper Usage

```bash
pip install beautifulsoup4
python scripts/scrape_wyr_kerala.py
```

## Data Source

All data from [SEC Kerala](https://sec.kerala.gov.in/public/wyr) public WYR pages. MIT license.
