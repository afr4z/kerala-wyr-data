import requests
import csv
import re
import os
import subprocess
import time
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://sec.kerala.gov.in/public"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DISTRICT_NAMES = {
    1: "Kasaragod", 2: "Kannur", 3: "Wayanad", 4: "Kozhikode",
    5: "Malappuram", 6: "Palakkad", 7: "Thrissur", 8: "Ernakulam",
    9: "Idukki", 10: "Kottayam", 11: "Alappuzha", 12: "Pathanamthitta",
    13: "Kollam", 14: "Thiruvananthapuram"
}
OUTPUT_CSV = "kerala_wyr_all_members.csv"
TMP_DIR = "/tmp/wyr_scrape"
os.makedirs(TMP_DIR, exist_ok=True)


def fetch(url, timeout=60):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return None


def fetch_with_curl(url, outpath, timeout=120):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-o", outpath, url]
    try:
        subprocess.run(cmd, check=True, timeout=timeout+10)
        return os.path.getsize(outpath) if os.path.exists(outpath) else 0
    except:
        return 0


def find_card_header(soup, text_match):
    for h5 in soup.find_all('h5'):
        if text_match in h5.get_text():
            return h5
    return None


def parse_wyrw_page(html, lb_type, lb_name, wyrw_id, district):
    members = []
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return members
    rows = table.find_all('tr')[1:]
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        ward_no = cells[0].get_text(strip=True)
        ward_name = cells[1].get_text(strip=True)
        view_link = ""
        member_name = ""
        name_cell = cells[2] if len(cells) > 2 else cells[1]
        a = name_cell.find('a')
        if a:
            member_name = a.get_text(strip=True)
            view_link = a.get('href', '')
        else:
            member_name = name_cell.get_text(strip=True)
        position = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        party = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        reservation = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        members.append({
            'District': district, 'LB_Type': lb_type, 'LB_Name': lb_name,
            'Ward_No': ward_no, 'Ward_Name': ward_name,
            'Member_Name': member_name, 'Party': party,
            'Reservation': reservation, 'Position': position,
            'View_URL': f"{BASE}{view_link}" if view_link else "",
            'WYRW_ID': str(wyrw_id)
        })
    return members


def parse_view_page(html, member):
    soup = BeautifulSoup(html, 'html.parser')
    # Profile card for coalition, party, name, details
    profile_card = find_card_header(soup, 'Profile')
    if profile_card:
        header = profile_card.find_parent('div', class_='card-header')
        if header:
            badges = header.find_all('span', class_='badge')
            if len(badges) >= 1:
                member['Coalition'] = badges[0].get_text(strip=True)
            if len(badges) >= 2:
                member['Party'] = badges[1].get_text(strip=True)
        card_body = profile_card.find_parent('div', class_='card')
        if card_body:
            body = card_body.find('div', class_='card-body')
            if body:
                for item in body.find_all('div', class_='border-bottom'):
                    small_el = item.find('span', class_='text-muted')
                    strong_el = item.find('strong')
                    if not small_el or not strong_el:
                        continue
                    label = small_el.get_text(strip=True).rstrip(':')
                    val = strong_el.get_text(strip=True)
                    if label == 'Age':
                        age_match = re.search(r'(\d+)', val)
                        if age_match:
                            member['Age'] = age_match.group(1)
                        if 'Female' in val:
                            member['Gender'] = 'Female'
                        elif 'Male' in val:
                            member['Gender'] = 'Male'
                    elif label == 'Phone':
                        member['Phone'] = val
                    elif label == 'Address':
                        member['Address'] = val
                    elif label == 'Votes':
                        member['Votes'] = val.replace(',', '')
                    elif label == 'Margin':
                        member['Margin'] = val.replace(',', '')
                    elif label == 'Serving From':
                        member['Serving_From'] = val
    # Ward card for district and LSGI name
    ward_card = find_card_header(soup, 'Ward')
    if ward_card:
        parent = ward_card.find_parent('div', class_='card')
        if parent:
            body = parent.find('div', class_='card-body')
            if body:
                for d in body.find_all('div', class_='rounded-3'):
                    small = d.find('small')
                    strong = d.find('strong')
                    if not small or not strong:
                        continue
                    label = small.get_text(strip=True)
                    if label == 'District':
                        member['District'] = strong.get_text(strip=True)
                    elif label == 'LSGI':
                        member['LB_Name'] = strong.get_text(strip=True)
                    elif label == 'Ward':
                        ward_text = d.get_text(separator=' ', strip=True)
                        res_span = d.find('span', class_='badge')
                        if res_span:
                            member['Reservation'] = res_span.get_text(strip=True)
                        ward_info = strong.get_text(strip=True)
                        parts = ward_info.split('-', 1)
                        if len(parts) == 2:
                            member['Ward_No'] = parts[0].strip()
                            member['Ward_Name'] = parts[1].strip()
                        else:
                            member['Ward_Name'] = ward_info
    return member


def main():
    all_lb_types = {}  # maps source_table_type -> list of LB entries

    # === STEP 1: Parse all listing pages ===
    print("=== Step 1: Parsing listing pages ===")

    # GPs, Blocks, Municipalities (wyrw-based)
    for lb_type, suffix in [('Grama Panchayat', 'G'), ('Block Panchayat', 'B'), ('Municipality', 'M')]:
        entries = []
        for n in range(1, 15):
            path = f'/tmp/wyrlb_{n}_{suffix}.html'
            if not os.path.exists(path):
                continue
            with open(path) as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            table = soup.find('table')
            if not table:
                continue
            for row in table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                a = cells[1].find('a')
                if not a:
                    continue
                wyrw_id = a['href'].split('/')[-1].strip()
                full_text = a.get_text(strip=True)
                # Extract code and name
                parts = full_text.split('-', 1)
                code = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else full_text
                ward_count = cells[2].get_text(strip=True)
                entries.append({
                    'wyrw_id': wyrw_id, 'code': code, 'name': name,
                    'district_n': n, 'district': DISTRICT_NAMES[n],
                    'ward_count': ward_count, 'lb_type': lb_type
                })
        all_lb_types[suffix] = entries
        print(f"  {lb_type}s: {len(entries)}")

    # Corporations (C) - view-link based (same structure as wyrw page but embedded)
    corp_entries = []
    for n in range(1, 15):
        path = f'/tmp/wyrlb_{n}_C.html'
        if not os.path.exists(path):
            continue
        with open(path) as f:
            html = f.read()
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        if not table:
            continue
        rows = table.find_all('tr')[1:]
        if len(rows) <= 1:
            continue  # empty
        # Get the corporation name from the heading
        lb_name = ""
        for span in soup.find_all('span', class_='fs-3'):
            lb_name = span.get_text(strip=True)
            break
        members = []
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            ward_no = cells[0].get_text(strip=True)
            ward_name = cells[1].get_text(strip=True)
            a = cells[2].find('a') if len(cells) > 2 else None
            member_name = a.get_text(strip=True) if a else cells[2].get_text(strip=True)
            view_url = f"{BASE}{a['href']}" if a and 'href' in a.attrs else ""
            position = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            party = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            reservation = cells[5].get_text(strip=True) if len(cells) > 5 else ""
            corp_entries.append({
                'District': DISTRICT_NAMES[n], 'LB_Type': 'Corporation',
                'LB_Name': lb_name, 'Ward_No': ward_no,
                'Ward_Name': ward_name, 'Member_Name': member_name,
                'Party': party, 'Reservation': reservation,
                'Position': position, 'View_URL': view_url
            })
    print(f"  Corporations: {len(corp_entries)} members from listing pages")

    # District Panchayats (D) - view-link based
    dist_entries = []
    for n in range(1, 15):
        path = f'/tmp/wyrlb_{n}_D.html'
        if not os.path.exists(path):
            continue
        with open(path) as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        table = soup.find('table')
        if not table:
            continue
        # Get district panchayat name
        lb_name = f"{DISTRICT_NAMES[n]} District Panchayat"
        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            a = cells[2].find('a') if len(cells) > 2 else None
            if not a or 'href' not in a.attrs:
                continue
            view_url = f"{BASE}{a['href']}"
            dist_entries.append({
                'District': DISTRICT_NAMES[n], 'LB_Type': 'District Panchayat',
                'LB_Name': lb_name, 'View_URL': view_url,
                'WYRW_ID': ''
            })
    print(f"  District Panchayat members from listing: {len(dist_entries)}")

    # === STEP 2: Download all wyrw pages (G/B/M) ===
    print("\n=== Step 2: Downloading wyrw pages ===")
    all_wyrw = []
    for suffix in ['G', 'B', 'M']:
        for entry in all_lb_types[suffix]:
            all_wyrw.append(entry)

    wyrw_dir = f"{TMP_DIR}/wyrw"
    os.makedirs(wyrw_dir, exist_ok=True)

    # Download in parallel batches of 8
    to_download = []
    for e in all_wyrw:
        wid = e['wyrw_id']
        outpath = f"{wyrw_dir}/{wid}.html"
        if not os.path.exists(outpath) or os.path.getsize(outpath) == 0:
            to_download.append((wid, outpath))

    print(f"  {len(to_download)} wyrw pages to download (of {len(all_wyrw)} total)")

    batch_size = 8
    for i in range(0, len(to_download), batch_size):
        batch = to_download[i:i+batch_size]
        procs = []
        for wid, outpath in batch:
            url = f"{BASE}/wyrw/{wid}"
            p = subprocess.Popen(
                ["curl", "-s", "--max-time", "120", "-o", outpath, url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            procs.append(p)
        for p in procs:
            p.wait()
        if (i // batch_size) % 10 == 0:
            print(f"  ...downloaded {i+len(batch)}/{len(to_download)}")
        time.sleep(0.5)

    print(f"  Wyrw pages downloaded: {len(to_download)}")

    # === STEP 3: Parse wyrw pages for member data ===
    print("\n=== Step 3: Parsing wyrw pages ===")
    wyrw_members = []

    for e in all_wyrw:
        wid = e['wyrw_id']
        path = f"{wyrw_dir}/{wid}.html"
        if not os.path.exists(path):
            continue
        with open(path) as f:
            html = f.read()
        if len(html) < 100:
            continue
        members = parse_wyrw_page(html, e['lb_type'], e['name'], wid, e['district'])
        wyrw_members.extend(members)

    print(f"  Members from wyrw pages: {len(wyrw_members)}")

    # === STEP 4: Collect all view URLs ===
    print("\n=== Step 4: Collecting view URLs ===")
    view_urls = set()

    # From wyrw members
    for m in wyrw_members:
        if m['View_URL']:
            view_urls.add(m['View_URL'])

    # From district entries
    for m in dist_entries:
        if m['View_URL']:
            view_urls.add(m['View_URL'])

    # From corporation entries
    for m in corp_entries:
        if m['View_URL']:
            view_urls.add(m['View_URL'])

    print(f"  Total unique view URLs: {len(view_urls)}")

    # === STEP 5: Download view pages for full details ===
    print("\n=== Step 5: Downloading view pages ===")
    view_dir = f"{TMP_DIR}/view"
    os.makedirs(view_dir, exist_ok=True)

    to_dl = []
    for url in view_urls:
        vid = url.split('/')[-1]
        outpath = f"{view_dir}/{vid}.html"
        if not os.path.exists(outpath) or os.path.getsize(outpath) == 0:
            to_dl.append((url, vid, outpath))

    print(f"  {len(to_dl)} view pages to download")

    batch_size = 8
    for i in range(0, len(to_dl), batch_size):
        batch = to_dl[i:i+batch_size]
        procs = []
        for url, vid, outpath in batch:
            p = subprocess.Popen(
                ["curl", "-s", "--max-time", "120", "-o", outpath, url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            procs.append(p)
        for p in procs:
            p.wait()
        if (i // batch_size) % 10 == 0:
            print(f"  ...downloaded {i+len(batch)}/{len(to_dl)}")
        time.sleep(0.3)

    print(f"  View pages downloaded: {len(to_dl)}")

    # === STEP 6: Parse view pages and enrich member data ===
    print("\n=== Step 6: Enriching member data ===")
    view_cache = {}
    for url in view_urls:
        vid = url.split('/')[-1]
        path = f"{view_dir}/{vid}.html"
        if os.path.exists(path):
            with open(path) as f:
                view_cache[url] = f.read()

    # Enrich wyrw members
    for m in wyrw_members:
        html = view_cache.get(m['View_URL'])
        if html:
            parse_view_page(html, m)

    # Enrich district members
    dist_members = []
    for e in dist_entries:
        html = view_cache.get(e['View_URL'])
        if html:
            m = {
                'District': e['District'], 'LB_Type': e['LB_Type'],
                'LB_Name': e['LB_Name'], 'Ward_No': '', 'Ward_Name': '',
                'Member_Name': '', 'Party': '', 'Reservation': '',
                'Position': '', 'Coalition': '', 'Phone': '', 'Address': '',
                'Age': '', 'Gender': '', 'Votes': '', 'Margin': '',
                'Serving_From': '', 'View_URL': e['View_URL']
            }
            parse_view_page(html, m)
            if m['Member_Name']:
                dist_members.append(m)

    # Enrich corporation members
    corp_members = []
    for e in corp_entries:
        html = view_cache.get(e['View_URL'])
        m = dict(e)
        for k in ['Coalition', 'Phone', 'Address', 'Age', 'Gender', 'Votes', 'Margin', 'Serving_From']:
            m[k] = ''
        if html:
            parse_view_page(html, m)
        corp_members.append(m)

    print(f"  Wyrw members enriched: {len(wyrw_members)}")
    print(f"  District members: {len(dist_members)}")
    print(f"  Corporation members: {len(corp_members)}")

    # === STEP 7: Combine and output ===
    all_members = wyrw_members + dist_members + corp_members
    fieldnames = [
        'District', 'LB_Type', 'LB_Name', 'Ward_No', 'Ward_Name',
        'Member_Name', 'Party', 'Coalition', 'Reservation', 'Position',
        'Phone', 'Address', 'Age', 'Gender', 'Votes', 'Margin',
        'Serving_From', 'View_URL'
    ]

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for m in all_members:
            row = {k: m.get(k, '') for k in fieldnames}
            writer.writerow(row)

    print(f"\n{'='*60}")
    print(f"Saved to {OUTPUT_CSV}")
    print(f"Total members: {len(all_members)}")

    from collections import Counter
    type_counts = Counter(m.get('LB_Type', '?') for m in all_members)
    print(f"\nBy type:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    dist_counts = Counter(m.get('District', '?') for m in all_members)
    print(f"\nBy district:")
    for d in sorted(dist_counts):
        print(f"  {d}: {dist_counts[d]}")


if __name__ == '__main__':
    main()
