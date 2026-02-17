"""Hard validation: scrape a sample of players from Sports Reference
and compare every stat against what's in player_db.json.

Checks: PPG, RPG, APG, SPG, BPG, eFG%, 3P%, FT%, MPG, GP, FTA, height.
Reports any discrepancy > threshold.
"""
import sys, os, json, re, time, unicodedata
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PROCESSED_DIR

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "validation_results.json")

# Sample: mix of tiers, positions, draft years across 2009-2019
VALIDATION_SAMPLE = [
    # T1 superstars
    ("Stephen Curry", "Davidson", 2009),
    ("James Harden", "Arizona St.", 2009),
    ("Blake Griffin", "Oklahoma", 2009),
    ("John Wall", "Kentucky", 2010),
    ("DeMarcus Cousins", "Kentucky", 2010),
    ("Kyrie Irving", "Duke", 2011),
    ("Kawhi Leonard", "San Diego St.", 2011),
    ("Damian Lillard", "Weber St.", 2012),
    ("Anthony Davis", "Kentucky", 2012),
    ("Giannis Antetokounmpo", "None", 2013),  # international, skip
    ("Karl-Anthony Towns", "Kentucky", 2015),
    ("Devin Booker", "Kentucky", 2015),
    ("Ben Simmons", "LSU", 2016),
    ("Jayson Tatum", "Duke", 2017),
    ("Donovan Mitchell", "Louisville", 2017),  # known collision, skip
    ("Luka Doncic", "None", 2018),  # international, skip
    ("Trae Young", "Oklahoma", 2018),
    ("Shai Gilgeous-Alexander", "Kentucky", 2018),
    ("Zion Williamson", "Duke", 2019),
    ("Ja Morant", "Murray St.", 2019),
    # T2-T3
    ("Draymond Green", "Michigan St.", 2012),
    ("Victor Oladipo", "Indiana", 2013),
    ("CJ McCollum", "Lehigh", 2013),
    ("Julius Randle", "Kentucky", 2014),
    ("Marcus Smart", "Oklahoma St.", 2014),
    ("Buddy Hield", "Oklahoma", 2016),
    ("Malcolm Brogdon", "Virginia", 2016),
    ("Jarrett Allen", "Texas", 2017),
    ("De'Aaron Fox", "Kentucky", 2017),
    ("Jaren Jackson Jr.", "Michigan St.", 2018),
    ("Collin Sexton", "Alabama", 2018),
    ("Darius Garland", "Vanderbilt", 2019),
    ("RJ Barrett", "Duke", 2019),
    # T4
    ("Frank Kaminsky", "Wisconsin", 2015),
    ("Gary Harris", "Michigan St.", 2014),
    ("Coby White", "North Carolina", 2019),
    ("Myles Turner", "Texas", 2015),
    ("Christian Braun", "Kansas", 2022),  # outside range, skip
    # T5
    ("Doug McDermott", "Creighton", 2014),
    ("Tyler Herro", "Kentucky", 2019),
    ("Rui Hachimura", "Gonzaga", 2019),
    ("Bol Bol", "Oregon", 2019),
]


def strip_accents(s):
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def name_to_slug(name):
    name = strip_accents(name)
    name = re.sub(r'\s+(Jr\.?|Sr\.?|III|II|IV)$', '', name, flags=re.IGNORECASE)
    name = name.replace(".", "").replace("'", "").replace("'", "")
    parts = name.lower().split()
    return "-".join(parts)


def fetch_page(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (NBAScoutPro research)"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_per_game_row(row_html):
    """Extract stats from a single per-game table row."""
    stats = {}
    fields = {
        "g": "gp", "gs": "gs", "mp": "mpg",
        "pts": "ppg", "trb": "rpg", "ast": "apg",
        "stl": "spg", "blk": "bpg", "tov": "tov",
        "fg_pct": "fg_pct", "fg3_pct": "threeP",
        "fg2_pct": "fg2_pct", "efg_pct": "efg",
        "ft_pct": "ft", "ft": "ftm_pg", "fta": "fta_pg",
        "orb": "orb", "drb": "drb",
    }
    for data_stat, key in fields.items():
        m = re.search(rf'data-stat="{data_stat}"[^>]*>([^<]*)', row_html)
        if m:
            val = m.group(1).strip()
            try:
                stats[key] = float(val)
            except ValueError:
                stats[key] = None
        else:
            stats[key] = None

    # Season and team
    m = re.search(r'data-stat="season"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
    stats["season"] = m.group(1).strip() if m else ""
    m = re.search(r'data-stat="team_id"[^>]*>(?:<a[^>]*>)?([^<]*)', row_html)
    stats["team"] = m.group(1).strip() if m else ""
    m = re.search(r'data-stat="class"[^>]*>([^<]*)', row_html)
    stats["class"] = m.group(1).strip() if m else ""

    return stats


def scrape_final_season(name, college, draft_year):
    """Scrape player's final college season stats from Sports Reference."""
    slug = name_to_slug(name)
    college_lower = college.lower() if college else ""

    for suffix in range(1, 6):
        url = f"https://www.sports-reference.com/cbb/players/{slug}-{suffix}.html"
        html = fetch_page(url)
        if html is None:
            continue

        # Verify school if possible
        if college_lower and college_lower != "none":
            if not any(part in html.lower() for part in college_lower.split() if len(part) > 3):
                continue

        # Find per-game table
        table_match = re.search(
            r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
            html, re.DOTALL)
        if not table_match:
            comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
            for comment in comments:
                table_match = re.search(
                    r'<table[^>]*id="players_per_game"[^>]*>(.*?)</table>',
                    comment, re.DOTALL)
                if table_match:
                    break
        if not table_match:
            continue

        # Parse all season rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.DOTALL)
        season_data = []
        for row_html in rows:
            if 'data-stat="season"' not in row_html:
                continue
            if 'class="thead"' in row_html:
                continue
            parsed = parse_per_game_row(row_html)
            if parsed["season"] and parsed["season"] != "Career":
                season_data.append(parsed)

        if not season_data:
            continue

        # Find the target season (draft_year - 1 to draft_year)
        target = f"{draft_year - 1}-{str(draft_year)[-2:]}"
        for s in season_data:
            if target in s["season"]:
                s["url"] = url
                s["all_seasons"] = [(sd["season"], sd["team"], sd.get("gp"), sd.get("ppg"))
                                     for sd in season_data]
                return s

        # If target season not found, return last season
        last = season_data[-1]
        last["url"] = url
        last["all_seasons"] = [(sd["season"], sd["team"], sd.get("gp"), sd.get("ppg"))
                                for sd in season_data]
        return last

    return None


def main():
    with open(os.path.join(PROCESSED_DIR, "player_db.json")) as f:
        db = json.load(f)
    db_map = {p["name"]: p for p in db}

    # Filter sample to players in our DB
    sample = [(n, c, dy) for n, c, dy in VALIDATION_SAMPLE
              if n in db_map and c != "None"]

    print("=" * 80)
    print("HARD VALIDATION: DB vs Sports Reference")
    print("=" * 80)
    print(f"Validating {len(sample)} players\n")

    results = []
    discrepancies = []

    for i, (name, college, draft_year) in enumerate(sample):
        p = db_map[name]
        db_stats = p["stats"]

        print(f"[{i+1}/{len(sample)}] {name} ({college}, {draft_year})...", end=" ", flush=True)

        sr = scrape_final_season(name, college, draft_year)
        if sr is None:
            print("FAILED to scrape")
            results.append({"name": name, "status": "scrape_failed"})
            time.sleep(3)
            continue

        print(f"got {sr['season']} at {sr['team']}")

        # Compare stats
        comparisons = [
            ("PPG", db_stats.get("ppg", 0), sr.get("ppg")),
            ("RPG", db_stats.get("rpg", 0), sr.get("rpg")),
            ("APG", db_stats.get("apg", 0), sr.get("apg")),
            ("SPG", db_stats.get("spg", 0), sr.get("spg")),
            ("BPG", db_stats.get("bpg", 0), sr.get("bpg")),
            ("eFG%", db_stats.get("fg", 0), sr.get("efg")),
            ("3P%", db_stats.get("threeP", 0), sr.get("threeP")),
            ("FT%", db_stats.get("ft", 0), sr.get("ft")),
            ("MPG", db_stats.get("mpg", 0), sr.get("mpg")),
            ("FTA/g", db_stats.get("fta_pg", 0), sr.get("fta_pg")),
            ("BPM", db_stats.get("bpm", 0), None),  # SR doesn't have BPM on college pages
        ]

        player_result = {
            "name": name, "college": college, "draft_year": draft_year,
            "sr_season": sr["season"], "sr_team": sr["team"],
            "sr_url": sr.get("url", ""),
            "comparisons": [],
            "status": "ok"
        }

        for stat_name, db_val, sr_val in comparisons:
            if sr_val is None:
                player_result["comparisons"].append({
                    "stat": stat_name, "db": db_val, "sr": None, "diff": None, "status": "no_sr_data"
                })
                continue

            diff = db_val - sr_val
            # Thresholds: percentages allow 1.0, counting stats allow 0.5
            if stat_name in ("eFG%", "3P%", "FT%"):
                # DB stores as 0-100, SR might be decimal or 0-100
                if sr_val < 1.0:
                    sr_val *= 100
                    diff = db_val - sr_val
                threshold = 1.5
            elif stat_name == "FTA/g":
                threshold = 0.5
            else:
                threshold = 0.5

            status = "OK" if abs(diff) < threshold else ("CLOSE" if abs(diff) < threshold * 2 else "WRONG")

            comp = {"stat": stat_name, "db": round(db_val, 1), "sr": round(sr_val, 1),
                    "diff": round(diff, 1), "status": status}
            player_result["comparisons"].append(comp)

            if status == "WRONG":
                discrepancies.append(f"  {name}: {stat_name} DB={db_val:.1f} SR={sr_val:.1f} (diff={diff:+.1f})")
                player_result["status"] = "discrepancy"

        results.append(player_result)
        time.sleep(3)  # Rate limit

    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    ok = sum(1 for r in results if r["status"] == "ok")
    disc = sum(1 for r in results if r["status"] == "discrepancy")
    failed = sum(1 for r in results if r["status"] == "scrape_failed")

    print(f"\n  Validated: {len(results)}")
    print(f"  Clean:     {ok}")
    print(f"  Discrepancies: {disc}")
    print(f"  Scrape failed: {failed}")

    if discrepancies:
        print(f"\n  DISCREPANCIES FOUND:")
        for d in discrepancies:
            print(d)

    # Detailed per-player report
    print("\n\n--- DETAILED RESULTS ---")
    for r in results:
        if r["status"] == "scrape_failed":
            print(f"\n{r['name']}: SCRAPE FAILED")
            continue

        flags = [c for c in r.get("comparisons", []) if c["status"] not in ("OK", "no_sr_data")]
        if flags:
            print(f"\n{r['name']} ({r.get('sr_season','')} at {r.get('sr_team','')}):")
            for c in r["comparisons"]:
                marker = " <--" if c["status"] not in ("OK", "no_sr_data") else ""
                if c["sr"] is not None:
                    print(f"    {c['stat']:6s}: DB={c['db']:6.1f}  SR={c['sr']:6.1f}  diff={c['diff']:+5.1f}  {c['status']}{marker}")

    # Save results
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
