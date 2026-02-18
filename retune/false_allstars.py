"""List all false All-Stars: predicted T1/T2 but actually T4/T5.
Focus on the T2 over-prediction problem."""
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

# All predicted T2 players
pred_t2 = []
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
    if pred["tier"] == 2:
        pred_t2.append({
            "name": p["name"],
            "actual": p["tier"],
            "score": pred["score"],
            "year": p.get("draft_year"),
            "pick": p.get("draft_pick", 61),
            "college": p.get("college", "?"),
            "pos": p["pos"],
            "h": p.get("h", 0),
            "age": p.get("age", 4),
            "level": p.get("level", "?"),
            "ppg": s.get("ppg", 0),
            "rpg": s.get("rpg", 0),
            "apg": s.get("apg", 0),
            "fg": s.get("fg", 0),
            "ft": s.get("ft", 0),
            "bpm": s.get("bpm", 0),
            "obpm": s.get("obpm", 0),
            "fta": s.get("fta", 0),
            "ftr": s.get("ftr", 0),
            "rim_pct": (s.get("rimmade", 0) / s.get("rim_att", 1) * 100) if s.get("rim_att", 0) > 0 else 0,
            "usg": s.get("usg", 0),
            "reasons": pred["reasons"],
            "star_signals": pred["star_signals"],
        })

pred_t2.sort(key=lambda x: x["score"], reverse=True)

# Group by actual tier
by_actual = Counter(p["actual"] for p in pred_t2)
print(f"ALL 86 PREDICTED T2 (All-Star) — where do they actually land?\n")
print(f"  Actually T1 (Superstar):    {by_actual.get(1, 0):>3}")
print(f"  Actually T2 (All-Star):     {by_actual.get(2, 0):>3}  <-- correct")
print(f"  Actually T3 (Starter):      {by_actual.get(3, 0):>3}  <-- over by 1, forgivable")
print(f"  Actually T4 (Role Player):  {by_actual.get(4, 0):>3}  <-- bad miss")
print(f"  Actually T5 (Bust):         {by_actual.get(5, 0):>3}  <-- bad miss")

# Show the bad misses (predicted T2, actually T4 or T5)
false_allstars = [p for p in pred_t2 if p["actual"] in (4, 5)]
print(f"\n\n{'='*120}")
print(f"FALSE ALL-STARS: {len(false_allstars)} predicted T2 but actually T4/T5")
print(f"{'='*120}\n")

# Look for patterns
ages = Counter()
positions = Counter()
levels = Counter()
class_years = Counter()

for p in false_allstars:
    positions[p["pos"]] += 1
    levels[p["level"]] += 1
    ages[p["age"]] += 1

print(f"PATTERNS:")
print(f"  By position: {dict(positions.most_common())}")
print(f"  By level:    {dict(levels.most_common())}")
print(f"  By age:      {dict(ages.most_common())}")
print(f"  Avg BPM:     {sum(p['bpm'] for p in false_allstars)/len(false_allstars):.1f}")
print(f"  Avg PPG:     {sum(p['ppg'] for p in false_allstars)/len(false_allstars):.1f}")
print(f"  Avg FT%:     {sum(p['ft'] for p in false_allstars)/len(false_allstars):.1f}")
print(f"  Avg FTA:     {sum(p['fta'] for p in false_allstars)/len(false_allstars):.1f}")

# Compare to TRUE all-stars
true_allstars = [p for p in pred_t2 if p["actual"] in (1, 2)]
if true_allstars:
    print(f"\n  vs TRUE All-Stars (pred T2, actual T1/T2):")
    print(f"  Avg BPM:     {sum(p['bpm'] for p in true_allstars)/len(true_allstars):.1f}")
    print(f"  Avg PPG:     {sum(p['ppg'] for p in true_allstars)/len(true_allstars):.1f}")
    print(f"  Avg FT%:     {sum(p['ft'] for p in true_allstars)/len(true_allstars):.1f}")
    print(f"  Avg FTA:     {sum(p['fta'] for p in true_allstars)/len(true_allstars):.1f}")

print(f"\n\nDETAILED LIST (sorted by score, highest first):\n")
print(f"{'Name':28s} Act  Score  Yr  Pick Age  Pos Ht     Level        PPG   eFG   FT%   BPM  OBPM  FTA   FTR   Rim%  USG")
print("-" * 155)
for p in false_allstars:
    h = p["h"]
    ht = f"{h//12}'{h%12:02d}" if h else "?"
    print(f"{p['name']:28s} T{p['actual']}  {p['score']:5.0f}  {p['year']}  {p['pick']:>3}  {p['age']}   {p['pos']}  {ht}  {p['level']:12s}"
          f" {p['ppg']:5.1f} {p['fg']:5.1f} {p['ft']:5.1f} {p['bpm']:5.1f} {p['obpm']:5.1f} {p['fta']:4.1f}  {p['ftr']:4.0f}%  {p['rim_pct']:4.0f}%  {p['usg']:4.0f}")

print(f"\n\nMODEL REASONING (why did we think they were stars?):\n")
for p in false_allstars:
    print(f"--- {p['name']} (score {p['score']:.0f}, actual T{p['actual']}) ---")
    print(f"    {p['college']} | {p['pos']} | {p['level']} | Age {p['age']} | {p['year']} pick {p['pick']}")
    for r in p["reasons"]:
        flag = " <<<" if "Red flag" in r else ""
        print(f"      {r}{flag}")
    print()
