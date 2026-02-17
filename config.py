"""NBAScoutPro configuration: paths, constants, column mappings."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
ZIP_PATH = os.path.join(DATA_DIR, "archive.zip")

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
}

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

# WAR tier thresholds
TIER_THRESHOLDS = {
    1: 25,   # Superstar
    2: 15,   # All-Star
    3: 5,    # Starter
    4: 0,    # Role Player
    # 5: everything else (Bust)
}

TIER_LABELS = {
    1: "Superstar / MVP",
    2: "All-Star",
    3: "Solid Starter",
    4: "Role Player",
    5: "Bust / Out of League",
}

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

# V3 weights: retuned on clean 493-player dataset (2009-2019 drafts)
# Derived from Pearson r vs NBA WS + star/bust separation analysis.
V3_WEIGHTS = {
    # Tier 1: Advanced metrics (strongest predictors, translate directly)
    "bpm": 5.0,       # r=0.276, #1 predictor, Cohen d=0.69
    "fg": 3.2,        # r=0.103, eFG% sep=+1.39 (efficient scoring translates)
    "fta_pg": 3.0,    # r=0.171, FTA volume = star signal (Cohen d=0.50)
    "obpm": 2.72,     # r=0.186, offensive impact
    "dbpm": 2.66,     # r=0.162, defensive impact (Cohen d=0.46)
    "usg": 2.61,      # r=0.086, offensive load indicator

    # Tier 2: Physical + age (translate directly)
    "height": 2.5,    # physical translation — range-normalized (70-86")
    "age": 2.13,      # r=-0.209, #2 raw predictor! Fr=23.7 WS vs Sr=10.5 WS

    # Tier 3: Penalty-stat (FT%) + moderate predictors
    # FT% has r=0.018 overall BUT FT<65 = 71% bust rate. Works as penalty.
    # Kept high for similarity matching (player style fingerprint).
    "ft": 3.5,        # penalty-stat: broken shot = bust signal, good FT = style match
    "ppg": 1.0,       # r=0.106, context-dependent (level-adjusted only)
    "rpg": 1.0,       # r=0.128, context-dependent
    "mpg": 1.0,       # r=0.054, context indicator
    "bpg": 0.83,      # r=0.084, mostly height-dependent
    "stl_per": 0.76,  # r=0.111, defensive instincts
    "spg": 0.63,      # r=0.110, partially opportunity-based
    "tpg": 0.57,      # r=0.054, turnover rate
    "ato": 0.5,       # derived from apg/tpg

    # Tier 4: Weak/zero predictors
    "threeP": 0.3,    # r=-0.092 (NEGATIVE — stars shoot worse 3P% in college)
    "apg": 0.17,      # r=0.008 (essentially zero)

    # Disabled — no real data
    "weight": 0.0,    # all placeholder 200lbs
    "ws": 0.0,        # all estimated h+4
    "ath": 0.0,       # no data for historicals
}

# Star signal thresholds (retuned on clean 493-player dataset, 2009-2019)
# Optimal cutpoints for separating T1+T2 from T4+T5 by F1 score.
STAR_SIGNAL_THRESHOLDS = {
    "bpm": 9.6,       # F1=0.308, precision=0.267
    "obpm": 7.1,      # F1=0.279, precision=0.281
    "fta": 4.6,       # F1=0.321, precision=0.207 (high recall)
    "spg": 1.4,       # F1=0.268, precision=0.196
    "stl_per": 2.5,   # F1=0.256, precision=0.186
    "usg": 25.9,      # F1=0.270, precision=0.183
    "ft": 79.9,       # F1=0.231 (new: FT% as star signal)
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
