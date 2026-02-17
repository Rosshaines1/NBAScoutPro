"""ML-based feature importance ranking for NBA draft prediction.

Uses Random Forest and Gradient Boosting to rank which college stats
best predict career WAR. Compares data-driven weights to the original
hardcoded weights from nbascout.txt.
"""
import sys
import os
import json

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    PLAYER_DB_PATH, PROCESSED_DIR, FEATURE_IMPORTANCE_PATH,
    ORIGINAL_WEIGHTS, LEVEL_MODIFIERS,
)

STAT_FEATURES = ["ppg", "rpg", "apg", "spg", "bpg", "fg", "threeP", "ft", "tpg", "mpg", "bpm"]
PHYSICAL_FEATURES = ["h", "w"]
ALL_FEATURES = STAT_FEATURES + PHYSICAL_FEATURES


def load_data():
    with open(PLAYER_DB_PATH) as f:
        players = json.load(f)

    rows = []
    for p in players:
        if p.get("draft_pick", 61) > 60:
            continue
        row = {
            "name": p["name"],
            "pos": p["pos"],
            "h": p["h"],
            "w": p["w"],
            "level": p["level"],
            "tier": p["tier"],
            "war_total": p["war_total"],
        }
        for stat in STAT_FEATURES:
            row[stat] = p["stats"].get(stat, 0)

        # Encode level as numeric
        row["level_mod"] = LEVEL_MODIFIERS.get(p["level"], 0.7)
        rows.append(row)

    return pd.DataFrame(rows)


def run_feature_importance(df):
    """Run Random Forest and Gradient Boosting to rank features."""
    try:
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("WARNING: scikit-learn not available. Using correlation fallback.")
        return correlation_fallback(df)

    X = df[ALL_FEATURES].fillna(0)
    y = df["war_total"]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Random Forest
    rf = RandomForestRegressor(n_estimators=200, random_state=42, max_depth=8)
    rf.fit(X_scaled, y)
    rf_importance = dict(zip(ALL_FEATURES, rf.feature_importances_))

    # Gradient Boosting
    gb = GradientBoostingRegressor(n_estimators=200, random_state=42, max_depth=4, learning_rate=0.1)
    gb.fit(X_scaled, y)
    gb_importance = dict(zip(ALL_FEATURES, gb.feature_importances_))

    # Average the two
    avg_importance = {}
    for feat in ALL_FEATURES:
        avg_importance[feat] = (rf_importance[feat] + gb_importance[feat]) / 2

    return rf_importance, gb_importance, avg_importance


def correlation_fallback(df):
    """Fallback if sklearn not available: use absolute correlation as importance."""
    from scipy import stats as sp_stats
    importance = {}
    for feat in ALL_FEATURES:
        valid = df[[feat, "war_total"]].dropna()
        if len(valid) < 20:
            importance[feat] = 0
            continue
        r, _ = sp_stats.pearsonr(valid[feat], valid["war_total"])
        importance[feat] = abs(r)
    return importance, importance, importance


def importance_to_weights(avg_importance):
    """Convert raw importance scores to similarity weights (0.5-3.0 scale)."""
    max_imp = max(avg_importance.values()) if avg_importance else 1
    weights = {}
    for feat, imp in avg_importance.items():
        # Normalize to 0-1, then scale to 0.5-3.0
        normalized = imp / max_imp if max_imp > 0 else 0
        weights[feat] = round(0.5 + normalized * 2.5, 2)
    return weights


def validate_level_modifiers(df):
    """Check if conference level actually predicts NBA success."""
    print("\n=== LEVEL MODIFIER VALIDATION ===")
    for level in ["High Major", "Mid Major", "Low Major"]:
        subset = df[df["level"] == level]
        if len(subset) < 5:
            continue
        avg_war = subset["war_total"].mean()
        avg_tier = subset["tier"].mean()
        star_rate = (subset["tier"] <= 2).mean() * 100
        print(f"  {level:12s}: n={len(subset):3d}, avg_WAR={avg_war:5.1f}, "
              f"avg_tier={avg_tier:.1f}, star_rate={star_rate:.1f}%")


def main():
    print("Loading player database...")
    df = load_data()
    print(f"  {len(df)} drafted players loaded")

    print("\nRunning feature importance analysis...")
    rf_imp, gb_imp, avg_imp = run_feature_importance(df)

    # Convert to weights
    suggested_weights = importance_to_weights(avg_imp)

    print("\n=== FEATURE IMPORTANCE RANKING ===")
    print(f"{'Feature':>10s} {'RF':>8s} {'GB':>8s} {'Avg':>8s} {'Weight':>8s} {'Original':>8s}")
    print("-" * 60)
    sorted_feats = sorted(avg_imp.keys(), key=lambda k: avg_imp[k], reverse=True)
    for feat in sorted_feats:
        orig = ORIGINAL_WEIGHTS.get(feat, "N/A")
        orig_str = f"{orig:.1f}" if isinstance(orig, (int, float)) else orig
        print(f"{feat:>10s} {rf_imp[feat]:8.4f} {gb_imp[feat]:8.4f} "
              f"{avg_imp[feat]:8.4f} {suggested_weights[feat]:8.2f} {orig_str:>8s}")

    # Validate level modifiers
    validate_level_modifiers(df)

    # Export
    output = {
        "rf_importance": {k: round(v, 6) for k, v in rf_imp.items()},
        "gb_importance": {k: round(v, 6) for k, v in gb_imp.items()},
        "avg_importance": {k: round(v, 6) for k, v in avg_imp.items()},
        "suggested_weights": suggested_weights,
        "original_weights": ORIGINAL_WEIGHTS,
    }

    with open(FEATURE_IMPORTANCE_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Feature importance saved to {FEATURE_IMPORTANCE_PATH}")


if __name__ == "__main__":
    main()
