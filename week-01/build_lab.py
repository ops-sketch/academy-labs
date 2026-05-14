"""Build week-01/lab.ipynb from canonical Python source.

Run from academy-labs/week-01/: `python build_lab.py`

The notebook teaches the three GIS primitives — Point (your live location),
Line (the real ISS ground track for the next orbit), Polygon (your country
boundary from Natural Earth) — plus the CRS transform + point-in-polygon +
geodesic-vs-Euclidean distance lessons. Personalized per learner.
"""
import json
from pathlib import Path

def md(text):
    lines = [ln + "\n" for ln in text.split("\n")]
    if lines:
        lines[-1] = lines[-1].rstrip("\n")
    return {"cell_type": "markdown", "metadata": {}, "source": lines}

def code(text):
    lines = [ln + "\n" for ln in text.split("\n")]
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
"""# Week 1: Points, Lines, Polygons — the three primitives of space GIS

**Track:** Ground Station Operator (Beginner)
**Full primer + quiz:** [https://launchdetect.com/academy/week/1/](https://launchdetect.com/academy/week/1/)
**Track index:** [https://launchdetect.com/academy/ground-station-operator/](https://launchdetect.com/academy/ground-station-operator/)

---

_GIS is built on three geometric primitives — **Point**, **Line**, and **Polygon** — and every map you've ever looked at is some combination of those three. This week you'll create one of each, using **your own live location** (a Point), **the International Space Station's real ground track** (a Line), and **the country you're in** (a Polygon). Then we'll do the canonical GIS query — is your point inside your country's polygon? — and the canonical GIS mistake — measuring distance the wrong way._
"""
))

cells.append(md(
"""## Why this week matters

Every space-domain measurement you'll ever touch comes attached to a **coordinate**, and every coordinate is meaningless without two answers: **which system is it in**, and **what does that system measure**. Get either wrong and your downstream maps, distances, and detections are silently wrong — not crash-and-burn wrong, but off-by-tens-of-kilometers wrong, which is far more dangerous because nothing in the code complains.

But before "which CRS" there's an even more fundamental question: **what shape is this thing?** A launch pad is a Point. A rocket's trajectory is a Line. A keep-out zone, a country, a hazard area is a Polygon. The three primitives compose into every spatial query you'll write for the rest of your career.

Space GIS amplifies the CRS problem in a brutal way: your coordinates come from satellites, which natively report in geocentric or sensor-local frames; you visualize them on screens that are flat (so projected); and you compare them to ground-station registries that may have been compiled in a regional datum from the 1980s. Three different coordinate systems on three sides of one query. Get fluent now or drown later.
"""
))

cells.append(md(
"""## Learning objectives

By the end of this lab you will be able to:

- Identify the **three geometric primitives** (Point, Line, Polygon) by dimension and structure
- Build each one in Python from real data — IP geolocation, a live TLE, and Natural Earth
- Distinguish **geographic** (lat/lon, `EPSG:4326`) from **projected** (Web Mercator, `EPSG:3857`) CRS
- Run a **point-in-polygon** query — the foundational spatial test
- Measure **geodesic** vs **Euclidean** distance, and know which to use when
- Handle the **antimeridian crossing** problem (your line will hit it; the ISS crosses it every orbit)
"""
))

cells.append(md(
"""## Setup — and why these dependencies

- **`leafmap`** — universal interactive-map widget for Colab. Wraps Folium + ipyleaflet + MapLibre.
- **`pyproj`** — Python bindings to PROJ, the reference implementation of every coordinate transform. Never invent your own.
- **`geopandas`** + **`shapely`** — vector geometry algebra and IO. The `geopandas.GeoDataFrame` is a pandas DataFrame whose rows know their geometry.
- **`skyfield`** — high-precision astrodynamics. We use it to turn an ISS TLE into a list of (lat, lon, time) sub-satellite points. Same library JPL uses for some of its public ephemerides.
- **`requests`** — HTTP for fetching the live TLE and the IP geolocation.
"""
))

cells.append(code(
"""# One install cell — Colab persists this for the session.
!pip install -q "leafmap[common]" pyproj geopandas shapely skyfield requests folium"""
))

cells.append(md(
"""## Step 1 — YOU as a Point

A **Point** is the simplest GIS primitive. **Zero dimensions.** Defined by exactly one (longitude, latitude) pair when we're talking lat/lon, or (x, y) in projected coordinates.

We'll grab your live location using a free IP-geolocation API. This won't be GPS-accurate — IP geolocation is typically right to within tens of kilometers, sometimes way more on cellular or VPN — but it's enough for a Week-1 lab and it's *yours*. (If you're on a campus or corporate network where everyone NATs through one exit, set `FALLBACK` below to a meaningful local location.)
"""
))

cells.append(code(
"""import requests
from shapely.geometry import Point

# Optional override (lat, lon). Used if IP geolocation fails or is bogus.
# Examples: Honolulu = (21.3099, -157.8581) | London = (51.5074, -0.1278)
FALLBACK = None

try:
    r = requests.get('https://ipapi.co/json/', timeout=6)
    geo = r.json()
    YOUR_LAT  = float(geo['latitude'])
    YOUR_LON  = float(geo['longitude'])
    YOUR_ISO2 = geo['country_code']
    YOUR_COUNTRY = geo['country_name']
    YOUR_CITY = geo.get('city', '') or '(unknown city)'
    print(f"IP-geolocated to: {YOUR_CITY}, {YOUR_COUNTRY} ({YOUR_ISO2})")
except Exception as e:
    if FALLBACK is None:
        raise RuntimeError(
            f"Geolocation failed ({e}). Set FALLBACK = (lat, lon) at top of cell."
        )
    YOUR_LAT, YOUR_LON = FALLBACK
    YOUR_ISO2, YOUR_COUNTRY, YOUR_CITY = "US", "United States", "(fallback)"
    print(f"Using fallback location: {FALLBACK}")

# Build the Point. Note: Shapely is (x, y) which means (lon, lat). Always.
you = Point(YOUR_LON, YOUR_LAT)

print()
print(f"Your point:        ({YOUR_LAT:.4f}, {YOUR_LON:.4f}) lat/lon")
print(f"Shapely geometry:  {you.wkt}")
print(f"Geometry type:     {you.geom_type}")
print(f"Dimensions:        {you.geom_type.count('Point') and 0}   # a Point has 0 dimensions")
print(f"Coordinate count:  {len(list(you.coords))}")"""
))

cells.append(md(
"""## Step 2 — The ISS as a Line

A **Line** (`LineString`) is **one-dimensional**: an ordered sequence of Points connected end-to-end. The ISS doesn't just sit somewhere — every 90 minutes it traces a complete loop around the Earth. That loop, projected straight down onto Earth's surface, is the *sub-satellite track*, and it is a **Line**.

We'll do the real thing:

1. Fetch the **live** ISS Two-Line Element set (TLE) from CelesTrak.
2. Use **Skyfield** to propagate the orbit for the next 90 minutes in 30-second steps.
3. For each step, compute the sub-satellite point (lon, lat).
4. Stitch those points into a `LineString` — handling the antimeridian.

The antimeridian thing is real: the ISS crosses ±180° longitude on most orbits. If you naively connect (179°, 0°) to (-179°, 0°) with a straight line, every renderer will draw a 358°-long zigzag across the whole map. We split the line wherever |Δlon| > 180°.
"""
))

cells.append(code(
"""from datetime import timedelta
from skyfield.api import EarthSatellite, load, wgs84
from shapely.geometry import LineString, MultiLineString
import requests

# Primary: CelesTrak (canonical TLE source for 25 years).
# Fallback 1: ivanstanojevic.me TLE mirror (JSON, also kept fresh).
# Fallback 2: embedded last-known TLE (will go stale; lab still works).
def _fetch_iss_tle():
    try:
        r = requests.get(
            "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE",
            timeout=8,
        )
        if r.ok and r.text.strip().startswith("ISS"):
            lines = r.text.strip().splitlines()
            return lines[0].strip(), lines[1].strip(), lines[2].strip(), "celestrak.org"
    except Exception:
        pass
    try:
        j = requests.get("https://tle.ivanstanojevic.me/api/tle/25544", timeout=8).json()
        return j["name"], j["line1"], j["line2"], "tle.ivanstanojevic.me"
    except Exception:
        pass
    # Embedded fallback — refresh by running build_lab.py against a live mirror.
    return (
        "ISS (ZARYA)",
        "1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993",
        "2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361",
        "embedded-fallback (may be stale)",
    )

name, line1, line2, src = _fetch_iss_tle()
print(f"TLE source: {src}")
print(f"TLE for {name}:")
print(f"  {line1}")
print(f"  {line2}")

ts = load.timescale()
sat = EarthSatellite(line1, line2, name, ts)

# Propagate one orbit (≈90 min) in 30-second steps → 181 sub-satellite points.
now = ts.now()
end = ts.from_datetime(now.utc_datetime() + timedelta(minutes=90))
times = ts.linspace(now, end, 181)
subs = wgs84.subpoint_of(sat.at(times))
lats = subs.latitude.degrees.tolist()
lons = subs.longitude.degrees.tolist()

# Antimeridian-safe assembly: split wherever the longitude wraps.
segments, cur = [], [(lons[0], lats[0])]
for i in range(1, len(lons)):
    if abs(lons[i] - lons[i-1]) > 180:
        segments.append(cur)
        cur = []
    cur.append((lons[i], lats[i]))
segments.append(cur)
iss_track = MultiLineString([LineString(s) for s in segments if len(s) >= 2])

total_vertices = sum(len(list(g.coords)) for g in iss_track.geoms)
print()
print(f"Geometry type:    {iss_track.geom_type}")
print(f"Dimensions:       1   # a Line has 1 dimension")
print(f"Sub-line count:   {len(iss_track.geoms)}   # >1 if the orbit crossed the antimeridian")
print(f"Vertices:         {total_vertices}")
print(f"First sub-point:  lat={lats[0]:.3f}, lon={lons[0]:.3f}")
print(f"Last sub-point:   lat={lats[-1]:.3f}, lon={lons[-1]:.3f}   (90 min later)")"""
))

cells.append(md(
"""## Step 3 — Your country as a Polygon

A **Polygon** is **two-dimensional**: a closed ring of Points (the *exterior*), optionally with closed rings of Points punched out of it (the *interiors*, also called *holes* — used for things like Lesotho carved out of South Africa).

We'll load **Natural Earth** at 1:110m — the canonical free dataset of country boundaries that NASA, USGS, and pretty much every GIS textbook uses. Then we'll:

1. Find **your** country by matching the ISO 3166-1 alpha-2 code from your geolocation.
2. Count the vertices. (Spoiler: country borders are not smooth.)
3. Run the canonical GIS query — `polygon.contains(point)`.

If `contains` returns `False` even though you're "in" your country, it's almost always one of two things: (a) you're on a small territory that 1:110m Natural Earth has dropped (the world's gnarliest enclaves and exclaves get simplified out), or (b) your IP-based location is in the ocean because your ISP's geocoder is rough. Both are real GIS lessons.
"""
))

cells.append(code(
"""import geopandas as gpd

# Natural Earth 1:110m countries. Public-domain. The S3 mirror works in Colab.
NE_URL = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
countries = gpd.read_file(NE_URL)
print(f"Loaded {len(countries)} countries from Natural Earth 1:110m")
print(f"CRS: {countries.crs}  ({'OK — geographic WGS84' if countries.crs.to_epsg() == 4326 else 'unexpected'})")

# Match your country. Natural Earth's column for ISO A2 has varied across versions.
candidates = [c for c in ['ISO_A2_EH', 'ISO_A2', 'ADM0_A2'] if c in countries.columns]
match = None
for col in candidates:
    sel = countries[countries[col].astype(str).str.upper() == YOUR_ISO2.upper()]
    if len(sel) >= 1:
        match = sel.iloc[0]; break

# Some territories (Taiwan, Hong Kong, Western Sahara, etc.) need name fallback.
if match is None and 'NAME' in countries.columns:
    sel = countries[countries['NAME'].str.contains(YOUR_COUNTRY, case=False, na=False, regex=False)]
    if len(sel) >= 1:
        match = sel.iloc[0]

if match is None:
    raise ValueError(f"Could not match {YOUR_ISO2} / {YOUR_COUNTRY} in Natural Earth")

your_country_name = match.get('NAME', YOUR_COUNTRY)
country_poly = match.geometry

def count_vertices(g):
    if g.geom_type == 'Polygon':
        return sum(len(r.coords) for r in [g.exterior, *g.interiors])
    return sum(count_vertices(p) for p in g.geoms)

inside = country_poly.contains(you)

print()
print(f"Your country:     {your_country_name}")
print(f"Geometry type:    {country_poly.geom_type}")
print(f"Dimensions:       2   # a Polygon has 2 dimensions")
print(f"Sub-polygons:     {1 if country_poly.geom_type == 'Polygon' else len(country_poly.geoms)}")
print(f"Vertex count:     {count_vertices(country_poly):,}   # this is what 'a country' actually is — a list of points")
print()
print(f"point.within(country)?  {inside}")
if not inside:
    print("  False is common at 1:110m for small territories, islands, or rough IP geolocation.")
    print("  In a real pipeline you'd use 1:10m and verify with a higher-precision geocoder.")"""
))

cells.append(md(
"""## All three on one map

Now we render the three primitives together: **your Point** in gold, the **ISS Line** in red, **your country Polygon** in cream with a teal border. This is the entirety of "what a map is" — composed primitives with a CRS.
"""
))

cells.append(code(
"""import folium
import leafmap.foliumap as leafmap
from shapely.geometry import mapping

m = leafmap.Map(center=[YOUR_LAT, YOUR_LON], zoom=4, draw_control=False, measure_control=False)

# --- Polygon layer: your country ---
folium.GeoJson(
    mapping(country_poly),
    name=f"Polygon: {your_country_name}",
    style_function=lambda f: {
        "fillColor": "#fff5e0", "color": "#0891b2",
        "weight": 2, "fillOpacity": 0.30,
    },
).add_to(m)

# --- Line layer: ISS ground track ---
folium.GeoJson(
    mapping(iss_track),
    name="Line: ISS next-90-min ground track",
    style_function=lambda f: {"color": "#dc2626", "weight": 3, "opacity": 0.85},
).add_to(m)

# --- Point layer: YOU ---
folium.CircleMarker(
    location=[YOUR_LAT, YOUR_LON],
    radius=9, color="#c2410c", weight=3, fill=True,
    fill_color="#f59e0b", fill_opacity=1.0,
    popup=f"You — {YOUR_CITY}<br>({YOUR_LAT:.4f}, {YOUR_LON:.4f})",
    tooltip="You (Point)",
).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m"""
))

cells.append(md(
"""## Coordinates: it's points all the way down

Now zoom out from the rendering and look at what we actually have in memory:

| Primitive | Stored as                            | Dimensions |
|-----------|--------------------------------------|------------|
| Point     | 1 `(lon, lat)` pair                  | 0          |
| Line      | Ordered list of `(lon, lat)` pairs   | 1          |
| Polygon   | Closed ring of `(lon, lat)` pairs    | 2          |

**The geometry differs, the coordinates don't.** All three are lists of `(lon, lat)` pairs in the **same CRS** (WGS84, `EPSG:4326`). The shape is just a rule about how to connect them — and the CRS is the rule that says what the numbers actually mean.

CRS is where careers go to die. Let's show why.
"""
))

cells.append(code(
"""import math
from pyproj import Transformer, Geod

# Reference point: the first sub-satellite point of the ISS track we built.
iss0_lon, iss0_lat = list(iss_track.geoms[0].coords)[0]

# (A) Reproject both points from WGS84 lat/lon → Web Mercator meters.
to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
you_x, you_y = to_merc.transform(YOUR_LON, YOUR_LAT)
iss_x, iss_y = to_merc.transform(iss0_lon, iss0_lat)

# (B) Naive Euclidean distance in Web Mercator meters — what most beginners do.
d_euclid_km = math.hypot(you_x - iss_x, you_y - iss_y) / 1000

# (C) True geodesic distance on the WGS84 ellipsoid — what you should do.
geod = Geod(ellps="WGS84")
_, _, d_geod_m = geod.inv(YOUR_LON, YOUR_LAT, iss0_lon, iss0_lat)
d_geod_km = d_geod_m / 1000

err_pct = (d_euclid_km - d_geod_km) / d_geod_km * 100

print(f"Your point in EPSG:4326:   ({YOUR_LAT:9.4f}°, {YOUR_LON:9.4f}°)")
print(f"Your point in EPSG:3857:   ({you_x:>14,.0f} m, {you_y:>14,.0f} m)")
print(f"ISS-start in EPSG:4326:    ({iss0_lat:9.4f}°, {iss0_lon:9.4f}°)")
print(f"ISS-start in EPSG:3857:    ({iss_x:>14,.0f} m, {iss_y:>14,.0f} m)")
print()
print(f"Euclidean dist in Web Mercator:  {d_euclid_km:>10,.1f} km   ← WRONG for anything > a city block")
print(f"Geodesic dist on WGS84 ellipsoid:{d_geod_km:>10,.1f} km   ← CORRECT")
print(f"Web Mercator error:              {err_pct:>+9.1f}%")
print()
print("Why: Web Mercator is a CONFORMAL projection — it preserves angles, not")
print("distances. Distortion grows with |latitude|. Greenland looks the size of")
print("Africa for the same reason your distance number here is wrong.")
print()
print("Rule of thumb: for any distance > ~100 km, use pyproj.Geod.inv() on lat/lon")
print("directly. For everything else, reproject into a LOCAL equidistant CRS")
print("(UTM zone, Lambert Conformal Conic, Albers Equal Area) before measuring.")"""
))

cells.append(md(
"""## Common gotchas (the bugs that bite in production)

- **`(lat, lon)` vs `(lon, lat)`.** Shapely and most modern libs are `(x, y) = (lon, lat)`. Some legacy APIs (old `pyproj` without `always_xy=True`, some GeoJSON parsers in the wild, anything Esri-flavored) use `(lat, lon)`. If your point lands in the Indian Ocean when you meant New York: this is the bug.
- **Antimeridian crossings.** Any orbit, flight path, or fault line that crosses ±180° will draw a wraparound zigzag if you don't split the geometry. We did the split in Step 2. Look for this any time you draw a line on a global map.
- **EPSG:4326 is geographic, not projected.** Distances in degrees are non-uniform: 1° of longitude is ~111 km at the equator and ~55 km at 60° latitude. Never compute Euclidean distance on lat/lon — project first, or use `Geod`.
- **Web Mercator breaks near the poles.** At ±85.05° it explodes. For Arctic / Antarctic work use polar stereographic (`EPSG:3413` north, `EPSG:3031` south).
- **Natural Earth ISO codes drift.** Some versions have `ISO_A2`, some `ISO_A2_EH` (Eastern Hemisphere disputed-territory flavor). Cells above fall back through both — production code should pin a known version of the dataset.
- **Point-in-polygon is exact, but only at the resolution of the polygon.** Your point may *truly* be inside your country but `False` at 1:110m because the 1:110m polygon dropped your peninsula. Resolution choice is a real engineering decision.
"""
))

cells.append(md(
"""## Doing this in QGIS (alternative path)

If you prefer desktop GIS, every step here has a QGIS equivalent — `Layer → Add Delimited Text Layer` for your point, `Layer → Add Vector Layer` for the Natural Earth zip, `Vector → Geoprocessing → Select by Location` for the point-in-polygon test. The trick is that QGIS hides the CRS work behind a "transform on the fly" toggle, which is great for exploration and dangerous for analysis: if you measure distances on a 4326 layer in QGIS, you get **degrees**, not meters.

**Use QGIS for exploration and final map composition. Use Python for anything that needs to run twice.** A Python notebook with `pyproj` is one file, version-controllable, runnable in CI. A QGIS project is a binary `.qgz` with absolute file paths.
"""
))

cells.append(md(
"""## Self-check

Before considering the lab complete, verify:

- [ ] **Point.** The location print-out shows a real city near you (or your fallback).
- [ ] **Line.** The ISS track has > 100 vertices and (usually) more than one sub-line — meaning it crossed the antimeridian.
- [ ] **Polygon.** Your country was matched and has > 100 vertices.
- [ ] **Point-in-polygon.** `country_poly.contains(you)` returned `True` (or you can explain why not).
- [ ] **CRS.** Web Mercator distance differs from geodesic distance by a non-trivial percentage.
- [ ] **Map.** The interactive map shows all three layers, the legend toggles them, and the ISS track does not draw a stripe across the whole globe.
- [ ] **Quiz on the [Week 1 page](https://launchdetect.com/academy/week/1/).** Try answering before checking the key.

## What's next

**Week 2** — Map projections in depth. We'll pick the right projection for three real space-domain tasks (a global mosaic, a polar pass, a single launch site) and see when each one lies to you.

---

Found a bug or want to contribute? Open an issue or PR at [github.com/launchdetect/academy-labs](https://github.com/launchdetect/academy-labs).
"""
))

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
        "colab": {"provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).parent / "lab.ipynb"
out.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {out} ({len(cells)} cells, {out.stat().st_size:,} bytes)")
