"""Build week-16/lab.ipynb — Web mapping: Leaflet vs MapLibre vs OpenLayers."""
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
"""# Week 16: Web mapping — Leaflet vs MapLibre vs OpenLayers

**Track:** Mission GIS Engineer (Advanced)
**Full primer + quiz:** [https://launchdetect.com/academy/week/16/](https://launchdetect.com/academy/week/16/)

---

_Three browser map libraries compete for the same job: render geo data interactively on the web. **Leaflet** is the original — tiny, easy, raster-tile-native. **MapLibre** is the open-source fork of Mapbox GL — vector tiles, WebGL, GPU-fast. **OpenLayers** is the enterprise heavyweight — every projection, every feature, learn-curve. This week renders the SAME layer in all three so the trade-offs are visible side by side._
"""))

cells.append(md(
"""## The choice matrix

| Question                         | Leaflet  | MapLibre GL JS | OpenLayers |
|---------------------------------|----------|----------------|------------|
| Bundle size                       | ~40 KB  | ~250 KB         | ~600 KB     |
| Raster tiles                      | yes      | yes              | yes         |
| **Vector tiles**                  | plugin   | **first-class**  | yes         |
| WebGL rendering                  | plugin   | **yes**          | yes (since 8.x) |
| Non-WebMercator projections       | hard     | hard (planned)   | **yes (every EPSG)** |
| Plugin ecosystem                  | huge     | growing          | huge        |
| Use when                          | quick interactive maps with raster tiles | vector tiles, smooth pan/zoom, basemap styling, mobile | technical accuracy, projections beyond Web Mercator, federal/military work |

LaunchDetect's STM dashboard uses MapLibre because we need vector tiles + GPU rendering for the constellation overlays. The /admin dashboard uses Leaflet because the interactions are simple.
"""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q folium ipyleaflet shapely geopandas requests"""))

cells.append(md(
"""## Step 1 — A shared dataset: every Starlink satellite right now

We pull the current Starlink TLE catalog from CelesTrak (~6000 satellites in 2026), propagate to NOW, render the same point cloud in all three libraries.
"""))
cells.append(code(
"""import requests
def fetch_starlink_tle():
    \"\"\"Returns list of (name, line1, line2) tuples for active Starlinks.\"\"\"
    try:
        r = requests.get('https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=TLE', timeout=15)
        if r.ok and 'STARLINK' in r.text.upper():
            ls = r.text.strip().splitlines()
            return [(ls[i], ls[i+1], ls[i+2]) for i in range(0, len(ls)-2, 3) if ls[i].strip()]
    except: pass
    try:
        j = requests.get('https://tle.ivanstanojevic.me/api/tle?search=STARLINK&pageSize=2000', timeout=15).json()
        return [(d['name'], d['line1'], d['line2']) for d in j.get('member', [])]
    except: pass
    # Fallback: a handful of embedded TLEs so cell runs offline
    return [
        ('STARLINK-1007',
         '1 44713U 19074A   26133.55468750  .00012345  00000-0  90123-3 0  9991',
         '2 44713  53.0531 175.4322 0001234 100.1234 259.8765 15.06398765234567'),
    ]

tles = fetch_starlink_tle()
print(f'Loaded {len(tles)} Starlink TLEs')"""))

cells.append(md("""## Step 2 — Propagate all to NOW, build a GeoJSON FeatureCollection"""))
cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
ts = load.timescale(); now = ts.now()

features = []
for (name, l1, l2) in tles[:1500]:  # cap at 1500 for speed
    try:
        sat = EarthSatellite(l1, l2, name, ts)
        sub = wgs84.subpoint_of(sat.at(now))
        alt = wgs84.height_of(sat.at(now)).km
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [float(sub.longitude.degrees), float(sub.latitude.degrees)]},
            'properties': {'name': name, 'alt_km': round(alt, 1)},
        })
    except Exception:
        continue
fc = {'type': 'FeatureCollection', 'features': features}
print(f'Propagated {len(features)} Starlink positions for {now.utc_strftime(\"%Y-%m-%d %H:%M UTC\")}')

import os
out = '/content/starlinks.geojson' if os.path.exists('/content') else 'starlinks.geojson'
with open(out, 'w') as f: json.dump(fc, f)
print(f'Wrote {out} ({os.path.getsize(out):,} bytes)')"""))

cells.append(md("""## Step 3 — Render in Leaflet (via folium) — the "easy" option

`folium` is a Python wrapper around Leaflet. One line to load the GeoJSON onto a map. Performance starts to suffer past ~10k features in raw Leaflet."""))
cells.append(code(
"""import folium
m_leaflet = folium.Map(location=[0, 0], zoom_start=2, tiles='cartodbpositron')
folium.GeoJson(
    fc,
    name='Starlinks (Leaflet via folium)',
    marker=folium.CircleMarker(radius=2, color='#dc2626', fill=True, fill_opacity=0.8),
).add_to(m_leaflet)
m_leaflet"""))

cells.append(md("""## Step 4 — Render in MapLibre (via HTML/iframe in the notebook)

MapLibre is JS-only — we embed a minimal HTML page that uses the MapLibre GL JS CDN to render the same GeoJSON. GPU-accelerated, smooth pan/zoom even with 10k+ points."""))
cells.append(code(
r"""from IPython.display import HTML

geojson_str = json.dumps(fc).replace('</', '<\\/')
html = '''
<div id=\"maplibre-map\" style=\"width:100%;height:480px\"></div>
<link href=\"https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css\" rel=\"stylesheet\" />
<script src=\"https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js\"></script>
<script>
(function() {
  var map = new maplibregl.Map({
    container: 'maplibre-map',
    style: 'https://demotiles.maplibre.org/style.json',
    center: [0, 0], zoom: 1.5
  });
  map.on('load', function() {
    map.addSource('sats', { type: 'geojson', data: ''' + geojson_str + ''' });
    map.addLayer({
      id: 'sat-points', type: 'circle', source: 'sats',
      paint: {
        'circle-radius': 3, 'circle-color': '#dc2626',
        'circle-opacity': 0.85, 'circle-stroke-width': 0.5,
        'circle-stroke-color': '#7f1d1d'
      }
    });
  });
})();
</script>
'''
HTML(html)"""))

cells.append(md("""## Step 5 — Render in OpenLayers (HTML/iframe)

Same data, OpenLayers wraps it as a `VectorSource`. Notice the explicit `useGeographic()` — OpenLayers defaults to Web Mercator coordinates, unlike Leaflet/MapLibre which interpret raw `[lon, lat]` GeoJSON correctly."""))
cells.append(code(
r"""html_ol = '''
<div id=\"ol-map\" style=\"width:100%;height:480px\"></div>
<link href=\"https://cdn.jsdelivr.net/npm/ol@v8.2.0/ol.css\" rel=\"stylesheet\" />
<script src=\"https://cdn.jsdelivr.net/npm/ol@v8.2.0/dist/ol.js\"></script>
<script>
(function() {
  ol.proj.useGeographic();
  var src = new ol.source.Vector({
    features: new ol.format.GeoJSON().readFeatures(''' + geojson_str + ''')
  });
  var lyr = new ol.layer.Vector({
    source: src,
    style: new ol.style.Style({
      image: new ol.style.Circle({
        radius: 2,
        fill: new ol.style.Fill({ color: 'rgba(220,38,38,0.85)' }),
        stroke: new ol.style.Stroke({ color: '#7f1d1d', width: 0.5 })
      })
    })
  });
  var map = new ol.Map({
    target: 'ol-map',
    layers: [ new ol.layer.Tile({ source: new ol.source.OSM() }), lyr ],
    view: new ol.View({ center: [0, 0], zoom: 1.5 })
  });
})();
</script>
'''
HTML(html_ol)"""))

cells.append(md("""## Common gotchas

- **GeoJSON coordinate order is `[lon, lat]`** — all three libraries agree on this. The web habit of saying "(lat, lon)" is what breaks every other beginner.
- **Leaflet's `setView` takes `[lat, lon]` (reversed!).** Despite GeoJSON being `[lon, lat]`. Set this wrong and the map opens in the wrong hemisphere.
- **MapLibre style spec is JSON.** You can re-style the same source layer (color by altitude, size by satellite type) without re-fetching data.
- **OpenLayers defaults to Web Mercator.** Use `ol.proj.useGeographic()` if your data is `[lon, lat]`; otherwise reproject features at load time.
- **Vector tile budgets.** With 10k+ raw features, Leaflet stutters. MapLibre with vector tiles (Week 17) stays smooth. OpenLayers WebGL is fast too but a steeper API learning curve.
"""))

cells.append(md(
"""## Self-check
- [ ] Pulled live Starlink TLEs (or fell back to embedded sample).
- [ ] Propagated ≥ 100 satellites and produced a GeoJSON FeatureCollection.
- [ ] Three maps rendered: Leaflet/folium, MapLibre, OpenLayers — all show the same point cloud.
- [ ] Pan/zoom works in each; MapLibre is noticeably smoother with many points.
- [ ] Quiz on the [Week 16 page](https://launchdetect.com/academy/week/16/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-16/lab.ipynb ({len(cells)} cells)")
