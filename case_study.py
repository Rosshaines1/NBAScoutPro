"""Case study: Deep dive into specific problem players.

Compare players who are way off to find differentiating patterns.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR

with open(PLAYER_DB_PATH) as f:
    DB = json.load(f)

def show_player(name):
    matches = [p for p in DB if p["name"] == name]
    if not matches:
        print(f"  {name}: NOT FOUND")
        return
    p = matches[0]
    s = p["stats"]
    print(f"\n  {'=' * 60}")
    print(f"  {name} — T{p['tier']} ({p.get('outcome','?')})")
    print(f"  {'=' * 60}")
    print(f"  Pick #{p.get('draft_pick','?')} ({p.get('draft_year','?')}) | NBA WS: {p.get('nba_ws',0):.1f}")
    print(f"  College: {p.get('college','?')} | Level: {p['level']} | Pos: {p['pos']}")
    print(f"  Height: {p['h']}\" | Weight: {p['w']} | Wingspan: {p.get('ws', '?')}\"")
    print(f"")
    print(f"  COUNTING STATS:")
    print(f"    PPG={s['ppg']:.1f}  RPG={s['rpg']:.1f}  APG={s['apg']:.1f}  SPG={s['spg']:.1f}  BPG={s['bpg']:.1f}")
    print(f"    MPG={s['mpg']:.1f}  TPG={s['tpg']:.1f}  GP={s.get('gp', '?')}")
    print(f"")
    print(f"  SHOOTING:")
    print(f"    eFG={s['fg']:.1f}%  3P={s['threeP']:.1f}%  FT={s['ft']:.1f}%")
    print(f"    FTA={s.get('fta',0):.0f}  FTM={s.get('ftm',0):.0f}")
    print(f"")
    print(f"  ADVANCED:")
    print(f"    BPM={s.get('bpm',0):.1f}  OBPM={s.get('obpm',0):.1f}  DBPM={s.get('dbpm',0):.1f}")
    print(f"    USG={s.get('usg',0):.1f}  STL%={s.get('stl_per',0):.1f}  TS%={s.get('ts_per',0):.1f}")
    print(f"    Stops={s.get('stops',0):.1f}  RimAtt={s.get('rim_att',0):.1f}")
    print(f"    ADJOE={s.get('adjoe',0):.1f}  ADRTG={s.get('adrtg',0):.1f}")
    return p


print("=" * 70)
print("  CASE STUDY 1: FALSE POSITIVE BUSTS vs REAL STARS (LOTTERY)")
print("  Question: What separates lottery busts from lottery stars?")
print("=" * 70)

print("\n  --- LOTTERY BUSTS (predicted star, actually bust) ---")
show_player("Frank Kaminsky")      # #9, T4, BPM=13.8
show_player("Jarrett Culver")      # #6, T5, BPM=10.3
show_player("Josh Jackson")        # #4, T5, BPM=9.1
show_player("Kris Dunn")           # #5, T4, BPM=9.7
show_player("Marvin Bagley III")   # #2, T4, BPM=8.7
show_player("Jahlil Okafor")       # #3, T4

print("\n  --- LOTTERY STARS (real superstars) ---")
show_player("James Harden")        # #3, T1
show_player("Anthony Davis")       # #1, T1
show_player("Kyrie Irving")        # #1, T1
show_player("Damian Lillard")      # #6, T1
show_player("Blake Griffin")       # #1, T1
show_player("Stephen Curry")       # #7, T1

print("\n\n" + "=" * 70)
print("  CASE STUDY 2: MISSED SUPERSTARS")
print("  Question: Is there ANY stat signal we're missing?")
print("=" * 70)

show_player("DeMar DeRozan")       # #9, T1, low stats
show_player("Devin Booker")        # #13, T2, low minutes
show_player("Paul George")         # #10, T1, mid major
show_player("Kawhi Leonard")       # #15, T1
show_player("Tobias Harris")       # #19, T2
show_player("Myles Turner")        # #11, T2


print("\n\n" + "=" * 70)
print("  PATTERN ANALYSIS: Lottery busts vs lottery stars")
print("=" * 70)

bust_names = ["Frank Kaminsky", "Jarrett Culver", "Josh Jackson", "Kris Dunn",
              "Marvin Bagley III", "Jahlil Okafor", "Markelle Fultz", "Lonzo Ball",
              "Trey Burke", "Denzel Valentine"]
star_names = ["James Harden", "Anthony Davis", "Kyrie Irving", "Damian Lillard",
              "Blake Griffin", "Stephen Curry", "Karl-Anthony Towns", "Jimmy Butler",
              "Kawhi Leonard"]

def avg_stat(names, stat_key, from_stats=True):
    vals = []
    for name in names:
        p = next((x for x in DB if x["name"] == name), None)
        if not p:
            continue
        if from_stats:
            v = p["stats"].get(stat_key, 0) or 0
        else:
            v = p.get(stat_key, 0) or 0
        vals.append(v)
    return sum(vals) / len(vals) if vals else 0

print(f"\n  {'Stat':>15s} {'Busts':>10s} {'Stars':>10s} {'Difference':>12s}")
print(f"  {'-' * 48}")
for stat in ["bpm", "obpm", "dbpm", "fta", "ppg", "rpg", "apg", "spg",
             "mpg", "usg", "stl_per", "fg", "ft", "threeP"]:
    b = avg_stat(bust_names, stat)
    s = avg_stat(star_names, stat)
    diff = s - b
    marker = " ***" if abs(diff) > abs(b) * 0.3 else ""
    print(f"  {stat:>15s} {b:10.1f} {s:10.1f} {diff:+11.1f}{marker}")

for stat in ["draft_pick", "h", "w"]:
    b = avg_stat(bust_names, stat, from_stats=False)
    s = avg_stat(star_names, stat, from_stats=False)
    diff = s - b
    marker = " ***" if abs(diff) > 3 else ""
    print(f"  {stat:>15s} {b:10.1f} {s:10.1f} {diff:+11.1f}{marker}")

# What about per-minute stats?
print(f"\n  PER-MINUTE RATES (per 30 minutes):")
for stat in ["ppg", "rpg", "apg", "spg", "bpg"]:
    b_vals, s_vals = [], []
    for name in bust_names:
        p = next((x for x in DB if x["name"] == name), None)
        if not p: continue
        mpg = p["stats"].get("mpg", 30) or 30
        v = (p["stats"].get(stat, 0) or 0) / mpg * 30
        b_vals.append(v)
    for name in star_names:
        p = next((x for x in DB if x["name"] == name), None)
        if not p: continue
        mpg = p["stats"].get("mpg", 30) or 30
        v = (p["stats"].get(stat, 0) or 0) / mpg * 30
        s_vals.append(v)
    b = sum(b_vals) / len(b_vals) if b_vals else 0
    s = sum(s_vals) / len(s_vals) if s_vals else 0
    diff = s - b
    print(f"  {stat+'/30':>15s} {b:10.1f} {s:10.1f} {diff:+11.1f}")

# FTA per game (rate instead of volume)
print(f"\n  RATE STATS:")
for name_list, label in [(bust_names, "Busts"), (star_names, "Stars")]:
    fta_pg_vals = []
    for name in name_list:
        p = next((x for x in DB if x["name"] == name), None)
        if not p: continue
        fta = p["stats"].get("fta", 0) or 0
        fta_pg_vals.append(fta)
    print(f"  {label:>15s} FTA/game: {sum(fta_pg_vals)/len(fta_pg_vals):.1f}")
