"""Build week-17/lab.ipynb — Vector tiles, tippecanoe-style in Python."""
import json
from pathlib import Path
def md(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"markdown","metadata":{},"source":L}
def code(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":L}
cells=[]
cells.append(md(
"""# Week 17: Vector tiles — tippecanoe, MBTiles, and the Z/X/Y grid

**Track:** Mission GIS Engineer (Advanced)
**Full primer + quiz:** [https://launchdetect.com/academy/week/17/](https://launchdetect.com/academy/week/17/)

---

_When you need to serve millions of features to a web map without melting the browser, you reach for **vector tiles**. The data is pre-cut into a pyramid of square tiles (zoom × x × y), each containing only the features visible at that zoom level. **Tippecanoe** is Mapbox's CLI for building these; **MBTiles** is the SQLite-backed container; **MVT (Mapbox Vector Tile)** is the binary Protobuf format. This week you build a tile pyramid IN PYTHON for the full active-satellite catalog from CelesTrak (~10k sats) — same concept, no native tippecanoe install needed in Colab._
"""))

cells.append(md("""## Why this week matters

Below ~10k features Leaflet/MapLibre handle raw GeoJSON fine. Past 10k it stutters; past 100k it freezes. Vector tiles solve this by pre-filtering: at zoom 0 (global view) you might keep only 1% of features (representative sample); at zoom 10 you serve all features in that tile only. Browser only ever sees a few hundred features at any one time, no matter the dataset size.

LaunchDetect's STM dashboard ingests the full CelesTrak active catalog (~10k sats) via vector tiles — without them the dashboard would be unusably slow on phones."""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q geopandas shapely numpy mercantile requests"""))

cells.append(md(
"""## Step 1 — Fetch the full active satellite catalog

CelesTrak's `active` group is every operational orbital satellite. ~10k objects as of 2026.
"""))
cells.append(code(
"""import requests
def fetch_active():
    try:
        r = requests.get('https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=TLE', timeout=15)
        if r.ok and 'ISS' in r.text.upper():
            ls = r.text.strip().splitlines()
            return [(ls[i], ls[i+1], ls[i+2]) for i in range(0, len(ls)-2, 3) if ls[i].strip()]
    except: pass
    # Tiny embedded fallback
    return [('ISS','1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
                  '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361')]
tles = fetch_active()
print(f'Active sats: {len(tles)}')"""))

cells.append(md("""## Step 2 — Propagate, build features, tag by altitude band"""))
cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
ts = load.timescale(); now = ts.now()

features = []
for (name, l1, l2) in tles:
    try:
        s = EarthSatellite(l1, l2, name, ts)
        g = s.at(now); sub = wgs84.subpoint_of(g)
        alt = wgs84.height_of(g).km
        band = 'LEO' if alt < 2000 else 'MEO' if alt < 35000 else 'GEO'
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [float(sub.longitude.degrees), float(sub.latitude.degrees)]},
            'properties': {'name': name.strip(), 'alt_km': round(alt, 1), 'band': band},
        })
    except: continue

import collections
counts = collections.Counter(f['properties']['band'] for f in features)
print(f'Propagated {len(features)} sats:  LEO={counts[\"LEO\"]:>5}  MEO={counts[\"MEO\"]:>4}  GEO={counts[\"GEO\"]:>4}')"""))

cells.append(md(
"""## Step 3 — The tile pyramid concept

Vector tiles work on the Web Mercator quadkey grid. `mercantile` gives us the math: at zoom `z`, the world is divided into `2^z × 2^z` square tiles. Z=0 is one tile covering the world. Z=4 is 256 tiles. Z=10 is ~1M tiles.

For each `(z, x, y)` tile we collect the features whose lat/lon falls inside the tile's bbox, then sample/aggregate per zoom level.
"""))
cells.append(code(
"""import mercantile, math

def lonlat_to_tile(lon, lat, z):
    return mercantile.tile(lon, lat, z)

def features_in_tile(features, z, x, y):
    bbox = mercantile.bounds(x, y, z)
    return [f for f in features
            if bbox.west <= f['geometry']['coordinates'][0] <= bbox.east
            and bbox.south <= f['geometry']['coordinates'][1] <= bbox.north]

# How many features land in each tile at zoom 2?
zoom = 2
tile_counts = collections.Counter()
for f in features:
    lon, lat = f['geometry']['coordinates']
    if abs(lat) > 85: continue  # outside Web Mercator
    t = lonlat_to_tile(lon, lat, zoom)
    tile_counts[(t.x, t.y)] += 1
print(f'Zoom {zoom}: {len(tile_counts)} tiles contain features')
for (x, y), n in sorted(tile_counts.items(), key=lambda kv: -kv[1])[:5]:
    bbox = mercantile.bounds(x, y, zoom)
    print(f'  tile ({zoom}/{x}/{y})  {n:>4} sats   bbox: ({bbox.west:+6.1f}, {bbox.south:+6.1f}) → ({bbox.east:+6.1f}, {bbox.north:+6.1f})')"""))

cells.append(md(
"""## Step 4 — Per-zoom filtering: the "tippecanoe drop rate"

At low zoom we keep a *sample* of features so the browser sees an even global density. Tippecanoe's `-r` flag does this. With `-r 2.5` and `-Z0 -z10`: at z=10 keep 100%; at z=9 keep 40%; at z=8 keep 16%; at z=0 keep just 0.01%. Each zoom up keeps 2.5× more features than the previous.
"""))
cells.append(code(
"""# At z=0 we keep 1%; at z=4 we keep ~16%; at z=10 we keep 100%.
# Tippecanoe's default drop rate is 2.5, meaning each zoom up keeps 2.5x more.
DROP_RATE = 2.5

def keep_fraction(z, max_z=10, base_rate=DROP_RATE):
    return min(1.0, (1.0 / base_rate**(max_z - z)))

# Demonstrate the per-tile feature count after sampling
import random
random.seed(42)
def sample(features, z):
    frac = keep_fraction(z)
    return [f for f in features if random.random() < frac]

for z in range(0, 6):
    kept = sample(features, z)
    print(f'z={z}: keep {keep_fraction(z)*100:>6.2f}%  →  {len(kept):>5} features ({len(features)} → {len(kept)})')"""))

cells.append(md(
"""## Step 5 — Render z=2 with the sampled features in folium

The tile-aware rendering you'd get from MapLibre + a real `.mbtiles` file. Here in folium we just visualize the z=2 selection.
"""))
cells.append(code(
"""import folium
m = folium.Map(location=[0, 0], zoom_start=2, tiles='cartodbpositron')
sampled = sample(features, 2)
band_colors = {'LEO':'#dc2626', 'MEO':'#0891b2', 'GEO':'#f59e0b'}
for f in sampled:
    p = f['properties']; c = f['geometry']['coordinates']
    folium.CircleMarker(
        [c[1], c[0]], radius=2, color=band_colors.get(p['band'], '#888'),
        fill=True, fill_opacity=0.8,
        popup=f\"{p['name']}<br>{p['alt_km']} km · {p['band']}\",
    ).add_to(m)
print(f'Rendering {len(sampled)} sampled features (full set: {len(features)})')
m"""))

cells.append(md(
"""## To make a REAL MBTiles file

In a shell with `tippecanoe` installed:
```bash
tippecanoe -o sats.mbtiles -z10 -Z0 --drop-rate=2.5 --drop-densest-as-needed sats.geojson
```
That produces `sats.mbtiles` — a SQLite file of MVT-encoded Z/X/Y tiles. Serve via `tileserver-gl` or feed it directly into MapLibre's `vector` source.

## Common gotchas

- **Mercator clamps at ±85.05°.** A satellite directly over the pole won't have a Web-Mercator tile. Drop or clamp these.
- **Tile size limit.** Mapbox spec says MVT tiles should stay below ~500 KB; large + dense data needs aggressive `drop-rate`.
- **Always pin the drop seed.** A random sample without a fixed seed gives different visuals every build.
- **Z=22 is the deepest practical zoom.** Past z=22 you'd be at sub-meter resolution; only matters for ultra-zoomed indoor data.
"""))

cells.append(md(
"""## Self-check
- [ ] Active sat catalog loaded (≥ 100 features).
- [ ] LEO/MEO/GEO altitude classification looks right (LEO dominates).
- [ ] At z=2, multiple tiles contain features (more than one).
- [ ] Sampling fraction grows with zoom: z=0 keeps 0.01%, z=8 keeps ~16%, z=10 keeps 100% (each step is 2.5× the previous).
- [ ] Map renders sampled features colored by altitude band.
- [ ] Quiz on the [Week 17 page](https://launchdetect.com/academy/week/17/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-17/lab.ipynb ({len(cells)} cells)")
