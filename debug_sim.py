"""Quick debug script to test similarity engine."""
import json, math
from app.similarity import find_top_matches, calculate_similarity

with open('data/processed/player_db.json') as f:
    db = json.load(f)
with open('data/processed/positional_avgs.json') as f:
    pa = json.load(f)

prospect = {
    'name': 'Test', 'pos': 'G', 'h': 75, 'w': 195,
    'ws': 79, 'age': 20.5, 'level': 'High Major', 'ath': 2,
    'ppg': 15.0, 'rpg': 4.5, 'apg': 3.5, 'spg': 1.2, 'bpg': 0.4,
    'fg': 45.0, 'threeP': 35.0, 'ft': 75.0, 'tpg': 2.5, 'mpg': 30.0,
    'bpm': 0, 'obpm': 0, 'dbpm': 0, 'fta': 0,
    'stl_per': 0, 'usg': 0,
}

# Test with first 3 players
for p in db[:3]:
    sim = calculate_similarity(prospect, p, pa, use_v2=True)
    diffs_sum = sum(sim['diffs'].values())
    total_dist = math.sqrt(diffs_sum) + sim['penalty']
    print(f"{p['name']}: score={sim['score']}, penalty={sim['penalty']}, "
          f"sqrt_diffs={math.sqrt(diffs_sum):.2f}, total_dist={total_dist:.2f}")
    print(f"  Top diffs: {sorted(sim['diffs'].items(), key=lambda x: -x[1])[:5]}")
    print(f"  Penalty reasons: {sim['penalty_reasons']}")

print("\nTop 5 matches:")
matches = find_top_matches(prospect, db, pa, top_n=5, use_v2=True)
for m in matches:
    print(f"  {m['player']['name']}: {m['similarity']['score']}% "
          f"(penalty={m['similarity']['penalty']})")
