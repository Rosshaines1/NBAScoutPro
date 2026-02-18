"""Check how quadrant changes affect predict_tier vs old level system."""
import json, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

clean = [p for p in db if p.get('has_college_stats')
         and 2009 <= (p.get('draft_year') or 0) <= 2019
         and p.get('nba_ws') is not None]

# Compare old level vs new quadrant assignments
changes = []
for p in clean:
    old_level = p.get('level', 'High Major')
    new_quad = p.get('quadrant', 'Q1')

    # Map old level to effective modifier
    old_mods = {'High Major': 1.0, 'Mid Major': 0.85, 'Low Major': 0.70}
    new_mods = {'Q1': 1.0, 'Q2': 0.90, 'Q3': 0.80, 'Q4': 0.70}

    old_mod = old_mods.get(old_level, 1.0)
    new_mod = new_mods.get(new_quad, 1.0)

    if abs(old_mod - new_mod) > 0.01:
        direction = "UP" if new_mod > old_mod else "DOWN"
        changes.append({
            'name': p['name'], 'tier': p['tier'],
            'old_level': old_level, 'new_quad': new_quad,
            'old_mod': old_mod, 'new_mod': new_mod,
            'direction': direction, 'diff': new_mod - old_mod
        })

print(f"Players whose modifier changed: {len(changes)}/{len(clean)}")
print(f"\n=== PROMOTED (modifier increased) ===")
promoted = [c for c in changes if c['direction'] == 'UP']
print(f"  Total: {len(promoted)}")
tiers = Counter(c['tier'] for c in promoted)
for t in range(1, 6):
    print(f"    Tier {t}: {tiers.get(t, 0)}")
for c in sorted(promoted, key=lambda x: -x['diff'])[:15]:
    print(f"  {c['name']:25s} T{c['tier']}  {c['old_level']:12s}({c['old_mod']:.2f}) -> {c['new_quad']}({c['new_mod']:.2f})  +{c['diff']:.2f}")

print(f"\n=== DEMOTED (modifier decreased) ===")
demoted = [c for c in changes if c['direction'] == 'DOWN']
print(f"  Total: {len(demoted)}")
tiers = Counter(c['tier'] for c in demoted)
for t in range(1, 6):
    print(f"    Tier {t}: {tiers.get(t, 0)}")
for c in sorted(demoted, key=lambda x: x['diff'])[:15]:
    print(f"  {c['name']:25s} T{c['tier']}  {c['old_level']:12s}({c['old_mod']:.2f}) -> {c['new_quad']}({c['new_mod']:.2f})  {c['diff']:.2f}")
