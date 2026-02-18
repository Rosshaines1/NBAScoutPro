"""Generate a CSV for manual tier review.

Outputs every player in the database with their current WS-based tier
so the user can correct misclassifications.

Columns: Name, Draft Year, Pick, College, Position, NBA WS, NBA Games, Current Tier, Current Label, Corrected Tier
"""
import json
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, TIER_LABELS

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

# Sort by draft year then pick for easy reviewing
db.sort(key=lambda p: (p.get("draft_year", 9999), p.get("draft_pick", 99)))

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tier_review.csv")

with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Name", "Draft Year", "Pick", "College", "Position",
        "NBA Win Shares", "NBA Games", "Current Tier", "Current Label",
        "Corrected Tier (1-5, leave blank if correct)"
    ])

    for p in db:
        ws = p.get("nba_ws", 0) or 0
        games = p.get("nba_games", 0) or 0
        tier = p.get("tier", 5)
        label = TIER_LABELS.get(tier, "?")
        writer.writerow([
            p.get("name", "?"),
            p.get("draft_year", "?"),
            p.get("draft_pick", "?"),
            p.get("college", "?"),
            p.get("pos", "?"),
            f"{ws:.1f}",
            games,
            tier,
            label,
            ""  # blank for user to fill in
        ])

print(f"Written {len(db)} players to {out_path}")
print(f"\nTier distribution:")
from collections import Counter
tier_counts = Counter(p.get("tier", 5) for p in db)
for t in sorted(tier_counts):
    print(f"  T{t} {TIER_LABELS.get(t, '?'):25s}: {tier_counts[t]}")

# Show some obvious misclassifications to demonstrate the problem
print("\n--- Likely Misclassified (examples) ---")
print("\nHigh WS but probably not that good (role players on good teams):")
for p in sorted(db, key=lambda x: x.get("nba_ws", 0) or 0, reverse=True):
    ws = p.get("nba_ws", 0) or 0
    tier = p.get("tier", 5)
    if tier <= 2 and ws > 40:
        print(f"  T{tier} {p['name']:25s} {ws:6.1f} WS  {p.get('nba_games',0):4d} GP  Pick #{p.get('draft_pick','?')}")
    if tier <= 1 and ws > 80:
        continue  # these are probably right

print("\nLow WS but probably better than tier suggests (injuries/bad teams):")
for p in sorted(db, key=lambda x: x.get("nba_ws", 0) or 0):
    ws = p.get("nba_ws", 0) or 0
    tier = p.get("tier", 5)
    pick = p.get("draft_pick", 99)
    if pick <= 5 and tier >= 4 and ws < 20:
        print(f"  T{tier} {p['name']:25s} {ws:6.1f} WS  {p.get('nba_games',0):4d} GP  Pick #{pick}")
