"""Build the player database from raw archive data + Basketball Reference.

V2: Uses BRef Win Shares (1989-2023) instead of RAPTOR WAR (2014-2022 only).
    Adds advanced college stats: FTA, obpm, dbpm, porpag, dporpag, stl_per, usg, stops.
    Fixes name matching with fuzzy matching for "AJ" vs "A.J.", "Bam" vs "Edrice", etc.
    Includes pre-2009 draft picks from BRef as outcome-only comparison targets.

CRITICAL FIX: College CSV stats (pts, ast, treb, stl, blk, mp) are ALREADY
per-game. The old pipeline divided by GP again, producing garbage.
"""
import sys
import os
import json
import zipfile
import re
import unicodedata

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ZIP_PATH, PROCESSED_DIR, PLAYER_DB_PATH, POSITIONAL_AVGS_PATH,
    ZIP_FILES, HIGH_MAJORS, MID_MAJORS,
    TIER_LABELS,
)
from pipeline.height_parser import parse_height

BREF_PATH = os.path.join(PROCESSED_DIR, "bref_draft_stats.json")

# Players to completely exclude from the database (per user audit review).
# Reasons: bad data, played too few games, played overseas, etc.
REMOVE_PLAYERS = {
    "Joel Embiid",       # Injured at Kansas, bad college data
    "James Wiseman",     # Played one college game at Memphis
    "Patrick Beverley",  # Played in Europe, not real US college data
}

# Players whose name collision causes them to match the WRONG person in the
# college CSV. Their correct college isn't in our CSV (pre-2009 or missing).
# Force these to BRef-only so they don't poison comps with wrong stats.
FORCE_BREF_ONLY = {
    "Larry Johnson",     # UNLV (matched to Arkansas Pine Bluff Larry Johnson)
    "Steve Smith",       # Michigan State (matched to Fairfield Steve Smith)
    "Shawn Kemp",        # Never attended college (matched to Washington)
    "Emeka Okafor",      # UConn (matched to Western Illinois Emeka Okafor)
    "Donyell Marshall",  # UConn (matched to Central Connecticut)
    "Vin Baker",         # Hartford (matched to Boston College Vin Baker)
    "Anthony Black",     # Arkansas (matched to Little Rock Anthony Black)
}

# Manual stat overrides for players whose final season is missing from the CSV.
# Format: {name: {stat_key: value, ...}}
# These are applied after the main pipeline builds the player record.
STAT_OVERRIDES = {
    "Jaylen Clark": {"mpg": 30.5},       # UCLA Jr 2022-23 (CSV only has Fr 2020-21)
    "Ben Sheppard": {"dbpm": -0.4},      # Belmont Jr 2022-23 (CSV only has So 2020-21)
}

# Win Shares tier thresholds (replaces RAPTOR WAR thresholds)
# Calibrated: LeBron=274, Curry=147, avg starter ~40-60, role player ~10-30
WS_TIERS = {
    1: 80,    # Superstar (top ~30 all-time per draft era)
    2: 40,    # All-Star
    3: 20,    # Solid Starter
    4: 5,     # Role Player
    # 5: below 5 (Bust)
}

# Manual tier corrections from user review (Feb 2026).
# WS-based tiers misclassify players affected by injuries, bad teams, or longevity.
# 99 corrections: role players on good teams demoted, injured stars promoted, etc.
TIER_OVERRIDES = {
    "Andrew Nicholson": 4,
    "Austin Rivers": 3,
    "Avery Bradley": 3,
    "Ben Simmons": 2,
    "Bol Bol": 4,
    "Bradley Beal": 1,
    "Brandon Ingram": 2,
    "Brandon Knight": 3,
    "Cam Reddish": 4,
    "Chinanu Onuaku": 4,
    "Coby White": 3,
    "Cody Martin": 3,
    "Collin Sexton": 3,
    "Danny Green": 3,
    "Darius Garland": 2,
    "Darren Collison": 3,
    "De'Aaron Fox": 2,
    "Deandre Ayton": 3,
    "Derrick Favors": 3,
    "Derrick White": 3,
    "Devin Booker": 1,
    "Devonte' Graham": 3,
    "Dillon Brooks": 3,
    "Dion Waiters": 3,
    "Donovan Mitchell": 1,
    "Dwight Powell": 3,
    "Ed Davis": 4,
    "Elfrid Payton": 3,
    "Eric Bledsoe": 3,
    "Eric Paschall": 4,
    "Frank Kaminsky": 3,
    "Gary Trent Jr.": 3,
    "Grant Williams": 3,
    "Greg Monroe": 3,
    "Greivis Vasquez": 3,
    "Iman Shumpert": 3,
    "Ja Morant": 2,
    "Jabari Parker": 3,
    "Jae Crowder": 3,
    "Jakob Poeltl": 3,
    "Jalen Brunson": 1,
    "Jalen McDaniels": 3,
    "Jared Sullinger": 3,
    "Jaren Jackson Jr.": 2,
    "Jarrett Allen": 3,
    "Jarrett Culver": 4,
    "Jaylen Brown": 1,
    "Jayson Tatum": 1,
    "Jeff Withey": 5,
    "Jonathan Isaac": 3,
    "Jordan Bell": 4,
    "Jordan Poole": 3,
    "Josh Hart": 3,
    "Justin Anderson": 4,
    "Kelly Olynyk": 3,
    "Kentavious Caldwell-Pope": 3,
    "Kevin Porter Jr.": 3,
    "Kevon Looney": 4,
    "Klay Thompson": 1,
    "Kyle Anderson": 3,
    "Kyle Kuzma": 3,
    "Lance Stephenson": 3,
    "Landry Shamet": 3,
    "Larry Nance Jr.": 4,
    "Lauri Markkanen": 2,
    "Lonnie Walker IV": 4,
    "Lonzo Ball": 2,
    "Luke Kennard": 4,
    "Malik Monk": 3,
    "Markelle Fultz": 3,
    "Mason Plumlee": 3,
    "Meyers Leonard": 3,
    "Michael Carter-Williams": 3,
    "Michael Porter Jr.": 2,
    "Mo Bamba": 5,
    "Montrezl Harrell": 3,
    "Moritz Wagner": 3,
    "Nassir Little": 4,
    "Nickeil Alexander-Walker": 3,
    "Nikola Vucevic": 2,
    "Norris Cole": 4,
    "OG Anunoby": 2,
    "P.J. Washington": 3,
    "RJ Barrett": 3,
    "Rodney Hood": 3,
    "Rui Hachimura": 3,
    "Sam Young": 5,
    "Shai Gilgeous-Alexander": 1,
    "Skal Labissiere": 4,
    "Steven Adams": 3,
    "Taj Gibson": 3,
    "Talen Horton-Tucker": 3,
    "Terrence Jones": 3,
    "Tristan Thompson": 3,
    "Ty Lawson": 3,
    "Tyler Herro": 2,
    "Zach Collins": 3,
    "Zach LaVine": 2,
    "Zion Williamson": 2,
}


def load_datasets():
    """Load college data from archive.zip.

    NOTE: CollegeBasketballPlayers2022.csv is EXCLUDED — it contains 100%
    duplicate rows from the 2009-2021 file with year bumped to 2022 but
    identical stats. Using it causes returning players to show freshman stats
    for their final season.
    """
    print(f"Loading from {ZIP_PATH}...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        with z.open(ZIP_FILES["college"]) as f:
            college = pd.read_csv(f, low_memory=False)
    print(f"  College records: {len(college):,}")
    print(f"  (Skipped 2022 CSV — verified as 100% duplicate data)")
    return college


def load_bref():
    """Load Basketball Reference draft stats."""
    if not os.path.exists(BREF_PATH):
        print(f"  WARNING: {BREF_PATH} not found. Run pipeline/scrape_bref.py first.")
        return {}
    with open(BREF_PATH) as f:
        bref = json.load(f)
    print(f"  BRef draft picks: {len(bref):,}")
    # Build lookup: name -> best entry (handle duplicates by keeping highest WS)
    bref_map = {}
    for p in bref:
        name = p["name"]
        if name not in bref_map or (p.get("nba_ws") or 0) > (bref_map[name].get("nba_ws") or 0):
            bref_map[name] = p
    return bref_map


def normalize_name(name):
    """Normalize a name for fuzzy matching.

    Handles: periods (A.J.->AJ), suffixes (Jr/Sr/II/III/IV),
    and accented characters (Vučević->Vucevic).
    """
    name = name.strip()
    # Strip accented characters: é->e, č->c, š->s, etc.
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Remove periods: "A.J." -> "AJ"
    name = name.replace(".", "")
    # Remove Jr/Sr/III suffixes
    name = re.sub(r'\s+(Jr|Sr|III|II|IV)$', '', name, flags=re.IGNORECASE)
    return name.lower()


def build_name_index(names):
    """Build a normalized name -> original name index for fuzzy matching."""
    index = {}
    for name in names:
        norm = normalize_name(name)
        if norm not in index:
            index[norm] = name
    return index


# Known name aliases: BRef draft name -> college CSV name
NAME_ALIASES = {
    # Original aliases
    "Bam Adebayo": "Edrice Adebayo",
    "P.J. Washington": "PJ Washington",
    "Cam Thomas": "Cameron Thomas",
    "Herb Jones": "Herbert Jones",
    "Bones Hyland": "Nah'Shon Hyland",
    "Trey Murphy III": "Trey Murphy",
    # Fixed direction (BRef has full name, CSV has nickname)
    "Maurice Harkless": "Moe Harkless",
    # New aliases from audit
    "Mo Bamba": "Mohamed Bamba",
    "Nic Claxton": "Nicolas Claxton",
    "Devyn Marble": "Roy Devyn Marble",
    "Svi Mykhailiuk": "Sviatoslav Mykhailiuk",
    "Wes Iwundu": "Wesley Iwundu",
    "Kay Felder": "Kahlil Felder",
    "Jeff Taylor": "Jeffery Taylor",
    "Joe Young": "Joseph Young",
}


CLASS_YEAR_MAP = {"Fr": 1, "So": 2, "Jr": 3, "Sr": 4}


def parse_class_year(row):
    """Extract class year (1-4) from college CSV 'yr' column.

    Returns integer 1-4 if found, or 4 (senior) as fallback.
    """
    yr = row.get("yr")
    if pd.notna(yr):
        yr_str = str(yr).strip()
        if yr_str in CLASS_YEAR_MAP:
            return CLASS_YEAR_MAP[yr_str]
    return 4  # Default to senior if unknown


def get_conf_level(conf):
    if conf in HIGH_MAJORS:
        return "High Major"
    if conf in MID_MAJORS:
        return "Mid Major"
    return "Low Major"


def assign_position(height_inches):
    if height_inches < 76:
        return "G"
    elif height_inches > 81:
        return "B"
    return "W"


def assign_tier_ws(nba_ws, draft_pick, nba_games):
    """Assign tier from Win Shares, with context for young players."""
    if nba_ws is None:
        # No NBA data at all
        return 5, TIER_LABELS[5]

    # For very young players (< 3 seasons), project forward cautiously
    # But don't override — just use what we have

    if nba_ws > WS_TIERS[1]:
        return 1, TIER_LABELS[1]
    if nba_ws > WS_TIERS[2]:
        return 2, TIER_LABELS[2]
    if nba_ws > WS_TIERS[3]:
        return 3, TIER_LABELS[3]
    if nba_ws > WS_TIERS[4]:
        return 4, TIER_LABELS[4]
    return 5, TIER_LABELS[5]


def safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (ValueError, TypeError):
        return default


def build_player_db():
    """Main pipeline: load, clean, match, export."""
    college = load_datasets()
    bref_map = load_bref()

    # Build normalized name indexes for matching
    college_name_index = build_name_index(college["player_name"].dropna().unique())
    bref_name_index = build_name_index(bref_map.keys())

    # College: keep latest season per player
    college["year"] = pd.to_numeric(college["year"], errors="coerce")
    college["GP"] = pd.to_numeric(college["GP"], errors="coerce")
    college = college.dropna(subset=["year", "GP"])

    # Primary lookup: GP >= 10 (filters out redshirts, injuries, transfers)
    college_gp10 = college[college["GP"] >= 10]
    latest = college_gp10.sort_values("year", ascending=False).drop_duplicates("player_name")
    latest_lookup = {str(row["player_name"]).strip(): row for _, row in latest.iterrows()}

    # Relaxed lookup: GP >= 3 (catches injured players like Bol Bol GP=9, Garland GP=5)
    college_gp3 = college[college["GP"] >= 3]
    latest_relaxed = college_gp3.sort_values("year", ascending=False).drop_duplicates("player_name")
    relaxed_lookup = {str(row["player_name"]).strip(): row for _, row in latest_relaxed.iterrows()}

    # College-by-school lookup: (normalized_name, school) -> row for disambiguation.
    # Built from ALL entries (not deduplicated) so name collisions across schools
    # can be resolved. Keeps the latest season per (name, school) pair.
    # Handles "Donovan Mitchell" at Louisville vs Wake Forest, etc.
    college_by_school = {}
    for _, row in college_gp3.sort_values("year", ascending=False).iterrows():
        name_str = str(row["player_name"]).strip()
        school = str(row.get("team", "")).strip().lower()
        key = (normalize_name(name_str), school)
        if key not in college_by_school:  # Keep latest season per (name, school)
            college_by_school[key] = row

    print(f"\nBuilding player database...")
    print(f"  College players (latest season, GP>=10): {len(latest):,}")
    print(f"  BRef draft picks: {len(bref_map):,}")

    players = []
    matched_count = 0
    alias_count = 0
    fuzzy_count = 0
    bref_only_count = 0

    # --- PASS 1: Process all BRef draft picks (primary source of truth) ---
    removed_count = 0
    for bref_name, bref_data in bref_map.items():
        if bref_name in REMOVE_PLAYERS:
            removed_count += 1
            continue

        nba_ws = bref_data.get("nba_ws")
        draft_pick = bref_data.get("draft_pick", 61)
        draft_year = bref_data.get("draft_year")
        nba_games = bref_data.get("nba_games")

        # Try to find college stats
        college_row = None
        match_method = None
        bref_college = str(bref_data.get("college", "")).strip().lower()

        # 1. Exact match
        if bref_name in latest_lookup:
            college_row = latest_lookup[bref_name]
            match_method = "exact"
            matched_count += 1

        # 2. Alias match
        elif bref_name in NAME_ALIASES and NAME_ALIASES[bref_name] in latest_lookup:
            college_row = latest_lookup[NAME_ALIASES[bref_name]]
            match_method = "alias"
            alias_count += 1

        # 3. Fuzzy match (normalize periods, suffixes, accents)
        if college_row is None:
            norm = normalize_name(bref_name)
            if norm in college_name_index:
                orig_name = college_name_index[norm]
                if orig_name in latest_lookup:
                    college_row = latest_lookup[orig_name]
                    match_method = "fuzzy"
                    fuzzy_count += 1

        # 4. Relaxed GP match (GP >= 3 instead of 10, catches injured players)
        if college_row is None:
            if bref_name in relaxed_lookup:
                college_row = relaxed_lookup[bref_name]
                match_method = "relaxed_gp"
                fuzzy_count += 1
            elif bref_name in NAME_ALIASES and NAME_ALIASES[bref_name] in relaxed_lookup:
                college_row = relaxed_lookup[NAME_ALIASES[bref_name]]
                match_method = "relaxed_gp_alias"
                alias_count += 1
            else:
                norm = normalize_name(bref_name)
                if norm in college_name_index:
                    orig_name = college_name_index[norm]
                    if orig_name in relaxed_lookup:
                        college_row = relaxed_lookup[orig_name]
                        match_method = "relaxed_gp_fuzzy"
                        fuzzy_count += 1

        # 5. College-aware disambiguation for name collisions.
        #    If we matched but the college doesn't align with BRef, try
        #    to find a better match at the correct school.
        if college_row is not None and bref_college:
            csv_school = str(college_row.get("team", "")).strip().lower()
            if bref_college not in csv_school and csv_school not in bref_college:
                # Name matched but wrong school — try school-aware lookup
                norm = normalize_name(bref_name)
                for school_key in college_by_school:
                    if school_key[0] == norm and bref_college in school_key[1]:
                        college_row = college_by_school[school_key]
                        match_method = "college_disambig"
                        break
                # If no better match found, keep the original — school name
                # abbreviations differ between BRef and CSV (e.g. "Oklahoma State"
                # vs "Oklahoma St.") and most mismatches are just formatting.

        # 6. Force BRef-only for known wrong matches (correct college not in CSV)
        if bref_name in FORCE_BREF_ONLY:
            college_row = None
            match_method = None

        # Build player record
        if college_row is not None:
            row = college_row
            # ---- STATS ARE ALREADY PER-GAME ----
            ppg = safe_float(row.get("pts"))
            rpg = safe_float(row.get("treb"))
            apg = safe_float(row.get("ast"))
            spg = safe_float(row.get("stl"))
            bpg = safe_float(row.get("blk"))
            mpg = safe_float(row.get("mp"), 30.0)

            efg = safe_float(row.get("eFG"), 45.0)
            tp_pct = safe_float(row.get("TP_per"))
            ft_pct = safe_float(row.get("FT_per"))
            if tp_pct <= 1.0:
                tp_pct *= 100
            if ft_pct <= 1.0:
                ft_pct *= 100

            ato = safe_float(row.get("ast/tov"), 1.0)
            tpg = apg / ato if ato > 0 else apg
            bpm_val = safe_float(row.get("bpm"))

            height = parse_height(row.get("ht"))
            weight = safe_float(row.get("weight"), 200.0)
            if weight < 100 or weight > 400:
                weight = 200.0

            pos = assign_position(height)
            conf = str(row.get("conf", ""))
            level = get_conf_level(conf)
            gp = safe_float(row.get("GP"), 20)

            # Advanced stats (NEW in V2)
            fta_raw = safe_float(row.get("FTA"))
            ftm_raw = safe_float(row.get("FTM"))
            obpm = safe_float(row.get("obpm"))
            dbpm = safe_float(row.get("dbpm"))
            stl_per = safe_float(row.get("stl_per"))
            usg = safe_float(row.get("usg"))
            stops_raw = safe_float(row.get("stops"))
            rimmade_raw = safe_float(row.get("rimmade"))
            rim_att_raw = safe_float(row.get("rimmade+rimmiss"))
            ts_per = safe_float(row.get("TS_per"))
            adjoe = safe_float(row.get("adjoe"))
            adrtg = safe_float(row.get("adrtg"))

            # NEW stats for correlation analysis
            tpa_raw = safe_float(row.get("TPA"))  # 3pt attempts (season total)
            tpm_raw = safe_float(row.get("TPM"))  # 3pt makes (season total)
            two_pa_raw = safe_float(row.get("twoPA"))  # 2pt attempts (season total)
            two_pm_raw = safe_float(row.get("twoPM"))  # 2pt makes (season total)
            two_p_pct = safe_float(row.get("twoP_per"))  # 2pt %
            oreb_pg = safe_float(row.get("oreb"))  # offensive reb (per-game)
            dreb_pg = safe_float(row.get("dreb"))  # defensive reb (per-game)
            ftr_val = safe_float(row.get("ftr"))  # FT rate
            orb_per = safe_float(row.get("ORB_per"))  # offensive reb %
            drb_per = safe_float(row.get("DRB_per"))  # defensive reb %
            ast_per = safe_float(row.get("AST_per"))  # assist %
            to_per = safe_float(row.get("TO_per"))  # turnover %
            blk_per = safe_float(row.get("blk_per"))  # block %
            ortg = safe_float(row.get("Ortg"))  # offensive rating
            porpag_val = safe_float(row.get("porpag"))  # pts over replacement/game
            dporpag_val = safe_float(row.get("dporpag"))  # defensive PORG

            # Convert season totals to per-game
            gp_div = gp if gp > 0 else 30
            fta = fta_raw / gp_div if fta_raw else 0
            ftm = ftm_raw / gp_div if ftm_raw else 0
            stops = stops_raw / gp_div if stops_raw else 0
            rimmade = rimmade_raw / gp_div if rimmade_raw else 0
            rim_att = rim_att_raw / gp_div if rim_att_raw else 0
            tpa = tpa_raw / gp_div if tpa_raw else 0
            tpm = tpm_raw / gp_div if tpm_raw else 0
            two_pa = two_pa_raw / gp_div if two_pa_raw else 0
            two_pm = two_pm_raw / gp_div if two_pm_raw else 0

            tier, outcome = assign_tier_ws(nba_ws, draft_pick, nba_games)
            class_year = parse_class_year(row)

            player = {
                "name": bref_name,
                "college": str(row.get("team", "")),
                "pos": pos,
                "h": height,
                "w": round(weight, 0),
                "ws": height + 4,
                "age": class_year,
                "level": level,
                "ath": 2,
                "draft_pick": draft_pick,
                "draft_year": draft_year,
                "nba_ws": round(nba_ws, 1) if nba_ws is not None else None,
                "nba_vorp": bref_data.get("nba_vorp"),
                "nba_bpm": bref_data.get("nba_bpm"),
                "has_college_stats": True,
                "stats": {
                    "ppg": round(ppg, 1), "rpg": round(rpg, 1), "apg": round(apg, 1),
                    "spg": round(spg, 1), "bpg": round(bpg, 1),
                    "fg": round(efg, 1), "threeP": round(tp_pct, 1), "ft": round(ft_pct, 1),
                    "tpg": round(tpg, 1), "mpg": round(mpg, 1), "bpm": round(bpm_val, 1),
                    # Advanced stats (per-game where applicable)
                    "fta": round(fta, 2), "ftm": round(ftm, 2),
                    "obpm": round(obpm, 1), "dbpm": round(dbpm, 1),
                    "stl_per": round(stl_per, 1), "usg": round(usg, 1),
                    "stops": round(stops, 2),
                    "rimmade": round(rimmade, 2), "rim_att": round(rim_att, 2),
                    "ts_per": round(ts_per, 2), "adjoe": round(adjoe, 1),
                    "adrtg": round(adrtg, 1),
                    "gp": round(gp, 0),
                    # NEW stats
                    "tpa": round(tpa, 2), "tpm": round(tpm, 2),
                    "two_pa": round(two_pa, 2), "two_pm": round(two_pm, 2),
                    "two_p_pct": round(two_p_pct, 3),
                    "oreb": round(oreb_pg, 2), "dreb": round(dreb_pg, 2),
                    "ftr": round(ftr_val, 1),
                    "orb_per": round(orb_per, 1), "drb_per": round(drb_per, 1),
                    "ast_per": round(ast_per, 1), "to_per": round(to_per, 1),
                    "blk_per": round(blk_per, 1),
                    "ortg": round(ortg, 1),
                    "porpag": round(porpag_val, 2),
                    "dporpag": round(dporpag_val, 2),
                },
                "outcome": outcome,
                "tier": tier,
            }
            players.append(player)

        elif bref_data.get("college") and nba_ws is not None:
            # BRef-only player (pre-2009 or name mismatch): include with NBA stats as profile
            # These can be matched against, but use NBA career stats as their "profile"
            nba_ppg = bref_data.get("nba_ppg") or 0
            nba_rpg = bref_data.get("nba_rpg") or 0
            nba_apg = bref_data.get("nba_apg") or 0

            # Estimate position from NBA stats
            if nba_rpg > 6:
                pos = "B"
            elif nba_apg > 4:
                pos = "G"
            else:
                pos = "W"

            tier, outcome = assign_tier_ws(nba_ws, draft_pick, nba_games)

            player = {
                "name": bref_name,
                "college": bref_data.get("college", ""),
                "pos": pos,
                "h": 78, "w": 200, "ws": 82,
                "age": 4,  # No college row — default to senior
                "level": "High Major",  # Assume for historical players
                "ath": 2,
                "draft_pick": draft_pick,
                "draft_year": draft_year,
                "nba_ws": round(nba_ws, 1),
                "nba_vorp": bref_data.get("nba_vorp"),
                "nba_bpm": bref_data.get("nba_bpm"),
                "has_college_stats": False,
                "stats": {
                    "ppg": round(nba_ppg, 1), "rpg": round(nba_rpg, 1),
                    "apg": round(nba_apg, 1),
                    "spg": 0, "bpg": 0,
                    "fg": round((bref_data.get("nba_fg_pct") or 0.45) * 100, 1),
                    "threeP": round((bref_data.get("nba_3p_pct") or 0.33) * 100, 1),
                    "ft": round((bref_data.get("nba_ft_pct") or 0.75) * 100, 1),
                    "tpg": 0, "mpg": 30.0, "bpm": 0,
                    "fta": 0, "ftm": 0, "obpm": 0, "dbpm": 0,
                    "stl_per": 0, "usg": 0,
                    "stops": 0, "rimmade": 0, "rim_att": 0,
                    "ts_per": 0, "adjoe": 0, "adrtg": 0, "gp": 0,
                },
                "outcome": outcome,
                "tier": tier,
            }
            players.append(player)
            bref_only_count += 1

    # --- PASS 2: Add undrafted college players who made the NBA ---
    # (They appear in BRef's RAPTOR data from the original archive)
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        with z.open(ZIP_FILES["raptor"]) as f:
            raptor = pd.read_csv(f, low_memory=False)
    raptor["war_total"] = pd.to_numeric(raptor["war_total"], errors="coerce").fillna(0)
    raptor_war = raptor.groupby("player_name")["war_total"].sum().to_dict()

    existing_names = {p["name"] for p in players}
    undrafted_added = 0
    for name, war in raptor_war.items():
        if name in existing_names or war < 1.0 or name in REMOVE_PLAYERS:
            continue
        if name in latest_lookup:
            row = latest_lookup[name]
            ppg = safe_float(row.get("pts"))
            rpg = safe_float(row.get("treb"))
            apg = safe_float(row.get("ast"))
            spg = safe_float(row.get("stl"))
            bpg = safe_float(row.get("blk"))
            mpg = safe_float(row.get("mp"), 30.0)
            efg = safe_float(row.get("eFG"), 45.0)
            tp_pct = safe_float(row.get("TP_per"))
            ft_pct = safe_float(row.get("FT_per"))
            if tp_pct <= 1.0: tp_pct *= 100
            if ft_pct <= 1.0: ft_pct *= 100
            ato = safe_float(row.get("ast/tov"), 1.0)
            tpg = apg / ato if ato > 0 else apg
            height = parse_height(row.get("ht"))
            weight = safe_float(row.get("weight"), 200.0)
            if weight < 100 or weight > 400: weight = 200.0
            pos = assign_position(height)

            # Estimate WS from WAR (rough: WAR and WS are correlated)
            est_ws = war * 3  # Very rough

            tier, outcome = assign_tier_ws(est_ws, 61, None)

            # Convert season totals to per-game
            u_gp = safe_float(row.get("GP"), 30) or 30
            u_fta = safe_float(row.get("FTA"))
            u_ftm = safe_float(row.get("FTM"))
            u_stops = safe_float(row.get("stops"))
            u_rimmade = safe_float(row.get("rimmade"))
            u_rim_att = safe_float(row.get("rimmade+rimmiss"))

            u_class_year = parse_class_year(row)

            player = {
                "name": name,
                "college": str(row.get("team", "")),
                "pos": pos,
                "h": height, "w": round(weight, 0), "ws": height + 4,
                "age": u_class_year,
                "level": get_conf_level(str(row.get("conf", ""))),
                "ath": 2,
                "draft_pick": 61,
                "draft_year": None,
                "nba_ws": round(est_ws, 1),
                "nba_vorp": None, "nba_bpm": None,
                "has_college_stats": True,
                "stats": {
                    "ppg": round(ppg, 1), "rpg": round(rpg, 1), "apg": round(apg, 1),
                    "spg": round(spg, 1), "bpg": round(bpg, 1),
                    "fg": round(efg, 1), "threeP": round(tp_pct, 1), "ft": round(ft_pct, 1),
                    "tpg": round(tpg, 1), "mpg": round(mpg, 1),
                    "bpm": round(safe_float(row.get("bpm")), 1),
                    "fta": round(u_fta / u_gp, 2) if u_fta else 0,
                    "ftm": round(u_ftm / u_gp, 2) if u_ftm else 0,
                    "obpm": round(safe_float(row.get("obpm")), 1),
                    "dbpm": round(safe_float(row.get("dbpm")), 1),
                    "stl_per": round(safe_float(row.get("stl_per")), 1),
                    "usg": round(safe_float(row.get("usg")), 1),
                    "stops": round(u_stops / u_gp, 2) if u_stops else 0,
                    "rimmade": round(u_rimmade / u_gp, 2) if u_rimmade else 0,
                    "rim_att": round(u_rim_att / u_gp, 2) if u_rim_att else 0,
                    "ts_per": round(safe_float(row.get("TS_per")), 2),
                    "adjoe": round(safe_float(row.get("adjoe")), 1),
                    "adrtg": round(safe_float(row.get("adrtg")), 1),
                    "gp": round(u_gp, 0),
                },
                "outcome": outcome,
                "tier": tier,
            }
            players.append(player)
            undrafted_added += 1

    # --- Apply manual stat overrides ---
    override_count = 0
    for p in players:
        if p["name"] in STAT_OVERRIDES:
            for stat_key, val in STAT_OVERRIDES[p["name"]].items():
                p["stats"][stat_key] = val
            override_count += 1

    # --- Apply manual tier corrections ---
    # Match by exact name first, then by accent-stripped name
    tier_override_count = 0
    tier_override_index = {}
    for override_name, override_tier in TIER_OVERRIDES.items():
        tier_override_index[override_name] = override_tier
        stripped = unicodedata.normalize("NFKD", override_name).encode("ascii", "ignore").decode("ascii")
        if stripped != override_name:
            tier_override_index[stripped] = override_tier

    for p in players:
        name = p["name"]
        stripped_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        new_tier = tier_override_index.get(name) or tier_override_index.get(stripped_name)
        if new_tier is not None and new_tier != p["tier"]:
            p["tier"] = new_tier
            p["outcome"] = TIER_LABELS[new_tier]
            tier_override_count += 1

    print(f"\n  Match results:")
    print(f"    Exact name match:  {matched_count}")
    print(f"    Alias match:       {alias_count}")
    print(f"    Fuzzy match:       {fuzzy_count}")
    print(f"    BRef-only (no college stats): {bref_only_count}")
    print(f"    Removed (bad data):          {removed_count}")
    print(f"    Stat overrides applied:      {override_count}")
    print(f"    Tier overrides applied:      {tier_override_count}/{len(TIER_OVERRIDES)}")
    print(f"    Undrafted NBA players added:  {undrafted_added}")
    print(f"    TOTAL: {len(players)}")

    return players


def compute_positional_averages(players):
    """Compute real positional averages from players WITH college stats."""
    from collections import defaultdict
    stats_by_pos = defaultdict(lambda: defaultdict(list))
    stat_keys = ["ppg", "rpg", "apg", "spg", "bpg", "fg", "threeP", "ft", "tpg", "mpg"]

    for p in players:
        if not p.get("has_college_stats"):
            continue
        pos = p["pos"]
        for key in stat_keys:
            val = p["stats"].get(key, 0)
            if val is not None:
                stats_by_pos[pos][key].append(val)

    avgs = {}
    for pos in ["G", "W", "B"]:
        avgs[pos] = {}
        for key in stat_keys:
            vals = stats_by_pos[pos][key]
            avgs[pos][key] = round(np.mean(vals), 1) if vals else 0.0
        avg_apg = avgs[pos]["apg"]
        avg_tpg = avgs[pos]["tpg"]
        avgs[pos]["ato"] = round(avg_apg / avg_tpg, 2) if avg_tpg > 0 else 1.0

    return avgs


def validate(players):
    """Run sanity checks on the output."""
    print("\n--- VALIDATION ---")

    for check_name in ["Cade Cunningham", "Stephen Curry", "LeBron James", "Tim Duncan", "Kobe Bryant"]:
        found = [p for p in players if check_name in p["name"]]
        if found:
            p = found[0]
            ppg = p["stats"]["ppg"]
            ws = p.get("nba_ws", "?")
            print(f"  {check_name:20s} PPG={ppg:5.1f} WS={ws} Tier={p['tier']} college_stats={p.get('has_college_stats')}")
        else:
            print(f"  WARNING: {check_name} not found")

    from collections import Counter
    tier_counts = Counter(p["tier"] for p in players)
    print(f"\n  Tier distribution:")
    for t in sorted(tier_counts):
        label = TIER_LABELS.get(t, "?")
        print(f"    Tier {t} ({label:25s}): {tier_counts[t]}")

    total = len(players)
    with_college = sum(1 for p in players if p.get("has_college_stats"))
    print(f"\n  Total: {total} ({with_college} with college stats, {total - with_college} BRef-only)")


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    players = build_player_db()
    pos_avgs = compute_positional_averages(players)

    print(f"\nExporting {len(players)} players to {PLAYER_DB_PATH}")
    with open(PLAYER_DB_PATH, "w") as f:
        json.dump(players, f, indent=2)

    print(f"Exporting positional averages to {POSITIONAL_AVGS_PATH}")
    with open(POSITIONAL_AVGS_PATH, "w") as f:
        json.dump(pos_avgs, f, indent=2)

    validate(players)
    print("\nDone!")


if __name__ == "__main__":
    main()
