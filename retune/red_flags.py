"""Analyze counter-indicators: stat contradictions that predict bust outcomes.

Goal: Find "If X looks good BUT Y is bad → red flag" rules.
Uses corrected tier labels (Feb 2026).

Focus on players who LOOK like stars but aren't:
- Have 1+ star signals but ended up T4/T5
- Have above-average counting stats but busted
These are the false positives we need to catch.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, LEVEL_MODIFIERS, STAR_SIGNAL_THRESHOLDS
from app.similarity import count_star_signals, predict_tier

with open(PLAYER_DB_PATH, encoding="utf-8") as f:
    db = json.load(f)

# Filter to clean dataset: 2009-2019, college stats, known outcomes
clean = [
    p for p in db
    if p.get("has_college_stats")
    and 2009 <= (p.get("draft_year") or 0) <= 2019
    and p.get("nba_ws") is not None
]
print(f"Clean dataset: {len(clean)} players\n")

def get_stat(p, key):
    return p.get("stats", {}).get(key, 0) or 0

def is_star(p):
    return p["tier"] in (1, 2)

def is_bust(p):
    return p["tier"] in (4, 5)

def is_starter(p):
    return p["tier"] == 3

# Build flat stat dicts for analysis
players = []
for p in clean:
    s = p["stats"]
    flat = {
        "name": p["name"], "tier": p["tier"], "pos": p["pos"],
        "draft_pick": p.get("draft_pick", 61),
        "draft_year": p.get("draft_year"),
        "level": p.get("level", "High Major"),
        "age": p.get("age", 4),
        "ppg": s.get("ppg", 0), "rpg": s.get("rpg", 0), "apg": s.get("apg", 0),
        "spg": s.get("spg", 0), "bpg": s.get("bpg", 0), "tpg": s.get("tpg", 0),
        "fg": s.get("fg", 45), "threeP": s.get("threeP", 0), "ft": s.get("ft", 70),
        "mpg": s.get("mpg", 30), "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
        "dbpm": s.get("dbpm", 0), "fta": s.get("fta", 0), "usg": s.get("usg", 0),
        "stl_per": s.get("stl_per", 0), "nba_ws": p.get("nba_ws", 0),
    }
    # Derived
    flat["ato"] = flat["apg"] / flat["tpg"] if flat["tpg"] > 0 else flat["apg"]
    flat["fta_per_ppg"] = flat["fta"] / flat["ppg"] if flat["ppg"] > 0 else 0
    flat["bpm_minus_obpm"] = flat["bpm"] - flat["obpm"]  # negative = offense-only
    flat["ppg_per_usg"] = flat["ppg"] / flat["usg"] if flat["usg"] > 0 else 0
    players.append(flat)

stars = [p for p in players if p["tier"] in (1, 2)]
busts = [p for p in players if p["tier"] in (4, 5)]
starters = [p for p in players if p["tier"] == 3]

print(f"Stars (T1+T2): {len(stars)}")
print(f"Starters (T3): {len(starters)}")
print(f"Busts (T4+T5): {len(busts)}")

# ============================================================
# ANALYSIS 1: FALSE STARS
# Players with star-level counting stats who busted
# ============================================================
print("\n" + "=" * 60)
print("FALSE STARS: Good surface stats, bad outcomes")
print("=" * 60)

# Who are the false stars? High PPG/BPM busts
false_stars = [p for p in busts if p["ppg"] >= 16 or p["bpm"] >= 7]
print(f"\nBusts with PPG>=16 or BPM>=7: {len(false_stars)}")
for p in sorted(false_stars, key=lambda x: x["nba_ws"]):
    print(f"  T{p['tier']} {p['name']:25s} {p['ppg']:.1f}ppg {p['fg']:.0f}%eFG "
          f"{p['ft']:.0f}%FT BPM={p['bpm']:.1f} USG={p['usg']:.0f} "
          f"FTA={p['fta']:.1f} {p['level']} age={p['age']} "
          f"WS={p['nba_ws']:.0f}")

# ============================================================
# ANALYSIS 2: CONTRADICTION RULES
# Test specific if/then combinations
# ============================================================
print("\n" + "=" * 60)
print("CONTRADICTION RULES: If good X but bad Y")
print("=" * 60)

def test_rule(name, good_filter, bad_filter):
    """Test a contradiction rule: players who pass good_filter AND bad_filter."""
    matches = [p for p in players if good_filter(p) and bad_filter(p)]
    if not matches:
        print(f"\n{name}: 0 matches")
        return
    n = len(matches)
    n_star = sum(1 for p in matches if p["tier"] in (1, 2))
    n_bust = sum(1 for p in matches if p["tier"] in (4, 5))
    n_starter = sum(1 for p in matches if p["tier"] == 3)
    bust_rate = n_bust / n * 100
    star_rate = n_star / n * 100
    print(f"\n{name}: {n} players")
    print(f"  Stars: {n_star} ({star_rate:.0f}%) | Starters: {n_starter} | Busts: {n_bust} ({bust_rate:.0f}%)")
    # Show some examples
    for p in sorted(matches, key=lambda x: x["tier"], reverse=True)[:5]:
        print(f"    T{p['tier']} {p['name']:25s} {p['ppg']:.1f}ppg eFG={p['fg']:.0f} FT={p['ft']:.0f} "
              f"BPM={p['bpm']:.1f} USG={p['usg']:.0f} FTA={p['fta']:.1f}")

# Rule 1: High usage but low BPM (empty calories)
test_rule("High USG (>24) + Low BPM (<6)",
          lambda p: p["usg"] >= 24,
          lambda p: p["bpm"] < 6)

test_rule("High USG (>26) + Low BPM (<7)",
          lambda p: p["usg"] >= 26,
          lambda p: p["bpm"] < 7)

# Rule 2: High scoring but bad efficiency
test_rule("High PPG (>16) + Low eFG (<48)",
          lambda p: p["ppg"] >= 16,
          lambda p: p["fg"] < 48)

test_rule("High PPG (>14) + Low eFG (<46)",
          lambda p: p["ppg"] >= 14,
          lambda p: p["fg"] < 46)

# Rule 3: High scoring but low FT% (broken shot for guards/wings)
test_rule("Guard/Wing + PPG>14 + FT<68",
          lambda p: p["pos"] in ("G", "W") and p["ppg"] >= 14,
          lambda p: p["ft"] < 68)

# Rule 4: High BPM but low eFG (stat-stuffing but can't shoot)
test_rule("High BPM (>7) + Low eFG (<48)",
          lambda p: p["bpm"] >= 7,
          lambda p: p["fg"] < 48)

# Rule 5: Senior with good stats (already peaked)
test_rule("Senior (age=4) + PPG>14",
          lambda p: p["age"] >= 4,
          lambda p: p["ppg"] >= 14)

test_rule("Senior (age=4) + BPM>7",
          lambda p: p["age"] >= 4,
          lambda p: p["bpm"] >= 7)

# Rule 6: High turnovers relative to assists
test_rule("APG>3 + ATO<1.0 (turnover machine)",
          lambda p: p["apg"] >= 3,
          lambda p: p["ato"] < 1.0)

# Rule 7: Low FTA despite high usage (can't draw fouls = can't create)
test_rule("High USG (>24) + Low FTA (<3)",
          lambda p: p["usg"] >= 24,
          lambda p: p["fta"] < 3)

# Rule 8: Mid/Low major with star signals
test_rule("Mid/Low Major + BPM>8",
          lambda p: p["level"] in ("Mid Major", "Low Major"),
          lambda p: p["bpm"] >= 8)

test_rule("Low Major + PPG>18",
          lambda p: p["level"] == "Low Major",
          lambda p: p["ppg"] >= 18)

# Rule 9: High scoring guard who doesn't get to the line
test_rule("Guard + PPG>15 + FTA<3",
          lambda p: p["pos"] == "G" and p["ppg"] >= 15,
          lambda p: p["fta"] < 3)

# Rule 10: Big with no defensive impact
test_rule("Big + RPG>7 + DBPM<2 + BPG<1",
          lambda p: p["pos"] == "B" and p["rpg"] >= 7,
          lambda p: p["dbpm"] < 2 and p["bpg"] < 1)

# Rule 11: Offensive-only player (high OBPM, low/negative DBPM)
test_rule("OBPM>5 + DBPM<1 (offense-only)",
          lambda p: p["obpm"] >= 5,
          lambda p: p["dbpm"] < 1)

# Rule 12: High volume scorer at low minutes (small sample inflated per-game)
test_rule("PPG>16 + MPG<28 (inflated per-game?)",
          lambda p: p["ppg"] >= 16,
          lambda p: p["mpg"] < 28)

# ============================================================
# ANALYSIS 3: STAR vs BUST separator within high-stat players
# Among players with BPM >= 7, what separates stars from busts?
# ============================================================
print("\n" + "=" * 60)
print("WITHIN HIGH-BPM PLAYERS (>=7): What separates stars from busts?")
print("=" * 60)

high_bpm = [p for p in players if p["bpm"] >= 7]
high_bpm_stars = [p for p in high_bpm if p["tier"] in (1, 2)]
high_bpm_busts = [p for p in high_bpm if p["tier"] in (4, 5)]

print(f"\nHigh BPM players: {len(high_bpm)} (stars={len(high_bpm_stars)}, busts={len(high_bpm_busts)})")

if high_bpm_stars and high_bpm_busts:
    compare_stats = ["ppg", "fg", "ft", "fta", "usg", "obpm", "dbpm", "age", "tpg", "ato", "mpg"]
    print(f"\n{'Stat':>10s}  {'Star avg':>10s}  {'Bust avg':>10s}  {'Gap':>8s}")
    print("-" * 45)
    for stat in compare_stats:
        star_avg = sum(p[stat] for p in high_bpm_stars) / len(high_bpm_stars)
        bust_avg = sum(p[stat] for p in high_bpm_busts) / len(high_bpm_busts)
        gap = star_avg - bust_avg
        marker = " ***" if abs(gap) > 2 else " *" if abs(gap) > 1 else ""
        print(f"{stat:>10s}  {star_avg:10.1f}  {bust_avg:10.1f}  {gap:+8.2f}{marker}")

# ============================================================
# ANALYSIS 4: Within high-PPG players
# ============================================================
print("\n" + "=" * 60)
print("WITHIN HIGH-PPG PLAYERS (>=16): What separates stars from busts?")
print("=" * 60)

high_ppg = [p for p in players if p["ppg"] >= 16]
high_ppg_stars = [p for p in high_ppg if p["tier"] in (1, 2)]
high_ppg_busts = [p for p in high_ppg if p["tier"] in (4, 5)]

print(f"\nHigh PPG players: {len(high_ppg)} (stars={len(high_ppg_stars)}, busts={len(high_ppg_busts)})")

if high_ppg_stars and high_ppg_busts:
    compare_stats = ["bpm", "fg", "ft", "fta", "usg", "obpm", "dbpm", "age", "tpg", "ato", "spg", "stl_per"]
    print(f"\n{'Stat':>10s}  {'Star avg':>10s}  {'Bust avg':>10s}  {'Gap':>8s}")
    print("-" * 45)
    for stat in compare_stats:
        star_avg = sum(p[stat] for p in high_ppg_stars) / len(high_ppg_stars)
        bust_avg = sum(p[stat] for p in high_ppg_busts) / len(high_ppg_busts)
        gap = star_avg - bust_avg
        marker = " ***" if abs(gap) > 2 else " *" if abs(gap) > 1 else ""
        print(f"{stat:>10s}  {star_avg:10.1f}  {bust_avg:10.1f}  {gap:+8.2f}{marker}")

# ============================================================
# SUMMARY: Rank rules by bust rate
# ============================================================
print("\n" + "=" * 60)
print("RULE SUMMARY (ranked by bust rate)")
print("=" * 60)
