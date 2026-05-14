"""Build week-20/lab.ipynb — Capstone 4: real-time spatiotemporal tracker."""
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
"""# Week 20 — CAPSTONE 4: Real-time spatiotemporal tracker

**Track:** Mission GIS Engineer (Advanced) — capstone
**Credential:** [Certified Mission GIS Engineer](https://launchdetect.com/academy/mission-gis-engineer/)
**Full primer + quiz:** [https://launchdetect.com/academy/week/20/](https://launchdetect.com/academy/week/20/)

---

_Bring Track 4 together. Build a real-time tracker that ingests **live TLEs** for ISS + a subset of Starlinks, propagates them over the next 24 hours, detects **pass events** over your ground station (rise/culmination/set with peak elevation ≥ 10°), and emits a unified event log + visualization-ready GeoJSON. The rubric runs the 5 checks the cert verifier does._
"""))

cells.append(md(
"""## Deliverable

`capstone4.json` — a single document containing:

- `metadata`: station name + lat/lon, run timestamp, TLE source
- `tracked`: list of NORAD IDs you propagated
- `events`: ordered list of pass events with rise/culm/set timestamps, peak elevation, peak azimuth
- `track_geojson`: FeatureCollection of MultiLineStrings (one per satellite's 24h ground track, antimeridian-aware)

**Rubric (5 checks, all must pass):**

1. ≥ 10 satellites tracked (live TLE fetch worked or fallbacks expanded)
2. ≥ 1 pass event detected
3. Every event has rise < culm < set (temporal monotonicity)
4. Every ground track is `MultiLineString` (antimeridian-safe)
5. `capstone4.json` round-trips cleanly through `json.dump` / `json.load`
"""))

cells.append(code("""!pip install -q skyfield shapely requests"""))

cells.append(md("""## Step 1 — Configure station + fetch active TLEs"""))
cells.append(code(
"""STATION_NAME='Honolulu'; STATION_LAT=21.3099; STATION_LON=-157.8581

import requests
def fetch_active(limit=12):
    \"\"\"ISS + first N Starlinks for breadth.\"\"\"
    out = []
    # ISS first
    try:
        r=requests.get('https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE', timeout=8)
        if r.ok:
            ls=r.text.strip().splitlines(); out.append((ls[0],ls[1],ls[2]))
    except: pass
    if not out:
        out.append(('ISS (ZARYA)',
            '1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
            '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361'))
    # Starlinks
    try:
        r=requests.get('https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=TLE', timeout=15)
        if r.ok:
            ls=r.text.strip().splitlines()
            for i in range(0, min((limit-1)*3, len(ls)-2), 3):
                if ls[i].strip(): out.append((ls[i],ls[i+1],ls[i+2]))
    except: pass
    if len(out) < 10:
        # Mirror fallback
        try:
            j=requests.get('https://tle.ivanstanojevic.me/api/tle?search=STARLINK&pageSize=15', timeout=12).json()
            for d in j.get('member', [])[:limit-1]:
                out.append((d['name'], d['line1'], d['line2']))
        except: pass
    return out

tles = fetch_active()
print(f'Tracking {len(tles)} satellites: {[t[0][:18] for t in tles[:6]]}…')"""))

cells.append(md("""## Step 2 — Propagate, build 24h tracks, detect passes"""))
cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
from datetime import timedelta
from shapely.geometry import LineString, MultiLineString, mapping
import datetime

ts=load.timescale(); now=ts.now(); end=ts.from_datetime(now.utc_datetime()+timedelta(hours=24))
station=wgs84.latlon(STATION_LAT, STATION_LON, 0)

tracked_ids = []
tracks_features = []
events = []

for (name, l1, l2) in tles:
    try:
        sat = EarthSatellite(l1, l2, name, ts)
        # Track ID = NORAD catalog number from TLE
        norad = int(l1[2:7])
        tracked_ids.append(norad)

        # 24h ground track (10-min sample for speed)
        sample_n = 24 * 6 + 1
        ttimes = ts.linspace(now, end, sample_n)
        sub = wgs84.subpoint_of(sat.at(ttimes))
        lats = sub.latitude.degrees; lons = sub.longitude.degrees

        # Antimeridian split
        segs = []; cur = [(lons[0], lats[0])]
        for i in range(1, sample_n):
            if abs(lons[i] - lons[i-1]) > 180:
                segs.append(cur); cur = []
            cur.append((lons[i], lats[i]))
        segs.append(cur)
        mls = MultiLineString([LineString(s) for s in segs if len(s) >= 2])
        tracks_features.append({
            'type': 'Feature',
            'geometry': mapping(mls),
            'properties': {'norad': norad, 'name': name.strip()},
        })

        # Pass detection
        te, ev = sat.find_events(station, now, end, altitude_degrees=0)
        i = 0
        while i < len(ev) - 2:
            if ev[i] == 0 and ev[i+1] == 1 and ev[i+2] == 2:
                diff = (sat - station).at(te[i+1])
                alt, az, _ = diff.altaz()
                peak = float(alt.degrees)
                if peak >= 10:  # ≥ 10° peak only
                    events.append({
                        'norad': norad,
                        'name': name.strip(),
                        'rise_utc': te[i].utc_datetime().isoformat(),
                        'culm_utc': te[i+1].utc_datetime().isoformat(),
                        'set_utc':  te[i+2].utc_datetime().isoformat(),
                        'peak_elev_deg': peak,
                        'peak_az_deg':   float(az.degrees),
                    })
                i += 3
            else:
                i += 1
    except Exception as e:
        print(f'  skip {name}: {e}')

events.sort(key=lambda e: e['rise_utc'])
print(f'Tracks: {len(tracks_features)}  |  Pass events (≥10°): {len(events)}')
for e in events[:5]:
    print(f'  {e[\"rise_utc\"][:19]}  {e[\"name\"][:18]:<18}  peak {e[\"peak_elev_deg\"]:>5.1f}° az {e[\"peak_az_deg\"]:>5.1f}°')"""))

cells.append(md("""## Step 3 — Assemble + save + rubric"""))
cells.append(code(
"""import os, datetime as _dt

doc = {
    'metadata': {
        'station': STATION_NAME, 'station_lat': STATION_LAT, 'station_lon': STATION_LON,
        'generated_at_utc': _dt.datetime.utcnow().isoformat() + 'Z',
        'tle_source': 'celestrak + tle.ivanstanojevic mirror',
    },
    'tracked': tracked_ids,
    'events': events,
    'track_geojson': {'type': 'FeatureCollection', 'features': tracks_features},
}

out = '/content/capstone4.json' if os.path.exists('/content') else 'capstone4.json'
with open(out, 'w') as f: json.dump(doc, f)
print(f'Wrote {out} ({os.path.getsize(out):,} bytes)')

# Round-trip the file from disk (the rubric must trust the file, not memory)
with open(out) as f: rt = json.load(f)

results = {}
results['1_min_10_sats'] = (len(rt['tracked']) >= 10, f'{len(rt[\"tracked\"])} tracked')
results['2_one_pass']    = (len(rt['events']) >= 1, f'{len(rt[\"events\"])} events')

import datetime as DT
mono = True
for e in rt['events']:
    r = DT.datetime.fromisoformat(e['rise_utc'].replace('Z','+00:00'))
    c = DT.datetime.fromisoformat(e['culm_utc'].replace('Z','+00:00'))
    s = DT.datetime.fromisoformat(e['set_utc'].replace('Z','+00:00'))
    if not (r < c < s): mono = False; break
results['3_event_monotonic'] = (mono, 'rise < culm < set' if mono else 'NOT monotonic')

all_mls = all(f['geometry']['type'] == 'MultiLineString' for f in rt['track_geojson']['features'])
results['4_antimeridian_safe'] = (all_mls,
    f\"{sum(1 for f in rt['track_geojson']['features'] if f['geometry']['type']=='MultiLineString')} / {len(rt['track_geojson']['features'])} MultiLineString\")

results['5_roundtrip'] = (True, f'reread {len(rt[\"events\"])} events, {len(rt[\"tracked\"])} sats')

print('\\n'+'='*72)
print('CAPSTONE 4 — RUBRIC REPORT')
print('='*72)
allp = True
for k in sorted(results):
    ok, d = results[k]
    print(f'  [{\"PASS\" if ok else \"FAIL\"}] {k:30s}  {d}')
    if not ok: allp = False
print('='*72)
print('VERDICT:', 'PASS — cert eligible' if allp else 'FAIL — fix and re-run')"""))

cells.append(md(
"""## Step 4 — Visualize: all tracks + the events on one map
"""))
cells.append(code(
"""import folium
import leafmap.foliumap as leafmap
m = leafmap.Map(center=[STATION_LAT, STATION_LON], zoom=2)

# Track layer
folium.GeoJson(doc['track_geojson'], name=f'{len(tracks_features)} 24-h ground tracks',
               style_function=lambda f:{'color':'#dc2626' if f['properties']['norad']==25544 else '#0891b2',
                                         'weight':1.5,'opacity':0.6}).add_to(m)

# Station
folium.CircleMarker([STATION_LAT, STATION_LON], radius=9, color='#c2410c', weight=3,
                    fill=True, fill_color='#f59e0b', fill_opacity=1.0,
                    popup=f'Station: {STATION_NAME}').add_to(m)

# Pass events — small markers at the culmination ground point (approx station)
for e in events[:30]:
    folium.CircleMarker([STATION_LAT, STATION_LON], radius=3, color='#15803d',
                        fill=True, fill_opacity=0.6,
                        popup=f\"{e['name']} pass<br>{e['rise_utc'][:19]} → {e['set_utc'][:19]}<br>peak {e['peak_elev_deg']:.1f}°\").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m"""))

cells.append(md(
"""## Self-check
- [ ] All 5 rubric checks PASS.
- [ ] `capstone4.json` exists and is a single document with `metadata`, `tracked`, `events`, `track_geojson`.
- [ ] Map shows ≥ 10 satellite tracks + station marker + at least one pass-event marker.
- [ ] You can defend the pipeline: why a 10-min sample for 24-h tracks (storage), why MultiLineString (antimeridian), why ≥10° peak filter (visibility).
- [ ] Quiz on the [Week 20 page](https://launchdetect.com/academy/week/20/).

**Mint your Mission GIS Engineer credential at [launchdetect.com/academy/mission-gis-engineer/](https://launchdetect.com/academy/mission-gis-engineer/)** by uploading `capstone4.json`. Then Track 5: **Space GIS Architect** (10 weeks).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-20/lab.ipynb ({len(cells)} cells)")
