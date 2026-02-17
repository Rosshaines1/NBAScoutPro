"""Audit: Check predict_tier() vs comp-based prediction for all backtest players.

Key question: Is predict_tier() actually better than comp averaging?
If so, the backtester should use it. If not, we need to fix it.
"""
import json, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS
from app.similarity import find_top_matches, predict_tier, count_star_signals

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)
pos_avgs_path = os.path.join(PROCESSED_DIR, "positional_avgs.json")
with open(pos_avgs_path) as f:
    pos_avgs = json.load(f)

TEST_YEARS = list(range(2009, 2021))

def player_to_prospect(player):
    s = player["stats"]
    prospect = {
        "name": player["name"], "pos": player["pos"],
        "h": player["h"], "w": player["w"],
        "ws": player.get("ws", player["h"] + 4),
        "age": player.get("age", 22), "level": player["level"],
        "ath": player.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"],
        "fg": s["fg"], "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect

# ---- Run both systems on all test players ----
comp_results = []
tier_results = []
both_results = []

for test_year in TEST_YEARS:
    train_db = [p for p in db if p.get("draft_year") != test_year]
    test_players = [p for p in db
                    if p.get("draft_year") == test_year
                    and p.get("has_college_stats")
                    and p.get("draft_pick", 61) <= 60
                    and p.get("nba_ws") is not None]

    for tp in test_players:
        prospect = player_to_prospect(tp)
        actual = tp["tier"]

        # System 1: Comp-based (current backtester)
        matches = find_top_matches(prospect, train_db, pos_avgs, top_n=5, use_v2=True)
        if matches:
            total_w = sum(m["similarity"]["score"] for m in matches)
            comp_pred = round(sum(m["similarity"]["score"] * m["player"]["tier"] for m in matches) / total_w) if total_w else 5
        else:
            comp_pred = 5

        # System 2: predict_tier()
        tier_pred_result = predict_tier(prospect, pos_avgs)
        tier_pred = tier_pred_result["tier"]

        sig_count, sig_tags = count_star_signals(prospect)

        both_results.append({
            "name": tp["name"], "year": test_year, "pick": tp.get("draft_pick", 99),
            "actual": actual, "comp_pred": comp_pred, "tier_pred": tier_pred,
            "tier_score": tier_pred_result["score"],
            "ws": tp.get("nba_ws", 0) or 0,
            "star_sigs": sig_count,
            "reasons": tier_pred_result["reasons"],
            "has_advanced": tier_pred_result["has_advanced_stats"],
        })

# ---- Compare systems ----
print("=" * 80)
print("  SYSTEM COMPARISON: Comp-based vs predict_tier()")
print("=" * 80)

comp_exact = sum(1 for r in both_results if r["comp_pred"] == r["actual"])
tier_exact = sum(1 for r in both_results if r["tier_pred"] == r["actual"])
comp_w1 = sum(1 for r in both_results if abs(r["comp_pred"] - r["actual"]) <= 1)
tier_w1 = sum(1 for r in both_results if abs(r["tier_pred"] - r["actual"]) <= 1)
n = len(both_results)

print(f"\n  Total players tested: {n}")
print(f"  {'Metric':>25s} {'Comp-based':>12s} {'predict_tier':>12s}")
print(f"  {'-' * 50}")
print(f"  {'Exact accuracy':>25s} {comp_exact/n*100:11.1f}% {tier_exact/n*100:11.1f}%")
print(f"  {'Within-1 accuracy':>25s} {comp_w1/n*100:11.1f}% {tier_w1/n*100:11.1f}%")

# Star detection
stars = [r for r in both_results if r["actual"] <= 2]
comp_star_det = sum(1 for r in stars if r["comp_pred"] <= 2)
tier_star_det = sum(1 for r in stars if r["tier_pred"] <= 2)
print(f"  {'Star detection (T1-T2)':>25s} {comp_star_det}/{len(stars)} ({comp_star_det/len(stars)*100:.0f}%) {tier_star_det}/{len(stars)} ({tier_star_det/len(stars)*100:.0f}%)")

busts = [r for r in both_results if r["actual"] == 5]
comp_bust_det = sum(1 for r in busts if r["comp_pred"] >= 4)
tier_bust_det = sum(1 for r in busts if r["tier_pred"] >= 4)
print(f"  {'Bust detection (T4-T5)':>25s} {comp_bust_det}/{len(busts)} ({comp_bust_det/len(busts)*100:.0f}%) {tier_bust_det}/{len(busts)} ({tier_bust_det/len(busts)*100:.0f}%)")

# ---- Confusion matrix for predict_tier ----
print(f"\n  predict_tier() CONFUSION MATRIX:")
print(f"  {'':>12s}", end="")
for t in range(1, 6):
    print(f" Pred={t:d}", end="")
print()
for actual_t in range(1, 6):
    row = [r for r in both_results if r["actual"] == actual_t]
    print(f"  Actual={actual_t:d}  ", end="")
    for pred_t in range(1, 6):
        count = sum(1 for r in row if r["tier_pred"] == pred_t)
        print(f" {count:6d}", end="")
    print(f"  (n={len(row)})")

# ---- T1 superstar deep dive ----
print(f"\n{'=' * 80}")
print("  T1 SUPERSTARS - DETAILED BREAKDOWN")
print("=" * 80)
t1 = sorted([r for r in both_results if r["actual"] == 1], key=lambda x: -x["ws"])
for r in t1:
    print(f"\n  {r['name']:25s} #{r['pick']:2d} ({r['year']}) WS={r['ws']:.0f}")
    print(f"    Comp pred: T{r['comp_pred']} | Tier pred: T{r['tier_pred']} (score={r['tier_score']:.0f})")
    print(f"    Star signals: {r['star_sigs']} | Advanced: {r['has_advanced']}")
    print(f"    Reasons: {r['reasons']}")

# ---- T2 All-Stars ----
print(f"\n{'=' * 80}")
print("  T2 ALL-STARS - DETAILED BREAKDOWN")
print("=" * 80)
t2 = sorted([r for r in both_results if r["actual"] == 2], key=lambda x: -x["ws"])
for r in t2[:15]:
    print(f"\n  {r['name']:25s} #{r['pick']:2d} ({r['year']}) WS={r['ws']:.0f}")
    print(f"    Comp pred: T{r['comp_pred']} | Tier pred: T{r['tier_pred']} (score={r['tier_score']:.0f})")
    print(f"    Star signals: {r['star_sigs']} | Advanced: {r['has_advanced']}")
    print(f"    Reasons: {r['reasons']}")

# ---- Biggest predict_tier misses (both directions) ----
print(f"\n{'=' * 80}")
print("  WORST predict_tier() MISSES")
print("=" * 80)
worst = sorted(both_results, key=lambda r: abs(r["tier_pred"] - r["actual"]), reverse=True)
print("\n  Predicted TOO HIGH (thought they'd be good, they busted):")
too_high = [r for r in worst if r["tier_pred"] < r["actual"]][:10]
for r in too_high:
    print(f"    {r['name']:25s} pred=T{r['tier_pred']} actual=T{r['actual']} "
          f"WS={r['ws']:.0f} score={r['tier_score']:.0f} sigs={r['star_sigs']} adv={r['has_advanced']}")

print("\n  Predicted TOO LOW (missed the star):")
too_low = [r for r in worst if r["tier_pred"] > r["actual"]][:10]
for r in too_low:
    print(f"    {r['name']:25s} pred=T{r['tier_pred']} actual=T{r['actual']} "
          f"WS={r['ws']:.0f} score={r['tier_score']:.0f} sigs={r['star_sigs']} adv={r['has_advanced']}")
