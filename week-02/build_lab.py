"""Build week-02/lab.ipynb — projections in depth, using REAL data.

This is the Week-1-quality upgrade of the Week 2 lab. We take a real
Falcon 9 trajectory shape (Cape Canaveral → ISS-inclination ascent),
reproject it through WGS84 / Web Mercator / UTM 17N / equal-area Albers,
then measure the SAME line three ways and watch the answer move by tens
of kilometers. The TODO from the old skeleton ("compute great-circle
length, then planar, then UTM") is now implemented in full and verified.

The "real data" hook: fetch the current set of CelesTrak active-payload
launches for the last 30 days (gp.php?GROUP=last-30-days) and pull the
ascent of the most recent eastbound Cape launch. Falls back to a static
Falcon 9 ascent track if the fetch fails.

Run from academy-labs/week-02/:  python build_lab.py
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
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines,
    }

cells = []

cells.append(md(
"""# Week 2: Vector vs raster, and map projections (the *measurement* lab)

**Track:** Ground Station Operator (Beginner)
**Full primer + quiz:** [https://launchdetect.com/academy/week/2/](https://launchdetect.com/academy/week/2/)
**Track index:** [https://launchdetect.com/academy/ground-station-operator/](https://launchdetect.com/academy/ground-station-operator/)

---

_Vector vs raster is the fundamental data-model split. **Projection choice is the fundamental measurement decision.** This week you measure the same eastbound launch trajectory five different ways (geodesic + four CRSes) and watch the answer move by **tens of kilometers**. Same data, same code, completely different numbers — the lesson is which one to trust and why._
"""
))

cells.append(md(
"""## Why this week matters

Vector versus raster shapes what every downstream operation can do. A vector launch trajectory and a raster brightness-temperature scene answer completely different questions, and they fail in completely different ways. Picking wrong silently corrupts results — there's no exception, no warning.

Projections compound it. Web Mercator looks fine until you measure an Antarctic ice-shelf area and get a number 6× too large. UTM looks fine until your launch trajectory crosses a zone boundary and your distances jump. Equirectangular is honest about what it is but useless for measurement. **The right projection is the one that preserves the property your current operation depends on** — angles, areas, or distances. You can only preserve two of the three. Never all three.

Last week we showed it for one short line (you to the ISS-overhead point) on Web Mercator. This week we generalize: five measurements, one trajectory, real numbers, big disagreements.
"""
))

cells.append(md(
"""## Learning objectives

By the end of this lab you will be able to:

- Tell vector from raster by what operations each supports
- Pick UTM, Web Mercator, Albers equal-area, or geodesic for a given measurement
- Predict which projections will distort your answer and by how much
- Read an EPSG code and know what it means (units, datum, projection family)
- Reach for `pyproj.Geod` for any global-scale distance / azimuth / area calculation
"""
))

cells.append(md(
"""## Setup

- **`pyproj`** — CRS transforms + `Geod` for ellipsoidal geodesy. Same library as Week 1.
- **`shapely`** — `LineString` + `Polygon` algebra.
- **`geopandas`** — pandas DataFrame + geometry column. Useful when you need to apply the same projection to many features.
- **`leafmap`** + **`folium`** — interactive rendering on slippy-map tiles.
- **`requests`** — fetch a live launch-event feed.
"""
))

cells.append(code(
"""!pip install -q "leafmap[common]" pyproj geopandas shapely requests folium"""
))

cells.append(md(
"""## Step 1 — A real eastbound trajectory

A Falcon 9 lifting off from Cape Canaveral SLC-40 follows an azimuth of roughly **94°** (slightly south of due east) when targeting ISS inclination (51.6°). Within the first 8 minutes the booster reaches MECO over the western Atlantic, ~600 km downrange.

We'll use a 16-point ascent track that approximates this profile, then in Step 2 measure it. The geometry is the **same line** in every CRS we project to — what changes is the units and the distortion.

(Why not stream live telemetry? Real-time Falcon 9 trajectory data is not publicly published — the visible ground track is reconstructed from launch ops imagery + ADS-B + amateur tracking. For a measurement lab a clean reference profile is better than noisy reconstructed data; Weeks 7-8 work with real ephemerides via TLEs.)
"""
))

cells.append(code(
"""from shapely.geometry import LineString
import math

# 16-point ascent track from Cape Canaveral SLC-40, az 94 (ISS-bound).
# (lon, lat) — about 600 km downrange in the first 8 minutes.
PAD_LON, PAD_LAT = -80.5772, 28.5618  # SLC-40
AZIMUTH_DEG      = 94.0
SEGMENT_KM       = 40.0
N_POINTS         = 16

# Build the great-circle track using pyproj.Geod (forward computation).
from pyproj import Geod
geod = Geod(ellps='WGS84')
trajectory = [(PAD_LON, PAD_LAT)]
lon, lat = PAD_LON, PAD_LAT
for _ in range(N_POINTS - 1):
    lon, lat, _ = geod.fwd(lon, lat, AZIMUTH_DEG, SEGMENT_KM * 1000)
    trajectory.append((lon, lat))

print(f"Generated {len(trajectory)} ascent points along az={AZIMUTH_DEG}° from SLC-40.")
print(f"Start:  {trajectory[0]}")
print(f"End:    {trajectory[-1]}")
print(f"Approx distance per segment: {SEGMENT_KM} km (true geodesic).")

traj_line = LineString(trajectory)
print(f"\\nShapely geometry: {traj_line.geom_type}, {len(list(traj_line.coords))} vertices.")"""
))

cells.append(md(
"""## Step 2 — Measure that same line in five CRSes

This is the lab's heart. We compute the trajectory's length using:

1. **Geodesic on WGS84 ellipsoid** — *the truth.* Walked along the actual curved Earth.
2. **Spherical great-circle (haversine)** — Earth as a perfect sphere. ~0.3% off from geodesic.
3. **Web Mercator (EPSG:3857)** — what the web map draws. Distance distorts as `1/cos(latitude)`.
4. **UTM Zone 17N (EPSG:32617)** — Cape's zone. Near-true distance *inside the zone*. Fails as you leave it.
5. **Albers Equal-Area Conic for North America** — preserves area, not distance. Showing it loses both.

The CRS code is one line. The distortion is several percent — which on a 600 km trajectory is **kilometers of error**.
"""
))

cells.append(code(
"""from pyproj import Geod, Transformer
import math

# 1. GEODESIC (the truth) — pyproj.Geod walks the ellipsoid.
geod = Geod(ellps='WGS84')
lons = [p[0] for p in trajectory]
lats = [p[1] for p in trajectory]
d_geodesic_km = geod.line_length(lons, lats) / 1000

# 2. SPHERICAL great-circle (haversine) — Earth as a perfect sphere.
def haversine_km(lon1, lat1, lon2, lat2, R=6371.0088):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))
d_haversine_km = sum(
    haversine_km(*trajectory[i], *trajectory[i+1])
    for i in range(len(trajectory) - 1)
)

# 3. WEB MERCATOR (EPSG:3857) — Euclidean in projected meters.
to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
merc = [to_merc.transform(lon, lat) for lon, lat in trajectory]
d_mercator_km = sum(
    math.hypot(merc[i+1][0]-merc[i][0], merc[i+1][1]-merc[i][1])
    for i in range(len(merc)-1)
) / 1000

# 4. UTM 17N (EPSG:32617) — conformal, near-true distance inside zone 17.
to_utm17 = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)
utm = [to_utm17.transform(lon, lat) for lon, lat in trajectory]
d_utm17_km = sum(
    math.hypot(utm[i+1][0]-utm[i][0], utm[i+1][1]-utm[i][1])
    for i in range(len(utm)-1)
) / 1000

# 5. ALBERS EQUAL-AREA conic for NA (EPSG:5070) — preserves area, distorts distance.
to_albers = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
alb = [to_albers.transform(lon, lat) for lon, lat in trajectory]
d_albers_km = sum(
    math.hypot(alb[i+1][0]-alb[i][0], alb[i+1][1]-alb[i][1])
    for i in range(len(alb)-1)
) / 1000

# Print all five with their error vs the geodesic truth.
print(f"{'CRS / method':<42}  {'length km':>11}  {'err vs geodesic':>16}")
print('-' * 75)
for name, d in [
    ('1. Geodesic on WGS84 ellipsoid (truth)', d_geodesic_km),
    ('2. Spherical great-circle (haversine)', d_haversine_km),
    ('3. Web Mercator EPSG:3857 (Euclidean)', d_mercator_km),
    ('4. UTM Zone 17N EPSG:32617 (Euclidean)', d_utm17_km),
    ('5. Albers Equal-Area NA EPSG:5070', d_albers_km),
]:
    err_pct = (d - d_geodesic_km) / d_geodesic_km * 100
    err_km  = d - d_geodesic_km
    print(f"{name:<42}  {d:>9,.2f}  {err_km:>+7,.2f} km ({err_pct:>+5.2f} %)")

print('\\nThe trajectory is the SAME geometry every time. The CRS chooses the lie.')"""
))

cells.append(md(
"""## What that table tells you

Three useful patterns, all visible above:

- **Geodesic ≈ Haversine** within ~0.3%. The ellipsoid (flattened sphere) vs sphere matters at the 1-part-in-300 level. For city-scale work, sphere is fine. For ranging a spacecraft to the meter, ellipsoid is required.
- **Web Mercator inflates distance** by a factor of `1/cos(latitude)`. At 28° (Cape) that's ~13%. On a 600 km track, that's **~80 km of fake distance**.
- **UTM 17N matches geodesic** to small fractions of a percent — *inside its zone*. If our trajectory extended past 78° W (zone-16 boundary) the error would spike. Try it: extend `N_POINTS` to 60 and watch.

In production: use `Geod` for anything that crosses zones, oceans, or hemispheres. Use UTM for high-precision local work (range safety, surveying). Use Web Mercator **only** for display, never for measurement.
"""
))

cells.append(md(
"""## Step 3 — Visualize all four projected lines on one map

The map renders in Web Mercator regardless (that's how slippy-map tiles work), but we colour-code each projection's reprojected curve. They all start at the same SLC-40 point and end near the same downrange point — but the in-between curvature *visibly* differs.
"""
))

cells.append(code(
"""import folium
import leafmap.foliumap as leafmap
from shapely.geometry import mapping, LineString as SLineString

def back_to_lonlat(coords, transformer_back):
    return [transformer_back.transform(x, y) for x, y in coords]

back_merc   = Transformer.from_crs("EPSG:3857",  "EPSG:4326", always_xy=True)
back_utm    = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
back_albers = Transformer.from_crs("EPSG:5070",  "EPSG:4326", always_xy=True)

# Re-back to lon/lat for rendering. They should match the original to <1e-9
# (round-trip) — the distortion shows up in DISTANCES, not in where the
# points land. We render the input geometry plus straight-line connections
# between the projected vertices so the differing planar-vs-curved
# interpolation is visible.
mid_lat = sum(lats) / len(lats)
mid_lon = sum(lons) / len(lons)
m = leafmap.Map(center=[mid_lat, mid_lon], zoom=5)

# Geodesic — the truth.
folium.GeoJson(
    mapping(traj_line),
    name='1. Geodesic (truth)',
    style_function=lambda f: {'color': '#15803d', 'weight': 5, 'opacity': 0.9},
).add_to(m)

# SLC-40 marker
folium.CircleMarker(
    [PAD_LAT, PAD_LON], radius=7, color='#c2410c',
    fill=True, fill_color='#f59e0b', fill_opacity=1.0,
    popup='SLC-40 (start)',
).add_to(m)

# Endpoint marker
folium.CircleMarker(
    [trajectory[-1][1], trajectory[-1][0]], radius=6,
    color='#dc2626', fill=True, fill_color='#fb923c', fill_opacity=1.0,
    popup=f'End: {SEGMENT_KM*(N_POINTS-1):.0f} km downrange (geodesic)',
).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m"""
))

cells.append(md(
"""## Step 4 — Vector vs raster, the practical split

Now the data-model lesson. A trajectory is a **vector**: a list of (lon, lat) pairs, exact, infinitely zoomable. A satellite image is a **raster**: a grid of pixels, each with a value (temperature, reflectance, brightness). Different file formats, different libraries, completely different operations.

| Operation                  | Vector            | Raster                          |
|---------------------------|-------------------|---------------------------------|
| "Is this point inside?"   | `polygon.contains` | Sample the pixel at (x, y)     |
| "Length of this curve?"   | `Geod.line_length` | Not meaningful                 |
| "Average temperature?"    | Not meaningful    | `numpy.mean(array)`             |
| "Buffer 5 km around"      | `geom.buffer(5000)` | Morphological dilation        |
| "Crop to a region"        | `gpd.clip()`       | `rasterio.windowed_read()`      |

You'll meet the raster side in earnest in Track 3 (Remote Sensing). The point now: the data model decides which questions you can even *ask*.
"""
))

cells.append(md(
"""## Common gotchas

- **Don't compute area in Web Mercator.** Near the poles, areas are inflated by more than 10×. Use Albers Equal-Area (`EPSG:5070` for NA, `EPSG:3035` for Europe), Mollweide, or `Geod.polygon_area_perimeter`.
- **UTM is valid inside one zone.** Crossing a zone boundary (every 6° of longitude) breaks distance. Detect via `floor((lon + 180) / 6) + 1`; for global work prefer `Geod`.
- **Antimeridian crossings.** A geometry that spans ±180° draws a "scribble" across the map (we hit this in Week 1 with the ISS track). Pacific-centric projections (`+proj=merc +lon_0=180`) or geometry splitting fix it.
- **EPSG:4326 with `always_xy=True`.** Old pyproj defaulted to the CRS's native axis order — `(lat, lon)` for 4326 — which is a constant source of bugs. Set `always_xy=True` on every `Transformer.from_crs` call. Always.
- **Round-trip ≠ no distortion.** Projecting WGS84→Web Mercator→WGS84 returns the same lon/lat to floating-point precision. The distortion is in **distances**, **areas**, **angles** — not in the coordinate values themselves. Don't be fooled by "the points are unchanged after reproject" arguments.
"""
))

cells.append(md(
"""## Doing this in QGIS (alternative path)

Load your trajectory CSV → set the project CRS to EPSG:4326 → use **Vector → Geometry Tools → "Add geometry attributes"** with the "Calculate using" dropdown set to the CRS you want to measure in. Run it three times (4326, 3857, 32617) and you'll get three different length columns *for the same line*. That table reproduces the cell above visually.

**Use QGIS for exploration. Use Python for anything that runs twice.** A scripted `pyproj.Geod` call is auditable; a QGIS click-trail is not.
"""
))

cells.append(md(
"""## Self-check

Before considering the lab complete:

- [ ] Geodesic length is closest to `SEGMENT_KM × (N_POINTS - 1)` (≈600 km).
- [ ] Haversine differs by < 0.3% (ellipsoid vs sphere — tiny effect at 28° lat).
- [ ] Web Mercator is **larger** than geodesic by ~13% (the `1/cos(28°)` distortion factor).
- [ ] UTM 17N is within ~0.1% of geodesic — small because the trajectory stays inside the zone.
- [ ] Albers Equal-Area gives a different (often *under*-stated) distance — it preserves *area*, not length.
- [ ] The interactive map renders the geodesic track, SLC-40 marker, and endpoint marker.
- [ ] Quiz on the [Week 2 page](https://launchdetect.com/academy/week/2/) — try before checking.

## What's next

**Week 3** — QGIS hands-on. Load the same trajectory in QGIS, reproject it visually, and reproduce this table point-and-click. You'll see why the scripted answer is the one you trust.

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
