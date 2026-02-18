"""Compute team strength from roster-level stats in our CSV.
Use sum of top-8 BPMs as a KenPom-like team strength proxy."""
import zipfile
import csv
import io
import json
import sys
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, '.')
from config import PLAYER_DB_PATH

# Load all players from CSV
with zipfile.ZipFile("data/archive.zip") as z:
    with z.open("CollegeBasketballPlayers2009-2021.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
        rows = list(reader)

# Group by team+year, compute team strength
team_data = defaultdict(list)
for r in rows:
    team = r.get("team", "")
    year = r.get("year", "")
    bpm = float(r.get("bpm", 0) or 0)
    gp = int(r.get("GP", 0) or 0)
    mp = float(r.get("Min_per", 0) or 0)
    if team and year and gp >= 10 and mp >= 10:  # filter out walkons
        team_data[(team, year)].append(bpm)

# Team strength = average of top 8 BPMs (starters + key bench)
team_strength = {}
for (team, year), bpms in team_data.items():
    top8 = sorted(bpms, reverse=True)[:8]
    team_strength[(team, year)] = sum(top8) / len(top8)

# Show distribution
vals = list(team_strength.values())
vals.sort()
print(f"Team strength computed for {len(team_strength)} team-seasons")
print(f"  Min: {min(vals):.1f}  Max: {max(vals):.1f}  Median: {vals[len(vals)//2]:.1f}")
print(f"  25th pctl: {vals[len(vals)//4]:.1f}  75th pctl: {vals[3*len(vals)//4]:.1f}")

# Show our key teams
print(f"\n=== KEY TEAMS ===")
key_teams = [
    ("South Florida", "2010"), ("Butler", "2010"), ("Marquette", "2011"),
    ("Duke", "2019"), ("Kentucky", "2018"), ("Murray St.", "2019"),
    ("Davidson", "2009"), ("Fresno St.", "2010"), ("Weber St.", "2012"),
    ("Kansas", "2018"), ("BYU", "2011"), ("North Carolina", "2012"),
    ("Duke", "2012"), ("Kentucky", "2012"), ("Arizona St.", "2009"),
    ("Oklahoma", "2009"), ("Connecticut", "2011"), ("San Diego St.", "2011"),
    ("Michigan", "2013"), ("Texas Tech", "2019"), ("Virginia", "2019"),
]
for team, year in key_teams:
    s = team_strength.get((team, year))
    if s is not None:
        # Rank among all teams that year
        year_teams = [(t, v) for (t, y), v in team_strength.items() if y == year]
        year_teams.sort(key=lambda x: x[1], reverse=True)
        rank = next(i+1 for i, (t, v) in enumerate(year_teams) if t == team)
        total = len(year_teams)
        pctile = (1 - rank/total) * 100
        print(f"  {team:20s} ({year}): strength={s:>5.1f}  rank={rank:>3}/{total}  (top {pctile:.0f}%)")
    else:
        print(f"  {team:20s} ({year}): NOT FOUND")

# Now check: does team strength correlate with NBA outcomes?
print(f"\n\n=== TEAM STRENGTH vs NBA OUTCOMES ===")
with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

clean = [p for p in db if p.get("has_college_stats")
         and 2009 <= (p.get("draft_year") or 0) <= 2019
         and p.get("nba_ws") is not None]

# Match players to team strength
matched = []
for p in clean:
    college = p.get("college", "")
    year = str(p.get("draft_year", ""))
    # Try exact match, then year-1 (since draft year = year after college season)
    ts = team_strength.get((college, year))
    if ts is None:
        ts = team_strength.get((college, str(int(year)-1)))
    if ts is not None:
        matched.append({"name": p["name"], "tier": p["tier"], "team_strength": ts,
                        "college": college, "year": year, "level": p.get("level", "?")})

print(f"Matched {len(matched)}/{len(clean)} players to team strength")

# Correlation: avg team strength by tier
from collections import Counter
for t in range(1, 6):
    group = [m for m in matched if m["tier"] == t]
    if group:
        avg = sum(m["team_strength"] for m in group) / len(group)
        print(f"  Tier {t}: avg team strength = {avg:.2f}  (n={len(group)})")

# Compare to current level system
print(f"\n=== CURRENT LEVEL vs TEAM STRENGTH ===")
for level in ["High Major", "Mid Major", "Low Major"]:
    group = [m for m in matched if m["level"] == level]
    if group:
        avg = sum(m["team_strength"] for m in group) / len(group)
        strengths = [m["team_strength"] for m in group]
        strengths.sort()
        lo = strengths[len(strengths)//4]
        hi = strengths[3*len(strengths)//4]
        print(f"  {level:12s}: avg={avg:.2f}  IQR=[{lo:.1f} to {hi:.1f}]  n={len(group)}")
