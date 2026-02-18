"""Analyze height vs NBA outcome by position — find 'too short' thresholds."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

clean = [
    p for p in db
    if p.get("has_college_stats")
    and 2009 <= (p.get("draft_year") or 0) <= 2019
    and p.get("nba_ws") is not None
]

for pos in ["G", "W", "B"]:
    pos_players = [p for p in clean if p["pos"] == pos]
    print(f"\n=== {pos} ({len(pos_players)} players) ===")

    by_height = {}
    for p in pos_players:
        h = p["h"]
        if h not in by_height:
            by_height[h] = {"star": 0, "starter": 0, "bust": 0, "total": 0}
        by_height[h]["total"] += 1
        if p["tier"] in (1, 2):
            by_height[h]["star"] += 1
        elif p["tier"] == 3:
            by_height[h]["starter"] += 1
        else:
            by_height[h]["bust"] += 1

    print(f"  Height      Total  Stars  Start  Busts  Bust%  Star%")
    for h in sorted(by_height.keys()):
        d = by_height[h]
        if d["total"] >= 2:
            ft = h // 12
            inch = h % 12
            bust_pct = d["bust"] / d["total"] * 100
            star_pct = d["star"] / d["total"] * 100
            print(f"  {ft}'{inch:02d}\" ({h})   {d['total']:3d}   {d['star']:3d}   {d['starter']:3d}   {d['bust']:3d}   {bust_pct:4.0f}%   {star_pct:4.0f}%")

# Cumulative: what happens below certain height thresholds?
print("\n\n=== CUMULATIVE: Guards below height X ===")
guards = [p for p in clean if p["pos"] == "G"]
for threshold in [72, 73, 74, 75, 76]:
    short = [p for p in guards if p["h"] <= threshold]
    if not short:
        continue
    n = len(short)
    stars = sum(1 for p in short if p["tier"] in (1, 2))
    busts = sum(1 for p in short if p["tier"] in (4, 5))
    ft = threshold // 12
    inch = threshold % 12
    print(f"  G <= {ft}'{inch:02d}\": n={n:3d}  stars={stars} ({stars/n*100:.0f}%)  busts={busts} ({busts/n*100:.0f}%)")

print("\n=== CUMULATIVE: Wings below height X ===")
wings = [p for p in clean if p["pos"] == "W"]
for threshold in [75, 76, 77, 78, 79]:
    short = [p for p in wings if p["h"] <= threshold]
    if not short:
        continue
    n = len(short)
    stars = sum(1 for p in short if p["tier"] in (1, 2))
    busts = sum(1 for p in short if p["tier"] in (4, 5))
    ft = threshold // 12
    inch = threshold % 12
    print(f"  W <= {ft}'{inch:02d}\": n={n:3d}  stars={stars} ({stars/n*100:.0f}%)  busts={busts} ({busts/n*100:.0f}%)")

print("\n=== CUMULATIVE: Bigs below height X ===")
bigs = [p for p in clean if p["pos"] == "B"]
for threshold in [78, 79, 80, 81, 82]:
    short = [p for p in bigs if p["h"] <= threshold]
    if not short:
        continue
    n = len(short)
    stars = sum(1 for p in short if p["tier"] in (1, 2))
    busts = sum(1 for p in short if p["tier"] in (4, 5))
    ft = threshold // 12
    inch = threshold % 12
    print(f"  B <= {ft}'{inch:02d}\": n={n:3d}  stars={stars} ({stars/n*100:.0f}%)  busts={busts} ({busts/n*100:.0f}%)")

# List every player under 6'0" and every false star that's short
print("\n\n=== ALL PLAYERS UNDER 6'0\" ===")
short_all = [p for p in clean if p["h"] < 72]
for p in sorted(short_all, key=lambda x: x["h"]):
    h = p["h"]
    ft = h // 12
    inch = h % 12
    print(f"  {ft}'{inch:02d}\" {p['pos']} T{p['tier']} {p['name']:25s} {p.get('college','?')}")

print("\n=== FALSE STAR HEIGHTS (predicted T1/T2 but actually T4/T5) ===")
# Quick predict to find false stars with height
from app.similarity import predict_tier
from config import POSITIONAL_AVGS_PATH, POSITIONAL_AVGS
pos_avgs = POSITIONAL_AVGS
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)

false_stars_by_height = []
for p in clean:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p.get("w", 200),
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 4),
        "level": p.get("level", "High Major"), "ath": p.get("ath", 0),
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
    if pred["tier"] in (1, 2) and p["tier"] in (4, 5):
        h = p["h"]
        ft = h // 12
        inch = h % 12
        false_stars_by_height.append((h, p))

false_stars_by_height.sort(key=lambda x: x[0])
for h, p in false_stars_by_height:
    ft = h // 12
    inch = h % 12
    print(f"  {ft}'{inch:02d}\" {p['pos']} T{p['tier']} pred=T1/T2  {p['name']:25s}")

# Height distribution of false stars
print(f"\nFalse star height summary:")
heights = [h for h, _ in false_stars_by_height]
under_74 = sum(1 for h in heights if h <= 74)
under_76 = sum(1 for h in heights if h <= 76)
print(f"  Total: {len(heights)}")
print(f"  Under 6'2\": {under_74}")
print(f"  Under 6'4\": {under_76}")

# Show stars by height — who DOES make it at each height?
print("\n\n=== GUARDS WHO MADE IT (T1/T2) by height ===")
g_stars = [p for p in clean if p["pos"] == "G" and p["tier"] in (1, 2)]
for p in sorted(g_stars, key=lambda x: x["h"]):
    h = p["h"]
    ft_h = h // 12
    inch_h = h % 12
    name = p["name"]
    tier = p["tier"]
    print(f"  {ft_h}'{inch_h:02d}\" T{tier} {name}")

print("\n=== WINGS WHO MADE IT (T1/T2) by height ===")
w_stars = [p for p in clean if p["pos"] == "W" and p["tier"] in (1, 2)]
for p in sorted(w_stars, key=lambda x: x["h"]):
    h = p["h"]
    ft_h = h // 12
    inch_h = h % 12
    name = p["name"]
    tier = p["tier"]
    print(f"  {ft_h}'{inch_h:02d}\" T{tier} {name}")
