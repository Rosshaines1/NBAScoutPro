"""Smoke test: verify all core systems work with quadrant model."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from config import *
from app.similarity import (predict_tier, calculate_similarity, classify_archetype,
                             find_archetype_matches, find_top_matches, count_star_signals)

print("1. All imports OK")

# Load DB
with open(PLAYER_DB_PATH) as f:
    db = json.load(f)
print(f"2. Player DB loaded: {len(db)} players")

# Check quadrant field exists
with_quad = sum(1 for p in db if 'quadrant' in p)
print(f"3. Players with quadrant field: {with_quad}/{len(db)}")

# Test predict_tier with quadrant
prospect = {
    'name': 'Test Wing', 'pos': 'W', 'h': 78, 'w': 200, 'ws': 82,
    'age': 2, 'quadrant': 'Q2', 'ath': 0,
    'ppg': 18, 'rpg': 6, 'apg': 3, 'spg': 1.2, 'bpg': 0.5,
    'fg': 52, 'threeP': 35, 'ft': 78, 'tpg': 2.0, 'mpg': 32,
    'bpm': 8.0, 'obpm': 5.0, 'dbpm': 3.0, 'fta': 5.0,
    'stl_per': 2.0, 'usg': 28, 'ftr': 35, 'rim_pct': 65, 'tpa': 4.0,
}
r1 = predict_tier(prospect)
prospect['quadrant'] = 'Q4'
r2 = predict_tier(prospect)
print(f"4. predict_tier Q2: tier={r1['tier']}, score={r1['score']:.0f}")
print(f"   predict_tier Q4: tier={r2['tier']}, score={r2['score']:.0f}")
print(f"   Q4 discount: {r1['score'] - r2['score']:.0f} points")

# Test classify_archetype
prospect['quadrant'] = 'Q1'
arch = classify_archetype(prospect)
print(f"5. classify_archetype: {arch}")

# Test find_top_matches
pos_avgs = POSITIONAL_AVGS
try:
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)
except: pass

matches = find_top_matches(prospect, db, pos_avgs, top_n=5)
print(f"6. find_top_matches: {len(matches)} matches")
for m in matches[:3]:
    if isinstance(m, dict):
        print(f"   {m.get('name', m.get('player', {}).get('name', '?')):25s}")
    else:
        print(f"   match type: {type(m)}")

# Test find_archetype_matches
arch_matches = find_archetype_matches(prospect, db, pos_avgs, top_n=5)
print(f"7. find_archetype_matches: {len(arch_matches)} matches")

# Test calculate_similarity
if len(db) > 2:
    p1 = prospect
    p2 = db[0]
    sim = calculate_similarity(p1, p2, pos_avgs)
    if isinstance(sim, dict):
        print(f"8. calculate_similarity: {sim.get('similarity', sim.get('score', '?'))}%")
    else:
        print(f"8. calculate_similarity: {sim:.1f}%")

# Verify star signals
signals = count_star_signals(prospect)
print(f"9. count_star_signals: {signals[0]} signals, tags={signals[1]}")

# Check rim% data
print(f"\n10. RIM% DATA CHECK:")
clean = [p for p in db if p.get('has_college_stats') and 2009 <= (p.get('draft_year') or 0) <= 2019]
has_rim = sum(1 for p in clean if p['stats'].get('rim_att', 0) > 0)
no_rim = sum(1 for p in clean if p['stats'].get('rim_att', 0) == 0)
print(f"    Players with rim_att > 0: {has_rim}/{len(clean)}")
print(f"    Players with rim_att = 0: {no_rim}/{len(clean)}")

# Sample rim% values
print(f"\n    Sample rim% values:")
for name in ['Zion Williamson', 'Stephen Curry', 'Anthony Davis', 'Damian Lillard',
             'Kawhi Leonard', 'Jimmy Butler', 'Trae Young']:
    p = next((x for x in db if x['name'] == name), None)
    if p:
        s = p['stats']
        rm = s.get('rimmade', 0)
        ra = s.get('rim_att', 0)
        rpct = (rm / ra * 100) if ra > 0 else 0
        print(f"    {name:25s} rimmade={rm:.2f}  rim_att={ra:.2f}  rim%={rpct:.0f}%")

print("\nALL TESTS PASSED")
