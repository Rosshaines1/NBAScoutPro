"""NBAScoutPro V4 - Archetype-based scouting with floor/ceiling ranges.

Archetype classifier: "What type of player is this?"
Same-archetype comps: "Who are the most similar players of this type?"
Floor/ceiling: "What's the range of outcomes for this player type?"
Model prediction: "Where do the statistical signals point?"
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go

from config import (
    POSITIONAL_AVGS, LEVEL_MODIFIERS, QUADRANT_MODIFIERS, TIER_LABELS,
    PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, MAX_STATS, DATA_DIR,
    STAR_SIGNAL_THRESHOLDS,
)
from app.similarity import (
    find_archetype_matches, classify_archetype,
    count_star_signals, detect_unicorn_traits, predict_tier,
)

PROSPECTS_PATH = os.path.join(DATA_DIR, "prospects.json")

st.set_page_config(page_title="NBAScoutPro", page_icon="\U0001f3c0", layout="wide")


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

    return player_db, pos_avgs, prospects


def format_height(inches):
    feet = int(inches) // 12
    inc = int(inches) % 12
    return f"{feet}'{inc}\""


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


UNICORN_LABELS = {
    "rebounding_guard": "Rebounding Guard",
    "passing_big": "Passing Big",
    "stretch_big": "Stretch Big",
    "shot_blocking_wing": "Shot-Blocking Wing",
    "tall_playmaker": "Tall Playmaker",
    "pickpocket": "Pickpocket",
    "defensive_unicorn": "Defensive Unicorn",
}

STAR_SIGNAL_LABELS = {
    "bpm": ("BPM", STAR_SIGNAL_THRESHOLDS.get("bpm", 9.6)),
    "obpm": ("Off BPM", STAR_SIGNAL_THRESHOLDS.get("obpm", 7.1)),
    "fta": ("FTA Rate", STAR_SIGNAL_THRESHOLDS.get("fta", 4.6)),
    "spg": ("Steals", STAR_SIGNAL_THRESHOLDS.get("spg", 1.4)),
    "stl_per": ("Steal %", STAR_SIGNAL_THRESHOLDS.get("stl_per", 2.5)),
    "usg": ("Usage", STAR_SIGNAL_THRESHOLDS.get("usg", 25.9)),
    "ft": ("FT%", STAR_SIGNAL_THRESHOLDS.get("ft", 79.9)),
}

TIER_COLORS = {
    1: "#FFD700",  # Gold
    2: "#C0C0C0",  # Silver
    3: "#4CAF50",  # Green
    4: "#FF9800",  # Orange
    5: "#F44336",  # Red
}

ARCHETYPE_COLORS = {
    "Scoring Guard": "#E53935",
    "Playmaking Guard": "#1E88E5",
    "3&D Wing": "#43A047",
    "Scoring Wing": "#FB8C00",
    "Skilled Big": "#8E24AA",
    "Athletic Big": "#6D4C41",
}

ARCHETYPE_ICONS = {
    "Scoring Guard": "Bucket-getter who creates their own shot",
    "Playmaking Guard": "Pass-first floor general who controls tempo",
    "3&D Wing": "Shooting + defense role player, complementary piece",
    "Scoring Wing": "Primary scorer with size and versatility",
    "Skilled Big": "Big with shooting touch, offensive skill, and floor spacing",
    "Athletic Big": "Rim protector and rebounder, physicality over finesse",
}


def main():
    player_db, pos_avgs, prospects = load_data()

    st.title("NBAScoutPro")
    st.caption(f"Compare prospects against {len(player_db)} historical college players")

    pos_list = ["G", "W", "B"]
    quadrant_list = list(QUADRANT_MODIFIERS.keys())

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
            # Legacy fallback: map level to quadrant
            level_to_quad = {"High Major": "Q1", "Mid Major": "Q2", "Low Major": "Q4"}
            st.session_state["inp_quadrant"] = level_to_quad.get(p["level"], "Q1")

    # ---- SIDEBAR ----
    with st.sidebar:
        st.header("Prospect Profile")

        complete = [p for p in prospects if p.get("bpm", 0) != 0 and p.get("usg", 0) != 0]
        prospect_names = ["Custom"] + [p["name"] for p in complete]
        st.selectbox("Load Prospect", prospect_names,
                     key="prospect_select", on_change=on_prospect_change)

        name = st.text_input("Name", "Draft Prospect", key="inp_name")
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
            h_ft = st.number_input("Height (ft)", 5, 7, 6, key="inp_h_ft")
        with c2:
            h_in = st.number_input("Height (in)", 0, 11, 3, key="inp_h_in")

        height = h_ft * 12 + h_in

        c1, c2 = st.columns(2)
        with c1:
            class_yr_list = ["Fr", "So", "Jr", "Sr"]
            class_yr_map = {"Fr": 1, "So": 2, "Jr": 3, "Sr": 4}
            class_yr_sel = st.selectbox("Class Year", class_yr_list, index=0, key="inp_age")
            age = class_yr_map[class_yr_sel]
        with c2:
            pass  # Removed Athleticism — placeholder data only

        st.subheader("Stats (Per Game)")
        c1, c2, c3 = st.columns(3)
        with c1:
            ppg = st.number_input("PPG", 0.0, 40.0, 15.0, step=0.1, format="%.1f", key="inp_ppg")
            spg = st.number_input("SPG", 0.0, 5.0, 1.2, step=0.1, format="%.1f", key="inp_spg")
        with c2:
            rpg = st.number_input("RPG", 0.0, 20.0, 4.5, step=0.1, format="%.1f", key="inp_rpg")
            bpg = st.number_input("BPG", 0.0, 6.0, 0.4, step=0.1, format="%.1f", key="inp_bpg")
        with c3:
            apg = st.number_input("APG", 0.0, 15.0, 3.5, step=0.1, format="%.1f", key="inp_apg")
            tpg = st.number_input("TPG", 0.0, 8.0, 2.5, step=0.1, format="%.1f", key="inp_tpg")

        st.subheader("Shooting & Minutes")
        c1, c2, c3 = st.columns(3)
        with c1:
            fg = st.number_input("eFG%", 20.0, 75.0, 45.0, step=0.1, format="%.1f", key="inp_fg")
        with c2:
            threeP = st.number_input("3P%", 0.0, 55.0, 35.0, step=0.1, format="%.1f", key="inp_3p")
        with c3:
            ft = st.number_input("FT%", 30.0, 100.0, 75.0, step=0.1, format="%.1f", key="inp_ft")

        c1, c2 = st.columns(2)
        with c1:
            mpg = st.number_input("MPG", 10.0, 42.0, 30.0, step=0.1, format="%.1f", key="inp_mpg")
        with c2:
            tpa = st.number_input("3PA/G", 0.0, 12.0, 0.0, step=0.1, format="%.1f",
                                  help="3-point attempts per game (volume context for 3P%)", key="inp_tpa")

        st.subheader("Advanced Stats (Per Game)")
        st.caption("These stats drive the prediction model. Add them for full accuracy.")
        st.caption("(from basketball-reference or equivalent)")
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            bpm = st.number_input("BPM", -10.0, 20.0, 0.0, step=0.1, format="%.1f",
                                  help="Box Plus/Minus", key="inp_bpm")
            obpm = st.number_input("OBPM", -10.0, 15.0, 0.0, step=0.1, format="%.1f",
                                   help="Offensive BPM", key="inp_obpm")
            fta = st.number_input("FTA/G", 0.0, 12.0, 0.0, step=0.1, format="%.1f",
                                  help="Free throw attempts per game", key="inp_fta")
        with ac2:
            stl_per = st.number_input("Steal %", 0.0, 6.0, 0.0, step=0.1, format="%.1f", key="inp_stl_per")
            usg = st.number_input("USG%", 0.0, 45.0, 0.0, step=0.1, format="%.1f",
                                  help="Usage rate", key="inp_usg")
            dbpm = st.number_input("DBPM", -8.0, 12.0, 0.0, step=0.1, format="%.1f",
                                   help="Defensive BPM", key="inp_dbpm")
        with ac3:
            ftr = st.number_input("FT Rate", 0.0, 70.0, 0.0, step=0.1, format="%.1f",
                                  help="FTA/FGA — how often you get to the line", key="inp_ftr")
            rim_pct = st.number_input("Rim %", 0.0, 90.0, 0.0, step=0.1, format="%.1f",
                                      help="Shooting % at the rim", key="inp_rim_pct")

    # Build prospect dict (w/ws/ath set as internal defaults — no user input)
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

    # ---- RUN V4 SYSTEMS ----
    prediction = predict_tier(prospect, pos_avgs)
    arch_result = find_archetype_matches(prospect, player_db, pos_avgs, top_n=10, anchor_tier=prediction["tier"], use_v3=True)

    archetype = arch_result["archetype"]
    secondary = arch_result["secondary"]
    arch_color = ARCHETYPE_COLORS.get(archetype, "#888")
    arch_desc = ARCHETYPE_ICONS.get(archetype, "")

    ceil_tier = arch_result["ceiling_tier"]
    floor_tier = arch_result["floor_tier"]
    predicted_tier = arch_result["predicted_tier"]
    closest_comp = arch_result["closest_comp"]
    ceil_comp = arch_result["ceiling_comp"]
    floor_comp = arch_result["floor_comp"]
    matches = arch_result["matches"]
    pool_size = arch_result["pool_size"]

    pred_tier = prediction["tier"]
    pred_label = TIER_LABELS.get(pred_tier, "Unknown")
    pred_color = TIER_COLORS.get(pred_tier, "#888")

    # ---- ADVANCED STATS WARNING ----
    if not prediction["has_advanced_stats"]:
        st.warning("No advanced stats provided. Add BPM, OBPM, and FTA for full prediction accuracy.")

    # ================================================================
    # SECTION 1: THE VERDICT (archetype tag + tier headline)
    # ================================================================
    st.markdown(
        f"<div style='padding:16px 20px; border-radius:10px; "
        f"border: 2px solid {pred_color}; background: {pred_color}0D;'>"
        f"<span style='display:inline-block; padding:3px 12px; border-radius:20px; "
        f"background:{arch_color}; color:white; font-size:0.85em; font-weight:bold; "
        f"margin-right:12px; vertical-align:middle;'>{archetype}</span>"
        f"<span style='font-size:1.6em; font-weight:bold; color:{pred_color}; "
        f"vertical-align:middle;'>{pred_label}</span>"
        f"<span style='font-size:0.95em; color:#888; margin-left:10px; "
        f"vertical-align:middle;'>Tier {pred_tier} Projection</span>"
        f"<br><span style='font-size:0.85em; color:#888; margin-left:2px;'>"
        f"{arch_desc} &nbsp;|&nbsp; 2nd: {secondary} &nbsp;|&nbsp; "
        f"Pool: {pool_size} players</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ================================================================
    # SECTION 2: OUTCOME RANGE (ceiling → likely → floor)
    # ================================================================
    st.divider()
    st.markdown("### Outcome Range")

    def _range_line(label, comp, tier):
        if not comp:
            tier_label = TIER_LABELS.get(tier, "?")
            return f"<div style='padding:6px 0;'><b>{label}:</b> T{tier} {tier_label} — no comp found</div>"
        p = comp["player"]
        sim_score = comp["similarity"]["score"]
        ws = p.get("nba_ws", 0) or 0
        tier_label = TIER_LABELS.get(p["tier"], "?")
        t_color = TIER_COLORS.get(p["tier"], "#888")
        return (
            f"<div style='padding:8px 12px; margin:4px 0; border-left:4px solid {t_color}; "
            f"background:{t_color}0D; border-radius:0 6px 6px 0;'>"
            f"<b>{label}:</b> &nbsp;"
            f"<span style='color:{t_color}; font-weight:bold;'>{p['name']}</span>"
            f" &nbsp;— T{p['tier']} {tier_label}"
            f" &nbsp;| {ws:.0f} WS | {sim_score:.0f}% match"
            f"</div>"
        )

    range_html = ""
    range_html += _range_line("Ceiling", ceil_comp, ceil_tier)
    range_html += _range_line("Floor", floor_comp, floor_tier)

    st.markdown(range_html, unsafe_allow_html=True)

    # ================================================================
    # SECTION 3: PLAYS MOST LIKE (top 3 similar players)
    # ================================================================
    if matches:
        st.divider()
        st.markdown("### Plays Most Like")
        st.caption("Based on college statistical similarity — not an outcome prediction.")

        cols = st.columns(3)
        for i, match in enumerate(matches[:3]):
            p = match["player"]
            sim = match["similarity"]
            s = p["stats"]
            ws_val = p.get("nba_ws", 0) or 0
            t_color = TIER_COLORS.get(p["tier"], "#888")
            tier_label = TIER_LABELS.get(p["tier"], "?")
            pick_str = f"#{p['draft_pick']}" if p.get("draft_pick", 61) <= 60 else "Undrafted"

            with cols[i]:
                st.markdown(
                    f"<div style='text-align:center; padding:14px 8px; border-radius:8px; "
                    f"border:2px solid {t_color}; background:{t_color}0D; min-height:160px;'>"
                    f"<div style='font-size:1.15em; font-weight:bold;'>{p['name']}</div>"
                    f"<div style='font-size:1.3em; font-weight:bold; color:{t_color}; "
                    f"margin:4px 0;'>{sim['score']:.0f}% match</div>"
                    f"<div style='font-size:0.85em; color:#888;'>{p['college']}</div>"
                    f"<div style='font-size:0.85em; color:#888;'>{pick_str} | "
                    f"{ws_val:.0f} WS</div>"
                    f"<div style='margin-top:6px; font-size:0.8em;'>"
                    f"{s['ppg']:.1f}p / {s['rpg']:.1f}r / {s['apg']:.1f}a | "
                    f"{s['fg']:.0f}% eFG</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ================================================================
    # SECTION 4: WHY WE THINK THIS (collapsed)
    # ================================================================
    with st.expander("Why We Think This", expanded=False):
        # Star signals
        if prediction["star_signals"] > 0:
            total_signals = len(STAR_SIGNAL_LABELS)
            st.markdown(f"**Star Signals: {prediction['star_signals']}/{total_signals} thresholds exceeded**")
            signal_details = []
            for tag in prediction["star_signal_tags"]:
                label, threshold = STAR_SIGNAL_LABELS.get(tag, (tag, "?"))
                signal_details.append(f"- {label} (>{threshold})")
            st.markdown("\n".join(signal_details))
        else:
            st.markdown("**Star Signals:** None — no elite thresholds exceeded")

        # Unicorn traits
        if prediction["unicorn_traits"]:
            labels = [UNICORN_LABELS.get(t, t) for t in prediction["unicorn_traits"]]
            st.markdown(f"**Unicorn Traits:** {' | '.join(labels)}")

        # Model reasoning
        if prediction["reasons"]:
            st.markdown("**Model Reasoning:**")
            for reason in prediction["reasons"]:
                st.markdown(f"- {reason}")

    # ================================================================
    # SECTION 5: DEEP DIVE (collapsed — stat table, radar, full comps)
    # ================================================================
    if matches:
        with st.expander("Deep Dive — Full Comparisons", expanded=False):
            # Side-by-side stat comparison vs top comp
            if closest_comp:
                comp_p = closest_comp["player"]
                comp_s = comp_p["stats"]
                st.markdown(f"**Stat Comparison: Prospect vs {comp_p['name']}**")

                stat_compare = {
                    "PPG": "ppg", "RPG": "rpg", "APG": "apg",
                    "SPG": "spg", "BPG": "bpg",
                    "eFG%": "fg", "FT%": "ft", "BPM": "bpm",
                }

                header = "| Stat | Prospect | Comp |"
                sep = "|:---|:---:|:---:|"
                rows = [header, sep]
                for label, key in stat_compare.items():
                    p_val = prospect.get(key, 0)
                    c_val = comp_s.get(key, 0)
                    fmt = ".0f" if label in ("eFG%", "FT%") else ".1f"
                    suffix = "%" if label in ("eFG%", "FT%") else ""
                    rows.append(f"| **{label}** | {p_val:{fmt}}{suffix} | {c_val:{fmt}}{suffix} |")
                st.markdown("\n".join(rows))

            st.markdown("---")

            # Radar chart with top 3
            fig = build_radar_chart(prospect, matches)
            st.plotly_chart(fig, width="stretch")

            # Full comp table
            st.markdown(f"**Top 10 {archetype} Comps** (from {pool_size} in pool)")

            table_header = "| # | Player | Sim% | Tier | Outcome | WS | Pick |"
            table_sep = "|:--|:---|:---:|:---:|:---|:---:|:---:|"
            table_rows = [table_header, table_sep]
            for i, match in enumerate(matches[:10]):
                p = match["player"]
                sim = match["similarity"]
                ws_val = p.get("nba_ws", 0) or 0
                t_label = TIER_LABELS.get(p["tier"], "?")
                pick_str = f"#{p['draft_pick']}" if p.get("draft_pick", 61) <= 60 else "—"
                tag = ""
                if ceil_comp and p["name"] == ceil_comp["player"]["name"]:
                    tag = " ▲"
                elif floor_comp and p["name"] == floor_comp["player"]["name"]:
                    tag = " ▼"
                table_rows.append(
                    f"| {i+1} | {p['name']}{tag} | {sim['score']:.0f}% | T{p['tier']} | "
                    f"{t_label} | {ws_val:.0f} | {pick_str} |"
                )
            st.markdown("\n".join(table_rows))

    # Footer
    st.divider()
    st.caption(f"Database: {len(player_db)} players | "
               f"Archetypes: 6 types | "
               f"Model: BPM/OBPM/FTA/SPG/age + star signals | "
               f"Comps: Archetype-filtered weighted Euclidean distance")


if __name__ == "__main__":
    main()
