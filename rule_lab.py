"""Rule Lab: Test proposed rule changes against the full dataset.

Workflow:
1. Run current predict_tier as baseline
2. Run experimental predict_tier with proposed rules
3. Compare: who improved, who got worse, overall stats
"""
import json, os, sys, math
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    PLAYER_DB_PATH, PROCESSED_DIR, TIER_LABELS,
    LEVEL_MODIFIERS, STAR_SIGNAL_THRESHOLDS, POSITIONAL_AVGS,
)
from app.similarity import predict_tier as original_predict_tier, count_star_signals, detect_unicorn_traits

with open(PLAYER_DB_PATH) as f:
    DB = json.load(f)
with open(os.path.join(PROCESSED_DIR, "positional_avgs.json")) as f:
    POS_AVGS = json.load(f)


def player_to_prospect(player):
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
        "draft_pick": player.get("draft_pick", 60),
    }
    for adv in ["bpm", "obpm", "dbpm", "fta", "stl_per", "usg", "gp"]:
        if adv in s and s[adv]:
            prospect[adv] = s[adv]
    return prospect


# =====================================================================
#  EXPERIMENTAL predict_tier — modify rules here
# =====================================================================
def experimental_predict_tier(player, pos_avgs=None):
    """Same as original but with proposed rule changes."""
    if pos_avgs is None:
        pos_avgs = POSITIONAL_AVGS

    bpm = player.get("bpm", 0) or 0
    obpm = player.get("obpm", 0) or 0
    dbpm = player.get("dbpm", 0) or 0
    fta = player.get("fta", 0) or 0
    spg = player.get("spg", 0) or 0
    stl_per = player.get("stl_per", 0) or 0
    usg = player.get("usg", 0) or 0
    ppg = player.get("ppg", 0) or 0
    rpg = player.get("rpg", 0) or 0
    apg = player.get("apg", 0) or 0
    age = player.get("age", 21) or 21
    mpg = player.get("mpg", 30) or 30
    level = player.get("level", "High Major")
    fg = player.get("fg", 45) or 45
    draft_pick = player.get("draft_pick", 60)

    star_count, star_tags = count_star_signals(player)
    unicorns = detect_unicorn_traits(player, pos_avgs.get(player.get("pos", "W"), {}))

    score = 0.0
    reasons = []

    # ============================================================
    # RULE 1: Draft position — PENALTY ONLY, no bonus.
    # Lottery bonuses backfire (boost lottery busts equally).
    # But late picks with monster stats = teams saw something wrong.
    # ============================================================
    if draft_pick <= 14:
        pass  # neutral — lottery is a coin flip
    elif draft_pick <= 20:
        pass  # neutral
    elif draft_pick <= 30:
        score -= 5
        reasons.append(f"Mid-1st discount (#{draft_pick})")
    elif draft_pick <= 45:
        score -= 15
        reasons.append(f"Late pick discount (#{draft_pick})")
    else:
        score -= 25
        reasons.append(f"Deep 2nd round discount (#{draft_pick})")

    # ============================================================
    # RULE CHANGE 2: Conference-adjusted BPM/OBPM
    # BPM at weaker conferences is inflated by weaker competition.
    # Apply level modifier before scoring.
    # ============================================================
    level_mod = LEVEL_MODIFIERS.get(level, 1.0)
    adj_bpm = bpm * level_mod
    adj_obpm = obpm * level_mod

    # --- BPM family (conference-adjusted) ---
    # Reduced top tier: BPM>=10 is common among busts too (Kaminsky 13.8,
    # Calathes 8.9, Thornwell 13.5). Scale down the ceiling.
    if adj_bpm > 0:
        if adj_bpm >= 12.0:
            score += 20
            reasons.append(f"Elite adj-BPM ({adj_bpm:.1f})")
        elif adj_bpm >= 8.0:
            score += 14
            reasons.append(f"Star-level adj-BPM ({adj_bpm:.1f})")
        elif adj_bpm >= 5.0:
            score += 9
            reasons.append(f"Strong adj-BPM ({adj_bpm:.1f})")
        elif adj_bpm >= 3.0:
            score += 5
            reasons.append(f"Above-avg adj-BPM ({adj_bpm:.1f})")
        elif adj_bpm >= 0:
            score += 2

    if adj_obpm > 0:
        if adj_obpm >= 7.0:
            score += 16
            reasons.append(f"Elite adj-OBPM ({adj_obpm:.1f})")
        elif adj_obpm >= 5.0:
            score += 11
            reasons.append(f"Star adj-OBPM ({adj_obpm:.1f})")
        elif adj_obpm >= 3.0:
            score += 7
            reasons.append(f"Strong adj-OBPM ({adj_obpm:.1f})")
        elif adj_obpm >= 1.0:
            score += 3

    # DBPM (less affected by conference since defense is more universal)
    if dbpm > 0:
        if dbpm >= 4.0:
            score += 8
            reasons.append(f"Elite DBPM ({dbpm:.1f})")
        elif dbpm >= 2.5:
            score += 4

    # --- FTA per game (already stored as per-game rate) ---
    fta_pg = fta
    if fta_pg >= 7.0:
        score += 16
        reasons.append(f"Elite FTA rate ({fta_pg:.1f}/game)")
    elif fta_pg >= 5.5:
        score += 10
        reasons.append(f"High FTA rate ({fta_pg:.1f}/game)")
    elif fta_pg >= 4.0:
        score += 5
    elif fta_pg >= 2.5:
        score += 2

    # --- Steals ---
    if spg >= 1.8:
        score += 8
        reasons.append(f"Elite steals ({spg:.1f})")
    elif spg >= 1.3:
        score += 4

    if stl_per > 0 and stl_per >= 2.5:
        score += 6
        reasons.append(f"High steal% ({stl_per:.1f})")
    elif stl_per > 0 and stl_per >= 1.8:
        score += 3

    # --- Usage ---
    if usg > 0:
        if usg >= 30:
            score += 8
            reasons.append(f"High usage ({usg:.0f}%)")
        elif usg >= 27:
            score += 5
        elif usg >= 24:
            score += 2

    # ============================================================
    # RULE CHANGE 4: FT% — strongest separator (10% gap stars vs busts)
    # FT% = pure shooting skill proxy. Bad FT shooters rarely develop.
    # BUT: position-dependent. Bigs (Drummond, Bam, Harrell) can
    # succeed with bad FT%. Guards/wings cannot.
    # ============================================================
    ft_pct = player.get("ft", 70) or 70
    pos = player.get("pos", "W")
    # Full weight for G/W, reduced for B
    ft_weight = 1.0 if pos in ("G", "W") else 0.4

    if ft_pct >= 85:
        ft_pts = 10
        reasons.append(f"Elite FT shooter ({ft_pct:.0f}%)")
    elif ft_pct >= 78:
        ft_pts = 5
        reasons.append(f"Good FT shooter ({ft_pct:.0f}%)")
    elif ft_pct >= 70:
        ft_pts = 0  # neutral
    elif ft_pct >= 60:
        ft_pts = -6
        reasons.append(f"Poor FT shooter ({ft_pct:.0f}%)")
    else:
        ft_pts = -12
        reasons.append(f"Broken FT shot ({ft_pct:.0f}%)")
    score += ft_pts * ft_weight

    # --- PPG with level adjustment ---
    adj_ppg = ppg * level_mod
    if adj_ppg >= 20:
        score += 8
        reasons.append(f"20+ PPG scorer ({adj_ppg:.1f} adj)")
    elif adj_ppg >= 16:
        score += 4
    elif adj_ppg >= 12:
        score += 1

    # --- RPG for position ---
    pos = player.get("pos", "W")
    if pos == "G" and rpg >= 6:
        score += 4
        reasons.append(f"Rebounding guard ({rpg:.1f})")
    elif pos in ("W", "B") and rpg >= 9:
        score += 4
    elif rpg >= 5:
        score += 1

    # --- APG ---
    if apg >= 5:
        score += 4
        reasons.append(f"Playmaker ({apg:.1f} APG)")
    elif apg >= 3:
        score += 1

    # --- Efficiency with volume ---
    if fg >= 52 and adj_ppg >= 15:
        score += 4
        reasons.append(f"Efficient scorer ({fg:.0f}% on {adj_ppg:.0f} PPG)")

    # --- Star signal count ---
    if star_count >= 5:
        score += 12
        reasons.append(f"5+ star signals ({star_count}/6)")
    elif star_count >= 3:
        score += 6
        reasons.append(f"3+ star signals ({star_count}/6)")
    elif star_count >= 2:
        score += 2

    # --- Unicorn bonus ---
    if unicorns:
        score += 3 * len(unicorns)
        reasons.append(f"Unicorn traits: {', '.join(unicorns)}")

    # --- Level penalty (stats at lower levels inflate) ---
    if level == "Mid Major":
        score -= 5
    elif level == "Low Major":
        score -= 10
        reasons.append("Low Major discount")

    # --- Minutes context ---
    if mpg < 22:
        score -= 5
        reasons.append(f"Low minutes ({mpg:.0f} MPG)")

    # ============================================================
    # RULE CHANGE 3: Low-MPG + early pick = potential signal
    # Freshmen on stacked teams (Booker at Kentucky) play fewer
    # minutes but still get drafted high. Don't punish them.
    # Give a bonus for "high pick despite low minutes" — teams
    # see something the stats don't show.
    # ============================================================
    if mpg < 25 and draft_pick <= 14:
        score += 8
        reasons.append(f"Early pick despite low minutes (potential)")

    # --- Missing advanced stats ---
    has_advanced = any(player.get(s, 0) for s in ["bpm", "obpm", "fta", "stl_per", "usg"])
    if not has_advanced:
        if score > 40:
            score = 40
            reasons.append("Capped: no advanced stats available")

    # Map score to tier (same thresholds)
    if score >= 70:
        tier = 1
        confidence = min(95, 60 + score - 70)
    elif score >= 50:
        tier = 2
        confidence = 50 + (score - 50)
    elif score >= 30:
        tier = 3
        confidence = 40 + (score - 30)
    elif score >= 15:
        tier = 4
        confidence = 35 + (score - 15)
    else:
        tier = 5
        confidence = 30 + max(0, 15 - score)

    return {
        "tier": tier, "score": round(score, 1),
        "confidence": round(min(confidence, 95), 0),
        "reasons": reasons, "star_signals": star_count,
        "star_signal_tags": star_tags, "unicorn_traits": unicorns,
        "has_advanced_stats": has_advanced,
    }


# =====================================================================
#  Run comparison
# =====================================================================
def run_comparison():
    test_players = [p for p in DB
                    if p.get("has_college_stats")
                    and p.get("draft_pick", 99) <= 60
                    and p.get("nba_ws") is not None]

    results = []
    for p in test_players:
        prospect = player_to_prospect(p)
        actual = p["tier"]

        old = original_predict_tier(prospect, POS_AVGS)
        new = experimental_predict_tier(prospect, POS_AVGS)

        results.append({
            "name": p["name"], "pick": p.get("draft_pick", 99),
            "year": p.get("draft_year", "?"),
            "actual": actual, "ws": p.get("nba_ws", 0) or 0,
            "old_tier": old["tier"], "old_score": old["score"],
            "new_tier": new["tier"], "new_score": new["score"],
            "new_reasons": new["reasons"],
            "level": p["level"],
        })

    n = len(results)

    # --- Overall stats ---
    old_exact = sum(1 for r in results if r["old_tier"] == r["actual"])
    new_exact = sum(1 for r in results if r["new_tier"] == r["actual"])
    old_w1 = sum(1 for r in results if abs(r["old_tier"] - r["actual"]) <= 1)
    new_w1 = sum(1 for r in results if abs(r["new_tier"] - r["actual"]) <= 1)

    stars = [r for r in results if r["actual"] <= 2]
    old_star = sum(1 for r in stars if r["old_tier"] <= 2)
    new_star = sum(1 for r in stars if r["new_tier"] <= 2)

    busts = [r for r in results if r["actual"] >= 4]
    old_bust = sum(1 for r in busts if r["old_tier"] >= 4)
    new_bust = sum(1 for r in busts if r["new_tier"] >= 4)

    # False positives: predicted T1-T2 but actually T4-T5
    old_fp = sum(1 for r in results if r["old_tier"] <= 2 and r["actual"] >= 4)
    new_fp = sum(1 for r in results if r["new_tier"] <= 2 and r["actual"] >= 4)

    print("=" * 70)
    print("  RULE COMPARISON: Original vs Experimental predict_tier()")
    print("=" * 70)
    print(f"\n  {'Metric':>30s} {'Original':>10s} {'Experiment':>10s} {'Delta':>8s}")
    print(f"  {'-' * 60}")
    print(f"  {'Exact accuracy':>30s} {old_exact/n*100:9.1f}% {new_exact/n*100:9.1f}% {(new_exact-old_exact)/n*100:+7.1f}%")
    print(f"  {'Within-1 accuracy':>30s} {old_w1/n*100:9.1f}% {new_w1/n*100:9.1f}% {(new_w1-old_w1)/n*100:+7.1f}%")
    print(f"  {'Star detection (T1-T2)':>30s} {old_star}/{len(stars)} ({old_star/len(stars)*100:.0f}%) {new_star}/{len(stars)} ({new_star/len(stars)*100:.0f}%)")
    print(f"  {'Bust detection (T4-T5)':>30s} {old_bust}/{len(busts)} ({old_bust/len(busts)*100:.0f}%) {new_bust}/{len(busts)} ({new_bust/len(busts)*100:.0f}%)")
    print(f"  {'FALSE POSITIVES (pred<=2,act>=4)':>30s} {old_fp:>10d} {new_fp:>10d} {new_fp-old_fp:>+8d}")

    # --- Confusion matrix ---
    print(f"\n  EXPERIMENTAL CONFUSION MATRIX:")
    print(f"  {'':>12s}", end="")
    for t in range(1, 6):
        print(f" Pred={t:d}", end="")
    print()
    for actual_t in range(1, 6):
        row = [r for r in results if r["actual"] == actual_t]
        print(f"  Actual={actual_t:d}  ", end="")
        for pred_t in range(1, 6):
            count = sum(1 for r in row if r["new_tier"] == pred_t)
            print(f" {count:6d}", end="")
        print(f"  (n={len(row)})")

    # --- Who changed? ---
    improved = [r for r in results if abs(r["new_tier"] - r["actual"]) < abs(r["old_tier"] - r["actual"])]
    worsened = [r for r in results if abs(r["new_tier"] - r["actual"]) > abs(r["old_tier"] - r["actual"])]
    print(f"\n  Players improved: {len(improved)}")
    print(f"  Players worsened: {len(worsened)}")
    print(f"  Net improvement: {len(improved) - len(worsened):+d}")

    # Show T1 superstar results
    print(f"\n{'=' * 70}")
    print("  T1 SUPERSTARS")
    print("=" * 70)
    t1 = sorted([r for r in results if r["actual"] == 1], key=lambda x: -x["ws"])
    for r in t1:
        old_label = f"T{r['old_tier']}({r['old_score']:.0f})"
        new_label = f"T{r['new_tier']}({r['new_score']:.0f})"
        delta = r["old_tier"] - r["new_tier"]  # positive = improved
        marker = ">>>" if delta > 0 else ("<<<" if delta < 0 else "   ")
        print(f"  {marker} {r['name']:25s} #{r['pick']:2d} WS={r['ws']:5.0f} "
              f"old={old_label:10s} new={new_label:10s} actual=T1")

    # Show worst false positives that remain
    print(f"\n{'=' * 70}")
    print("  REMAINING FALSE POSITIVES (pred T1-T2, actual T4-T5)")
    print("=" * 70)
    remaining_fp = sorted([r for r in results if r["new_tier"] <= 2 and r["actual"] >= 4],
                          key=lambda x: -x["new_score"])
    for r in remaining_fp[:20]:
        print(f"  {r['name']:25s} #{r['pick']:2d} ({r['year']}) {r['level']:12s} "
              f"pred=T{r['new_tier']}({r['new_score']:.0f}) actual=T{r['actual']} WS={r['ws']:.0f}")

    # Show worst worsened players
    print(f"\n{'=' * 70}")
    print("  BIGGEST REGRESSIONS (new is further from actual)")
    print("=" * 70)
    worst_reg = sorted(worsened, key=lambda r: abs(r["new_tier"] - r["actual"]) - abs(r["old_tier"] - r["actual"]),
                       reverse=True)
    for r in worst_reg[:15]:
        print(f"  {r['name']:25s} #{r['pick']:2d} actual=T{r['actual']} "
              f"old=T{r['old_tier']}({r['old_score']:.0f}) new=T{r['new_tier']}({r['new_score']:.0f}) "
              f"WS={r['ws']:.0f}")

    # Show biggest improvements
    print(f"\n{'=' * 70}")
    print("  BIGGEST IMPROVEMENTS")
    print("=" * 70)
    best_imp = sorted(improved, key=lambda r: abs(r["old_tier"] - r["actual"]) - abs(r["new_tier"] - r["actual"]),
                      reverse=True)
    for r in best_imp[:15]:
        print(f"  {r['name']:25s} #{r['pick']:2d} actual=T{r['actual']} "
              f"old=T{r['old_tier']}({r['old_score']:.0f}) new=T{r['new_tier']}({r['new_score']:.0f}) "
              f"WS={r['ws']:.0f}")


if __name__ == "__main__":
    run_comparison()
