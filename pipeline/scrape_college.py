"""Scrape Sports Reference college basketball pages for missing player stats.

Fills the 2022-2023 data gap: ~91 players who either have no college stats
or have early-season (freshman/sophomore) stats because the Kaggle CSV
only covers through 2021.

Scrapes per-game stats from individual player pages on sports-reference.com/cbb/.
Respects rate limits: 3-second delay between requests per robots.txt.

Output: data/processed/college_scrape.json
"""
import urllib.request
import urllib.parse
import re
import time
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROCESSED_DIR

OUTPUT_PATH = os.path.join(PROCESSED_DIR, "college_scrape.json")

# Stats to extract from per-game table (data-stat attr -> our key name)
PER_GAME_STATS = {
    "g": "gp",
    "gs": "gs",
    "mp": "mp",
    "fg_pct": "fg_pct",
    "fg3_pct": "fg3_pct",
    "fg3a": "fg3a",
    "fg2_pct": "fg2_pct",
    "efg_pct": "efg_pct",
    "ft": "ftm",
    "fta": "fta",
    "ft_pct": "ft_pct",
    "trb": "treb",
    "orb": "orb",
    "drb": "drb",
    "ast": "ast",
    "stl": "stl",
    "blk": "blk",
    "tov": "tov",
    "pf": "pf",
    "pts": "pts",
}


def strip_accents(s):
    """Remove accent marks for URL generation."""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def name_to_url_slug(name):
    """Convert player name to Sports Reference URL slug.
    e.g. 'Keegan Murray' -> 'keegan-murray'
    """
    name = strip_accents(name)
    # Remove suffixes like Jr., Sr., III, II, IV
    name = re.sub(r'\s+(Jr\.?|Sr\.?|III|II|IV)$', '', name, flags=re.IGNORECASE)
    # Remove periods and apostrophes
    name = name.replace(".", "").replace("'", "")
    # Split and rejoin with hyphens
    parts = name.lower().split()
    return "-".join(parts)


def fetch_page(url):
    """Fetch a page with proper headers."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (NBAScoutPro research tool)"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def search_player(name):
    """Search Sports Reference for a player and return their URL slug."""
    query = urllib.parse.quote(name)
    url = f"https://www.sports-reference.com/cbb/search/search.fcgi?search={query}"
    html = fetch_page(url)
    if html is None:
        return None

    # Check if we were redirected directly to a player page
    if 'data-stat="season"' in html:
        # We landed on the player page directly
        m = re.search(r'/cbb/players/([^"]+)\.html', html)
        if m:
            return m.group(1)

    # Look for player links in search results
    matches = re.findall(r'/cbb/players/([^"]+)\.html', html)
    if matches:
        return matches[0]

    return None


def parse_player_page(html, target_season=None):
    """Extract per-game stats from a player page.

    If target_season is given (e.g. "2021-22"), extract that specific season.
    Otherwise, extract the LAST season row.

    Returns dict with stats, or None if not found.
    """
    # Find the per-game table
    # Sports Reference wraps tables in comments, so check both
    # First try direct table
    table_match = re.search(
        r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
        html, re.DOTALL
    )

    if not table_match:
        # Try inside comments
        comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
        for comment in comments:
            table_match = re.search(
                r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
                comment, re.DOTALL
            )
            if table_match:
                break

    if not table_match:
        return None

    table_html = table_match.group(1)

    # Parse all data rows (skip header rows)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

    season_rows = []
    for row_html in rows:
        if 'data-stat="season"' not in row_html:
            continue
        if 'class="thead"' in row_html or 'class="over_header' in row_html:
            continue

        # Extract season
        season_m = re.search(r'data-stat="season"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
        if not season_m:
            continue
        season = season_m.group(1).strip()
        if not season or season == "Career":
            continue

        # Extract team
        team_m = re.search(r'data-stat="team_id"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
        team = team_m.group(1).strip() if team_m else ""

        # Extract class year
        class_m = re.search(r'data-stat="class"[^>]*>([^<]*)', row_html)
        class_yr = class_m.group(1).strip() if class_m else ""

        # Extract conference
        conf_m = re.search(r'data-stat="conf_id"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
        conf = conf_m.group(1).strip() if conf_m else ""

        # Extract all numeric stats
        stats = {"season": season, "team": team, "class": class_yr, "conf": conf}
        for data_stat, our_key in PER_GAME_STATS.items():
            m = re.search(rf'data-stat="{data_stat}"[^>]*>([^<]*)', row_html)
            if m:
                val = m.group(1).strip()
                try:
                    stats[our_key] = float(val)
                except ValueError:
                    stats[our_key] = 0.0
            else:
                stats[our_key] = 0.0

        season_rows.append(stats)

    if not season_rows:
        return None

    # Pick target season or last season
    if target_season:
        for sr in season_rows:
            if sr["season"] == target_season:
                return sr
        # Try partial match
        for sr in season_rows:
            if target_season[:4] in sr["season"]:
                return sr

    # Return last season with GP > 0
    for sr in reversed(season_rows):
        if sr.get("gp", 0) > 0:
            return sr

    return season_rows[-1] if season_rows else None


def get_all_seasons(html):
    """Extract ALL seasons from a player page for verification."""
    table_match = re.search(
        r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
        html, re.DOTALL
    )
    if not table_match:
        comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
        for comment in comments:
            table_match = re.search(
                r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
                comment, re.DOTALL
            )
            if table_match:
                break
    if not table_match:
        return []

    table_html = table_match.group(1)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

    seasons = []
    for row_html in rows:
        season_m = re.search(r'data-stat="season"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
        if not season_m:
            continue
        season = season_m.group(1).strip()
        if not season or season == "Career":
            continue

        team_m = re.search(r'data-stat="team_id"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
        team = team_m.group(1).strip() if team_m else ""

        gp_m = re.search(r'data-stat="g"[^>]*>([^<]*)', row_html)
        gp = gp_m.group(1).strip() if gp_m else "0"

        pts_m = re.search(r'data-stat="pts"[^>]*>([^<]*)', row_html)
        pts = pts_m.group(1).strip() if pts_m else "0"

        seasons.append(f"{season} at {team} (GP={gp}, ppg={pts})")

    return seasons


def scrape_player(name, college, draft_year):
    """Scrape a single player's college stats.

    Returns dict with stats or None if not found.
    """
    slug = name_to_url_slug(name)

    # Try URL variants: -1, -2, -3
    for suffix in range(1, 5):
        url = f"https://www.sports-reference.com/cbb/players/{slug}-{suffix}.html"
        html = fetch_page(url)
        if html is None:
            continue

        # Verify this is the right player by checking school name
        if college:
            college_lower = college.lower()
            # Check if the page mentions the school
            page_lower = html.lower()
            # Try several forms of the school name
            school_parts = college_lower.split()
            if any(part in page_lower for part in school_parts if len(part) > 3):
                # Found a match
                pass
            else:
                # Wrong player, try next suffix
                continue

        # Get the target season: draft_year corresponds to the season ending that year
        # e.g. draft 2022 -> 2021-22 season
        target = f"{draft_year - 1}-{str(draft_year)[-2:]}"
        stats = parse_player_page(html, target_season=target)

        if stats:
            stats["url"] = url
            stats["all_seasons"] = get_all_seasons(html)
            return stats

    # If direct URL fails, try search
    print(f"    Direct URL failed, trying search for {name}...")
    time.sleep(3)
    slug = search_player(name)
    if slug:
        url = f"https://www.sports-reference.com/cbb/players/{slug}.html"
        html = fetch_page(url)
        if html:
            target = f"{draft_year - 1}-{str(draft_year)[-2:]}"
            stats = parse_player_page(html, target_season=target)
            if stats:
                stats["url"] = url
                stats["all_seasons"] = get_all_seasons(html)
                return stats

    return None


def get_players_to_scrape():
    """Build list of players that need college stats scraped."""
    import zipfile
    import pandas as pd
    from config import ZIP_PATH, ZIP_FILES
    from pipeline.build_player_db import normalize_name, NAME_ALIASES

    with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
        db = json.load(f)

    with zipfile.ZipFile(ZIP_PATH) as z:
        with z.open(ZIP_FILES["college"]) as f:
            college = pd.read_csv(f, low_memory=False)

    college["year"] = pd.to_numeric(college["year"], errors="coerce")
    college = college.dropna(subset=["year"])

    # Group 1: Players with no college stats at all (2022-2023 drafts)
    no_stats = [p for p in db if not p.get("has_college_stats")
                and p.get("draft_year") in (2021, 2022, 2023)]

    # Group 2: Players with college stats but from early seasons (CSV cutoff)
    early_stats = []
    college["_norm"] = college["player_name"].apply(
        lambda x: normalize_name(str(x)) if pd.notna(x) else "")
    for p in db:
        if not p.get("has_college_stats"):
            continue
        dy = p.get("draft_year")
        if dy not in (2020, 2021, 2022, 2023):
            continue

        norm = normalize_name(p["name"])
        alias = NAME_ALIASES.get(p["name"])
        alias_norm = normalize_name(alias) if alias else None

        mask = college["_norm"] == norm
        if alias_norm:
            mask = mask | (college["_norm"] == alias_norm)
        rows = college[mask]

        if len(rows) == 0:
            continue

        latest_year = int(rows["year"].max())
        if dy - latest_year > 0:
            early_stats.append(p)

    # Combine and deduplicate
    names_seen = set()
    players = []
    for p in no_stats + early_stats:
        if p["name"] not in names_seen:
            names_seen.add(p["name"])
            players.append({
                "name": p["name"],
                "college": p.get("college", ""),
                "draft_year": p.get("draft_year"),
                "draft_pick": p.get("draft_pick"),
                "has_existing": p.get("has_college_stats", False),
            })

    players.sort(key=lambda x: (x["draft_year"] or 0, x.get("draft_pick") or 99))
    return players


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Load existing results for resume support
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            data = json.load(f)
            existing = {p["name"]: p for p in data}
        print(f"Resuming: {len(existing)} players already scraped")

    players = get_players_to_scrape()
    print(f"\nPlayers to scrape: {len(players)}")

    remaining = [p for p in players if p["name"] not in existing]
    print(f"Remaining (not yet scraped): {len(remaining)}")

    if not remaining:
        print("All players already scraped!")
        return

    print(f"\nScraping Sports Reference college pages...")
    print(f"Rate limit: 3s between requests")
    print()

    success = 0
    failed = []

    for i, p in enumerate(remaining):
        name = p["name"]
        college = p["college"]
        draft_year = p["draft_year"] or 2022

        print(f"  [{i+1}/{len(remaining)}] {name} ({college}, draft {draft_year})...", end=" ")

        try:
            stats = scrape_player(name, college, draft_year)
            if stats:
                result = {
                    "name": name,
                    "college": college,
                    "draft_year": draft_year,
                    "draft_pick": p.get("draft_pick"),
                    "scraped_stats": stats,
                }
                existing[name] = result
                success += 1
                print(f"OK - {stats.get('season','')} at {stats.get('team','')}, "
                      f"ppg={stats.get('pts',0)}, gp={stats.get('gp',0)}")
            else:
                failed.append(name)
                print("FAILED - not found")
        except Exception as e:
            failed.append(name)
            print(f"ERROR - {e}")

        # Save after each player (resume-safe)
        with open(OUTPUT_PATH, "w") as f:
            json.dump(list(existing.values()), f, indent=2)

        # Rate limit
        if i < len(remaining) - 1:
            time.sleep(3)

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Scraped: {success}")
    print(f"  Failed:  {len(failed)}")
    print(f"  Total in file: {len(existing)}")

    if failed:
        print(f"\n  Failed players:")
        for name in failed:
            print(f"    {name}")

    print(f"\n  Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
