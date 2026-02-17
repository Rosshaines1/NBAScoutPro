# NBAScoutPro V4 Plan: Archetypes + Floor/Ceiling

## Problem Statement
- Single-tier prediction has false precision (college stats explain ~21% of NBA outcomes)
- Current similarity engine finds "statistically similar" players regardless of play style
- Comps are meaningless when a scoring guard gets matched with a defensive big
- Scouts think in ranges (floor/ceiling), not point estimates

## V4 Architecture

### 1. Archetype Classification System

Replace G/W/B with 6-7 data-driven archetypes. Each player gets classified
by their statistical profile using thresholds on stats we already have.

**Proposed Archetypes (6):**

| # | Archetype | Classification Logic |
|---|-----------|---------------------|
| 1 | **Scoring Guard** | G + (PPG ≥ 16 OR USG ≥ 27) + FTA/game ≥ 4 |
| 2 | **Playmaking Guard** | G + APG ≥ 4 + ATO ≥ 1.5 (pass-first) |
| 3 | **3&D Wing** | W + (3P% ≥ 33 OR FT% ≥ 75) + SPG ≥ 1.0 + PPG < 18 |
| 4 | **Scoring Wing** | W + (PPG ≥ 15 OR USG ≥ 25) |
| 5 | **Skilled Big** | B + FT% ≥ 70 OR 3P% ≥ 30 (can shoot) |
| 6 | **Athletic Big** | B + FT% < 70 AND dunks > 20 OR BPG ≥ 1.5 (rim protector) |

*Fallback: if a player doesn't clearly fit, use closest match by distance.*

**Sample size check needed:** Run classification on all 802 players, verify
each archetype has 80+ members. Adjust thresholds if any bucket is too
small or too large.

**Overlap handling:** Some players fit multiple (e.g., scoring + playmaking
guard). Use primary archetype based on strongest signal, but store secondary.

### 2. Archetype-Specific Similarity Weights

Instead of one universal weight set, each archetype gets its own weights
emphasizing the stats that matter for that play style:

- **Scoring Guard:** PPG↑, FTA↑, USG↑, FT%↑, 3P%↑ (shot creation matters)
- **Playmaking Guard:** APG↑, ATO↑, STL%↑, TPG↓ (passing + defense)
- **3&D Wing:** 3P%↑, SPG↑, FT%↑, BPG↑ (shooting + defense)
- **Scoring Wing:** PPG↑, FTA↑, USG↑, height↑ (size + scoring)
- **Skilled Big:** FT%↑, BPM↑, RPG↑, height↑, 3P%↑ (skill + size)
- **Athletic Big:** DBPM↑, BPG↑, dunks↑, RPG↑ (defense + physicality)

### 3. Floor/Ceiling Output

For a prospect:
1. Classify into archetype
2. Find top-10 comps WITHIN that archetype (same-style matching)
3. Output:
   - **Ceiling:** Best tier among top-5 same-archetype comps (+ name)
   - **Floor:** Worst tier among top-5 same-archetype comps (+ name)
   - **Most Likely:** Median tier of top-5 comps
   - **Model Prediction:** predict_tier() score as additional signal
   - **Confidence:** Width of floor-ceiling range (narrow = more certain)

Example output:
```
Cooper Flagg — Scoring Wing
  Ceiling: T1 Superstar (comp: Paul George, 93%)
  Most Likely: T2 All-Star
  Floor: T3 Starter (comp: Tobias Harris, 91%)
  Model Score: 78/120 — leans T1-T2
  Star Signals: 6/8 | Unicorn: defensive_unicorn
```

### 4. predict_tier() Rules (from today's work)

Keep the rules we validated today as the "model prediction" overlay:
- Draft position penalty (late picks)
- Conference-adjusted BPM/OBPM
- FTA per game (rate not volume)
- FT% by position
- Athlete-without-skill flag (G/W only)
- BPM ceiling reduction

Plus two new rules to test:
- FT% + BPM combo bonus (for low-MPG stars like Booker, Turner)
- Reduced Low Major penalty when BPM is strong (for PG, Lillard types)

## Implementation Order

### Phase 1: Archetype System
1. Write archetype classifier function
2. Run on full DB, check bucket sizes, tune thresholds
3. Validate: do known players land in sensible archetypes?

### Phase 2: Archetype-Specific Weights
4. Define per-archetype weight sets
5. Modify similarity engine to use archetype weights
6. Backtest: do same-archetype comps improve accuracy?

### Phase 3: Floor/Ceiling Output
7. Modify find_top_matches to filter by archetype
8. Build floor/ceiling/most-likely calculation
9. Update Streamlit UI to show range instead of single prediction

### Phase 4: Integration + Polish
10. Wire predict_tier() rules into the output as "model lean"
11. Run full backtest with new system
12. Compare V4 vs V3 accuracy across all metrics

## Open Questions
- Should archetype assignment be hard (one bucket) or soft (probabilities)?
- Should floor/ceiling use top-5 or top-10 comps?
- How to handle prospects whose archetype has very few high-tier players?
  (e.g., Athletic Big ceiling may be capped because very few become T1)
- Do we want cross-archetype comps as a secondary view? ("closest player
  in a different archetype")

## What We Learned Today (Rules Session)
- Original predict_tier: 18.7% exact, 46.8% within-1
- After rules: 34.6% exact, 69.2% within-1 (+85% and +48% improvement)
- False positives: 200 → 86 (-57%)
- FT% is the strongest separator between lottery stars and busts (+10% gap)
- FTA/game rate > raw FTA volume (corrects for seniors playing 39 games)
- Draft position penalty works well for late picks, bonus backfires for lottery
- College BPM is inflated at lower conferences — apply level modifier
- Dunks + bad FT% in guards/wings = bust signal
- 8 players have bad data (wrong name match in pipeline)
- ~10 players are genuinely unpredictable from college stats (DeRozan)
- 18 missed stars are potentially fixable with better archetype matching
