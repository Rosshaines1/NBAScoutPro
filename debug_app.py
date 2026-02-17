"""Simulate exactly what the Streamlit app does."""
import json
from app.similarity import find_top_matches, count_star_signals
from config import POSITIONAL_AVGS, ATHLETIC_VALUES, PLAYER_DB_PATH, POSITIONAL_AVGS_PATH
import os

with open(PLAYER_DB_PATH) as f:
    player_db = json.load(f)
pos_avgs = POSITIONAL_AVGS
if os.path.exists(POSITIONAL_AVGS_PATH):
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)

# Exact defaults from the Streamlit sidebar
prospect = {
    "name": "Draft Prospect", "pos": "G", "h": 75, "w": 195,
    "ws": 79, "age": 20.5, "level": "High Major",
    "ath": ATHLETIC_VALUES["Average"],  # = 2
    "ppg": 15.0, "rpg": 4.5, "apg": 3.5, "spg": 1.2, "bpg": 0.4,
    "fg": 45.0, "threeP": 35.0, "ft": 75.0, "tpg": 2.5, "mpg": 30.0,
    "bpm": 0.0, "obpm": 0.0, "dbpm": 0.0, "fta": 0.0,
    "stl_per": 0.0, "usg": 0.0,
}

print("Prospect:", prospect)
print(f"\nRunning find_top_matches with {len(player_db)} players...")
matches = find_top_matches(prospect, player_db, pos_avgs, top_n=5, use_v2=True)

print(f"\nGot {len(matches)} matches:")
for i, m in enumerate(matches):
    p = m["player"]
    sim = m["similarity"]
    print(f"  #{i+1}: {p['name']} -> {sim['score']}% (penalty={sim['penalty']}, "
          f"tier={p['tier']}, outcome={p['outcome']})")

# Also test with a loaded prospect (Cooper Flagg)
with open("data/prospects.json") as f:
    prospects = json.load(f)
flagg = prospects[0]
print(f"\n\nLoaded prospect: {flagg['name']}")
prospect2 = {
    "name": flagg["name"], "pos": flagg["pos"],
    "h": flagg["h_ft"]*12 + flagg["h_in"], "w": flagg["weight"],
    "ws": flagg["wingspan"], "age": flagg["age"], "level": flagg["level"],
    "ath": ATHLETIC_VALUES[flagg["athleticism"]],
    "ppg": flagg["ppg"], "rpg": flagg["rpg"], "apg": flagg["apg"],
    "spg": flagg["spg"], "bpg": flagg["bpg"],
    "fg": flagg["fg"], "threeP": flagg["threeP"], "ft": flagg["ft"],
    "tpg": flagg["tpg"], "mpg": flagg["mpg"],
    "bpm": flagg["bpm"], "obpm": flagg["obpm"], "dbpm": flagg["dbpm"],
    "fta": flagg["fta"], "stl_per": flagg["stl_per"], "usg": flagg["usg"],
}
matches2 = find_top_matches(prospect2, player_db, pos_avgs, top_n=5, use_v2=True)
print(f"Got {len(matches2)} matches:")
for i, m in enumerate(matches2):
    p = m["player"]
    sim = m["similarity"]
    print(f"  #{i+1}: {p['name']} -> {sim['score']}% (penalty={sim['penalty']})")
