"""Verify quadrant assignments in player_db.json."""
import json, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

clean = [p for p in db if p.get('has_college_stats') and 2009 <= (p.get('draft_year') or 0) <= 2019]

quads = Counter(p.get('quadrant') for p in clean)
print('Quadrant distribution (2009-2019 w/ college stats):')
for q in ['Q1', 'Q2', 'Q3', 'Q4', None]:
    print(f'  {q}: {quads.get(q, 0)}')

print(f'\n=== KEY PLAYERS ===')
for name in ['Dominique Jones', 'Gordon Hayward', 'Jimmy Butler', 'Kawhi Leonard',
             'Ja Morant', 'Stephen Curry', 'Damian Lillard', 'Paul George',
             'Zion Williamson', 'Trae Young', 'Anthony Davis']:
    p = next((x for x in db if x['name'] == name), None)
    if p:
        print(f"  {name:25s} college={p.get('college',''):20s} quad={p.get('quadrant')}  rank={str(p.get('team_rank','')):>4s}  old_level={p.get('level')}")
