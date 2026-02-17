"""Retune predict_tier thresholds on clean 524-player dataset.

For each stat:
  - Find optimal thresholds separating T1+T2 from T4+T5
  - Recalibrate point values proportional to separation power
  - Verify broken-shot detector, chucker filter
  - Test class year as signal
  - Recalibrate tier score boundaries
"""
import json
import os
import sys
import math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, LEVEL_MODIFIERS
from app.similarity import predict_tier, classify_archetype


def load_clean_db():
    with open(PLAYER_DB_PATH) as f:
        db = json.load(f)
    return [
        p for p in db
        if p.get("has_college_stats")
        and 2009 <= p.get("draft_year", 0) <= 2019
        and p.get("nba_ws") is not None
    ]


def get_stat(player, stat):
    s = player.get("stats", {})
    if stat == "age":
        return player.get("age", 4) or 4
    return s.get(stat, 0) or 0


def player_to_prospect(player):
    s = player["stats"]
    prospect = {
        "name": player["name"],
        "pos": player["pos"],
        "h": player["h"],
        "w": player["w"],
        "ws": player.get("ws", player["h"] + 4),
        "age": player.get("age", 4),
        "level": player["level"],
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"],
        "fg": s["fg"], "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
        "draft_pick": player.get("draft_pick", 0),
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect


def find_optimal_threshold(players, stat, higher_is_better=True):
    """Find threshold that best separates stars (T1+T2) from busts (T4+T5).

    Returns (threshold, precision, recall, f1) for the best cutpoint.
    """
    values = []
    for p in players:
        val = get_stat(p, stat)
        if val == 0:
            continue
        is_star = p["tier"] <= 2
        values.append((val, is_star))

    if len(values) < 20:
        return None, 0, 0, 0

    values.sort(key=lambda x: x[0])
    all_vals = [v[0] for v in values]

    # Try percentile-based thresholds
    best_f1 = 0
    best_thresh = 0
    best_prec = 0
    best_rec = 0

    for pct in range(50, 96):
        idx = int(len(all_vals) * pct / 100)
        thresh = all_vals[min(idx, len(all_vals) - 1)]

        if higher_is_better:
            predicted_star = [v for v in values if v[0] >= thresh]
            predicted_not = [v for v in values if v[0] < thresh]
        else:
            predicted_star = [v for v in values if v[0] <= thresh]
            predicted_not = [v for v in values if v[0] > thresh]

        tp = sum(1 for v in predicted_star if v[1])
        fp = sum(1 for v in predicted_star if not v[1])
        fn = sum(1 for v in predicted_not if v[1])

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh
            best_prec = precision
            best_rec = recall

    return best_thresh, best_prec, best_rec, best_f1


def test_broken_shot_detector(players):
    """Verify: FT% < X with 3P% > Y — does it flag real busts?"""
    print("\n" + "=" * 60)
    print("BROKEN SHOT DETECTOR TEST")
    print("  Looking for: low FT% shooters (bad touch) — bust signal?")
    print("=" * 60)

    for ft_thresh in [60, 65, 68]:
        flagged = [p for p in players if get_stat(p, "ft") > 0 and get_stat(p, "ft") < ft_thresh]
        if not flagged:
            continue
        bust_rate = sum(1 for p in flagged if p["tier"] >= 4) / len(flagged)
        star_rate = sum(1 for p in flagged if p["tier"] <= 2) / len(flagged)
        print(f"\n  FT% < {ft_thresh}: {len(flagged)} players")
        print(f"    Bust rate (T4+T5): {bust_rate:.1%}")
        print(f"    Star rate (T1+T2): {star_rate:.1%}")
        # Show names
        for p in sorted(flagged, key=lambda x: x.get("nba_ws", 0), reverse=True)[:5]:
            print(f"      {p['name']:25s} T{p['tier']} FT={get_stat(p, 'ft'):.0f}% WS={p.get('nba_ws', 0):.1f}")


def test_chucker_filter(players):
    """Verify: high PPG + low eFG% — does it predict busts?"""
    print("\n" + "=" * 60)
    print("CHUCKER FILTER TEST")
    print("  Looking for: high volume + bad efficiency = bust signal?")
    print("=" * 60)

    for ppg_thresh, fg_thresh in [(16, 42), (18, 44), (14, 40)]:
        flagged = [p for p in players
                   if get_stat(p, "ppg") >= ppg_thresh and get_stat(p, "fg") < fg_thresh
                   and get_stat(p, "fg") > 0]
        if not flagged:
            print(f"\n  PPG >= {ppg_thresh} + eFG < {fg_thresh}: 0 players")
            continue
        bust_rate = sum(1 for p in flagged if p["tier"] >= 4) / len(flagged)
        print(f"\n  PPG >= {ppg_thresh} + eFG < {fg_thresh}: {len(flagged)} players")
        print(f"    Bust rate (T4+T5): {bust_rate:.1%}")
        for p in flagged[:8]:
            print(f"      {p['name']:25s} T{p['tier']} PPG={get_stat(p, 'ppg'):.1f} "
                  f"eFG={get_stat(p, 'fg'):.1f}% WS={p.get('nba_ws', 0):.1f}")


def test_class_year_signal(players):
    """Test: freshmen declaring early = strong signal?"""
    print("\n" + "=" * 60)
    print("CLASS YEAR SIGNAL TEST")
    print("  Hypothesis: freshmen declaring early = stronger NBA outcome")
    print("=" * 60)

    by_year = defaultdict(list)
    for p in players:
        yr = p.get("age", 0) or 0
        if yr > 0:
            by_year[yr].append(p)

    yr_labels = {1: "Fr", 2: "So", 3: "Jr", 4: "Sr"}
    for yr in sorted(by_year):
        group = by_year[yr]
        avg_ws = sum(p.get("nba_ws", 0) or 0 for p in group) / len(group)
        star_rate = sum(1 for p in group if p["tier"] <= 2) / len(group)
        bust_rate = sum(1 for p in group if p["tier"] >= 4) / len(group)
        print(f"\n  {yr_labels.get(yr, f'Yr{yr}')} (n={len(group)}):")
        print(f"    Avg WS: {avg_ws:.1f}")
        print(f"    Star rate (T1+T2): {star_rate:.1%}")
        print(f"    Bust rate (T4+T5): {bust_rate:.1%}")
        tier_dist = defaultdict(int)
        for p in group:
            tier_dist[p["tier"]] += 1
        print(f"    Tier dist: {dict(sorted(tier_dist.items()))}")


def test_current_predict_tier(players):
    """Run current predict_tier on all players, measure accuracy."""
    print("\n" + "=" * 60)
    print("CURRENT predict_tier ACCURACY (before retuning)")
    print("=" * 60)

    correct = 0
    within_1 = 0
    scores_by_tier = defaultdict(list)
    predictions = []

    for p in players:
        prospect = player_to_prospect(p)
        result = predict_tier(prospect)
        pred = result["tier"]
        actual = p["tier"]
        score = result["score"]

        predictions.append((p["name"], actual, pred, score))
        scores_by_tier[actual].append(score)

        if pred == actual:
            correct += 1
        if abs(pred - actual) <= 1:
            within_1 += 1

    n = len(predictions)
    print(f"\n  Exact accuracy: {correct}/{n} ({correct/n*100:.1f}%)")
    print(f"  Within-1: {within_1}/{n} ({within_1/n*100:.1f}%)")

    print(f"\n  Score distribution by actual tier:")
    for t in sorted(scores_by_tier):
        vals = scores_by_tier[t]
        avg = sum(vals) / len(vals)
        mn = min(vals)
        mx = max(vals)
        print(f"    T{t} (n={len(vals):3d}): avg={avg:5.1f}  min={mn:5.1f}  max={mx:5.1f}")

    # Find optimal tier boundaries from actual score distributions
    print(f"\n  SUGGESTED TIER BOUNDARIES:")
    all_scores = [(p[1], p[3]) for p in predictions]  # (actual_tier, score)

    for boundary_name, tier_above, tier_below in [
        ("T1/T2", 1, 2), ("T2/T3", 2, 3), ("T3/T4", 3, 4), ("T4/T5", 4, 5)
    ]:
        above_scores = [s for t, s in all_scores if t <= tier_above]
        below_scores = [s for t, s in all_scores if t >= tier_below]
        if above_scores and below_scores:
            # Find midpoint between average scores
            avg_above = sum(above_scores) / len(above_scores)
            avg_below = sum(below_scores) / len(below_scores)
            midpoint = (avg_above + avg_below) / 2
            print(f"    {boundary_name}: avg_above={avg_above:.1f}, avg_below={avg_below:.1f}, "
                  f"midpoint={midpoint:.1f}")

    return predictions


def test_archetype_distribution(players):
    """Check archetype classifier distribution on clean data."""
    print("\n" + "=" * 60)
    print("ARCHETYPE DISTRIBUTION (on clean 524-player dataset)")
    print("=" * 60)

    arch_counts = defaultdict(int)
    arch_tiers = defaultdict(lambda: defaultdict(int))
    arch_ws = defaultdict(list)

    for p in players:
        arch, score, secondary = classify_archetype(p)
        arch_counts[arch] += 1
        arch_tiers[arch][p["tier"]] += 1
        arch_ws[arch].append(p.get("nba_ws", 0) or 0)

    for arch in sorted(arch_counts, key=lambda x: -arch_counts[x]):
        n = arch_counts[arch]
        avg_ws = sum(arch_ws[arch]) / n
        tiers = dict(sorted(arch_tiers[arch].items()))
        star_count = arch_tiers[arch].get(1, 0) + arch_tiers[arch].get(2, 0)
        print(f"\n  {arch:20s}: n={n:3d} ({n/len(players)*100:.0f}%)  avg_WS={avg_ws:.1f}")
        print(f"    Tier dist: {tiers}")
        print(f"    Star rate: {star_count/n*100:.0f}%  ({star_count} stars)")


def main():
    players = load_clean_db()

    # 1. Find optimal thresholds for star signal stats
    print("=" * 60)
    print("OPTIMAL STAR SIGNAL THRESHOLDS")
    print("  Finding best cutpoints to separate T1+T2 from T4+T5")
    print("=" * 60)

    star_stats = [
        ("bpm", True), ("obpm", True), ("dbpm", True),
        ("fta", True), ("spg", True), ("stl_per", True),
        ("usg", True), ("ft", True), ("ppg", True),
        ("apg", True), ("rpg", True),
    ]

    thresholds = {}
    print(f"\n{'Stat':>10s} {'Threshold':>10s} {'Precision':>10s} {'Recall':>8s} {'F1':>6s}")
    print("-" * 50)

    for stat, higher in star_stats:
        thresh, prec, rec, f1 = find_optimal_threshold(players, stat, higher)
        if thresh is not None:
            thresholds[stat] = {
                "threshold": round(thresh, 1),
                "precision": round(prec, 3),
                "recall": round(rec, 3),
                "f1": round(f1, 3),
            }
            print(f"{stat:>10s} {thresh:>10.1f} {prec:>10.3f} {rec:>8.3f} {f1:>6.3f}")

    # 2. Test specific detectors
    test_broken_shot_detector(players)
    test_chucker_filter(players)
    test_class_year_signal(players)

    # 3. Test current predict_tier accuracy
    predictions = test_current_predict_tier(players)

    # 4. Check archetype distribution
    test_archetype_distribution(players)

    # Save results
    output = {
        "thresholds": thresholds,
        "n_players": len(players),
    }
    output_path = os.path.join(os.path.dirname(__file__), "star_signal_results.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
