"""Investigate how many players in player_db.json have the wrong season's stats.

Checks:
1. Players who played multiple seasons but DB has their earliest (worst) stats
2. Players whose DB stats don't match their FINAL season in the CSV
3. Scope of the 2021-22 and 2022-23 data gap
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR

# Load data
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

# Build lookup: ALL seasons per player
from collections import defaultdict, Counter
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
print("WRONG SEASON ANALYSIS")
print("=" * 70)

wrong_season = []
correct_season = []
single_season = []
not_in_csv = []

db_college = [p for p in db if p.get("has_college_stats")]

for p in db_college:
    name = p["name"]
    db_ppg = p["stats"].get("ppg", 0)
    db_mpg = p["stats"].get("mpg", 0)

    if name not in player_seasons:
        not_in_csv.append(name)
        continue

    seasons = player_seasons[name]
    if len(seasons) == 1:
        single_season.append(name)
        continue

    final_season = seasons[-1]
    first_season = seasons[0]

    # Check which season the DB stats match (use PPG as fingerprint)
    best_match_idx = -1
    best_match_diff = 999
    for i, s in enumerate(seasons):
        diff = abs(db_ppg - s["pts"])
        if diff < best_match_diff:
            best_match_diff = diff
            best_match_idx = i

    is_final = (best_match_idx == len(seasons) - 1)

    if not is_final and best_match_diff < 1.0:
        matched_season = seasons[best_match_idx]
        wrong_season.append({
            "name": name,
            "draft_year": p.get("draft_year"),
            "draft_pick": p.get("draft_pick"),
            "tier": p["tier"],
            "db_ppg": db_ppg,
            "db_mpg": db_mpg,
            "db_season_yr": matched_season["yr"],
            "db_season_year": matched_season["year"],
            "db_season_team": matched_season["team"],
            "final_ppg": final_season["pts"],
            "final_mpg": final_season["mp"],
            "final_yr": final_season["yr"],
            "final_year": final_season["year"],
            "final_team": final_season["team"],
            "num_seasons": len(seasons),
            "season_matched": best_match_idx,
        })
    else:
        correct_season.append(name)

print("\n--- SEASON MATCH RESULTS ---")
print("Players with college stats: %d" % len(db_college))
print("Single season (no issue):   %d" % len(single_season))
print("Correct final season:       %d" % len(correct_season))
print("WRONG SEASON (not final):   %d" % len(wrong_season))
print("Not found in CSV:           %d" % len(not_in_csv))

if wrong_season:
    print("\n--- WRONG SEASON DETAILS (sorted by tier, then draft pick) ---")
    wrong_season.sort(key=lambda x: (x["tier"], (x.get("draft_pick") or 99)))
    for w in wrong_season:
        ppg_diff = w["final_ppg"] - w["db_ppg"]
        mpg_diff = w["final_mpg"] - w["db_mpg"]
        print("\n  %s (draft %s #%s, tier %s, %d seasons in CSV)" % (
            w["name"], w.get("draft_year"), w.get("draft_pick"), w["tier"], w["num_seasons"]))
        print("    DB has: %s at %s (year=%s) - ppg=%.1f mpg=%.1f" % (
            w["db_season_yr"], w["db_season_team"], w["db_season_year"], w["db_ppg"], w["db_mpg"]))
        print("    Should: %s at %s (year=%s) - ppg=%.1f mpg=%.1f" % (
            w["final_yr"], w["final_team"], w["final_year"], w["final_ppg"], w["final_mpg"]))
        print("    Impact: ppg %+.1f, mpg %+.1f" % (ppg_diff, mpg_diff))

# --- CHECK 2: Draft year vs CSV coverage gap ---
print("\n\n--- DATA COVERAGE BY DRAFT YEAR (2009+) ---")
draft_years = defaultdict(lambda: {"total": 0, "has_stats": 0, "bref_only": 0})
for p in db:
    dy = p.get("draft_year")
    if dy:
        draft_years[dy]["total"] += 1
        if p.get("has_college_stats"):
            draft_years[dy]["has_stats"] += 1
        else:
            draft_years[dy]["bref_only"] += 1

print("\nDraft Year | Total | College Stats | BRef-Only | Coverage")
for yr in sorted(draft_years.keys()):
    if yr >= 2009:
        d = draft_years[yr]
        pct = d["has_stats"] / d["total"] * 100 if d["total"] > 0 else 0
        print("  %d    |  %3d  |     %3d       |    %3d    |  %5.1f%%" % (
            yr, d["total"], d["has_stats"], d["bref_only"], pct))

# --- CHECK 3: Summary stats ---
print("\n\n--- IMPACT SUMMARY ---")
if wrong_season:
    ppg_diffs = [w["final_ppg"] - w["db_ppg"] for w in wrong_season]
    mpg_diffs = [w["final_mpg"] - w["db_mpg"] for w in wrong_season]
    print("Wrong-season players: %d" % len(wrong_season))

    has_freshman = sum(1 for w in wrong_season if w["db_season_yr"] == "Fr")
    has_sophomore = sum(1 for w in wrong_season if w["db_season_yr"] == "So")
    has_junior = sum(1 for w in wrong_season if w["db_season_yr"] == "Jr")
    print("  Stuck on Freshman stats:  %d" % has_freshman)
    print("  Stuck on Sophomore stats: %d" % has_sophomore)
    print("  Stuck on Junior stats:    %d" % has_junior)

    print("\n  PPG impact if corrected to final season:")
    print("    Avg change: %+.1f ppg" % np.mean(ppg_diffs))
    print("    Median:     %+.1f ppg" % np.median(ppg_diffs))
    print("    Max increase: %+.1f ppg" % max(ppg_diffs))

    print("\n  MPG impact if corrected:")
    print("    Avg change: %+.1f mpg" % np.mean(mpg_diffs))
    print("    Median:     %+.1f mpg" % np.median(mpg_diffs))

    tier_dist = Counter(w["tier"] for w in wrong_season)
    print("\n  Tiers affected:")
    for t in sorted(tier_dist):
        print("    Tier %d: %d players" % (t, tier_dist[t]))

    # Check: how many have SIGNIFICANT stat differences
    big_ppg_diff = [w for w in wrong_season if abs(w["final_ppg"] - w["db_ppg"]) > 3.0]
    big_mpg_diff = [w for w in wrong_season if abs(w["final_mpg"] - w["db_mpg"]) > 5.0]
    print("\n  Severity:")
    print("    PPG off by >3 points:  %d players" % len(big_ppg_diff))
    print("    MPG off by >5 minutes: %d players" % len(big_mpg_diff))
