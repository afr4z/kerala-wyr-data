import csv
import os
from collections import defaultdict

CANONICAL = {
    'KASARGOD': 'KASARGOD', 'Kannur': 'KANNUR', 'Wayanad': 'WAYANAD',
    'Kozhikode': 'KOZHIKODE', 'Malappuram': 'MALAPPURAM',
    'Palakkad': 'PALAKKAD', 'Thrissur': 'THRISSUR',
    'Ernakulam': 'ERNAKULAM', 'Idukki': 'IDUKKI',
    'Kottayam': 'KOTTAYAM', 'Alappuzha': 'ALAPPUZHA',
    'Pathanamthitta': 'PATHANAMTHITTA', 'Kollam': 'KOLLAM',
    'Thiruvananthapuram': 'THIRUVANANTHAPURAM',
    'KANNUR': 'KANNUR', 'WAYANAD': 'WAYANAD', 'KOZHIKODE': 'KOZHIKODE',
    'MALAPPURAM': 'MALAPPURAM', 'PALAKKAD': 'PALAKKAD',
    'THRISSUR': 'THRISSUR', 'ERNAKULAM': 'ERNAKULAM',
    'IDUKKI': 'IDUKKI', 'KOTTAYAM': 'KOTTAYAM',
    'ALAPPUZHA': 'ALAPPUZHA', 'PATHANAMTHITTA': 'PATHANAMTHITTA',
    'KOLLAM': 'KOLLAM', 'THIRUVANANTHAPURAM': 'THIRUVANANTHAPURAM',
    'KASARGOD': 'KASARGOD',
}

LB_DISTRICT_MAP = {
    'ചാലിയാര്‍': 'MALAPPURAM',
    'പെരിങ്ങമ്മല': 'THIRUVANANTHAPURAM',
    'നഗരൂര്‍': 'THIRUVANANTHAPURAM',
    'നെന്‍മേനി': 'WAYANAD',
    'അന്നമനട': 'THRISSUR',
    'കാണക്കാരി': 'KOTTAYAM',
    'പത്തനാപുരം': 'KOLLAM',
    'അഞ്ചല്‍': 'KOLLAM',
    'കൊട്ടാരക്കര': 'KOLLAM',
}

OUTPUT_DIR = "/home/afr4z/git/LSG2025"
COMBINED_CSV = f"{OUTPUT_DIR}/kerala_wyr_all_members.csv"

fixed_rows = []
unknown_rows = []
district_rows = defaultdict(list)

with open(COMBINED_CSV, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        d = row['District'].strip()
        # Normalize case
        if d in CANONICAL:
            row['District'] = CANONICAL[d]
        elif not d:
            lb_name = row['LB_Name'].strip()
            if lb_name in LB_DISTRICT_MAP:
                row['District'] = LB_DISTRICT_MAP[lb_name]
            else:
                print(f"WARNING: No district for {lb_name}")
        else:
            print(f"WARNING: Unknown district '{d}'")
        fixed_rows.append(row)
        district_rows[row['District']].append(row)
        if not row['District'].strip():
            unknown_rows.append(row)

with open(COMBINED_CSV, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(fixed_rows)

for district, rows in sorted(district_rows.items()):
    if not district:
        continue
    safe_name = district.lower().replace(' ', '_')
    path = f"{OUTPUT_DIR}/{safe_name}_wyr_members.csv"
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

with open(f"{OUTPUT_DIR}/unknown_wyr_members.csv", 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(unknown_rows)

print(f"Remaining unknown: {len(unknown_rows)}")
print(f"Total: {len(fixed_rows)}")
for d, rows in sorted(district_rows.items()):
    if d:
        print(f"  {d}: {len(rows)}")
