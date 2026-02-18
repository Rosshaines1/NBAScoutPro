"""List all false stars: predicted T1/T2 but actually T4/T5."""
import json
import os
import sys

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

false_stars = []
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
    if pred["tier"] in (1, 2) and p["tier"] in (4, 5):
        false_stars.append({
            "name": p["name"],
            "pred_tier": pred["tier"],
            "actual_tier": p["tier"],
            "score": pred["score"],
            "draft_year": p.get("draft_year"),
            "draft_pick": p.get("draft_pick", 61),
            "college": p.get("college", "?"),
            "h": p.get("h", 0),
            "pos": p["pos"],
            "level": p.get("level"),
            "age": p.get("age"),
            "nba_ws": p.get("nba_ws", 0),
            "ppg": s.get("ppg", 0),
            "rpg": s.get("rpg", 0),
            "apg": s.get("apg", 0),
            "fg": s.get("fg", 0),
            "ft": s.get("ft", 0),
            "bpm": s.get("bpm", 0),
            "obpm": s.get("obpm", 0),
            "dbpm": s.get("dbpm", 0),
            "fta": s.get("fta", 0),
            "usg": s.get("usg", 0),
            "reasons": pred["reasons"],
            "red_flags": [r for r in pred["reasons"] if "Red flag" in r],
            "star_signals": pred["star_signals"],
        })

false_stars.sort(key=lambda x: x["score"], reverse=True)

print(f"FALSE STARS: {len(false_stars)} players predicted T1/T2 but actually T4/T5\n")
print(f"{'Name':28s} Pred Act  Score  Yr  Age Ht   Pos Lvl         PPG   eFG   FT%   BPM  OBPM  DBPM   FTA   USG")
print("-" * 150)
for p in false_stars:
    yr = p["draft_year"] or "?"
    h = p.get("h", 0)
    ht_str = f"{h//12}'{h%12:02d}" if h else "?"
    print(f"{p['name']:28s}  T{p['pred_tier']}  T{p['actual_tier']}  {p['score']:5.0f}  {yr}   {p['age']}  {ht_str}  {p['pos']}  {p['level']:12s} "
          f"{p['ppg']:5.1f} {p['fg']:5.1f} {p['ft']:5.1f} {p['bpm']:5.1f} {p['obpm']:5.1f} {p['dbpm']:5.1f} {p['fta']:5.1f} {p['usg']:5.1f}")

print(f"\n\nDETAILED BREAKDOWN:\n")
for p in false_stars:
    h = p.get("h", 0)
    ht_str = f"{h//12}'{h%12:02d}\"" if h else "?"
    print(f"--- {p['name']} (predicted T{p['pred_tier']}, actually T{p['actual_tier']}) ---")
    print(f"    {p['college']} | {p['pos']} {ht_str} | {p['level']} | Age {p['age']} | {p['draft_year']}")
    print(f"    Stats: {p['ppg']:.1f}ppg {p['rpg']:.1f}rpg {p['apg']:.1f}apg | {p['fg']:.0f}%eFG {p['ft']:.0f}%FT | BPM={p['bpm']:.1f} OBPM={p['obpm']:.1f} DBPM={p['dbpm']:.1f} | FTA={p['fta']:.1f} USG={p['usg']:.0f}")
    print(f"    Model reasons:")
    for r in p["reasons"]:
        flag = " <<<" if "Red flag" in r else ""
        print(f"      - {r}{flag}")
    if not p["red_flags"]:
        print(f"      (NO red flags fired)")
    print()
