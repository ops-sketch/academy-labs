"""Build week-28/lab.ipynb — Privacy + ethics: MGRS, sub-meter, ITAR."""
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
"""# Week 28: Privacy + ethics — MGRS, sub-meter, ITAR

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/28/](https://launchdetect.com/academy/week/28/)

---

_The technical question is "how precise can my detection be?" The professional question is "**how precise should it be**?" Sub-meter precision is fun until it accidentally pinpoints individuals (e.g., a launch pad's security checkpoint, the ground crew's vehicle). This week covers the **MGRS grid** (the military-grade alternative to lat/lon), the **ITAR / EAR regulations** on space-data export, and a practical **coordinate-coarsening** pattern for privacy-respecting public APIs._
"""))

cells.append(md("""## Why this week matters

LaunchDetect publishes detections every 5 minutes to a global audience. Even 2 km GOES pixels can map to identifiable buildings near small launch sites. **Three things matter**:

1. **MGRS** — the U.S. military grid reference system. 5×5 km, 1 km, 100 m, 10 m, 1 m grid precision; pick one to coarsen to.
2. **ITAR** — International Traffic in Arms Regulations. Some satellite ephemerides and imagery have export controls; published derivatives may inherit them.
3. **EAR + 0.5 m rule** — Commercial export rules for satellite imagery. Sub-0.5-m resolution requires a license; coarser is unrestricted.
"""))

cells.append(code("""!pip install -q mgrs"""))

cells.append(md("""## Step 1 — MGRS round trip"""))
cells.append(code(
"""import mgrs

m = mgrs.MGRS()

# Convert each Track-1 launch pad to MGRS at four precisions:
PADS = [
    ('Cape Canaveral SLC-40', 28.5618, -80.5772),
    ('Vandenberg SLC-4E',     34.6321, -120.6106),
    ('Mahia LC-1',           -39.2606,  177.8649),
    ('Tanegashima',           30.40,    130.97),
    ('Honolulu (LD HQ)',      21.3099, -157.8581),
]

print(f'{\"Location\":<26} {\"1m\":>22} {\"100m\":>20} {\"1km\":>14} {\"10km\":>10}')
print('-'*100)
for (name, lat, lon) in PADS:
    s5 = m.toMGRS(lat, lon, MGRSPrecision=5)  # 1 m
    s3 = m.toMGRS(lat, lon, MGRSPrecision=3)  # 100 m
    s2 = m.toMGRS(lat, lon, MGRSPrecision=2)  # 1 km
    s1 = m.toMGRS(lat, lon, MGRSPrecision=1)  # 10 km
    print(f'{name:<26} {s5:>22} {s3:>20} {s2:>14} {s1:>10}')

# Round-trip verification: 1-m MGRS → lat/lon should match input to ~1 m
print()
print('Round-trip lat/lon precision at each MGRS scale:')
for (name, lat, lon) in [PADS[0]]:
    for precision in [5, 4, 3, 2, 1, 0]:
        gz = m.toMGRS(lat, lon, MGRSPrecision=precision)
        lat_back, lon_back = m.toLatLon(gz)
        dlat_m = (lat - lat_back) * 111000
        dlon_m = (lon - lon_back) * 111000 * 0.879   # cos(28.5°)
        err_m = (dlat_m**2 + dlon_m**2)**0.5
        digits = {5:'1 m', 4:'10 m', 3:'100 m', 2:'1 km', 1:'10 km', 0:'100 km'}[precision]
        print(f'  precision={precision} ({digits:<7s})  →  err {err_m:>10,.2f} m')"""))

cells.append(md("""## Step 2 — Privacy-preserving coordinate coarsening

A detection at (28.5618, -80.5772, ±100 m) is fine for a global feed. The same detection at (28.5618432, -80.5772101, ±0.5 m) accidentally identifies the security gate. Pattern: **always coarsen before publishing**."""))
cells.append(code(
"""def coarsen_latlon(lat: float, lon: float, grid_m: int = 1000):
    \"\"\"Snap coordinates to a grid of given size in meters.\"\"\"
    import math
    # 1 deg of lat ≈ 111000 m
    grid_deg_lat = grid_m / 111000.0
    grid_deg_lon = grid_m / (111000.0 * max(0.1, math.cos(math.radians(lat))))
    snap_lat = round(lat / grid_deg_lat) * grid_deg_lat
    snap_lon = round(lon / grid_deg_lon) * grid_deg_lon
    return round(snap_lat, 6), round(snap_lon, 6)

print('Coarsening Cape Canaveral SLC-40 (28.5618, -80.5772):')
for grid_m in (10, 100, 1000, 10000, 100000):
    cl, clon = coarsen_latlon(28.5618, -80.5772, grid_m)
    label = f'{grid_m} m' if grid_m < 1000 else f'{grid_m//1000} km'
    print(f'  {label:>6s} grid →  ({cl:+8.5f}, {clon:+9.5f})')

# Same via MGRS: drop digits
print('\\nSame via MGRS (drop trailing digits — semantically identical):')
for precision in (5, 4, 3, 2, 1):
    s = m.toMGRS(28.5618, -80.5772, MGRSPrecision=precision)
    print(f'  precision={precision}  →  {s}')"""))

cells.append(md(
"""## Step 3 — Choosing what to publish

| Audience                  | Recommended precision | Rationale |
|---------------------------|------------------------|-----------|
| Public feed / blog post  | 1 km / MGRS-2          | Identifies the site, not a building |
| Subscribers / API tier 1 | 100 m / MGRS-3         | Pad-level resolution |
| Authenticated / paid     | 10 m / MGRS-4          | Operational analysis |
| Internal / government    | 1 m / MGRS-5           | Raw sensor truth |

LaunchDetect publishes at MGRS-3 (100 m) on the public feed. Internal data retains MGRS-5.

## ITAR + EAR: the short version

- **ITAR Category XV** covers spacecraft components and their technical data. Public TLEs (CelesTrak's mainstream catalog) are EAR99, not ITAR. The categorization of derived products (e.g., a ground-track in your app) follows the inputs.
- **EAR § 740.11(e)** has the 0.5-meter rule for commercial satellite imagery — sub-0.5-m GSD requires a license, ≥ 0.5 m is unrestricted. Your overlays (Sentinel-2 at 10 m, GOES at 2 km) are unrestricted.
- **Persons of concern**: U.S. ITAR lists certain destinations + parties. Logging IP addresses on requests + maintaining export-control records is a real compliance burden if you fall under a controlled product.

This is not legal advice. Talk to a lawyer before deploying anything sub-meter or with potentially-controlled imagery.

## Common gotchas

- **MGRS at the poles.** The Universal Polar Stereographic (UPS) zone takes over above 84°N and below 80°S. The `mgrs` library handles this; just know your zone letter looks unusual at high latitudes (A, B, Y, Z).
- **Don't truncate; round.** `int(lat*100)/100` truncates toward zero — biased on negative latitudes. Use `round()`.
- **Document the privacy budget on the API.** Users need to know that values are coarsened. Otherwise downstream consumers will treat 1 km precision as if it were 1 m.
- **Combine coarsening with time-quantization** for very small datasets. A 100-m grid + 5-minute time-buckets is statistically harder to deanonymize than 1 m + millisecond.
"""))

cells.append(md(
"""## Self-check
- [ ] MGRS round-trip at precision 5 returns within ~1 m of input.
- [ ] At precision 1 (10 km), round-trip error is ~5 km.
- [ ] Coarsening 1 km grid gives consistent results at any latitude (formula scales by `cos(lat)` for longitude).
- [ ] You can pick a publication precision for a fictional space-detection feed serving (a) blog readers, (b) paid subscribers, (c) government customers.
- [ ] Quiz on the [Week 28 page](https://launchdetect.com/academy/week/28/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-28/lab.ipynb ({len(cells)} cells)")
