"""Test predict_tier accuracy after adding red flag penalties."""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, POSITIONAL_AVGS, TIER_LABELS
from app.similarity import predict_tier

with open(PLAYER_DB_PATH, encoding="utf-8") as f:
    db = json.load(f)

pos_avgs = POSITIONAL_AVGS
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH, encoding="utf-8") as f:
        pos_avgs = json.load(f)

clean = [
    p for p in db
    if p.get("has_college_stats")
    and 2009 <= (p.get("draft_year") or 0) <= 2019
    and p.get("nba_ws") is not None
]
print(f"Dataset: {len(clean)} players\n")

# Build flat prospect dicts from DB entries
exact = 0
within_1 = 0
star_correct = 0
star_total = 0
bust_correct = 0
bust_total = 0
false_stars = 0
confusion = defaultdict(lambda: defaultdict(int))
red_flag_fired = Counter()

for p in clean:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p.get("w", 200),
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 4),
        "level": p.get("level", "High Major"),
        "ath": p.get("ath", 0), "draft_pick": p.get("draft_pick", 0),
        "ppg": s.get("ppg", 0), "rpg": s.get("rpg", 0), "apg": s.get("apg", 0),
        "spg": s.get("spg", 0), "bpg": s.get("bpg", 0), "tpg": s.get("tpg", 0),
        "fg": s.get("fg", 45), "threeP": s.get("threeP", 0), "ft": s.get("ft", 70),
        "mpg": s.get("mpg", 30), "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
        "dbpm": s.get("dbpm", 0), "fta": s.get("fta", 0),
        "stl_per": s.get("stl_per", 0), "usg": s.get("usg", 0),
        "ftr": s.get("ftr", 0),
        "rim_pct": (s.get("rimmade", 0) / s.get("rim_att", 1) * 100) if s.get("rim_att", 0) > 0 else 0,
        "tpa": s.get("tpa", 0),
    }

    pred = predict_tier(prospect, pos_avgs)
    pred_tier = pred["tier"]
    actual_tier = p["tier"]

    confusion[actual_tier][pred_tier] += 1

    if pred_tier == actual_tier:
        exact += 1
    if abs(pred_tier - actual_tier) <= 1:
        within_1 += 1

    if actual_tier in (1, 2):
        star_total += 1
        if pred_tier in (1, 2):
            star_correct += 1
    if actual_tier in (4, 5):
        bust_total += 1
        if pred_tier in (4, 5):
            bust_correct += 1

    # False star: predicted T1/T2 but actually T4/T5
    if pred_tier in (1, 2) and actual_tier in (4, 5):
        false_stars += 1

    # Count red flags
    for r in pred["reasons"]:
        if "Red flag" in r:
            red_flag_fired[r.split(":")[1].strip().split("(")[0].strip()] += 1

n = len(clean)
print(f"Exact accuracy: {exact}/{n} ({exact/n*100:.1f}%)")
print(f"Within-1: {within_1}/{n} ({within_1/n*100:.1f}%)")
print(f"Star detection (T1+T2): {star_correct}/{star_total} ({star_correct/star_total*100:.1f}%)")
print(f"Bust detection (T4+T5): {bust_correct}/{bust_total} ({bust_correct/bust_total*100:.1f}%)")
print(f"False stars: {false_stars}")

print(f"\nConfusion matrix (predicted vs actual):")
print(f"{'':>12s}", end="")
for pt in range(1, 6):
    print(f" Pred={pt}", end="")
print()
for at in range(1, 6):
    print(f"  Actual={at}", end="")
    for pt in range(1, 6):
        print(f" {confusion[at][pt]:6d}", end="")
    tier_n = sum(confusion[at][pt] for pt in range(1, 6))
    print(f"  (n={tier_n})")

print(f"\nRed flags fired:")
for flag, count in red_flag_fired.most_common():
    print(f"  {flag}: {count}")

print(f"\n--- SUMMARY ---")
print(f"Exact: {exact/n*100:.1f}%  Within-1: {within_1/n*100:.1f}%")
print(f"Star detection: {star_correct/star_total*100:.1f}%  Bust detection: {bust_correct/bust_total*100:.1f}%  False stars: {false_stars}")
print(f"Uses corrected tiers + user-available stats only (no draft position)")
