"""Compare predicted tier distribution vs actual tier distribution.
Are we putting the right NUMBER of players in each bucket?"""
import json
import os
import sys
from collections import Counter

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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

# Run predictions
actual_counts = Counter()
pred_counts = Counter()
results = []

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
    actual_counts[p["tier"]] += 1
    pred_counts[pred["tier"]] += 1
    results.append({"name": p["name"], "actual": p["tier"], "pred": pred["tier"]})

n = len(clean)

print(f"{'Tier':<6} {'Label':<22} {'Actual':>8} {'Actual%':>8} {'Predicted':>10} {'Pred%':>8} {'Diff':>6} {'Ratio':>8}")
print("-" * 80)
for t in range(1, 6):
    label = TIER_LABELS.get(t, "?")
    a = actual_counts[t]
    p = pred_counts[t]
    a_pct = a / n * 100
    p_pct = p / n * 100
    diff = p - a
    ratio = p / a if a > 0 else float('inf')
    sign = "+" if diff > 0 else ""
    print(f"  T{t}   {label:<22} {a:>6}   {a_pct:>5.1f}%   {p:>8}   {p_pct:>5.1f}%  {sign}{diff:>5}  {ratio:>6.2f}x")

print(f"\n  Total {'':<22} {n:>6}   100.0%   {n:>8}   100.0%")

# Where do the extras/deficits go?
print(f"\n\n=== CROSS-TAB: Where does each actual tier get predicted? ===\n")
print(f"{'':>12}", end="")
for pt in range(1, 6):
    print(f"  Pred T{pt}", end="")
print(f"  | Total  Correct%")
print("-" * 85)

for at in range(1, 6):
    label = TIER_LABELS.get(at, "?")[:12]
    row = [r for r in results if r["actual"] == at]
    print(f"  Actual T{at}", end="")
    for pt in range(1, 6):
        count = sum(1 for r in row if r["pred"] == pt)
        pct = count / len(row) * 100 if row else 0
        print(f"  {count:>3} ({pct:>4.0f}%)", end="")
    correct = sum(1 for r in row if r["pred"] == r["actual"])
    print(f"  | {len(row):>4}    {correct/len(row)*100:.0f}%")

# Stars specifically
print(f"\n\n=== STAR ANALYSIS (T1+T2) ===")
actual_stars = [r for r in results if r["actual"] in (1, 2)]
pred_stars = [r for r in results if r["pred"] in (1, 2)]
true_pos = [r for r in results if r["pred"] in (1, 2) and r["actual"] in (1, 2)]
false_pos = [r for r in results if r["pred"] in (1, 2) and r["actual"] in (4, 5)]
false_neg = [r for r in results if r["pred"] in (4, 5) and r["actual"] in (1, 2)]

print(f"  Actual stars (T1+T2):     {len(actual_stars):>4}  ({len(actual_stars)/n*100:.1f}%)")
print(f"  Predicted stars (T1+T2):  {len(pred_stars):>4}  ({len(pred_stars)/n*100:.1f}%)")
print(f"  True positives:           {len(true_pos):>4}  (correctly ID'd as star)")
print(f"  False positives:          {len(false_pos):>4}  (predicted star, actually T4/T5)")
print(f"  False negatives:          {len(false_neg):>4}  (actual star, predicted T4/T5)")
print(f"  Precision:                {len(true_pos)/len(pred_stars)*100:.1f}%  (of predicted stars, how many are real)")
print(f"  Recall:                   {len(true_pos)/len(actual_stars)*100:.1f}%  (of actual stars, how many did we find)")

print(f"\n\n=== BUST ANALYSIS (T4+T5) ===")
actual_busts = [r for r in results if r["actual"] in (4, 5)]
pred_busts = [r for r in results if r["pred"] in (4, 5)]
true_bust = [r for r in results if r["pred"] in (4, 5) and r["actual"] in (4, 5)]
false_bust = [r for r in results if r["pred"] in (4, 5) and r["actual"] in (1, 2)]

print(f"  Actual busts (T4+T5):     {len(actual_busts):>4}  ({len(actual_busts)/n*100:.1f}%)")
print(f"  Predicted busts (T4+T5):  {len(pred_busts):>4}  ({len(pred_busts)/n*100:.1f}%)")
print(f"  True positives:           {len(true_bust):>4}  (correctly ID'd as bust)")
print(f"  False positives:          {len(false_bust):>4}  (predicted bust, actually T1/T2)")
print(f"  Precision:                {len(true_bust)/len(pred_busts)*100:.1f}%  (of predicted busts, how many are real)")
print(f"  Recall:                   {len(true_bust)/len(actual_busts)*100:.1f}%  (of actual busts, how many did we find)")
