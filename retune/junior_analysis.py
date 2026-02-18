"""Analyze junior outcomes vs other class years."""
import json, os, sys
from collections import Counter

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, TIER_LABELS

with open(PLAYER_DB_PATH, encoding="utf-8") as f:
    db = json.load(f)

clean = [p for p in db if p.get("has_college_stats")
         and 2009 <= (p.get("draft_year") or 0) <= 2019
         and p.get("nba_ws") is not None]

print(f"Dataset: {len(clean)} players\n")

# Tier distribution by class year
for yr_val, yr_name in [(1, "Freshman"), (2, "Sophomore"), (3, "Junior"), (4, "Senior")]:
    players = [p for p in clean if p.get("age") == yr_val]
    if not players:
        continue
    tiers = Counter(p["tier"] for p in players)
    n = len(players)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"{yr_name} (n={n}):")
    for t in range(1, 6):
        ct = tiers.get(t, 0)
        bar = "#" * int(ct / n * 50)
        print(f"  T{t} {TIER_LABELS.get(t,''):22s} {ct:>4} ({ct/n*100:5.1f}%)  {bar}")
    print(f"  Star rate (T1+T2): {stars/n*100:.1f}%   Bust rate (T4+T5): {busts/n*100:.1f}%")
    print()

# Compare Jr vs So specifically
print("=" * 60)
print("JUNIOR vs SOPHOMORE comparison:\n")
for yr_val, yr_name in [(2, "Sophomore"), (3, "Junior")]:
    players = [p for p in clean if p.get("age") == yr_val]
    n = len(players)
    tiers = Counter(p["tier"] for p in players)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"  {yr_name:12s} n={n:>3}  Star={stars/n*100:5.1f}%  Bust={busts/n*100:5.1f}%  T3={tiers.get(3,0)/n*100:5.1f}%")

# Also check: juniors with high BPM — do they bust more?
print(f"\n\nJUNIORS with BPM >= 7 (same threshold as senior flag):")
jr_high_bpm = [p for p in clean if p.get("age") == 3 and p.get("stats", {}).get("bpm", 0) >= 7]
n = len(jr_high_bpm)
if n:
    tiers = Counter(p["tier"] for p in jr_high_bpm)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"  n={n}  Star={stars/n*100:.1f}%  Bust={busts/n*100:.1f}%")
    for t in range(1, 6):
        print(f"    T{t}: {tiers.get(t, 0)}")

print(f"\nSOPHOMORES with BPM >= 7:")
so_high_bpm = [p for p in clean if p.get("age") == 2 and p.get("stats", {}).get("bpm", 0) >= 7]
n = len(so_high_bpm)
if n:
    tiers = Counter(p["tier"] for p in so_high_bpm)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"  n={n}  Star={stars/n*100:.1f}%  Bust={busts/n*100:.1f}%")
    for t in range(1, 6):
        print(f"    T{t}: {tiers.get(t, 0)}")

print(f"\nJUNIORS with PPG >= 14:")
jr_scorers = [p for p in clean if p.get("age") == 3 and p.get("stats", {}).get("ppg", 0) >= 14]
n = len(jr_scorers)
if n:
    tiers = Counter(p["tier"] for p in jr_scorers)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"  n={n}  Star={stars/n*100:.1f}%  Bust={busts/n*100:.1f}%")

print(f"\nSOPHOMORES with PPG >= 14:")
so_scorers = [p for p in clean if p.get("age") == 2 and p.get("stats", {}).get("ppg", 0) >= 14]
n = len(so_scorers)
if n:
    tiers = Counter(p["tier"] for p in so_scorers)
    stars = tiers.get(1, 0) + tiers.get(2, 0)
    busts = tiers.get(4, 0) + tiers.get(5, 0)
    print(f"  n={n}  Star={stars/n*100:.1f}%  Bust={busts/n*100:.1f}%")
