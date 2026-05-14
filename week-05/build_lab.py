"""Build week-05/lab.ipynb — Spatial operations: joins, buffers, intersects, dissolve.

Upgrade: implements the old TODO ("extend the buffer along a predicted
trajectory") using a real Falcon 9 az-94 ascent + a 5 km hazard buffer,
THEN intersects that with shipping-lane proxy polygons (a synthetic Gulf
Stream lane), so the keep-out vs traffic computation is concrete.
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
"""# Week 5: Spatial operations — joins, buffers, intersects, dissolve

**Track:** Orbital Analyst (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/5/](https://launchdetect.com/academy/week/5/)

---

_Five operations cover 90% of what you do to vector data: **buffer** (grow a geometry by N meters), **intersect** (where do two layers overlap), **dissolve** (merge by attribute), **clip** (cut one by another), and **spatial join** (attach attributes by location). This week you wrap them around a real launch-range hazard calculation: build a hazard corridor along a Falcon 9 ascent, intersect with a shipping-lane proxy, dissolve to a single keep-out polygon, and measure the conflict._
"""))

cells.append(md(
"""## Why this week matters

Range safety operations decide which boats can be where, which airspace closes, which beach evacuates — for every launch. The geometric core of those decisions is the five operations above. Get fluent now; reach for them weekly for the rest of the curriculum.
"""))

cells.append(md(
"""## Learning objectives

- Compute a buffer in **meters** on lat/lon data without distortion (reproject → buffer → reproject back)
- Intersect two GeoDataFrames and read the result schema
- Dissolve by an attribute to collapse N pieces into a single multipolygon
- Use `gpd.sjoin` for spatial joins
- Measure overlap with `Geod.polygon_area_perimeter`
"""))

cells.append(code(
"""!pip install -q geopandas shapely pyproj matplotlib folium leafmap[common]"""))

cells.append(md(
"""## Step 1 — Real ascent trajectory + 5 km hazard buffer

We reuse the Week 2 ascent generator (`Geod.fwd` along az 94 from SLC-40, 600 km out) and buffer it 5 km. To buffer in *meters* on lat/lon data we project to a meter-units CRS first, buffer, then reproject back to WGS84 for rendering.
"""))
cells.append(code(
"""import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
from pyproj import Geod
import math

PAD_LON, PAD_LAT = -80.5772, 28.5618
AZ, SEG_KM, N = 94.0, 40.0, 40   # 1600 km — realistic end-of-ascent
geod = Geod(ellps='WGS84')
pts=[(PAD_LON,PAD_LAT)]; lon,lat=PAD_LON,PAD_LAT
for _ in range(N-1):
    lon,lat,_=geod.fwd(lon,lat,AZ,SEG_KM*1000); pts.append((lon,lat))
trajectory=LineString(pts)
traj_gdf=gpd.GeoDataFrame({'kind':['trajectory']}, geometry=[trajectory], crs='EPSG:4326')

# Project to UTM 17N (meters), buffer 5000 m, back to WGS84
to_utm = traj_gdf.to_crs('EPSG:32617')
hazard_utm = to_utm.buffer(5000)  # 5 km
hazard = hazard_utm.to_crs('EPSG:4326')

hazard_gdf = gpd.GeoDataFrame({'kind':['hazard_5km']}, geometry=hazard.values, crs='EPSG:4326')

# Measure the buffer's area on the ellipsoid
ring = list(hazard.iloc[0].exterior.coords)
ga,_ = geod.polygon_area_perimeter([p[0] for p in ring],[p[1] for p in ring])
print(f'Trajectory:  {len(pts)} vertices, ~{(N-1)*SEG_KM:.0f} km long')
print(f'Hazard buffer: 5 km radius, area on ellipsoid = {abs(ga)/1e6:,.0f} km²')
# Predicted: roughly 2 × r × length + π × r² = 2*5*600 + π*25 ≈ 6078 km²
expected = 2 * 5 * (N-1)*SEG_KM + math.pi * 5**2
print(f'Predicted (2·r·L + π·r²):                    {expected:,.0f} km²')"""))

cells.append(md(
"""## Step 2 — Shipping-lane proxy polygons + intersection

In a real range-safety workflow you'd ingest IMO shipping-lane data or AIS density polygons. For this lab we approximate with three rectangles representing US-east-coast → Europe great-circle traffic.
"""))
cells.append(code(
"""# Three proxy lanes (longitude, latitude pairs of rectangle corners)
lanes_polys = [
    # Lane 1: near-shore Bermuda corridor, 28.0–30.5°N — intersects ascent
    Polygon([(-78, 28.0), (-65, 28.0), (-65, 30.5), (-78, 30.5)]),
    # Lane 2: mid-ascent eastbound, 26.5–28.5°N, sweeps SE under the trajectory — intersects
    Polygon([(-68, 26.5), (-50, 26.5), (-50, 28.5), (-68, 28.5)]),
    # Lane 3: North-Atlantic westbound, 32–35°N — well above the trajectory; should NOT intersect
    Polygon([(-55, 32.0), (-25, 32.0), (-25, 35.0), (-55, 35.0)]),
]
lanes_gdf = gpd.GeoDataFrame({'lane_id':[1,2,3]}, geometry=lanes_polys, crs='EPSG:4326')

# Intersect hazard with lanes
intersection = gpd.overlay(hazard_gdf, lanes_gdf, how='intersection')
print(f'{len(intersection)} intersection feature(s) between hazard and {len(lanes_gdf)} lanes:')
for i,r in intersection.iterrows():
    ring=list(r.geometry.exterior.coords) if r.geometry.geom_type=='Polygon' else list(r.geometry.geoms[0].exterior.coords)
    a,_=geod.polygon_area_perimeter([p[0] for p in ring],[p[1] for p in ring])
    print(f'  intersection with lane {r.lane_id}: area {abs(a)/1e6:.1f} km²')"""))

cells.append(md(
"""## Step 3 — Dissolve to a single keep-out polygon

The hazard intersects N lanes individually; we may want a *single* polygon representing all "conflict zones". `dissolve` collapses by an attribute (here we add a single 'all' key so it dissolves everything).
"""))
cells.append(code(
"""intersection['group']='conflict'
dissolved = intersection.dissolve(by='group')
print(f'Dissolved geometry type: {dissolved.iloc[0].geometry.geom_type}')
# Total conflict area
geom = dissolved.iloc[0].geometry
total_km2 = 0
if geom.geom_type == 'Polygon':
    polys = [geom]
else:
    polys = list(geom.geoms)
for p in polys:
    r=list(p.exterior.coords)
    a,_=geod.polygon_area_perimeter([x[0] for x in r],[x[1] for x in r])
    total_km2 += abs(a)/1e6
print(f'Total conflict area: {total_km2:.1f} km²')
print(f'(Lanes-3 outside the trajectory get zero contribution — they were excluded by the intersection.)')"""))

cells.append(md(
"""## Step 4 — Visualize all four layers on one map
"""))
cells.append(code(
"""import folium
import leafmap.foliumap as leafmap
from shapely.geometry import mapping

m = leafmap.Map(center=[32, -55], zoom=4, draw_control=False)
# Hazard buffer
folium.GeoJson(mapping(hazard.iloc[0]), name='Hazard (5 km buffer)',
               style_function=lambda f:{'fillColor':'#fde68a','color':'#f59e0b','weight':2,'fillOpacity':0.4}).add_to(m)
# Lanes
for i, p in enumerate(lanes_polys):
    folium.GeoJson(mapping(p), name=f'Lane {i+1}',
                   style_function=lambda f:{'fillColor':'#bae6fd','color':'#0891b2','weight':2,'fillOpacity':0.25}).add_to(m)
# Trajectory
folium.GeoJson(mapping(trajectory), name='Trajectory',
               style_function=lambda f:{'color':'#dc2626','weight':3,'opacity':0.9}).add_to(m)
# Conflict zones
folium.GeoJson(mapping(dissolved.iloc[0].geometry), name='Conflict (dissolved)',
               style_function=lambda f:{'fillColor':'#fecaca','color':'#dc2626','weight':2,'fillOpacity':0.55}).add_to(m)
# SLC-40
folium.CircleMarker([PAD_LAT, PAD_LON], radius=7, color='#c2410c', weight=3, fill=True,
                    fill_color='#f59e0b', fill_opacity=1.0, popup='SLC-40').add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
m"""))

cells.append(md(
"""## Step 5 — Spatial join (the 5th operation)

`sjoin` attaches one GeoDataFrame's columns to another by spatial predicate. Here: which lane does each segment of the trajectory pass through? Useful for "for each launch, what airspace did its ascent traverse?"
"""))
cells.append(code(
"""# Break the trajectory into per-segment Points for joining
segments = gpd.GeoDataFrame(
    {'seg_idx':range(len(pts))},
    geometry=[Point(p) for p in pts],
    crs='EPSG:4326'
)
joined = gpd.sjoin(segments, lanes_gdf, how='left', predicate='within')
print('Trajectory segment → lane membership:')
print(joined[['seg_idx','lane_id']].to_string(index=False))

n_in_lanes = joined['lane_id'].notna().sum()
print(f'\\n{n_in_lanes} of {len(segments)} trajectory points fall inside a defined shipping lane.')"""))

cells.append(md(
"""## Common gotchas

- **`geopandas.buffer(N)` works in the layer's CRS units.** On a 4326 layer that's degrees — a "5 unit buffer" is 555 km at the equator, way different at high latitudes. Always reproject to a metric CRS first.
- **`overlay` vs `intersection`.** `gpd.overlay(a, b, how='intersection')` keeps attributes from both. `a.intersection(b)` returns geometry only.
- **`dissolve` requires a grouping column.** If you want to merge everything, add a dummy column with a single value and dissolve on it.
- **Shapely 2.x deprecated some old APIs** (`unary_union`, `cascaded_union`). Use `.union_all()` or stick to `geopandas`'s wrappers.
- **CRS mismatches silently degrade joins.** `gpd.sjoin` warns if the CRSes differ, but always reproject one to match the other before joining.
"""))

cells.append(md(
"""## Self-check

- [ ] Hazard buffer area is within ±5% of `2·r·L + π·r²` ≈ 6,078 km².
- [ ] At least 2 of 3 lanes show non-zero intersection with the hazard.
- [ ] Dissolved conflict geometry is a `MultiPolygon` (multiple disjoint pieces).
- [ ] At least 1 trajectory segment falls inside a defined lane (sjoin returns ≥ 1 non-null).
- [ ] Map renders trajectory, buffer, lanes, conflict layers separately togglable.
- [ ] Quiz on the [Week 5 page](https://launchdetect.com/academy/week/5/).

## What's next

**Week 6 — PostGIS.** Same operations, expressed as spatial SQL. The Python here is fine for one-off analysis; PostGIS is what scales to a million launches.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-05/lab.ipynb ({len(cells)} cells)")
