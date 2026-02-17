"""Add real draft ages to player_db.json using college class year from CSV.

Age estimation from class year:
  Fr = 19.5, So = 20.5, Jr = 21.5, Sr = 22.5
  (average age at draft for each class, based on typical timelines)

For international/non-college players or missing data, keeps existing age.
"""
import sys, os, json, zipfile, io
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ZIP_PATH, ZIP_FILES, PLAYER_DB_PATH

CLASS_TO_AGE = {
    "Fr": 19.5,
    "So": 20.5,
    "Jr": 21.5,
    "Sr": 22.5,
}


def normalize_name(name):
    """Normalize player name for matching."""
    if not name:
        return ""
    n = name.strip().lower()
    # Remove suffixes
    for suf in [" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"]:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    # Normalize punctuation
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    return n


def main():
    # Load college CSV from archive
    print("Loading college data from archive...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        with z.open(ZIP_FILES["college"]) as f:
            df1 = pd.read_csv(f, low_memory=False)
        with z.open(ZIP_FILES["college_2022"]) as f:
            df2 = pd.read_csv(f, low_memory=False)
    college = pd.concat([df1, df2], ignore_index=True)
    print(f"  College records: {len(college):,}")

    # Build lookup: for each player, find their LAST college year (closest to draft)
    # Group by player_name, take the row with the highest 'year' value
    college["yr_clean"] = college["yr"].map(lambda x: str(x).strip() if pd.notna(x) else "")
    college["year_int"] = pd.to_numeric(college["year"], errors="coerce")

    # For each player name, get the row with the latest year and a valid class
    valid = college[college["yr_clean"].isin(CLASS_TO_AGE.keys())].copy()
    valid["norm_name"] = valid["player_name"].apply(normalize_name)

    # Take the latest year entry per player (their draft-year season)
    latest = valid.sort_values("year_int", ascending=False).drop_duplicates("norm_name", keep="first")
    class_lookup = dict(zip(latest["norm_name"], latest["yr_clean"]))
    print(f"  Players with class year: {len(class_lookup):,}")

    # Load player DB
    with open(PLAYER_DB_PATH) as f:
        db = json.load(f)
    print(f"  Player DB entries: {len(db)}")

    # Update ages
    updated = 0
    unchanged = 0
    missing = 0
    for player in db:
        name = player.get("name", "")
        norm = normalize_name(name)
        yr = class_lookup.get(norm)
        if yr and yr in CLASS_TO_AGE:
            new_age = CLASS_TO_AGE[yr]
            if player.get("age") != new_age:
                player["age"] = new_age
                updated += 1
            else:
                unchanged += 1
        else:
            missing += 1

    print(f"\n  Updated: {updated}")
    print(f"  Already correct: {unchanged}")
    print(f"  No class data (kept 22.0): {missing}")

    # Save
    with open(PLAYER_DB_PATH, "w") as f:
        json.dump(db, f, indent=2)
    print(f"\n  Saved to {PLAYER_DB_PATH}")

    # Spot check
    print("\n  Spot check:")
    check_names = [
        "Stephen Curry", "James Harden", "Anthony Davis", "Damian Lillard",
        "Zach LaVine", "Andrew Wiggins", "Anthony Bennett", "Jimmer Fredette",
    ]
    lookup = {p["name"]: p for p in db}
    for n in check_names:
        p = lookup.get(n)
        if p:
            print(f"    {n:<25} age: {p['age']}")


if __name__ == "__main__":
    main()
