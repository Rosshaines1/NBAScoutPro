"""Audit 3: Check age data and data quality for key players."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

# 1. Age distribution
print("=" * 60)
print("  AGE DATA CHECK")
print("=" * 60)
ages = [p.get("age") for p in db if p.get("has_college_stats")]
none_count = sum(1 for a in ages if a is None)
has_age = [a for a in ages if a is not None]
print(f"Total with college stats: {len(ages)}")
print(f"Age = None: {none_count}")
print(f"Age = 22 exactly: {sum(1 for a in has_age if a == 22)}")
print(f"Age has value: {len(has_age)}")
if has_age:
    from collections import Counter
    age_dist = Counter(round(a, 0) for a in has_age)
    for age in sorted(age_dist.keys()):
        print(f"  Age ~{age:.0f}: {age_dist[age]}")

# 2. Check class year / years in school data
print(f"\n{'=' * 60}")
print("  CLASS YEAR / EXPERIENCE DATA")
print("=" * 60)
has_yr = sum(1 for p in db if p.get("yr") is not None)
has_class = sum(1 for p in db if p.get("class") is not None)
has_exp = sum(1 for p in db if p.get("experience") is not None)
print(f"Has 'yr': {has_yr}")
print(f"Has 'class': {has_class}")
print(f"Has 'experience': {has_exp}")

# Check what fields a typical player has
sample = [p for p in db if p.get("has_college_stats")][:3]
for p in sample:
    print(f"\n  Sample: {p['name']}")
    for k, v in p.items():
        if k != "stats":
            print(f"    {k}: {v}")
    print(f"    stats keys: {list(p['stats'].keys())}")

# 3. Data quality check for known problem players
print(f"\n{'=' * 60}")
print("  DATA QUALITY - KNOWN PLAYERS")
print("=" * 60)
check_names = [
    "Donovan Mitchell", "Larry Johnson", "Emeka Okafor",
    "Isaiah Thomas", "Steve Smith", "Kyle Anderson",
    "Jason Richardson", "Donyell Marshall", "Shawn Kemp",
    "DeMar DeRozan", "Devin Booker", "Khris Middleton",
    "Tobias Harris", "Myles Turner",
]
for name in check_names:
    matches = [p for p in db if p["name"] == name]
    if not matches:
        print(f"\n  {name}: NOT FOUND")
        continue
    for p in matches:
        s = p["stats"]
        print(f"\n  {name} (T{p['tier']}, WS={p.get('nba_ws',0):.0f})")
        print(f"    College: {p.get('college', '?')} | Level: {p['level']} | {p['pos']}")
        print(f"    Pick #{p.get('draft_pick','?')} ({p.get('draft_year','?')})")
        print(f"    {s['ppg']:.1f} PPG, {s['rpg']:.1f} RPG, {s['apg']:.1f} APG | {s['mpg']:.1f} MPG")
        print(f"    BPM={s.get('bpm',0):.1f} OBPM={s.get('obpm',0):.1f} FTA={s.get('fta',0):.0f}")
        print(f"    Age: {p.get('age', 'NONE')}")

# 4. Check what BRef data we have for draft year separation
print(f"\n{'=' * 60}")
print("  DRAFT YEAR COVERAGE")
print("=" * 60)
from collections import Counter
years = Counter(p.get("draft_year") for p in db if p.get("has_college_stats"))
for yr in sorted(years.keys()):
    if yr:
        count = years[yr]
        has_bpm = sum(1 for p in db if p.get("draft_year") == yr
                      and p.get("has_college_stats") and p["stats"].get("bpm"))
        print(f"  {yr}: {count} players, {has_bpm} with BPM data")
