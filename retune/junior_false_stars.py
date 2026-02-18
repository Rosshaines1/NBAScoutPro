"""Find junior (age=3) false stars."""
import json, os, sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, POSITIONAL_AVGS
from app.similarity import predict_tier

with open(PLAYER_DB_PATH, encoding="utf-8") as f:
    db = json.load(f)
pos_avgs = POSITIONAL_AVGS
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH, encoding="utf-8") as f:
        pos_avgs = json.load(f)

clean = [p for p in db if p.get("has_college_stats")
         and 2009 <= (p.get("draft_year") or 0) <= 2019
         and p.get("nba_ws") is not None]

juniors = []
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
    if pred["tier"] in (1, 2) and p["tier"] in (4, 5) and p.get("age") == 3:
        juniors.append((p, pred))

print(f"Junior (age=3) false stars: {len(juniors)}\n")
for p, pred in sorted(juniors, key=lambda x: x[1]["score"], reverse=True):
    s = p["stats"]
    h = p["h"]
    ht = f"{h//12}'{h%12:02d}" if h else "?"
    print(f"{p['name']:28s} pred=T{pred['tier']} actual=T{p['tier']}  score={pred['score']:3.0f}  {p.get('draft_year')} pick {p.get('draft_pick','?'):>3}  {p['pos']} {ht}  {p.get('college','?')}")
    print(f"    PPG={s.get('ppg',0):.1f} BPM={s.get('bpm',0):.1f} OBPM={s.get('obpm',0):.1f} DBPM={s.get('dbpm',0):.1f} FT={s.get('ft',0):.0f}% FTA={s.get('fta',0):.1f} USG={s.get('usg',0):.0f}")
    print(f"    Reasons:")
    for r in pred["reasons"]:
        print(f"      {r}")
    print()
