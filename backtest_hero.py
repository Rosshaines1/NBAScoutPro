"""Backtest the hero section projection for 15 known players.

Feeds each player's college stats through predict_tier + find_archetype_matches
as if they were a prospect, excluding them from the comp pool so they can't
match against themselves. Prints the full hero projection for each.
"""
import json, sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import POSITIONAL_AVGS, TIER_LABELS
from app.similarity import predict_tier, find_archetype_matches, load_player_db

player_db, pos_avgs = load_player_db()

TEST_PLAYERS = [
    # Awesome (T1)
    "Stephen Curry",
    "James Harden",
    "Anthony Davis",
    "Damian Lillard",
    "Kawhi Leonard",
    # Mid (T3)
    "Zach LaVine",
    "Marcus Smart",
    "De'Aaron Fox",
    "Andrew Wiggins",
    "Tyrese Haliburton",
    # Busts (T4-5)
    "Anthony Bennett",
    "Markelle Fultz",
    "Hasheem Thabeet",
    "Jimmer Fredette",
    "Jonny Flynn",
    # Random batch 2 (2 per tier)
    "Wesley Matthews",
    "Gary Payton",
    "Juwan Howard",
    "Jae Crowder",
    "Cory Joseph",
    "Marcus Morris",
    "Kyle Singler",
    "Jordan McLaughlin",
    "Goran Suton",
    "Marcus Sasser",
]

# Build lookup
db_lookup = {p["name"]: p for p in player_db}

print("=" * 90)
print(f"{'HERO SECTION BACKTEST':^90}")
print("=" * 90)

for name in TEST_PLAYERS:
    player = db_lookup.get(name)
    if not player:
        print(f"\n  SKIP: {name} not found in DB")
        continue

    s = player.get("stats", {})
    actual_tier = player["tier"]
    actual_outcome = player.get("outcome", "?")
    nba_ws = player.get("nba_ws") or 0

    # Build prospect dict from college stats (same shape as streamlit_app.py)
    prospect = {
        "name": name,
        "pos": player["pos"],
        "h": player["h"],
        "w": player.get("w", 200),
        "ws": player.get("ws", 80),
        "age": player.get("age", 3),
        "level": player.get("level", "High Major"),
        "ath": player.get("ath", 2),
        "ppg": s.get("ppg", 0),
        "rpg": s.get("rpg", 0),
        "apg": s.get("apg", 0),
        "spg": s.get("spg", 0),
        "bpg": s.get("bpg", 0),
        "fg": s.get("fg", 45),
        "threeP": s.get("threeP", 33),
        "ft": s.get("ft", 75),
        "tpg": s.get("tpg", 0),
        "mpg": s.get("mpg", 30),
        "bpm": s.get("bpm", 0),
        "obpm": s.get("obpm", 0),
        "dbpm": s.get("dbpm", 0),
        "fta": s.get("fta", 0),
        "stl_per": s.get("stl_per", 0),
        "usg": s.get("usg", 0),
    }

    # Exclude this player from the DB so they can't comp against themselves
    filtered_db = [p for p in player_db if p["name"] != name]

    # Run both systems
    prediction = predict_tier(prospect, pos_avgs)
    arch_result = find_archetype_matches(
        prospect, filtered_db, pos_avgs, top_n=10,
        anchor_tier=prediction["tier"]
    )

    pred_tier = prediction["tier"]
    pred_label = TIER_LABELS.get(pred_tier, "?")
    archetype = arch_result["archetype"]
    secondary = arch_result["secondary"]
    closest = arch_result["closest_comp"]
    ceiling = arch_result["ceiling_comp"]
    floor = arch_result["floor_comp"]
    ceil_tier = arch_result["ceiling_tier"]
    floor_tier = arch_result["floor_tier"]

    # Closest comp boost indicator
    comp_actual = closest["player"]["tier"] if closest else pred_tier
    gap = comp_actual - pred_tier
    if gap > 0:
        boost = " " + ("+" * gap)
    elif gap < 0:
        boost = " " + ("-" * abs(gap))
    else:
        boost = ""

    # Grade the prediction
    diff = abs(pred_tier - actual_tier)
    if diff == 0:
        grade = "EXACT"
    elif diff == 1:
        grade = "CLOSE"
    else:
        grade = f"MISS (off by {diff})"

    print(f"\n{'─' * 90}")
    print(f"  {name}")
    print(f"  Actual: T{actual_tier} {actual_outcome} ({nba_ws:.0f} WS)")
    print(f"  Archetype: {archetype} (2nd: {secondary})")
    print(f"{'─' * 90}")

    # Ceiling row
    if ceiling:
        cn = ceiling["player"]["name"]
        ct = ceiling["player"]["tier"]
        cs = ceiling["similarity"]["score"]
        cw = ceiling["player"].get("nba_ws") or 0
        print(f"  Best Case   │ T{ct} {TIER_LABELS.get(ct, '?'):<20} │ {cn} ({cs:.0f}%, {cw:.0f} WS)")

    # Closest comp row
    if closest:
        mn = closest["player"]["name"]
        mt = closest["player"]["tier"]
        ms = closest["similarity"]["score"]
        print(f"  Closest Comp│ T{pred_tier} {pred_label:<20} │ {mn}{boost} ({ms:.0f}%)")

    # Floor row
    if floor:
        fn = floor["player"]["name"]
        ft_ = floor["player"]["tier"]
        fs = floor["similarity"]["score"]
        fw = floor["player"].get("nba_ws") or 0
        print(f"  Worst Case  │ T{ft_} {TIER_LABELS.get(ft_, '?'):<20} │ {fn} ({fs:.0f}%, {fw:.0f} WS)")

    print(f"  Model Lean  │ T{pred_tier} {pred_label} (Score: {prediction['score']:.0f}/120+)")
    print(f"  Result: {grade}")

print(f"\n{'=' * 90}")

# Summary
print(f"\n{'SUMMARY':^90}")
print(f"{'─' * 90}")
exact = close = miss = 0
for name in TEST_PLAYERS:
    player = db_lookup.get(name)
    if not player:
        continue
    s = player.get("stats", {})
    prospect = {
        "name": name, "pos": player["pos"], "h": player["h"],
        "w": player.get("w", 200), "ws": player.get("ws", 80),
        "age": player.get("age", 3), "level": player.get("level", "High Major"),
        "ath": player.get("ath", 2),
        "ppg": s.get("ppg", 0), "rpg": s.get("rpg", 0), "apg": s.get("apg", 0),
        "spg": s.get("spg", 0), "bpg": s.get("bpg", 0),
        "fg": s.get("fg", 45), "threeP": s.get("threeP", 33), "ft": s.get("ft", 75),
        "tpg": s.get("tpg", 0), "mpg": s.get("mpg", 30),
        "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0), "dbpm": s.get("dbpm", 0),
        "fta": s.get("fta", 0), "stl_per": s.get("stl_per", 0), "usg": s.get("usg", 0),
    }
    pred = predict_tier(prospect, pos_avgs)
    d = abs(pred["tier"] - player["tier"])
    if d == 0:
        exact += 1
    elif d == 1:
        close += 1
    else:
        miss += 1
    print(f"  {name:<25} Actual: T{player['tier']}  Predicted: T{pred['tier']}  {'EXACT' if d==0 else 'CLOSE' if d==1 else f'MISS ({d})'}")

total = exact + close + miss
print(f"\n  Exact: {exact}/{total}  |  Within 1: {exact+close}/{total}  |  Miss: {miss}/{total}")
print("=" * 90)
