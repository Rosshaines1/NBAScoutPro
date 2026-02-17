"""Derive new V3 weights from correlation analysis results.

Maps combined predictive power scores to weight scale (0.0 - 5.0).
Applies user constraints and scouting insights.
Outputs V3_WEIGHTS dict ready for config.py.
"""
import json
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_correlations():
    path = os.path.join(os.path.dirname(__file__), "correlation_results.json")
    with open(path) as f:
        return json.load(f)


def derive_weights(corr_data):
    """Derive V3 weights from correlation data with user constraints."""
    stats = corr_data["stats"]
    ranked = corr_data["ranked"]

    # Get all combined scores
    scores = {stat: data["combined_score"] for stat, data in ranked}
    max_score = max(scores.values()) if scores else 1

    # Map to 0-5 scale proportionally
    raw_weights = {}
    for stat, score in scores.items():
        raw_weights[stat] = round(score / max_score * 5.0, 2)

    print("RAW DATA-DRIVEN WEIGHTS (0-5 scale)")
    print("=" * 50)
    for stat, w in sorted(raw_weights.items(), key=lambda x: -x[1]):
        r = stats[stat]["r"]
        sep = stats[stat]["separation"]
        print(f"  {stat:>10s}: {w:>5.2f}  (r={r:+.4f}, sep={sep:+.2f})")

    # Apply constraints from scouting insights
    v3 = dict(raw_weights)

    # --- HARD CONSTRAINTS ---
    # Disabled stats (no real data)
    v3["weight"] = 0.0
    v3["ws"] = 0.0      # wingspan — all estimated h+4
    v3["ath"] = 0.0      # athleticism — no data

    # BPM must stay highest (per previous analysis + user insight)
    # If data says otherwise, keep BPM at top but note it
    if "bpm" in v3:
        v3["bpm"] = max(v3["bpm"], 4.5)

    # FT% must remain high (star/bust separator per user insight)
    if "ft" in v3:
        v3["ft"] = max(v3["ft"], 3.5)

    # FTA must remain high (star signal per user insight)
    if "fta" in v3:
        v3["fta_pg"] = max(v3.get("fta", 0), 3.0)
        if "fta" in v3 and "fta_pg" not in raw_weights:
            del v3["fta"]  # rename to fta_pg

    # 3P% stays very low (r~0 per previous analysis)
    if "threeP" in v3:
        v3["threeP"] = min(v3["threeP"], 0.3)

    # Counting stats context-dependent — cap them
    for stat in ["ppg", "rpg", "apg", "bpg", "mpg"]:
        if stat in v3:
            v3[stat] = min(v3[stat], 1.0)

    # Height stays meaningful for comps (physical translation)
    if "height" in v3:
        v3["height"] = max(v3["height"], 2.5)

    # Age (class year) — freshmen declaring is strong signal
    if "age" in v3:
        v3["age"] = max(v3["age"], 1.0)

    # Ensure fta key is fta_pg for consistency with similarity engine
    if "fta" in v3:
        v3["fta_pg"] = v3.pop("fta")

    print("\n\nV3 WEIGHTS (after constraints)")
    print("=" * 50)
    for stat, w in sorted(v3.items(), key=lambda x: -x[1]):
        constraint = ""
        if stat in ("weight", "ws", "ath"):
            constraint = " [DISABLED - no data]"
        elif stat in raw_weights and abs(v3[stat] - raw_weights.get(stat, 0)) > 0.01:
            constraint = f" [constrained from {raw_weights.get(stat, 0):.2f}]"
        print(f"  {stat:>10s}: {w:>5.2f}{constraint}")

    return v3


def derive_archetype_mods(corr_data):
    """Suggest archetype weight modifier adjustments based on data patterns."""
    stats = corr_data["stats"]

    print("\n\nARCHETYPE MODIFIER SUGGESTIONS")
    print("=" * 50)
    print("(Based on which stats have highest overall predictive power)")
    print("Note: actual within-archetype tuning requires per-archetype correlation")
    print("analysis which will be done in Step 5 after base weights are set.")

    # For now, keep existing modifiers but flag any that conflict with data
    suggestions = {}

    # If a stat has near-zero correlation but high archetype modifier, flag it
    for stat, data in stats.items():
        if data["abs_r"] < 0.03 and data["combined_score"] < 0.1:
            print(f"  WARNING: {stat} has near-zero predictive power (r={data['r']:.4f})")
            print(f"           Consider reducing archetype modifiers that boost this stat")

    return suggestions


def main():
    corr_data = load_correlations()
    v3_weights = derive_weights(corr_data)
    suggestions = derive_archetype_mods(corr_data)

    # Save
    output = {
        "v3_weights": v3_weights,
        "archetype_suggestions": suggestions,
    }
    output_path = os.path.join(os.path.dirname(__file__), "v3_weights.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nV3 weights saved to {output_path}")

    # Print config-ready format
    print("\n\n# COPY-PASTE FOR config.py:")
    print("V3_WEIGHTS = {")
    for stat, w in sorted(v3_weights.items(), key=lambda x: -x[1]):
        print(f'    "{stat}": {w},')
    print("}")


if __name__ == "__main__":
    main()
