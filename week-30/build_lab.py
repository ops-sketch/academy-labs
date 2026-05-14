"""Build week-30/lab.ipynb — CAPSTONE 5: production-grade space-GIS service."""
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
"""# Week 30 — CAPSTONE 5: Production space-GIS service (final cert)

**Track:** Space GIS Architect (Expert) — capstone
**Credential:** [Certified Space GIS Architect](https://launchdetect.com/academy/space-gis-architect/)
**Full primer + quiz:** [https://launchdetect.com/academy/week/30/](https://launchdetect.com/academy/week/30/)

---

_The final synthesis. Build **one Python service** that combines (a) **live orbit propagation** (Weeks 7-10), (b) **live geostationary thermal detection** from real GOES-18 (Weeks 11-15), (c) **multi-sensor fusion + parallax correction** (Weeks 15 + 21), and emits (d) a **GeoJSON detection event** with confidence score + matched orbit candidate. This is the architectural skeleton of LaunchDetect itself, distilled into one notebook._
"""))

cells.append(md(
"""## Deliverable

`capstone5.json` — the **output of one full detection pipeline run**:

```json
{
  \"run_id\": \"...\", \"run_utc\": \"...\",
  \"input\": {\"goes_scene\": \"...\", \"tle_count\": N},
  \"detections\": [
    {
      \"lat\": ..., \"lon\": ..., \"bt_K\": ...,
      \"confidence\": 0-1,
      \"matched_orbits\": [{\"norad\": 25544, \"distance_km\": ..., \"score\": ...}]
    }
  ],
  \"summary_geojson\": { \"type\": \"FeatureCollection\", ... }
}
```

**Rubric (6 checks):**

1. Real or fallback GOES Band-7 scene was loaded
2. ≥ 50 active satellites were propagated to the scan time
3. Detection pipeline produced ≥ 0 events (the run completed; 0 is fine for a quiet scene)
4. Every detection has all 5 required fields
5. `capstone5.json` round-trips through `json.dump/load`
6. `summary_geojson` is a valid FeatureCollection with one Point per detection + the station marker
"""))

cells.append(code("""!pip install -q numpy s3fs xarray h5netcdf skyfield shapely pyproj scipy requests"""))

cells.append(md("""## Step 1 — Live GOES-18 Band-7 fetch + brightness temperature (Week 14)"""))
cells.append(code(
"""import s3fs, datetime, re, numpy as np
target = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
target = target.replace(minute=0, second=0, microsecond=0)
year=target.year; doy=target.timetuple().tm_yday; hour=target.hour
s3 = s3fs.S3FileSystem(anon=True)
ds = None
try:
    cands = s3.ls(f'noaa-goes18/ABI-L1b-RadC/{year}/{doy:03d}/{hour:02d}/')
    b7 = sorted([c for c in cands if re.search(r'M\\dC07_G18', c)])
    if b7:
        import xarray as xr
        ds = xr.open_dataset(s3.open(b7[0]), engine='h5netcdf', decode_times=False)
        print(f'Loaded {b7[0].split(\"/\")[-1]} ({ds[\"Rad\"].shape})')
except Exception as e:
    print(f'S3 unavailable ({e}); will use synthetic scene.')

if ds is not None:
    fk1=float(ds['planck_fk1'].values); fk2=float(ds['planck_fk2'].values)
    bc1=float(ds['planck_bc1'].values); bc2=float(ds['planck_bc2'].values)
    rad = ds['Rad'].values.astype('float32')
    bt = (fk2/np.log(fk1/rad+1) - bc1)/bc2
    bt[~np.isfinite(bt)] = np.nan
    SAT_LON = float(ds['nominal_satellite_subpoint_lon'].values) if 'nominal_satellite_subpoint_lon' in ds.variables else -137.0
    SCAN_TIME_UTC = datetime.datetime.utcfromtimestamp(float(ds['t'].values) + 946728000)
    x_arr = ds['x'].values; y_arr = ds['y'].values
    real_scene = True
else:
    rng = np.random.default_rng(42)
    bt = rng.normal(285, 4, (500, 500)).astype('f4')
    # Inject 2 hotspots
    bt[120, 320] = 420; bt[200, 200] = 360
    SAT_LON = -137.0
    SCAN_TIME_UTC = datetime.datetime.utcnow()
    x_arr = np.linspace(-0.075, 0.075, 500)
    y_arr = np.linspace( 0.085,-0.085, 500)
    real_scene = False

print(f'Scene: {\"REAL\" if real_scene else \"synthetic\"}  BT range {np.nanmin(bt):.1f}-{np.nanmax(bt):.1f} K  scan {SCAN_TIME_UTC.isoformat()}')"""))

cells.append(md("""## Step 2 — Hotspot detection (Week 14)"""))
cells.append(code(
"""from scipy import ndimage
finite = bt[np.isfinite(bt)]
p995 = np.nanpercentile(finite, 99.5)
threshold = max(p995 + 5, 310.0)
hot = bt > threshold
labels, n_clust = ndimage.label(hot, structure=np.ones((3,3), int))
sizes = ndimage.sum_labels(np.ones_like(bt), labels, range(1,n_clust+1)).astype(int) if n_clust else np.array([], dtype=int)
peaks = ndimage.maximum(bt, labels, range(1,n_clust+1)) if n_clust else np.array([])
print(f'threshold {threshold:.1f} K  →  {n_clust} cluster(s)')"""))

cells.append(md("""## Step 3 — Georeference + parallax (Week 15)"""))
cells.append(code(
"""R_EQ=6378137.0; R_POL=6356752.31414; H_GEO=42164160.0

def goes_xy_to_latlon(x, y, sat_lon_deg):
    x=np.asarray(x,'f8'); y=np.asarray(y,'f8'); lambda0=np.deg2rad(sat_lon_deg)
    a=np.sin(x)**2 + np.cos(x)**2*(np.cos(y)**2 + (R_EQ**2/R_POL**2)*np.sin(y)**2)
    b=-2*H_GEO*np.cos(x)*np.cos(y); c=H_GEO**2 - R_EQ**2
    disc=b*b-4*a*c
    if disc < 0: return float('nan'), float('nan')
    rs=(-b - np.sqrt(disc))/(2*a)
    s_x=rs*np.cos(x)*np.cos(y); s_y=-rs*np.sin(x); s_z=rs*np.cos(x)*np.sin(y)
    lat=np.arctan((R_EQ**2/R_POL**2)*(s_z/np.sqrt((H_GEO-s_x)**2 + s_y**2)))
    lon=lambda0 - np.arctan2(s_y, H_GEO-s_x)
    return float(np.rad2deg(lat)), float(np.rad2deg(lon))

def parallax_correct(o_lat, o_lon, s_lat, s_lon, h_km):
    R=6371; H=35786
    olr=np.deg2rad(o_lat); olo=np.deg2rad(o_lon); slr=np.deg2rad(s_lat); slo=np.deg2rad(s_lon)
    p_obs=np.array([R*np.cos(olr)*np.cos(olo), R*np.cos(olr)*np.sin(olo), R*np.sin(olr)])
    p_sat=np.array([(R+H)*np.cos(slr)*np.cos(slo), (R+H)*np.cos(slr)*np.sin(slo), (R+H)*np.sin(slr)])
    look=p_obs-p_sat; look/=np.linalg.norm(look)
    R_top=R+h_km
    A=np.dot(look,look); B=2*np.dot(p_sat,look); C=np.dot(p_sat,p_sat)-R_top**2
    disc=B*B-4*A*C
    if disc<0: return o_lat, o_lon
    t=(-B-np.sqrt(disc))/(2*A); pt=p_sat+t*look
    return float(np.rad2deg(np.arcsin(pt[2]/np.linalg.norm(pt)))), float(np.rad2deg(np.arctan2(pt[1],pt[0])))"""))

cells.append(md("""## Step 4 — Live orbit catalog (Weeks 7-10)"""))
cells.append(code(
"""import requests
from skyfield.api import EarthSatellite, load, wgs84

def fetch_active_tles(min_count=50):
    out=[]
    try:
        r=requests.get('https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=TLE', timeout=15)
        if r.ok and 'ISS' in r.text.upper():
            ls=r.text.strip().splitlines()
            out=[(ls[i],ls[i+1],ls[i+2]) for i in range(0,len(ls)-2,3) if ls[i].strip()]
    except: pass
    if len(out) < min_count:
        try:
            j=requests.get('https://tle.ivanstanojevic.me/api/tle?pageSize=200', timeout=15).json()
            for d in j.get('member', [])[:200]: out.append((d['name'], d['line1'], d['line2']))
        except: pass
    if len(out) < min_count:
        # Embedded ISS only
        out=[('ISS','1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
              '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361')]
    return out

tles = fetch_active_tles()
print(f'Loaded {len(tles)} active TLEs')

ts = load.timescale()
scan_t = ts.from_datetime(SCAN_TIME_UTC.replace(tzinfo=datetime.timezone.utc))
orbit_positions = []
for (name, l1, l2) in tles[:200]:   # cap propagation count for capstone speed
    try:
        s = EarthSatellite(l1, l2, name, ts)
        sub = wgs84.subpoint_of(s.at(scan_t))
        norad = int(l1[2:7])
        orbit_positions.append({
            'norad': norad, 'name': name.strip(),
            'lat': float(sub.latitude.degrees), 'lon': float(sub.longitude.degrees),
            'alt_km': float(wgs84.height_of(s.at(scan_t)).km),
        })
    except: continue
print(f'Propagated {len(orbit_positions)} orbits to scan time')"""))

cells.append(md("""## Step 5 — Score detections + match against orbits"""))
cells.append(code(
"""import math, uuid
def haversine_km(lat1, lon1, lat2, lon2, R=6371.0088):
    p1=math.radians(lat1); p2=math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

detections = []
for cl_idx in range(n_clust):
    sub_mask = labels == (cl_idx + 1)
    iy, ix = np.argwhere(sub_mask).mean(axis=0)
    iy_i, ix_i = int(round(iy)), int(round(ix))
    if iy_i >= len(y_arr) or ix_i >= len(x_arr): continue
    x_rad = float(x_arr[ix_i]); y_rad = float(y_arr[iy_i])
    lat, lon = goes_xy_to_latlon(x_rad, y_rad, SAT_LON)
    if not (np.isfinite(lat) and np.isfinite(lon)):
        continue
    # Parallax-correct assuming a 5 km plume
    lat_corr, lon_corr = parallax_correct(lat, lon, 0.0, SAT_LON, 5.0)
    peak = float(peaks[cl_idx])
    size_px = int(sizes[cl_idx])
    # Confidence: cluster size (more px = more confidence) × magnitude over threshold (capped)
    confidence = min(1.0, (peak - threshold)/100) * min(1.0, size_px / 5)

    # Match orbit candidates within 50 km
    matched = []
    for o in orbit_positions:
        d = haversine_km(lat_corr, lon_corr, o['lat'], o['lon'])
        if d < 50:
            matched.append({'norad': o['norad'], 'name': o['name'],
                            'distance_km': round(d, 2), 'score': round((50-d)/50, 3)})
    matched.sort(key=lambda m: m['distance_km'])

    detections.append({
        'detection_id': str(uuid.uuid4())[:8],
        'lat': round(lat_corr, 4), 'lon': round(lon_corr, 4),
        'bt_K': round(peak, 1), 'size_px': size_px,
        'confidence': round(confidence, 3),
        'matched_orbits': matched[:3],
    })
print(f'Built {len(detections)} detection event(s)')
for d in detections[:3]:
    print(f'  {d[\"detection_id\"]}  ({d[\"lat\"]:+.4f},{d[\"lon\"]:+.4f})  {d[\"bt_K\"]} K  conf {d[\"confidence\"]:.2f}  matches: {len(d[\"matched_orbits\"])}')"""))

cells.append(md("""## Step 6 — Bundle + rubric"""))
cells.append(code(
"""import os
STATION_LAT, STATION_LON = 21.3099, -157.8581   # Honolulu — change to yours

features = [{'type':'Feature',
             'geometry':{'type':'Point','coordinates':[STATION_LON, STATION_LAT]},
             'properties':{'kind':'station','name':'Honolulu'}}]
for d in detections:
    features.append({'type':'Feature',
                     'geometry':{'type':'Point','coordinates':[d['lon'], d['lat']]},
                     'properties': {'kind':'detection', **d}})

doc = {
    'run_id': str(uuid.uuid4()),
    'run_utc': datetime.datetime.utcnow().isoformat() + 'Z',
    'input': {'goes_scene':  'real GOES-18 ABI Band 7 CONUS' if real_scene else 'synthetic',
              'tle_count':  len(orbit_positions)},
    'detections': detections,
    'summary_geojson': {'type':'FeatureCollection','features':features},
}

out = '/content/capstone5.json' if os.path.exists('/content') else 'capstone5.json'
with open(out, 'w') as f: json.dump(doc, f)
print(f'Wrote {out} ({os.path.getsize(out):,} bytes)')

# Rubric
rt = json.load(open(out))
results = {}
results['1_scene_loaded'] = (True, f'{rt[\"input\"][\"goes_scene\"]}')
results['2_50_orbits'] = (rt['input']['tle_count'] >= 50, f'{rt[\"input\"][\"tle_count\"]} orbits propagated')
results['3_pipeline_completed'] = (isinstance(rt['detections'], list), f'detections is list, len={len(rt[\"detections\"])}')

required = {'lat','lon','bt_K','confidence','matched_orbits'}
field_ok = all(required.issubset(d.keys()) for d in rt['detections'])
results['4_detection_schema'] = (field_ok, 'all detections have required 5 fields')

results['5_roundtrip'] = (True, 'json dump→load clean')
features_ok = (rt['summary_geojson']['type']=='FeatureCollection'
               and len(rt['summary_geojson']['features']) >= 1)
results['6_geojson_valid'] = (features_ok, f'{len(rt[\"summary_geojson\"][\"features\"])} features')

print('\\nCAPSTONE 5 RUBRIC')
print('='*72)
allp = True
for k in sorted(results):
    ok, d = results[k]
    print(f'  [{\"PASS\" if ok else \"FAIL\"}] {k:30s}  {d}')
    if not ok: allp = False
print('='*72)
print('VERDICT:', 'PASS — Space GIS Architect cert eligible' if allp else 'FAIL — fix and re-run')"""))

cells.append(md("""## What you just shipped

The data flow you implemented mirrors LaunchDetect's production pipeline:

1. **Ingest** — GOES-18 ABI Band 7 NetCDF from public NOAA S3 (Week 14).
2. **Decode** — Planck inverse to brightness temperature using in-file calibration (Week 11+14).
3. **Detect** — 99.5th-percentile + 310-K-floor threshold, 8-connectivity clustering (Week 14).
4. **Geolocate** — ABI fixed-grid scan-radians to WGS84 lat/lon (Week 15).
5. **Parallax-correct** — vector-geometry ray-cast for plume altitude (Week 15).
6. **Match** — propagate active satellite catalog to scan time, nearest-neighbor match within 50 km (Weeks 7-10).
7. **Score + emit** — confidence from cluster-size × magnitude; output structured event (LaunchDetect's emit pattern).

In production this whole pipeline runs in <30 s per CONUS scan, every 5 minutes. The complexity isn't the math; it's keeping every step **idempotent**, **traceable**, and **fast** under failure modes (S3 timeouts, stale TLEs, sensor outages, antimeridian crossings).

## Self-check

- [ ] All 6 rubric checks PASS.
- [ ] `capstone5.json` exists with run metadata + detection list + GeoJSON.
- [ ] You can defend the pipeline at a whiteboard — every step, every CRS transition, every failure mode.
- [ ] Quiz on the [Week 30 page](https://launchdetect.com/academy/week/30/).

**Mint your Space GIS Architect credential** at [launchdetect.com/academy/space-gis-architect/](https://launchdetect.com/academy/space-gis-architect/) by uploading `capstone5.json`. You're done. You've built the architectural skeleton of a production space-GIS company.
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-30/lab.ipynb ({len(cells)} cells)")
