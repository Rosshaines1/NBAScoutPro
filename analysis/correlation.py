"""Correlate college stats against career WAR to find predictive features.

Runs Pearson and Spearman correlations overall and per-position.
Outputs a correlation table and heatmap.
"""
import sys
import os
import json

import pandas as pd
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, PROCESSED_DIR


STAT_COLS = ["ppg", "rpg", "apg", "spg", "bpg", "fg", "threeP", "ft", "tpg", "mpg", "bpm"]
PHYSICAL_COLS = ["h", "w"]


def load_players():
    with open(PLAYER_DB_PATH) as f:
        players = json.load(f)

    rows = []
    for p in players:
        row = {
            "name": p["name"],
            "pos": p["pos"],
            "h": p["h"],
            "w": p["w"],
            "level": p["level"],
            "tier": p["tier"],
            "war_total": p["war_total"],
            "draft_pick": p.get("draft_pick", 61),
        }
        for stat in STAT_COLS:
            row[stat] = p["stats"].get(stat, 0)
        rows.append(row)

    return pd.DataFrame(rows)


def compute_correlations(df, features, target="war_total"):
    """Compute Pearson and Spearman correlations for each feature vs target."""
    results = []
    for feat in features:
        valid = df[[feat, target]].dropna()
        if len(valid) < 20:
            continue
        pearson_r, pearson_p = stats.pearsonr(valid[feat], valid[target])
        spearman_r, spearman_p = stats.spearmanr(valid[feat], valid[target])
        results.append({
            "feature": feat,
            "pearson_r": round(pearson_r, 4),
            "pearson_p": round(pearson_p, 6),
            "spearman_r": round(spearman_r, 4),
            "spearman_p": round(spearman_p, 6),
            "abs_pearson": round(abs(pearson_r), 4),
        })
    return pd.DataFrame(results).sort_values("abs_pearson", ascending=False)


def plot_heatmap(corr_overall, corr_by_pos, output_path):
    """Create a heatmap showing correlations by position."""
    features = corr_overall["feature"].tolist()

    # Build matrix: rows=features, cols=[Overall, G, W, B]
    data = {}
    data["Overall"] = corr_overall.set_index("feature")["pearson_r"]
    for pos, corr_df in corr_by_pos.items():
        data[pos] = corr_df.set_index("feature")["pearson_r"]

    matrix = pd.DataFrame(data).reindex(features)
    matrix = matrix.fillna(0)

    fig, ax = plt.subplots(figsize=(8, max(6, len(features) * 0.5)))
    sns.heatmap(
        matrix, annot=True, fmt=".3f", cmap="RdYlGn", center=0,
        vmin=-0.3, vmax=0.3, ax=ax, linewidths=0.5,
    )
    ax.set_title("College Stats vs Career WAR (Pearson r)")
    ax.set_ylabel("College Stat")
    ax.set_xlabel("Position Group")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Heatmap saved to {output_path}")


def main():
    print("Loading player database...")
    df = load_players()

    # Filter to players with meaningful WAR data (drafted + some NBA time)
    df_war = df[df["draft_pick"] <= 60].copy()
    print(f"  {len(df_war)} drafted players with WAR data")

    all_features = STAT_COLS + PHYSICAL_COLS

    # Overall correlations
    print("\n=== OVERALL CORRELATIONS (college stats vs career WAR) ===")
    corr_overall = compute_correlations(df_war, all_features)
    print(corr_overall.to_string(index=False))

    # Per-position correlations
    corr_by_pos = {}
    for pos in ["G", "W", "B"]:
        df_pos = df_war[df_war["pos"] == pos]
        if len(df_pos) < 20:
            continue
        print(f"\n=== {pos} CORRELATIONS ({len(df_pos)} players) ===")
        corr_pos = compute_correlations(df_pos, all_features)
        corr_by_pos[pos] = corr_pos
        print(corr_pos.to_string(index=False))

    # Save heatmap
    heatmap_path = os.path.join(PROCESSED_DIR, "correlation_heatmap.png")
    plot_heatmap(corr_overall, corr_by_pos, heatmap_path)

    # Save correlation data
    corr_output = {
        "overall": corr_overall.to_dict(orient="records"),
    }
    for pos, df_c in corr_by_pos.items():
        corr_output[pos] = df_c.to_dict(orient="records")

    corr_path = os.path.join(PROCESSED_DIR, "correlations.json")
    with open(corr_path, "w") as f:
        json.dump(corr_output, f, indent=2)
    print(f"\n  Correlation data saved to {corr_path}")


if __name__ == "__main__":
    main()
