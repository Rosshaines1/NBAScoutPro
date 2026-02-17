"""Quick test: why are scrapes failing?"""
import urllib.request, re

url = "https://www.sports-reference.com/cbb/players/stephen-curry-1.html"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NBAScoutPro research)"})
resp = urllib.request.urlopen(req, timeout=20)
html = resp.read().decode("utf-8", errors="replace")

print("Page length: %d chars" % len(html))

# School check
for word in ["Davidson", "davidson"]:
    if word in html:
        print("Found '%s' in HTML" % word)

# Table check
if "players_per_game" in html:
    print("players_per_game table found in HTML directly")
else:
    print("players_per_game NOT in direct HTML")
    comments = re.findall(r"<!--(.*?)-->", html, re.DOTALL)
    print("Found %d HTML comments" % len(comments))
    for i, c in enumerate(comments):
        if "players_per_game" in c:
            print("  Found players_per_game in comment #%d (len=%d)" % (i, len(c)))
            # Extract a sample row
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", c, re.DOTALL)
            print("  %d rows in table" % len(rows))
            for r in rows[:3]:
                season_m = re.search(r'data-stat="season"[^>]*>(?:<a[^>]*>)?([^<]*)', r)
                if season_m:
                    print("    Season: %s" % season_m.group(1).strip())
            break
    else:
        print("  NOT found in comments either")

# Also check: does the school validation pass?
college = "Davidson"
college_lower = college.lower()
parts = college_lower.split()
matching_parts = [part for part in parts if len(part) > 3 and part in html.lower()]
print("School validation parts > 3 chars: %s" % parts)
print("Matching parts in HTML: %s" % matching_parts)
