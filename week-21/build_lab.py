"""Build week-21/lab.ipynb — Multi-sensor fusion: GOES-East + GOES-West + Himawari."""
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
"""# Week 21: Multi-sensor fusion — GOES-East + GOES-West + Himawari-9

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/21/](https://launchdetect.com/academy/week/21/)

---

_One geostationary thermal IR satellite sees a third of the world. **Three** satellites (GOES-19 East at -75°, GOES-18 West at -137°, Himawari-9 at +140°) see the whole inhabited Pacific Rim with significant overlap. The art is **fusing** their Band-7 detections: deduplicating overlapping observations, weighting by view geometry, projecting each into a common lat/lon frame. This is the production architecture LaunchDetect runs in real time._
"""))

cells.append(md("""## Why this week matters

Single-sensor detection has blind spots. Cape Canaveral viewed by GOES-19 at -75° is excellent; viewed by GOES-18 at -137° it's at the edge of useful elevation. Vandenberg is the inverse — superb on GOES-18, marginal on GOES-19. A plume crossing the boundary appears in both, possibly twice, possibly at slightly displaced coordinates due to parallax + scan-time offsets.

**Fusion strategy**:
1. **Reproject** each sensor's footprint into a common WGS84 lat/lon grid.
2. **Time-align**: scenes within ±2 min of each other get merged.
3. **Dedup**: detections from different sensors within 30 km of each other are the same event.
4. **Score**: weight each sensor's vote by view geometry (high elevation = high confidence)."""))

cells.append(code("""!pip install -q numpy shapely pyproj matplotlib"""))

cells.append(md("""## Step 1 — The three sensors' coverage footprints

Each geostationary satellite sees a spherical cap from its sub-point. Useful coverage (elevation ≥ 10° from the ground) is roughly a 70° angular radius cap.
"""))
cells.append(code(
"""import math, numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon
from pyproj import Geod

R = 6371.0   # mean Earth radius km
geod = Geod(ellps='WGS84')

# Geostationary altitude
GEO_ALT = 35786

SATS = {
    'GOES-19 (East)':  {'lon': -75.2, 'lat': 0.0, 'color': '#dc2626'},
    'GOES-18 (West)':  {'lon': -137.0, 'lat': 0.0, 'color': '#0891b2'},
    'Himawari-9':      {'lon':  140.7, 'lat': 0.0, 'color': '#15803d'},
}

# Useful-coverage half-angle from sub-point, at 10° min elevation.
# theta = acos(R/(R+h) * cos(min_elev)) - min_elev
def useful_cap_radius_km(min_elev_deg=10.0):
    me = math.radians(min_elev_deg)
    half_angle = math.acos(R / (R + GEO_ALT) * math.cos(me)) - me
    return half_angle * R, half_angle

cap_km, cap_rad = useful_cap_radius_km()
print(f'Useful-coverage cap radius: {cap_km:.0f} km  ({math.degrees(cap_rad):.1f}° half-angle from sub-point)')

# Build a polygon ring per sensor — 96 vertices at the cap boundary.
# Note: at GEO altitude a 10°-elevation cap is ~71° half-angle (~7944 km).
# That's so large its lat/lon footprint wraps around the antipode, which
# can produce self-intersecting rings near the poles. `buffer(0)` is the
# canonical Shapely fix-up to recover a valid geometry.
def cap_polygon(sub_lon, sub_lat, arc_km, nverts=96):
    ring = []
    for az in np.linspace(0, 360, nverts+1)[:-1]:
        lon2, lat2, _ = geod.fwd(sub_lon, sub_lat, az, arc_km*1000)
        ring.append((lon2, lat2))
    ring.append(ring[0])
    poly = Polygon(ring)
    return poly if poly.is_valid else poly.buffer(0)

footprints = {name: cap_polygon(s['lon'], s['lat'], cap_km) for name, s in SATS.items()}
for name, fp in footprints.items():
    ring=list(fp.exterior.coords)
    a,_=geod.polygon_area_perimeter([p[0] for p in ring],[p[1] for p in ring])
    print(f'  {name}: area {abs(a)/1e6:,.0f} km²')"""))

cells.append(md("""## Step 2 — Overlap analysis: how big are the seams?

We compute the pairwise intersections — these are the regions where two satellites see the same ground simultaneously."""))
cells.append(code(
"""pair_areas = {}
sat_names = list(footprints)
for i in range(len(sat_names)):
    for j in range(i+1, len(sat_names)):
        a_poly = footprints[sat_names[i]]; b_poly = footprints[sat_names[j]]
        inter = a_poly.intersection(b_poly)
        if inter.is_empty:
            pair_areas[(sat_names[i], sat_names[j])] = 0
            continue
        polys = [inter] if inter.geom_type == 'Polygon' else list(inter.geoms)
        total = 0
        for p in polys:
            if p.geom_type != 'Polygon': continue
            r = list(p.exterior.coords)
            ar, _ = geod.polygon_area_perimeter([x[0] for x in r],[x[1] for x in r])
            total += abs(ar)/1e6
        pair_areas[(sat_names[i], sat_names[j])] = total
        print(f'{sat_names[i]:<18} ∩ {sat_names[j]:<18}  overlap {total:>12,.0f} km²')

triple = footprints['GOES-19 (East)'].intersection(footprints['GOES-18 (West)']).intersection(footprints['Himawari-9'])
if triple.is_empty:
    print('No triple-coverage region (the three GEO sats do not all overlap).')
else:
    print(f'\\nTriple coverage exists (where all three sats see the same ground).')

print()
print('Real-world implication: most of CONUS sits in the GOES-19 ∩ GOES-18 overlap;')
print('the Hawaiian Islands sit in GOES-18 ∩ Himawari-9; Cape Verde sits in GOES-19 only.')"""))

cells.append(md("""## Step 3 — Simulate a fusion pass

Synthetic input: a "plume" lat/lon. Each sensor reports a detection at slightly displaced coordinates (due to parallax + scan-time drift). Fusion algorithm: cluster detections by 30 km proximity, weight by view geometry."""))
cells.append(code(
"""# Truth: plume at Cape Canaveral
TRUTH = (-80.5772, 28.5618)

# Three sensor reports — each with simulated parallax shift (10-30 km in
# the direction away from the sat's sub-point) and time offset.
def parallax_shift(true_lon, true_lat, sat_lon, sat_lat=0, shift_km=15):
    az,_,_ = geod.inv(true_lon, true_lat, sat_lon, sat_lat)
    az = (az + 180) % 360  # away from sat
    lon2, lat2, _ = geod.fwd(true_lon, true_lat, az, shift_km*1000)
    return (lon2, lat2)

detections = []
for name, s in SATS.items():
    fp = footprints[name]
    pt_truth = Point(*TRUTH)
    if not fp.contains(pt_truth):
        print(f'  {name}: out of view — no detection')
        continue
    shifted = parallax_shift(*TRUTH, s['lon'])
    detections.append({
        'sensor': name,
        'lon': shifted[0], 'lat': shifted[1],
        # View elevation from this sat's sub-point at the truth lat/lon
        # (rough; real computation uses the great-circle distance)
        'elev_deg': max(10, 90 - math.degrees(geod.inv(s['lon'],0,*TRUTH)[0]) / 111.32 / 100),
        't_offset_s': 0 if name == 'GOES-19 (East)' else (30 if 'West' in name else -60),
    })

print('Per-sensor reports:')
for d in detections:
    print(f'  {d[\"sensor\"]:<18}  ({d[\"lat\"]:+8.4f}, {d[\"lon\"]:+9.4f})  t_off {d[\"t_offset_s\"]:+}s')

# Fusion: cluster by 30 km
from shapely.geometry import MultiPoint
import shapely

def haversine_km(lon1, lat1, lon2, lat2, R=6371.0088):
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

clusters = []
for d in detections:
    placed = False
    for c in clusters:
        if any(haversine_km(d['lon'], d['lat'], m['lon'], m['lat']) < 30 for m in c['members']):
            c['members'].append(d); placed = True; break
    if not placed:
        clusters.append({'members':[d]})

print(f'\\n{len(clusters)} fused detection cluster(s):')
for c in clusters:
    # Weighted average lat/lon, weighted by elevation
    members = c['members']
    weights = [m['elev_deg'] for m in members]
    cw = sum(weights)
    lon_f = sum(m['lon']*w for m,w in zip(members,weights)) / cw
    lat_f = sum(m['lat']*w for m,w in zip(members,weights)) / cw
    err_km = haversine_km(TRUTH[0], TRUTH[1], lon_f, lat_f)
    print(f'  cluster of {len(members)} sensors → ({lat_f:+8.4f}, {lon_f:+9.4f})  err vs truth: {err_km:.1f} km')

assert len(clusters) == 1, 'all 3 sensors should fuse to one cluster'"""))

cells.append(md("""## Common gotchas

- **Time-align before fusion.** GOES-19 and Himawari-9 scan at different cadences; a CONUS scene and a full-disk scene are minutes apart even when both 'cover' the plume.
- **Parallax depends on plume altitude.** Surface fires don't shift; rocket plumes at 30 km shift by 10-20 km from the equator-viewing GEO at off-nadir angles. Correct *before* clustering (Week 15 gave you the formula).
- **View-geometry weighting.** At low elevation (< 20°) atmospheric path is long, contrast is reduced, geolocation error is amplified. Down-weight aggressively in the average.
- **Antimeridian.** Detections at +179° and -179° are 2° apart, not 358°. Convert to a common 0-360 frame before averaging longitudes.
- **Don't average if clusters are >50 km apart.** Two real fires near each other will get merged by a naive nearest-neighbor cluster; use DBSCAN with `eps=30` km and `min_samples=1`.
"""))

cells.append(md(
"""## Self-check
- [ ] Useful-coverage cap is ~71° half-angle (≈ 8000 km arc).
- [ ] All three pairwise overlaps are non-zero.
- [ ] Cape Canaveral fuses to 1 cluster with the simulated detections.
- [ ] Fused position is within 30 km of truth (parallax not corrected — that's Week 15's job).
- [ ] Quiz on the [Week 21 page](https://launchdetect.com/academy/week/21/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-21/lab.ipynb ({len(cells)} cells)")
