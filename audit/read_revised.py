"""Read the revised data sheet and display all user actions."""
import pandas as pd
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

df = pd.read_excel('audit/revisedata.xlsx', engine='openpyxl')

# Show all rows with ACTION filled
mask = df['ACTION'].notna() & (df['ACTION'].astype(str).str.strip() != '')
has_action = df[mask]
print('=== ROWS WITH ACTION (%d of %d) ===' % (len(has_action), len(df)))

for _, r in has_action.iterrows():
    print()
    print('NAME: %s | ACTION: %s' % (r['NAME'], r['ACTION']))
    print('  PRI: %s | DRAFT: %s #%s | TIER: %s' % (r['PRIORITY'], r.get('DRAFT_YEAR',''), r.get('DRAFT_PICK',''), r.get('TIER','')))
    print('  COLLEGE_IN_DB: %s' % r.get('COLLEGE_IN_DB',''))
    csv_name = r.get('CORRECT_CSV_NAME', '')
    if pd.notna(csv_name) and str(csv_name).strip():
        print('  CORRECT_CSV_NAME: %s' % csv_name)
    college = r.get('CORRECT_COLLEGE', '')
    if pd.notna(college) and str(college).strip():
        print('  CORRECT_COLLEGE: %s' % college)
    ht = r.get('CORRECT_HEIGHT_IN', '')
    if pd.notna(ht) and str(ht).strip():
        print('  CORRECT_HEIGHT_IN: %s' % ht)
    wt = r.get('CORRECT_WEIGHT_LBS', '')
    if pd.notna(wt) and str(wt).strip():
        print('  CORRECT_WEIGHT_LBS: %s' % wt)
    notes = r.get('NOTES', '')
    if pd.notna(notes) and str(notes).strip():
        print('  NOTES: %s' % notes)

# Show rows WITHOUT action
no_action = df[~mask]
if len(no_action) > 0:
    print('\n\n=== ROWS WITHOUT ACTION (%d) ===' % len(no_action))
    for _, r in no_action.iterrows():
        notes = r.get('NOTES', '')
        notes_str = ' | NOTES: %s' % notes if pd.notna(notes) and str(notes).strip() else ''
        print('  %s | %s | %s%s' % (r['PRIORITY'], r['NAME'], r.get('ISSUES','')[:80], notes_str))
