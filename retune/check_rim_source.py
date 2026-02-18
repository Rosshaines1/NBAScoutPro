"""Check where rim% data comes from in the CSV."""
import zipfile, csv, io, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with zipfile.ZipFile("data/archive.zip") as z:
    with z.open("CollegeBasketballPlayers2009-2021.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
        first_row = next(reader)

# Show all column names
cols = list(first_row.keys())
print(f"Total columns: {len(cols)}")
print(f"\nAll columns:")
for i, c in enumerate(cols):
    print(f"  {i:3d}: {c}")

# Check rim-related columns
print(f"\n=== RIM-RELATED COLUMNS ===")
for c in cols:
    if 'rim' in c.lower():
        print(f"  {c}: example value = {first_row[c]}")

# Check a few known players for rim data
print(f"\n=== SAMPLE RIM DATA ===")
with zipfile.ZipFile("data/archive.zip") as z:
    with z.open("CollegeBasketballPlayers2009-2021.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
        targets = {'Zion Williamson', 'Ja Morant', 'Trae Young', 'Anthony Davis',
                   'Damian Lillard', 'Stephen Curry', 'Kawhi Leonard'}
        for row in reader:
            name = row.get('player_name', '')
            if name in targets:
                rm = row.get('rimmade', '')
                rmiss = row.get('rimmade+rimmiss', '')
                year = row.get('year', '')
                team = row.get('team', '')
                print(f"  {name:25s} ({year}, {team}) rimmade={rm:>6s}  rim_att={rmiss:>6s}")
                targets.discard(name)
        if targets:
            print(f"\n  NOT FOUND: {targets}")
