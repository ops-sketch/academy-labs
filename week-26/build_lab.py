"""Build week-26/lab.ipynb — Cloud-native EO: COG, Zarr, STAC."""
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
"""# Week 26: Cloud-native EO — COG, Zarr, STAC

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/26/](https://launchdetect.com/academy/week/26/)

---

_The old model — "download the whole scene, then read it" — falls apart at petabyte scale. The new model is **cloud-native**: data lives on S3, is structured so HTTP range-requests can fetch only the bytes you need, and is **discoverable** via standardized catalogs. This week you use all three: **STAC** to find scenes (Week 12 had a taste), **COG** to read pixel windows without downloading the whole file (Week 12 used these), and **Zarr** to do the same for multi-dimensional data._
"""))

cells.append(md(
"""## Why this week matters

| Format | What it is | When |
|--------|------------|------|
| **COG** (Cloud-Optimized GeoTIFF) | A GeoTIFF with internal tiling + overviews + IFD header at the front. Range-request friendly. | Single-band or RGB raster scenes, traditional EO. |
| **Zarr** | Chunked, compressed N-dim arrays + JSON metadata. Each chunk is one object. | Time-series climate cubes, model output, lightning data. |
| **STAC** (Spatio-Temporal Asset Catalog) | JSON spec for cataloging EO data. Items + collections + searchable. | Discoverability across heterogeneous archives. |

All three are now the de-facto for petabyte-scale archives: NOAA's Open Data Dissemination uses COG + STAC; ESA's Copernicus uses Zarr for some products; AWS Open Data is mostly COG.
"""))

cells.append(code("""!pip install -q rioxarray xarray rasterio requests"""))

cells.append(md("""## Step 1 — STAC search (re-using Week 12's API)

Find one Sentinel-2 scene over Hawaiʻi via the EarthSearch STAC API. The response is a STAC ItemCollection — JSON with one entry per matching scene + per-asset URLs.
"""))
cells.append(code(
"""import requests
STAC_API = 'https://earth-search.aws.element84.com/v1'
r = requests.post(f'{STAC_API}/search', json={
    'collections': ['sentinel-2-l2a'],
    'bbox': [-158.5, 21.0, -157.5, 22.0],   # Oʻahu
    'datetime': '2024-06-01T00:00:00Z/2024-08-31T23:59:59Z',
    'query': {'eo:cloud_cover': {'lt': 20}},
    'limit': 3,
}, timeout=15)
feats = r.json().get('features', [])
print(f'STAC search returned {len(feats)} scenes over Oʻahu')
if feats:
    s = feats[0]
    print(f'\\nFirst scene: {s[\"id\"]}')
    print(f'  Cloud cover:  {s[\"properties\"][\"eo:cloud_cover\"]:.2f}%')
    print(f'  Datetime:     {s[\"properties\"][\"datetime\"]}')
    print(f'  Asset keys:   {list(s[\"assets\"].keys())[:8]}…')
    # The 'red' asset's href is a COG URL — the next step opens it.
    print(f'  Red COG:      {s[\"assets\"][\"red\"][\"href\"][:90]}…')"""))

cells.append(md(
"""## Step 2 — COG: read a window without downloading the whole file

A COG has its image-file-directory (IFD) header at the FRONT of the file. The header tells you the tile offsets for every internal tile (typically 512×512). With a single HTTP HEAD + a few range-requests, you can fetch JUST the tiles covering your area of interest — even from a 1 GB scene.

We use `rioxarray.open_rasterio` which does this under the hood via GDAL's `vsicurl` driver.
"""))
cells.append(code(
"""import rioxarray as rxr
if feats:
    red_url = feats[0]['assets']['red']['href']
    # Open at overview level 2 (~40 m px) and bound to a tiny Oʻahu window
    da = rxr.open_rasterio(red_url, overview_level=2, masked=True).squeeze()
    print(f'Full overview shape: {da.shape}')
    print(f'CRS:                 {da.rio.crs}')

    # Clip to a 0.1° box around Honolulu
    clip = da.rio.clip_box(minx=-157.95, miny=21.27, maxx=-157.75, maxy=21.35, crs='EPSG:4326')
    print(f'Clipped shape:       {clip.shape}')
    print(f'Pixels read:         {int(clip.size):,} (~{int(clip.size)/da.size*100:.2f}% of full overview)')
    print('(The bytes fetched from S3 were even fewer — GDAL only downloaded the COG tiles overlapping the clip.)')

    # Quick sanity on the values: red-band reflectance × 10000
    print(f'Pixel value range: {int(clip.min()):,} – {int(clip.max()):,}')
else:
    print('No STAC scene; skipping COG demo.')"""))

cells.append(md(
"""## Step 3 — Zarr: chunked multi-dim arrays in object storage

Zarr is what COG is to GeoTIFF, but for **N-dimensional** arrays. Climate cubes (time × lat × lon × band), GOES SST archives, ECMWF reanalysis — all migrated to Zarr.

Demonstrate by **writing** a small Zarr cube locally and reading just one chunk. Reading a real cloud Zarr (NOAA's tide gauge cube, ERA5 reanalysis) follows the same pattern with `fsspec` URLs instead of paths.
"""))
cells.append(code(
"""import os, numpy as np, xarray as xr

# Synthetic time × lat × lon cube of brightness temperature, 30 time steps × 100 × 100
rng = np.random.default_rng(7)
times = np.arange(30)
lats = np.linspace(20, 25, 100)
lons = np.linspace(-160, -155, 100)
bt = rng.normal(295, 4, (30, 100, 100)).astype('f4')

cube = xr.DataArray(bt, dims=('time','lat','lon'),
                    coords={'time':times,'lat':lats,'lon':lons},
                    name='brightness_temperature')
cube.attrs['units'] = 'K'

zpath = '/content/cube.zarr' if os.path.exists('/content') else 'cube.zarr'
cube.to_zarr(zpath, mode='w', consolidated=True)
print(f'Wrote zarr cube to {zpath}')

# The store is a directory of chunks (one file per chunk). List them:
chunks = []
for root, _, files in os.walk(zpath):
    for f in files: chunks.append(os.path.join(root, f).replace(zpath+os.sep, ''))
print(f'Chunks on disk: {len(chunks)}')
print(f'Sample chunk filenames: {chunks[:5]}')

# Read JUST one time slice — Zarr only fetches that chunk's bytes
re_cube = xr.open_zarr(zpath, consolidated=True)
slice_t10 = re_cube['brightness_temperature'].sel(time=10).values
print(f'\\nLoaded just time=10 slice: shape {slice_t10.shape}, mean {slice_t10.mean():.2f} K')
print('(In production, this is HTTP range-requests against s3:// — same API, different store.)')"""))

cells.append(md(
"""## Common gotchas

- **COG validation.** Not every .tif on S3 is a COG. Use `rio cogeo validate file.tif` (rio-cogeo) before assuming you can range-request it.
- **Zarr chunking choice is permanent.** Pick chunks that match your read patterns: query-by-time → chunk by `(time, lat//N, lon//N)`. Query by region → chunk smaller in lat/lon.
- **STAC self-link vs catalog-link.** STAC items have a `self` link (canonical URL) and a `links` array including `parent` (collection) and `root` (catalog). Use `self` for permanent references.
- **Consolidated Zarr metadata.** Without `consolidated=True`, every open call has to walk the whole chunk hierarchy. Always consolidate after writes.
- **COG range-request granularity.** GDAL fetches 16 KB by default per range; for tiny clips on huge files set `GDAL_INGESTED_BYTES_AT_OPEN=33554432` (32 MB) to grab headers in one shot.
"""))

cells.append(md(
"""## Self-check
- [ ] STAC search returns ≥1 Sentinel-2 scene over Oʻahu (cloud < 20%).
- [ ] Opened the red COG asset and clipped to a 0.1° window without downloading the full scene.
- [ ] Zarr cube written locally with 30 time × 100×100 pixels.
- [ ] Reading time=10 slice returns a 100×100 array with mean ~295 K.
- [ ] Quiz on the [Week 26 page](https://launchdetect.com/academy/week/26/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-26/lab.ipynb ({len(cells)} cells)")
