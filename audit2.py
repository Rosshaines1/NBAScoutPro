"""Quick check: What's the level/conference breakdown of predict_tier false positives?"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR
from app.similarity import predict_tier, count_star_signals

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)
with open(os.path.join(PROCESSED_DIR, "positional_avgs.json")) as f:
    pos_avgs = json.load(f)

# Check all T5 busts that predict_tier thinks are T1-T2
print("=" * 80)
print("  FALSE POSITIVES: T5 busts predicted as T1-T2")
print("=" * 80)
false_pos = []
for p in db:
    if not p.get("has_college_stats") or p.get("draft_pick", 99) > 60:
        continue
    if p["tier"] != 5:
        continue
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p["w"],
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 22),
        "level": p["level"], "ath": p.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"], "fg": s["fg"],
        "threeP": s["threeP"], "ft": s["ft"], "tpg": s["tpg"], "mpg": s["mpg"],
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    pred = predict_tier(prospect, pos_avgs)
    if pred["tier"] <= 2:
        sigs, tags = count_star_signals(prospect)
        false_pos.append({
            "name": p["name"], "level": p["level"], "pos": p["pos"],
            "pred_tier": pred["tier"], "score": pred["score"],
            "sigs": sigs, "pick": p.get("draft_pick", 99),
            "year": p.get("draft_year", "?"), "ws": p.get("nba_ws", 0),
            "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
            "fta": s.get("fta", 0), "ppg": s["ppg"], "mpg": s["mpg"],
            "age": p.get("age", 22), "college": p.get("college", "?"),
        })

# Sort by score
false_pos.sort(key=lambda x: -x["score"])

from collections import Counter
levels = Counter(fp["level"] for fp in false_pos)
print(f"\nTotal false positives (T5 predicted T1-T2): {len(false_pos)}")
print(f"By level: {dict(levels)}")

print(f"\nAll false positives:")
for fp in false_pos:
    print(f"  {fp['name']:25s} {fp['level']:12s} pred=T{fp['pred_tier']} "
          f"score={fp['score']:5.0f} sigs={fp['sigs']} "
          f"BPM={fp['bpm']:5.1f} OBPM={fp['obpm']:5.1f} FTA={fp['fta']:5.0f} "
          f"PPG={fp['ppg']:5.1f} MPG={fp['mpg']:5.1f} age={fp['age']:.1f} "
          f"#{fp['pick']:2d} ({fp['year']}) {fp['college']}")

# Also check: T4 busts predicted T1
print(f"\n{'=' * 80}")
print("  FALSE POSITIVES: T4 role players predicted as T1")
print("=" * 80)
false_pos_t4 = []
for p in db:
    if not p.get("has_college_stats") or p.get("draft_pick", 99) > 60:
        continue
    if p["tier"] != 4:
        continue
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p["w"],
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 22),
        "level": p["level"], "ath": p.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"], "fg": s["fg"],
        "threeP": s["threeP"], "ft": s["ft"], "tpg": s["tpg"], "mpg": s["mpg"],
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    pred = predict_tier(prospect, pos_avgs)
    if pred["tier"] == 1:
        sigs, _ = count_star_signals(prospect)
        false_pos_t4.append({
            "name": p["name"], "level": p["level"],
            "score": pred["score"], "sigs": sigs,
            "pick": p.get("draft_pick", 99), "year": p.get("draft_year", "?"),
            "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
            "age": p.get("age", 22), "college": p.get("college", "?"),
        })

false_pos_t4.sort(key=lambda x: -x["score"])
levels4 = Counter(fp["level"] for fp in false_pos_t4)
print(f"\nTotal: {len(false_pos_t4)}")
print(f"By level: {dict(levels4)}")
for fp in false_pos_t4[:15]:
    print(f"  {fp['name']:25s} {fp['level']:12s} score={fp['score']:5.0f} "
          f"sigs={fp['sigs']} BPM={fp['bpm']:5.1f} OBPM={fp['obpm']:5.1f} "
          f"age={fp['age']:.1f} #{fp['pick']:2d} ({fp['year']}) {fp['college']}")

# Now: the missed superstars - what do they have in common?
print(f"\n{'=' * 80}")
print("  MISSED SUPERSTARS: T1/T2 predicted T4-T5")
print("=" * 80)
missed = []
for p in db:
    if not p.get("has_college_stats") or p.get("draft_pick", 99) > 60:
        continue
    if p["tier"] > 2:
        continue
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p["w"],
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 22),
        "level": p["level"], "ath": p.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"], "fg": s["fg"],
        "threeP": s["threeP"], "ft": s["ft"], "tpg": s["tpg"], "mpg": s["mpg"],
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    pred = predict_tier(prospect, pos_avgs)
    if pred["tier"] >= 4:
        sigs, _ = count_star_signals(prospect)
        missed.append({
            "name": p["name"], "tier": p["tier"], "level": p["level"],
            "pred_tier": pred["tier"], "score": pred["score"],
            "sigs": sigs, "pick": p.get("draft_pick", 99),
            "year": p.get("draft_year", "?"),
            "ws": p.get("nba_ws", 0),
            "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
            "fta": s.get("fta", 0), "ppg": s["ppg"], "mpg": s["mpg"],
            "age": p.get("age", 22), "college": p.get("college", "?"),
        })

missed.sort(key=lambda x: -x["ws"])
print(f"\nTotal missed stars: {len(missed)}")
for m in missed:
    print(f"  {m['name']:25s} T{m['tier']} pred=T{m['pred_tier']} "
          f"score={m['score']:5.0f} sigs={m['sigs']} "
          f"BPM={m['bpm']:5.1f} OBPM={m['obpm']:5.1f} FTA={m['fta']:5.0f} "
          f"PPG={m['ppg']:5.1f} MPG={m['mpg']:5.1f} age={m['age']:.1f} "
          f"#{m['pick']:2d} ({m['year']}) WS={m['ws']:.0f} {m['college']}")
