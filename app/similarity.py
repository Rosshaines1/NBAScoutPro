"""V3 similarity engine: comp finder + separated tier prediction.

Key changes from V2:
- Athleticism REMOVED from distance calc (no real data for historicals)
- Age REMOVED from penalties (young = good, handled in tier prediction)
- Penalties scaled way down (max 5-15 pts, cap at 25 total)
- Similarity is now purely "how similar do these stat lines look?"
- Tier prediction is a SEPARATE system using features that actually predict NBA success
"""
import json
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MAX_STATS, LEVEL_MODIFIERS, POSITIONAL_AVGS, V2_WEIGHTS, V3_WEIGHTS,
    PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, FEATURE_IMPORTANCE_PATH,
    STAR_SIGNAL_THRESHOLDS, ARCHETYPE_WEIGHT_MODS, STAT_RANGES,
    EXCLUDE_PLAYERS, COMP_YEAR_RANGE, QUADRANT_MODIFIERS,
)

# Maximum total penalty (percentage points) — prevents penalty stacking from
# destroying match scores. Penalties are for "these players shouldn't be compared"
# not "this player is bad".
MAX_PENALTY = 25


def normalize(val, max_val):
    return min(max(val / max_val, 0), 1) if max_val != 0 else 0


def range_normalize(val, key):
    """Normalize using meaningful stat ranges instead of absolute max.

    A 4-inch height gap = 25% of range (70-86), not 4.7% of max (/86).
    Stats with real floors (height, FT%, BPM) get proper range scaling.
    Falls back to MAX_STATS-based normalization for unknown keys.
    """
    if key in STAT_RANGES:
        lo, hi = STAT_RANGES[key]
        if hi == lo:
            return 0.5
        return min(max((val - lo) / (hi - lo), 0), 1)
    max_val = MAX_STATS.get(key, 1)
    return min(max(val / max_val, 0), 1) if max_val != 0 else 0


def get_outlier_multiplier(val, avg):
    if avg == 0:
        return 1.0
    ratio = val / avg
    if ratio > 1.4:
        return 3.0
    if ratio > 1.2:
        return 1.5
    if ratio < 0.7:
        return 1.5
    return 1.0


def calculate_identity_map(adj_a, player_a, input_ato, pos_avg):
    return {
        "ppg": get_outlier_multiplier(adj_a["ppg"], pos_avg.get("ppg", 13)),
        "rpg": get_outlier_multiplier(adj_a["rpg"], pos_avg.get("rpg", 5)),
        "apg": get_outlier_multiplier(adj_a["apg"], pos_avg.get("apg", 2.5)),
        "spg": get_outlier_multiplier(adj_a["spg"], pos_avg.get("spg", 1)),
        "bpg": get_outlier_multiplier(adj_a["bpg"], pos_avg.get("bpg", 0.5)),
        "threeP": get_outlier_multiplier(player_a.get("threeP", 33), pos_avg.get("threeP", 33)),
        "ft": get_outlier_multiplier(player_a.get("ft", 70), pos_avg.get("ft", 70)),
        "ato": get_outlier_multiplier(input_ato, pos_avg.get("ato", 1.25)),
    }


def normalize_to_30(stats_dict, mpg):
    """Per-30-minute normalization with non-linear MPG handling."""
    mpg = mpg or 30.0
    factor = 30.0 / mpg
    damped_factor = 1 + (factor - 1) * 0.7
    if mpg < 22:
        damped_factor *= (0.88 + 0.12 * (mpg / 22.0))
    result = dict(stats_dict)
    for key in ["ppg", "rpg", "apg", "spg", "bpg", "tpg"]:
        result[key] = (stats_dict.get(key, 0) or 0) * damped_factor
    return result


def count_star_signals(player):
    """Count how many superstar indicator thresholds a player exceeds."""
    signals = 0
    tags = []
    for stat, threshold in STAR_SIGNAL_THRESHOLDS.items():
        val = player.get(stat, 0) or 0
        if val > threshold:
            signals += 1
            tags.append(stat)
    return signals, tags


def detect_unicorn_traits(prospect, pos_avg):
    """Detect unusual/unicorn traits that indicate special upside."""
    traits = []
    pos = prospect.get("pos", "W")
    ppg = prospect.get("ppg", 0)
    rpg = prospect.get("rpg", 0)
    apg = prospect.get("apg", 0)
    bpg = prospect.get("bpg", 0)
    spg = prospect.get("spg", 0)
    threeP = prospect.get("threeP", 0)
    h = prospect.get("h", 78)

    if pos == "G" and rpg > 7.0:
        traits.append("rebounding_guard")
    if pos == "B" and apg > 3.5:
        traits.append("passing_big")
    if pos == "B" and threeP > 33 and ppg > 10:
        traits.append("stretch_big")
    if pos in ("G", "W") and bpg > 1.5:
        traits.append("shot_blocking_wing")
    if pos == "G" and h > 77 and apg > 4:
        traits.append("tall_playmaker")
    if pos == "G" and h < 75 and spg > 2.0:
        traits.append("pickpocket")
    if pos in ("W", "B") and spg > 1.8:
        traits.append("defensive_unicorn")

    return traits


def predict_tier(player, pos_avgs=None):
    """Predict NBA tier from college stats only (no draft position or NBA data).

    V4 improvements:
      - Removed draft_pick (NBA data, not available for prospects)
      - Added FT Rate, Rim%, 3PA volume context
      - Team-strength-adjusted BPM/OBPM (quadrant modifier applied before scoring)
      - Red flag counter-indicators (6 rules from bust pattern analysis)
      - Boundaries retuned: 80/54/40/22

    Returns: dict with tier, score, confidence, reasons, signals
    """
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
    mpg = player.get("mpg", 30) or 30
    level = player.get("level", "High Major")
    quadrant = player.get("quadrant", "Q1")
    fg = player.get("fg", 45) or 45
    ftr = player.get("ftr", 0) or 0
    rim_pct = player.get("rim_pct", 0) or 0
    tpa = player.get("tpa", 0) or 0
    pos = player.get("pos", "W")

    star_count, star_tags = count_star_signals(player)
    unicorns = detect_unicorn_traits(player, pos_avgs.get(pos, {}))

    score = 0.0
    reasons = []

    # --- Team-strength-adjusted BPM/OBPM ---
    # BPM at weaker teams is inflated by weaker competition.
    # Uses Barttorvik quadrant: Q1=1.0, Q2=0.90, Q3=0.80, Q4=0.70
    quad_mod = QUADRANT_MODIFIERS.get(quadrant, 1.0)
    adj_bpm = bpm * quad_mod
    adj_obpm = obpm * quad_mod

    if adj_bpm >= 12.0:
        score += 20
        reasons.append("Dominant all-around impact — elite production relative to competition")
    elif adj_bpm >= 8.0:
        score += 14
        reasons.append("Strong all-around impact — producing at a high level on both ends")
    elif adj_bpm >= 5.0:
        score += 9
        reasons.append("Solid overall impact — positive contributor across the board")
    elif adj_bpm >= 3.0:
        score += 5
        reasons.append("Moderate overall impact — above-average contributor")
    elif adj_bpm >= 0:
        score += 2
    elif adj_bpm >= -2.0:
        score -= 3
    else:
        score -= 8
        reasons.append("Negative overall impact — production does not translate to winning")

    if adj_obpm > 0:
        if adj_obpm >= 7.0:
            score += 16
            reasons.append("Elite offensive creation — generates scoring at a star-level rate")
        elif adj_obpm >= 5.0:
            score += 11
            reasons.append("Strong offensive creation — high-level scoring impact")
        elif adj_obpm >= 3.0:
            score += 7
            reasons.append("Good offensive creation — positive scoring impact")
        elif adj_obpm >= 1.0:
            score += 3

    if dbpm > 0:
        if dbpm >= 4.0:
            score += 8
            reasons.append("Defensive playmaking signals — high-impact defender by the numbers")
        elif dbpm >= 2.5:
            score += 4

    # --- FTA per game (already stored as per-game rate) ---
    fta_pg = fta
    if fta_pg >= 7.0:
        score += 16
        reasons.append(f"Free throw rate indicates scoring scalability ({fta_pg:.1f} FTA/game)")
    elif fta_pg >= 5.5:
        score += 10
        reasons.append(f"Good free throw rate — gets to the line at a strong clip ({fta_pg:.1f} FTA/game)")
    elif fta_pg >= 4.0:
        score += 5
    elif fta_pg >= 2.5:
        score += 2

    # --- FT Rate (ftr): how often you get to the line per shot attempt ---
    # Independent of BPM (r=0.103 vs bpm), star-bust gap +4.0
    # Measures aggressiveness/craft — translates to NBA
    if ftr > 0:
        if ftr >= 50:
            score += 8
            reasons.append(f"Aggressive scorer — draws fouls at an elite rate ({ftr:.0f}% FT rate)")
        elif ftr >= 42:
            score += 4
        elif ftr >= 35:
            score += 1

    # --- Rim finishing (rim_pct): percentage at the rim ---
    # Very independent of BPM (r=0.045), r=0.138 with WS
    # Finishing at the rim translates directly to NBA
    if rim_pct > 0:
        if rim_pct >= 72:
            score += 6
            reasons.append(f"Finishes at the rim at an elite rate ({rim_pct:.0f}%) — translates to NBA")
        elif rim_pct >= 65:
            score += 3
        elif rim_pct < 55:
            score -= 3
            reasons.append(f"Struggles finishing at the rim ({rim_pct:.0f}%) — concerning for NBA translation")

    # --- Steals (consolidated: use STL_PER if available, else SPG) ---
    # Both r~0.11 and highly correlated — pick the better one, don't double-dip.
    if stl_per > 0:
        if stl_per >= 2.5:
            score += 8
            reasons.append("Defensive playmaking — elite ball-hawk instincts")
        elif stl_per >= 1.8:
            score += 4
    else:
        if spg >= 1.8:
            score += 8
            reasons.append(f"Defensive playmaking — active hands and anticipation ({spg:.1f} SPG)")
        elif spg >= 1.3:
            score += 4

    # --- Usage ---
    if usg > 0:
        if usg >= 30:
            score += 8
            reasons.append(f"High-volume role — the offense runs through this player ({usg:.0f}% USG)")
        elif usg >= 27:
            score += 5
        elif usg >= 24:
            score += 2

    # --- FT%: PENALTY ONLY (V3: r=0.018 overall, but FT<65 = 71% bust rate) ---
    # Good FT% does NOT predict stars. Bad FT% DOES predict busts.
    # Bigs can succeed with bad FT% (Drummond, Bam), guards/wings cannot.
    ft_pct = player.get("ft", 70) or 70
    ft_weight = 1.0 if pos in ("G", "W") else 0.4

    if ft_pct >= 70:
        ft_pts = 0
    elif ft_pct >= 60:
        ft_pts = -6
        reasons.append(f"Concerning free throw shooting ({ft_pct:.0f}%) — limits scoring ceiling")
    else:
        ft_pts = -12
        reasons.append(f"Free throw shooting is a major concern ({ft_pct:.0f}%) — historically a bust indicator")
    score += ft_pts * ft_weight

    # --- PPG with team strength adjustment ---
    adj_ppg = ppg * quad_mod
    if adj_ppg >= 20:
        score += 8
        reasons.append(f"High-level scorer — {adj_ppg:.1f} PPG adjusted for competition")
    elif adj_ppg >= 16:
        score += 4
    elif adj_ppg >= 12:
        score += 1

    # --- RPG for position ---
    if pos == "G" and rpg >= 6:
        score += 4
        reasons.append(f"Rebounding guard — rare trait that signals versatility ({rpg:.1f} RPG)")
    elif pos in ("W", "B") and rpg >= 9:
        score += 4
    elif rpg >= 5:
        score += 1

    # --- APG: removed (V3: r=0.008, essentially zero predictor) ---

    # --- Efficiency with volume ---
    if fg >= 52 and adj_ppg >= 15:
        score += 4
        reasons.append(f"Efficient production at moderate-to-high usage ({fg:.0f}% eFG on {adj_ppg:.0f} PPG)")

    # --- 3PA volume context ---
    # Good 3P% on low volume is meaningless; high volume + good % is a real skill
    threeP = player.get("threeP", 0) or 0
    if tpa > 0 and threeP > 0:
        if tpa >= 5 and threeP >= 35:
            score += 4
            reasons.append(f"Proven 3-point shooter on volume ({tpa:.1f} attempts at {threeP:.0f}%)")
        elif tpa >= 3 and threeP >= 37:
            score += 2

    # --- Star signal count ---
    n_thresholds = len(STAR_SIGNAL_THRESHOLDS)
    if star_count >= 5:
        score += 12
        reasons.append(f"Strong star profile — exceeds {star_count} of {n_thresholds} historical star thresholds")
    elif star_count >= 3:
        score += 6
        reasons.append(f"Promising star profile — exceeds {star_count} of {n_thresholds} historical star thresholds")
    elif star_count >= 2:
        score += 2

    # --- Unicorn bonus ---
    if unicorns:
        score += 3 * len(unicorns)
        reasons.append(f"Rare statistical outlier: {', '.join(unicorns)}")

    # --- Team strength penalty (quadrant-based) ---
    if quadrant == "Q2":
        score -= 3
    elif quadrant == "Q3":
        score -= 7
        reasons.append("Competition level discount — mid-tier program (team rank 101-200)")
    elif quadrant == "Q4":
        score -= 12
        reasons.append("Competition level discount — low-tier program (team rank 200+)")

    # --- Minutes context ---
    if mpg < 22:
        score -= 5
        reasons.append(f"Limited sample size — only {mpg:.0f} minutes per game")

    # --- Height / size filter ---
    # Guards under 6'1": 77% bust rate, only 1 star (Isaiah Thomas) in dataset.
    # Wings under 6'4": 60% bust rate, 0 stars in dataset.
    h = player.get("h", 78) or 78
    if pos == "G" and h < 73:
        score -= 10
        reasons.append(f"Size concern: undersized guard at {h // 12}'{h % 12:02d}\" — historically 77% bust rate")
    elif pos == "G" and h < 74:
        score -= 5
        reasons.append(f"Size concern: undersized guard at {h // 12}'{h % 12:02d}\"")
    elif pos == "W" and h < 76:
        score -= 8
        reasons.append(f"Size concern: undersized wing at {h // 12}'{h % 12:02d}\" — historically 60% bust rate")

    # --- Missing advanced stats fallback ---
    # Players without BPM/OBPM/USG can't earn those star signals, so they're
    # structurally capped. Award proxy points from counting stats instead.
    has_advanced = any(player.get(s, 0) for s in ["bpm", "obpm", "fta", "stl_per", "usg"])
    if not has_advanced:
        proxy = 0
        # Elite scorer + good touch = proxy for high BPM/USG
        if adj_ppg >= 20 and ft_pct >= 78:
            proxy += 12
            reasons.append(f"Scoring profile suggests high impact ({adj_ppg:.0f} PPG, {ft_pct:.0f}% FT)")
        elif adj_ppg >= 16 and ft_pct >= 75:
            proxy += 6
            reasons.append("Solid scoring profile with respectable touch")
        # High FTA rate even without other advanced stats
        if fta_pg >= 5.5:
            proxy += 8
            reasons.append(f"Gets to the foul line at a high rate ({fta_pg:.1f}/game)")
        elif fta_pg >= 3.5:
            proxy += 4
        # Elite steals per game = defensive instincts proxy
        if spg >= 1.8:
            proxy += 4
        score += proxy
        if proxy == 0 and score > 40:
            score = 40
            reasons.append("Projection capped — add advanced stats (BPM, OBPM, FTA) for full accuracy")

    # --- Class year signal (V4: retuned Feb 2026 on 582 players) ---
    # Fr: 22.9% star, 22.2% bust | So: 8.8% star, 34.6% bust
    # Jr: 6.0% star, 41.9% bust  | Sr: 2.8% star, 54.5% bust
    # Fr->So is the steepest cliff (14pp star drop), gap widened accordingly.
    class_yr = player.get("age", 0) or 0
    if class_yr == 1:  # Freshman — 51.6% starter+ rate
        score += 6
        reasons.append("Freshman declaring — historically the strongest age signal for NBA success")
    elif class_yr == 2:  # Sophomore — 38.2% starter+ rate
        score += 1
    elif class_yr == 3:  # Junior — 27.4% starter+ rate, 41.9% bust rate
        score -= 2
        reasons.append("Junior — later declaration correlates with lower NBA outcomes historically")
    elif class_yr == 4:  # Senior — 18.8% starter+ rate, 54.5% bust rate
        score -= 5
        reasons.append("Senior — four-year players have significantly worse NBA track records")

    # ================================================================
    # RED FLAGS: Counter-indicators that predict bust despite good stats
    # Derived from corrected-tier analysis (Feb 2026, 496 players)
    # These fire AFTER bonuses so they counterbalance inflated scores.
    # ================================================================

    # Red flag 1: Empty calories — high usage but low impact
    # USG>24 + BPM<6 = 74% bust rate, 8% star rate
    # Scaled: bigger gap between USG and BPM = stronger penalty
    if has_advanced and usg >= 24 and adj_bpm < 6:
        gap_severity = (24 - adj_bpm) / 4  # 0 at BPM=6, ~1.5 at BPM=0
        ec_penalty = min(10, round(4 + gap_severity * 4))
        score -= ec_penalty
        reasons.append(f"Concern: high usage without proportional impact ({usg:.0f}% USG but limited BPM)")

    # Red flag 2: Offense-only player — no defensive value
    # OBPM>5 + DBPM<1 = 67% bust rate
    if has_advanced and obpm >= 5 and dbpm < 1:
        score -= 6
        reasons.append("Concern: offensive production with no defensive contribution")

    # Red flag 3: Inefficient volume scorer
    # PPG>14 + eFG<46 = 62% bust rate, 0% star rate
    if adj_ppg >= 14 and fg < 46:
        score -= 8
        reasons.append(f"Concern: scoring volume without efficiency ({adj_ppg:.0f} PPG on {fg:.0f}% eFG)")

    # Red flag 4: Can't draw fouls at high usage
    # USG>24 + FTA<3 = 70% bust rate — can't create at next level
    if has_advanced and usg >= 24 and fta_pg < 3:
        score -= 6
        reasons.append("Concern: high usage but rarely gets to the foul line — questions NBA-level shot creation")

    # Red flag 5: Senior stat-stuffer — retuned Feb 2026.
    # Senior + PPG>14 = 75% bust rate, 3% star rate.
    # Senior + BPM>7: avg tier 4.03 (best Sr subgroup, but still bad).
    # Reduced BPM penalty (was -5, now -3) since high-BPM seniors are the
    # most likely to succeed. Max Sr penalty = -5 + -6 + -3 = -14.
    if class_yr == 4 and adj_ppg >= 14:
        score -= 6
        reasons.append("Concern: senior scorer — historically 75% bust rate for 4-year scorers")
    if class_yr == 4 and has_advanced and adj_bpm >= 7:
        score -= 3
        reasons.append("Concern: strong senior production may represent a peak, not a trajectory")

    # Red flag 6: Weak team stat inflation
    # Q3/Q4 team + BPM>8 = inflated stats against weak competition
    # (quad_mod already discounts BPM, but this adds explicit penalty for extreme cases)
    if quadrant in ("Q3", "Q4") and has_advanced and bpm >= 8:
        penalty = -5 if quadrant == "Q3" else -8
        score += penalty
        reasons.append(f"Concern: inflated stats from weak competition ({quadrant} program)")

    # Map score to tier (V4: retuned after adding ftr/rim_pct/tpa, removing draft_pick)
    if score >= 80:
        tier = 1
        confidence = min(95, 60 + score - 80)
    elif score >= 54:
        tier = 2
        confidence = 50 + (score - 54)
    elif score >= 40:
        tier = 3
        confidence = 40 + (score - 40)
    elif score >= 22:
        tier = 4
        confidence = 35 + (score - 22)
    else:
        tier = 5
        confidence = 30 + max(0, 22 - score)

    return {
        "tier": tier,
        "score": round(score, 1),
        "confidence": round(min(confidence, 95), 0),
        "reasons": reasons,
        "star_signals": star_count,
        "star_signal_tags": star_tags,
        "unicorn_traits": unicorns,
        "has_advanced_stats": has_advanced,
    }


def classify_archetype(player):
    """Classify a player into one of 6 archetypes based on statistical profile.

    Works with both DB entries (stats nested under 'stats' key) and prospect
    dicts (stats flat at top level).

    Returns (primary_archetype, confidence_score, secondary_archetype).
    """
    if "stats" in player:
        s = player["stats"]
        pos = player.get("pos", "W")
        h = player.get("h", 78)
    else:
        s = player
        pos = player.get("pos", "W")
        h = player.get("h", 78)

    ppg = s.get("ppg", 0) or 0
    rpg = s.get("rpg", 0) or 0
    apg = s.get("apg", 0) or 0
    spg = s.get("spg", 0) or 0
    bpg = s.get("bpg", 0) or 0
    tpg = s.get("tpg", 0) or 0
    mpg = s.get("mpg", 30) or 30
    fg = s.get("fg", 45) or 45
    threeP = s.get("threeP", 33) or 33
    ft = s.get("ft", 70) or 70
    fta = s.get("fta", 0) or 0
    usg = s.get("usg", 0) or 0
    bpm = s.get("bpm", 0) or 0
    obpm = s.get("obpm", 0) or 0
    dbpm = s.get("dbpm", 0) or 0
    rim_att = s.get("rim_att", 0) or 0
    stl_per = s.get("stl_per", 0) or 0

    ato = apg / tpg if tpg > 0 else apg
    fta_pg = fta  # already per-game

    # Guard affinity: wings who play like guards
    guard_like = False
    if pos == "W":
        if h <= 76:
            guard_like = True
        elif h <= 78 and (apg >= 3.5 or (ppg >= 18 and rpg < 5)):
            guard_like = True

    scores = {}

    # --- SCORING GUARD ---
    sg_score = 0
    if pos == "G":
        sg_score += 12
    elif guard_like:
        sg_score += 8
    if ppg >= 20: sg_score += 10
    elif ppg >= 16: sg_score += 6
    elif ppg >= 12: sg_score += 3
    if usg >= 28: sg_score += 6
    elif usg >= 24: sg_score += 3
    if fta_pg >= 5: sg_score += 4
    elif fta_pg >= 3: sg_score += 2
    if ft >= 78: sg_score += 3
    if threeP >= 35: sg_score += 2
    if apg >= 4: sg_score += 2
    scores["Scoring Guard"] = sg_score

    # --- PLAYMAKING GUARD ---
    pg_score = 0
    if pos == "G":
        pg_score += 12
    elif guard_like and apg >= 3:
        pg_score += 8
    elif pos == "W" and apg >= 5:
        pg_score += 6
    if apg >= 6: pg_score += 10
    elif apg >= 4.5: pg_score += 7
    elif apg >= 3.5: pg_score += 4
    elif apg >= 2.5: pg_score += 2
    if ato >= 2.5: pg_score += 6
    elif ato >= 1.8: pg_score += 4
    elif ato >= 1.3: pg_score += 2
    if spg >= 1.5: pg_score += 3
    if stl_per >= 2.5: pg_score += 3
    if ppg < 14: pg_score += 2
    scores["Playmaking Guard"] = pg_score

    # --- 3&D WING ---
    td_score = 0
    if pos == "W":
        td_score += 8
    elif pos == "G" and h >= 76:
        td_score += 4
    if threeP >= 38: td_score += 7
    elif threeP >= 35: td_score += 5
    elif threeP >= 33: td_score += 3
    if ft >= 78: td_score += 3
    elif ft >= 73: td_score += 1
    if spg >= 1.5: td_score += 5
    elif spg >= 1.0: td_score += 3
    elif spg >= 0.8: td_score += 1
    if bpg >= 0.8: td_score += 2
    if dbpm >= 3.0: td_score += 3
    elif dbpm >= 1.5: td_score += 1
    if ppg < 12: td_score += 3
    elif ppg < 15: td_score += 1
    elif ppg >= 20: td_score -= 5
    elif ppg >= 18: td_score -= 3
    scores["3&D Wing"] = td_score

    # --- SCORING WING ---
    sw_score = 0
    if pos == "W":
        sw_score += 10
    elif pos == "B" and h <= 81:
        sw_score += 5
    elif pos == "G" and h >= 77:
        sw_score += 5
    if ppg >= 20: sw_score += 10
    elif ppg >= 16: sw_score += 7
    elif ppg >= 13: sw_score += 4
    elif ppg >= 10: sw_score += 1
    if usg >= 28: sw_score += 6
    elif usg >= 24: sw_score += 4
    elif usg >= 20: sw_score += 2
    if fta_pg >= 5: sw_score += 4
    elif fta_pg >= 3: sw_score += 2
    if h >= 79: sw_score += 3
    elif h >= 77: sw_score += 1
    if rpg >= 7: sw_score += 3
    elif rpg >= 5: sw_score += 1
    scores["Scoring Wing"] = sw_score

    # --- SKILLED BIG ---
    sb_score = 0
    if pos == "B":
        sb_score += 10
    elif pos == "W" and h >= 81:
        sb_score += 5
    if ft >= 78: sb_score += 8
    elif ft >= 72: sb_score += 6
    elif ft >= 65: sb_score += 3
    if threeP >= 33: sb_score += 6
    elif threeP >= 25: sb_score += 3
    elif threeP >= 15: sb_score += 1
    if rpg >= 8: sb_score += 3
    elif rpg >= 6: sb_score += 1
    if bpm >= 6: sb_score += 4
    elif bpm >= 3: sb_score += 2
    if obpm >= 4: sb_score += 4
    elif obpm >= 2: sb_score += 2
    if ppg >= 15: sb_score += 2
    scores["Skilled Big"] = sb_score

    # --- ATHLETIC BIG ---
    ab_score = 0
    if pos == "B":
        ab_score += 10
    elif pos == "W" and h >= 82:
        ab_score += 5
    if bpg >= 2.5: ab_score += 8
    elif bpg >= 1.5: ab_score += 5
    elif bpg >= 1.0: ab_score += 3
    if rim_att >= 4.0: ab_score += 6
    elif rim_att >= 2.5: ab_score += 4
    elif rim_att >= 1.0: ab_score += 2
    if rpg >= 9: ab_score += 5
    elif rpg >= 7: ab_score += 3
    elif rpg >= 5: ab_score += 1
    if dbpm >= 5: ab_score += 5
    elif dbpm >= 3: ab_score += 3
    elif dbpm >= 1: ab_score += 1
    if ft < 55: ab_score += 4
    elif ft < 65: ab_score += 2
    elif ft >= 78: ab_score -= 4
    elif ft >= 72: ab_score -= 2
    scores["Athletic Big"] = ab_score

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return ranked[0][0], ranked[0][1], ranked[1][0]


def calculate_similarity(player_a, player_b, pos_avgs=None, use_v2=True, weight_mods=None, use_v3=False):
    """Calculate weighted similarity between prospect and database player.

    This answers: "How similar do these two players LOOK statistically?"
    It does NOT predict tier — that's predict_tier()'s job.

    Weight selection: use_v3=True > use_v2=True > original weights.
    """
    if pos_avgs is None:
        pos_avgs = POSITIONAL_AVGS

    if use_v3:
        base_weights = dict(V3_WEIGHTS)
    elif use_v2:
        base_weights = dict(V2_WEIGHTS)
    else:
        base_weights = {
            "ppg": 1.0, "rpg": 1.0, "apg": 1.0, "spg": 1.0, "bpg": 1.0,
            "fg": 0.8, "threeP": 2.0, "ft": 1.5, "ato": 1.5,
            "height": 1.5, "weight": 0.8, "ws": 1.5, "ath": 2.0,
            "age": 1.2, "mpg": 1.5,
            "bpm": 1.0, "obpm": 1.0, "dbpm": 0.5, "fta": 0.5,
            "stl_per": 0.5, "usg": 0.5,
        }

    # Apply archetype weight modifiers if provided
    if weight_mods:
        for stat, mult in weight_mods.items():
            if stat in base_weights:
                base_weights[stat] = base_weights[stat] * mult

    # Team strength modifiers (quadrant-based)
    quad_mod_a = QUADRANT_MODIFIERS.get(player_a.get("quadrant", "Q1"), 1.0)
    quad_mod_b = QUADRANT_MODIFIERS.get(player_b.get("quadrant", "Q1"), 1.0)

    # Per-30 normalization
    stats_a = {k: player_a.get(k, 0) for k in ["ppg", "rpg", "apg", "spg", "bpg", "tpg"]}
    per30_a = normalize_to_30(stats_a, player_a.get("mpg", 30))

    b_stats = player_b.get("stats", {})
    stats_b = {k: b_stats.get(k, 0) for k in ["ppg", "rpg", "apg", "spg", "bpg", "tpg"]}
    per30_b = normalize_to_30(stats_b, b_stats.get("mpg", 30))

    # Adjusted stats: team strength modifier on scoring only
    adj_a = {"ppg": per30_a["ppg"] * quad_mod_a, "rpg": per30_a["rpg"],
             "apg": per30_a["apg"], "spg": per30_a["spg"], "bpg": per30_a["bpg"]}
    adj_b = {"ppg": per30_b["ppg"] * quad_mod_b, "rpg": per30_b["rpg"],
             "apg": per30_b["apg"], "spg": per30_b["spg"], "bpg": per30_b["bpg"]}

    # ATO
    tpg_a = player_a.get("tpg", 0)
    input_ato = player_a.get("apg", 0) / tpg_a if tpg_a > 0 else player_a.get("apg", 0)
    tpg_b = b_stats.get("tpg", 0)
    db_ato = b_stats.get("apg", 0) / tpg_b if tpg_b > 0 else b_stats.get("apg", 0)

    # Identity map
    pos_avg = pos_avgs.get(player_a.get("pos", "W"), pos_avgs.get("W", POSITIONAL_AVGS.get("W", {})))
    identity_map = calculate_identity_map(adj_a, player_a, input_ato, pos_avg)

    # Wingspan multiplier (disabled in V3 — all wingspan data is estimated h+4)
    ws_a = player_a.get("ws", player_a.get("h", 78) + 4)
    h_a = player_a.get("h", 78)
    ws_multiplier = 1.0 if use_v3 else (2.5 if (h_a > 0 and ws_a / h_a >= 1.06) else 1.0)

    # Defensive specialist clause
    ppg_weight = base_weights.get("ppg", 1.0) * identity_map["ppg"]
    stocks = adj_a["spg"] + adj_a["bpg"]
    if stocks > 2.5 and adj_a["ppg"] < 10.0:
        ppg_weight = 0.3

    # Build dynamic weights
    # Weight disabled — all DB players have placeholder 200 lbs (no real data)
    # Athleticism partially available — ~550 players have real ratings
    dynamic_weights = {
        "ppg": ppg_weight,
        "rpg": base_weights.get("rpg", 0.8) * identity_map["rpg"],
        "apg": base_weights.get("apg", 0.8) * identity_map["apg"],
        "spg": base_weights.get("spg", 1.8) * identity_map["spg"],
        "bpg": base_weights.get("bpg", 0.5) * identity_map["bpg"],
        "fg": base_weights.get("fg", 0.5) * get_outlier_multiplier(player_a.get("fg", 45), pos_avg.get("fg", 45)),
        "threeP": base_weights.get("threeP", 0.5) * identity_map["threeP"],
        "ft": base_weights.get("ft", 0.4) * identity_map["ft"],
        "ato": base_weights.get("ato", 0.8) * identity_map["ato"],
        "height": base_weights.get("height", 1.5),
        "weight": 0,  # disabled — placeholder data (all 200 lbs)
        "ws": base_weights.get("ws", 1.5) * ws_multiplier,
        "age": base_weights.get("age", 1.2),
        "mpg": base_weights.get("mpg", 1.0),
        # Advanced stats
        "bpm": base_weights.get("bpm", 2.5),
        "obpm": base_weights.get("obpm", 2.0),
        "dbpm": base_weights.get("dbpm", 1.0),
        "fta_pg": base_weights.get("fta_pg", 3.5),
        "stl_per": base_weights.get("stl_per", 1.5),
        "usg": base_weights.get("usg", 1.0),
        # New V4 stats
        "ftr": base_weights.get("ftr", 2.5),
        "rim_pct": base_weights.get("rim_pct", 2.0),
        "tpa": base_weights.get("tpa", 0.3),
    }

    # ---- PENALTIES (scaled down, capped) ----
    # Penalties answer: "should these two players even be compared?"
    # They should NOT predict tier — just filter bad comps.
    penalty = 0
    penalty_reasons = []

    pos_map = {"G": 0, "W": 1, "B": 2}
    pos_a = pos_map.get(player_a.get("pos", "W"), 1)
    pos_b = pos_map.get(player_b.get("pos", "W"), 1)
    pos_diff = abs(pos_a - pos_b)

    pos_penalty = 0
    if pos_diff == 2:
        pos_penalty = 15
    elif pos_diff == 1:
        pos_penalty = 5
    # Unicorn exceptions: passing big can match guards, rebounding guard can match wings
    if player_a.get("pos") == "B" and adj_a["apg"] > 4.0 and player_b.get("pos") in ("G", "W"):
        pos_penalty = 0
    if player_a.get("pos") == "G" and adj_a["rpg"] > 7.0 and player_b.get("pos") in ("W", "B"):
        pos_penalty = 0
    if pos_penalty > 0:
        penalty += pos_penalty
        penalty_reasons.append(f"Position gap ({pos_penalty})")

    # Chucker: high volume + bad efficiency vs efficient player
    if adj_a["ppg"] > 18.0 and player_a.get("fg", 45) < 42.0 and b_stats.get("fg", 45) > 48.0:
        penalty += 8
        penalty_reasons.append("Chucker vs efficient")

    # Broken shot: really bad FT shooter vs good one
    if player_a.get("ft", 70) < 55.0 and b_stats.get("ft", 70) > 72.0:
        penalty += 8
        penalty_reasons.append("Broken shot mismatch")

    # Usage gap: low-usage player matched to go-to scorer
    input_usage = adj_a["ppg"] + adj_a["apg"]
    match_usage = adj_b["ppg"] + adj_b["apg"]
    if input_usage < 12.0 and match_usage > 25.0:
        penalty += 8
        penalty_reasons.append("Usage gap")

    # Height mismatch (>4 inches = different player type)
    h_b = player_b.get("h", 78)
    if abs(h_a - h_b) > 4:
        penalty += 10
        penalty_reasons.append(f"Height mismatch ({abs(h_a - h_b)}\")")

    # Wingspan mismatch — DISABLED in V3 (all ws = h+4, so this just duplicates height penalty)
    ws_b = player_b.get("ws", h_b + 4)

    # Shot volume: good % on low attempts vs high-volume efficient
    fg_a = player_a.get("fg", 45)
    fg_b = b_stats.get("fg", 45)
    if fg_a > 50 and adj_a["ppg"] < 10 and fg_b > 50 and adj_b["ppg"] > 18:
        penalty += 5
        penalty_reasons.append("Low-volume efficiency mismatch")

    # 3PT archetype mismatch (sniper vs non-shooter)
    three_a = player_a.get("threeP", 33)
    three_b = b_stats.get("threeP", 33)
    if (three_a > 40.0 and three_b < 28.0) or (three_a < 25.0 and three_b > 40.0):
        penalty += 5
        penalty_reasons.append("Shooting archetype mismatch")

    # Class year: handled via age weight in distance calc (V3: weight=2.13).
    # Removed separate gap penalty to avoid double-counting.

    # Cap total penalty
    penalty = min(penalty, MAX_PENALTY)

    # Unicorn traits and star signals (informational, not used in distance)
    prospect_unicorns = detect_unicorn_traits(player_a, pos_avg)
    prospect_signals, prospect_signal_tags = count_star_signals(player_a)

    # ---- DISTANCE CALCULATION ----
    def get_a(key):
        return player_a.get(key, 0)

    def get_b(key):
        return b_stats.get(key, 0)

    diffs = {}
    # Core counting stats (adjusted) — range-normalized
    diffs["ppg"] = (range_normalize(adj_a["ppg"], "ppg") - range_normalize(adj_b["ppg"], "ppg")) ** 2 * dynamic_weights["ppg"]
    diffs["rpg"] = (range_normalize(adj_a["rpg"], "rpg") - range_normalize(adj_b["rpg"], "rpg")) ** 2 * dynamic_weights["rpg"]
    diffs["apg"] = (range_normalize(adj_a["apg"], "apg") - range_normalize(adj_b["apg"], "apg")) ** 2 * dynamic_weights["apg"]
    diffs["spg"] = (range_normalize(adj_a["spg"], "spg") - range_normalize(adj_b["spg"], "spg")) ** 2 * dynamic_weights["spg"]
    diffs["bpg"] = (range_normalize(adj_a["bpg"], "bpg") - range_normalize(adj_b["bpg"], "bpg")) ** 2 * dynamic_weights["bpg"]

    # Shooting percentages
    diffs["fg"] = (range_normalize(get_a("fg"), "fg") - range_normalize(get_b("fg"), "fg")) ** 2 * dynamic_weights["fg"]
    diffs["threeP"] = (range_normalize(get_a("threeP"), "threeP") - range_normalize(get_b("threeP"), "threeP")) ** 2 * dynamic_weights["threeP"]
    diffs["ft"] = (range_normalize(get_a("ft"), "ft") - range_normalize(get_b("ft"), "ft")) ** 2 * dynamic_weights["ft"]
    diffs["ato"] = (range_normalize(input_ato, "ato") - range_normalize(db_ato, "ato")) ** 2 * dynamic_weights["ato"]

    # Physical — range-normalized (4" height gap = 25%, not 5%)
    diffs["height"] = (range_normalize(h_a, "height") - range_normalize(h_b, "height")) ** 2 * dynamic_weights["height"]
    diffs["weight"] = (range_normalize(get_a("w"), "weight") - range_normalize(player_b.get("w", 200), "weight")) ** 2 * dynamic_weights["weight"]
    diffs["ws"] = (range_normalize(ws_a, "ws") - range_normalize(ws_b, "ws")) ** 2 * dynamic_weights["ws"]
    diffs["age"] = (range_normalize(get_a("age"), "age") - range_normalize(player_b.get("age", 4), "age")) ** 2 * dynamic_weights["age"]
    diffs["mpg"] = (range_normalize(get_a("mpg"), "mpg") - range_normalize(get_b("mpg"), "mpg")) ** 2 * dynamic_weights["mpg"]

    # Advanced stats (only compare if both players have them)
    # When prospect has a stat but comp doesn't, assume comp is at range midpoint
    # (0.5 normalized). This gives meaningful distance — a prospect with elite BPM
    # should be farther from an unknown-BPM comp than from a comp with avg BPM.
    for stat in ["bpm", "obpm", "dbpm", "stl_per", "usg"]:
        val_a = get_a(stat)
        val_b = get_b(stat)
        w = dynamic_weights.get(stat, 0.5)
        if val_a != 0 and val_b != 0:
            diffs[stat] = (range_normalize(val_a, stat) - range_normalize(val_b, stat)) ** 2 * w
        elif val_a != 0 and val_b == 0:
            # Comp has no data — treat as range midpoint (0.5)
            diffs[stat] = (range_normalize(val_a, stat) - 0.5) ** 2 * w * 0.5

    # FTA per game (already stored as per-game)
    fta_pg_a = get_a("fta")
    fta_pg_b = get_b("fta")
    w_fta = dynamic_weights.get("fta_pg", 0.5)
    if fta_pg_a != 0 and fta_pg_b != 0:
        diffs["fta_pg"] = (range_normalize(fta_pg_a, "fta_pg") - range_normalize(fta_pg_b, "fta_pg")) ** 2 * w_fta
    elif fta_pg_a != 0 and fta_pg_b == 0:
        diffs["fta_pg"] = (range_normalize(fta_pg_a, "fta_pg") - 0.5) ** 2 * w_fta * 0.5

    # New V4 stats: FTR, rim_pct, TPA
    for stat in ["ftr", "rim_pct", "tpa"]:
        val_a = get_a(stat)
        val_b = get_b(stat)
        w = dynamic_weights.get(stat, 0.5)
        if val_a != 0 and val_b != 0:
            diffs[stat] = (range_normalize(val_a, stat) - range_normalize(val_b, stat)) ** 2 * w
        elif val_a != 0 and val_b == 0:
            diffs[stat] = (range_normalize(val_a, stat) - 0.5) ** 2 * w * 0.5

    raw_dist = math.sqrt(sum(diffs.values()))
    max_dist = 6.0  # Lower = more spread. Range-norm produces larger diffs.
    similarity = max(0, 100 - (raw_dist / max_dist * 100))
    # Apply capped penalty as percentage-point deduction
    similarity = max(0, similarity - penalty)

    return {
        "score": round(similarity, 1),
        "weights": dynamic_weights,
        "input_ato": round(input_ato, 2),
        "db_ato": round(db_ato, 2),
        "identity_map": identity_map,
        "penalty": penalty,
        "penalty_reasons": penalty_reasons,
        "diffs": {k: round(v, 4) for k, v in diffs.items()},
        "star_signals": prospect_signals,
        "star_signal_tags": prospect_signal_tags,
        "unicorn_traits": prospect_unicorns,
    }


def find_top_matches(prospect, player_db, pos_avgs=None, weights_override=None, top_n=5, use_v2=True, use_v3=False):
    """Find the top N most similar players from the database."""
    results = []
    yr_lo, yr_hi = COMP_YEAR_RANGE
    for player in player_db:
        if player.get("name", "") in EXCLUDE_PLAYERS:
            continue
        draft_yr = player.get("draft_year") or 0
        if draft_yr < yr_lo or draft_yr > yr_hi:
            continue
        s = player.get("stats", {})
        if (s.get("gp", 30) or 30) < 25 or (s.get("mpg", 30) or 30) < 20:
            continue
        sim = calculate_similarity(prospect, player, pos_avgs, use_v2, use_v3=use_v3)
        results.append({"player": player, "similarity": sim})

    results.sort(key=lambda x: x["similarity"]["score"], reverse=True)
    return results[:top_n]


def find_archetype_matches(prospect, player_db, pos_avgs=None, top_n=10, use_v2=True, anchor_tier=None, use_v3=False):
    """V4: Find top comps WITHIN the prospect's archetype using archetype-specific weights.

    Args:
      anchor_tier: model-predicted tier used to anchor ceiling/floor comp selection.
                   If None, falls back to similarity-weighted tier from top 5.

    Returns dict with:
      - archetype/secondary/arch_confidence
      - matches: top N same-archetype comps
      - predicted_tier: the anchor tier used for ceiling/floor
      - closest_comp/ceiling_comp/floor_comp: named player comps
    """
    # Classify the prospect
    archetype, arch_score, secondary = classify_archetype(prospect)
    weight_mods = ARCHETYPE_WEIGHT_MODS.get(archetype, {})

    # Pre-classify all DB players and filter to same archetype
    # Skip excluded players, out-of-range years, and small samples
    same_arch = []
    yr_lo, yr_hi = COMP_YEAR_RANGE
    for player in player_db:
        if not player.get("has_college_stats"):
            continue
        if player.get("name", "") in EXCLUDE_PLAYERS:
            continue
        draft_yr = player.get("draft_year") or 0
        if draft_yr < yr_lo or draft_yr > yr_hi:
            continue
        s = player.get("stats", {})
        if (s.get("gp", 30) or 30) < 25 or (s.get("mpg", 30) or 30) < 20:
            continue
        p_arch, _, _ = classify_archetype(player)
        if p_arch == archetype:
            same_arch.append(player)

    # Run similarity with archetype-specific weights
    results = []
    for player in same_arch:
        sim = calculate_similarity(prospect, player, pos_avgs, use_v2, weight_mods=weight_mods, use_v3=use_v3)
        results.append({"player": player, "similarity": sim})

    results.sort(key=lambda x: x["similarity"]["score"], reverse=True)
    top_matches = results[:top_n]

    # Closest comp: highest-similarity player (always exists if results non-empty)
    closest_comp = results[0] if results else None

    # Use model-predicted tier as the anchor; fall back to top-match tier if not provided
    if anchor_tier is not None:
        pred = anchor_tier
    elif closest_comp:
        pred = closest_comp["player"]["tier"]
    else:
        pred = 4

    # Ceiling comp: best-similarity player 1-2 tiers better than model prediction
    ceiling_comp = None
    ceil_target_lo = max(1, pred - 2)
    ceil_target_hi = pred - 1
    if ceil_target_hi >= ceil_target_lo:
        for m in results:
            if ceil_target_lo <= m["player"]["tier"] <= ceil_target_hi and m["similarity"]["score"] >= 30:
                ceiling_comp = m
                break
    # Fallback: any comp with tier <= pred (at least as good), best similarity first
    if ceiling_comp is None:
        for m in results:
            if m["player"]["tier"] <= pred and m["similarity"]["score"] >= 30:
                ceiling_comp = m
                break
    # Final fallback: use closest comp
    if ceiling_comp is None:
        ceiling_comp = closest_comp

    # Floor comp: best-similarity player 1-2 tiers worse than model prediction
    floor_comp = None
    floor_target_lo = pred + 1
    floor_target_hi = min(5, pred + 2)
    if floor_target_hi >= floor_target_lo:
        for m in results:
            if floor_target_lo <= m["player"]["tier"] <= floor_target_hi and m["similarity"]["score"] >= 30:
                floor_comp = m
                break
    # Fallback: any comp with tier >= pred (at least as bad), best similarity first
    if floor_comp is None:
        for m in results:
            if m["player"]["tier"] >= pred and m["similarity"]["score"] >= 30:
                floor_comp = m
                break
    # Final fallback: use closest comp
    if floor_comp is None:
        floor_comp = closest_comp

    # Sanity check: ceiling must never be a worse tier than floor
    if ceiling_comp and floor_comp and ceiling_comp["player"]["tier"] > floor_comp["player"]["tier"]:
        ceiling_comp, floor_comp = floor_comp, ceiling_comp

    return {
        "archetype": archetype,
        "secondary": secondary,
        "arch_confidence": arch_score,
        "matches": top_matches,
        "predicted_tier": pred,
        "closest_comp": closest_comp,
        "ceiling_comp": ceiling_comp,
        "ceiling_tier": ceiling_comp["player"]["tier"] if ceiling_comp else pred,
        "floor_comp": floor_comp,
        "floor_tier": floor_comp["player"]["tier"] if floor_comp else pred,
        "pool_size": len(same_arch),
    }


def load_player_db():
    """Load player database and positional averages from processed files."""
    with open(PLAYER_DB_PATH) as f:
        player_db = json.load(f)

    pos_avgs = POSITIONAL_AVGS
    if os.path.exists(POSITIONAL_AVGS_PATH):
        with open(POSITIONAL_AVGS_PATH) as f:
            pos_avgs = json.load(f)

    return player_db, pos_avgs
