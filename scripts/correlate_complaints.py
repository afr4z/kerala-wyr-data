import requests
import csv
import sys
import time
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher

PARATHIPETTY_API = "https://parathipetty.com/api/complaints"
REPS_DIR = "/home/afr4z/git/LSG2025"
HEADERS = {"User-Agent": "LSG2025-correlate/1.0", "Accept": "application/json"}

KERALA_DISTRICTS = [
    "Kasaragod", "Kannur", "Wayanad", "Kozhikode", "Malappuram",
    "Palakkad", "Thrissur", "Ernakulam", "Idukki", "Kottayam",
    "Alappuzha", "Pathanamthitta", "Kollam", "Thiruvananthapuram"
]

# SEC CSV district name (uppercase) -> ParathiPetty district name (title case)
SEC_TO_PETTY = {
    "KASARGOD": "Kasaragod", "KANNUR": "Kannur", "WAYANAD": "Wayanad",
    "KOZHIKODE": "Kozhikode", "MALAPPURAM": "Malappuram", "PALAKKAD": "Palakkad",
    "THRISSUR": "Thrissur", "ERNAKULAM": "Ernakulam", "IDUKKI": "Idukki",
    "KOTTAYAM": "Kottayam", "ALAPPUZHA": "Alappuzha", "PATHANAMTHITTA": "Pathanamthitta",
    "KOLLAM": "Kollam", "THIRUVANANTHAPURAM": "Thiruvananthapuram",
}


def fetch_complaints(districts=None):
    if districts:
        all_complaints = []
        for d in districts:
            resp = requests.get(f"{PARATHIPETTY_API}?district={d}", headers=HEADERS, timeout=15)
            resp.raise_for_status()
            all_complaints.extend(resp.json().get("complaints", []))
            time.sleep(0.3)
        return all_complaints
    else:
        resp = requests.get(PARATHIPETTY_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json().get("complaints", [])


def load_all_reps(reps_dir):
    """Load all district rep CSVs. Returns dict: sec_district_name -> (reps_by_lsgi, lsgi_names)"""
    result = {}
    import glob
    pattern = f"{reps_dir}/*_wyr_members.csv"
    for path in sorted(glob.glob(pattern)):
        if "unknown" in path or "kerala_wyr_all" in path:
            continue
        reps_by_lsgi = defaultdict(list)
        lsgi_names = set()
        rep_district = ""
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lsgi = row.get("LB_Name", "").strip()
                if not lsgi:
                    continue
                reps_by_lsgi[lsgi].append(row)
                lsgi_names.add(lsgi)
                if not rep_district:
                    rep_district = row.get("District", "").strip()
        if rep_district:
            result[rep_district] = (reps_by_lsgi, lsgi_names)
    return result


def reverse_geocode(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        addr = data.get("address", {})
        village = addr.get("village") or addr.get("town") or addr.get("city") or addr.get("municipality") or ""
        county = addr.get("county", "")
        # Collect additional location names for ward matching
        other_names = []
        for k in ("hamlet", "quarter", "suburb", "neighbourhood", "locality"):
            v = addr.get(k)
            if v and v not in (village, county):
                other_names.append(v)
        return village, county, other_names
    except Exception:
        return None, None, []


def find_all_boundaries(lat, lon):
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""[out:json];
is_in({lat},{lon});
area._[admin_level~"^(7|8|9|10)$"];
out tags;"""
    for attempt in range(3):
        try:
            resp = requests.get(overpass_url, params={"data": query}, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            boundaries = {}
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                level = tags.get("admin_level")
                name = tags.get("name", "")
                if level and name:
                    boundaries[int(level)] = name
            if boundaries:
                return boundaries
            time.sleep(1)
        except Exception:
            time.sleep(2)
    return {}


def find_lsgi_boundary(lat, lon):
    boundaries = find_all_boundaries(lat, lon)
    return boundaries.get(8)  # admin_level=8 is Gram Panchayat


def best_lsgi_match(name, lsgi_names):
    if not name:
        return None
    name_lower = name.lower().strip()
    # exact match
    for lsgi in lsgi_names:
        if lsgi.lower().strip() == name_lower:
            return lsgi
    # substring match
    for lsgi in lsgi_names:
        if name_lower in lsgi.lower() or lsgi.lower() in name_lower:
            return lsgi
    # fuzzy match
    best_score = 0
    best = None
    for lsgi in lsgi_names:
        score = SequenceMatcher(None, name_lower, lsgi.lower()).ratio()
        if score > best_score:
            best_score = score
            best = lsgi
    return best if best_score > 0.5 else None


def find_ward_match(boundaries, lsgi, reps_by_lsgi):
    if not lsgi or lsgi not in reps_by_lsgi:
        return None

    wards = reps_by_lsgi[lsgi]

    def fuzzy_match(name, threshold=0.7):
        name = name.lower().strip()
        if not name:
            return None
        # exact
        for rep in wards:
            if name == rep["Ward_Name"].lower().strip():
                return rep
        # substring
        for rep in wards:
            ward = rep["Ward_Name"].lower().strip()
            if name in ward or ward in name:
                return rep
        # fuzzy
        best_score = 0
        best = None
        for rep in wards:
            score = SequenceMatcher(None, name, rep["Ward_Name"].lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best = rep
        return best if best_score >= threshold else None

    # 1-2) Level 9/10 boundaries with exact, substring, fuzzy
    for level in [9, 10]:
        name = boundaries.get(level, "")
        if name:
            result = fuzzy_match(name)
            if result:
                return result

    # 3) Collect all location names from Nominatim and try each
    loc_names = set()
    for key in ("village", "town", "city", "municipality"):
        v = boundaries.get(key) or boundaries.get("village", "")
        if v:
            loc_names.add(v)
    for n in boundaries.get("other_names", []):
        if n:
            loc_names.add(n)

    for loc_name in sorted(loc_names, key=len, reverse=True):
        result = fuzzy_match(loc_name, threshold=0.6)
        if result:
            return result
        # Also try first word
        first_word = loc_name.split()[0] if loc_name.split() else ""
        if first_word:
            for rep in wards:
                if first_word.lower() in rep["Ward_Name"].lower():
                    return rep

    return None


def main():
    # Determine districts to process
    target_districts = None
    if len(sys.argv) > 1:
        target_districts = [d for d in KERALA_DISTRICTS if d.lower() == sys.argv[1].lower()]
        if not target_districts:
            print(f"Unknown district '{sys.argv[1]}'. Options: {', '.join(KERALA_DISTRICTS)} or 'all'")
            return
    else:
        target_districts = None  # fetch all

    complaints = fetch_complaints(target_districts)
    print(f"Fetched {len(complaints)} total complaints from ParathiPetty")

    # Group by district for reporting
    from collections import Counter
    valid = [c for c in complaints if c["lat"] is not None and c["lon"] is not None]
    dist_counts = Counter(c["district"] for c in valid)
    for d, n in sorted(dist_counts.items()):
        print(f"  {d}: {n}")

    # Load all district rep CSVs
    all_reps = load_all_reps(REPS_DIR)
    print(f"Loaded reps data for {len(all_reps)} districts: {', '.join(sorted(all_reps.keys()))}")
    has_any_reps = bool(all_reps)

    # deduplicate by lat/lon to avoid redundant geocoding
    seen_coords = {}
    geocode_cache = {}

    for c in complaints:
        if c["lat"] is None or c["lon"] is None:
            continue
        key = (c["lat"], c["lon"])
        if key not in seen_coords:
            seen_coords[key] = []
        seen_coords[key].append(c)

    output = []
    rep_cols = ["LB_Type", "LB_Name", "Ward_No", "Ward_Name", "Reservation",
                "Member_Name", "Party", "Coalition", "Phone",
                "Address", "Age", "Gender", "Position",
                "Votes", "Margin"]

    for idx, ((lat, lon), complaints_group) in enumerate(seen_coords.items()):
        print(f"\nGeocoding point {idx+1}/{len(seen_coords)} ({lat}, {lon})...")

        # geocode once per unique coordinate
        if (lat, lon) in geocode_cache:
            village, gp_name, boundaries, certainty, other_names = geocode_cache[(lat, lon)]
        else:
            village, county, other_names = reverse_geocode(lat, lon)
            boundaries = find_all_boundaries(lat, lon)
            boundaries["village"] = village or ""
            boundaries["other_names"] = other_names
            gp_name = boundaries.get(8, "")
            certainty = "exact" if gp_name else "none"
            geocode_cache[(lat, lon)] = (village or "", gp_name, boundaries, certainty, other_names)
            time.sleep(0.5)

        village, gp_name, boundaries, certainty, other_names = geocode_cache[(lat, lon)]

        # Try rep lookup using complaint's district
        complaint_district = complaints_group[0]["district"]
        # Map ParathiPetty district name to SEC district name
        petty_to_sec = {v: k for k, v in SEC_TO_PETTY.items()}
        sec_district = petty_to_sec.get(complaint_district, "")

        ward_match = None
        matched_lsgi = None
        has_rep_data = sec_district in all_reps

        if has_rep_data:
            reps_by_lsgi, lsgi_names = all_reps[sec_district]
            # Map Overpass GP name to LSGI name in our CSV
            matched_lsgi = best_lsgi_match(gp_name, lsgi_names) if gp_name else None
            if matched_lsgi is None:
                matched_lsgi = best_lsgi_match(village, lsgi_names)
            ward_match = find_ward_match(boundaries, matched_lsgi, reps_by_lsgi) if matched_lsgi else None

        # Record all available Overpass boundary levels
        overpass_levels = {}
        for al in [6, 7, 8, 9, 10]:
            if al in boundaries:
                overpass_levels[f"Boundary_L{ al}"] = boundaries[al]
        other_str = ", ".join(other_names[:3]) if other_names else ""

        # Fallback: if ward didn't match, try coarser LSGI levels
        if not ward_match and has_rep_data:
            reps_by_lsgi, lsgi_names = all_reps[sec_district]
            # Try admin_level 7 (Block) if 8 (GP) didn't match
            if not matched_lsgi:
                for al in [7, 6]:
                    name = boundaries.get(al, "")
                    if name:
                        matched_lsgi = best_lsgi_match(name, lsgi_names)
                        if matched_lsgi:
                            break

        for c in complaints_group:
            row = {
                "District": complaint_district,
                "Complaint_ID": c["id"],
                "Category": c["category"],
                "Description": c["description"],
                "Status": c["status"],
                "Latitude": c["lat"],
                "Longitude": c["lon"],
                "Pincode": c["pincode"],
                "Photo_URL": c["photo"],
                "Created_At": c["createdAt"],
                "Nearest_Village": village.title() if village else "",
                "Nearest_Other": other_str,
                "GP_Name": gp_name,
                "Boundary_L10": overpass_levels.get("Boundary_L10", ""),
                "Boundary_L9": overpass_levels.get("Boundary_L9", ""),
                "Boundary_L7": overpass_levels.get("Boundary_L7", ""),
                "Boundary_L6": overpass_levels.get("Boundary_L6", ""),
                "Certainty": certainty,
                "Has_Rep_Data": "yes" if has_rep_data else "no",
            }

            if ward_match:
                for col in rep_cols:
                    row[f"Rep_{col}"] = ward_match[col]
                row["Match_Level"] = "ward"
            elif has_rep_data and matched_lsgi:
                row["Match_Level"] = "lsgi"
                row["Matched_LSGI"] = matched_lsgi
                row["Rep_LB_Name"] = matched_lsgi
                lsgi_reps = all_reps[sec_district][0].get(matched_lsgi, [])
                row["Rep_Count"] = len(lsgi_reps)
                if lsgi_reps:
                    row["Rep_LB_Type"] = lsgi_reps[0].get("LB_Type", "")
            else:
                row["Match_Level"] = "gp_only"
                row["Matched_LSGI"] = gp_name

            output.append(row)

        print(f"  → Village: {village or '?'}, GP: {gp_name or '?'}")

    # Build fieldnames
    base_cols = ["District", "Complaint_ID", "Category", "Description", "Status",
                 "Latitude", "Longitude", "Pincode", "Photo_URL", "Created_At"]
    match_cols = ["Nearest_Village", "Nearest_Other", "GP_Name",
                  "Boundary_L10", "Boundary_L9", "Boundary_L7", "Boundary_L6",
                  "Certainty", "Match_Level", "Has_Rep_Data"]
    rep_cols_prefixed = [f"Rep_{c}" for c in rep_cols] + ["Matched_LSGI", "Rep_Count"]
    fieldnames = base_cols + match_cols + rep_cols_prefixed

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"kerala_complaints_correlated_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)

    print(f"\n{'='*60}")
    print(f"Saved to {filename}")
    print(f"Total complaints processed: {len(output)}")
    print(f"\nSummary by district:")
    for d in sorted(set(r["District"] for r in output)):
        n = sum(1 for r in output if r["District"] == d)
        matched = sum(1 for r in output if r["District"] == d and r.get("Rep_Member_Name"))
        gp_only = sum(1 for r in output if r["District"] == d and r["Match_Level"] == "gp_only")
        print(f"  {d:25s} | {n:2d} complaints | ward={matched:2d}  gp_only={gp_only:2d}")

    print(f"\nDetailed:")
    for row in output:
        loc = f"{row['Nearest_Village']:20s}"
        gp = f"{row['GP_Name'] or '?':20s}"
        rep = row.get("Rep_Member_Name", f"[GP only]")
        print(f"  {row['District']:20s} | {loc} | {gp} | {rep}")


if __name__ == "__main__":
    main()
