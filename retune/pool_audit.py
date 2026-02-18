"""Audit comp pool — who's in there that shouldn't be?"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

college = [p for p in db if p.get("has_college_stats")]

# Group by draft year
by_year = {}
for p in college:
    yr = p.get("draft_year") or "None"
    if yr not in by_year:
        by_year[yr] = []
    by_year[yr].append(p)

print("=== COLLEGE-STATS PLAYERS BY DRAFT YEAR ===")
for yr in sorted(by_year.keys(), key=lambda x: str(x)):
    players = by_year[yr]
    has_ws = sum(1 for p in players if p.get("nba_ws") is not None)
    print(f"  {yr}: {len(players):3d} players ({has_ws} with outcomes)")

# Show some pre-2009 examples
print("\n=== PRE-2009 EXAMPLES (should these be here?) ===")
pre09 = [p for p in college if (p.get("draft_year") or 9999) < 2009]
for p in sorted(pre09, key=lambda x: x.get("draft_year") or 0)[:15]:
    s = p.get("stats", {})
    name = p["name"]
    yr = p.get("draft_year")
    ppg = s.get("ppg", 0)
    bpm = s.get("bpm", 0)
    gp = s.get("gp", 0)
    col = p.get("college", "?")
    print(f"  {yr} {name:25s} {col:20s} PPG={ppg:5.1f} BPM={bpm:5.1f} GP={gp:.0f}")

# Show post-2019 examples
print("\n=== POST-2019 EXAMPLES (should these be here?) ===")
post19 = [p for p in college if (p.get("draft_year") or 0) > 2019]
for p in sorted(post19, key=lambda x: x.get("draft_year") or 0)[:15]:
    s = p.get("stats", {})
    name = p["name"]
    yr = p.get("draft_year")
    ppg = s.get("ppg", 0)
    bpm = s.get("bpm", 0)
    gp = s.get("gp", 0)
    col = p.get("college", "?")
    ws = p.get("nba_ws")
    ws_str = f"WS={ws:.1f}" if ws is not None else "no WS"
    print(f"  {yr} {name:25s} {col:20s} PPG={ppg:5.1f} BPM={bpm:5.1f} GP={gp:.0f} {ws_str}")

# The real question: how many total should we have?
print(f"\n=== SUMMARY ===")
print(f"Total with college stats: {len(college)}")
print(f"  Pre-2009:  {len(pre09)}")
in_range = [p for p in college if 2009 <= (p.get('draft_year') or 0) <= 2019]
print(f"  2009-2019: {len(in_range)}")
post = [p for p in college if (p.get('draft_year') or 0) > 2019]
print(f"  Post-2019: {len(post)}")
no_yr = [p for p in college if p.get('draft_year') is None]
print(f"  No year:   {len(no_yr)}")
