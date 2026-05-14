"""Build week-24/lab.ipynb — Geodesy: ellipsoid vs geoid, EGM2008."""
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
"""# Week 24: Geodesy — ellipsoid vs geoid, EGM2008, NADCON / NTv2

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/24/](https://launchdetect.com/academy/week/24/)

---

_GPS gives you altitude **above the WGS84 ellipsoid**. Your altimeter, the topographic map, and the FAA's airspace data all give altitude **above mean sea level**, which is **above the geoid** — a lumpy gravitational equipotential surface. The two differ by up to **±100 meters** worldwide. This week you compute the difference using EGM2008 and learn when each frame is correct._
"""))

cells.append(md("""## Why this week matters

A satellite at "400 km altitude" can mean two things off by 100 m depending on which surface you reference. For launch trajectory tracking, ground-station antenna pointing, and any cross-system data fusion, you must know which one your numbers are in.

| Surface       | What it is                                       | Used by                              |
|---------------|--------------------------------------------------|--------------------------------------|
| Ellipsoid (WGS84) | Smooth mathematical shape                     | GPS, satellite data, modern GIS      |
| Geoid (EGM2008)   | Gravitational equipotential ≈ mean sea level  | Survey, topography, hydrology        |
| Sea level         | The water at the coast on a calm day          | Maritime, intuitive talk             |

Ellipsoid height = orthometric (sea-level) height + geoid undulation `N`.
"""))

cells.append(code("""!pip install -q numpy matplotlib pyproj"""))

cells.append(md("""## Step 1 — Geoid undulation samples

EGM2008 is a spherical-harmonic model of Earth's gravity field that gives the geoid undulation `N(lat, lon)`. The full model has 2160-degree harmonics — too big for this lab — so we use a low-resolution lookup table of known reference values.
"""))
cells.append(code(
"""# Reference EGM2008 geoid undulations N (m) at a handful of well-known points.
# Real production code uses pyproj's geographiclib bindings or the
# `pygeoid` / `geoidheight` packages. Values below are EGM2008 N in metres
# (positive = geoid above ellipsoid).
SAMPLES = [
    ('Honolulu, HI',          21.31, -157.86,   -1.0),
    ('Cape Canaveral, FL',    28.56,  -80.58,  -27.0),
    ('Vandenberg, CA',        34.63, -120.61,  -33.0),
    ('Kourou, FR Guiana',      5.24,  -52.78,  -22.0),
    ('Baikonur, KZ',          45.92,   63.34,  -28.0),
    ('Plesetsk, RU',          62.93,   40.58,   13.0),
    ('Tanegashima, JP',       30.40,  130.97,   33.0),
    ('Mahia, NZ',            -39.26,  177.86,   16.0),
    ('Reykjavik, IS',         64.13,  -21.94,   59.0),       # high — N Atlantic ridge
    ('Maldives',               4.18,   73.51,  -103.0),      # lowest on Earth
    ('Mt Everest base',       28.00,   86.93,  -29.0),
]

print(f'{\"Location\":<28} {\"lat\":>7} {\"lon\":>8} {\"N (m)\":>7}')
print('-'*60)
for (name, lat, lon, n) in SAMPLES:
    print(f'{name:<28} {lat:>7.2f} {lon:>8.2f} {n:>+7.1f}')

print()
print(f'Range of N across these samples: {min(s[3] for s in SAMPLES):+.0f} m to {max(s[3] for s in SAMPLES):+.0f} m')
print('Worldwide range of EGM2008 N: approximately -106 m (Indian Ocean) to +85 m (Iceland/New Guinea).')"""))

cells.append(md("""## Step 2 — Convert altitudes

For a GPS-reported 400 km satellite altitude (ellipsoid-referenced) over Cape Canaveral, what's the altitude above sea level?
"""))
cells.append(code(
"""# h_orthometric = h_ellipsoid - N
def orthometric_from_ellipsoid(h_ellipsoid_m, N_m):
    return h_ellipsoid_m - N_m

# Cape Canaveral case
N_cape = -27.0  # geoid is 27 m BELOW ellipsoid at Cape
h_iss_ellipsoid = 410_000  # m, typical ISS
h_iss_orthometric = orthometric_from_ellipsoid(h_iss_ellipsoid, N_cape)
print(f'ISS altitude over Cape:  ellipsoid = {h_iss_ellipsoid/1000:.3f} km')
print(f'                         orthometric = {h_iss_orthometric/1000:.3f} km   (Δ = {-N_cape} m)')
print()
# Survey-quality benchmark: 1 m at Honolulu ellipsoid is at 2 m sea level? (Honolulu N = -1 m)
# A pad surveyed 'at 5 m sea level' is at 5 + (-1) = 4 m on the ellipsoid.
N_hono = -1
print(f'Pad surveyed at \"5 m above sea level\" in Honolulu:')
print(f'  → ellipsoid height = 5 + ({N_hono}) = {5 + N_hono} m   (use this in GIS)')

# Sanity assertion
assert abs(h_iss_orthometric - h_iss_ellipsoid - (-N_cape)) < 0.001"""))

cells.append(md("""## Step 3 — Plot N vs latitude

Geoid undulation correlates with latitude — equatorial bulge effects, plus continental anomalies. Plotting N from our samples gives a rough picture.
"""))
cells.append(code(
"""import matplotlib.pyplot as plt
import numpy as np

lats=[s[1] for s in SAMPLES]; ns=[s[3] for s in SAMPLES]; names=[s[0] for s in SAMPLES]

fig, ax = plt.subplots(figsize=(11, 5), dpi=110)
ax.scatter(lats, ns, s=80, color='#0891b2', edgecolor='#222', linewidth=0.6)
for x, y, n in zip(lats, ns, names):
    ax.annotate(n.split(',')[0], (x, y), textcoords='offset points', xytext=(5, 5), fontsize=8)
ax.axhline(0, color='#888', linestyle=':')
ax.set_xlabel('Latitude (°N)'); ax.set_ylabel('Geoid undulation N (m)')
ax.set_title('EGM2008 geoid undulation at selected reference sites')
ax.grid(True, alpha=0.4)
ax.set_xlim(-50, 75)
plt.tight_layout(); plt.show()
print('Note: N is NOT a clean function of latitude — continental gravity anomalies dominate.')"""))

cells.append(md("""## Step 4 — Datum shifts: NADCON vs NTv2

When converting historical North-American data from **NAD27** to **NAD83** (modern), you use **NADCON** — a U.S.-only grid-shift file. For Canadian data, the equivalent is **NTv2** (a binary grid format used elsewhere too — Australia, UK).

Both shift coordinates by 0-150 m depending on the location. Get this wrong and your 1950s USGS topo overlay is 100 m off your GPS pad coordinate.
"""))
cells.append(code(
"""# Demonstrate NAD27 → NAD83 shift via pyproj. The shift is grid-based; pyproj uses
# the bundled grids automatically when you use the right CRS strings.
from pyproj import Transformer

# Same point, in NAD27 vs NAD83
nad27_to_nad83 = Transformer.from_crs('EPSG:4267', 'EPSG:4269', always_xy=True)
# Cape Canaveral coordinates in NAD27 (hypothetical legacy survey)
lon27, lat27 = -80.5772, 28.5618
lon83, lat83 = nad27_to_nad83.transform(lon27, lat27)
shift_lat_m = (lat83 - lat27) * 111000
shift_lon_m = (lon83 - lon27) * 111000 * np.cos(np.radians(lat27))
print(f'Cape Canaveral NAD27 → NAD83 shift:')
print(f'  Δlat  = {(lat83-lat27)*3600:.4f} arc-sec  ({shift_lat_m:+.2f} m)')
print(f'  Δlon  = {(lon83-lon27)*3600:.4f} arc-sec  ({shift_lon_m:+.2f} m)')
print(f'  Total shift magnitude: {np.hypot(shift_lat_m, shift_lon_m):.2f} m')

# NAD83 → WGS84 is sub-meter; the big shift is NAD27 → NAD83.
nad83_to_wgs84 = Transformer.from_crs('EPSG:4269', 'EPSG:4326', always_xy=True)
lon84, lat84 = nad83_to_wgs84.transform(lon83, lat83)
print(f'\\nNAD83 → WGS84 shift:')
print(f'  Δlat = {(lat84-lat83)*3600:.6f} arc-sec  ({(lat84-lat83)*111000:+.4f} m)')
print(f'  (NAD83 was designed to match WGS84 at the meter level — they agree closely today.)')"""))

cells.append(md(
"""## Common gotchas

- **GPS / NMEA outputs WGS84 ellipsoid altitude.** "Altitude" on a phone's compass app is usually pre-corrected by an embedded geoid model; raw NMEA $GPGGA gives ellipsoid + geoid correction separately.
- **EGM96 vs EGM2008.** EGM96 is the older 360-degree model; EGM2008 is the modern 2160-degree model. Difference ~1-2 m worldwide. Use EGM2008 unless explicitly constrained.
- **Topographic maps in the US are in NAVD88** (orthometric) — feet above the geoid. UK uses ODN; rest of the world has dozens of vertical datums.
- **Geoid is not sea level.** The geoid is the *theoretical* equipotential; mean-sea-level tide gauges show ~1-2 m deviation due to ocean currents and atmospheric pressure.
- **NADCON / NTv2 grid files are gigabytes.** pyproj downloads them on first use via `pyproj-data`. For air-gapped systems, pre-cache.
"""))

cells.append(md(
"""## Self-check
- [ ] Table of N values prints with the world range of ~-106 to +85 m noted.
- [ ] ISS-altitude-over-Cape conversion adds 27 m (positive because N is negative there).
- [ ] N vs latitude plot renders with labeled points.
- [ ] NAD27 → NAD83 shift for Cape Canaveral is order ~tens-of-meters.
- [ ] You can articulate which datum each of your data sources is in.
- [ ] Quiz on the [Week 24 page](https://launchdetect.com/academy/week/24/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-24/lab.ipynb ({len(cells)} cells)")
