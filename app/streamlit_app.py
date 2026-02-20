"""NBAScoutPro — Prospect Translation Report.

Projection based on position-adjusted statistical profile and team context.
Style similarity does not imply identical NBA outcome.
"""
import sys
import os
import json
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go

from config import (
    POSITIONAL_AVGS, LEVEL_MODIFIERS, QUADRANT_MODIFIERS, TIER_LABELS,
    PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, MAX_STATS, DATA_DIR, PROCESSED_DIR,
    STAR_SIGNAL_THRESHOLDS,
)
from app.similarity import (
    find_archetype_matches, classify_archetype,
    count_star_signals, detect_unicorn_traits, predict_tier,
)

PROSPECTS_PATH = os.path.join(DATA_DIR, "prospects.json")
DRAFT_SIMS_PATH = os.path.join(PROCESSED_DIR, "draft_simulations.json")

st.set_page_config(page_title="NBAScoutPro", page_icon="\U0001f3c0", layout="wide")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_data():
    with open(PLAYER_DB_PATH) as f:
        player_db = json.load(f)

    pos_avgs = POSITIONAL_AVGS
    if os.path.exists(POSITIONAL_AVGS_PATH):
        with open(POSITIONAL_AVGS_PATH) as f:
            pos_avgs = json.load(f)

    prospects = []
    if os.path.exists(PROSPECTS_PATH):
        with open(PROSPECTS_PATH) as f:
            prospects = json.load(f)

    draft_sims = {}
    if os.path.exists(DRAFT_SIMS_PATH):
        with open(DRAFT_SIMS_PATH) as f:
            draft_sims = json.load(f)

    return player_db, pos_avgs, prospects, draft_sims


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

TIER_COLORS = {
    1: "#FFD700",  # Gold
    2: "#C0C0C0",  # Silver
    3: "#4CAF50",  # Green
    4: "#FF9800",  # Orange
    5: "#F44336",  # Red
    6: "#9E9E9E",  # Gray (TBD)
}

ARCHETYPE_COLORS = {
    "Scoring Guard": "#E53935",
    "Playmaking Guard": "#1E88E5",
    "3&D Wing": "#43A047",
    "Scoring Wing": "#FB8C00",
    "Skilled Big": "#8E24AA",
    "Athletic Big": "#6D4C41",
}

STAR_SIGNAL_LABELS = {
    "bpm": ("BPM", STAR_SIGNAL_THRESHOLDS.get("bpm", 7.6)),
    "obpm": ("Off BPM", STAR_SIGNAL_THRESHOLDS.get("obpm", 6.9)),
    "fta": ("FTA Rate", STAR_SIGNAL_THRESHOLDS.get("fta", 4.7)),
    "spg": ("Steals", STAR_SIGNAL_THRESHOLDS.get("spg", 1.4)),
    "stl_per": ("Steal %", STAR_SIGNAL_THRESHOLDS.get("stl_per", 2.3)),
    "usg": ("Usage", STAR_SIGNAL_THRESHOLDS.get("usg", 25.9)),
    "ft": ("FT%", STAR_SIGNAL_THRESHOLDS.get("ft", 81.3)),
}

POS_LABELS = {"G": "Guard", "W": "Wing", "B": "Big"}

ROLE_DESCRIPTORS = {
    (1, "G"): "Franchise-level guard",
    (1, "W"): "Franchise-level wing",
    (1, "B"): "Franchise-level big",
    (2, "G"): "Perennial All-Star guard",
    (2, "W"): "Perennial All-Star wing",
    (2, "B"): "Perennial All-Star big",
    (3, "G"): "Quality starting guard",
    (3, "W"): "Quality starting wing",
    (3, "B"): "Quality starting big",
    (4, "G"): "Rotation guard",
    (4, "W"): "Rotation wing",
    (4, "B"): "Rotation big",
    (5, "G"): "Limited NBA tenure",
    (5, "W"): "Limited NBA tenure",
    (5, "B"): "Limited NBA tenure",
}


def get_role_descriptor(player):
    tier = player.get("tier", 5)
    pos = player.get("pos", "W")
    return ROLE_DESCRIPTORS.get((tier, pos), TIER_LABELS.get(tier, "Unknown"))


def compute_projection_stability(matches):
    """Determine how tightly clustered the comparison group is."""
    if not matches or len(matches) < 3:
        return "High Variance Outcome"
    tiers = [m["player"]["tier"] for m in matches[:8]]
    mean_t = sum(tiers) / len(tiers)
    var = sum((t - mean_t) ** 2 for t in tiers) / len(tiers)
    std = math.sqrt(var)
    if std < 0.7:
        return "Stable Projection"
    elif std < 1.2:
        return "Moderate Variance"
    else:
        return "High Variance Outcome"


def build_radar_chart(prospect, matches, stat_keys=None):
    if stat_keys is None:
        stat_keys = ["ppg", "rpg", "apg", "spg", "bpg", "fg", "threeP", "ft"]

    labels = [k.upper() for k in stat_keys]
    maxes = {k: MAX_STATS.get(k, 1) for k in stat_keys}

    def norm_vals(stats_dict):
        return [min(100, (stats_dict.get(k, 0) / maxes.get(k, 1)) * 100) for k in stat_keys]

    fig = go.Figure()

    prospect_vals = norm_vals(prospect)
    fig.add_trace(go.Scatterpolar(
        r=prospect_vals + [prospect_vals[0]],
        theta=labels + [labels[0]],
        name="Prospect",
        fill="toself",
        opacity=0.3,
        line=dict(color="red", width=3),
    ))

    colors = ["#1f77b4", "#2ca02c", "#ff7f0e"]
    for i, match in enumerate(matches[:3]):
        p = match["player"]
        vals = norm_vals(p["stats"])
        score = match["similarity"]["score"]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=labels + [labels[0]],
            name=f"{p['name']} ({score:.0f}%)",
            fill="toself",
            opacity=0.15,
            line=dict(color=colors[i % len(colors)], width=2),
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        height=450,
        margin=dict(l=60, r=60, t=40, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main():
    player_db, pos_avgs, prospects, draft_sims = load_data()

    # ---- HEADER ----
    st.markdown("# Prospect Translation Report")
    st.caption(
        "Projection based on position-adjusted statistical profile and team context. "
        "Style similarity does not imply identical NBA outcome."
    )

    pos_list = ["G", "W", "B"]
    quadrant_list = list(QUADRANT_MODIFIERS.keys())

    # Initialize session state defaults (avoids "default vs session state" warning)
    _defaults = {
        "inp_name": "Draft Prospect", "inp_h_ft": 6, "inp_h_in": 3,
        "inp_age": "Fr", "inp_pos": "G", "inp_quadrant": "Q1",
        "inp_ppg": 15.0, "inp_rpg": 4.5, "inp_apg": 3.5,
        "inp_spg": 1.2, "inp_bpg": 0.4, "inp_tpg": 2.5,
        "inp_fg": 45.0, "inp_3p": 35.0, "inp_ft": 75.0,
        "inp_mpg": 30.0, "inp_tpa": 0.0,
        "inp_bpm": 0.0, "inp_obpm": 0.0, "inp_dbpm": 0.0,
        "inp_fta": 0.0, "inp_stl_per": 0.0, "inp_usg": 0.0,
        "inp_ftr": 0.0, "inp_rim_pct": 0.0,
    }
    for k, v in _defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    def on_prospect_change():
        sel = st.session_state.prospect_select
        if sel == "Custom":
            return
        p = next((px for px in prospects if px["name"] == sel), None)
        if not p:
            return
        field_map = {
            "inp_name": "name", "inp_h_ft": "h_ft", "inp_h_in": "h_in",
            "inp_age": "age",
            "inp_ppg": "ppg", "inp_rpg": "rpg", "inp_apg": "apg",
            "inp_spg": "spg", "inp_bpg": "bpg", "inp_tpg": "tpg",
            "inp_fg": "fg", "inp_3p": "threeP", "inp_ft": "ft",
            "inp_mpg": "mpg",
            "inp_bpm": "bpm", "inp_obpm": "obpm", "inp_dbpm": "dbpm",
            "inp_fta": "fta", "inp_stl_per": "stl_per", "inp_usg": "usg",
        }
        for widget_key, json_key in field_map.items():
            if json_key in p:
                st.session_state[widget_key] = p[json_key]
        if p.get("pos") in pos_list:
            st.session_state["inp_pos"] = p["pos"]
        if p.get("quadrant") in quadrant_list:
            st.session_state["inp_quadrant"] = p["quadrant"]
        elif p.get("level") in list(LEVEL_MODIFIERS.keys()):
            level_to_quad = {"High Major": "Q1", "Mid Major": "Q2", "Low Major": "Q4"}
            st.session_state["inp_quadrant"] = level_to_quad.get(p["level"], "Q1")

    # ---- SIDEBAR ----
    with st.sidebar:
        st.header("Prospect Profile")

        complete = [p for p in prospects if p.get("bpm", 0) != 0 and p.get("usg", 0) != 0]
        prospect_names = ["Custom"] + [p["name"] for p in complete]
        st.selectbox("Load Prospect", prospect_names,
                     key="prospect_select", on_change=on_prospect_change)

        name = st.text_input("Name", key="inp_name")
        col1, col2 = st.columns(2)
        with col1:
            position = st.selectbox("Position", pos_list, key="inp_pos")
        with col2:
            quadrant = st.selectbox("Team Strength", quadrant_list,
                                    key="inp_quadrant",
                                    help="Q1=Top 50, Q2=51-100, Q3=101-200, Q4=200+")

        st.subheader("Physical")
        c1, c2 = st.columns(2)
        with c1:
            h_ft = st.number_input("Height (ft)", 5, 7, key="inp_h_ft")
        with c2:
            h_in = st.number_input("Height (in)", 0, 11, key="inp_h_in")

        height = h_ft * 12 + h_in

        c1, c2 = st.columns(2)
        with c1:
            class_yr_list = ["Fr", "So", "Jr", "Sr"]
            class_yr_map = {"Fr": 1, "So": 2, "Jr": 3, "Sr": 4}
            class_yr_sel = st.selectbox("Class Year", class_yr_list, key="inp_age")
            age = class_yr_map[class_yr_sel]
        with c2:
            pass

        st.subheader("Stats (Per Game)")
        c1, c2, c3 = st.columns(3)
        with c1:
            ppg = st.number_input("PPG", 0.0, 40.0, step=0.1, format="%.1f", key="inp_ppg")
            spg = st.number_input("SPG", 0.0, 5.0, step=0.1, format="%.1f", key="inp_spg")
        with c2:
            rpg = st.number_input("RPG", 0.0, 20.0, step=0.1, format="%.1f", key="inp_rpg")
            bpg = st.number_input("BPG", 0.0, 6.0, step=0.1, format="%.1f", key="inp_bpg")
        with c3:
            apg = st.number_input("APG", 0.0, 15.0, step=0.1, format="%.1f", key="inp_apg")
            tpg = st.number_input("TPG", 0.0, 8.0, step=0.1, format="%.1f", key="inp_tpg")

        st.subheader("Shooting & Minutes")
        c1, c2, c3 = st.columns(3)
        with c1:
            fg = st.number_input("eFG%", 20.0, 75.0, step=0.1, format="%.1f", key="inp_fg")
        with c2:
            threeP = st.number_input("3P%", 0.0, 55.0, step=0.1, format="%.1f", key="inp_3p")
        with c3:
            ft = st.number_input("FT%", 30.0, 100.0, step=0.1, format="%.1f", key="inp_ft")

        c1, c2 = st.columns(2)
        with c1:
            mpg = st.number_input("MPG", 10.0, 42.0, step=0.1, format="%.1f", key="inp_mpg")
        with c2:
            tpa = st.number_input("3PA/G", 0.0, 12.0, step=0.1, format="%.1f",
                                  help="3-point attempts per game", key="inp_tpa")

        st.subheader("Advanced Stats")
        st.caption("These stats drive the prediction model. Add them for full accuracy.")
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            bpm = st.number_input("BPM", -10.0, 20.0, step=0.1, format="%.1f",
                                  help="Box Plus/Minus", key="inp_bpm")
            obpm = st.number_input("OBPM", -10.0, 15.0, step=0.1, format="%.1f",
                                   help="Offensive BPM", key="inp_obpm")
            fta = st.number_input("FTA/G", 0.0, 12.0, step=0.1, format="%.1f",
                                  help="Free throw attempts per game", key="inp_fta")
        with ac2:
            stl_per = st.number_input("Steal %", 0.0, 6.0, step=0.1, format="%.1f", key="inp_stl_per")
            usg = st.number_input("USG%", 0.0, 45.0, step=0.1, format="%.1f",
                                  help="Usage rate", key="inp_usg")
            dbpm = st.number_input("DBPM", -8.0, 12.0, step=0.1, format="%.1f",
                                   help="Defensive BPM", key="inp_dbpm")
        with ac3:
            ftr = st.number_input("FT Rate", 0.0, 70.0, step=0.1, format="%.1f",
                                  help="FTA/FGA ratio", key="inp_ftr")
            rim_pct = st.number_input("Rim %", 0.0, 90.0, step=0.1, format="%.1f",
                                      help="Shooting % at the rim", key="inp_rim_pct")

    # Build prospect dict
    prospect = {
        "name": name, "pos": position, "h": height, "w": 200,
        "ws": height + 4, "age": age, "quadrant": quadrant,
        "ath": 0,
        "ppg": ppg, "rpg": rpg, "apg": apg, "spg": spg, "bpg": bpg,
        "fg": fg, "threeP": threeP, "ft": ft, "tpg": tpg, "mpg": mpg,
        "bpm": bpm, "obpm": obpm, "dbpm": dbpm, "fta": fta,
        "stl_per": stl_per, "usg": usg,
        "ftr": ftr, "rim_pct": rim_pct, "tpa": tpa,
    }

    # ---- RUN MODEL ----
    prediction = predict_tier(prospect, pos_avgs)
    arch_result = find_archetype_matches(
        prospect, player_db, pos_avgs, top_n=10,
        anchor_tier=prediction["tier"], use_v3=True,
    )

    archetype = arch_result["archetype"]
    ceil_comp = arch_result["ceiling_comp"]
    floor_comp = arch_result["floor_comp"]
    closest_comp = arch_result["closest_comp"]
    matches = arch_result["matches"]
    pool_size = arch_result["pool_size"]

    pred_tier = prediction["tier"]
    pred_label = TIER_LABELS.get(pred_tier, "Unknown")
    pred_color = TIER_COLORS.get(pred_tier, "#888")

    # ---- ADVANCED STATS WARNING ----
    if not prediction["has_advanced_stats"]:
        st.warning("No advanced stats provided. Add BPM, OBPM, and FTA for full prediction accuracy.")

    # Compute stability once (used in Section 1)
    stability = compute_projection_stability(matches)
    stability_colors = {
        "Stable Projection": "#4CAF50",
        "Moderate Variance": "#FF9800",
        "High Variance Outcome": "#F44336",
    }
    stab_color = stability_colors.get(stability, "#888")

    arch_color = ARCHETYPE_COLORS.get(archetype, "#888")

    # ================================================================
    # SECTION 1: PLAYER IDENTITY + PROJECTED NBA OUTCOME
    # ================================================================
    st.markdown(
        f"<div style='padding:20px 24px; border-radius:10px; "
        f"border:2px solid {pred_color}; background:{pred_color}0D; "
        f"margin-bottom:12px;'>"
        # Player name
        f"<div style='font-size:1.5em; font-weight:bold; margin-bottom:6px;'>{name}</div>"
        # Archetype badge + Stability badge on same line
        f"<div style='margin-bottom:10px;'>"
        f"<span style='display:inline-block; padding:3px 10px; border-radius:12px; "
        f"font-size:0.8em; font-weight:600; color:white; background:{arch_color}; "
        f"margin-right:8px;'>{archetype}</span>"
        f"<span style='display:inline-block; padding:3px 10px; border-radius:12px; "
        f"font-size:0.8em; font-weight:600; color:{stab_color}; "
        f"border:1px solid {stab_color};'>{stability}</span>"
        f"</div>"
        # Tier prediction
        f"<div style='font-size:1.8em; font-weight:bold; color:{pred_color};'>"
        f"Projects as: {pred_label}</div>"
        # Star signals
        f"<div style='font-size:0.9em; color:#aaa; margin-top:6px;'>"
        f"{prediction['star_signals']} of {len(STAR_SIGNAL_LABELS)} historical star thresholds met"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.caption(
        "Projection based on historical outcomes of players with "
        "similar statistical profiles, adjusted for position and competition level."
    )

    # ================================================================
    # SECTION 2: HISTORICAL OUTCOME RANGE
    # ================================================================
    st.divider()
    st.markdown("### Historical Outcome Range")
    st.caption(
        "Among statistically similar college players, these represent "
        "the best and worst NBA careers that followed."
    )

    def _outcome_block(label, comp):
        if not comp:
            return (
                f"<div style='padding:10px 14px; margin:6px 0; "
                f"border-left:4px solid #555; background:#5550D; "
                f"border-radius:0 6px 6px 0;'>"
                f"<b>{label}:</b> No comparable player found</div>"
            )
        p = comp["player"]
        sim_score = comp["similarity"]["score"]
        t_color = TIER_COLORS.get(p["tier"], "#888")
        descriptor = get_role_descriptor(p)
        return (
            f"<div style='padding:12px 16px; margin:6px 0; "
            f"border-left:4px solid {t_color}; background:{t_color}0D; "
            f"border-radius:0 6px 6px 0;'>"
            f"<div style='font-size:0.8em; color:#888; margin-bottom:2px;'>"
            f"{label} &nbsp;·&nbsp; {sim_score:.0f}% statistical match</div>"
            f"<div style='font-size:1.15em; font-weight:bold; color:{t_color}; "
            f"margin:2px 0;'>{p['name']}</div>"
            f"<div style='font-size:0.9em; color:#aaa;'>{descriptor}</div>"
            f"</div>"
        )

    range_html = _outcome_block("Upper Historical Outcome", ceil_comp)
    range_html += _outcome_block("Lower Historical Outcome", floor_comp)
    st.markdown(range_html, unsafe_allow_html=True)

    st.caption(
        "These reflect the range of historical outcomes, not prediction certainty. "
        "The prospect will not necessarily match either outcome."
    )

    # ================================================================
    # SECTION 3: KEY INDICATORS DRIVING PROJECTION
    # ================================================================
    st.divider()
    st.markdown("### Key Indicators Driving Projection")

    reasons = prediction.get("reasons", [])
    # Separate positive/neutral reasons from concerns
    concerns = [r for r in reasons if r.startswith("Concern:") or r.startswith("Size concern:")]
    positives = [r for r in reasons if r not in concerns]

    if positives:
        for reason in positives[:5]:
            st.markdown(f"- {reason}")
    else:
        st.markdown("- No strong statistical signals detected")

    if concerns:
        st.markdown("**Areas of Concern**")
        for reason in concerns[:4]:
            # Strip the "Concern: " / "Size concern: " prefix for cleaner display
            clean = reason.split(": ", 1)[1] if ": " in reason else reason
            st.markdown(f"- {clean}")

    # ================================================================
    # SECTION 4: CLOSEST STATISTICAL STYLE MATCHES
    # ================================================================
    st.divider()
    st.markdown("### Closest Statistical Style Matches")
    st.caption(
        "These players had similar college statistical profiles. "
        "Similarity does not guarantee similar NBA outcome."
    )

    if matches:
        table_header = "| # | Player | Match | Archetype | Stat Line |"
        table_sep = "|:--|:---|:---:|:---|:---|"
        table_rows = [table_header, table_sep]
        for i, match in enumerate(matches[:10]):
            p = match["player"]
            sim = match["similarity"]
            s = p["stats"]
            arch_tag, _, _ = classify_archetype(p)
            stat_line = f"{s['ppg']:.1f}p / {s['rpg']:.1f}r / {s['apg']:.1f}a"
            table_rows.append(
                f"| {i+1} | **{p['name']}** | {sim['score']:.0f}% | {arch_tag} | {stat_line} |"
            )
        st.markdown("\n".join(table_rows))

    st.caption(
        f"Evaluated relative to the {POS_LABELS.get(position, 'Wing').lower()} position group."
    )

    # ================================================================
    # EXPANDED STATISTICAL COMPARISON (collapsible)
    # ================================================================
    if matches:
        with st.expander("Expanded Statistical Comparison", expanded=False):
            if closest_comp:
                comp_p = closest_comp["player"]
                comp_s = comp_p["stats"]
                comp_sim = closest_comp["similarity"]["score"]
                st.markdown(f"**{name} vs {comp_p['name']}** ({comp_sim:.0f}% match)")

                stat_compare = {
                    "PPG": "ppg", "RPG": "rpg", "APG": "apg",
                    "SPG": "spg", "BPG": "bpg",
                    "eFG%": "fg", "3P%": "threeP", "FT%": "ft",
                    "BPM": "bpm", "USG%": "usg",
                }

                header = f"| Stat | {name} | {comp_p['name']} |"
                sep = "|:---|:---:|:---:|"
                rows = [header, sep]
                for label, key in stat_compare.items():
                    p_val = prospect.get(key, 0)
                    c_val = comp_s.get(key, 0)
                    fmt = ".0f" if "%" in label else ".1f"
                    suffix = "%" if "%" in label else ""
                    rows.append(f"| **{label}** | {p_val:{fmt}}{suffix} | {c_val:{fmt}}{suffix} |")
                st.markdown("\n".join(rows))

            st.markdown("---")

            fig = build_radar_chart(prospect, matches)
            st.plotly_chart(fig, use_container_width=True)

    # ================================================================
    # PAST DRAFT SIMULATIONS (trust-building)
    # ================================================================
    if draft_sims:
        st.divider()
        st.markdown("### Model Validation: Past Draft Simulations")
        st.caption(
            "The model was run retroactively on every draft class from 2010-2021. "
            "Below is how the model would have ranked each class using only their "
            "college stats — no draft position or NBA data."
        )

        sim_years = sorted(draft_sims.keys(), reverse=True)
        for year in sim_years:
            players = draft_sims[year]
            n = len(players)

            with st.expander(f"{year} Draft  —  {n} players", expanded=False):
                header = "| Rank | Player |"
                sep = "|:---:|:---|"
                rows = [header, sep]
                for p in players:
                    rows.append(f"| {p['rank']} | {p['name']} |")
                st.markdown("\n".join(rows))

    # Footer
    st.divider()
    st.caption(
        "Metrics evaluated relative to position group (Guard / Wing / Big). "
        "Model uses archetype-filtered weighted Euclidean distance across "
        "advanced and counting stats."
    )


if __name__ == "__main__":
    main()
