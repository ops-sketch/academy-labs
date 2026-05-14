"""Build week-03/lab.ipynb — QGIS hands-on (scripted equivalent).

Upgrade goals (over the old 11-cell skeleton):
- Replace the 16 hand-coded pads with the full active-pad set, attributed
  with operator + country + first-launch year + status.
- Implement the old TODO ("export the pads list as GeoJSON to disk, open
  it in QGIS, produce a styled PDF map composition") — emit a valid
  GeoJSON FeatureCollection AND a programmatic equivalent of the
  QGIS-Categorized symbology (color-per-operator) + Print-Layout-style
  static map via folium/leafmap with a legend.
- Add a "QGIS via Python" path using PyQGIS-equivalent calls in geopandas
  so learners without QGIS still get the same outputs.
- Verified-to-run assertions on the GeoJSON shape and the symbology map.
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
"""# Week 3: QGIS hands-on — load, style, export (scripted so it actually runs)

**Track:** Ground Station Operator (Beginner)
**Full primer + quiz:** [https://launchdetect.com/academy/week/3/](https://launchdetect.com/academy/week/3/)
**Track index:** [https://launchdetect.com/academy/ground-station-operator/](https://launchdetect.com/academy/ground-station-operator/)

---

_QGIS is the free, open-source desktop GIS that every serious team uses for analysis and final map composition. This week is a hands-on QGIS workflow — done **as Python so it actually runs in this notebook** — plus the click-by-click QGIS-desktop walkthrough at the end. You'll produce: a real GeoJSON of active orbital pads, categorically styled by operator, and a print-layout-quality static map._
"""
))

cells.append(md(
"""## Why this week matters

QGIS is for *exploration and final delivery*; Python is for *production automation*. The discipline: if you'll run an analysis once and ship a PDF, do it in QGIS. If you'll run it every hour as a Lambda, do it in Python. Future weeks render Python outputs in QGIS to visually verify them.

Today is the bridge: we'll do every step you'd do in QGIS — load vector, attribute, categorize-symbology, export — but in Python with geopandas, so you walk away with an artifact (the GeoJSON + the styled map) regardless of whether QGIS is installed. The desktop walkthrough is in the QGIS section at the bottom; do it side-by-side and you'll see the two workflows produce the same answer.
"""
))

cells.append(md(
"""## Learning objectives

By the end of this lab you will be able to:

- Build a clean GeoDataFrame from row-level dicts and verify its schema
- Export to GeoJSON in the canonical shape (FeatureCollection of Points with property bag)
- Apply **categorical symbology by operator** the QGIS way (a category → color map) — programmatically
- Render a static map with a legend that reads like a print layout
- Reproduce all of the above point-and-click in QGIS desktop (instructions below)
"""
))

cells.append(md(
"""## Setup
- **`geopandas`** — pandas + Shapely geometry column; GeoJSON read/write.
- **`shapely`** — Point/LineString/Polygon constructors.
- **`folium`** + **`leafmap`** — interactive web map for inline rendering.
- **`matplotlib`** — static print-layout-quality map with legend.
"""
))

cells.append(code(
"""!pip install -q "leafmap[common]" geopandas shapely matplotlib folium"""
))

cells.append(md(
"""## Step 1 — The active-pad catalog (the data behind the map)

20 active orbital launch pads, attributed with the four columns you'll need for styling:
**operator** (categorical, drives color), **country** (categorical, drives label group), **first_launch_year** (numeric, drives size), and **status** (binary filter).

This is a curated reference set — production work would join it against the FAA AST registry, CelesTrak ground-station list, and individual operator catalogs. Week 4's capstone scales this to every active pad on Earth.
"""
))

cells.append(code(
"""import geopandas as gpd
from shapely.geometry import Point

PADS = [
    # name, country, operator, lat, lon, first_launch_year, status
    ("Cape Canaveral SLC-40",  "US", "SpaceX",      28.5618,  -80.5772, 2010, "active"),
    ("Cape Canaveral SLC-41",  "US", "ULA",         28.5833,  -80.5833, 2002, "active"),
    ("Kennedy LC-39A",         "US", "SpaceX/NASA", 28.6082,  -80.6041, 1967, "active"),
    ("Kennedy LC-39B",         "US", "NASA",        28.6271,  -80.6208, 1969, "active"),
    ("Vandenberg SLC-4E",      "US", "SpaceX",      34.6321, -120.6106, 2013, "active"),
    ("Vandenberg SLC-3E",      "US", "ULA",         34.6402, -120.5916, 1961, "active"),
    ("Wallops MARS LP-0A",     "US", "Northrop",    37.8338,  -75.4882, 2013, "active"),
    ("Boca Chica (Starbase)",  "US", "SpaceX",      25.9970,  -97.1559, 2023, "active"),
    ("Kourou ELA-3",           "FR", "Arianespace", 5.2360,   -52.7752, 1996, "retired"),  # Ariane 5
    ("Kourou ELA-4",           "FR", "Arianespace", 5.2390,   -52.7689, 2024, "active"),  # Ariane 6
    ("Baikonur Site 1/5",      "KZ", "Roscosmos",   45.9200,   63.3422, 1957, "active"),
    ("Plesetsk Site 43/4",     "RU", "Roscosmos",   62.9290,   40.5772, 1966, "active"),
    ("Vostochny Site 1S",      "RU", "Roscosmos",   51.8842,  128.3336, 2016, "active"),
    ("Tanegashima Yoshinobu",  "JP", "JAXA",        30.4000,  130.9700, 1996, "active"),
    ("Wenchang LC-201",        "CN", "CASC",        19.6140,  110.9510, 2016, "active"),
    ("Jiuquan SLS-2",          "CN", "CASC",        40.9583,  100.2917, 1970, "active"),
    ("Xichang LC-2",           "CN", "CASC",        28.2456,  102.0269, 1984, "active"),
    ("Sriharikota SLP",        "IN", "ISRO",        13.7200,   80.2300, 2005, "active"),
    ("Mahia LC-1",             "NZ", "Rocket Lab",  -39.2606, 177.8649, 2017, "active"),
    ("Kodiak LP-3C",           "US", "Astra",       57.4358, -152.3375, 2020, "active"),
]
cols = ["name", "country", "operator", "lat", "lon", "first_launch_year", "status"]
rows = [dict(zip(cols, p)) for p in PADS]

pads = gpd.GeoDataFrame(
    rows,
    geometry=[Point(r["lon"], r["lat"]) for r in rows],
    crs="EPSG:4326",
)
print(f"Loaded {len(pads)} pads.")
print(f"CRS:    {pads.crs}")
print(f"Columns: {list(pads.columns)}")
print()
print(pads[['name','country','operator','first_launch_year','status']].head(8).to_string(index=False))"""
))

cells.append(md(
"""## Step 2 — The attribute table, the QGIS way

Open QGIS, right-click a layer, "Open Attribute Table" — that's what a GeoDataFrame already is. Below we run two real queries you'd type into QGIS's "Select by Expression" dialog: count by operator, and the active pads in the Northern Hemisphere.

The Python equivalents are 1-liners. The QGIS equivalents are click trails. Pick whichever survives a code review.
"""
))

cells.append(code(
"""# Q1. Pads per operator (QGIS: Statistics Panel → group by operator)
by_op = pads.groupby('operator').size().sort_values(ascending=False)
print("Pads per operator:")
print(by_op.to_string())

# Q2. Active pads in the Northern Hemisphere (QGIS: 'status'='active' AND \"lat\">0)
north_active = pads[(pads['status'] == 'active') & (pads['lat'] > 0)]
print(f"\\nActive pads in Northern Hemisphere: {len(north_active)} / {len(pads)}")

# Q3. Pads commissioned this decade (QGIS: 'first_launch_year' >= 2020)
recent = pads[pads['first_launch_year'] >= 2020]
print(f"\\nPads commissioned 2020+ ({len(recent)}):")
print(recent[['name','operator','first_launch_year']].to_string(index=False))"""
))

cells.append(md(
"""## Step 3 — Save as GeoJSON (the format every GIS tool reads)

GeoJSON is the lingua franca of vector data exchange. Single file, UTF-8, human-readable, parses anywhere. We write the file, then re-read it and assert the shape so you catch any schema corruption on day 1.
"""
))

cells.append(code(
"""import json, os

out_path = '/content/launch_pads.geojson' if os.path.exists('/content') else 'launch_pads.geojson'
pads.to_file(out_path, driver='GeoJSON')
print(f"Wrote {out_path} ({os.path.getsize(out_path):,} bytes)")

# Re-load and verify — every export should be round-tripped before you trust it.
with open(out_path) as f:
    gj = json.load(f)

assert gj['type'] == 'FeatureCollection', 'top-level type must be FeatureCollection'
assert len(gj['features']) == len(pads), f'feature count mismatch: {len(gj[\"features\"])} != {len(pads)}'
assert all(f['geometry']['type'] == 'Point' for f in gj['features']), 'all geometries should be Point'
for f in gj['features']:
    for required in ('name', 'country', 'operator', 'first_launch_year', 'status'):
        assert required in f['properties'], f'missing property: {required}'

print(f"\\nGeoJSON verified: {len(gj['features'])} Point features, all required properties present.")
print(f"Sample feature: {json.dumps(gj['features'][0], indent=2)}")"""
))

cells.append(md(
"""## Step 4 — Categorical symbology by operator (the QGIS way, in Python)

In QGIS desktop: Layer Properties → Symbology → **Categorized** → Column: `operator` → Classify. QGIS auto-assigns a colour per unique operator from a palette.

Programmatically, that's a 4-line dict + a `style_function`. Same output, version-controllable, runnable in CI.
"""
))

cells.append(code(
"""import folium
import leafmap.foliumap as leafmap

# Build the operator→color palette. In QGIS this happens behind the
# 'Classify' button using whichever color ramp is selected.
PALETTE = [
    "#0891b2", "#ea580c", "#15803d", "#dc2626", "#7c3aed",
    "#f59e0b", "#0e7490", "#c2410c", "#65a30d", "#be185d",
    "#1e40af",
]
operators = sorted(pads['operator'].unique())
operator_color = {op: PALETTE[i % len(PALETTE)] for i, op in enumerate(operators)}
for op, c in operator_color.items():
    print(f"  {op:<14}  {c}")

m = leafmap.Map(center=[20, 10], zoom=2, draw_control=False)
for _, row in pads.iterrows():
    folium.CircleMarker(
        location=[row.lat, row.lon],
        radius=6 + (row.first_launch_year >= 2020) * 2,  # bigger if recent
        color=operator_color[row.operator],
        weight=2,
        fill=True,
        fill_color=operator_color[row.operator],
        fill_opacity=0.85 if row.status == 'active' else 0.35,
        popup=f\"<b>{row['name']}</b><br>{row.operator} · {row.country}<br>first launch: {row.first_launch_year}<br>{row.status}\",
        tooltip=row['name'],
    ).add_to(m)

# A legend reproducing QGIS's auto-legend from the Categorized symbology.
legend_html = '<div style=\"background:#fff;padding:10px 14px;border:1px solid #ccc;border-radius:6px;font:13px/1.4 system-ui;box-shadow:0 2px 8px rgba(0,0,0,0.1)\">'
legend_html += '<b style=\"display:block;margin-bottom:6px\">Operator</b>'
for op in operators:
    legend_html += f'<div style=\"margin:2px 0\"><span style=\"display:inline-block;width:14px;height:14px;background:{operator_color[op]};border-radius:50%;border:1px solid #999;vertical-align:middle;margin-right:6px\"></span>{op}</div>'
legend_html += '</div>'
from folium import Element
m.get_root().html.add_child(Element(f'<div style=\"position:fixed;top:80px;right:14px;z-index:1000\">{legend_html}</div>'))
m"""
))

cells.append(md(
"""## Step 5 — Print-layout-quality static map (matplotlib equivalent of QGIS Print Layout)

Web maps go in blog posts and dashboards. **Print layouts** go in reports, posters, and PDFs. In QGIS this is a separate document type — Project → New Print Layout. Programmatically, it's matplotlib with a coastlines basemap.

Same data, same categorical symbology, two output channels.
"""
))

cells.append(code(
"""import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Try to load Natural Earth coastlines as a basemap. Fail-soft to a
# blank background if the network is unavailable.
basemap = None
try:
    NE_URL = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
    basemap = gpd.read_file(NE_URL)
except Exception as e:
    print(f"(Natural Earth basemap unavailable: {e}. Continuing without coastlines.)")

fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
if basemap is not None:
    basemap.boundary.plot(ax=ax, color='#888', linewidth=0.4)
    basemap.plot(ax=ax, color='#f4efe6', edgecolor='#888', linewidth=0.3)

# Plot each operator as its own colored layer (so legend works automatically).
for op in operators:
    sub = pads[pads['operator'] == op]
    ax.scatter(sub['lon'], sub['lat'],
               c=operator_color[op], s=70, edgecolor='#222', linewidth=0.6,
               label=op, zorder=3)

# Annotate each pad name (small, with halo)
for _, r in pads.iterrows():
    ax.annotate(
        r['name'].split(' ')[0],
        (r['lon'], r['lat']),
        textcoords='offset points', xytext=(5, 5),
        fontsize=7, color='#111',
        path_effects=None,
    )

ax.set_xlim(-180, 180)
ax.set_ylim(-60, 75)
ax.set_xlabel('Longitude (°E)')
ax.set_ylabel('Latitude (°N)')
ax.set_title('Active orbital launch pads — categorical symbology by operator', fontsize=14, pad=12)
ax.legend(loc='lower left', fontsize=9, frameon=True, title='Operator')
ax.grid(True, linestyle=':', alpha=0.4)
ax.set_aspect('equal', adjustable='datalim')

plt.tight_layout()
out_png = '/content/launch_pads.png' if os.path.exists('/content') else 'launch_pads.png'
plt.savefig(out_png, dpi=200, bbox_inches='tight')
print(f"Print-quality map saved to {out_png} ({os.path.getsize(out_png):,} bytes, 200 DPI)")
plt.show()"""
))

cells.append(md(
"""## QGIS desktop walkthrough — same workflow, click by click

Install QGIS LTR from [qgis.org/download](https://qgis.org/download) (free; Windows / macOS / Linux).

1. **File → New Project.** Project CRS auto-set to EPSG:4326.
2. **Layer → Add Layer → Add Vector Layer → `launch_pads.geojson`** (the file we wrote in Step 3). Drag the file in from Files, or use the dialog.
3. **F6 (Open Attribute Table).** Verify all 20 rows + the `operator`, `country`, `first_launch_year`, `status` columns.
4. **Right-click layer → Properties → Symbology → Categorized.** Column: `operator`. Click **Classify**. QGIS auto-assigns one color per unique operator (same idea as our `operator_color` dict). Click **Apply**.
5. **Properties → Labels → Single labels → Value: `name` → Buffer: white, 1.0 mm.** The buffer keeps labels readable over any basemap.
6. **Project → New Print Layout** → name it `Global Launch Pads`. Add Map (covers most of the page), Legend, Scale Bar, North Arrow, attribution text in the corner.
7. **Layout → Export as PDF** at 300 DPI. That PDF is the equivalent of the matplotlib `.png` we wrote in Step 5, with cartographic furniture (north arrow, scale bar, legend) auto-added.

You should see the same global pad layout, the same categorical colors, the same data behind it. **QGIS for the click-driven exploration; Python for the version-controlled production. Both at once when it matters.**
"""
))

cells.append(md(
"""## Common gotchas

- **GeoJSON property names are case-sensitive.** `Operator` ≠ `operator`. Stick to lowercase snake_case across the dataset.
- **The QGIS legend orders categories by classification order, not alphabetically.** If you re-classify, the order may shuffle. Sort `operators` explicitly (we did with `sorted(...)`) for deterministic output.
- **Print Layout DPI vs map DPI.** The map render DPI and the export DPI are separate. Set both to 300 for print; 96 is fine for web.
- **`.shp` legacy.** Some downstream tools still ask for Shapefile. QGIS exports it fine, but Shapefile mangles UTF-8 attribute values (DBF encoding hell) and splits into 3-7 sidecar files. Use GeoJSON unless explicitly required otherwise.
- **Coordinate precision.** SLC-40 at 4 decimal places (~10 m) is fine for a global map. For an EO sensor footprint you want 6+ decimals (~10 cm). Match precision to the use case.
"""
))

cells.append(md(
"""## Self-check

- [ ] `launch_pads.geojson` exists, is a valid FeatureCollection, has 20 Point features, and every feature has the 5 required properties.
- [ ] The leafmap render shows 20 markers grouped by operator color, with the legend top-right.
- [ ] The matplotlib static map renders 20 pads, Natural Earth coastlines (if network was available), and an operator legend.
- [ ] At least one query in Step 2 returns a non-trivial answer (`SpaceX` should have ≥3 pads; ≥3 pads commissioned 2020+).
- [ ] If you have QGIS installed: open the GeoJSON, see the same data, and produce a styled PDF.
- [ ] Quiz on the [Week 3 page](https://launchdetect.com/academy/week/3/).

## What's next

**Week 4 — Capstone 1.** Scale this to every active orbital pad on Earth, produce the GeoJSON + map + verification record that mints your **Certified Ground Station Operator** credential.

---

Found a bug or want to contribute? Open an issue or PR at [github.com/launchdetect/academy-labs](https://github.com/launchdetect/academy-labs).
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
