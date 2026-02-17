"""Generate a data audit CSV for human review.

Outputs:
  audit/data_audit.csv   - CRITICAL/HIGH/MEDIUM players needing human review (~97 rows)
  audit/data_summary.csv - Overall data health dashboard

The user reviews data_audit.csv in Excel, fills in CORRECT_* and ACTION columns,
then returns it for automated fixes.
"""
import sys, os, json, zipfile, csv
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EXCLUDE_PLAYERS, ZIP_PATH, ZIP_FILES, PROCESSED_DIR

DB_PATH = os.path.join(PROCESSED_DIR, "player_db.json")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_CSV = os.path.join(OUT_DIR, "data_audit.csv")
SUMMARY_CSV = os.path.join(OUT_DIR, "data_summary.csv")

# ── Load data ──────────────────────────────────────────────────────────
with open(DB_PATH) as f:
    db = json.load(f)

print(f"Loaded {len(db)} players from player_db.json")

# Load college CSV to check class year + name availability
import pandas as pd
with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college1 = pd.read_csv(f, low_memory=False)
    with z.open(ZIP_FILES["college_2022"]) as f:
        college2 = pd.read_csv(f, low_memory=False)
college = pd.concat([college1, college2], ignore_index=True)

# Build lookup: latest season per player
college["year"] = pd.to_numeric(college["year"], errors="coerce")
college["GP"] = pd.to_numeric(college["GP"], errors="coerce")
college = college.dropna(subset=["year", "GP"])
college = college[college["GP"] >= 10]
latest = college.sort_values("year", ascending=False).drop_duplicates("player_name")
college_lookup = {str(row["player_name"]).strip(): row for _, row in latest.iterrows()}

# Also build a list of all college player names for fuzzy match suggestions
all_college_names = set(college_lookup.keys())

# Class year mapping
YR_MAP = {"Fr": 1, "So": 2, "Jr": 3, "Sr": 4}

# ── Helper: suggest similar names in college CSV ──
def suggest_college_match(bref_name, college_str):
    """Try to find similar names in college CSV for a failed match."""
    # Check if last name matches any college player at same school
    parts = bref_name.split()
    if len(parts) < 2:
        return ""
    last = parts[-1].lower()
    suggestions = []
    for cn in all_college_names:
        cn_parts = cn.split()
        if len(cn_parts) < 2:
            continue
        cn_last = cn_parts[-1].lower()
        # Same last name
        if cn_last == last:
            crow = college_lookup[cn]
            cn_team = str(crow.get("team", "")).strip()
            # If college matches too, strong suggestion
            if college_str and college_str.lower() in cn_team.lower():
                suggestions.insert(0, f"{cn} ({cn_team})")
            else:
                suggestions.append(f"{cn} ({cn_team})")
    if suggestions:
        return "; ".join(suggestions[:3])
    return ""


# ── Analyze each player ───────────────────────────────────────────────
all_rows = []  # All issues (for summary stats)
review_rows = []  # Only CRITICAL/HIGH/MEDIUM (for audit sheet)

# Track systemic issue counts
systemic_counts = Counter()

for p in db:
    name = p["name"]
    issues = []
    priority = "LOW"

    has_stats = p.get("has_college_stats", False)
    draft_yr = p.get("draft_year")
    stats = p.get("stats", {})

    # ── Issue 1: EXCLUDE_PLAYERS (wrong name match) ──
    if name in EXCLUDE_PLAYERS:
        issues.append("WRONG_MATCH: College data likely from wrong person")
        priority = "CRITICAL"

    # ── Issue 2: No college stats ──
    if not has_stats:
        if draft_yr and draft_yr >= 2009:
            issues.append("NO_COLLEGE_STATS: Drafted 2009+ but failed name match")
            priority = max(priority, "HIGH", key=["LOW","MEDIUM","HIGH","CRITICAL"].index)
        else:
            systemic_counts["bref_only_pre2009"] += 1

    # ── Issue 3: Zero advanced stats despite having college stats ──
    if has_stats:
        zero_advanced = []
        for key in ["bpm", "obpm", "dbpm", "stl_per", "usg"]:
            if stats.get(key, 0) == 0:
                zero_advanced.append(key)
        if zero_advanced:
            issues.append(f"ZERO_ADVANCED: {', '.join(zero_advanced)} = 0")
            priority = max(priority, "MEDIUM", key=["LOW","MEDIUM","HIGH","CRITICAL"].index)

    # ── Issue 4: Suspicious stat values ──
    if has_stats:
        if stats.get("mpg", 0) < 15 and stats.get("gp", 0) > 0:
            issues.append(f"LOW_MPG: {stats['mpg']} mpg")
            if priority == "LOW":
                priority = "MEDIUM"
        if stats.get("ppg", 0) == 0 and stats.get("gp", 0) > 20:
            issues.append("ZERO_PPG: 0.0 ppg with games played")
            priority = "MEDIUM"
        if stats.get("fg", 0) > 75:
            issues.append(f"HIGH_EFG: {stats['fg']}%")
            priority = "MEDIUM"
        if stats.get("ft", 0) > 100 or stats.get("threeP", 0) > 100:
            issues.append("PCT_OVER_100: scaling error")
            priority = "MEDIUM"
        if stats.get("fta", 0) > 15:
            issues.append(f"HIGH_FTA: {stats['fta']} fta/g")
            priority = "MEDIUM"

    # ── Track systemic issues (don't put in audit sheet) ──
    if p["w"] == 200:
        systemic_counts["weight_placeholder"] += 1
    if p["ws"] == p["h"] + 4:
        systemic_counts["wingspan_estimated"] += 1
    if has_stats:
        csv_yr = None
        if name in college_lookup:
            raw_yr = college_lookup[name].get("yr")
            if pd.notna(raw_yr):
                csv_yr = str(raw_yr).strip()
        if csv_yr and csv_yr in YR_MAP:
            systemic_counts["class_year_recoverable"] += 1
        else:
            systemic_counts["class_year_missing"] += 1

    # ── Build row if actionable ──
    if issues and priority in ("CRITICAL", "HIGH", "MEDIUM"):
        # For HIGH (failed name match), try to suggest correct CSV name
        csv_suggestion = ""
        csv_yr_val = ""
        if not has_stats and draft_yr and draft_yr >= 2009:
            csv_suggestion = suggest_college_match(name, p.get("college", ""))

        # For players with stats, check class year
        if has_stats and name in college_lookup:
            raw_yr = college_lookup[name].get("yr")
            if pd.notna(raw_yr):
                yr_str = str(raw_yr).strip()
                if yr_str in YR_MAP:
                    csv_yr_val = yr_str

        row = {
            "PRIORITY": priority,
            "NAME": name,
            "DRAFT_YEAR": draft_yr or "",
            "DRAFT_PICK": p.get("draft_pick", ""),
            "COLLEGE_IN_DB": p.get("college", ""),
            "POS": p["pos"],
            "HEIGHT_IN": p["h"],
            "TIER": p["tier"],
            "OUTCOME": p.get("outcome", ""),
            "NBA_WS": p.get("nba_ws", ""),
            "HAS_COLLEGE_STATS": has_stats,
            "ISSUES": " | ".join(issues),
            "CSV_NAME_SUGGESTION": csv_suggestion,
            # ── Columns for user to fill in ──
            "CORRECT_COLLEGE": "",
            "CORRECT_CSV_NAME": "",  # Name as it appears in college CSV
            "CORRECT_HEIGHT_IN": "",
            "CORRECT_WEIGHT_LBS": "",
            "ACTION": "",  # KEEP / REMOVE / FIX_NAME / SKIP
            "NOTES": "",
        }
        review_rows.append(row)

    all_rows.append({"priority": priority, "issues": issues})

# ── Sort by priority then draft year (recent first) ──
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
review_rows.sort(key=lambda r: (
    PRIORITY_ORDER.get(r["PRIORITY"], 9),
    -(r["DRAFT_YEAR"] if isinstance(r["DRAFT_YEAR"], int) else 0),
    r["NAME"]
))

# ── Write audit CSV ──
fieldnames = [
    "PRIORITY", "NAME", "DRAFT_YEAR", "DRAFT_PICK", "COLLEGE_IN_DB",
    "POS", "HEIGHT_IN", "TIER", "OUTCOME", "NBA_WS", "HAS_COLLEGE_STATS",
    "ISSUES", "CSV_NAME_SUGGESTION",
    "CORRECT_COLLEGE", "CORRECT_CSV_NAME", "CORRECT_HEIGHT_IN",
    "CORRECT_WEIGHT_LBS", "ACTION", "NOTES"
]

with open(AUDIT_CSV, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(review_rows)

print(f"\nWrote {len(review_rows)} rows to data_audit.csv")

# ── Priority breakdown ──
pri_counts = Counter(r["priority"] for r in all_rows)
for pri in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
    print(f"  {pri}: {pri_counts.get(pri, 0)}")

# ── Generate summary CSV ──
summary_rows = []
summary_rows.append({"METRIC": "=== DATABASE OVERVIEW ===", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "Total players in DB", "VALUE": len(db), "NOTE": ""})
summary_rows.append({"METRIC": "With college stats (archetype engine uses these)", "VALUE": sum(1 for p in db if p.get("has_college_stats")), "NOTE": ""})
summary_rows.append({"METRIC": "BRef-only (outcome comps only)", "VALUE": sum(1 for p in db if not p.get("has_college_stats")), "NOTE": ""})
summary_rows.append({"METRIC": "", "VALUE": "", "NOTE": ""})

summary_rows.append({"METRIC": "=== NEEDS YOUR REVIEW (in data_audit.csv) ===", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "CRITICAL: Wrong name matches", "VALUE": pri_counts.get("CRITICAL", 0), "NOTE": "Bad data poisoning comps. ACTION: REMOVE or provide correct CSV name"})
summary_rows.append({"METRIC": "HIGH: 2009+ failed name matches", "VALUE": pri_counts.get("HIGH", 0), "NOTE": "Recent players with no college stats. ACTION: provide correct CSV name or SKIP"})
summary_rows.append({"METRIC": "MEDIUM: Suspicious values", "VALUE": pri_counts.get("MEDIUM", 0), "NOTE": "Zero advanced stats or weird values. ACTION: investigate or KEEP"})
summary_rows.append({"METRIC": "", "VALUE": "", "NOTE": ""})

summary_rows.append({"METRIC": "=== SYSTEMIC ISSUES (auto-fixable, no manual review) ===", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "Class years recoverable from CSV", "VALUE": systemic_counts["class_year_recoverable"], "NOTE": "Pipeline will auto-fix: read 'yr' column from college CSV"})
summary_rows.append({"METRIC": "Class years NOT in CSV", "VALUE": systemic_counts["class_year_missing"], "NOTE": "Would need manual lookup or new data source"})
summary_rows.append({"METRIC": "Weight = 200 placeholder", "VALUE": systemic_counts["weight_placeholder"], "NOTE": "No weight in college CSV at all. Need scrape or manual."})
summary_rows.append({"METRIC": "Wingspan = h+4 estimate", "VALUE": systemic_counts["wingspan_estimated"], "NOTE": "Need NBA Combine data scrape"})
summary_rows.append({"METRIC": "BRef-only pre-2009 (expected)", "VALUE": systemic_counts["bref_only_pre2009"], "NOTE": "These are fine - college CSV only covers 2009-2022"})
summary_rows.append({"METRIC": "", "VALUE": "", "NOTE": ""})

summary_rows.append({"METRIC": "=== HOW TO USE data_audit.csv ===", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "1. Open data_audit.csv in Excel", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "2. For CRITICAL rows:", "VALUE": "", "NOTE": "Set ACTION=REMOVE to delete, or fill CORRECT_CSV_NAME to re-match"})
summary_rows.append({"METRIC": "3. For HIGH rows:", "VALUE": "", "NOTE": "Check CSV_NAME_SUGGESTION. If correct, copy to CORRECT_CSV_NAME + ACTION=FIX_NAME"})
summary_rows.append({"METRIC": "4. For MEDIUM rows:", "VALUE": "", "NOTE": "Check if stat values look wrong. ACTION=KEEP if fine, ACTION=REMOVE if garbage"})
summary_rows.append({"METRIC": "5. Save and return the file", "VALUE": "", "NOTE": "I will apply all fixes automatically"})
summary_rows.append({"METRIC": "", "VALUE": "", "NOTE": ""})

summary_rows.append({"METRIC": "=== ACTION VALUES ===", "VALUE": "", "NOTE": ""})
summary_rows.append({"METRIC": "KEEP", "VALUE": "", "NOTE": "Data is fine as-is, no changes needed"})
summary_rows.append({"METRIC": "REMOVE", "VALUE": "", "NOTE": "Delete this player from the database"})
summary_rows.append({"METRIC": "FIX_NAME", "VALUE": "", "NOTE": "Re-match using CORRECT_CSV_NAME column"})
summary_rows.append({"METRIC": "SKIP", "VALUE": "", "NOTE": "Not worth fixing right now, leave as-is"})

with open(SUMMARY_CSV, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["METRIC", "VALUE", "NOTE"])
    writer.writeheader()
    writer.writerows(summary_rows)

print(f"Wrote summary to data_summary.csv")

# ── Print action items ──
print(f"\n{'='*60}")
print("DATA AUDIT COMPLETE")
print(f"{'='*60}")
print(f"\nFiles in: {OUT_DIR}")
print(f"  data_audit.csv   - {len(review_rows)} players to review")
print(f"  data_summary.csv - Dashboard + instructions")
print(f"\nQUICK WINS (I can auto-fix without your input):")
print(f"  - {systemic_counts['class_year_recoverable']} class years from CSV 'yr' column")
print(f"\nNEEDS YOUR EYES ({len(review_rows)} rows):")
print(f"  - {pri_counts.get('CRITICAL', 0)} CRITICAL: wrong matches to remove/fix")
print(f"  - {pri_counts.get('HIGH', 0)} HIGH: name match failures to resolve")
print(f"  - {pri_counts.get('MEDIUM', 0)} MEDIUM: suspicious stat values")
print(f"\nSYSTEMIC (decision needed, not per-player):")
print(f"  - Weight: no source exists. Scrape from new source?")
print(f"  - Wingspan: no source exists. Scrape NBA Combine data?")
