"""Compute fresh stat-to-outcome correlations on clean 524-player dataset.

Outputs:
  - Pearson r of each stat vs NBA Win Shares
  - Mean stat values per tier (T1-T5) with separation gaps
  - Star/bust separators (T1+T2 vs T4+T5 mean differences)
  - Effect sizes (Cohen's d) for each stat
"""
import json
import os
import sys
import math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, LEVEL_MODIFIERS

STATS_TO_ANALYZE = [
    # Current stats
    "ppg", "rpg", "apg", "spg", "bpg", "fg", "threeP", "ft",
    "mpg", "bpm", "obpm", "dbpm", "fta", "stl_per", "usg",
    "age", "tpg",
    # NEW: stats we have in CSV but don't use yet
    "gp",           # games played
    "tpa",          # 3-point attempts per game
    "tpm",          # 3-point makes per game
    "ftm",          # free throws made per game
    "ftr",          # FT rate (FTA/FGA)
    "oreb",         # offensive rebounds per game
    "dreb",         # defensive rebounds per game
    "ts_per",       # true shooting %
    "orb_per",      # offensive rebound %
    "drb_per",      # defensive rebound %
    "ast_per",      # assist %
    "to_per",       # turnover %
    "blk_per",      # block %
    "ortg",         # offensive rating
    "porpag",       # points over replacement per game
    "adjoe",        # adjusted offensive efficiency
    "rim_pct",      # rim finishing %
    "rim_att",      # rim attempts per game
    "mid_pct",      # mid-range %
    "dunk_pct",     # dunk percentage of rim attempts
]


def load_clean_db():
    """Load player_db, filter to 2009-2019 drafts with college stats."""
    with open(PLAYER_DB_PATH) as f:
        db = json.load(f)
    clean = [
        p for p in db
        if p.get("has_college_stats")
        and 2010 <= (p.get("draft_year") or 0) <= 2021
        and p.get("nba_ws") is not None
        and p.get("tier", 5) != 6
    ]
    print(f"Loaded {len(clean)} players (2010-2021 with college stats + WS)")
    return clean


def get_stat(player, stat):
    """Get a stat value from player dict (checking stats sub-dict too)."""
    s = player.get("stats", {})
    if stat == "age":
        return player.get("age", 4) or 4  # class year 1-4
    if stat == "ato":
        apg = s.get("apg", 0) or 0
        tpg = s.get("tpg", 0) or 0
        return apg / tpg if tpg > 0 else apg
    if stat == "rim_pct":
        made = s.get("rimmade", 0) or 0
        att = s.get("rim_att", 0) or 0
        return (made / att * 100) if att > 0 else 0
    if stat == "mid_pct":
        # Not extracted — skip
        return 0
    if stat == "dunk_pct":
        # Not extracted — skip
        return 0
    val = s.get(stat, 0) or 0
    return val


def pearson_r(xs, ys):
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0
    return cov / denom


def cohens_d(group1, group2):
    """Compute Cohen's d effect size between two groups."""
    if len(group1) < 2 or len(group2) < 2:
        return 0.0
    m1 = sum(group1) / len(group1)
    m2 = sum(group2) / len(group2)
    var1 = sum((x - m1) ** 2 for x in group1) / (len(group1) - 1)
    var2 = sum((x - m2) ** 2 for x in group2) / (len(group2) - 1)
    pooled_sd = math.sqrt((var1 + var2) / 2)
    if pooled_sd == 0:
        return 0.0
    return (m1 - m2) / pooled_sd


def main():
    players = load_clean_db()

    # Tier distribution
    tier_counts = defaultdict(int)
    for p in players:
        tier_counts[p["tier"]] += 1
    print(f"\nTier distribution:")
    for t in sorted(tier_counts):
        print(f"  T{t}: {tier_counts[t]}")

    # Group players by tier
    by_tier = defaultdict(list)
    for p in players:
        by_tier[p["tier"]].append(p)

    stars = by_tier[1] + by_tier[2]  # T1+T2
    busts = by_tier[4] + by_tier[5]  # T4+T5

    # Compute correlations
    results = {}
    ws_values = [p.get("nba_ws", 0) or 0 for p in players]

    print(f"\n{'Stat':>10s} {'r':>7s} {'|r|':>6s} {'T1 mean':>9s} {'T2 mean':>9s} "
          f"{'T3 mean':>9s} {'T4 mean':>9s} {'T5 mean':>9s} {'Star-Bust':>10s} {'Cohen d':>8s} {'N_valid':>8s}")
    print("-" * 105)

    for stat in STATS_TO_ANALYZE:
        # Get stat values for all players
        stat_values = [get_stat(p, stat) for p in players]

        # Filter to players with non-zero values for this stat
        valid = [(sv, ws) for sv, ws in zip(stat_values, ws_values) if sv != 0]
        n_valid = len(valid)

        if n_valid < 10:
            print(f"  {stat:>10s}: only {n_valid} valid values, skipping")
            continue

        valid_stats = [v[0] for v in valid]
        valid_ws = [v[1] for v in valid]

        r = pearson_r(valid_stats, valid_ws)

        # Tier means
        tier_means = {}
        for t in range(1, 6):
            tier_vals = [get_stat(p, stat) for p in by_tier[t] if get_stat(p, stat) != 0]
            tier_means[t] = sum(tier_vals) / len(tier_vals) if tier_vals else 0

        # Star vs bust separation
        star_vals = [get_stat(p, stat) for p in stars if get_stat(p, stat) != 0]
        bust_vals = [get_stat(p, stat) for p in busts if get_stat(p, stat) != 0]

        star_mean = sum(star_vals) / len(star_vals) if star_vals else 0
        bust_mean = sum(bust_vals) / len(bust_vals) if bust_vals else 0
        separation = star_mean - bust_mean

        d = cohens_d(star_vals, bust_vals)

        results[stat] = {
            "r": round(r, 4),
            "abs_r": round(abs(r), 4),
            "tier_means": {str(t): round(v, 2) for t, v in tier_means.items()},
            "star_mean": round(star_mean, 2),
            "bust_mean": round(bust_mean, 2),
            "separation": round(separation, 2),
            "cohens_d": round(d, 3),
            "n_valid": n_valid,
        }

        print(f"{stat:>10s} {r:>7.4f} {abs(r):>6.4f} "
              f"{tier_means[1]:>9.2f} {tier_means[2]:>9.2f} {tier_means[3]:>9.2f} "
              f"{tier_means[4]:>9.2f} {tier_means[5]:>9.2f} "
              f"{separation:>10.2f} {d:>8.3f} {n_valid:>8d}")

    # Rank by combined predictive power
    print(f"\n{'=' * 60}")
    print("RANKED BY COMBINED PREDICTIVE POWER")
    print(f"  Score = |r| * 0.5 + normalized_separation * 0.5")
    print(f"{'=' * 60}")

    # Normalize separations to 0-1 scale for combining
    max_sep = max(abs(v["separation"]) for v in results.values()) if results else 1
    for stat, data in results.items():
        norm_sep = abs(data["separation"]) / max_sep if max_sep > 0 else 0
        data["combined_score"] = round(data["abs_r"] * 0.5 + norm_sep * 0.5, 4)

    ranked = sorted(results.items(), key=lambda x: x[1]["combined_score"], reverse=True)
    print(f"\n{'Rank':>4s} {'Stat':>10s} {'|r|':>6s} {'Separation':>12s} {'Cohen d':>8s} {'Combined':>9s}")
    print("-" * 55)
    for i, (stat, data) in enumerate(ranked, 1):
        print(f"{i:>4d} {stat:>10s} {data['abs_r']:>6.4f} "
              f"{data['separation']:>12.2f} {data['cohens_d']:>8.3f} {data['combined_score']:>9.4f}")

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "correlation_results.json")
    with open(output_path, "w") as f:
        json.dump({"stats": results, "ranked": [(s, d) for s, d in ranked],
                    "n_players": len(players), "tier_counts": dict(tier_counts)},
                   f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
