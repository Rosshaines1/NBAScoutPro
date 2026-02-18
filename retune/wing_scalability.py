"""Wing scalability analysis.

Hypothesis: wings who succeed in the NBA have "scalable" games —
efficient at moderate usage, shoot 3s, don't rely on getting to the line.
Wings who bust are high-usage, high-FTR, volume scorers whose game
doesn't translate when they can't dominate the ball.

Let's test: eFG% at given USG, 3PA volume, FTR as negative signal for wings.
"""
import json, sys, math

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from config import PLAYER_DB_PATH

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

clean = [p for p in db if p.get('has_college_stats')
         and 2009 <= (p.get('draft_year') or 0) <= 2019
         and p.get('nba_ws') is not None
         and p['pos'] == 'W']

# Define a "scalability" score for wings
# Positive: eFG% (efficiency translates), 3PA volume (shooting translates), lower USG (not ball-dominant)
# Negative: high FTR without efficiency (relying on fouls), high USG without proportional eFG

def wing_scalability(p):
    s = p['stats']
    efg = s.get('fg', 45) or 45
    usg = s.get('usg', 25) or 25
    tpa = s.get('tpa', 0) or 0
    ftr = s.get('ftr', 30) or 30
    ppg = s.get('ppg', 10) or 10

    # eFG per point of USG — are you efficient relative to how much you use?
    efg_per_usg = efg / usg if usg > 0 else 0

    # 3PA volume — does this wing actually shoot?
    three_volume = min(tpa / 5.0, 1.5)  # cap at 7.5 3PA

    # FTR penalty — wings who rely on fouls tend to bust
    # But FTR below 35 is fine, it's the 45%+ that's a red flag for wings
    ftr_penalty = max(0, (ftr - 35) / 25)  # 0 at 35, 1.0 at 60

    # Scoring efficiency: PPG / USG — are you scoring proportionally?
    ppg_per_usg = ppg / usg if usg > 0 else 0

    return {
        'efg_per_usg': efg_per_usg,
        'three_volume': three_volume,
        'ftr_penalty': ftr_penalty,
        'ppg_per_usg': ppg_per_usg,
        'scalability': efg_per_usg * 2 + three_volume - ftr_penalty * 0.5,
    }


# Score all wings
results = []
for p in clean:
    s = p['stats']
    sc = wing_scalability(p)
    results.append({
        'name': p['name'], 'tier': p['tier'],
        'ppg': s.get('ppg', 0), 'efg': s.get('fg', 0),
        'usg': s.get('usg', 0), 'tpa': s.get('tpa', 0),
        'ftr': s.get('ftr', 0), 'bpm': s.get('bpm', 0),
        'ft': s.get('ft', 0), 'apg': s.get('apg', 0),
        'age': p.get('age', 4), 'quadrant': p.get('quadrant', '?'),
        'nba_ws': p.get('nba_ws', 0),
        'draft_pick': p.get('draft_pick', 0),
        **sc,
    })

# Correlation: scalability vs tier
tiers = [r['tier'] for r in results]
scales = [r['scalability'] for r in results]
n = len(results)
mean_t = sum(tiers) / n
mean_s = sum(scales) / n
cov = sum((t - mean_t) * (s - mean_s) for t, s in zip(tiers, scales)) / n
std_t = (sum((t - mean_t)**2 for t in tiers) / n) ** 0.5
std_s = (sum((s - mean_s)**2 for s in scales) / n) ** 0.5
corr = cov / (std_t * std_s) if std_t * std_s else 0
print(f"Wings in dataset: {n}")
print(f"Scalability vs tier correlation: r = {corr:.3f}")
print(f"(Negative = higher scalability → lower tier number → better)")

# Same for components
for label, key in [('eFG/USG', 'efg_per_usg'), ('3PA volume', 'three_volume'),
                    ('FTR penalty', 'ftr_penalty'), ('PPG/USG', 'ppg_per_usg')]:
    vals = [r[key] for r in results]
    mean_v = sum(vals) / n
    cov_v = sum((t - mean_t) * (v - mean_v) for t, v in zip(tiers, vals)) / n
    std_v = (sum((v - mean_v)**2 for v in vals) / n) ** 0.5
    corr_v = cov_v / (std_v * std_t) if std_v * std_t else 0
    print(f"  {label:15s}: r = {corr_v:+.3f}")

# By tier: average scalability
print(f"\n=== SCALABILITY BY TIER (wings only) ===")
for t in range(1, 6):
    group = [r for r in results if r['tier'] == t]
    if group:
        avg_sc = sum(r['scalability'] for r in group) / len(group)
        avg_efg_usg = sum(r['efg_per_usg'] for r in group) / len(group)
        avg_3v = sum(r['three_volume'] for r in group) / len(group)
        avg_ftr = sum(r['ftr_penalty'] for r in group) / len(group)
        avg_ppg_usg = sum(r['ppg_per_usg'] for r in group) / len(group)
        print(f"  Tier {t}: scalability={avg_sc:.2f}  eFG/USG={avg_efg_usg:.2f}  3PA_vol={avg_3v:.2f}  FTR_pen={avg_ftr:.2f}  PPG/USG={avg_ppg_usg:.2f}  (n={len(group)})")

# Key players
print(f"\n=== KEY WING PROFILES ===")
print(f"{'Name':25s} {'Tier':>4s} {'PPG':>5s} {'eFG':>5s} {'USG':>5s} {'3PA':>5s} {'FTR':>5s} {'FT%':>5s} {'BPM':>5s} {'eFG/U':>6s} {'3Pvol':>6s} {'FTRp':>5s} {'Scale':>6s} {'Age':>3s} {'Quad':>4s}")
print("-" * 130)

key_names = ['Paul George', 'Gordon Hayward', 'Kawhi Leonard', 'Klay Thompson',
             'James Harden', 'Mikal Bridges', 'Zion Williamson', 'Lonzo Ball',
             'Jimmy Butler', 'Jamal Murray', 'John Wall',
             '---',
             'Dominique Jones', 'Derrick Williams', 'Jarrett Culver', 'Landry Fields',
             'Josh Jackson', 'Stanley Johnson', 'Caleb Swanigan', 'Chandler Hutchison',
             'Damion James', 'Royce White', 'Jarnell Stokes', 'Kris Dunn',
             'Jordan Hamilton', 'Xavier Henry', 'Chuma Okeke', 'P.J. Hairston']

for name in key_names:
    if name == '---':
        print(f"\n  --- FALSE STAR WINGS ---")
        continue
    r = next((x for x in results if x['name'] == name), None)
    if r:
        marker = "**" if r['tier'] <= 2 else "  " if r['tier'] == 3 else "!!" if r['tier'] >= 4 else ""
        print(f"{marker}{r['name']:23s} T{r['tier']}  {r['ppg']:>5.1f} {r['efg']:>5.1f} {r['usg']:>5.0f} {r['tpa']:>5.1f} {r['ftr']:>5.0f} {r['ft']:>5.0f} {r['bpm']:>5.1f} {r['efg_per_usg']:>6.2f} {r['three_volume']:>6.2f} {r['ftr_penalty']:>5.2f} {r['scalability']:>6.2f}  {r['age']} {r['quadrant']:>4s}")

# What thresholds separate?
print(f"\n\n=== THRESHOLD ANALYSIS: eFG/USG ===")
for thresh in [1.8, 1.9, 2.0, 2.1, 2.2, 2.3]:
    above = [r for r in results if r['efg_per_usg'] >= thresh]
    below = [r for r in results if r['efg_per_usg'] < thresh]
    if above and below:
        a_star = sum(1 for r in above if r['tier'] <= 2) / len(above) * 100
        b_star = sum(1 for r in below if r['tier'] <= 2) / len(below) * 100
        a_bust = sum(1 for r in above if r['tier'] >= 4) / len(above) * 100
        b_bust = sum(1 for r in below if r['tier'] >= 4) / len(below) * 100
        print(f"  eFG/USG >= {thresh:.1f}: star={a_star:>4.0f}%  bust={a_bust:>4.0f}%  (n={len(above)})   |   < {thresh:.1f}: star={b_star:>4.0f}%  bust={b_bust:>4.0f}%  (n={len(below)})")

print(f"\n=== THRESHOLD ANALYSIS: FTR (wings only) ===")
for thresh in [35, 40, 45, 50, 55]:
    above = [r for r in results if r['ftr'] >= thresh]
    below = [r for r in results if r['ftr'] < thresh and r['ftr'] > 0]
    if above and below:
        a_star = sum(1 for r in above if r['tier'] <= 2) / len(above) * 100
        b_star = sum(1 for r in below if r['tier'] <= 2) / len(below) * 100
        a_bust = sum(1 for r in above if r['tier'] >= 4) / len(above) * 100
        b_bust = sum(1 for r in below if r['tier'] >= 4) / len(below) * 100
        print(f"  FTR >= {thresh:>2}: star={a_star:>4.0f}%  bust={a_bust:>4.0f}%  (n={len(above)})   |   < {thresh}: star={b_star:>4.0f}%  bust={b_bust:>4.0f}%  (n={len(below)})")

print(f"\n=== THRESHOLD ANALYSIS: 3PA/G (wings only) ===")
for thresh in [2.0, 3.0, 4.0, 5.0, 6.0]:
    above = [r for r in results if r['tpa'] >= thresh]
    below = [r for r in results if r['tpa'] < thresh]
    if above and below:
        a_star = sum(1 for r in above if r['tier'] <= 2) / len(above) * 100
        b_star = sum(1 for r in below if r['tier'] <= 2) / len(below) * 100
        a_bust = sum(1 for r in above if r['tier'] >= 4) / len(above) * 100
        b_bust = sum(1 for r in below if r['tier'] >= 4) / len(below) * 100
        print(f"  3PA >= {thresh:.1f}: star={a_star:>4.0f}%  bust={a_bust:>4.0f}%  (n={len(above)})   |   < {thresh:.1f}: star={b_star:>4.0f}%  bust={b_bust:>4.0f}%  (n={len(below)})")

# Combo check: high USG + low eFG (empty volume) vs moderate USG + high eFG (scalable)
print(f"\n=== COMBO: USG vs eFG QUADRANTS (wings only) ===")
combos = [
    ("High USG + High eFG", lambda r: r['usg'] >= 27 and r['efg'] >= 55),
    ("High USG + Low eFG",  lambda r: r['usg'] >= 27 and r['efg'] < 55),
    ("Low USG + High eFG",  lambda r: r['usg'] < 27 and r['efg'] >= 55),
    ("Low USG + Low eFG",   lambda r: r['usg'] < 27 and r['efg'] < 55),
]
for label, fn in combos:
    group = [r for r in results if fn(r) and r['usg'] > 0]
    if group:
        star = sum(1 for r in group if r['tier'] <= 2) / len(group) * 100
        bust = sum(1 for r in group if r['tier'] >= 4) / len(group) * 100
        avg_ws = sum(r['nba_ws'] for r in group) / len(group)
        print(f"  {label:25s}: star={star:>4.0f}%  bust={bust:>4.0f}%  avg_ws={avg_ws:>5.1f}  (n={len(group)})")

# What about wings with high FTR + low eFG (the "can't score, draws fouls" profile)?
print(f"\n=== RED FLAG COMBO: High FTR + Low eFG (wings only) ===")
combos2 = [
    ("FTR>=45 + eFG<55",   lambda r: r['ftr'] >= 45 and r['efg'] < 55),
    ("FTR>=45 + eFG>=55",  lambda r: r['ftr'] >= 45 and r['efg'] >= 55),
    ("FTR<45 + eFG<55",    lambda r: r['ftr'] < 45 and r['ftr'] > 0 and r['efg'] < 55),
    ("FTR<45 + eFG>=55",   lambda r: r['ftr'] < 45 and r['ftr'] > 0 and r['efg'] >= 55),
]
for label, fn in combos2:
    group = [r for r in results if fn(r)]
    if group:
        star = sum(1 for r in group if r['tier'] <= 2) / len(group) * 100
        bust = sum(1 for r in group if r['tier'] >= 4) / len(group) * 100
        print(f"  {label:25s}: star={star:>4.0f}%  bust={bust:>4.0f}%  (n={len(group)})")
