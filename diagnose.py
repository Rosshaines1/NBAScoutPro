"""Deep diagnosis of the similarity engine problems.

Three questions:
1. Is our 80.9% backtesting accuracy actually meaningful, or is it base-rate cheating?
2. Why is the similarity ceiling ~66% for real prospects?
3. Why does Cooper Flagg get predicted as T3 despite an elite college season?
"""
import json, math, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.similarity import find_top_matches, calculate_similarity, count_star_signals
from config import POSITIONAL_AVGS, ATHLETIC_VALUES, PLAYER_DB_PATH, POSITIONAL_AVGS_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)
else:
    pos_avgs = POSITIONAL_AVGS

print("=" * 80)
print("  DIAGNOSIS 1: BASE RATE PROBLEM")
print("=" * 80)
# What's the actual tier distribution?
tiers = Counter(p["tier"] for p in db if p.get("has_college_stats"))
total = sum(tiers.values())
print(f"\nTier distribution ({total} players with college stats):")
for t in sorted(tiers.keys()):
    pct = tiers[t] / total * 100
    print(f"  T{t}: {tiers[t]:4d} ({pct:.1f}%)")

# What would a "predict T4 for everyone" strategy score?
naive_exact = tiers.get(4, 0) / total * 100
naive_within1 = (tiers.get(3, 0) + tiers.get(4, 0) + tiers.get(5, 0)) / total * 100
print(f"\nNaive 'predict T4 for everyone':")
print(f"  Exact match:  {naive_exact:.1f}%")
print(f"  Within 1 tier: {naive_within1:.1f}%")
print(f"  Our model:     80.9% within 1 tier")
print(f"  => Are we actually doing better than naive? By how much?")

# Also: what's the star detection rate?
t1_players = [p for p in db if p.get("has_college_stats") and p["tier"] == 1]
t2_players = [p for p in db if p.get("has_college_stats") and p["tier"] == 2]
print(f"\nStar players to find: {len(t1_players)} T1, {len(t2_players)} T2")
print(f"T1 examples: {[p['name'] for p in t1_players[:10]]}")

print("\n" + "=" * 80)
print("  DIAGNOSIS 2: SIMILARITY SCORE DISTRIBUTION")
print("=" * 80)

# Pick 5 known players and run them through the engine
test_players = [
    ("Cooper Flagg (elite wing)", {
        "name": "Flagg", "pos": "W", "h": 81, "w": 205, "ws": 87,
        "age": 18.9, "level": "High Major", "ath": 4,
        "ppg": 18.8, "rpg": 8.6, "apg": 4.5, "spg": 1.5, "bpg": 1.2,
        "fg": 51.0, "threeP": 36.0, "ft": 74.0, "tpg": 2.8, "mpg": 32.0,
        "bpm": 12.0, "obpm": 7.5, "dbpm": 4.5, "fta": 6.14,
        "stl_per": 2.1, "usg": 28.0,
    }),
]

# Also test by converting some KNOWN T1 players back through the engine
# to see: can the engine even find itself?
print("\n--- Self-matching test: Can T1 players find other T1 players? ---")
for p in t1_players[:5]:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p["w"],
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 21),
        "level": p.get("level", "High Major"), "ath": p.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"],
        "fg": s["fg"], "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
        "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
        "dbpm": s.get("dbpm", 0), "fta": s.get("fta", 0),
        "stl_per": s.get("stl_per", 0), "usg": s.get("usg", 0),
    }
    matches = find_top_matches(prospect, db, pos_avgs, top_n=5, use_v2=True)
    tiers_found = [m["player"]["tier"] for m in matches]
    scores = [m["similarity"]["score"] for m in matches]
    penalties = [m["similarity"]["penalty"] for m in matches]
    comp_names = [f"{m['player']['name']}(T{m['player']['tier']})" for m in matches]
    sig_count, _ = count_star_signals(prospect)
    print(f"\n  {p['name']} (T{p['tier']}, WS={p.get('nba_ws',0):.0f}, {sig_count}sig):")
    print(f"    Scores:    {scores}")
    print(f"    Penalties: {penalties}")
    print(f"    Comps: {comp_names}")
    pred_tier = round(sum(s * t for s, t in zip(scores, tiers_found)) / max(sum(scores), 1))
    print(f"    Predicted: T{pred_tier} (actual T{p['tier']})")

print("\n\n--- Cooper Flagg detailed breakdown ---")
flagg = test_players[0][1]
matches = find_top_matches(flagg, db, pos_avgs, top_n=10, use_v2=True)
for i, m in enumerate(matches[:10]):
    p = m["player"]
    sim = m["similarity"]
    print(f"\n  #{i+1}: {p['name']} (T{p['tier']}, {p['outcome']}, WS={p.get('nba_ws',0):.0f})")
    print(f"    Score: {sim['score']}%, Penalty: {sim['penalty']}")
    print(f"    Penalty reasons: {sim['penalty_reasons']}")
    # Show top diff contributors
    top_diffs = sorted(sim["diffs"].items(), key=lambda x: -x[1])[:5]
    print(f"    Top diffs: {[(k, round(v, 3)) for k, v in top_diffs]}")

print("\n\n" + "=" * 80)
print("  DIAGNOSIS 3: WHAT'S HAPPENING TO RAW DISTANCES?")
print("=" * 80)

# For Flagg, compute raw distance (before penalty) for EVERY player,
# then look at the distribution
print("\nFlagg: raw distance distribution across all players...")
all_results = []
for p in db:
    if not p.get("has_college_stats"):
        continue
    sim = calculate_similarity(flagg, p, pos_avgs, use_v2=True)
    raw_dist = math.sqrt(sum(sim["diffs"].values()))
    all_results.append({
        "name": p["name"], "tier": p["tier"], "raw_dist": raw_dist,
        "penalty": sim["penalty"], "score": sim["score"],
        "pre_penalty_score": max(0, 100 - (raw_dist / 12.0 * 100)),
    })

# Sort by raw distance
all_results.sort(key=lambda x: x["raw_dist"])
print(f"\nTop 10 by raw distance (before penalties):")
for r in all_results[:10]:
    print(f"  {r['name']:25s} T{r['tier']} raw={r['raw_dist']:.3f} "
          f"pre_penalty={r['pre_penalty_score']:.1f}% "
          f"penalty={r['penalty']} final={r['score']}%")

print(f"\nDistance distribution:")
dists = [r["raw_dist"] for r in all_results]
print(f"  Min:    {min(dists):.3f}")
print(f"  P25:    {sorted(dists)[len(dists)//4]:.3f}")
print(f"  Median: {sorted(dists)[len(dists)//2]:.3f}")
print(f"  P75:    {sorted(dists)[3*len(dists)//4]:.3f}")
print(f"  Max:    {max(dists):.3f}")
print(f"  Mean:   {sum(dists)/len(dists):.3f}")

# How many players have raw_dist < 1.0 (very close)?
close = [r for r in all_results if r["raw_dist"] < 1.0]
print(f"\n  Players within raw_dist < 1.0: {len(close)}")
print(f"  Players within raw_dist < 2.0: {len([r for r in all_results if r['raw_dist'] < 2.0])}")
print(f"  Players within raw_dist < 3.0: {len([r for r in all_results if r['raw_dist'] < 3.0])}")

# For the top 10 closest: what's killing them with penalties?
print(f"\nPenalty breakdown for Flagg's 10 closest (by raw distance):")
for r in all_results[:10]:
    # Recompute to get penalty reasons
    p = next(x for x in db if x["name"] == r["name"])
    sim = calculate_similarity(flagg, p, pos_avgs, use_v2=True)
    reasons = sim["penalty_reasons"]
    print(f"  {r['name']:25s} raw={r['raw_dist']:.2f} pen={r['penalty']:3d} "
          f"final={r['score']}% | {reasons}")

print("\n\n" + "=" * 80)
print("  DIAGNOSIS 4: CAN THE ENGINE SEPARATE TIERS AT ALL?")
print("=" * 80)

# For a generic high-major guard, what tier distribution do the top-5 comps have?
generic = {
    "name": "Generic", "pos": "G", "h": 75, "w": 195, "ws": 79,
    "age": 20.5, "level": "High Major", "ath": 2,
    "ppg": 15.0, "rpg": 4.5, "apg": 3.5, "spg": 1.2, "bpg": 0.4,
    "fg": 45.0, "threeP": 35.0, "ft": 75.0, "tpg": 2.5, "mpg": 30.0,
    "bpm": 0, "obpm": 0, "dbpm": 0, "fta": 0,
    "stl_per": 0, "usg": 0,
}
elite = {
    "name": "Elite", "pos": "G", "h": 76, "w": 205, "ws": 82,
    "age": 19.5, "level": "High Major", "ath": 3,
    "ppg": 22.0, "rpg": 5.5, "apg": 5.5, "spg": 1.8, "bpg": 0.6,
    "fg": 48.0, "threeP": 38.0, "ft": 82.0, "tpg": 3.0, "mpg": 34.0,
    "bpm": 9.0, "obpm": 6.5, "dbpm": 2.5, "fta": 6.7,
    "stl_per": 2.8, "usg": 30.0,
}
print("\nGeneric guard (average everything):")
gm = find_top_matches(generic, db, pos_avgs, top_n=5, use_v2=True)
for m in gm:
    print(f"  {m['player']['name']:25s} T{m['player']['tier']} {m['similarity']['score']}% pen={m['similarity']['penalty']}")

print(f"\nElite guard (star-level stats + advanced stats):")
em = find_top_matches(elite, db, pos_avgs, top_n=5, use_v2=True)
for m in em:
    print(f"  {m['player']['name']:25s} T{m['player']['tier']} {m['similarity']['score']}% pen={m['similarity']['penalty']}")

# Key question: does the elite guard find BETTER tier comps than the generic guard?
avg_tier_generic = sum(m["player"]["tier"] for m in gm) / 5
avg_tier_elite = sum(m["player"]["tier"] for m in em) / 5
print(f"\nAvg tier - Generic: {avg_tier_generic:.1f}, Elite: {avg_tier_elite:.1f}")
print(f"Tier separation: {avg_tier_generic - avg_tier_elite:.1f} tiers")
if avg_tier_generic - avg_tier_elite < 1.0:
    print(">>> PROBLEM: Engine can't separate average from elite by even 1 full tier!")
