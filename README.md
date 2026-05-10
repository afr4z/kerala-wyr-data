# Kerala WYR — Ward Your Representative Data

Complete elected representative data for all 23,573 local body members across Kerala, scraped from [SEC Kerala](https://sec.kerala.gov.in) — the State Election Commission website.

## What's Included

- **`data/kerala_wyr_all_members.csv`** — All 23,573 members across 14 districts, covering:
  - 17,335 Grama Panchayat members
  - 3,205 Municipality members
  - 2,267 Block Panchayat members
  - 420 Corporation members
  - 346 District Panchayat members

  Each row includes: District, LB Type, LB Name, Ward No, Ward Name, Member Name, Party, Coalition, Reservation, Position, Phone, Address, Age, Gender, Votes, Margin

- **`scripts/scrape_wyr_kerala.py`** — Main scraper that downloads all member data from SEC Kerala
- **`scripts/fix_districts.py`** — Data cleanup script (handles missing/normalized district names)
- **`scripts/correlate_complaints.py`** — Correlates ParathiPetty complaints against representatives using OSM geocoding + fuzzy ward matching

## Data Source

All representative data is from the **Kerala State Election Commission** website:
https://sec.kerala.gov.in/public/wyr

The data was scraped from public WYR (Ward Your Representative) pages on SEC Kerala and is provided as-is.

## How to Use

```bash
# Install dependencies (for correlation script)
pip install requests beautifulsoup4

# Run scraper (downloads fresh data)
python scrips/scrape_wyr_kerala.py

# Run correlation with ParathiPetty complaints
python scripts/correlate_complaints.py
```

## Matching with ParathiPetty

The `correlate_complaints.py` script:
1. Fetches complaints from [ParathiPetty](https://parathipetty.com) API
2. Geocodes complaint locations using Nominatim + Overpass API
3. Matches complaints to representatives by district → local body → ward
4. Generates a CSV with matched representative details and WhatsApp links

### Match Accuracy

- **Ward-level**: ~87% of geocodable complaints matched to specific representatives
- **LSGI-level**: Remaining matched at local body level (President fallback)
- Matching uses exact, substring, and Levenshtein fuzzy matching for ward names

## License

MIT — Data sourced from public government records (SEC Kerala).
