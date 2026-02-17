"""Investigate why 'name and school correct' players fail to match."""
import sys, os, json, zipfile, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import ZIP_PATH, ZIP_FILES, PROCESSED_DIR
from pipeline.build_player_db import normalize_name, NAME_ALIASES

# Load college CSV
with zipfile.ZipFile(ZIP_PATH) as z:
    with z.open(ZIP_FILES["college"]) as f:
        college1 = pd.read_csv(f, low_memory=False)
    with z.open(ZIP_FILES["college_2022"]) as f:
        college2 = pd.read_csv(f, low_memory=False)
college = pd.concat([college1, college2], ignore_index=True)
college["year"] = pd.to_numeric(college["year"], errors="coerce")
college["GP"] = pd.to_numeric(college["GP"], errors="coerce")

print("College CSV year range: %d - %d" % (college["year"].min(), college["year"].max()))
print("Total rows: %d" % len(college))
print("Unique players: %d" % college["player_name"].nunique())

# Players that failed to match but user says name/school is correct
failed_players = [
    ("AJ Griffin", "Duke", 2022),
    ("Blake Wesley", "Notre Dame", 2022),
    ("Bol Bol", "Oregon", 2019),
    ("Cam Whitmore", "Villanova", 2023),
    ("Max Christie", "Michigan State", 2022),
    ("Darius Garland", "Vanderbilt", 2019),
    ("Dewan Hernandez", "Miami (FL)", 2019),
    ("GG Jackson II", "South Carolina", 2023),
    ("Hamady N'Diaye", "Rutgers University", 2010),
    ("Isaiah Thomas", "Washington", 2011),
    ("Jeff Taylor", "Vanderbilt", 2012),
    ("JD Davison", "Alabama", 2022),
    ("Johnny Davis", "Wisconsin", 2022),
    ("Keyonte George", "Baylor", 2023),
    ("Mo Bamba", "Texas", 2018),
    ("Nic Claxton", "Georgia", 2019),
    ("Devyn Marble", "Iowa", 2014),
    ("Svi Mykhailiuk", "Kansas", 2018),
    ("TyTy Washington Jr.", "Kentucky", 2022),
    ("Wes Iwundu", "Kansas State", 2017),
    ("Jordan Hawkins", "UConn", 2023),
    ("Kendall Brown", "Baylor", 2022),
    ("Julian Phillips", "Tennessee", 2023),
    ("Jarace Walker", "Houston", 2023),
    ("Dereck Lively II", "Duke", 2023),
    ("Dariq Whitehead", "Duke", 2023),
    ("Jett Howard", "Michigan", 2023),
    ("Taylor Hendricks", "Central Florida", 2023),
    ("Jalen Duren", "Memphis", 2022),
    ("Chris Livingston", "Kentucky", 2023),
    ("Joe Young", "Oregon", 2015),
    ("Kay Felder", "Oakland", 2016),
    ("Kennedy Chandler", "Tennessee", 2022),
    ("Jabari Smith Jr.", "Auburn", 2022),
    ("Peyton Watson", "UCLA", 2022),
    ("Emoni Bates", "Eastern Michigan", 2023),
    ("Patrick Baldwin Jr.", "UW-Milwaukee", 2022),
    ("Dennis Smith Jr.", "NC State", 2017),
    ("Maxwell Lewis", "Pepperdine", 2023),
    ("Mouhamed Gueye", "Washington State", 2023),
    ("Jordan Walsh", "Arkansas", 2023),
    ("Cason Wallace", "Kentucky", 2023),
    ("Amari Bailey", "UCLA", 2023),
    ("Donovan Mitchell", "Louisville", 2017),
    ("Paolo Banchero", "Duke", 2022),
    ("Chet Holmgren", "Gonzaga", 2022),
    ("Shaedon Sharpe", "Kentucky", 2022),
    ("Brandin Podziemski", "Santa Clara", 2023),
    ("Brice Sensabaugh", "Ohio State", 2023),
    ("Gradey Dick", "Kansas", 2023),
    ("Jalen Hood-Schifino", "Indiana", 2023),
    ("Kobe Bufkin", "Michigan", 2023),
    ("Noah Clowney", "Alabama", 2023),
    ("Caleb Houstan", "Michigan", 2022),
    ("Jeremy Sochan", "Baylor", 2022),
    ("Josh Minott", "Memphis", 2022),
    ("Malaki Branham", "Ohio State", 2022),
    ("Trevor Keels", "Duke", 2022),
    ("Bryce McGowens", "Nebraska", 2022),
    ("Filip Petrusev", "Gonzaga", 2021),
    ("Jay Scrubb", "John A. Logan College", 2020),
    ("Skal Labissiere", "Kentucky", 2016),
    ("Ricky Ledo", "Providence", 2013),
    ("Nikola Vucevic", "USC", 2011),
    ("Greivis Vasquez", "Maryland", 2010),
    ("Moussa Diabate", "Michigan", 2022),
    ("Maurice Harkless", "St. John's", 2012),
]

print("\n=== INVESTIGATING FAILURES ===\n")

# Categorize failures
no_csv_data = []     # College year > CSV coverage
name_mismatch = []   # Name is different in CSV
found_match = []     # Actually found - pipeline bug?

for bref_name, bref_college, draft_yr in failed_players:
    # What college season would they have played?
    # Draft year X means they played season X-1 or earlier
    last_season = draft_yr - 1  # 2023 draft -> played 2022-23 season (year=2023 in CSV)

    # Search by exact name
    exact = college[college["player_name"] == bref_name]

    # Search by normalized name
    norm_name = normalize_name(bref_name)
    college["_norm"] = college["player_name"].apply(lambda x: normalize_name(str(x)) if pd.notna(x) else "")
    norm_matches = college[college["_norm"] == norm_name]

    # Search by last name + partial first
    parts = bref_name.split()
    last_name = parts[-1] if len(parts) > 1 else bref_name
    last_matches = college[college["player_name"].str.contains(last_name, case=False, na=False)]

    # Also check aliases
    alias = NAME_ALIASES.get(bref_name, None)
    alias_matches = pd.DataFrame()
    if alias:
        alias_matches = college[college["player_name"] == alias]

    if len(exact) > 0:
        # Found exact match - why didn't pipeline catch it?
        row = exact.iloc[0]
        gp = pd.to_numeric(row.get("GP"), errors="coerce")
        yr = row.get("year")
        team = row.get("team", "")
        print("FOUND EXACT: %s -> '%s' at %s, year=%s, GP=%s" % (bref_name, row["player_name"], team, yr, gp))
        if pd.notna(gp) and gp < 10:
            print("  ** GP < 10 -- FILTERED OUT by pipeline")
        found_match.append((bref_name, bref_college, "exact", str(row["player_name"]), str(team)))
    elif len(norm_matches) > 0:
        row = norm_matches.iloc[0]
        gp = pd.to_numeric(row.get("GP"), errors="coerce")
        yr = row.get("year")
        team = row.get("team", "")
        print("FOUND NORMALIZED: %s -> '%s' at %s, year=%s, GP=%s" % (bref_name, row["player_name"], team, yr, gp))
        if pd.notna(gp) and gp < 10:
            print("  ** GP < 10 -- FILTERED OUT by pipeline")
        found_match.append((bref_name, bref_college, "normalized", str(row["player_name"]), str(team)))
    elif len(alias_matches) > 0:
        row = alias_matches.iloc[0]
        print("FOUND VIA ALIAS: %s -> '%s' at %s" % (bref_name, row["player_name"], row.get("team","")))
        found_match.append((bref_name, bref_college, "alias", str(row["player_name"]), str(row.get("team",""))))
    elif len(last_matches) > 0:
        # Found by last name - show all to see what the CSV name actually is
        relevant = last_matches[["player_name", "team", "year", "GP"]].drop_duplicates("player_name").head(5)
        matches_str = "; ".join(["%s (%s, yr=%s)" % (r["player_name"], r["team"], r["year"]) for _, r in relevant.iterrows()])
        print("PARTIAL MATCH: %s -> Last name matches: %s" % (bref_name, matches_str))
        name_mismatch.append((bref_name, bref_college, matches_str))
    else:
        print("NOT IN CSV: %s (%s, draft %d)" % (bref_name, bref_college, draft_yr))
        no_csv_data.append((bref_name, bref_college, draft_yr))

college.drop(columns=["_norm"], inplace=True)

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("\nFOUND IN CSV (pipeline matching bug): %d" % len(found_match))
for name, college_str, method, csv_name, csv_team in found_match:
    print("  %s -> CSV name: '%s' at %s (method: %s)" % (name, csv_name, csv_team, method))

print("\nPARTIAL NAME MATCH (need alias): %d" % len(name_mismatch))
for name, college_str, matches in name_mismatch:
    print("  %s (%s) -> %s" % (name, college_str, matches))

print("\nNOT IN CSV AT ALL: %d" % len(no_csv_data))
for name, college_str, draft_yr in no_csv_data:
    print("  %s (%s, draft %d) -> last season %d, CSV max year = %d" % (name, college_str, draft_yr, draft_yr-1, college["year"].max()))
