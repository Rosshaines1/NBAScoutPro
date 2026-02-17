"""V2: Separate name collisions from genuine wrong-season issues.

A "wrong season" is only real if the DB entry and the "correct" final entry
are at the SAME school (or a known transfer). If they're at different schools,
it's a name collision (different person) and the DB is probably correct.
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR

with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
    db = json.load(f)

with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college = pd.read_csv(f, low_memory=False)

college["year"] = pd.to_numeric(college["year"], errors="coerce")
college["GP"] = pd.to_numeric(college["GP"], errors="coerce")
college["mp"] = pd.to_numeric(college["mp"], errors="coerce")
college["pts"] = pd.to_numeric(college["pts"], errors="coerce")
college = college.dropna(subset=["year", "GP"])

from collections import defaultdict, Counter

# Build ALL seasons per player name (including different people with same name)
player_seasons = defaultdict(list)
for _, row in college.iterrows():
    name = str(row["player_name"]).strip()
    player_seasons[name].append({
        "team": str(row.get("team", "")),
        "yr": str(row.get("yr", "")),
        "year": int(row["year"]),
        "gp": int(row["GP"]) if pd.notna(row["GP"]) else 0,
        "mp": float(row["mp"]) if pd.notna(row["mp"]) else 0,
        "pts": float(row["pts"]) if pd.notna(row["pts"]) else 0,
    })

for name in player_seasons:
    player_seasons[name].sort(key=lambda s: s["year"])

print("=" * 70)
print("WRONG SEASON ANALYSIS V2 — Separating name collisions from real issues")
print("=" * 70)

db_college = [p for p in db if p.get("has_college_stats")]

name_collisions = []
genuine_wrong = []
correct = []
single_season_players = []
not_found = []

for p in db_college:
    name = p["name"]
    db_ppg = p["stats"].get("ppg", 0)
    db_mpg = p["stats"].get("mpg", 0)
    db_college_name = p.get("college", "").lower()

    if name not in player_seasons:
        not_found.append(name)
        continue

    seasons = player_seasons[name]

    # Get seasons at the SAME school as what's in the DB
    same_school = [s for s in seasons if db_college_name in s["team"].lower()
                   or s["team"].lower() in db_college_name]

    if len(same_school) <= 1:
        # Only one season at this school — check if there are later seasons at OTHER schools
        all_schools = set(s["team"] for s in seasons)
        if len(all_schools) > 1:
            # Multiple schools in CSV = possible name collision OR transfer
            # Check if DB has the correct one based on BRef college
            pass
        single_season_players.append(name)
        continue

    # Multiple seasons at same school — check if DB has the final one
    same_school.sort(key=lambda s: s["year"])
    final_at_school = same_school[-1]

    # Which same-school season does the DB match?
    best_idx = -1
    best_diff = 999
    for i, s in enumerate(same_school):
        diff = abs(db_ppg - s["pts"]) + abs(db_mpg - s["mp"]) * 0.1
        if diff < best_diff:
            best_diff = diff
            best_idx = i

    if best_idx < len(same_school) - 1 and best_diff < 2.0:
        # DB matches an EARLIER season at the same school
        matched = same_school[best_idx]
        genuine_wrong.append({
            "name": name,
            "draft_year": p.get("draft_year"),
            "draft_pick": p.get("draft_pick"),
            "tier": p["tier"],
            "college": p.get("college"),
            "db_ppg": db_ppg,
            "db_mpg": db_mpg,
            "db_yr": matched["yr"],
            "db_year": matched["year"],
            "db_gp": matched["gp"],
            "final_ppg": final_at_school["pts"],
            "final_mpg": final_at_school["mp"],
            "final_yr": final_at_school["yr"],
            "final_year": final_at_school["year"],
            "final_gp": final_at_school["gp"],
            "num_seasons": len(same_school),
        })
    else:
        correct.append(name)

# Also check: multi-school players (transfers) where we might have wrong school entirely
# These are trickier — need BRef college to validate
print("\n--- GENUINE WRONG SEASON (same school, earlier year) ---")
print("Found: %d players" % len(genuine_wrong))
genuine_wrong.sort(key=lambda x: (x["tier"], x.get("draft_pick") or 99))
for w in genuine_wrong:
    ppg_diff = w["final_ppg"] - w["db_ppg"]
    mpg_diff = w["final_mpg"] - w["db_mpg"]
    print("\n  %s (%s, draft %s #%s, tier %s)" % (
        w["name"], w["college"], w.get("draft_year"), w.get("draft_pick"), w["tier"]))
    print("    DB has: %s (year=%s, GP=%s) ppg=%.1f mpg=%.1f" % (
        w["db_yr"], w["db_year"], w["db_gp"], w["db_ppg"], w["db_mpg"]))
    print("    Final:  %s (year=%s, GP=%s) ppg=%.1f mpg=%.1f" % (
        w["final_yr"], w["final_year"], w["final_gp"], w["final_ppg"], w["final_mpg"]))
    print("    Delta: ppg %+.1f, mpg %+.1f" % (ppg_diff, mpg_diff))
    # Flag if final season was filtered by GP < 10
    if w["final_gp"] < 10:
        print("    ** Final season GP=%d (< 10) — filtered by pipeline, using earlier season" % w["final_gp"])

print("\n\n--- SUMMARY ---")
print("Players with college stats:        %d" % len(db_college))
print("Single season / single school:     %d" % len(single_season_players))
print("Correct final season:              %d" % len(correct))
print("GENUINE wrong season (same school): %d" % len(genuine_wrong))
print("Not found in CSV:                  %d" % len(not_found))

# Impact
if genuine_wrong:
    ppg_diffs = [w["final_ppg"] - w["db_ppg"] for w in genuine_wrong]
    low_gp_final = [w for w in genuine_wrong if w["final_gp"] < 10]
    real_wrong = [w for w in genuine_wrong if w["final_gp"] >= 10]
    print("\nOf %d wrong-season:" % len(genuine_wrong))
    print("  Final season GP < 10 (pipeline filtered, arguably correct): %d" % len(low_gp_final))
    print("  Final season GP >= 10 (REAL problem):                      %d" % len(real_wrong))

    if real_wrong:
        print("\n  REAL PROBLEMS (final season has GP >= 10 but DB uses earlier):")
        for w in real_wrong:
            print("    %s: DB=%s(yr=%s) ppg=%.1f -> Final=%s(yr=%s) ppg=%.1f" % (
                w["name"], w["db_yr"], w["db_year"], w["db_ppg"],
                w["final_yr"], w["final_year"], w["final_ppg"]))

# Data gap
print("\n\n--- 2022-2023 DATA GAP ---")
gap_players = [p for p in db if p.get("draft_year") in (2022, 2023) and not p.get("has_college_stats")]
print("2022+2023 draft picks missing college stats: %d" % len(gap_players))
print("\nThese players need college data from a new source:")
gap_players.sort(key=lambda p: (p.get("draft_year"), p.get("draft_pick", 99)))
for p in gap_players:
    print("  %s (%s, %s #%s, NBA WS=%.1f)" % (
        p["name"], p.get("college", "?"), p.get("draft_year"), p.get("draft_pick"),
        p.get("nba_ws", 0) or 0))
