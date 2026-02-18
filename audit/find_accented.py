import json
import unicodedata

with open("data/processed/player_db.json", encoding="utf-8") as f:
    db = json.load(f)

for p in db:
    name = p["name"]
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    if stripped != name:
        with open("audit/accented_names.txt", "a", encoding="utf-8") as out:
            out.write(f"{repr(name)} -> {repr(stripped)}\n")
