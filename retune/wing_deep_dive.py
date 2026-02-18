"""Deep dive: false star wings vs true star wings.
Look for ANY statistical pattern that separates them."""
import json, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from config import PLAYER_DB_PATH, POSITIONAL_AVGS_PATH, POSITIONAL_AVGS
from app.similarity import predict_tier

with open(PLAYER_DB_PATH) as f:
    db = json.load(f)

pos_avgs = POSITIONAL_AVGS
try:
    with open(POSITIONAL_AVGS_PATH) as f:
        pos_avgs = json.load(f)
except: pass

clean = [p for p in db if p.get('has_college_stats')
         and 2009 <= (p.get('draft_year') or 0) <= 2019
         and p.get('nba_ws') is not None]

false_wings = []
true_wings = []

for p in clean:
    s = p["stats"]
    prospect = {
        "name": p["name"], "pos": p["pos"], "h": p["h"], "w": p.get("w", 200),
        "ws": p.get("ws", p["h"] + 4), "age": p.get("age", 4),
        "level": p.get("level", "High Major"),
        "quadrant": p.get("quadrant", "Q1"),
        "ath": p.get("ath", 0),
        "ppg": s.get("ppg", 0), "rpg": s.get("rpg", 0), "apg": s.get("apg", 0),
        "spg": s.get("spg", 0), "bpg": s.get("bpg", 0), "tpg": s.get("tpg", 0),
        "fg": s.get("fg", 45), "threeP": s.get("threeP", 0), "ft": s.get("ft", 70),
        "mpg": s.get("mpg", 30), "bpm": s.get("bpm", 0), "obpm": s.get("obpm", 0),
        "dbpm": s.get("dbpm", 0), "fta": s.get("fta", 0),
        "stl_per": s.get("stl_per", 0), "usg": s.get("usg", 0),
        "ftr": s.get("ftr", 0),
        "rim_pct": (s.get("rimmade", 0) / s.get("rim_att", 1) * 100) if s.get("rim_att", 0) > 0 else 0,
        "tpa": s.get("tpa", 0),
    }
    pred = predict_tier(prospect, pos_avgs)

    if p["pos"] != "W":
        continue

    entry = {**prospect, "actual_tier": p["tier"], "pred_tier": pred["tier"],
             "score": pred["score"], "draft_pick": p.get("draft_pick", 0),
             "draft_year": p.get("draft_year", 0),
             "nba_ws": p.get("nba_ws", 0)}

    if pred["tier"] <= 2 and p["tier"] >= 4:
        false_wings.append(entry)
    elif pred["tier"] <= 2 and p["tier"] <= 2:
        true_wings.append(entry)

print(f"False star wings: {len(false_wings)}")
print(f"True star wings:  {len(true_wings)}")

# Deep stat comparison
stats_to_compare = [
    ("Height", "h", ""),
    ("PPG", "ppg", ""),
    ("RPG", "rpg", ""),
    ("APG", "apg", ""),
    ("SPG", "spg", ""),
    ("BPG", "bpg", ""),
    ("eFG%", "fg", "%"),
    ("3P%", "threeP", "%"),
    ("FT%", "ft", "%"),
    ("MPG", "mpg", ""),
    ("USG", "usg", "%"),
    ("BPM", "bpm", ""),
    ("OBPM", "obpm", ""),
    ("DBPM", "dbpm", ""),
    ("FTA/G", "fta", ""),
    ("FTR", "ftr", "%"),
    ("Stl%", "stl_per", "%"),
    ("Rim%", "rim_pct", "%"),
    ("3PA/G", "tpa", ""),
    ("TPG", "tpg", ""),
    ("Age/Yr", "age", ""),
]

print(f"\n{'Stat':12s} {'False':>8s} {'True':>8s} {'Delta':>8s} {'Separation':>12s}")
print("-" * 52)

for label, key, suffix in stats_to_compare:
    f_vals = [f[key] for f in false_wings if f.get(key) is not None]
    t_vals = [f[key] for f in true_wings if f.get(key) is not None]
    if not f_vals or not t_vals:
        continue
    f_avg = sum(f_vals) / len(f_vals)
    t_avg = sum(t_vals) / len(t_vals)
    delta = t_avg - f_avg

    # Cohen's d-ish: delta / pooled stdev
    f_var = sum((v - f_avg)**2 for v in f_vals) / len(f_vals) if len(f_vals) > 1 else 1
    t_var = sum((v - t_avg)**2 for v in t_vals) / len(t_vals) if len(t_vals) > 1 else 1
    pooled_sd = ((f_var + t_var) / 2) ** 0.5
    sep = delta / pooled_sd if pooled_sd > 0.01 else 0

    marker = ""
    if abs(sep) >= 0.5:
        marker = " <-- notable"
    elif abs(sep) >= 0.3:
        marker = " <-"

    print(f"{label:12s} {f_avg:>8.1f} {t_avg:>8.1f} {delta:>+8.1f} {sep:>+10.2f}{marker}")

# Derived metrics
print(f"\n=== DERIVED / RATIO METRICS ===")
print(f"\n{'Stat':25s} {'False':>8s} {'True':>8s} {'Delta':>8s}")
print("-" * 55)

# PPG per USG point (scoring efficiency per usage)
f_ppg_usg = [f['ppg']/f['usg'] if f['usg'] > 0 else 0 for f in false_wings]
t_ppg_usg = [f['ppg']/f['usg'] if f['usg'] > 0 else 0 for f in true_wings]
print(f"{'PPG / USG':25s} {sum(f_ppg_usg)/len(f_ppg_usg):>8.2f} {sum(t_ppg_usg)/len(t_ppg_usg):>8.2f} {sum(t_ppg_usg)/len(t_ppg_usg) - sum(f_ppg_usg)/len(f_ppg_usg):>+8.2f}")

# OBPM - (PPG * 0.3) — offensive impact beyond scoring
f_obpm_adj = [f['obpm'] - f['ppg'] * 0.3 for f in false_wings]
t_obpm_adj = [f['obpm'] - f['ppg'] * 0.3 for f in true_wings]
print(f"{'OBPM - 0.3*PPG':25s} {sum(f_obpm_adj)/len(f_obpm_adj):>8.2f} {sum(t_obpm_adj)/len(t_obpm_adj):>8.2f} {sum(t_obpm_adj)/len(t_obpm_adj) - sum(f_obpm_adj)/len(f_obpm_adj):>+8.2f}")

# BPM / USG — impact per usage
f_bpm_usg = [f['bpm']/f['usg'] if f['usg'] > 0 else 0 for f in false_wings]
t_bpm_usg = [f['bpm']/f['usg'] if f['usg'] > 0 else 0 for f in true_wings]
print(f"{'BPM / USG':25s} {sum(f_bpm_usg)/len(f_bpm_usg):>8.3f} {sum(t_bpm_usg)/len(t_bpm_usg):>8.3f} {sum(t_bpm_usg)/len(t_bpm_usg) - sum(f_bpm_usg)/len(f_bpm_usg):>+8.3f}")

# DBPM / BPM ratio — how much of their impact is defense?
f_dbpm_ratio = [f['dbpm']/f['bpm'] if f['bpm'] > 0 else 0 for f in false_wings]
t_dbpm_ratio = [f['dbpm']/f['bpm'] if f['bpm'] > 0 else 0 for f in true_wings]
print(f"{'DBPM / BPM ratio':25s} {sum(f_dbpm_ratio)/len(f_dbpm_ratio):>8.2f} {sum(t_dbpm_ratio)/len(t_dbpm_ratio):>8.2f} {sum(t_dbpm_ratio)/len(t_dbpm_ratio) - sum(f_dbpm_ratio)/len(f_dbpm_ratio):>+8.2f}")

# FTA / PPG — drawing fouls relative to scoring
f_fta_ppg = [f['fta']/f['ppg'] if f['ppg'] > 0 else 0 for f in false_wings]
t_fta_ppg = [f['fta']/f['ppg'] if f['ppg'] > 0 else 0 for f in true_wings]
print(f"{'FTA / PPG':25s} {sum(f_fta_ppg)/len(f_fta_ppg):>8.2f} {sum(t_fta_ppg)/len(t_fta_ppg):>8.2f} {sum(t_fta_ppg)/len(t_fta_ppg) - sum(f_fta_ppg)/len(f_fta_ppg):>+8.2f}")

# 3PA / (3PA + 2PA proxy) — how much of their shot diet is 3s
# Use tpa and ppg/fg to estimate
f_3pa_share = [f['tpa'] / (f['ppg']/2 * 100/max(f['fg'],1)) if f['ppg'] > 0 and f['fg'] > 0 else 0 for f in false_wings]
t_3pa_share = [f['tpa'] / (f['ppg']/2 * 100/max(f['fg'],1)) if f['ppg'] > 0 and f['fg'] > 0 else 0 for f in true_wings]

# Senior % in each group
f_sr = sum(1 for f in false_wings if f['age'] == 4) / len(false_wings) * 100
t_sr = sum(1 for f in true_wings if f['age'] == 4) / len(true_wings) * 100
f_fr = sum(1 for f in false_wings if f['age'] == 1) / len(false_wings) * 100
t_fr = sum(1 for f in true_wings if f['age'] == 1) / len(true_wings) * 100
print(f"{'Senior %':25s} {f_sr:>7.0f}% {t_sr:>7.0f}% {t_sr-f_sr:>+7.0f}%")
print(f"{'Freshman %':25s} {f_fr:>7.0f}% {t_fr:>7.0f}% {t_fr-f_fr:>+7.0f}%")

# Q1 %
f_q1 = sum(1 for f in false_wings if f.get('quadrant') == 'Q1') / len(false_wings) * 100
t_q1 = sum(1 for f in true_wings if f.get('quadrant') == 'Q1') / len(true_wings) * 100
print(f"{'Q1 team %':25s} {f_q1:>7.0f}% {t_q1:>7.0f}% {t_q1-f_q1:>+7.0f}%")

print(f"\n=== WHO ARE THE TRUE STAR WINGS? ===")
for f in sorted(true_wings, key=lambda x: -x['nba_ws']):
    ht_str = f"{f['h'] // 12}'{f['h'] % 12:02d}\""
    ato = f['apg'] / f['tpg'] if f['tpg'] > 0 else f['apg']
    print(f"  {f['name']:25s} T{f['actual_tier']} WS={f['nba_ws']:>5.0f}  {ht_str}  PPG={f['ppg']:>4.1f}  APG={f['apg']:.1f}  eFG={f['fg']:.0f}%  3P={f['threeP']:.0f}%  FT={f['ft']:.0f}%  USG={f['usg']:.0f}  BPM={f['bpm']:.1f}  DBPM={f['dbpm']:.1f}  {f.get('quadrant','?')}")
