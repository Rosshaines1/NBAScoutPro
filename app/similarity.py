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
    EXCLUDE_PLAYERS,
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
    """Predict NBA tier using validated rules from rule_lab.py (34.6% exact accuracy).

    Key improvements over V3:
      - Conference-adjusted BPM/OBPM (level_mod applied before scoring)
      - FTA per-game rate instead of raw season total
      - Position-dependent FT% (bigs can succeed with bad FT, guards can't)
      - "Athlete without skill" penalty (dunks + bad FT for G/W = bust signal)
      - Draft position as penalty only (lottery bonuses backfire)
      - Low-MPG + early pick bonus (teams see something stats don't)

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
    fg = player.get("fg", 45) or 45
    draft_pick = player.get("draft_pick", 0)
    pos = player.get("pos", "W")

    star_count, star_tags = count_star_signals(player)
    unicorns = detect_unicorn_traits(player, pos_avgs.get(pos, {}))

    score = 0.0
    reasons = []

    # --- Draft position: PENALTY ONLY, no bonus ---
    # Lottery bonuses backfire (boost lottery busts equally).
    # Prospects (no pick yet) default to 0 = neutral.
    if draft_pick and draft_pick > 0:
        if draft_pick <= 20:
            pass
        elif draft_pick <= 30:
            score -= 5
            reasons.append(f"Mid-1st discount (#{draft_pick})")
        elif draft_pick <= 45:
            score -= 15
            reasons.append(f"Late pick discount (#{draft_pick})")
        elif draft_pick <= 60:
            score -= 25
            reasons.append(f"Deep 2nd round discount (#{draft_pick})")

    # --- Conference-adjusted BPM/OBPM ---
    # BPM at weaker conferences is inflated by weaker competition.
    level_mod = LEVEL_MODIFIERS.get(level, 1.0)
    adj_bpm = bpm * level_mod
    adj_obpm = obpm * level_mod

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
    elif adj_bpm >= -2.0:
        score -= 3
    else:
        score -= 8
        reasons.append(f"Negative adj-BPM ({adj_bpm:.1f}) — bust signal")

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

    # --- Steals (consolidated: use STL_PER if available, else SPG) ---
    # Both r~0.11 and highly correlated — pick the better one, don't double-dip.
    if stl_per > 0:
        if stl_per >= 2.5:
            score += 8
            reasons.append(f"Elite steal rate ({stl_per:.1f}%)")
        elif stl_per >= 1.8:
            score += 4
    else:
        if spg >= 1.8:
            score += 8
            reasons.append(f"Elite steals ({spg:.1f})")
        elif spg >= 1.3:
            score += 4

    # --- Usage ---
    if usg > 0:
        if usg >= 30:
            score += 8
            reasons.append(f"High usage ({usg:.0f}%)")
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
    if pos == "G" and rpg >= 6:
        score += 4
        reasons.append(f"Rebounding guard ({rpg:.1f})")
    elif pos in ("W", "B") and rpg >= 9:
        score += 4
    elif rpg >= 5:
        score += 1

    # --- APG: removed (V3: r=0.008, essentially zero predictor) ---

    # --- Efficiency with volume ---
    if fg >= 52 and adj_ppg >= 15:
        score += 4
        reasons.append(f"Efficient scorer ({fg:.0f}% on {adj_ppg:.0f} PPG)")

    # --- Star signal count ---
    n_thresholds = len(STAR_SIGNAL_THRESHOLDS)
    if star_count >= 5:
        score += 12
        reasons.append(f"5+ star signals ({star_count}/{n_thresholds})")
    elif star_count >= 3:
        score += 6
        reasons.append(f"3+ star signals ({star_count}/{n_thresholds})")
    elif star_count >= 2:
        score += 2

    # --- Unicorn bonus ---
    if unicorns:
        score += 3 * len(unicorns)
        reasons.append(f"Unicorn traits: {', '.join(unicorns)}")

    # --- Level penalty ---
    if level == "Mid Major":
        score -= 5
    elif level == "Low Major":
        score -= 10
        reasons.append("Low Major discount")

    # --- Minutes context ---
    if mpg < 22:
        score -= 5
        reasons.append(f"Low minutes ({mpg:.0f} MPG)")

    # --- Low-MPG + early pick = potential signal ---
    # Freshmen on stacked teams play fewer minutes but get drafted high.
    if mpg < 25 and draft_pick > 0 and draft_pick <= 14:
        score += 8
        reasons.append(f"Early pick despite low minutes (potential)")

    # --- Missing advanced stats fallback ---
    # Players without BPM/OBPM/USG can't earn those star signals, so they're
    # structurally capped. Award proxy points from counting stats instead.
    has_advanced = any(player.get(s, 0) for s in ["bpm", "obpm", "fta", "stl_per", "usg"])
    if not has_advanced:
        proxy = 0
        # Elite scorer + good touch = proxy for high BPM/USG
        if adj_ppg >= 20 and ft_pct >= 78:
            proxy += 12
            reasons.append(f"Proxy: elite scorer + good FT ({adj_ppg:.0f} PPG, {ft_pct:.0f}% FT)")
        elif adj_ppg >= 16 and ft_pct >= 75:
            proxy += 6
            reasons.append(f"Proxy: strong scorer + decent FT")
        # High FTA rate even without other advanced stats
        if fta_pg >= 5.5:
            proxy += 8
            reasons.append(f"Proxy: high FTA rate ({fta_pg:.1f}/game)")
        elif fta_pg >= 3.5:
            proxy += 4
        # Elite steals per game = defensive instincts proxy
        if spg >= 1.8:
            proxy += 4
        score += proxy
        if proxy == 0 and score > 40:
            score = 40
            reasons.append("Capped: no advanced stats, no proxy signals")

    # --- Class year signal (V3: verified strong, r=-0.209) ---
    # Fr avg WS=23.7, So=19.1, Jr=16.9, Sr=10.5
    class_yr = player.get("age", 0) or 0
    if class_yr == 1:  # Freshman
        score += 5
        reasons.append("Freshman declaring (strong signal)")
    elif class_yr == 2:  # Sophomore
        score += 2
    elif class_yr == 4:  # Senior
        score -= 4
        reasons.append("Senior (weaker NBA outlook)")

    # Map score to tier (V3: retuned boundaries from clean 493-player dataset)
    if score >= 68:
        tier = 1
        confidence = min(95, 60 + score - 68)
    elif score >= 48:
        tier = 2
        confidence = 50 + (score - 48)
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

    # Level modifiers
    level_mod_a = LEVEL_MODIFIERS.get(player_a.get("level", "High Major"), 1.0)
    level_mod_b = LEVEL_MODIFIERS.get(player_b.get("level", "High Major"), 0.8)

    # Per-30 normalization
    stats_a = {k: player_a.get(k, 0) for k in ["ppg", "rpg", "apg", "spg", "bpg", "tpg"]}
    per30_a = normalize_to_30(stats_a, player_a.get("mpg", 30))

    b_stats = player_b.get("stats", {})
    stats_b = {k: b_stats.get(k, 0) for k in ["ppg", "rpg", "apg", "spg", "bpg", "tpg"]}
    per30_b = normalize_to_30(stats_b, b_stats.get("mpg", 30))

    # Adjusted stats: level modifier on scoring only
    adj_a = {"ppg": per30_a["ppg"] * level_mod_a, "rpg": per30_a["rpg"],
             "apg": per30_a["apg"], "spg": per30_a["spg"], "bpg": per30_a["bpg"]}
    adj_b = {"ppg": per30_b["ppg"] * level_mod_b, "rpg": per30_b["rpg"],
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
    for player in player_db:
        if player.get("name", "") in EXCLUDE_PLAYERS:
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
    # Skip excluded players (broken data) and small samples (gp<25 or mpg<20)
    same_arch = []
    for player in player_db:
        if not player.get("has_college_stats"):
            continue
        if player.get("name", "") in EXCLUDE_PLAYERS:
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
