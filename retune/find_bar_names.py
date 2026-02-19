"""Find correct bar CSV names for unmatched players."""
import csv, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = 'NewCleanData'

# Unmatched: (cbr_name, bar_year, search_hints)
unmatched = [
    ("Dewan Hernandez", 2018, ["Hernandez", "Huell"]),
    ("James Nnaji", 2026, ["Nnaji"]),
    ("Airious Bailey", 2025, ["Bailey", "Airious"]),
    ("Bam Adebayo", 2017, ["Adebayo", "Edrice"]),
    ("DeAndre Bembry", 2016, ["Bembry"]),
    ("Dennis Smith Jr.", 2017, ["Dennis Smith"]),
    ("GG Jackson II", 2023, ["Jackson", "GG"]),
    ("Hamady N'Diaye", 2010, ["Diaye", "Hamady"]),
    ("Herb Jones", 2021, ["Jones", "Herbert"]),
    ("Joe Young", 2015, ["Young", "Joseph"]),
    ("Kameron Jones", 2025, ["Jones", "Kam "]),
    ("Kay Felder", 2016, ["Felder", "Kahlil"]),
    ("Kezie Okpala", 2019, ["Okpala", "KZ"]),
    ("Maurice Harkless", 2012, ["Harkless", "Moe"]),
    ("Raymond Spalding", 2018, ["Spalding"]),
    ("Trey Thompkins III", 2011, ["Thompkins"]),
    ("Vince Edwards", 2018, ["Edwards", "Vince"]),
]

for name, yr, hints in unmatched:
    csv_path = os.path.join(DATA_DIR, f"{yr}bar.csv")
    if not os.path.exists(csv_path):
        print(f"\n{name} ({yr}): NO BAR FILE for {yr}")
        continue

    matches = []
    with open(csv_path, encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            pname = row[0].strip()
            team = row[1].strip()
            for hint in hints:
                if hint.lower() in pname.lower():
                    matches.append(f"{pname} ({team})")
                    break

    print(f"\n{name} ({yr}):")
    if matches:
        for m in matches[:10]:
            print(f"  -> {m}")
    else:
        print(f"  NO MATCHES for hints {hints}")
