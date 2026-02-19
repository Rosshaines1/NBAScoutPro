"""Find remaining unmatched by team."""
import csv, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
DATA_DIR = 'NewCleanData'

searches = [
    (2025, "Rutgers", "Airious"),
    (2023, "South Carolina", "Jackson"),
    (2021, "Alabama", "Herbert"),
    (2021, "Alabama", "Herb"),
    (2025, "Marquette", "Jones"),
    (2025, "Marquette", "Kam"),
    (2011, "Georgia", "Trey"),
    (2011, "Georgia", "Thompkins"),
    (2018, "Purdue", "Edwards"),
    (2018, "Purdue", "Vincent"),
    (2018, "Purdue", "Vince"),
]

for yr, team, hint in searches:
    csv_path = os.path.join(DATA_DIR, f"{yr}bar.csv")
    if not os.path.exists(csv_path):
        print(f"No file for {yr}")
        continue
    with open(csv_path, encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            pname = row[0].strip()
            pteam = row[1].strip()
            if team.lower() in pteam.lower() and hint.lower() in pname.lower():
                print(f"  {yr} {team} '{hint}': {pname} ({pteam})")
