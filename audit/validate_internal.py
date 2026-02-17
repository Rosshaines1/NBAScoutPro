"""Internal validation: recompute stats from the raw CSV and compare
to what's stored in player_db.json.

This catches pipeline bugs — wrong season selected, bad rounding,
division errors, missing data, etc.

No web requests needed.
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR
from pipeline.build_player_db import normalize_name, NAME_ALIASES, FORCE_BREF_ONLY, REMOVE_PLAYERS

# Load DB
with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
    db = json.load(f)
db_map = {p["name"]: p for p in db}

# Load raw CSV
with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college = pd.read_csv(f, low_memory=False)

# Coerce types
for col in ["year", "GP", "mp", "pts", "ast", "treb", "stl", "blk",
            "FTA", "FTM", "bpm", "obpm", "dbpm", "stl_per", "usg"]:
    if col in college.columns:
        college[col] = pd.to_numeric(college[col], errors="coerce")

college = college.dropna(subset=["year", "GP"])
college["_norm"] = college["player_name"].apply(
    lambda x: normalize_name(str(x)) if pd.notna(x) else "")

# Build the SAME lookups as the pipeline
college_gp10 = college[college["GP"] >= 10]
latest = college_gp10.sort_values("year", ascending=False).drop_duplicates("player_name")
latest_lookup = {str(row["player_name"]).strip(): row for _, row in latest.iterrows()}

# Also build normalized lookup
from pipeline.build_player_db import build_name_index
college_name_index = build_name_index(college["player_name"].dropna().unique())

college_gp3 = college[college["GP"] >= 3]
relaxed_lookup = {str(row["player_name"]).strip(): row
                  for _, row in college_gp3.sort_values("year", ascending=False).drop_duplicates("player_name").iterrows()}

college_by_school = {}
for _, row in college_gp3.sort_values("year", ascending=False).iterrows():
    name_str = str(row["player_name"]).strip()
    school = str(row.get("team", "")).strip().lower()
    key = (normalize_name(name_str), school)
    if key not in college_by_school:
        college_by_school[key] = row

print("=" * 80)
print("INTERNAL VALIDATION: Recompute from CSV vs player_db.json")
print("=" * 80)
print("Players in DB: %d" % len(db))
print()

# For each DB player, find what CSV row the pipeline would have matched,
# then verify the stats match
discrepancies = []
verified = 0
not_found = 0

for p in db:
    name = p["name"]
    bref_college = p.get("college", "").strip().lower()
    db_stats = p["stats"]

    # Replicate pipeline matching logic
    college_row = None

    # 1. Exact match
    if name in latest_lookup:
        college_row = latest_lookup[name]
    # 2. Alias
    elif name in NAME_ALIASES and NAME_ALIASES[name] in latest_lookup:
        college_row = latest_lookup[NAME_ALIASES[name]]
    # 3. Fuzzy
    if college_row is None:
        norm = normalize_name(name)
        if norm in college_name_index:
            orig = college_name_index[norm]
            if orig in latest_lookup:
                college_row = latest_lookup[orig]
    # 4. Relaxed GP
    if college_row is None:
        if name in relaxed_lookup:
            college_row = relaxed_lookup[name]
        elif name in NAME_ALIASES and NAME_ALIASES[name] in relaxed_lookup:
            college_row = relaxed_lookup[NAME_ALIASES[name]]
        else:
            norm = normalize_name(name)
            if norm in college_name_index:
                orig = college_name_index[norm]
                if orig in relaxed_lookup:
                    college_row = relaxed_lookup[orig]

    # 5. College disambiguation
    if college_row is not None and bref_college:
        csv_school = str(college_row.get("team", "")).strip().lower()
        if bref_college not in csv_school and csv_school not in bref_college:
            norm = normalize_name(name)
            for school_key in college_by_school:
                if school_key[0] == norm and bref_college in school_key[1]:
                    college_row = college_by_school[school_key]
                    break

    # 6. Force BRef-only
    if name in FORCE_BREF_ONLY:
        college_row = None

    if college_row is None:
        not_found += 1
        continue

    # Now compare CSV row stats to DB stats
    row = college_row

    def sf(val, default=0.0):
        try:
            v = float(val)
            return v if not np.isnan(v) else default
        except:
            return default

    csv_ppg = sf(row.get("pts"))
    csv_rpg = sf(row.get("treb"))
    csv_apg = sf(row.get("ast"))
    csv_spg = sf(row.get("stl"))
    csv_bpg = sf(row.get("blk"))
    csv_mpg = sf(row.get("mp"), 30.0)
    csv_efg = sf(row.get("eFG"), 45.0)
    csv_tp = sf(row.get("TP_per"))
    csv_ft = sf(row.get("FT_per"))
    csv_bpm = sf(row.get("bpm"))
    csv_obpm = sf(row.get("obpm"))
    csv_dbpm = sf(row.get("dbpm"))
    csv_stl_per = sf(row.get("stl_per"))
    csv_usg = sf(row.get("usg"))
    csv_gp = sf(row.get("GP"), 20)
    csv_fta_raw = sf(row.get("FTA"))
    csv_fta_pg = csv_fta_raw / csv_gp if csv_gp > 0 else 0

    # Convert pct if stored as decimal
    if csv_tp <= 1.0:
        csv_tp *= 100
    if csv_ft <= 1.0:
        csv_ft *= 100

    # Round same as pipeline
    csv_ppg = round(csv_ppg, 1)
    csv_rpg = round(csv_rpg, 1)
    csv_apg = round(csv_apg, 1)
    csv_spg = round(csv_spg, 1)
    csv_bpg = round(csv_bpg, 1)
    csv_mpg = round(csv_mpg, 1)
    csv_efg = round(csv_efg, 1)
    csv_tp = round(csv_tp, 1)
    csv_ft = round(csv_ft, 1)
    csv_bpm = round(csv_bpm, 1)
    csv_obpm = round(csv_obpm, 1)
    csv_dbpm = round(csv_dbpm, 1)
    csv_fta_pg = round(csv_fta_pg, 1)

    # Compare
    checks = [
        ("ppg", db_stats.get("ppg", 0), csv_ppg, 0.2),
        ("rpg", db_stats.get("rpg", 0), csv_rpg, 0.2),
        ("apg", db_stats.get("apg", 0), csv_apg, 0.2),
        ("spg", db_stats.get("spg", 0), csv_spg, 0.2),
        ("bpg", db_stats.get("bpg", 0), csv_bpg, 0.2),
        ("mpg", db_stats.get("mpg", 0), csv_mpg, 0.5),
        ("eFG%", db_stats.get("fg", 0), csv_efg, 1.0),
        ("3P%", db_stats.get("threeP", 0), csv_tp, 1.0),
        ("FT%", db_stats.get("ft", 0), csv_ft, 1.0),
        ("BPM", db_stats.get("bpm", 0), csv_bpm, 0.5),
        ("OBPM", db_stats.get("obpm", 0), csv_obpm, 0.5),
        ("DBPM", db_stats.get("dbpm", 0), csv_dbpm, 0.5),
        ("FTA/g", db_stats.get("fta", 0), csv_fta_pg, 0.5),
        ("STL%", db_stats.get("stl_per", 0), csv_stl_per, 0.5),
        ("USG", db_stats.get("usg", 0), csv_usg, 1.0),
    ]

    player_issues = []
    for stat_name, db_val, csv_val, threshold in checks:
        diff = abs(db_val - csv_val)
        if diff > threshold:
            player_issues.append((stat_name, db_val, csv_val, diff))

    if player_issues:
        discrepancies.append({
            "name": name,
            "college": p.get("college", ""),
            "draft_year": p.get("draft_year"),
            "tier": p["tier"],
            "csv_name": str(row.get("player_name", "")),
            "csv_team": str(row.get("team", "")),
            "csv_year": int(row["year"]) if pd.notna(row["year"]) else 0,
            "issues": player_issues,
        })
    else:
        verified += 1

# Also check: school name mismatches
school_mismatches = []
for p in db:
    name = p["name"]
    db_college = p.get("college", "").lower()
    # The college field in DB is set from the CSV, so it should be consistent
    # But let's check against BRef data to see if they match
    # Actually we can't without BRef data here, skip this

print("\n--- RESULTS ---")
print("Verified (all stats match CSV): %d / %d" % (verified, len(db)))
print("Discrepancies found:            %d" % len(discrepancies))
print("Not found in CSV:               %d" % not_found)

if discrepancies:
    # Sort by severity (most issues first)
    discrepancies.sort(key=lambda d: -len(d["issues"]))

    print("\n\n--- DISCREPANCIES ---")
    for d in discrepancies:
        print("\n%s (T%d, %s, draft %s)" % (d["name"], d["tier"], d["college"], d["draft_year"]))
        print("  CSV match: '%s' at %s (year=%d)" % (d["csv_name"], d["csv_team"], d["csv_year"]))
        for stat, db_val, csv_val, diff in d["issues"]:
            print("    %6s: DB=%.1f  CSV=%.1f  diff=%.1f" % (stat, db_val, csv_val, diff))

    # Stats summary
    print("\n\n--- STAT-LEVEL SUMMARY ---")
    from collections import Counter
    stat_counts = Counter()
    for d in discrepancies:
        for stat, _, _, _ in d["issues"]:
            stat_counts[stat] += 1
    for stat, count in stat_counts.most_common():
        print("  %6s: %d players affected" % (stat, count))
