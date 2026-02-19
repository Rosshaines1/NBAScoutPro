"""NBAScoutPro configuration: paths, constants, column mappings."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
ZIP_PATH = os.path.join(DATA_DIR, "archive.zip")
NEW_DATA_DIR = os.path.join(BASE_DIR, "NewCleanData")

# Output files
PLAYER_DB_PATH = os.path.join(PROCESSED_DIR, "player_db.json")
POSITIONAL_AVGS_PATH = os.path.join(PROCESSED_DIR, "positional_avgs.json")
FEATURE_IMPORTANCE_PATH = os.path.join(PROCESSED_DIR, "feature_importance.json")

# Files inside archive.zip
ZIP_FILES = {
    "college": "CollegeBasketballPlayers2009-2021.csv",
    "college_2022": "CollegeBasketballPlayers2022.csv",
    "draft": "DraftedPlayers2009-2021.xlsx",
    "raptor": "modern_RAPTOR_by_player.csv",
}

# Column mappings from college CSV
COLLEGE_STAT_COLS = {
    "ppg": "pts",       # Already per-game!
    "rpg": "treb",
    "apg": "ast",
    "spg": "stl",
    "bpg": "blk",
    "mpg": "mp",        # Already per-game
}

COLLEGE_PCT_COLS = {
    "fg": "eFG",         # Effective FG%  (already 0-100 scale)
    "threeP": "TP_per",  # 3P% as decimal 0-1 -> multiply by 100
    "ft": "FT_per",      # FT% as decimal 0-1 -> multiply by 100
}

# Positional averages (hardcoded fallback, replaced by data-driven in pipeline)
POSITIONAL_AVGS = {
    "G": {"ppg": 13.0, "rpg": 3.5, "apg": 3.5, "spg": 1.2, "bpg": 0.2,
           "fg": 43.0, "threeP": 34.0, "ft": 75.0, "tpg": 2.2, "ato": 1.6},
    "W": {"ppg": 14.0, "rpg": 5.5, "apg": 2.0, "spg": 1.0, "bpg": 0.6,
           "fg": 46.0, "threeP": 35.0, "ft": 72.0, "tpg": 1.8, "ato": 1.1},
    "B": {"ppg": 12.0, "rpg": 8.5, "apg": 1.2, "spg": 0.6, "bpg": 1.5,
           "fg": 55.0, "threeP": 25.0, "ft": 65.0, "tpg": 1.8, "ato": 0.7},
}

MAX_STATS = {
    "ppg": 30, "rpg": 15, "apg": 11, "spg": 3.5, "bpg": 5.0,
    "fg": 70, "threeP": 50, "ft": 95, "tpg": 5.0, "ato": 4.0,
    "height": 86, "weight": 300, "ws": 92, "age": 24, "mpg": 40.0,
    # New advanced stat maxes (fta/ftm/stops/rimmade/rim_att now per-game)
    "bpm": 15, "obpm": 12, "dbpm": 8, "fta": 10, "ftm": 8,
    "stl_per": 5.0, "usg": 40,
    "stops": 10, "rimmade": 5, "rim_att": 8,
    "ts_per": 70, "adjoe": 135, "adrtg": 110,
    "ftr": 60, "rim_pct": 85, "tpa": 10,
}

# Range-based normalization: (min, max) for each stat.
# A 4-inch height gap should be ~25% of the range, not 5%.
# Stats where min=0 keep current behavior. Stats with real floors
# (height, weight, FT%, etc.) get proper range scaling.
STAT_RANGES = {
    # Physical (translate directly — range matters a LOT)
    "height": (70, 86),      # 5'10" to 7'2"
    "weight": (160, 280),    # guard min to center max
    "ws": (70, 96),          # wingspan range

    # Shooting (translate directly — touch is touch)
    "ft": (40, 95),          # realistic FT% range
    "fg": (35, 65),          # eFG% — nobody is below 35 or above 65
    "threeP": (0, 50),       # 0 is valid (non-shooters)

    # Advanced/efficiency (rate stats — translate well)
    "bpm": (-5, 15),         # can be negative
    "obpm": (-5, 12),
    "dbpm": (-3, 8),
    "usg": (12, 40),         # nobody below 12% usage

    # Context-dependent (wider ranges, more noise)
    "ppg": (0, 30),
    "rpg": (0, 15),
    "apg": (0, 11),
    "spg": (0, 3.5),
    "bpg": (0, 5.0),
    "tpg": (0, 5.0),
    "mpg": (15, 40),
    "ato": (0, 4.0),
    "age": (1, 4),  # class year: 1=Fr, 2=So, 3=Jr, 4=Sr

    # Volume/rate stats (now stored as per-game)
    "fta_pg": (0, 10),       # FTA per game
    "ftm": (0, 8),
    "stl_per": (0, 5.0),
    "stops": (0, 10),
    "rimmade": (0, 5),
    "rim_att": (0, 8),

    # NEW stats (V4)
    "ftr": (15, 60),         # FT rate (FTA/FGA * 100)
    "rim_pct": (30, 85),     # Rim finishing %
    "tpa": (0, 10),          # 3PA per game
}

# Valid draft year range for comp pool and backtest
# 2010-2021: have both college advanced stats (Barttorvik) and NBA outcomes
COMP_YEAR_RANGE = (2010, 2021)

EXCLUDE_PLAYERS = [
    "Joel Embiid", "Donovan Mitchell", "Larry Johnson", "Emeka Okafor",
    "Isaiah Thomas", "Steve Smith", "Shawn Kemp", "Donyell Marshall", "Vin Baker",
]

ATHLETIC_VALUES = {
    "Below Average": 1,
    "Average": 2,
    "Above Average": 3,
    "Elite": 4,
}

# Team strength quadrants based on Barttorvik/KenPom team ranking
# Replaces the old conference-based High/Mid/Low Major system
QUADRANT_RANGES = {
    "Q1": (1, 50),     # Elite teams
    "Q2": (51, 100),   # Good teams
    "Q3": (101, 200),  # Average teams
    "Q4": (201, 999),  # Weak teams
}

QUADRANT_MODIFIERS = {
    "Q1": 1.0,
    "Q2": 0.90,
    "Q3": 0.80,
    "Q4": 0.70,
}

# Legacy level system (kept for fallback if no team rank available)
LEVEL_MODIFIERS = {
    "High Major": 1.0,
    "Mid Major": 0.85,
    "Low Major": 0.70,
}

HIGH_MAJORS = [
    "ACC", "B12", "B10", "SEC", "P10", "P12", "BE",
    "Big East", "Pac-12", "Big 12", "Big Ten",
]

MID_MAJORS = [
    "A10", "MWC", "WCC", "AAC", "Amer", "CUSA", "MAC",
]

TEAM_RANKS_PATH = os.path.join(PROCESSED_DIR, "team_ranks.json")

# WAR tier thresholds
TIER_THRESHOLDS = {
    1: 25,   # Superstar
    2: 15,   # All-Star
    3: 5,    # Starter
    4: 0,    # Role Player
    # 5: everything else (Bust)
}

TIER_LABELS = {
    1: "Superstar",
    2: "Yearly All-Star",
    3: "Top Level Starter",
    4: "Rotation / Bench",
    5: "Bust Risk",
    6: "TBD (Too Early)",
}

# Draft year cutoff: players drafted in this year or later get TBD tier
TBD_DRAFT_YEAR = 2022

# Draft position fallback tiers (for players without RAPTOR data)
DRAFT_POSITION_TIERS = [
    (3, 2),    # Picks 1-3 -> Tier 2 (assume All-Star potential)
    (10, 3),   # Picks 4-10 -> Tier 3
    (20, 4),   # Picks 11-20 -> Tier 4
    (60, 5),   # Picks 21-60 -> Tier 5
]

# Original weights from nbascout.txt for comparison
ORIGINAL_WEIGHTS = {
    "ppg": 1.0, "rpg": 1.0, "apg": 1.0, "spg": 1.0, "bpg": 1.0,
    "fg": 0.8, "threeP": 2.0, "ft": 1.5, "ato": 1.5,
    "height": 1.5, "weight": 0.8, "ws": 1.5, "ath": 2.0,
    "age": 1.2, "mpg": 1.5,
}

# V2 weights: data-driven from backward superstar analysis (old 1620-player dataset)
# Kept for backtest comparison baseline.
V2_WEIGHTS = {
    "bpm": 5.0, "obpm": 4.0, "ft": 4.0, "fta_pg": 3.5,
    "stl_per": 3.0, "usg": 3.0, "dbpm": 2.0,
    "height": 3.0, "ws": 3.0, "weight": 0.6, "spg": 1.5,
    "ppg": 0.5, "rpg": 0.3, "apg": 0.3, "bpg": 0.3,
    "fg": 0.5, "threeP": 0.2, "ato": 0.5, "age": 1.2, "mpg": 0.3,
    "ath": 0.0,
}

# V3 weights: retuned on corrected 496-player dataset (2009-2019 drafts, Feb 2026 tier fixes)
# Derived from Pearson r vs corrected tiers + star/bust separation analysis.
V3_WEIGHTS = {
    # Tier 1: Advanced metrics (strongest predictors, retuned Feb 2026 on 547 corrected players)
    "bpm": 5.0,       # r=0.230, #1 by |r|, Cohen d=0.28
    "ftr": 4.0,       # r=0.183, #1 by combined score, star-bust gap +5.27
    "fta_pg": 3.0,    # r=0.130, FTA volume = star signal
    "fg": 3.2,        # r=0.122, eFG% sep=+1.43
    "age": 3.0,       # r=-0.188, #2 by |r|, Fr=stars, Sr=busts

    # Tier 2: Moderate predictors
    "height": 2.5,    # physical translation — range-normalized (70-86")
    "rim_pct": 2.5,   # r=0.166, rim finishing translates, independent of BPM
    "obpm": 2.0,      # r=0.124, offensive impact
    "dbpm": 1.8,      # r=0.172, defensive impact
    "ft": 1.5,        # r=0.022 (near-zero after tier corrections), penalty-only FT<65
    "rpg": 1.5,       # r=0.157, context-dependent
    "usg": 1.3,       # r=0.036, weak after tier corrections

    # Tier 3: Counting stats + weak predictors
    "ppg": 1.0,       # r=0.051, context-dependent (level-adjusted only)
    "stl_per": 0.8,   # r=0.057, defensive instincts
    "spg": 0.7,       # r=0.057, partially opportunity-based
    "bpg": 0.7,       # r=0.129, mostly height-dependent
    "tpg": 0.5,       # r=-0.016, turnover rate
    "apg": 0.4,       # r=-0.022 (near-zero — assists don't predict NBA success)
    "ato": 0.5,       # derived from apg/tpg
    "mpg": 0.4,       # r=0.024, weak
    "tpa": 0.3,       # r=-0.112, weak but useful for 3P% volume context

    # Tier 4: Weak/negative predictors
    "threeP": 0.3,    # r=-0.088 (NEGATIVE — stars shoot worse 3P% in college)

    # Disabled — no real data
    "weight": 0.0,    # all placeholder 200lbs
    "ws": 0.0,        # all estimated h+4
    "ath": 0.0,       # no data for historicals
}

# Star signal thresholds (retuned on 547-player corrected dataset, Feb 2026)
# Optimal cutpoints for separating T1+T2 from T4+T5 by F1 score.
STAR_SIGNAL_THRESHOLDS = {
    "bpm": 7.6,       # F1=0.235, precision=0.149
    "obpm": 6.9,      # F1=0.215, precision=0.194
    "fta": 4.7,       # F1=0.241, precision=0.151
    "spg": 1.4,       # F1=0.238, precision=0.164
    "stl_per": 2.3,   # F1=0.236, precision=0.151
    "usg": 25.9,      # F1=0.232, precision=0.150
    "ft": 81.3,       # F1=0.217, precision=0.160
}

# Archetype weight modifiers: multipliers applied to V3_WEIGHTS per archetype.
# Values > 1.0 emphasize that stat, < 1.0 de-emphasize it.
# Stats not listed default to 1.0 (no change).
# V3: Adjusted for data findings (APG near-zero predictor, 3P% negative).
ARCHETYPE_WEIGHT_MODS = {
    "Scoring Guard": {
        "usg": 1.3, "fta_pg": 1.3, "obpm": 1.2,
        "rpg": 0.5, "bpg": 0.3,
    },
    "Playmaking Guard": {
        "apg": 1.5, "ato": 1.5, "stl_per": 1.3,  # apg reduced from 2.0 (near-zero predictor)
        "ppg": 0.5,
    },
    "3&D Wing": {
        "threeP": 1.5, "spg": 1.3, "dbpm": 1.3,  # threeP reduced from 2.0 (negative predictor)
        "ppg": 0.5, "usg": 0.7, "fta_pg": 0.7,
    },
    "Scoring Wing": {
        "height": 1.3, "usg": 1.2, "fta_pg": 1.2,
        "apg": 0.5, "threeP": 0.7,
    },
    "Skilled Big": {
        "ft": 1.3, "obpm": 1.3, "fg": 1.2,  # fg added (eFG% now high-weight); threeP removed (negative predictor)
        "apg": 0.5, "spg": 0.7,
    },
    "Athletic Big": {
        "dbpm": 1.5, "bpg": 2.0,
        "ft": 0.5, "threeP": 0.3, "obpm": 0.7,
    },
}

# Barttorvik CSV column headers (no header row in CSVs, apply programmatically)
BAR_HEADERS = [
    "player_name", "team", "conf", "GP", "Min_per", "ORtg", "usg", "eFG",
    "TS_per", "ORB_per", "DRB_per", "AST_per", "TO_per", "FTM", "FTA",
    "FT_per", "twoPM", "twoPA", "twoP_per", "TPM", "TPA", "TP_per",
    "blk_per", "stl_per", "ftr", "yr", "ht", "num", "porpag", "adjoe",
    "pfr", "year", "pid", "type", "Rec Rank", "ast/tov", "rimmade",
    "rimmade+rimmiss", "midmade", "midmade+midmiss",
    "rimmade/(rimmade+rimmiss)", "midmade/(midmade+midmiss)", "dunksmade",
    "dunksmiss+dunksmade", "dunksmade/(dunksmade+dunksmiss)", "pick", "drtg",
    "adrtg", "dporpag", "stops", "bpm", "obpm", "dbpm", "gbpm", "mp",
    "ogbpm", "dgbpm", "oreb", "dreb", "treb", "ast", "stl", "blk", "pts",
    "role", "3p/100",
]
