"""Weight Lab: Retune similarity weights to efficiency-first.

Problem: Counting stats (PPG/RPG/APG) dominate distance calc, creating
97% compression where everyone looks the same. Efficiency stats
(BPM/OBPM/FT%/USG) that ACTUALLY predict NBA success are underweighted.

Solution: Flip the weight hierarchy. Efficiency = tier 1, counting = tier 3.
"""
import json, os, sys, math, copy
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS, V2_WEIGHTS, MAX_STATS, ARCHETYPE_WEIGHT_MODS
from app.similarity import (
    calculate_similarity, find_archetype_matches, classify_archetype,
    load_player_db, predict_tier, normalize,
)

DB, POS_AVGS = load_player_db()

# =====================================================================
#  NEW V4 WEIGHTS — Efficiency-first
# =====================================================================
V4_WEIGHTS = {
    # Tier 1: Efficiency/rate stats that predict NBA success
    "bpm": 5.0,       # r=0.25, strongest overall predictor
    "obpm": 4.0,      # +32% T1 vs T4, top superstar separator
    "ft": 4.0,        # strongest star/bust separator (+10% gap)
    "fta": 3.5,       # r=0.32, #1 raw predictor
    "stl_per": 3.0,   # r=0.21, defensive instincts (rate)
    "usg": 3.0,       # r=0.17, offensive load (rate)
    "dbpm": 2.0,      # defensive impact rate

    # Tier 2: Physical profile (translates directly)
    "height": 2.0,
    "ws": 2.0,        # wingspan
    "weight": 1.0,
    "spg": 1.5,       # partially rate-dependent

    # Tier 3: Context-dependent (low weight — noise)
    "ppg": 0.5,       # r=0.11, context-dependent
    "rpg": 0.3,       # r=0.08
    "apg": 0.3,       # r=0.08
    "bpg": 0.3,       # r=0.04
    "fg": 0.5,        # r=0.02
    "threeP": 0.2,    # r=-0.004 literally zero
    "ato": 0.5,
    "age": 0.5,
    "mpg": 0.3,
}

# Reset archetype mods to neutral for base weight testing
NEUTRAL_ARCH_MODS = {
    "Scoring Guard": {},
    "Playmaking Guard": {},
    "3&D Wing": {},
    "Scoring Wing": {},
    "Skilled Big": {},
    "Athletic Big": {},
}

# =====================================================================
#  FLAGG: Full stats (Duke 2024-25 via barttorvik)
# =====================================================================
FLAGG_FULL = {
    "name": "Cooper Flagg", "pos": "W", "h": 81, "w": 205, "ws": 86,
    "age": 18.5, "level": "High Major", "ath": 3,
    "ppg": 19.2, "rpg": 7.5, "apg": 4.2, "spg": 1.4, "bpg": 1.4,
    "fg": 53.0, "threeP": 39.0, "ft": 84.0, "tpg": 3.0, "mpg": 30.6,
    # Advanced stats filled in
    "bpm": 12.1, "obpm": 7.2, "dbpm": 4.9,
    "fta": 6.14, "stl_per": 2.1, "usg": 28.8,
}

FLAGG_BARE = {
    "name": "Cooper Flagg (no advanced)", "pos": "W", "h": 81, "w": 205, "ws": 86,
    "age": 18.5, "level": "High Major", "ath": 3,
    "ppg": 19.2, "rpg": 7.5, "apg": 4.2, "spg": 1.4, "bpg": 1.4,
    "fg": 53.0, "threeP": 39.0, "ft": 84.0, "tpg": 3.0, "mpg": 30.6,
    "bpm": 0, "obpm": 0, "dbpm": 0,
    "fta": 6.14, "stl_per": 0, "usg": 0,
}

# Known players for validation
TEST_PLAYERS = [
    "Stephen Curry", "James Harden", "Damian Lillard",
    "Karl-Anthony Towns", "Anthony Davis", "Joel Embiid",
    "Kawhi Leonard", "Paul George", "Jayson Tatum",
    "Mikal Bridges", "Gary Payton",
    "Frank Kaminsky", "Jarrett Culver", "Josh Jackson",
]


def run_similarity_with_weights(prospect, db, pos_avgs, weights_dict, top_n=10):
    """Run similarity with custom base weights by temporarily swapping V2_WEIGHTS."""
    import config
    original = config.V2_WEIGHTS.copy()
    config.V2_WEIGHTS.clear()
    config.V2_WEIGHTS.update(weights_dict)
    try:
        # Classify archetype
        arch, score, secondary = classify_archetype(prospect)
        # Filter to same archetype
        same_arch = [p for p in db if p.get("has_college_stats")
                     and classify_archetype(p)[0] == arch]
        # Run similarity (no archetype weight mods — just base weights)
        results = []
        for player in same_arch:
            sim = calculate_similarity(prospect, player, pos_avgs, use_v2=True, weight_mods=None)
            results.append({"player": player, "similarity": sim})
        results.sort(key=lambda x: x["similarity"]["score"], reverse=True)
        return arch, results[:top_n]
    finally:
        config.V2_WEIGHTS.clear()
        config.V2_WEIGHTS.update(original)


def show_comps(label, arch, matches, top_n=5):
    """Print comp results."""
    scores = [m["similarity"]["score"] for m in matches[:top_n]]
    print(f"\n  {label} -- {arch}")
    print(f"  Score range: {min(scores):.1f}% - {max(scores):.1f}% (spread: {max(scores)-min(scores):.1f})")
    for i, m in enumerate(matches[:top_n]):
        p = m["player"]
        s = p["stats"]
        ws = p.get("nba_ws", 0) or 0
        sim = m["similarity"]
        # Show which diffs contribute most
        top_diffs = sorted(sim["diffs"].items(), key=lambda x: -x[1])[:3]
        diff_str = ", ".join(f"{k}={v:.3f}" for k, v in top_diffs)
        print(f"    #{i+1}: {p['name']:25s} T{p['tier']} {sim['score']:5.1f}% | "
              f"{s['ppg']:.0f}ppg {s.get('bpm',0):.1f}bpm {s.get('ft',0):.0f}%ft WS={ws:.0f}")
        print(f"         Top diffs: {diff_str}")


# =====================================================================
#  TEST 1: Score distribution comparison
# =====================================================================
print("=" * 75)
print("  TEST 1: SCORE DISTRIBUTION (V2 vs V4 weights)")
print("=" * 75)

for label, weights in [("V2 (current)", V2_WEIGHTS), ("V4 (efficiency-first)", V4_WEIGHTS)]:
    # Pick 5 random test prospects and measure their score distributions
    all_scores = []
    for name in ["Stephen Curry", "Karl-Anthony Towns", "Mikal Bridges"]:
        p = next((x for x in DB if x["name"] == name), None)
        if not p:
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
        for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg", "gp"]:
            if adv in s and s[adv]:
                prospect[adv] = s[adv]

        db_filtered = [x for x in DB if x["name"] != name]
        arch, matches = run_similarity_with_weights(prospect, db_filtered, POS_AVGS, weights, top_n=20)
        scores = [m["similarity"]["score"] for m in matches]
        all_scores.extend(scores)

    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        top = max(all_scores)
        bot = min(all_scores)
        spread = top - bot
        print(f"\n  {label}:")
        print(f"    Top-20 comps avg score: {avg:.1f}%")
        print(f"    Range: {bot:.1f}% - {top:.1f}% (spread: {spread:.1f})")

        # Distribution buckets
        buckets = {"95-100": 0, "90-95": 0, "85-90": 0, "80-85": 0, "<80": 0}
        for sc in all_scores:
            if sc >= 95: buckets["95-100"] += 1
            elif sc >= 90: buckets["90-95"] += 1
            elif sc >= 85: buckets["85-90"] += 1
            elif sc >= 80: buckets["80-85"] += 1
            else: buckets["<80"] += 1
        for b, c in buckets.items():
            bar = "#" * (c * 2)
            print(f"    {b:>8s}: {c:3d} {bar}")


# =====================================================================
#  TEST 2: Cooper Flagg with full vs bare stats
# =====================================================================
print(f"\n{'=' * 75}")
print("  TEST 2: COOPER FLAGG — V2 vs V4 weights")
print("=" * 75)

for flagg, flabel in [(FLAGG_FULL, "Full advanced stats"), (FLAGG_BARE, "No advanced stats")]:
    print(f"\n  --- {flabel} ---")
    for wlabel, weights in [("V2", V2_WEIGHTS), ("V4", V4_WEIGHTS)]:
        arch, matches = run_similarity_with_weights(flagg, DB, POS_AVGS, weights, top_n=5)
        show_comps(f"Flagg ({flabel}) - {wlabel} weights", arch, matches)


# =====================================================================
#  TEST 3: Known players — does V4 produce better comps?
# =====================================================================
print(f"\n{'=' * 75}")
print("  TEST 3: KNOWN PLAYER COMPS (V2 vs V4)")
print("=" * 75)

for name in TEST_PLAYERS:
    p = next((x for x in DB if x["name"] == name), None)
    if not p or not p.get("has_college_stats"):
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
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg", "gp"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]

    db_filtered = [x for x in DB if x["name"] != name]
    actual_tier = p["tier"]
    ws = p.get("nba_ws", 0) or 0

    print(f"\n  {name} (Actual: T{actual_tier}, WS={ws:.0f})")

    for wlabel, weights in [("V2", V2_WEIGHTS), ("V4", V4_WEIGHTS)]:
        arch, matches = run_similarity_with_weights(prospect, db_filtered, POS_AVGS, weights, top_n=5)
        scores = [m["similarity"]["score"] for m in matches]
        tiers = [m["player"]["tier"] for m in matches]
        names = [m["player"]["name"] for m in matches[:3]]
        ceil = min(tiers)
        floor = max(tiers)
        spread = max(scores) - min(scores)
        print(f"    {wlabel}: {arch:20s} | Ceil=T{ceil} Floor=T{floor} | "
              f"Scores={min(scores):.0f}-{max(scores):.0f}% (spread={spread:.1f}) | "
              f"{', '.join(names)}")
