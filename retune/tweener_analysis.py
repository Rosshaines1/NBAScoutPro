"""Analyze false all-star guards — are they combo/tweener types?
Tweener = high scoring, low playmaking, undersized wing basically."""
import json, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from config import PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, POSITIONAL_AVGS
from app.similarity import predict_tier

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

pos_avgs = POSITIONAL_AVGS
try:
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)
except: pass

clean = [p for p in db if p.get('has_college_stats')
         and 2009 <= (p.get('draft_year') or 0) <= 2019
         and p.get('nba_ws') is not None]

# Run predict_tier on everyone, find false all-stars
false_stars = []
true_stars = []
for p in clean:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p.get("w", 200),
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 4),
        "level": p.get("level", "High Major"),
        "quadrant": p.get("quadrant", "Q1"),
        "ath": p.get("ath", 0),
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
    if pred["tier"] <= 2 and p["tier"] >= 4:
        false_stars.append({**prospect, "actual_tier": p["tier"], "pred_tier": pred["tier"],
                           "score": pred["score"], "draft_pick": p.get("draft_pick", 0),
                           "draft_year": p.get("draft_year", 0)})
    elif pred["tier"] <= 2 and p["tier"] <= 2:
        true_stars.append({**prospect, "actual_tier": p["tier"], "pred_tier": pred["tier"],
                          "score": pred["score"]})

# Classify guard play style
print(f"=== FALSE ALL-STAR GUARDS ({sum(1 for f in false_stars if f['pos'] == 'G')}) ===\n")
print(f"{'Name':25s} {'Ht':>5s} {'PPG':>5s} {'APG':>5s} {'RPG':>5s} {'USG':>5s} {'ATO':>5s} {'3PA':>5s} {'3P%':>5s} {'BPM':>5s} {'OBPM':>5s} {'DBPM':>5s} {'Quad':>4s} {'Type':>12s}")
print("-" * 130)

for f in sorted([f for f in false_stars if f['pos'] == 'G'], key=lambda x: -x['score']):
    ato = f['apg'] / f['tpg'] if f['tpg'] > 0 else f['apg']
    # Classify: true PG (high APG, high ATO) vs combo/scorer (high PPG, low APG)
    if f['apg'] >= 5 and ato >= 1.5:
        ptype = "True PG"
    elif f['apg'] >= 4:
        ptype = "Combo"
    else:
        ptype = "Scorer/Tweener"

    ht_str = f"{f['h'] // 12}'{f['h'] % 12:02d}\""
    print(f"{f['name']:25s} {ht_str:>5s} {f['ppg']:>5.1f} {f['apg']:>5.1f} {f['rpg']:>5.1f} {f['usg']:>5.0f} {ato:>5.1f} {f.get('tpa',0):>5.1f} {f['threeP']:>5.1f} {f['bpm']:>5.1f} {f['obpm']:>5.1f} {f['dbpm']:>5.1f} {f.get('quadrant','?'):>4s} {ptype:>12s}")

print(f"\n\n=== FALSE ALL-STAR WINGS ({sum(1 for f in false_stars if f['pos'] == 'W')}) ===\n")
print(f"{'Name':25s} {'Ht':>5s} {'PPG':>5s} {'APG':>5s} {'RPG':>5s} {'USG':>5s} {'ATO':>5s} {'3PA':>5s} {'3P%':>5s} {'BPM':>5s} {'OBPM':>5s} {'DBPM':>5s} {'Quad':>4s}")
print("-" * 120)

for f in sorted([f for f in false_stars if f['pos'] == 'W'], key=lambda x: -x['score']):
    ato = f['apg'] / f['tpg'] if f['tpg'] > 0 else f['apg']
    ht_str = f"{f['h'] // 12}'{f['h'] % 12:02d}\""
    print(f"{f['name']:25s} {ht_str:>5s} {f['ppg']:>5.1f} {f['apg']:>5.1f} {f['rpg']:>5.1f} {f['usg']:>5.0f} {ato:>5.1f} {f.get('tpa',0):>5.1f} {f['threeP']:>5.1f} {f['bpm']:>5.1f} {f['obpm']:>5.1f} {f['dbpm']:>5.1f} {f.get('quadrant','?'):>4s}")

# Now compare: what do TRUE star guards look like?
print(f"\n\n=== TRUE STAR GUARDS (pred T1/T2, actual T1/T2) ===\n")
print(f"{'Name':25s} {'Ht':>5s} {'PPG':>5s} {'APG':>5s} {'RPG':>5s} {'USG':>5s} {'ATO':>5s} {'3PA':>5s} {'3P%':>5s} {'BPM':>5s} {'OBPM':>5s} {'DBPM':>5s} {'Quad':>4s}")
print("-" * 120)

for f in sorted([f for f in true_stars if f['pos'] == 'G'], key=lambda x: -x['score']):
    ato = f['apg'] / f['tpg'] if f['tpg'] > 0 else f['apg']
    ht_str = f"{f['h'] // 12}'{f['h'] % 12:02d}\""
    print(f"{f['name']:25s} {ht_str:>5s} {f['ppg']:>5.1f} {f['apg']:>5.1f} {f['rpg']:>5.1f} {f['usg']:>5.0f} {ato:>5.1f} {f.get('tpa',0):>5.1f} {f['threeP']:>5.1f} {f['bpm']:>5.1f} {f['obpm']:>5.1f} {f['dbpm']:>5.1f} {f.get('quadrant','?'):>4s}")

# Summary stats
print(f"\n\n=== GUARD COMPARISON: FALSE vs TRUE STARS ===")
fg = [f for f in false_stars if f['pos'] == 'G']
tg = [f for f in true_stars if f['pos'] == 'G']

if fg and tg:
    for label, group in [("False star guards", fg), ("True star guards", tg)]:
        avg_h = sum(f['h'] for f in group) / len(group)
        avg_ppg = sum(f['ppg'] for f in group) / len(group)
        avg_apg = sum(f['apg'] for f in group) / len(group)
        avg_rpg = sum(f['rpg'] for f in group) / len(group)
        avg_usg = sum(f['usg'] for f in group) / len(group)
        avg_dbpm = sum(f['dbpm'] for f in group) / len(group)
        avg_3p = sum(f['threeP'] for f in group) / len(group)
        avg_ato = sum(f['apg'] / f['tpg'] if f['tpg'] > 0 else f['apg'] for f in group) / len(group)
        print(f"  {label:25s} n={len(group):>2}  ht={avg_h:.1f}\"  PPG={avg_ppg:.1f}  APG={avg_apg:.1f}  RPG={avg_rpg:.1f}  USG={avg_usg:.0f}  ATO={avg_ato:.1f}  3P%={avg_3p:.1f}  DBPM={avg_dbpm:.1f}")

# Same for wings
fw = [f for f in false_stars if f['pos'] == 'W']
tw = [f for f in true_stars if f['pos'] == 'W']
print()
if fw and tw:
    for label, group in [("False star wings", fw), ("True star wings", tw)]:
        avg_h = sum(f['h'] for f in group) / len(group)
        avg_ppg = sum(f['ppg'] for f in group) / len(group)
        avg_apg = sum(f['apg'] for f in group) / len(group)
        avg_rpg = sum(f['rpg'] for f in group) / len(group)
        avg_usg = sum(f['usg'] for f in group) / len(group)
        avg_dbpm = sum(f['dbpm'] for f in group) / len(group)
        avg_3p = sum(f['threeP'] for f in group) / len(group)
        print(f"  {label:25s} n={len(group):>2}  ht={avg_h:.1f}\"  PPG={avg_ppg:.1f}  APG={avg_apg:.1f}  RPG={avg_rpg:.1f}  USG={avg_usg:.0f}  3P%={avg_3p:.1f}  DBPM={avg_dbpm:.1f}")
