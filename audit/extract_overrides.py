"""Extract TIER_OVERRIDES dict from FinalTierCorrection.xlsx."""
import openpyxl
import os

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FinalTierCorrection.xlsx")
wb = openpyxl.load_workbook(path)
ws = wb.active

overrides = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    corrected = row[-1]
    if corrected is not None and str(corrected).strip() != "":
        name = row[0].strip()
        overrides[name] = int(corrected)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tier_overrides.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("TIER_OVERRIDES = {\n")
    for name in sorted(overrides.keys()):
        f.write(f'    "{name}": {overrides[name]},\n')
    f.write("}\n")
    f.write(f"\n# {len(overrides)} overrides total\n")
print(f"Written {len(overrides)} overrides to {out_path}")
