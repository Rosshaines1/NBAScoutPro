"""Quick test of V4 archetype matching + floor/ceiling."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.similarity import classify_archetype, find_archetype_matches, load_player_db, predict_tier
from config import TIER_LABELS

db, pos_avgs = load_player_db()

# Test prospect: Curry-like scoring guard
prospect_sg = {
    "name": "Test Scoring Guard", "pos": "G", "h": 75, "w": 185, "ws": 80,
    "age": 21, "level": "Mid Major", "ath": 2,
    "ppg": 29, "rpg": 4, "apg": 5, "spg": 1.6, "bpg": 0.1,
    "fg": 46, "threeP": 39, "ft": 88, "tpg": 3.5, "mpg": 34,
    "bpm": 11, "obpm": 9, "dbpm": 2, "fta": 5.7,
    "stl_per": 2.2, "usg": 28,
}

# Test prospect: KAT-like skilled big
prospect_sb = {
    "name": "Test Skilled Big", "pos": "B", "h": 84, "w": 248, "ws": 89,
    "age": 19, "level": "High Major", "ath": 3,
    "ppg": 10, "rpg": 7, "apg": 1, "spg": 0.5, "bpg": 1.5,
    "fg": 57, "threeP": 25, "ft": 81, "tpg": 1.5, "mpg": 21,
    "bpm": 8, "obpm": 4, "dbpm": 4, "fta": 3.3,
    "stl_per": 1.0, "usg": 22,
}

# Test prospect: Mikal Bridges-like 3&D wing
prospect_3d = {
    "name": "Test 3&D Wing", "pos": "W", "h": 79, "w": 210, "ws": 84,
    "age": 22, "level": "High Major", "ath": 2,
    "ppg": 13, "rpg": 5, "apg": 2, "spg": 1.4, "bpg": 0.5,
    "fg": 48, "threeP": 38, "ft": 80, "tpg": 1.5, "mpg": 30,
    "bpm": 5, "obpm": 3, "dbpm": 2, "fta": 2.0,
    "stl_per": 2.0, "usg": 18,
}

def show_report(prospect, db, pos_avgs):
    """Display a full scout report for a prospect."""
    arch, score, secondary = classify_archetype(prospect)
    print("=" * 70)
    print(f"  {prospect['name']} -- {arch} (score={score}, 2nd: {secondary})")
    print("=" * 70)

    result = find_archetype_matches(prospect, db, pos_avgs, top_n=5)
    pool = result["pool_size"]
    print(f"  Pool: {pool} {result['archetype']} players in DB")

    ceil_name = result["ceiling_comp"]["player"]["name"] if result["ceiling_comp"] else "?"
    floor_name = result["floor_comp"]["player"]["name"] if result["floor_comp"] else "?"
    ceil_tier = result["ceiling_tier"]
    floor_tier = result["floor_tier"]
    likely = result["most_likely_tier"]

    print(f"  Ceiling:     T{ceil_tier} {TIER_LABELS.get(ceil_tier, '?')} (comp: {ceil_name})")
    print(f"  Most Likely: T{likely} {TIER_LABELS.get(likely, '?')}")
    print(f"  Floor:       T{floor_tier} {TIER_LABELS.get(floor_tier, '?')} (comp: {floor_name})")
    print()

    pred = predict_tier(prospect, pos_avgs)
    print(f"  Model Prediction: T{pred['tier']} ({pred['score']:.0f}/120+)")
    print()

    print("  Top 5 Same-Archetype Comps:")
    for i, m in enumerate(result["matches"]):
        p = m["player"]
        s = p["stats"]
        ws = p.get("nba_ws", 0) or 0
        print(f"    #{i+1}: {p['name']:25s} T{p['tier']} {m['similarity']['score']:.0f}% | "
              f"{s['ppg']:.0f}ppg {s['rpg']:.0f}rpg {s['apg']:.0f}apg WS={ws:.0f}")
    print()


# --- Synthetic prospects ---
print("\n" + "#" * 70)
print("  PART 1: SYNTHETIC PROSPECTS")
print("#" * 70)
for prospect in [prospect_sg, prospect_sb, prospect_3d]:
    show_report(prospect, db, pos_avgs)

# --- Real players from DB (leave-one-out test) ---
print("\n" + "#" * 70)
print("  PART 2: REAL PLAYER LEAVE-ONE-OUT VALIDATION")
print("#" * 70)

test_players = [
    "Stephen Curry", "James Harden", "Damian Lillard",  # Scoring Guards
    "Karl-Anthony Towns", "Joel Embiid",                 # Bigs
    "Kawhi Leonard", "Paul George", "Jayson Tatum",      # Scoring Wings
    "Mikal Bridges",                                     # 3&D Wing
    "Gary Payton",                                       # Playmaking Guard
    "Frank Kaminsky", "Jarrett Culver",                  # Busts
]

for name in test_players:
    p = next((x for x in db if x["name"] == name), None)
    if not p or not p.get("has_college_stats"):
        print(f"\n  {name}: NOT FOUND")
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

    # Filter self out of DB
    db_filtered = [x for x in db if x["name"] != name]

    arch, _, secondary = classify_archetype(prospect)
    result = find_archetype_matches(prospect, db_filtered, pos_avgs, top_n=10)

    actual_tier = p["tier"]
    ws = p.get("nba_ws", 0) or 0

    ceil = result["ceiling_tier"]
    floor = result["floor_tier"]
    likely = result["most_likely_tier"]
    ceil_name = result["ceiling_comp"]["player"]["name"] if result["ceiling_comp"] else "?"
    floor_name = result["floor_comp"]["player"]["name"] if result["floor_comp"] else "?"

    # Check if actual tier is within floor-ceiling range
    in_range = "YES" if ceil <= actual_tier <= floor else "NO"

    print(f"\n  {name:25s} Actual=T{actual_tier} (WS={ws:.0f}) | {arch}")
    print(f"    Ceiling: T{ceil} ({ceil_name}) | Likely: T{likely} | Floor: T{floor} ({floor_name}) | In range: {in_range}")
    comps = ", ".join(f"{m['player']['name']}(T{m['player']['tier']})" for m in result["matches"][:3])
    print(f"    Top 3: {comps}")
