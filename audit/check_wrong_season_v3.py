"""V3: Direct comparison — for every DB player, find which CSV row their stats
actually match, and flag anyone NOT on their latest available season.

No clever school filtering. Just raw stat fingerprinting.
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR
from pipeline.build_player_db import normalize_name, NAME_ALIASES

# Load DB
with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
    db = json.load(f)

# Load college CSV (same as pipeline — only the 2009-2021 file)
with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college = pd.read_csv(f, low_memory=False)

college["year"] = pd.to_numeric(college["year"], errors="coerce")
college["GP"] = pd.to_numeric(college["GP"], errors="coerce")
college["mp"] = pd.to_numeric(college["mp"], errors="coerce")
college["pts"] = pd.to_numeric(college["pts"], errors="coerce")
college["ast"] = pd.to_numeric(college["ast"], errors="coerce")
college["treb"] = pd.to_numeric(college["treb"], errors="coerce")
college = college.dropna(subset=["year", "GP"])

# Add normalized name column
college["_norm"] = college["player_name"].apply(
    lambda x: normalize_name(str(x)) if pd.notna(x) else "")

# Build reverse alias map: CSV name -> BRef name
alias_rev = {normalize_name(v): k for k, v in NAME_ALIASES.items()}

print("=" * 80)
print("WRONG SEASON ANALYSIS V3 - Direct stat fingerprinting")
print("=" * 80)

db_college = [p for p in db if p.get("has_college_stats")]

wrong_season = []
correct = []
no_match = []

for p in db_college:
    name = p["name"]
    db_ppg = p["stats"].get("ppg", 0)
    db_rpg = p["stats"].get("rpg", 0)
    db_apg = p["stats"].get("apg", 0)
    db_mpg = p["stats"].get("mpg", 0)

    norm = normalize_name(name)
    # Also check alias
    alias = NAME_ALIASES.get(name, None)
    alias_norm = normalize_name(alias) if alias else None

    # Find ALL rows matching this player name (by normalized or alias)
    mask = college["_norm"] == norm
    if alias_norm:
        mask = mask | (college["_norm"] == alias_norm)
    rows = college[mask].copy()

    if len(rows) == 0:
        no_match.append(name)
        continue

    if len(rows) == 1:
        correct.append(name)
        continue

    # Multiple rows — fingerprint which one the DB matches
    rows = rows.sort_values("year", ascending=True).reset_index(drop=True)

    best_idx = -1
    best_diff = 999
    for i, row in rows.iterrows():
        # Use multiple stats for fingerprinting
        diff = (abs(db_ppg - (row["pts"] if pd.notna(row["pts"]) else 0)) +
                abs(db_rpg - (row["treb"] if pd.notna(row["treb"]) else 0)) * 0.5 +
                abs(db_apg - (row["ast"] if pd.notna(row["ast"]) else 0)) * 0.5 +
                abs(db_mpg - (row["mp"] if pd.notna(row["mp"]) else 0)) * 0.1)
        if diff < best_diff:
            best_diff = diff
            best_idx = i

    if best_diff > 3.0:
        # Can't confidently match any row
        continue

    matched_row = rows.loc[best_idx]
    matched_year = int(matched_row["year"])

    # Find the LATEST season with GP >= 10 (what pipeline should pick)
    playable = rows[rows["GP"] >= 10]
    if len(playable) == 0:
        continue
    latest_playable = playable.sort_values("year", ascending=False).iloc[0]
    latest_year = int(latest_playable["year"])

    if matched_year < latest_year:
        # DB has an EARLIER season than the latest playable one
        matched_yr_label = str(matched_row.get("yr", "?"))
        latest_yr_label = str(latest_playable.get("yr", "?"))
        wrong_season.append({
            "name": name,
            "draft_year": p.get("draft_year"),
            "draft_pick": p.get("draft_pick"),
            "tier": p["tier"],
            "college": p.get("college", ""),
            "db_ppg": db_ppg,
            "db_rpg": db_rpg,
            "db_apg": db_apg,
            "db_mpg": db_mpg,
            "matched_yr": matched_yr_label,
            "matched_year": matched_year,
            "matched_team": str(matched_row.get("team", "")),
            "matched_gp": int(matched_row["GP"]) if pd.notna(matched_row["GP"]) else 0,
            "latest_ppg": float(latest_playable["pts"]) if pd.notna(latest_playable["pts"]) else 0,
            "latest_rpg": float(latest_playable["treb"]) if pd.notna(latest_playable["treb"]) else 0,
            "latest_apg": float(latest_playable["ast"]) if pd.notna(latest_playable["ast"]) else 0,
            "latest_mpg": float(latest_playable["mp"]) if pd.notna(latest_playable["mp"]) else 0,
            "latest_yr": latest_yr_label,
            "latest_year": latest_year,
            "latest_team": str(latest_playable.get("team", "")),
            "latest_gp": int(latest_playable["GP"]) if pd.notna(latest_playable["GP"]) else 0,
            "all_seasons": [
                {"yr": str(r.get("yr","")), "year": int(r["year"]),
                 "team": str(r.get("team","")), "gp": int(r["GP"]) if pd.notna(r["GP"]) else 0,
                 "ppg": round(float(r["pts"]),1) if pd.notna(r["pts"]) else 0}
                for _, r in rows.iterrows()
            ]
        })
    else:
        correct.append(name)

print("\n--- RESULTS ---")
print("Players with college stats: %d" % len(db_college))
print("Correct (latest season):    %d" % len(correct))
print("WRONG (earlier season):     %d" % len(wrong_season))
print("No CSV match:               %d" % len(no_match))

if wrong_season:
    wrong_season.sort(key=lambda x: (x["tier"], x.get("draft_pick") or 99))

    # Separate name collisions from real problems
    print("\n\n--- WRONG SEASON DETAILS ---")
    print("(Check: does matched_team match the player's actual college?)\n")

    for w in wrong_season:
        same_school = w["college"].lower() in w["matched_team"].lower() or w["matched_team"].lower() in w["college"].lower()
        collision_flag = "" if same_school else " ** LIKELY NAME COLLISION **"

        ppg_diff = w["latest_ppg"] - w["db_ppg"]

        print("%s (T%d, %s, draft %s #%s)%s" % (
            w["name"], w["tier"], w["college"],
            w.get("draft_year"), w.get("draft_pick"), collision_flag))
        print("  DB stats match: %s at %s (year=%d, GP=%d) ppg=%.1f rpg=%.1f apg=%.1f mpg=%.1f" % (
            w["matched_yr"], w["matched_team"], w["matched_year"], w["matched_gp"],
            w["db_ppg"], w["db_rpg"], w["db_apg"], w["db_mpg"]))
        print("  Latest avail:   %s at %s (year=%d, GP=%d) ppg=%.1f rpg=%.1f apg=%.1f mpg=%.1f" % (
            w["latest_yr"], w["latest_team"], w["latest_year"], w["latest_gp"],
            w["latest_ppg"], w["latest_rpg"], w["latest_apg"], w["latest_mpg"]))
        print("  All seasons: %s" %
              ", ".join(["%s/%d@%s(GP=%d,ppg=%.1f)" % (s["yr"], s["year"], s["team"], s["gp"], s["ppg"])
                        for s in w["all_seasons"]]))
        print("  PPG delta: %+.1f" % ppg_diff)
        print()

    # Summary
    same_school_wrong = [w for w in wrong_season
                         if w["college"].lower() in w["matched_team"].lower()
                         or w["matched_team"].lower() in w["college"].lower()]
    diff_school = [w for w in wrong_season if w not in same_school_wrong]

    print("\n--- CLASSIFICATION ---")
    print("Same school (REAL wrong season): %d" % len(same_school_wrong))
    print("Different school (name collision, DB may be correct): %d" % len(diff_school))

    if same_school_wrong:
        print("\n  REAL WRONG SEASON (same school):")
        for w in same_school_wrong:
            print("    %s: DB=%s(yr=%d) ppg=%.1f -> should be %s(yr=%d) ppg=%.1f" % (
                w["name"], w["matched_yr"], w["matched_year"], w["db_ppg"],
                w["latest_yr"], w["latest_year"], w["latest_ppg"]))
