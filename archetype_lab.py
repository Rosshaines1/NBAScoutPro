"""Archetype Lab: Test archetype classification on the full database.

Step 1: Classify all players, check bucket sizes
Step 2: Validate known players land in sensible archetypes
Step 3: Check tier distribution within each archetype
"""
import json, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS

with open(PLAYER_DB_PATH) as f:
    DB = json.load(f)


def classify_archetype(player):
    """Classify a player (DB entry or prospect dict) into an archetype.

    Returns (primary_archetype, confidence_score, secondary_archetype).
    Works with both DB entries (stats nested) and prospect dicts (stats flat).
    """
    # Handle both DB format (stats nested) and prospect format (stats flat)
    if "stats" in player:
        s = player["stats"]
        pos = player.get("pos", "W")
        h = player.get("h", 78)
    else:
        s = player  # prospect dict has flat stats
        pos = player.get("pos", "W")
        h = player.get("h", 78)

    ppg = s.get("ppg", 0) or 0
    rpg = s.get("rpg", 0) or 0
    apg = s.get("apg", 0) or 0
    spg = s.get("spg", 0) or 0
    bpg = s.get("bpg", 0) or 0
    tpg = s.get("tpg", 0) or 0
    mpg = s.get("mpg", 30) or 30
    fg = s.get("fg", 45) or 45
    threeP = s.get("threeP", 33) or 33
    ft = s.get("ft", 70) or 70
    fta = s.get("fta", 0) or 0
    usg = s.get("usg", 0) or 0
    bpm = s.get("bpm", 0) or 0
    obpm = s.get("obpm", 0) or 0
    dbpm = s.get("dbpm", 0) or 0
    rim_att = s.get("rim_att", 0) or 0
    stl_per = s.get("stl_per", 0) or 0

    ato = apg / tpg if tpg > 0 else apg
    fta_pg = fta  # already per-game

    # Guard affinity: wings who play like guards (short + guard-like stats)
    guard_like = False
    if pos == "W":
        if h <= 76:  # 6'4" or shorter — basically a guard
            guard_like = True
        elif h <= 78 and (apg >= 3.5 or (ppg >= 18 and rpg < 5)):
            guard_like = True  # undersized wing with guard profile

    # Score each archetype — highest score wins
    scores = {}

    # --- SCORING GUARD ---
    # High-volume scorers who create their own shot
    sg_score = 0
    if pos == "G":
        sg_score += 12
    elif guard_like:
        sg_score += 8
    if ppg >= 20: sg_score += 10
    elif ppg >= 16: sg_score += 6
    elif ppg >= 12: sg_score += 3
    if usg >= 28: sg_score += 6
    elif usg >= 24: sg_score += 3
    if fta_pg >= 5: sg_score += 4
    elif fta_pg >= 3: sg_score += 2
    if ft >= 78: sg_score += 3
    if threeP >= 35: sg_score += 2
    if apg >= 4: sg_score += 2  # can create for others
    scores["Scoring Guard"] = sg_score

    # --- PLAYMAKING GUARD ---
    # Pass-first, high assist, controls tempo
    pg_score = 0
    if pos == "G":
        pg_score += 12
    elif guard_like and apg >= 3:
        pg_score += 8
    elif pos == "W" and apg >= 5:
        pg_score += 6  # any wing with 5+ APG is a playmaker
    if apg >= 6: pg_score += 10
    elif apg >= 4.5: pg_score += 7
    elif apg >= 3.5: pg_score += 4
    elif apg >= 2.5: pg_score += 2
    if ato >= 2.5: pg_score += 6
    elif ato >= 1.8: pg_score += 4
    elif ato >= 1.3: pg_score += 2
    if spg >= 1.5: pg_score += 3
    if stl_per >= 2.5: pg_score += 3
    if ppg < 14: pg_score += 2  # not score-first
    scores["Playmaking Guard"] = pg_score

    # --- 3&D WING ---
    # Shooting + defense, NOT a primary scorer — role player archetype
    td_score = 0
    if pos == "W":
        td_score += 8  # reduced from 10 — must earn it with stats
    elif pos == "G" and h >= 76:
        td_score += 4
    # Require real 3P evidence
    if threeP >= 38: td_score += 7
    elif threeP >= 35: td_score += 5
    elif threeP >= 33: td_score += 3
    # No points for sub-33%
    if ft >= 78: td_score += 3
    elif ft >= 73: td_score += 1
    # Defensive contribution
    if spg >= 1.5: td_score += 5
    elif spg >= 1.0: td_score += 3
    elif spg >= 0.8: td_score += 1
    if bpg >= 0.8: td_score += 2
    if dbpm >= 3.0: td_score += 3
    elif dbpm >= 1.5: td_score += 1
    # Anti-scorer: high PPG means you're a scorer, not a role player
    if ppg < 12: td_score += 3
    elif ppg < 15: td_score += 1
    elif ppg >= 20: td_score -= 5
    elif ppg >= 18: td_score -= 3
    scores["3&D Wing"] = td_score

    # --- SCORING WING ---
    # Primary scorer with size, high usage
    sw_score = 0
    if pos == "W":
        sw_score += 10
    elif pos == "B" and h <= 81:
        sw_score += 5
    elif pos == "G" and h >= 77:
        sw_score += 5
    if ppg >= 20: sw_score += 10
    elif ppg >= 16: sw_score += 7
    elif ppg >= 13: sw_score += 4
    elif ppg >= 10: sw_score += 1
    if usg >= 28: sw_score += 6
    elif usg >= 24: sw_score += 4
    elif usg >= 20: sw_score += 2
    if fta_pg >= 5: sw_score += 4
    elif fta_pg >= 3: sw_score += 2
    if h >= 79: sw_score += 3  # real size
    elif h >= 77: sw_score += 1
    if rpg >= 7: sw_score += 3
    elif rpg >= 5: sw_score += 1
    scores["Scoring Wing"] = sw_score

    # --- SKILLED BIG ---
    # Can shoot, good touch, skilled offense
    sb_score = 0
    if pos == "B":
        sb_score += 10
    elif pos == "W" and h >= 81:
        sb_score += 5
    if ft >= 78: sb_score += 8
    elif ft >= 72: sb_score += 6
    elif ft >= 65: sb_score += 3
    if threeP >= 33: sb_score += 6
    elif threeP >= 25: sb_score += 3
    elif threeP >= 15: sb_score += 1
    if rpg >= 8: sb_score += 3
    elif rpg >= 6: sb_score += 1
    if bpm >= 6: sb_score += 4
    elif bpm >= 3: sb_score += 2
    if obpm >= 4: sb_score += 4
    elif obpm >= 2: sb_score += 2
    if ppg >= 15: sb_score += 2  # offensive production
    scores["Skilled Big"] = sb_score

    # --- ATHLETIC BIG ---
    # Rim protection, rebounding, physicality over skill
    ab_score = 0
    if pos == "B":
        ab_score += 10
    elif pos == "W" and h >= 82:
        ab_score += 5
    if bpg >= 2.5: ab_score += 8
    elif bpg >= 1.5: ab_score += 5
    elif bpg >= 1.0: ab_score += 3
    if rim_att >= 4.0: ab_score += 6
    elif rim_att >= 2.5: ab_score += 4
    elif rim_att >= 1.0: ab_score += 2
    if rpg >= 9: ab_score += 5
    elif rpg >= 7: ab_score += 3
    elif rpg >= 5: ab_score += 1
    if dbpm >= 5: ab_score += 5
    elif dbpm >= 3: ab_score += 3
    elif dbpm >= 1: ab_score += 1
    # Skill anti-signals: good shooters aren't athletic bigs
    if ft < 55: ab_score += 4
    elif ft < 65: ab_score += 2
    elif ft >= 78: ab_score -= 4
    elif ft >= 72: ab_score -= 2
    scores["Athletic Big"] = ab_score

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    primary = ranked[0][0]
    primary_score = ranked[0][1]
    secondary = ranked[1][0]

    return primary, primary_score, secondary


# =====================================================================
#  Run classification on all players
# =====================================================================
results = []
for p in DB:
    if not p.get("has_college_stats"):
        continue
    arch, score, secondary = classify_archetype(p)
    results.append({
        "name": p["name"], "pos": p["pos"], "archetype": arch,
        "arch_score": score, "secondary": secondary,
        "tier": p["tier"], "ws": p.get("nba_ws", 0) or 0,
        "pick": p.get("draft_pick", 99),
        "ppg": p["stats"]["ppg"], "apg": p["stats"]["apg"],
        "rpg": p["stats"]["rpg"], "bpg": p["stats"]["bpg"],
        "ft": p["stats"].get("ft", 70),
        "threeP": p["stats"].get("threeP", 33),
    })

# --- Bucket sizes ---
print("=" * 70)
print("  ARCHETYPE BUCKET SIZES")
print("=" * 70)
arch_counts = Counter(r["archetype"] for r in results)
for arch, count in sorted(arch_counts.items(), key=lambda x: -x[1]):
    pct = count / len(results) * 100
    bar = "#" * (count // 5)
    print(f"  {arch:20s} {count:4d} ({pct:4.1f}%) {bar}")
print(f"  {'TOTAL':20s} {len(results):4d}")

# --- Tier distribution per archetype ---
print(f"\n{'=' * 70}")
print("  TIER DISTRIBUTION PER ARCHETYPE")
print("=" * 70)
for arch in sorted(arch_counts.keys()):
    players = [r for r in results if r["archetype"] == arch]
    tiers = Counter(r["tier"] for r in players)
    total = len(players)
    print(f"\n  {arch} ({total} players):")
    for t in range(1, 6):
        c = tiers.get(t, 0)
        pct = c / total * 100
        print(f"    T{t}: {c:4d} ({pct:4.1f}%)")

# --- Validate known players ---
print(f"\n{'=' * 70}")
print("  KNOWN PLAYER VALIDATION")
print("=" * 70)
check = [
    # Scoring Guards
    "Stephen Curry", "James Harden", "Damian Lillard", "Kyrie Irving",
    "Jimmer Fredette", "Trey Burke",
    # Playmaking Guards
    "Gary Payton", "Jrue Holiday",
    # 3&D Wings
    "Kawhi Leonard", "Mikal Bridges",
    # Scoring Wings
    "Paul George", "DeMar DeRozan", "Jayson Tatum", "Jaylen Brown",
    "Josh Jackson", "Jarrett Culver",
    # Skilled Bigs
    "Karl-Anthony Towns", "Anthony Davis", "Frank Kaminsky",
    "Joel Embiid",
    # Athletic Bigs
    "Andre Drummond", "Bam Adebayo", "Hasheem Thabeet",
    "Marvin Bagley III",
]
for name in check:
    r = next((x for x in results if x["name"] == name), None)
    if not r:
        print(f"  {name:25s} NOT FOUND")
        continue
    tier_label = f"T{r['tier']}"
    print(f"  {name:25s} -> {r['archetype']:20s} (2nd: {r['secondary']:20s}) "
          f"{tier_label} WS={r['ws']:5.0f}")

# --- Show top players per archetype ---
print(f"\n{'=' * 70}")
print("  TOP PLAYERS PER ARCHETYPE (by NBA WS)")
print("=" * 70)
for arch in sorted(arch_counts.keys()):
    players = sorted([r for r in results if r["archetype"] == arch],
                     key=lambda x: -x["ws"])
    print(f"\n  {arch}:")
    for p in players[:8]:
        print(f"    {p['name']:25s} T{p['tier']} WS={p['ws']:5.0f} | "
              f"{p['ppg']:.0f}ppg {p['apg']:.0f}apg {p['rpg']:.0f}rpg "
              f"FT={p['ft']:.0f}% 3P={p['threeP']:.0f}%")
