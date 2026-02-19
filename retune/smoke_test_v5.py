"""Smoke test: verify player_db loads, similarity engine works, archetype matches work."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS
from app.similarity import (
    calculate_similarity, find_top_matches, find_archetype_matches,
    classify_archetype, predict_tier,
)

# Load data
with open(PLAYER_DB_PATH) as f:
    db = json.load(f)
with open(os.path.join(PROCESSED_DIR, 'positional_avgs.json')) as f:
    pos_avgs = json.load(f)

print(f"Player DB: {len(db)} players")
print(f"Positions: {len(pos_avgs)} types")

# Check data quality
has_bpm = sum(1 for p in db if p['stats'].get('bpm', 0) != 0)
has_fta = sum(1 for p in db if p['stats'].get('fta', 0) > 0)
has_rim = sum(1 for p in db if p['stats'].get('rimmade', 0) > 0)
tbd = sum(1 for p in db if p['tier'] == 6)
print(f"\nData coverage:")
print(f"  Has BPM: {has_bpm}/{len(db)}")
print(f"  Has FTA: {has_fta}/{len(db)}")
print(f"  Has rim data: {has_rim}/{len(db)}")
print(f"  TBD tier: {tbd}")

# Test prospect
prospect = {
    "name": "Test Prospect", "pos": "W", "h": 79, "w": 200, "ws": 83,
    "age": 2, "level": "High Major", "quadrant": "Q1", "ath": 2,
    "ppg": 20.0, "rpg": 6.0, "apg": 3.0, "spg": 1.5, "bpg": 0.5,
    "fg": 52.0, "threeP": 35.0, "ft": 80.0, "tpg": 2.5, "mpg": 33.0,
    "bpm": 8.0, "obpm": 5.0, "dbpm": 3.0, "fta": 5.0, "stl_per": 2.0,
    "usg": 28.0,
}

# Test predict_tier
print("\n--- predict_tier ---")
pred = predict_tier(prospect)
print(f"  Predicted tier: {pred['tier']} ({TIER_LABELS.get(pred['tier'], '?')})")
print(f"  Score: {pred['score']}")
print(f"  Reasons: {pred['reasons'][:3]}")

# Test find_top_matches
print("\n--- find_top_matches (V3 weights) ---")
matches = find_top_matches(prospect, db, pos_avgs, top_n=5, use_v3=True)
for m in matches:
    p = m['player']
    s = m['similarity']
    print(f"  {p['name']:25s} T{p['tier']} score={s['score']:.1f} draft={p.get('draft_year')}")

# Test find_archetype_matches
print("\n--- find_archetype_matches ---")
result = find_archetype_matches(prospect, db, pos_avgs, top_n=5, use_v3=True)
print(f"  Archetype: {result['archetype']} ({result['arch_confidence']:.0f}%)")
if result.get('closest_comp'):
    cc = result['closest_comp']['player']
    print(f"  Closest: {cc['name']} T{cc['tier']}")
if result.get('ceiling_comp'):
    ceil = result['ceiling_comp']['player']
    print(f"  Ceiling: {ceil['name']} T{ceil['tier']}")
if result.get('floor_comp'):
    flr = result['floor_comp']['player']
    print(f"  Floor: {flr['name']} T{flr['tier']}")

# Test classify_archetype on a known player
print("\n--- Archetype classification (sample) ---")
for name in ["Zion Williamson", "Trae Young", "Ja Morant", "Paolo Banchero"]:
    found = [p for p in db if p['name'] == name]
    if found:
        p = found[0]
        arch, score, sec = classify_archetype(p)
        print(f"  {name:25s} -> {arch} ({score:.0f}), secondary={sec}")

print("\nSmoke test PASSED!")
