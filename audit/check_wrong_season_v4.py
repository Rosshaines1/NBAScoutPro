"""V4: Final analysis. For each DB player with multiple CSV rows, determine:
1. Is the DB actually using their data, or a different person with same name?
2. If it IS their data, is it their final season or an earlier one?

Key insight: if DB draft_year is within ~2 years of the CSV season year,
it's likely the same person. If it's decades off, it's a name collision.
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR
from pipeline.build_player_db import normalize_name, NAME_ALIASES

with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
    db = json.load(f)

with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college = pd.read_csv(f, low_memory=False)

for col in ["year", "GP", "mp", "pts", "ast", "treb", "stl", "blk"]:
    college[col] = pd.to_numeric(college[col], errors="coerce")
college = college.dropna(subset=["year", "GP"])
college["_norm"] = college["player_name"].apply(
    lambda x: normalize_name(str(x)) if pd.notna(x) else "")

db_college = [p for p in db if p.get("has_college_stats")]

real_wrong_season = []
name_collision_wrong = []
correct = []

for p in db_college:
    name = p["name"]
    draft_year = p.get("draft_year") or 2020  # fallback
    db_ppg = p["stats"].get("ppg", 0)
    db_rpg = p["stats"].get("rpg", 0)
    db_apg = p["stats"].get("apg", 0)
    db_mpg = p["stats"].get("mpg", 0)
    db_college_name = p.get("college", "").lower()

    norm = normalize_name(name)
    alias = NAME_ALIASES.get(name, None)
    alias_norm = normalize_name(alias) if alias else None

    mask = college["_norm"] == norm
    if alias_norm:
        mask = mask | (college["_norm"] == alias_norm)
    rows = college[mask].copy()

    if len(rows) <= 1:
        correct.append(name)
        continue

    # Fingerprint: which row does DB match?
    best_idx = -1
    best_diff = 999
    for idx, row in rows.iterrows():
        diff = (abs(db_ppg - (row["pts"] if pd.notna(row["pts"]) else 0)) +
                abs(db_rpg - (row["treb"] if pd.notna(row["treb"]) else 0)) * 0.5 +
                abs(db_apg - (row["ast"] if pd.notna(row["ast"]) else 0)) * 0.5 +
                abs(db_mpg - (row["mp"] if pd.notna(row["mp"]) else 0)) * 0.1)
        if diff < best_diff:
            best_diff = diff
            best_idx = idx

    if best_diff > 3.0:
        correct.append(name)
        continue

    matched_row = rows.loc[best_idx]
    matched_year = int(matched_row["year"])
    matched_team = str(matched_row.get("team", ""))

    # Separate CSV rows into "this person" vs "different person"
    # This person: played at or near the same time as draft year
    # The player's college career ends at draft_year (or draft_year - 1 for season labeling)
    # So their seasons should be in range [draft_year - 5, draft_year]
    own_rows = rows[(rows["year"] >= draft_year - 5) & (rows["year"] <= draft_year)]

    # Also include rows at the same school as the DB college regardless of year
    school_rows = rows[rows["team"].str.lower().str.contains(db_college_name[:6], na=False)
                       | rows["team"].apply(lambda t: db_college_name in str(t).lower())]
    own_rows = pd.concat([own_rows, school_rows]).drop_duplicates()

    if len(own_rows) <= 1:
        correct.append(name)
        continue

    # Among this person's rows, find their latest season with GP >= 10
    playable = own_rows[own_rows["GP"] >= 10]
    if len(playable) == 0:
        correct.append(name)
        continue

    latest = playable.sort_values("year", ascending=False).iloc[0]
    latest_year = int(latest["year"])

    if matched_year < latest_year:
        # DB has an earlier season. Is the matched row actually this person's?
        is_matched_own = matched_year >= draft_year - 5 and matched_year <= draft_year

        entry = {
            "name": name,
            "draft_year": p.get("draft_year"),
            "draft_pick": p.get("draft_pick"),
            "tier": p["tier"],
            "college": p.get("college", ""),
            "db_ppg": db_ppg, "db_rpg": db_rpg, "db_apg": db_apg, "db_mpg": db_mpg,
            "matched_yr": str(matched_row.get("yr", "?")),
            "matched_year": matched_year,
            "matched_team": matched_team,
            "matched_gp": int(matched_row["GP"]),
            "latest_ppg": float(latest["pts"]) if pd.notna(latest["pts"]) else 0,
            "latest_rpg": float(latest["treb"]) if pd.notna(latest["treb"]) else 0,
            "latest_apg": float(latest["ast"]) if pd.notna(latest["ast"]) else 0,
            "latest_mpg": float(latest["mp"]) if pd.notna(latest["mp"]) else 0,
            "latest_yr": str(latest.get("yr", "?")),
            "latest_year": latest_year,
            "latest_team": str(latest.get("team", "")),
            "latest_gp": int(latest["GP"]),
            "own_seasons": [
                {"yr": str(r.get("yr","")), "year": int(r["year"]),
                 "team": str(r.get("team","")),
                 "gp": int(r["GP"]) if pd.notna(r["GP"]) else 0,
                 "ppg": round(float(r["pts"]),1) if pd.notna(r["pts"]) else 0}
                for _, r in own_rows.sort_values("year").iterrows()
            ]
        }

        if is_matched_own:
            real_wrong_season.append(entry)
        else:
            name_collision_wrong.append(entry)
    else:
        correct.append(name)

print("=" * 80)
print("WRONG SEASON V4 - FINAL ANALYSIS")
print("=" * 80)
print("\nPlayers with college stats:     %d" % len(db_college))
print("Correct (latest season or N/A): %d" % len(correct))
print("REAL wrong season (same person):%d" % len(real_wrong_season))
print("Name collision (diff person):   %d" % len(name_collision_wrong))

if real_wrong_season:
    print("\n\n=== REAL WRONG SEASON (DB has this person's earlier season) ===")
    real_wrong_season.sort(key=lambda x: (x["tier"], x.get("draft_pick") or 99))
    for w in real_wrong_season:
        ppg_diff = w["latest_ppg"] - w["db_ppg"]
        print("\n%s (T%d, %s, draft %s #%s)" % (
            w["name"], w["tier"], w["college"], w["draft_year"], w["draft_pick"]))
        print("  DB has:  %s at %s (year=%d, GP=%d) ppg=%.1f rpg=%.1f apg=%.1f" % (
            w["matched_yr"], w["matched_team"], w["matched_year"], w["matched_gp"],
            w["db_ppg"], w["db_rpg"], w["db_apg"]))
        print("  Should:  %s at %s (year=%d, GP=%d) ppg=%.1f rpg=%.1f apg=%.1f" % (
            w["latest_yr"], w["latest_team"], w["latest_year"], w["latest_gp"],
            w["latest_ppg"], w["latest_rpg"], w["latest_apg"]))
        print("  PPG delta: %+.1f" % ppg_diff)
        print("  Seasons: %s" %
              ", ".join(["%s/%d@%s(GP=%d,ppg=%.1f)" % (s["yr"], s["year"], s["team"], s["gp"], s["ppg"])
                        for s in w["own_seasons"]]))

if name_collision_wrong:
    print("\n\n=== NAME COLLISIONS (DB matched a different person's earlier season) ===")
    print("These need FORCE_BREF_ONLY or college-aware disambiguation fixes")
    name_collision_wrong.sort(key=lambda x: (x["tier"], x.get("draft_pick") or 99))
    for w in name_collision_wrong:
        print("\n%s (T%d, %s, draft %s #%s)" % (
            w["name"], w["tier"], w["college"], w["draft_year"], w["draft_pick"]))
        print("  DB has:  %s at %s (year=%d) ppg=%.1f" % (
            w["matched_yr"], w["matched_team"], w["matched_year"], w["db_ppg"]))
        print("  CSV has: %s at %s (year=%d) ppg=%.1f" % (
            w["latest_yr"], w["latest_team"], w["latest_year"], w["latest_ppg"]))
        print("  Seasons: %s" %
              ", ".join(["%s/%d@%s(GP=%d,ppg=%.1f)" % (s["yr"], s["year"], s["team"], s["gp"], s["ppg"])
                        for s in w["own_seasons"]]))
