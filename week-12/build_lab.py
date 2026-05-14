"""Build week-12/lab.ipynb — Landsat / Sentinel-2: bands, NDVI, false color.

Upgrade implements the old TODO: fetch a real Sentinel-2 L2A scene from
the AWS Open Data COG mirror (no credentials), compute NDVI = (B08-B04)
/(B08+B04), render the false-color composite.
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
"""# Week 12: Landsat / Sentinel-2 — bands, NDVI, false color

**Track:** Remote Sensing Specialist (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/12/](https://launchdetect.com/academy/week/12/)

---

_Sentinel-2 and Landsat-9 are the public-eye-in-the-sky workhorses of optical EO. This week you fetch a **real Sentinel-2 L2A scene** from AWS Open Data (no credentials needed, served as Cloud-Optimized GeoTIFFs), compute the canonical NDVI vegetation index from the red + near-infrared bands, and render a false-color composite that makes plant biomass jump off the page._
"""))

cells.append(md(
"""## Why this week matters

Sentinel-2 and Landsat-9 sit beside the geostationary thermal birds (GOES, Himawari) in any real space-GIS toolkit — but for completely different questions. They're polar-orbiting, sun-synchronous, optical+VNIR. ~10 m resolution, ~5 day revisit. The fundamental thing you do with them: **band math**. NDVI, NDWI, NBR (Normalized Burn Ratio), and dozens of indices are all `(A - B) / (A + B)` between two specific bands. Knowing which bands and why is the entire art.
"""))

cells.append(md(
"""## Learning objectives

- Identify Sentinel-2 bands B04 (red, 665 nm) and B08 (NIR, 842 nm) — the NDVI pair
- Open a Cloud-Optimized GeoTIFF (COG) directly from S3 with `rioxarray`
- Compute NDVI on a real scene and interpret the values (-1 to +1)
- Render a false-color composite (NIR→R, R→G, G→B → "plants glow red")
- Know the Landsat equivalent bands and their slightly different wavelengths
"""))

cells.append(code(
"""!pip install -q rioxarray xarray rasterio matplotlib numpy"""))

cells.append(md(
"""## Step 1 — Find a Sentinel-2 scene over Iowa cornfields

Element 84 publishes Sentinel-2 L2A as STAC-indexed COGs on AWS Open Data — `https://earth-search.aws.element84.com/v1`. We hard-code one cloud-free Iowa scene below (July 2024, peak corn-growing season). For your own work use a STAC search.
"""))
cells.append(code(
"""# STAC search the Element84 EarthSearch catalog for a recent low-cloud
# Sentinel-2 L2A scene over Iowa farmland (T15TVG MGRS tile).
# Fall back to a synthetic scene if the search fails.
import requests, json

STAC_API = 'https://earth-search.aws.element84.com/v1'
BBOX = [-94.5, 41.5, -93.5, 42.5]  # 1°×1° Iowa farmland window

RED_URL = NIR_URL = GREEN_URL = None
try:
    search = requests.post(
        f'{STAC_API}/search',
        json={
            'collections': ['sentinel-2-l2a'],
            'bbox': BBOX,
            'datetime': '2024-06-01T00:00:00Z/2024-08-31T23:59:59Z',  # peak corn growing (RFC3339 required)
            'query': {'eo:cloud_cover': {'lt': 5}},
            'limit': 5,
        },
        timeout=15,
    )
    feats = search.json().get('features', [])
    print(f'STAC search returned {len(feats)} candidate scene(s)')
    if feats:
        scene = feats[0]
        assets = scene['assets']
        # Different STAC providers use 'red'/'nir'/'green' OR 'B04'/'B08'/'B03'
        red_key  = 'red'   if 'red'   in assets else 'B04'
        nir_key  = 'nir'   if 'nir'   in assets else 'B08'
        grn_key  = 'green' if 'green' in assets else 'B03'
        RED_URL   = assets[red_key]['href']
        NIR_URL   = assets[nir_key]['href']
        GREEN_URL = assets[grn_key]['href']
        print(f'Picked: {scene[\"id\"]}  ({scene[\"properties\"][\"datetime\"]})')
        print(f'  eo:cloud_cover = {scene[\"properties\"].get(\"eo:cloud_cover\", \"?\"):.1f}%')
        print(f'  red:   {RED_URL[:90]}…')
        print(f'  nir:   {NIR_URL[:90]}…')
except Exception as e:
    print(f'STAC search failed ({e}). Will use synthetic scene below.')"""))

cells.append(md(
"""## Step 2 — Open the COGs and compute NDVI

A COG is a regular GeoTIFF with internal tiles + overviews so HTTP range-requests can fetch just the parts you need. `rioxarray.open_rasterio` does the right thing automatically.
"""))
cells.append(code(
"""import rioxarray as rxr
import xarray as xr
import numpy as np

real = False
red = nir = green = None
if RED_URL:
    try:
        # Read at overview level 2 (~40 m px) to keep memory manageable in Colab
        red   = rxr.open_rasterio(RED_URL,   overview_level=2, masked=True).squeeze()
        nir   = rxr.open_rasterio(NIR_URL,   overview_level=2, masked=True).squeeze()
        green = rxr.open_rasterio(GREEN_URL, overview_level=2, masked=True).squeeze()
        print(f'Red:   {red.shape} CRS={red.rio.crs}')
        print(f'NIR:   {nir.shape}')
        print(f'Green: {green.shape}')
        real = True
    except Exception as e:
        print(f'COG fetch failed ({e}). Using synthetic scene.')

if not real:
    rng = np.random.default_rng(0)
    h, w = 400, 400
    yy, xx = np.mgrid[:h, :w]
    # Synthetic 'crops' and 'water' regions
    veg_mask = ((xx//50) % 2 == 0)
    red   = xr.DataArray(np.where(veg_mask, 500 + rng.normal(0, 50, (h,w)), 1800 + rng.normal(0, 100, (h,w))))
    nir   = xr.DataArray(np.where(veg_mask, 4500 + rng.normal(0, 200, (h,w)), 2000 + rng.normal(0, 100, (h,w))))
    green = xr.DataArray(np.where(veg_mask, 800 + rng.normal(0, 50, (h,w)),  2200 + rng.normal(0, 100, (h,w))))
    real = False

# NDVI = (NIR - Red) / (NIR + Red), clipped to [-1, 1].
ndvi = ((nir.astype('f4') - red.astype('f4')) / (nir.astype('f4') + red.astype('f4'))).clip(-1, 1)
print(f'\\nNDVI computed. Shape: {tuple(ndvi.shape)}')
print(f'NDVI min:    {float(ndvi.min()):.3f}')
print(f'NDVI median: {float(ndvi.median()):.3f}')
print(f'NDVI max:    {float(ndvi.max()):.3f}')

# Interpretation reference:
# NDVI < 0   → water / shadow
# 0 – 0.2    → barren, urban, soil
# 0.2 – 0.5  → moderate vegetation
# 0.5 – 0.9  → dense, healthy vegetation
veg_frac = float((ndvi > 0.5).sum()) / float(ndvi.size)
print(f'Pixels with NDVI > 0.5 (healthy vegetation): {veg_frac*100:.1f}%')
if real:
    assert veg_frac > 0.05, f'Sentinel-2 scene over Iowa cropland should have ≥5% healthy vegetation; got {veg_frac*100:.1f}%'
    # No upper bound — peak corn/soybean scenes regularly hit 95-100%."""))

cells.append(md(
"""## Step 3 — Render NDVI + false color side by side

False color = (NIR → R, R → G, G → B). Plants reflect strongly in NIR, so vegetation appears bright red — historically the way photo-interpreters spotted healthy crops before NDVI was invented.
"""))
cells.append(code(
"""import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(15, 6), dpi=110)

# NDVI panel
im0 = axes[0].imshow(np.asarray(ndvi), cmap='RdYlGn', vmin=-0.3, vmax=0.9)
axes[0].set_title(f'NDVI  (median {float(ndvi.median()):.2f})')
axes[0].set_xticks([]); axes[0].set_yticks([])
plt.colorbar(im0, ax=axes[0], label='NDVI', shrink=0.7)

# False-color panel — stretch each band to 2-98 percentile for display
def stretch(arr, lo=2, hi=98):
    arr = np.asarray(arr, dtype='f4')
    p_lo, p_hi = np.nanpercentile(arr, [lo, hi])
    return np.clip((arr - p_lo) / max(p_hi - p_lo, 1e-9), 0, 1)

rgb = np.dstack([stretch(nir), stretch(red), stretch(green)])
axes[1].imshow(rgb)
axes[1].set_title('False color (NIR → R, R → G, G → B) — plants glow red')
axes[1].set_xticks([]); axes[1].set_yticks([])

plt.tight_layout()
plt.show()"""))

cells.append(md(
"""## Step 4 — Landsat-9 equivalent bands

If you want this from Landsat-9 instead of Sentinel-2, the bands map roughly:

| Index            | Sentinel-2  | Landsat-9  |
|------------------|-------------|------------|
| Red              | B04 (665 nm)| B4 (655 nm)|
| Near-infrared    | B08 (842 nm)| B5 (865 nm)|
| Green            | B03 (560 nm)| B3 (561 nm)|
| Short-wave IR 1  | B11 (1610 nm)| B6 (1609 nm)|
| Thermal IR       | n/a         | B10/B11 (~11 µm)|

Landsat-9 is at `s3://usgs-landsat/collection02/level-2/` (free, requires-payer flag).
"""))

cells.append(md(
"""## Common gotchas

- **Sentinel-2 has TWO red-edge bands (B05, B06, B07) at 705/740/783 nm** — useful for crop-stress detection. NDVI uses B04 (red, 665 nm), not red-edge.
- **L1C vs L2A.** L1C is top-of-atmosphere reflectance (uncorrected); L2A is surface reflectance (atmospherically corrected by Sen2Cor). **Always use L2A for analysis.**
- **Scale factor.** Sentinel-2 L2A pixel values are reflectance × 10000. Divide before display if you need reflectance ∈ [0,1].
- **Cloud masking.** Even "cloud-free" scenes have edges. The L2A SCL (Scene Classification Layer) flags clouds, shadows, water — apply it before averaging or change detection.
- **NDVI saturates in dense forest.** Above NDVI ~0.8 the response curve flattens — use EVI (Enhanced Vegetation Index) or NIRv for dense canopies.
"""))

cells.append(md(
"""## Self-check

- [ ] Sentinel-2 COG opened from AWS Open Data (or synthetic fallback rendered).
- [ ] NDVI computed, range within [-1, 1].
- [ ] At least 5% of pixels have NDVI > 0.5 (healthy vegetation present in the Iowa scene).
- [ ] NDVI panel renders red-to-green color ramp (water/urban red, vegetation green).
- [ ] False-color panel shows vegetation as red.
- [ ] Quiz on the [Week 12 page](https://launchdetect.com/academy/week/12/).

## What's next

**Week 13** — GOES-R ABI products (full-disk, CONUS, mesoscale). Different sensor, different cadence, different question.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-12/lab.ipynb ({len(cells)} cells)")
