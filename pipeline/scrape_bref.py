"""Scrape Basketball Reference draft pages for NBA career stats.

Fetches Win Shares, VORP, BPM, and per-game stats for every draft pick
from 1989-2023. This gives us career outcome data for ~2,000 draft picks,
replacing the limited RAPTOR WAR data (2014-2022 only).

Respects rate limits: 3-second delay between requests per robots.txt.
"""
import urllib.request
import re
import time
import json
import os
import sys
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROCESSED_DIR

OUTPUT_PATH = os.path.join(PROCESSED_DIR, "bref_draft_stats.json")
START_YEAR = 1989
END_YEAR = 2023

FIELDS = [
    "pick_overall", "player", "college_name", "seasons", "g", "mp",
    "pts_per_g", "trb_per_g", "ast_per_g", "fg_pct", "fg3_pct", "ft_pct",
    "ws", "ws_per_48", "bpm", "vorp",
]


def fetch_draft_page(year):
    """Fetch and parse one draft year from Basketball Reference."""
    url = f"https://www.basketball-reference.com/draft/NBA_{year}.html"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NBAScoutPro research tool)"})
    resp = urllib.request.urlopen(req, timeout=20)
    html = resp.read().decode("utf-8")
    return html


def parse_draft_page(html, year):
    """Extract player rows from a draft page."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    players = []

    for row in rows:
        if 'data-stat="pick_overall"' not in row:
            continue

        vals = {}
        for field in FIELDS:
            m = re.search(rf'data-stat="{field}"[^>]*>(?:<a[^>]*>)?([^<]*)', row)
            vals[field] = m.group(1).strip() if m else ""

        # Skip header rows
        name = vals.get("player", "")
        pick = vals.get("pick_overall", "")
        if not name or not pick or not pick.isdigit():
            continue

        # Parse numeric fields
        def to_float(s):
            try:
                return float(s)
            except (ValueError, TypeError):
                return None

        player = {
            "name": name,
            "draft_year": year,
            "draft_pick": int(pick),
            "college": vals.get("college_name", ""),
            "nba_seasons": to_float(vals.get("seasons")),
            "nba_games": to_float(vals.get("g")),
            "nba_minutes": to_float(vals.get("mp")),
            "nba_ppg": to_float(vals.get("pts_per_g")),
            "nba_rpg": to_float(vals.get("trb_per_g")),
            "nba_apg": to_float(vals.get("ast_per_g")),
            "nba_fg_pct": to_float(vals.get("fg_pct")),
            "nba_3p_pct": to_float(vals.get("fg3_pct")),
            "nba_ft_pct": to_float(vals.get("ft_pct")),
            "nba_ws": to_float(vals.get("ws")),
            "nba_ws48": to_float(vals.get("ws_per_48")),
            "nba_bpm": to_float(vals.get("bpm")),
            "nba_vorp": to_float(vals.get("vorp")),
        }
        players.append(player)

    return players


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    all_players = []

    # Check for existing partial results
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            all_players = json.load(f)
        existing_years = set(p["draft_year"] for p in all_players)
        print(f"Resuming: {len(all_players)} players from {len(existing_years)} years already scraped")
    else:
        existing_years = set()

    years_to_fetch = [y for y in range(START_YEAR, END_YEAR + 1) if y not in existing_years]

    if not years_to_fetch:
        print("All years already scraped!")
        print(f"Total: {len(all_players)} players")
        return

    print(f"Scraping {len(years_to_fetch)} draft years from Basketball Reference...")
    print(f"  Years: {years_to_fetch[0]}-{years_to_fetch[-1]}")
    print(f"  Rate limit: 3s between requests")
    print()

    for i, year in enumerate(years_to_fetch):
        try:
            html = fetch_draft_page(year)
            players = parse_draft_page(html, year)
            all_players.extend(players)
            print(f"  {year}: {len(players)} picks scraped ({i+1}/{len(years_to_fetch)})")

            # Save after each year (resume-safe)
            with open(OUTPUT_PATH, "w") as f:
                json.dump(all_players, f, indent=2)

        except Exception as e:
            print(f"  {year}: ERROR - {e}")

        # Rate limit: 3 seconds between requests
        if i < len(years_to_fetch) - 1:
            time.sleep(3)

    # Summary
    print(f"\nDone! {len(all_players)} total draft picks scraped")

    # Stats
    with_college = [p for p in all_players if p["college"]]
    with_ws = [p for p in all_players if p["nba_ws"] is not None]
    print(f"  With college: {len(with_college)}")
    print(f"  With Win Shares: {len(with_ws)}")
    print(f"  Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
