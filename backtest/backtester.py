"""Backtest the similarity engine against known draft outcomes.

Leave-one-year-out: for each draft year 2014-2020, train on other years,
predict tier from top-5 matches, compare to actual tier.
Runs with both original and data-driven weights.
"""
import sys
import os
import json
from collections import Counter, defaultdict

# Fix Windows console encoding for player names with accents
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, FEATURE_IMPORTANCE_PATH, PROCESSED_DIR, TIER_LABELS
from app.similarity import calculate_similarity, find_top_matches

TEST_YEARS = list(range(2009, 2020))  # 2009-2019 (clean dataset, verified college stats)


def load_data():
    with open(PLAYER_DB_PATH) as f:
        player_db = json.load(f)

    # Load positional averages
    pos_avgs_path = os.path.join(PROCESSED_DIR, "positional_avgs.json")
    with open(pos_avgs_path) as f:
        pos_avgs = json.load(f)

    # Load data-driven weights if available
    dd_weights = None
    if os.path.exists(FEATURE_IMPORTANCE_PATH):
        with open(FEATURE_IMPORTANCE_PATH) as f:
            fi = json.load(f)
            dd_weights = fi.get("suggested_weights")

    return player_db, pos_avgs, dd_weights


def player_to_prospect(player):
    """Convert a player_db entry to a prospect dict for the similarity engine.

    Includes advanced stats for V2 engine (bpm, obpm, fta, etc.)
    """
    s = player["stats"]
    prospect = {
        "name": player["name"],
        "pos": player["pos"],
        "h": player["h"],
        "w": player["w"],
        "ws": player.get("ws", player["h"] + 4),
        "age": player.get("age", 22),
        "level": player["level"],
        "ath": player.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"],
        "fg": s["fg"], "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
    }
    # Advanced stats (V2) - only if present
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg",
                "stops", "ts_per", "adjoe", "adrtg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect


def predict_tier(matches):
    """Predict tier from top-5 matches using weighted average."""
    if not matches:
        return 5
    total_weight = 0
    weighted_tier = 0
    for m in matches:
        score = m["similarity"]["score"]
        tier = m["player"]["tier"]
        weighted_tier += score * tier
        total_weight += score
    if total_weight == 0:
        return 5
    avg = weighted_tier / total_weight
    return int(round(avg))


def run_backtest(player_db, pos_avgs, weights_override=None, label="", use_v2=True, use_v3=False):
    """Run leave-one-year-out backtest."""
    print(f"\n{'=' * 60}")
    print(f"BACKTEST: {label}")
    print(f"{'=' * 60}")

    all_predictions = []
    year_results = {}

    for test_year in TEST_YEARS:
        # Split: train on other years, test on this year
        train_db = [p for p in player_db if p.get("draft_year") != test_year]
        test_players = [p for p in player_db
                        if p.get("draft_year") == test_year
                        and p.get("has_college_stats")
                        and p.get("draft_pick", 61) <= 60
                        and p.get("nba_ws") is not None
                        and (p.get("stats", {}).get("gp", 30) or 30) >= 25
                        and (p.get("stats", {}).get("mpg", 30) or 30) >= 20]

        if not test_players:
            continue

        correct = 0
        within_1 = 0
        predictions = []

        for tp in test_players:
            prospect = player_to_prospect(tp)
            matches = find_top_matches(prospect, train_db, pos_avgs, weights_override, top_n=5, use_v2=use_v2, use_v3=use_v3)
            predicted = predict_tier(matches)
            actual = tp["tier"]
            star_sigs = matches[0]["similarity"].get("star_signals", 0) if matches else 0

            pred_entry = {
                "name": tp["name"],
                "year": test_year,
                "pick": tp.get("draft_pick", "?"),
                "actual_tier": actual,
                "predicted_tier": predicted,
                "war": tp.get("nba_ws", 0) or 0,
                "star_signals": star_sigs,
                "correct": predicted == actual,
                "within_1": abs(predicted - actual) <= 1,
                "error": predicted - actual,
                "top_match": matches[0]["player"]["name"] if matches else "None",
                "top_score": matches[0]["similarity"]["score"] if matches else 0,
            }
            predictions.append(pred_entry)
            all_predictions.append(pred_entry)

            if predicted == actual:
                correct += 1
            if abs(predicted - actual) <= 1:
                within_1 += 1

        n = len(predictions)
        year_results[test_year] = {
            "n": n,
            "accuracy": correct / n if n > 0 else 0,
            "within_1": within_1 / n if n > 0 else 0,
        }
        print(f"  {test_year}: {n} players, exact={correct}/{n} ({correct/n*100:.0f}%), "
              f"within-1={within_1}/{n} ({within_1/n*100:.0f}%)")

    # Overall metrics
    n_total = len(all_predictions)
    if n_total == 0:
        print("  No testable players found!")
        return {}

    exact_total = sum(1 for p in all_predictions if p["correct"])
    within1_total = sum(1 for p in all_predictions if p["within_1"])
    errors = [p["error"] for p in all_predictions]
    rmse = np.sqrt(np.mean([e**2 for e in errors]))

    # Tier-specific metrics
    actual_stars = [p for p in all_predictions if p["actual_tier"] <= 2]
    actual_busts = [p for p in all_predictions if p["actual_tier"] == 5]
    detected_stars = sum(1 for p in actual_stars if p["predicted_tier"] <= 2)
    detected_busts = sum(1 for p in actual_busts if p["predicted_tier"] >= 4)

    print(f"\n  OVERALL ({n_total} players):")
    print(f"    Exact accuracy: {exact_total}/{n_total} ({exact_total/n_total*100:.1f}%)")
    print(f"    Within-1 accuracy: {within1_total}/{n_total} ({within1_total/n_total*100:.1f}%)")
    print(f"    RMSE: {rmse:.2f}")
    if actual_stars:
        print(f"    Star detection: {detected_stars}/{len(actual_stars)} ({detected_stars/len(actual_stars)*100:.0f}%)")
    if actual_busts:
        print(f"    Bust detection: {detected_busts}/{len(actual_busts)} ({detected_busts/len(actual_busts)*100:.0f}%)")

    # Confusion matrix
    print(f"\n  CONFUSION MATRIX (predicted vs actual):")
    print(f"  {'':>12s}", end="")
    for t in range(1, 6):
        print(f" Pred={t:d}", end="")
    print()
    for actual_t in range(1, 6):
        row_players = [p for p in all_predictions if p["actual_tier"] == actual_t]
        print(f"  Actual={actual_t:d}  ", end="")
        for pred_t in range(1, 6):
            count = sum(1 for p in row_players if p["predicted_tier"] == pred_t)
            print(f" {count:6d}", end="")
        print(f"  (n={len(row_players)})")

    # Biggest misses and best calls
    sorted_by_error = sorted(all_predictions, key=lambda p: abs(p["error"]), reverse=True)
    print(f"\n  BIGGEST MISSES:")
    for p in sorted_by_error[:5]:
        print(f"    {p['name']:25s} (#{p['pick']:2}) yr={p['year']} "
              f"actual={p['actual_tier']} pred={p['predicted_tier']} "
              f"WAR={p['war']:.1f} comp={p['top_match']}")

    best_calls = [p for p in all_predictions if p["correct"] and p["actual_tier"] <= 2]
    if best_calls:
        print(f"\n  BEST CALLS (correctly ID'd stars):")
        for p in sorted(best_calls, key=lambda x: x["war"], reverse=True)[:5]:
            print(f"    {p['name']:25s} (#{p['pick']:2}) yr={p['year']} "
                  f"tier={p['actual_tier']} WAR={p['war']:.1f} comp={p['top_match']} ({p['top_score']:.0f}%)")

    return {
        "accuracy": exact_total / n_total,
        "within_1": within1_total / n_total,
        "rmse": rmse,
        "star_detection": detected_stars / len(actual_stars) if actual_stars else 0,
        "bust_detection": detected_busts / len(actual_busts) if actual_busts else 0,
        "n_tested": n_total,
        "predictions": all_predictions,
    }


def main():
    player_db, pos_avgs, dd_weights = load_data()

    # Filter to clean dataset (2009-2019 with college stats)
    clean_db = [p for p in player_db
                if p.get("has_college_stats")
                and 2009 <= (p.get("draft_year") or 0) <= 2019]
    print(f"Clean dataset: {len(clean_db)} players (2009-2019 with college stats)")

    # Run with V1 (original weights)
    v1_results = run_backtest(clean_db, pos_avgs, label="V1 (ORIGINAL WEIGHTS)", use_v2=False)

    # Run with V2 (old data-driven weights)
    v2_results = run_backtest(clean_db, pos_avgs, label="V2 (OLD DATA-DRIVEN)", use_v2=True)

    # Run with V3 (retuned on clean dataset)
    v3_results = run_backtest(clean_db, pos_avgs, label="V3 (RETUNED ON CLEAN DATA)", use_v2=False, use_v3=True)

    # Compare
    print(f"\n{'=' * 60}")
    print("V1 vs V2 vs V3 COMPARISON")
    print(f"{'=' * 60}")
    print(f"  {'Metric':>20s} {'V1':>10s} {'V2':>10s} {'V3':>10s} {'V2-V1':>8s} {'V3-V2':>8s}")
    print(f"  {'-' * 70}")
    for metric in ["accuracy", "within_1", "rmse", "star_detection", "bust_detection"]:
        v1 = v1_results.get(metric, 0)
        v2 = v2_results.get(metric, 0)
        v3 = v3_results.get(metric, 0)
        d12 = v2 - v1
        d23 = v3 - v2
        s12 = "+" if d12 > 0 else ""
        s23 = "+" if d23 > 0 else ""
        print(f"  {metric:>20s} {v1:10.3f} {v2:10.3f} {v3:10.3f} {s12}{d12:7.3f} {s23}{d23:7.3f}")

    # Save results
    output = {
        "v1": {k: v for k, v in v1_results.items() if k != "predictions"},
        "v2": {k: v for k, v in v2_results.items() if k != "predictions"},
        "v3": {k: v for k, v in v3_results.items() if k != "predictions"},
    }
    output_path = os.path.join(PROCESSED_DIR, "backtest_results.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
