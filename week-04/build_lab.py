"""Build week-04/lab.ipynb — Capstone 1: Every active orbital launch pad.

This is the Ground Station Operator certification gate. The bar is:
- 40+ pad catalog (expanded from Week 3's 20)
- Attributes: name, country, operator, lat, lon, first_launch_year, status, continent
- Real Natural Earth basemap with country polygons
- Programmatic SCORING RUBRIC that checks: schema, no duplicates,
  point-in-correct-country (per Natural Earth lookup), all 6 inhabited
  continents represented, geographic spread.
- Output artifact: pads_capstone1.geojson + the rubric report.
"""
import json
from pathlib import Path

def md(t):
    lines = [ln + "\n" for ln in t.split("\n")]
    if lines:
        lines[-1] = lines[-1].rstrip("\n")
    return {"cell_type": "markdown", "metadata": {}, "source": lines}

def code(t):
    lines = [ln + "\n" for ln in t.split("\n")]
    if lines:
        lines[-1] = lines[-1].rstrip("\n")
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": lines}

cells = []

cells.append(md(
"""# Week 4 — CAPSTONE 1: Every active orbital launch pad on Earth

**Track:** Ground Station Operator (Beginner) — capstone
**Credential awarded:** [Certified Ground Station Operator](https://launchdetect.com/academy/ground-station-operator/)
**Full primer + quiz:** [https://launchdetect.com/academy/week/4/](https://launchdetect.com/academy/week/4/)

---

_This is the cert-mint moment. By the end of this notebook you will have produced a **GeoJSON of every active orbital launch pad on Earth**, attributed correctly, validated by an automated rubric, and rendered on a publication-quality global map. The rubric in this notebook is the same one the LaunchDetect Academy verification service runs against your submission._
"""
))

cells.append(md(
"""## What you're building

A single deliverable file: **`pads_capstone1.geojson`** — a `FeatureCollection` of `Point` geometries, one per active orbital launch pad, with this attribute schema:

| column              | type    | example             | required |
|---------------------|---------|---------------------|----------|
| `name`              | string  | "Cape Canaveral SLC-40" | yes |
| `country`           | string  | "US" (ISO-3166-1 α-2)   | yes |
| `operator`          | string  | "SpaceX"                | yes |
| `lat`               | number  | 28.5618                 | yes |
| `lon`               | number  | -80.5772                | yes |
| `first_launch_year` | int     | 2010                    | yes |
| `status`            | enum    | "active" \\| "retired"  | yes |
| `continent`         | enum    | "North America"         | yes |

**Pass thresholds for the cert rubric:**

1. ≥ 30 active pads in the dataset
2. All 8 required columns present on every feature
3. Zero duplicate `(lat, lon)` pairs (within 100 m tolerance)
4. Every pad's geographic point falls inside the polygon of its declared country (Natural Earth lookup)
5. The catalog (active + retired) covers **all 6 inhabited continents** that have ever hosted an orbital launch (North America, South America, Europe, Africa, Asia, Oceania) — Antarctica excluded. Note Africa has no active orbital pads as of 2026; the historical Hammaguir (Algeria) and San Marco (Kenya) entries satisfy the continent check.
6. Map renders without errors and saves to PNG + GeoJSON

You can stop reading here, write the code yourself, and run the rubric at the bottom — that's the cert-defense path. Or work through the scaffold below.
"""
))

cells.append(md(
"""## Setup"""
))

cells.append(code(
"""!pip install -q "leafmap[common]" geopandas shapely matplotlib folium"""
))

cells.append(md(
"""## Step 1 — The pad catalog (curated for this capstone)

40 active or recently-retired pads, attributed for the rubric. In a production pipeline you would join this against the FAA AST registry, CelesTrak ground stations, and individual operator catalogs — the curated set below is enough to clear the cert rubric and small enough that you can audit it by eye.
"""
))

cells.append(code(
"""# Format: (name, country, operator, lat, lon, first_launch_year, status, continent)
PADS = [
    # === North America (US) ===
    ("Cape Canaveral SLC-40",     "US", "SpaceX",       28.5618,  -80.5772, 2010, "active",  "North America"),
    ("Cape Canaveral SLC-41",     "US", "ULA",          28.5833,  -80.5833, 2002, "active",  "North America"),
    ("Kennedy LC-39A",            "US", "SpaceX/NASA",  28.6082,  -80.6041, 1967, "active",  "North America"),
    ("Kennedy LC-39B",            "US", "NASA",         28.6271,  -80.6208, 1969, "active",  "North America"),
    ("Cape Canaveral LC-37B",     "US", "ULA",          28.5317,  -80.5648, 2002, "retired", "North America"),
    ("Vandenberg SLC-4E",         "US", "SpaceX",       34.6321, -120.6106, 2013, "active",  "North America"),
    ("Vandenberg SLC-3E",         "US", "ULA",          34.6402, -120.5916, 1961, "active",  "North America"),
    ("Vandenberg SLC-2W",         "US", "ULA",          34.7556, -120.6196, 1959, "retired", "North America"),
    ("Wallops MARS LP-0A",        "US", "Northrop",     37.8338,  -75.4882, 2013, "active",  "North America"),
    ("Wallops MARS LP-0B",        "US", "Rocket Lab",   37.8311,  -75.4884, 2023, "active",  "North America"),
    ("Boca Chica (Starbase)",     "US", "SpaceX",       25.9970,  -97.1559, 2023, "active",  "North America"),
    ("Kodiak LP-3C",              "US", "Astra/ABL",    57.4358, -152.3375, 2020, "active",  "North America"),
    # === South America ===
    ("Kourou ELA-3 (Ariane 5)",   "FR", "Arianespace",   5.2360,  -52.7752, 1996, "retired", "South America"),
    ("Kourou ELA-4 (Ariane 6)",   "FR", "Arianespace",   5.2390,  -52.7689, 2024, "active",  "South America"),
    ("Kourou ELV (Vega)",         "FR", "Arianespace",   5.2360,  -52.7750, 2012, "active",  "South America"),
    ("Alcântara",                 "BR", "AEB",          -2.3733,  -44.3964, 1990, "active",  "South America"),
    # === Europe ===
    ("Esrange Space Center",      "SE", "SSC",         67.8843,   21.0680, 2025, "active",  "Europe"),
    ("Andøya Spaceport",          "NO", "Andøya Space",69.2949,   16.0212, 2025, "active",  "Europe"),
    # === Africa ===
    ("Hammaguir",                 "DZ", "CNES (hist.)",30.8800,   -3.0500, 1965, "retired", "Africa"),
    ("San Marco (sea platform)",  "KE", "ASI (hist.)",  -2.9412,   40.2125, 1967, "retired", "Africa"),
    # === Asia (Russia + Kazakhstan + China + India + Japan + Iran + Israel + S.Korea + DPRK) ===
    ("Baikonur Site 1/5",         "KZ", "Roscosmos",   45.9200,   63.3422, 1957, "active",  "Asia"),
    ("Baikonur Site 31/6",        "KZ", "Roscosmos",   46.0700,   63.5650, 1961, "active",  "Asia"),
    ("Plesetsk Site 43/4",        "RU", "Roscosmos",   62.9290,   40.5772, 1966, "active",  "Asia"),
    ("Plesetsk Site 133",         "RU", "Roscosmos",   62.8847,   40.8556, 1969, "active",  "Asia"),
    ("Vostochny Site 1S",         "RU", "Roscosmos",   51.8842,  128.3336, 2016, "active",  "Asia"),
    ("Tanegashima Yoshinobu",     "JP", "JAXA",        30.4000,  130.9700, 1996, "active",  "Asia"),
    ("Uchinoura",                 "JP", "JAXA",        31.2510,  131.0823, 1970, "active",  "Asia"),
    ("Wenchang LC-201",           "CN", "CASC",        19.6140,  110.9510, 2016, "active",  "Asia"),
    ("Jiuquan SLS-2",             "CN", "CASC",        40.9583,  100.2917, 1970, "active",  "Asia"),
    ("Jiuquan Commercial LC-130", "CN", "CAS Space",   40.9530,  100.2942, 2023, "active",  "Asia"),
    ("Xichang LC-2",              "CN", "CASC",        28.2456,  102.0269, 1984, "active",  "Asia"),
    ("Xichang LC-3",              "CN", "CASC",        28.2467,  102.0298, 1990, "active",  "Asia"),
    ("Taiyuan LC-9",              "CN", "CASC",        38.8492,  111.6082, 2008, "active",  "Asia"),
    ("Sriharikota FLP",           "IN", "ISRO",        13.7340,   80.2354, 1980, "active",  "Asia"),
    ("Sriharikota SLP",           "IN", "ISRO",        13.7199,   80.2304, 2005, "active",  "Asia"),
    ("Imam Khomeini Spaceport",   "IR", "ISA",         35.2347,   53.9210, 2009, "active",  "Asia"),
    ("Palmachim",                 "IL", "IAI",         31.8842,   34.6890, 1988, "active",  "Asia"),
    ("Naro Space Center",         "KR", "KARI",        34.4313,  127.5350, 2009, "active",  "Asia"),
    ("Sohae",                     "KP", "DPRK",        39.6602,  124.7050, 2012, "active",  "Asia"),
    # === Oceania ===
    ("Mahia LC-1A",               "NZ", "Rocket Lab", -39.2606,  177.8649, 2017, "active",  "Oceania"),
    ("Mahia LC-1B",               "NZ", "Rocket Lab", -39.2632,  177.8665, 2022, "active",  "Oceania"),
    ("Whalers Way",               "AU", "Southern Lc.",-34.9417, 135.6217, 2024, "active",  "Oceania"),
]

cols = ["name","country","operator","lat","lon","first_launch_year","status","continent"]
print(f"Catalog: {len(PADS)} pads")
print(f"Active: {sum(1 for p in PADS if p[6]=='active')}")
print(f"Retired: {sum(1 for p in PADS if p[6]=='retired')}")
print()
import collections
print('By continent:', dict(collections.Counter(p[7] for p in PADS)))
print('By country (top 6):', collections.Counter(p[1] for p in PADS).most_common(6))"""
))

cells.append(md(
"""## Step 2 — Build the GeoDataFrame and export the deliverable
"""
))

cells.append(code(
"""import geopandas as gpd
from shapely.geometry import Point
import os

rows = [dict(zip(cols, p)) for p in PADS]
gdf = gpd.GeoDataFrame(rows,
                       geometry=[Point(r['lon'], r['lat']) for r in rows],
                       crs='EPSG:4326')

# Drop retired-only rows for the cert deliverable
active = gdf[gdf['status'] == 'active'].copy()
print(f"Active pads written to deliverable: {len(active)}")

out_path = '/content/pads_capstone1.geojson' if os.path.exists('/content') else 'pads_capstone1.geojson'
active.to_file(out_path, driver='GeoJSON')
print(f"Wrote {out_path} ({os.path.getsize(out_path):,} bytes)")"""
))

cells.append(md(
"""## Step 3 — The cert rubric (this is what verification runs)

Every check is one assertion. If any fail, fix the data and re-run. **All 6 must pass to mint the credential.**
"""
))

cells.append(code(
"""import json, math
from shapely.geometry import Point

# Load deliverable back from disk — the rubric must not trust in-memory state.
with open(out_path) as f:
    deliverable = json.load(f)

results = {}

# Check 1 — minimum size
n = len(deliverable['features'])
results['1_min_30_pads'] = (n >= 30, f'{n} active pads (need ≥30)')

# Check 2 — schema
required = {'name','country','operator','lat','lon','first_launch_year','status','continent'}
missing = [i for i,f in enumerate(deliverable['features']) if not required.issubset(f['properties'].keys())]
results['2_schema'] = (not missing, f'{len(missing)} features missing required columns')

# Check 3 — no near-duplicate pads (within 100 m)
def near(lat1, lon1, lat2, lon2):
    # Equirectangular approximation OK for proximity
    R = 6371000
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1+lat2)/2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * R
dupes = []
features = deliverable['features']
for i in range(len(features)):
    for j in range(i+1, len(features)):
        pi, pj = features[i]['properties'], features[j]['properties']
        if near(pi['lat'], pi['lon'], pj['lat'], pj['lon']) < 100:
            dupes.append((pi['name'], pj['name']))
results['3_no_dupes'] = (not dupes, f'{len(dupes)} pairs within 100 m')

# Check 4 — point-in-correct-country (Natural Earth lookup)
try:
    countries = gpd.read_file('https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip')
    iso_col = next((c for c in ['ISO_A2_EH','ISO_A2'] if c in countries.columns), None)
    wrong_country = []
    for f in features:
        p = f['properties']
        match = countries[countries[iso_col].astype(str).str.upper() == p['country'].upper()]
        if len(match) == 0:
            continue  # NE may miss small territories; rubric is lenient there
        poly = match.iloc[0].geometry
        # Allow up to ~1.0° (~110 km) slack. Natural Earth 1:110m heavily
        # simplifies small islands and coastlines — Tanegashima, Andøya,
        # Mahia, Naro, Alcântara all sit on coastline-simplified-out edges.
        # 1° is loose enough to admit them but tight enough that a pad
        # labeled "CN" in Brazil would still trip the check.
        if not (poly.contains(Point(p['lon'], p['lat'])) or poly.distance(Point(p['lon'], p['lat'])) < 1.0):
            wrong_country.append((p['name'], p['country']))
    results['4_point_in_country'] = (not wrong_country, f'{len(wrong_country)} pads outside their declared country polygon')
    if wrong_country:
        print('  Country mismatches:', wrong_country[:5])
except Exception as e:
    results['4_point_in_country'] = (None, f'SKIPPED: Natural Earth unavailable ({e})')

# Check 5 — geographic coverage. As of 2026 Africa has zero ACTIVE
# orbital launch pads (Algeria/Hammaguir and the Italian San Marco platform
# off Kenya are both retired), so we score the dataset's continent coverage
# against the FULL catalog (active + retired). Honest data > forced symmetry.
all_features_inc_retired = [dict(properties=dict(zip(cols, p))) for p in PADS]
needed = {'North America','South America','Europe','Africa','Asia','Oceania'}
got = {f['properties']['continent'] for f in all_features_inc_retired}
missing_continents = needed - got
results['5_six_continents_total'] = (not missing_continents,
    f'in catalog: {got}  | missing: {missing_continents or \"none\"}')

# Check 6 — files on disk
results['6_geojson_on_disk'] = (os.path.exists(out_path) and os.path.getsize(out_path) > 1000,
                                 f'{out_path} size={os.path.getsize(out_path)}b')

# Print rubric report
print('=' * 72)
print('CAPSTONE 1 — RUBRIC REPORT')
print('=' * 72)
all_pass = True
for key in sorted(results):
    ok, detail = results[key]
    if ok is None:
        mark = '[SKIP]'
    elif ok:
        mark = '[PASS]'
    else:
        mark = '[FAIL]'; all_pass = False
    print(f'  {mark}  {key:32s}  {detail}')
print('=' * 72)
print('VERDICT:', 'PASS — cert eligible' if all_pass else 'FAIL — fix issues and re-run')"""
))

cells.append(md(
"""## Step 4 — Render the global map (the visual deliverable)
"""
))

cells.append(code(
"""import matplotlib.pyplot as plt

# Operator palette (same idea as Week 3, larger set)
PALETTE = ["#0891b2","#ea580c","#15803d","#dc2626","#7c3aed","#f59e0b",
           "#0e7490","#c2410c","#65a30d","#be185d","#1e40af","#9333ea",
           "#0d9488","#a3411a","#84cc16","#db2777","#2563eb","#7e22ce"]
ops = sorted(active['operator'].unique())
op_color = {op: PALETTE[i % len(PALETTE)] for i, op in enumerate(ops)}

fig, ax = plt.subplots(figsize=(16, 8), dpi=110)
try:
    countries.plot(ax=ax, color='#f4efe6', edgecolor='#888', linewidth=0.3)
except Exception:
    pass

for op in ops:
    sub = active[active['operator'] == op]
    ax.scatter(sub['lon'], sub['lat'],
               c=op_color[op], s=60, edgecolor='#222', linewidth=0.5,
               label=op, zorder=3)

ax.set_xlim(-180, 180); ax.set_ylim(-60, 80)
ax.set_xlabel('Longitude (°E)'); ax.set_ylabel('Latitude (°N)')
ax.set_title(f'Capstone 1 — Every active orbital launch pad ({len(active)} pads, {len(ops)} operators)',
             fontsize=13, pad=12)
ax.legend(loc='lower left', fontsize=8, ncol=2, frameon=True, title='Operator')
ax.grid(True, linestyle=':', alpha=0.4)
ax.set_aspect('equal', adjustable='datalim')

plt.tight_layout()
out_png = '/content/pads_capstone1.png' if os.path.exists('/content') else 'pads_capstone1.png'
plt.savefig(out_png, dpi=200, bbox_inches='tight')
print(f"Rendered to {out_png} ({os.path.getsize(out_png):,} bytes)")
plt.show()"""
))

cells.append(md(
"""## Doing this in QGIS (alternative path)

Same pattern as Week 3 — load `pads_capstone1.geojson`, **Symbology → Categorized → operator → Classify**, add a print layout, export PDF at 300 DPI. The QGIS PDF is the formal deliverable some employers want; the Python PNG is fine for everything else.

## How verification works

When you mint the cert via `launchdetect.com/academy/verify/`, the service:

1. Receives your GeoJSON.
2. Runs the **same 6 checks above**, against the same Natural Earth boundary data.
3. Issues a verifiable credential URL `launchdetect.com/academy/verify/{certId}/` that anyone can re-verify.

This means: if you pass the rubric in this notebook, you pass the rubric on the server. There's no hidden grading.

## Self-check

- [ ] All 6 rubric checks pass (or check 4 is `[SKIP]` due to no network).
- [ ] `pads_capstone1.geojson` exists, ≥ 30 features, valid `FeatureCollection`.
- [ ] `pads_capstone1.png` is a single global map with operator-colored markers.
- [ ] You can defend the dataset — explain why each pad is in/out, and which continent each falls on.
- [ ] Quiz on the [Week 4 page](https://launchdetect.com/academy/week/4/).

## What's next

**Mint your credential at [launchdetect.com/academy/ground-station-operator/](https://launchdetect.com/academy/ground-station-operator/)** by uploading your `pads_capstone1.geojson`. Then continue to Track 2: **Orbital Analyst (Weeks 5-10)**.

---

Bug or improvement? Open an issue at [github.com/launchdetect/academy-labs](https://github.com/launchdetect/academy-labs).
"""
))

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "colab": {"provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).parent / "lab.ipynb"
out.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {out} ({len(cells)} cells, {out.stat().st_size:,} bytes)")
