import json
db = json.load(open("data/processed/player_db.json"))
p = db[0]
print("Keys:", list(p.keys()))
print("outcome:", p.get("outcome", "MISSING"))
print("war_total:", p.get("war_total", "MISSING"))
print("nba_ws:", p.get("nba_ws", "MISSING"))
print("college:", p.get("college", "MISSING"))
print("tier:", p.get("tier", "MISSING"))
# Check a player with college stats
cs = [x for x in db if x.get("has_college_stats")]
if cs:
    p2 = cs[0]
    print("\nFirst college player:", p2["name"])
    print("Keys:", list(p2.keys()))
    print("outcome:", p2.get("outcome", "MISSING"))
    print("stats keys:", list(p2.get("stats", {}).keys()))
