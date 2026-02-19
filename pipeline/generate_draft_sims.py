"""Generate draft simulation data for the Streamlit app.

For each draft year 2010-2021, runs predict_tier on all players from that year
and ranks them by predicted tier (best first). Saves results to JSON.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS
from app.similarity import predict_tier

SIM_YEARS = list(range(2010, 2022))


def player_to_prospect(player):
    """Convert a player_db entry to a prospect dict for predict_tier."""
    s = player["stats"]
    prospect = {
        "name": player["name"],
        "pos": player["pos"],
        "h": player["h"],
        "w": player["w"],
        "ws": player.get("ws", player["h"] + 4),
        "age": player.get("age", 4),
        "level": player["level"],
        "quadrant": player.get("quadrant", "Q1"),
        "ath": player.get("ath", 0),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"],
        "fg": s["fg"], "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg", "ftr", "rim_pct", "tpa"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect


def main():
    with open(PLAYER_DB_PATH) as f:
        db = json.load(f)

    sims = {}

    for year in SIM_YEARS:
        year_players = [
            p for p in db
            if p.get("draft_year") == year
            and p.get("has_college_stats")
            and p.get("tier", 5) != 6
        ]

        predictions = []
        for p in year_players:
            prospect = player_to_prospect(p)
            result = predict_tier(prospect)
            predictions.append({
                "name": p["name"],
                "predicted_tier": result["tier"],
                "predicted_label": TIER_LABELS.get(result["tier"], "?"),
                "actual_tier": p["tier"],
                "actual_label": TIER_LABELS.get(p["tier"], "?"),
                "score": result["score"],
            })

        # Sort by predicted tier (ascending = best first), then by score (descending)
        predictions.sort(key=lambda x: (x["predicted_tier"], -x["score"]))

        # Add rank
        for i, pred in enumerate(predictions):
            pred["rank"] = i + 1

        sims[str(year)] = predictions
        correct = sum(1 for p in predictions if p["predicted_tier"] == p["actual_tier"])
        within1 = sum(1 for p in predictions if abs(p["predicted_tier"] - p["actual_tier"]) <= 1)
        n = len(predictions)
        print(f"  {year}: {n} players, exact={correct}/{n} ({correct/n*100:.0f}%), within-1={within1}/{n} ({within1/n*100:.0f}%)")

    # Save
    output_path = os.path.join(PROCESSED_DIR, "draft_simulations.json")
    with open(output_path, "w") as f:
        json.dump(sims, f, indent=2)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
