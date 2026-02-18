"""Redraft a year using the model's scores vs actual draft order vs actual outcome."""
import json
import os
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, POSITIONAL_AVGS, TIER_LABELS
from app.similarity import predict_tier

YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2018

with open(PLAYER_DB_PATH, encoding="utf-8") as f:
    db = json.load(f)

pos_avgs = POSITIONAL_AVGS
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH, encoding="utf-8") as f:
        pos_avgs = json.load(f)

# Get all players from that draft year with college stats
year_players = [
    p for p in db
    if p.get("has_college_stats")
    and p.get("draft_year") == YEAR
    and p.get("nba_ws") is not None
]

# Score each player
scored = []
for p in year_players:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p.get("w", 200),
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 4),
        "level": p.get("level", "High Major"),
        "quadrant": p.get("quadrant", "Q1"),
        "ath": p.get("ath", 0), "draft_pick": 0,
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
    scored.append({
        "name": p["name"],
        "actual_pick": p.get("draft_pick", 61),
        "actual_tier": p["tier"],
        "model_score": pred["score"],
        "model_tier": pred["tier"],
        "college": p.get("college", "?"),
        "pos": p["pos"],
        "h": p.get("h", 0),
        "age": p.get("age", 4),
        "reasons": pred["reasons"],
        "ppg": s.get("ppg", 0),
        "bpm": s.get("bpm", 0),
    })

# Sort by model score (our redraft order)
model_order = sorted(scored, key=lambda x: x["model_score"], reverse=True)

# Sort by actual pick (real draft order)
actual_order = sorted(scored, key=lambda x: x["actual_pick"])

# Sort by actual tier then WS (hindsight perfect draft)
hindsight_order = sorted(scored, key=lambda x: (x["actual_tier"], -x["model_score"]))

print(f"{'='*100}")
print(f"  {YEAR} NBA REDRAFT — Model vs Reality vs Hindsight")
print(f"  {len(scored)} players with college stats in database")
print(f"{'='*100}")

# Side by side: Model Rank | Model Pick | Actual Pick | Actual Outcome
print(f"\n{'Model':>5} {'':>3} {'Name':28s} {'College':18s} {'Pos':>3} {'Score':>6} {'Model':>6} {'Actual':>7} {'Actual':>7} {'Diff':>6}")
print(f"{'Rank':>5} {'':>3} {'':28s} {'':18s} {'':>3} {'':>6} {'Tier':>6} {'Pick':>7} {'Tier':>7} {'':>6}")
print("-" * 105)

for i, p in enumerate(model_order):
    model_rank = i + 1
    tier_label = f"T{p['model_tier']}"
    actual_tier_label = f"T{p['actual_tier']}"
    diff = p["actual_pick"] - model_rank
    diff_str = f"+{diff}" if diff > 0 else str(diff)

    # Color coding via markers
    if p["actual_tier"] in (1, 2) and p["model_tier"] in (1, 2):
        marker = " ** "  # got it right — star identified
    elif p["actual_tier"] in (1, 2) and p["model_tier"] in (4, 5):
        marker = " xx "  # missed a star
    elif p["actual_tier"] in (4, 5) and p["model_tier"] in (1, 2):
        marker = " !! "  # false star
    elif p["actual_tier"] <= p["model_tier"]:
        marker = "    "  # outperformed prediction (fine, we're optimistic)
    else:
        marker = "    "

    print(f"  {model_rank:>3}{marker}{p['name']:28s} {p['college']:18s} {p['pos']:>3} {p['model_score']:>5.0f}  {tier_label:>5}  #{p['actual_pick']:>3}    {actual_tier_label:>5}  {diff_str:>5}")

# Summary stats
print(f"\n{'='*100}")
print(f"  REDRAFT ANALYSIS")
print(f"{'='*100}")

# How would the model's top 5 have done vs actual top 5?
model_top5 = model_order[:5]
actual_top5 = actual_order[:5]

print(f"\n  MODEL'S TOP 5 PICKS:")
for i, p in enumerate(model_top5):
    print(f"    #{i+1}: {p['name']:25s} → Actually T{p['actual_tier']} ({TIER_LABELS[p['actual_tier']]}), was pick #{p['actual_pick']}")

print(f"\n  ACTUAL TOP 5 PICKS:")
for i, p in enumerate(actual_top5):
    print(f"    #{i+1}: {p['name']:25s} → Actually T{p['actual_tier']} ({TIER_LABELS[p['actual_tier']]})")

# How would model's top 14 (lottery) have done?
model_lottery = model_order[:14]
actual_lottery = actual_order[:14]

model_lottery_stars = sum(1 for p in model_lottery if p["actual_tier"] in (1, 2))
actual_lottery_stars = sum(1 for p in actual_lottery if p["actual_tier"] in (1, 2))
model_lottery_busts = sum(1 for p in model_lottery if p["actual_tier"] in (4, 5))
actual_lottery_busts = sum(1 for p in actual_lottery if p["actual_tier"] in (4, 5))
model_lottery_contribs = sum(1 for p in model_lottery if p["actual_tier"] in (1, 2, 3))
actual_lottery_contribs = sum(1 for p in actual_lottery if p["actual_tier"] in (1, 2, 3))

print(f"\n  LOTTERY (TOP 14) COMPARISON:")
print(f"    {'':30s} {'Model Draft':>12} {'Actual Draft':>13}")
print(f"    {'Stars (T1+T2):':<30s} {model_lottery_stars:>10}   {actual_lottery_stars:>10}")
print(f"    {'Contributors (T1-T3):':<30s} {model_lottery_contribs:>10}   {actual_lottery_contribs:>10}")
print(f"    {'Busts (T4+T5):':<30s} {model_lottery_busts:>10}   {actual_lottery_busts:>10}")

# Biggest steals (model ranked much higher than actual pick, and player was good)
print(f"\n  BIGGEST MODEL STEALS (ranked higher than drafted, actually good):")
steals = [p for p in model_order if p["actual_tier"] in (1, 2, 3)]
steals.sort(key=lambda x: x["actual_pick"] - model_order.index(x), reverse=True)
for p in steals[:5]:
    model_rank = model_order.index(p) + 1
    print(f"    {p['name']:25s} Model #{model_rank}, Actual #{p['actual_pick']}, Outcome: T{p['actual_tier']}")

# Biggest whiffs (model ranked high but player busted)
print(f"\n  BIGGEST MODEL WHIFFS (ranked high, actually busted):")
whiffs = [(i+1, p) for i, p in enumerate(model_order) if p["actual_tier"] in (4, 5)]
for rank, p in whiffs[:5]:
    print(f"    {p['name']:25s} Model #{rank}, Actual #{p['actual_pick']}, Outcome: T{p['actual_tier']} ({TIER_LABELS[p['actual_tier']]})")

# Stars the model missed (ranked low but actually stars)
print(f"\n  STARS THE MODEL MISSED (ranked low, actually star):")
missed = [(i+1, p) for i, p in enumerate(model_order) if p["actual_tier"] in (1, 2) and i >= 14]
for rank, p in missed:
    print(f"    {p['name']:25s} Model #{rank}, Actual #{p['actual_pick']}, Outcome: T{p['actual_tier']} ({TIER_LABELS[p['actual_tier']]})")

print(f"\n  ** = star correctly identified   !! = false star   xx = missed star")
