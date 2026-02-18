"""Compare backtest pool vs comp pool — they should be the same."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_DB_PATH, COMP_YEAR_RANGE

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

college = [p for p in db if p.get("has_college_stats")]
print(f"Total with college stats: {len(college)}")

yr_lo, yr_hi = COMP_YEAR_RANGE

# Comp pool filter (from find_archetype_matches — year range + GP/MPG)
gp_mpg = [p for p in college
           if yr_lo <= (p.get("draft_year") or 0) <= yr_hi
           and (p.get("stats", {}).get("gp", 30) or 30) >= 25
           and (p.get("stats", {}).get("mpg", 30) or 30) >= 20]
print(f"Comp pool ({yr_lo}-{yr_hi} + GP/MPG): {len(gp_mpg)}")

# Backtest filter (from backtester — year range + WS + GP/MPG)
backtest = [p for p in college
            if yr_lo <= (p.get("draft_year") or 0) <= yr_hi
            and p.get("nba_ws") is not None
            and (p.get("stats", {}).get("gp", 30) or 30) >= 25
            and (p.get("stats", {}).get("mpg", 30) or 30) >= 20]
print(f"Backtest ({yr_lo}-{yr_hi} + WS + GP/MPG): {len(backtest)}")

# Intersection
bt_names = {p["name"] for p in backtest}
pool_names = {p["name"] for p in gp_mpg}

in_both = bt_names & pool_names
in_bt_only = bt_names - pool_names
in_pool_only = pool_names - bt_names

print(f"\nIn both:          {len(in_both)}")
print(f"Backtest only:    {len(in_bt_only)}  (in backtest but NOT in comp pool)")
print(f"Comp pool only:   {len(in_pool_only)}  (in comp pool but NOT in backtest)")

# Why are some in backtest but not comp pool?
if in_bt_only:
    print(f"\n--- BACKTEST-ONLY (fail GP/MPG filter) ---")
    for name in sorted(in_bt_only):
        p = next(x for x in backtest if x["name"] == name)
        s = p.get("stats", {})
        gp = s.get("gp", 30) or 30
        mpg = s.get("mpg", 30) or 30
        print(f"  {name:25s} GP={gp:3.0f} MPG={mpg:4.1f} T{p['tier']} ({p.get('draft_year')})")

# Why are some in comp pool but not backtest?
print(f"\n--- COMP-POOL-ONLY breakdown ---")
pool_only_players = [p for p in gp_mpg if p["name"] in in_pool_only]
no_ws = [p for p in pool_only_players if p.get("nba_ws") is None]
pre_09 = [p for p in pool_only_players if p.get("nba_ws") is not None and (p.get("draft_year") or 0) < 2009]
post_19 = [p for p in pool_only_players if p.get("nba_ws") is not None and (p.get("draft_year") or 0) > 2019]
print(f"  No outcome yet (recent):  {len(no_ws)}")
print(f"  Pre-2009 drafts:          {len(pre_09)}")
print(f"  Post-2019 drafts:         {len(post_19)}")
