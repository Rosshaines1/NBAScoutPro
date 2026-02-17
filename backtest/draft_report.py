"""Draft Class Report Card.

For each draft year, runs every pick through the similarity engine and
compares the predicted tier to actual NBA outcome. Shows which picks
the model got right, which it missed, and overall accuracy by year.
"""
import sys
import os
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS
from app.similarity import find_top_matches, count_star_signals

REPORT_PATH = os.path.join(PROCESSED_DIR, "draft_report.txt")


def load_data():
    with open(PLAYER_DB_PATH) as f:
        return json.load(f)

    pos_avgs_path = os.path.join(PROCESSED_DIR, "positional_avgs.json")
    with open(pos_avgs_path) as f:
        return json.load(f)


def player_to_prospect(player):
    """Convert a player_db entry to a prospect dict (V2 with advanced stats)."""
    s = player["stats"]
    prospect = {
        "name": player["name"], "pos": player["pos"],
        "h": player["h"], "w": player["w"],
        "ws": player.get("ws", player["h"] + 4),
        "age": player.get("age", 22), "level": player["level"],
        "ath": player.get("ath", 2),
        "ppg": s["ppg"], "rpg": s["rpg"], "apg": s["apg"],
        "spg": s["spg"], "bpg": s["bpg"], "fg": s["fg"],
        "threeP": s["threeP"], "ft": s["ft"],
        "tpg": s["tpg"], "mpg": s["mpg"],
    }
    # Advanced stats (V2)
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg",
                "stops", "ts_per", "adjoe", "adrtg"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect


def predict_tier(matches):
    if not matches:
        return 5
    total_w = sum(m["similarity"]["score"] for m in matches)
    if total_w == 0:
        return 5
    return int(round(sum(m["similarity"]["score"] * m["player"]["tier"] for m in matches) / total_w))


def grade(predicted, actual):
    """Letter grade for prediction accuracy."""
    diff = abs(predicted - actual)
    if diff == 0:
        return "A"
    if diff == 1:
        return "B"
    if diff == 2:
        return "C"
    return "F"


def run_report(player_db, years=None):
    """Generate draft class report cards."""
    if years is None:
        # Default: years where we have college stats AND outcomes
        years = sorted(set(
            p["draft_year"] for p in player_db
            if p.get("draft_year") and p.get("has_college_stats")
            and p.get("nba_ws") is not None
            and p["draft_year"] >= 2009 and p["draft_year"] <= 2021
        ))

    pos_avgs_path = os.path.join(PROCESSED_DIR, "positional_avgs.json")
    with open(pos_avgs_path) as f:
        pos_avgs = json.load(f)

    lines = []
    overall_grades = []

    for year in years:
        # Test players: drafted this year, have college stats, have outcomes
        test_players = [
            p for p in player_db
            if p.get("draft_year") == year
            and p.get("has_college_stats")
            and p.get("nba_ws") is not None
            and p.get("draft_pick", 61) <= 60
        ]
        test_players.sort(key=lambda p: p["draft_pick"])

        if not test_players:
            continue

        # Train DB: everyone except this year
        train_db = [p for p in player_db if p.get("draft_year") != year]

        lines.append(f"\n{'='*80}")
        lines.append(f"  {year} NBA DRAFT - REPORT CARD")
        lines.append(f"{'='*80}")

        year_grades = []
        for tp in test_players:
            prospect = player_to_prospect(tp)
            matches = find_top_matches(prospect, train_db, pos_avgs, None, top_n=5)
            predicted = predict_tier(matches)
            actual = tp["tier"]
            g = grade(predicted, actual)
            year_grades.append(g)
            overall_grades.append(g)

            top_comp = matches[0]["player"]["name"] if matches else "None"
            top_score = matches[0]["similarity"]["score"] if matches else 0
            star_sigs, star_tags = count_star_signals(prospect)

            # Icon for hit/miss
            icon = "+" if g in ("A", "B") else "-"
            ws = tp.get("nba_ws", 0) or 0

            sig_str = f" *{star_sigs}sig" if star_sigs >= 3 else ""
            lines.append(
                f"  {icon} #{tp['draft_pick']:2d} {tp['name']:25s} "
                f"Pred=T{predicted} Actual=T{actual} ({g}) "
                f"WS={ws:5.1f}  Comp: {top_comp} ({top_score:.0f}%){sig_str}"
            )

        # Year summary
        grade_counts = Counter(year_grades)
        n = len(year_grades)
        a_b = grade_counts.get("A", 0) + grade_counts.get("B", 0)
        lines.append(f"\n  {year} Summary: {n} picks graded | "
                     f"A={grade_counts.get('A',0)} B={grade_counts.get('B',0)} "
                     f"C={grade_counts.get('C',0)} F={grade_counts.get('F',0)} | "
                     f"Hit rate (A+B): {a_b}/{n} ({a_b/n*100:.0f}%)")

    # Overall summary
    lines.append(f"\n{'='*80}")
    lines.append(f"  OVERALL SUMMARY ({years[0]}-{years[-1]})")
    lines.append(f"{'='*80}")
    n = len(overall_grades)
    gc = Counter(overall_grades)
    a_b_total = gc.get("A", 0) + gc.get("B", 0)
    lines.append(f"  Total picks graded: {n}")
    lines.append(f"  A (exact):    {gc.get('A',0):4d} ({gc.get('A',0)/n*100:.1f}%)")
    lines.append(f"  B (within 1): {gc.get('B',0):4d} ({gc.get('B',0)/n*100:.1f}%)")
    lines.append(f"  C (within 2): {gc.get('C',0):4d} ({gc.get('C',0)/n*100:.1f}%)")
    lines.append(f"  F (off by 3+):{gc.get('F',0):4d} ({gc.get('F',0)/n*100:.1f}%)")
    lines.append(f"  Hit rate (A+B): {a_b_total}/{n} ({a_b_total/n*100:.1f}%)")

    report = "\n".join(lines)
    print(report)

    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"\nReport saved to {REPORT_PATH}")


def main():
    player_db = load_data()
    run_report(player_db)


if __name__ == "__main__":
    main()
