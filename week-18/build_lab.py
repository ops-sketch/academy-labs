"""Build week-18/lab.ipynb — CesiumJS + skyfield-driven ISS orbit."""
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
"""# Week 18: 3D globes — CesiumJS + skyfield-driven ISS orbit

**Track:** Mission GIS Engineer (Advanced)
**Full primer + quiz:** [https://launchdetect.com/academy/week/18/](https://launchdetect.com/academy/week/18/)

---

_When the orbit's curvature matters and the visualization is the deliverable, you reach for **CesiumJS**: a WebGL 3D globe that draws orbits, ground tracks, sensor cones, and time-animated tracks in true 3D. This week you generate a **CZML** track file from skyfield's SGP4 propagator and animate the ISS's next 90 minutes on a live 3D globe._
"""))

cells.append(md("""## Why this week matters

For everything orbital, the 2D map is a lie. The ground track on a slippy map looks like a sinusoid; in 3D on a globe it's actually a great circle bent by Earth's rotation underneath. CesiumJS shows you the truth.

CZML is Cesium's time-dynamic JSON format. You can express a position as a list of (time, lon, lat, alt) tuples and Cesium handles interpolation, animation, and time-window playback for you."""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q skyfield requests"""))

cells.append(md(
"""## Step 1 — Propagate ISS for the next 90 min, sample every 30 s
"""))
cells.append(code(
"""import requests
from skyfield.api import EarthSatellite, load, wgs84
from datetime import timedelta, timezone

def fetch_iss():
    try:
        r=requests.get('https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE', timeout=8)
        if r.ok and r.text.strip().startswith('ISS'):
            ls=r.text.strip().splitlines(); return ls[0],ls[1],ls[2]
    except: pass
    try:
        j=requests.get('https://tle.ivanstanojevic.me/api/tle/25544', timeout=8).json()
        return j['name'], j['line1'], j['line2']
    except: pass
    return ('ISS (ZARYA)',
            '1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
            '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361')

name, l1, l2 = fetch_iss()
ts=load.timescale(); sat=EarthSatellite(l1,l2,name,ts)
now=ts.now()
end=ts.from_datetime(now.utc_datetime()+timedelta(minutes=90))
samples=181
times=ts.linspace(now, end, samples)
geo=sat.at(times); sub=wgs84.subpoint_of(geo); alt=wgs84.height_of(geo).km
print(f'{name}: {samples} samples over 90 min')"""))

cells.append(md("""## Step 2 — Build a CZML document

CZML is JSON: an array of packets. The first packet is metadata (id 'document'); subsequent packets are entities. Each entity has a `position` field that can be a time-interpolated list."""))
cells.append(code(
"""# CZML position format: [t_offset_s, lon, lat, alt_m, t_offset_s, lon, lat, alt_m, ...]
start_iso = now.utc_datetime().replace(tzinfo=timezone.utc).isoformat()
end_iso   = end.utc_datetime().replace(tzinfo=timezone.utc).isoformat()

position_array = []
for i in range(samples):
    t_off = i * (90 * 60 / (samples - 1))  # seconds from start
    position_array += [t_off,
                       float(sub.longitude.degrees[i]),
                       float(sub.latitude.degrees[i]),
                       float(alt[i] * 1000)]  # CZML expects meters

czml = [
    {
        'id': 'document',
        'name': 'ISS Orbit',
        'version': '1.0',
        'clock': {
            'interval': f'{start_iso}/{end_iso}',
            'currentTime': start_iso,
            'multiplier': 60,
            'range': 'LOOP_STOP',
            'step': 'SYSTEM_CLOCK_MULTIPLIER'
        }
    },
    {
        'id': 'iss',
        'name': name,
        'availability': f'{start_iso}/{end_iso}',
        'position': {
            'epoch': start_iso,
            'cartographicDegrees': position_array,
        },
        'point': {
            'color': {'rgba': [220, 38, 38, 255]},
            'pixelSize': 14,
            'outlineColor': {'rgba': [127, 29, 29, 255]},
            'outlineWidth': 2,
        },
        'path': {
            'material': {'solidColor': {'color': {'rgba': [220, 38, 38, 200]}}},
            'width': 2,
            'leadTime': 5400, 'trailTime': 5400,  # show full 90 min orbit
            'resolution': 60,
        },
        'label': {
            'text': 'ISS',
            'font': '14pt sans-serif',
            'fillColor': {'rgba': [255, 245, 224, 255]},
            'outlineColor': {'rgba': [0, 0, 0, 255]},
            'outlineWidth': 2,
            'style': 'FILL_AND_OUTLINE',
            'verticalOrigin': 'BOTTOM',
            'pixelOffset': {'cartesian2': [0, -16]},
        },
    },
]

import os
out = '/content/iss.czml' if os.path.exists('/content') else 'iss.czml'
with open(out, 'w') as f: json.dump(czml, f)
print(f'Wrote {out} ({os.path.getsize(out):,} bytes)')
print(f'Packets: {len(czml)}, position samples: {samples}')"""))

cells.append(md(
"""## Step 3 — Embed Cesium viewer and load the CZML

CesiumJS via CDN. We use the default ion access token built into the SDK for non-commercial viewing. The viewer is fully interactive — drag to rotate, scroll to zoom, hit the play button to animate the ISS over the next 90 minutes.
"""))
cells.append(code(
r"""from IPython.display import HTML

czml_inline = json.dumps(czml).replace('</', '<\\/')
html = '''
<link href=\"https://cesium.com/downloads/cesiumjs/releases/1.115/Build/Cesium/Widgets/widgets.css\" rel=\"stylesheet\">
<div id=\"cesium-container\" style=\"width:100%;height:520px\"></div>
<script src=\"https://cesium.com/downloads/cesiumjs/releases/1.115/Build/Cesium/Cesium.js\"></script>
<script>
(function() {
  // No ion token needed for the default ellipsoid view.
  Cesium.Ion.defaultAccessToken = '';
  var viewer = new Cesium.Viewer('cesium-container', {
    timeline: true,
    animation: true,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    navigationHelpButton: false,
    sceneModePicker: true,
    selectionIndicator: true,
    infoBox: true,
  });
  // The default offline globe imagery (Cesium-shipped natural-earth-II)
  viewer.scene.skyAtmosphere.show = true;
  viewer.scene.globe.enableLighting = true;

  var czml = ''' + czml_inline + ''';
  var ds = Cesium.CzmlDataSource.load(czml);
  viewer.dataSources.add(ds).then(function(d) {
    viewer.trackedEntity = d.entities.getById('iss');
    viewer.clock.shouldAnimate = true;
  });
})();
</script>
'''
HTML(html)"""))

cells.append(md(
"""## Common gotchas

- **CZML position is `cartographicDegrees: [t_s, lon, lat, alt_m, ...]`** — alt is in **meters above WGS84 ellipsoid**, not km. Off-by-1000 is the classic bug.
- **`epoch` is the time zero for all `t_s` offsets in the array.** Set it once at the top of the position block; every subsequent t is relative.
- **Animation requires `clock.shouldAnimate = true`** and a valid `availability` interval on each entity.
- **Cesium Ion access token.** Without a personal token you only get the basic ellipsoid + the SDK-shipped imagery (Natural Earth). Bing/Mapbox high-res imagery needs a free ion.cesium.com signup.
- **WebGL context lost on Colab page refresh.** If the globe goes blank, re-run the cell — the viewer re-initializes.
"""))

cells.append(md(
"""## Self-check
- [ ] Live ISS TLE fetched (or fallback used).
- [ ] 181 samples produced over 90 minutes.
- [ ] CZML file written, parses as valid JSON, has 2 packets.
- [ ] Cesium viewer loads in the notebook output cell.
- [ ] Hitting "play" animates the ISS along its orbit; the trailing path traces a full great-circle loop on the globe.
- [ ] Quiz on the [Week 18 page](https://launchdetect.com/academy/week/18/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-18/lab.ipynb ({len(cells)} cells)")
