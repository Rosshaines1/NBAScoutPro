"""Case study 2: Focus on missed stars — which ones are fixable?

Categories:
A) Bad data (wrong player/school) — need pipeline fix, not rules
B) Genuinely unpredictable (mediocre stats, developed later)
C) Potentially fixable (there IS a signal we're missing)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR, LEVEL_MODIFIERS, STAR_SIGNAL_THRESHOLDS
from app.similarity import predict_tier, count_star_signals

with open(PLAYER_DB_PATH) as f:
    DB = json.load(f)
with open(os.path.join(PROCESSED_DIR, "positional_avgs.json")) as f:
    POS_AVGS = json.load(f)


def get_player(name):
    return next((p for p in DB if p["name"] == name), None)


# All T1-T2 players with their current predict_tier scores
stars = []
for p in DB:
    if p["tier"] > 2 or not p.get("has_college_stats"):
        continue
    if p.get("draft_pick", 99) > 60:
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
    pred = predict_tier(prospect, POS_AVGS)
    stars.append({
        "name": p["name"], "tier": p["tier"], "pred_tier": pred["tier"],
        "score": pred["score"], "pick": p.get("draft_pick", 99),
        "year": p.get("draft_year"), "ws": p.get("nba_ws", 0) or 0,
        "college": p.get("college"), "level": p["level"],
        "ppg": s["ppg"], "mpg": s["mpg"], "bpm": s.get("bpm", 0),
        "ft": s.get("ft", 0), "pos": p["pos"],
        "sigs": count_star_signals(prospect)[0],
        "reasons": pred["reasons"],
    })

# Sort into categories
print("=" * 80)
print("  CATEGORY A: BAD DATA (wrong player/school matched)")
print("  These need pipeline fixes, not algorithm rules.")
print("=" * 80)
# Identify by: very low stats that don't match known career
bad_data = [s for s in stars if s["ppg"] < 5 and s["ws"] > 30]
for s in sorted(bad_data, key=lambda x: -x["ws"]):
    print(f"  {s['name']:25s} T{s['tier']} #{s['pick']:2d} ({s['year']}) "
          f"WS={s['ws']:5.0f} | {s['ppg']:.1f} PPG at {s['college']} ({s['level']})")

print(f"\n  Count: {len(bad_data)} players with bad data")

print(f"\n{'=' * 80}")
print("  CATEGORY B: GENUINELY UNPREDICTABLE")
print("  Mediocre college stats, developed later. No stat rule will find them.")
print("=" * 80)
# These have decent PPG (not bad data) but low BPM and 0 signals
unpredictable = [s for s in stars
                 if s["ppg"] >= 5  # not bad data
                 and s["sigs"] == 0
                 and s["bpm"] < 5.0
                 and s["pred_tier"] >= 4]
for s in sorted(unpredictable, key=lambda x: -x["ws"]):
    print(f"  {s['name']:25s} T{s['tier']} #{s['pick']:2d} ({s['year']}) "
          f"WS={s['ws']:5.0f} | {s['ppg']:.1f} PPG, BPM={s['bpm']:.1f}, "
          f"FT={s['ft']:.0f}%, {s['mpg']:.0f} MPG at {s['college']}")

print(f"\n  Count: {len(unpredictable)}")

print(f"\n{'=' * 80}")
print("  CATEGORY C: POTENTIALLY FIXABLE (predicted too low, signal exists)")
print("  These have some positive signals but the model underweights them.")
print("=" * 80)
# Players who are predicted T3-T5 but have SOME positive signals
fixable = [s for s in stars
           if s["ppg"] >= 5  # not bad data
           and s not in unpredictable
           and s["pred_tier"] >= 3
           and s["pred_tier"] > s["tier"]]
for s in sorted(fixable, key=lambda x: -x["ws"]):
    print(f"  {s['name']:25s} T{s['tier']} pred=T{s['pred_tier']}({s['score']:.0f}) "
          f"#{s['pick']:2d} ({s['year']}) WS={s['ws']:5.0f}")
    print(f"    {s['ppg']:.1f} PPG, {s['mpg']:.0f} MPG, BPM={s['bpm']:.1f}, "
          f"FT={s['ft']:.0f}%, {s['pos']} | sigs={s['sigs']} | {s['college']} ({s['level']})")
    print(f"    Reasons: {s['reasons']}")

print(f"\n  Count: {len(fixable)}")

# Now: look for patterns in the fixable group
print(f"\n{'=' * 80}")
print("  PATTERN SEARCH: What do the fixable missed stars share?")
print("=" * 80)

if fixable:
    avg_bpm = sum(s["bpm"] for s in fixable) / len(fixable)
    avg_pick = sum(s["pick"] for s in fixable) / len(fixable)
    avg_ft = sum(s["ft"] for s in fixable) / len(fixable)
    avg_mpg = sum(s["mpg"] for s in fixable) / len(fixable)
    avg_ppg = sum(s["ppg"] for s in fixable) / len(fixable)

    print(f"  Avg draft pick: {avg_pick:.0f}")
    print(f"  Avg BPM: {avg_bpm:.1f}")
    print(f"  Avg FT%: {avg_ft:.0f}%")
    print(f"  Avg MPG: {avg_mpg:.0f}")
    print(f"  Avg PPG: {avg_ppg:.1f}")

    # How many are Low/Mid Major?
    from collections import Counter
    lvl = Counter(s["level"] for s in fixable)
    print(f"  Level distribution: {dict(lvl)}")

    # How many had low minutes (freshmen signal)?
    low_min = sum(1 for s in fixable if s["mpg"] < 25)
    print(f"  Low minutes (<25 MPG): {low_min}/{len(fixable)}")

    # How many had high FT%?
    high_ft = sum(1 for s in fixable if s["ft"] >= 78)
    print(f"  Good FT shooters (≥78%): {high_ft}/{len(fixable)}")

    # How many were lottery picks?
    lottery = sum(1 for s in fixable if s["pick"] <= 14)
    print(f"  Lottery picks: {lottery}/{len(fixable)}")
