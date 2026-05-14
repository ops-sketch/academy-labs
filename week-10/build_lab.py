"""Build week-10/lab.ipynb — Capstone 2: Spaceports and orbits.

Cert gate for Orbital Analyst. Combine: live TLE parse, 24h ground
track, instantaneous coverage polygon (visibility footprint), pass
schedule over a ground station, into one deliverable GeoJSON +
programmatic rubric.
"""
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

cells = []
cells.append(md(
"""# Week 10 — CAPSTONE 2: Spaceports and orbits

**Track:** Orbital Analyst (Intermediate) — capstone
**Credential:** [Certified Orbital Analyst](https://launchdetect.com/academy/orbital-analyst/)
**Full primer + quiz:** [https://launchdetect.com/academy/week/10/](https://launchdetect.com/academy/week/10/)

---

_Capstone 2 brings Weeks 5-9 together. Build one deliverable GeoJSON that contains: (a) the live ISS ground track for the next 24 hours, (b) an instantaneous coverage polygon (the footprint of "who can see the ISS right now"), and (c) a pass schedule for a ground station of your choice. Every artifact comes from a live CelesTrak TLE — no hardcoded coordinates. Then run the 5-check rubric. All pass = cert minted._
"""))

cells.append(md(
"""## Deliverable spec

Output: **`capstone2.geojson`** — a `FeatureCollection` with three feature types:

| Type        | Geometry            | Properties                            |
|-------------|---------------------|---------------------------------------|
| ground_track| MultiLineString     | hours, tle_epoch_utc                  |
| coverage    | Polygon             | min_elev_deg, sat_lat, sat_lon, alt_km|
| station     | Point               | name, lat, lon                        |

**Rubric:**
1. Ground track has > 1000 vertices (24 h × ~15 orbits)
2. Ground track is antimeridian-aware (uses MultiLineString, not one giant zig-zag)
3. Coverage polygon contains the sub-satellite point (sanity)
4. Coverage polygon's area is within ±20% of the geometric prediction `π · (a_visibility)²`
5. ≥ 1 pass found over the station in the next 24 h with peak elevation ≥ 10°
"""))

cells.append(md(
"""## Setup
"""))
cells.append(code(
"""!pip install -q skyfield geopandas shapely numpy requests"""))

cells.append(md(
"""## Step 1 — Configure your station + fetch live TLE
"""))
cells.append(code(
"""# ── EDIT THESE TO YOUR STATION ──────────────────────────────────────
STATION_NAME = "Honolulu, Hawaiʻi"
STATION_LAT  =  21.3099
STATION_LON  = -157.8581
# ────────────────────────────────────────────────────────────────────

import requests
def fetch_iss_tle():
    try:
        r=requests.get('https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE',timeout=8)
        if r.ok and r.text.strip().startswith('ISS'):
            ls=r.text.strip().splitlines(); return ls[0].strip(),ls[1].strip(),ls[2].strip(),'celestrak'
    except: pass
    try:
        j=requests.get('https://tle.ivanstanojevic.me/api/tle/25544',timeout=8).json()
        return j['name'],j['line1'],j['line2'],'ivanstanojevic'
    except: pass
    return ('ISS (ZARYA)',
            '1 25544U 98067A   26133.42450843  .00004829  00000+0  95080-4 0  9993',
            '2 25544  51.6310 112.1825 0007522  54.1994 305.9693 15.49203550566361',
            'embedded fallback')

name,line1,line2,src=fetch_iss_tle()
print(f'Station: {STATION_NAME} ({STATION_LAT:+.4f}, {STATION_LON:+.4f})')
print(f'TLE: {src}')
print(f'  {line1}')
print(f'  {line2}')"""))

cells.append(md(
"""## Step 2 — Ground track (24 h, antimeridian-safe)
"""))
cells.append(code(
"""from skyfield.api import EarthSatellite, load, wgs84
from datetime import timedelta
import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon, mapping

ts=load.timescale(); sat=EarthSatellite(line1,line2,name,ts)
now=ts.now()
end24=ts.from_datetime(now.utc_datetime()+timedelta(hours=24))
N=1500  # ~62 samples per minute for 24h → ~1500 total samples (1500 vertices)
times=ts.linspace(now,end24,N)
subs=wgs84.subpoint_of(sat.at(times))
lats=subs.latitude.degrees; lons=subs.longitude.degrees

# Antimeridian-safe assembly
segs=[]; cur=[(lons[0],lats[0])]
for i in range(1,len(lons)):
    if abs(lons[i]-lons[i-1])>180:
        segs.append(cur); cur=[]
    cur.append((lons[i],lats[i]))
segs.append(cur)
ground_track=MultiLineString([LineString(s) for s in segs if len(s)>=2])
print(f'Ground track: {ground_track.geom_type}, {len(ground_track.geoms)} sub-lines, {sum(len(list(g.coords)) for g in ground_track.geoms)} vertices')"""))

cells.append(md(
"""## Step 3 — Instantaneous coverage polygon

The coverage footprint of a satellite at altitude `h` is a spherical cap of angular radius `θ = arccos(R / (R + h))` from the sub-satellite point. We sample 64 points around that cap on the WGS84 ellipsoid and close them into a Polygon.
"""))
cells.append(code(
"""import math
from pyproj import Geod

geo_now=sat.at(now); sub_now=wgs84.subpoint_of(geo_now)
sat_lat=sub_now.latitude.degrees
sat_lon=sub_now.longitude.degrees
alt_km=wgs84.height_of(geo_now).km

R_EARTH=6371.0  # mean
MIN_ELEV_DEG=0  # horizon visibility — pure geometry
theta_rad=math.acos(R_EARTH/(R_EARTH+alt_km))  # half-angle of the cap
arc_km=theta_rad*R_EARTH

geod=Geod(ellps='WGS84')
azimuths=np.linspace(0,360,65)[:-1]  # 64 evenly-spaced azimuths
ring=[]
for az in azimuths:
    lon2,lat2,_=geod.fwd(sat_lon,sat_lat,az,arc_km*1000)
    ring.append((lon2,lat2))
ring.append(ring[0])
coverage=Polygon(ring)

print(f'Sub-satellite point: ({sat_lat:+.4f}, {sat_lon:+.4f})  alt {alt_km:.1f} km')
print(f'Cap half-angle: {math.degrees(theta_rad):.2f}°  ground arc radius {arc_km:.0f} km')
print(f'Coverage area (Shapely planar approx, degrees²): {coverage.area:.2f}')
# Geodesic area on ellipsoid:
poly_lons=[p[0] for p in ring]; poly_lats=[p[1] for p in ring]
geod_area_m2,_=geod.polygon_area_perimeter(poly_lons,poly_lats)
geod_area_km2=abs(geod_area_m2)/1e6
print(f'Coverage area (geodesic, km²):                   {geod_area_km2:,.0f}')
# Predicted area of a spherical cap: 2π R² (1 - cos θ)
predicted_km2=2*math.pi*R_EARTH**2*(1-math.cos(theta_rad))
print(f'Predicted spherical-cap area:                    {predicted_km2:,.0f} km²')
err=(geod_area_km2-predicted_km2)/predicted_km2*100
print(f'Measured vs predicted: {err:+.1f}%')"""))

cells.append(md(
"""## Step 4 — Pass schedule over your station
"""))
cells.append(code(
"""station=wgs84.latlon(STATION_LAT,STATION_LON,elevation_m=0)
times_ev,events=sat.find_events(station,now,end24,altitude_degrees=0)
passes=[]
i=0
while i<len(events)-2:
    if events[i]==0 and events[i+1]==1 and events[i+2]==2:
        diff=(sat-station).at(times_ev[i+1])
        alt,az,_=diff.altaz()
        passes.append({
            'rise_utc': times_ev[i].utc_datetime().isoformat(),
            'culm_utc': times_ev[i+1].utc_datetime().isoformat(),
            'set_utc':  times_ev[i+2].utc_datetime().isoformat(),
            'peak_elev_deg': float(alt.degrees),
            'peak_az_deg':   float(az.degrees),
            'duration_s':    (times_ev[i+2].utc_datetime()-times_ev[i].utc_datetime()).total_seconds(),
        })
        i+=3
    else:
        i+=1
print(f'{len(passes)} complete passes in next 24h over {STATION_NAME}')
good=[p for p in passes if p['peak_elev_deg']>=10]
print(f'  with peak ≥ 10°: {len(good)}')"""))

cells.append(md(
"""## Step 5 — Bundle to GeoJSON + run the rubric
"""))
cells.append(code(
"""import os, json
features=[]
features.append({'type':'Feature','geometry':mapping(ground_track),
                 'properties':{'kind':'ground_track','hours':24,
                               'tle_epoch_utc':str(sat.epoch.utc_datetime())}})
features.append({'type':'Feature','geometry':mapping(coverage),
                 'properties':{'kind':'coverage','min_elev_deg':MIN_ELEV_DEG,
                               'sat_lat':sat_lat,'sat_lon':sat_lon,'alt_km':alt_km,
                               'passes_next_24h':good}})
features.append({'type':'Feature','geometry':mapping(Point(STATION_LON,STATION_LAT)),
                 'properties':{'kind':'station','name':STATION_NAME,
                               'lat':STATION_LAT,'lon':STATION_LON}})
fc={'type':'FeatureCollection','features':features}

out='/content/capstone2.geojson' if os.path.exists('/content') else 'capstone2.geojson'
with open(out,'w') as f: json.dump(fc,f)
print(f'Wrote {out} ({os.path.getsize(out):,} bytes)')

# Reload and rubric
with open(out) as f: deliverable=json.load(f)
results={}
gt=next(f for f in deliverable['features'] if f['properties']['kind']=='ground_track')
cv=next(f for f in deliverable['features'] if f['properties']['kind']=='coverage')
st=next(f for f in deliverable['features'] if f['properties']['kind']=='station')

n_verts=sum(len(seg) for seg in gt['geometry']['coordinates']) if gt['geometry']['type']=='MultiLineString' else len(gt['geometry']['coordinates'])
results['1_track_vertices']=(n_verts>=1000,f'{n_verts} vertices (need ≥1000)')
results['2_antimeridian_safe']=(gt['geometry']['type']=='MultiLineString',f"geometry type {gt['geometry']['type']}")

from shapely.geometry import shape
cov_poly=shape(cv['geometry'])
sub_point=Point(cv['properties']['sat_lon'],cv['properties']['sat_lat'])
results['3_polygon_contains_subpt']=(cov_poly.contains(sub_point),
                                      f'sub-pt inside polygon: {cov_poly.contains(sub_point)}')

# Geodesic area vs predicted
ring=cv['geometry']['coordinates'][0]
poly_lons=[p[0] for p in ring]; poly_lats=[p[1] for p in ring]
geod_a,_=geod.polygon_area_perimeter(poly_lons,poly_lats)
geod_a=abs(geod_a)/1e6
alt=cv['properties']['alt_km']
theta=math.acos(6371/(6371+alt))
pred=2*math.pi*6371**2*(1-math.cos(theta))
err=abs(geod_a-pred)/pred*100
results['4_area_matches_geometry']=(err<20,f'measured {geod_a:.0f} vs predicted {pred:.0f} km² (err {err:.1f}%)')

results['5_good_pass_exists']=(len(good)>=1,f'{len(good)} passes ≥ 10° in next 24h')

print('\\n'+'='*72)
print('CAPSTONE 2 — RUBRIC REPORT')
print('='*72)
allp=True
for k in sorted(results):
    ok,d=results[k]
    print(f'  [{\"PASS\" if ok else \"FAIL\"}] {k:30s}  {d}')
    if not ok: allp=False
print('='*72)
print('VERDICT:', 'PASS — cert eligible' if allp else 'FAIL — fix issues and re-run')"""))

cells.append(md(
"""## Step 6 — Visualize the bundle

Same map renders all three feature types: the ground-track Line(s), the coverage Polygon, the station Point.
"""))
cells.append(code(
"""import folium
import leafmap.foliumap as leafmap

m=leafmap.Map(center=[STATION_LAT,STATION_LON],zoom=2,draw_control=False)

# Coverage polygon (cream fill, teal border)
folium.GeoJson(mapping(coverage),name='Coverage (instantaneous)',
               style_function=lambda f:{'fillColor':'#fff5e0','color':'#0891b2','weight':2,'fillOpacity':0.25}).add_to(m)
# Ground track (red)
folium.GeoJson(mapping(ground_track),name='Ground track (24h)',
               style_function=lambda f:{'color':'#dc2626','weight':2,'opacity':0.85}).add_to(m)
# Sub-satellite point (red dot)
folium.CircleMarker([sat_lat,sat_lon],radius=8,color='#7f1d1d',weight=2,fill=True,
                     fill_color='#dc2626',fill_opacity=1.0,popup=f'ISS now ({sat_lat:.2f}, {sat_lon:.2f})').add_to(m)
# Station (gold)
folium.CircleMarker([STATION_LAT,STATION_LON],radius=9,color='#c2410c',weight=3,fill=True,
                     fill_color='#f59e0b',fill_opacity=1.0,popup=f'Station: {STATION_NAME}').add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
m"""))

cells.append(md(
"""## Self-check + cert mint

- [ ] All 5 rubric checks PASS.
- [ ] `capstone2.geojson` exists with three features: ground_track, coverage, station.
- [ ] The map shows all three layers plus the sub-satellite Point and the station Point.
- [ ] You can articulate why the coverage area matches the spherical-cap prediction (geometry-only, no atmosphere).
- [ ] Quiz on the [Week 10 page](https://launchdetect.com/academy/week/10/).

**Mint your Orbital Analyst credential** at [launchdetect.com/academy/orbital-analyst/](https://launchdetect.com/academy/orbital-analyst/) by uploading `capstone2.geojson`. Then continue to Track 3: Remote Sensing Specialist (Weeks 11-15).
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-10/lab.ipynb ({len(cells)} cells)")
