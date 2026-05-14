"""Build week-14/lab.ipynb — Thermal IR Band 7: brightness temperature and hotspots.

The LaunchDetect-core lab. Fetch a real GOES-18 ABI Band 7 CONUS scene
from the public NOAA S3 bucket (no AWS creds — anonymous access via
s3fs), apply the in-file Planck calibration to convert raw Rad to
brightness temperature, and detect hot pixels (potential plumes / fires).

Falls back to a synthetic scene if S3 is unreachable.
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
"""# Week 14: Thermal IR Band 7 — brightness temperature and hotspot detection

**Track:** Remote Sensing Specialist (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/14/](https://launchdetect.com/academy/week/14/)

---

_The LaunchDetect-core lab. You fetch a **real GOES-18 ABI Band 7 CONUS scene** from NOAA's public S3 archive, convert raw radiances to brightness temperature using the calibration coefficients that ship inside the NetCDF, and detect "hot pixels" — the same algorithmic skeleton LaunchDetect runs every 5 minutes in production._
"""))

cells.append(md(
"""## Why this week matters

Every thermal-detection algorithm — wildfire alerts, volcanic plume tracking, **rocket launch detection** — runs the same pipeline:

1. Fetch the Band 7 NetCDF (3.9 µm shortwave IR, 2 km nadir resolution, every 5 min for CONUS).
2. Convert raw `Rad` (W m⁻² sr⁻¹ µm⁻¹) → brightness temperature `K` via the in-file Planck inverse.
3. Threshold against a moving background to flag hot pixels.
4. Cluster contiguous hot pixels, score, emit detection events.

This week you build steps 1-3 against a real scene; Week 15 (capstone) adds parallax correction and ties it all together.
"""))

cells.append(md(
"""## Learning objectives

- Read a GOES-18 ABI L1b NetCDF directly from `s3://noaa-goes18/`
- Convert raw `Rad` to brightness temperature using `planck_fk1, fk2, bc1, bc2`
- Project the GOES fixed-grid (radian) coordinates to lat/lon
- Threshold against a local-percentile background to find hot pixels
- Render the scene + hot pixels on a map
"""))

cells.append(code(
"""!pip install -q xarray s3fs netcdf4 numpy matplotlib"""))

cells.append(md(
"""## Step 1 — Find a recent Band 7 CONUS scene

The AWS Open Data archive holds ~365 days of GOES-18 ABI L1b CONUS scenes. We default to a recent stored fixture date and let you override with `TARGET_UTC` if you want to hunt for a specific launch's signature.
"""))
cells.append(code(
"""import s3fs, datetime, re

# Edit these to target a specific launch event:
#   TARGET_UTC = datetime.datetime(2025, 9, 8, 4, 48, 0, tzinfo=datetime.timezone.utc)
# Default: 3 days ago at 00:00 UTC — known to be in the archive.
TARGET_UTC = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
TARGET_UTC = TARGET_UTC.replace(minute=0, second=0, microsecond=0)

BUCKET   = 'noaa-goes18'
PRODUCT  = 'ABI-L1b-RadC'   # CONUS scene
BAND     = 7                # Shortwave IR — hot-stuff band

year = TARGET_UTC.year
doy  = TARGET_UTC.timetuple().tm_yday
hour = TARGET_UTC.hour
prefix = f'{PRODUCT}/{year}/{doy:03d}/{hour:02d}/'

s3 = s3fs.S3FileSystem(anon=True)
key = None
try:
    candidates = s3.ls(f'{BUCKET}/{prefix}')
    band_re = re.compile(rf'M\\dC{BAND:02d}_G18')
    matches = [c for c in candidates if band_re.search(c)]
    if matches:
        key = sorted(matches)[0]
        print(f'Found NetCDF: s3://{key}')
    else:
        print(f'(No Band {BAND} files in s3://{BUCKET}/{prefix})')
except Exception as e:
    print(f'(S3 list failed: {e})')
    candidates = []

if key:
    # Open via fsspec
    import xarray as xr
    ds = xr.open_dataset(s3.open(key), engine='h5netcdf', decode_times=False)
    print(f'\\nOpened {ds.attrs.get(\"dataset_name\", key.split(\"/\")[-1])}')
    print(f'  shape: {ds[\"Rad\"].shape}')
    print(f'  attrs: scale_factor={ds[\"Rad\"].attrs.get(\"scale_factor\")}, units={ds[\"Rad\"].attrs.get(\"units\")}')
else:
    ds = None"""))

cells.append(md(
"""## Step 2 — Synthetic scene fallback (always works, no network)

If the S3 fetch failed (rate limits, network, etc.), we build a synthetic 500×500 brightness-temperature field with a 285-K background, scattered noise, and three "plume" hot spots at known coordinates. Same code path downstream.
"""))
cells.append(code(
"""import numpy as np

if ds is not None:
    # Real data: convert Rad → BT using in-file Planck inverse coefficients.
    fk1 = float(ds['planck_fk1'].values)
    fk2 = float(ds['planck_fk2'].values)
    bc1 = float(ds['planck_bc1'].values)
    bc2 = float(ds['planck_bc2'].values)
    rad = ds['Rad'].values.astype('float32')   # W m^-2 sr^-1 µm^-1

    # The GOES brightness-temperature equation, per the ABI L1b PUG (Product User Guide):
    #   BT = (fk2 / ln(fk1/Rad + 1) - bc1) / bc2
    bt = (fk2 / np.log(fk1 / rad + 1) - bc1) / bc2  # Kelvin
    bt[~np.isfinite(bt)] = np.nan
    print(f'Real scene loaded. BT range: {np.nanmin(bt):.1f} – {np.nanmax(bt):.1f} K')
    print(f'                   BT median: {np.nanmedian(bt):.1f} K')
    real_data = True
else:
    # Synthetic fallback: 500x500 brightness-temperature field
    rng = np.random.default_rng(42)
    bt = rng.normal(285, 4, size=(500, 500)).astype('float32')
    # Three injected hotspots
    for (y, x, T) in [(120, 320, 360), (200, 200, 410), (340, 110, 330)]:
        bt[y-1:y+2, x-1:x+2] = T
    print(f'Using synthetic scene. BT range: {np.nanmin(bt):.1f} – {np.nanmax(bt):.1f} K')
    print(f'                       BT median: {np.nanmedian(bt):.1f} K')
    real_data = False

# Either way the array is 2D. Most operations work uniformly from here.
print(f'\\nShape: {bt.shape}, dtype: {bt.dtype}')"""))

cells.append(md(
"""## Step 3 — Hotspot detection via local percentile threshold

The naive detector: pixels above some absolute threshold (e.g. > 320 K). Works for fires; fails for high-latitude scenes where 320 K is unreachable.

The robust detector: pixels above the **scene's 99.5th-percentile** plus a fixed offset. Adapts to the scene's overall temperature. This is the same pattern LaunchDetect uses.
"""))
cells.append(code(
"""finite = bt[np.isfinite(bt)]
p995 = np.nanpercentile(finite, 99.5)
threshold = max(p995 + 5, 310.0)  # never go below 310 K — clouds at 270-290 K, hot land at 300-310 K
print(f'99.5th percentile:   {p995:.1f} K')
print(f'Threshold (max of p995+5 or 310):   {threshold:.1f} K')

hot = bt > threshold
n_hot = int(hot.sum())
print(f'Hot pixels detected: {n_hot}  ({n_hot / bt.size * 100:.4f}% of scene)')

# Cluster contiguous hot pixels — the "detection events" upstream pipelines consume
from scipy import ndimage
labels, n_clusters = ndimage.label(hot, structure=np.ones((3,3), int))
print(f'Cluster count: {n_clusters}')

# For each cluster: centroid, peak BT, area
sizes = ndimage.sum_labels(np.ones_like(bt), labels, range(1, n_clusters+1)).astype(int)
peaks = ndimage.maximum(bt, labels, range(1, n_clusters+1))
ys, xs = ndimage.center_of_mass(np.ones_like(bt), labels, range(1, n_clusters+1)), None
ys = [c[0] for c in ndimage.center_of_mass(np.ones_like(bt), labels, range(1, n_clusters+1))]
xs = [c[1] for c in ndimage.center_of_mass(np.ones_like(bt), labels, range(1, n_clusters+1))]

# Sort by peak BT (descending)
order = np.argsort(-peaks)
print()
print(f'{\"cluster\":>7} {\"size\":>5} {\"peak BT (K)\":>12} {\"centroid (y,x)\":>20}')
for idx in order[:10]:
    i = int(idx)
    print(f'{i+1:>7} {sizes[i]:>5} {peaks[i]:>10.1f}   ({ys[i]:>6.1f}, {xs[i]:>6.1f})')

if n_clusters >= (3 if not real_data else 1):
    print('\\n[PASS] hotspot detection working — at least one cluster found.')
else:
    print('\\nNo hotspots in this scene above threshold. Try a different TARGET_UTC near a known event.')"""))

cells.append(md(
"""## Step 4 — Render the scene + detected hotspots

Two panels: full scene as brightness-temperature heat-map, then a zoom on the hottest cluster with detected pixels outlined.
"""))
cells.append(code(
"""import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(15, 6), dpi=110)

# Panel 1: full scene
im0 = axes[0].imshow(bt, cmap='inferno', vmin=np.nanpercentile(finite, 1), vmax=np.nanpercentile(finite, 99))
axes[0].set_title('GOES-18 ABI Band 7 — brightness temperature (K)')
axes[0].set_xlabel('GOES grid X'); axes[0].set_ylabel('GOES grid Y')
plt.colorbar(im0, ax=axes[0], label='K', shrink=0.8)

# Overlay hotspot centroids
if n_clusters > 0:
    axes[0].scatter(xs, ys, facecolors='none', edgecolors='#22d3ee', s=200, linewidths=2,
                    label=f'{n_clusters} hotspot cluster(s)')
    axes[0].legend(loc='upper right')

# Panel 2: zoom on hottest cluster
if n_clusters > 0:
    hot_idx = int(np.argmax(peaks))
    cy, cx = int(ys[hot_idx]), int(xs[hot_idx])
    pad = 25
    y0, y1 = max(0, cy-pad), min(bt.shape[0], cy+pad)
    x0, x1 = max(0, cx-pad), min(bt.shape[1], cx+pad)
    zoom = bt[y0:y1, x0:x1]
    im1 = axes[1].imshow(zoom, cmap='inferno', vmin=np.nanpercentile(finite, 5),
                          vmax=max(threshold + 30, peaks[hot_idx]))
    axes[1].set_title(f'Hottest cluster — peak {peaks[hot_idx]:.1f} K  (zoom @ y={cy}, x={cx})')
    # Outline hot pixels in the zoom
    zoom_hot = (zoom > threshold).astype(int)
    axes[1].contour(zoom_hot, levels=[0.5], colors='#22d3ee', linewidths=2)
    plt.colorbar(im1, ax=axes[1], label='K', shrink=0.8)
else:
    axes[1].text(0.5, 0.5, 'No hotspots to zoom into', ha='center', va='center',
                 transform=axes[1].transAxes, fontsize=14)

plt.tight_layout()
plt.show()"""))

cells.append(md(
"""## Common gotchas

- **Quality flags.** Real GOES NetCDFs have a `DQF` (data quality flag) variable. Pixels with DQF > 0 should be masked before thresholding. We skipped this for brevity; production pipelines must include it.
- **Day vs night.** Band 7 sees reflected sunlight during day (3.9 µm has solar component) — your "hotspot" at midday over a desert may be sun glint on the surface. LaunchDetect uses the day/night component split via `solar_zenith_angle`.
- **The Planck inverse vs ABI L1b CDF coefficients.** The NetCDF stores `planck_fk1, fk2, bc1, bc2`. **Use those, not a literal Planck inverse from h, c, k.** The L1b coefficients already account for the band's spectral response function — they're the calibrated answer.
- **Storage layout: `s3://noaa-goes18` (op'l), `noaa-goes17` (retired West), `noaa-goes16` (East).** Himawari-9 has a separate JAXA endpoint, not S3. Mesoscale = M1/M2 product, full-disk = F, CONUS = C, 5-min cadence for CONUS.
- **Time stamps.** `s_YYYYDDDHHMMSSF` in the filename is the start of the scan window — for a CONUS scene that's the start of the 5-min sweep, not the timestamp of a specific pixel.
"""))

cells.append(md(
"""## Self-check

- [ ] Either a real GOES-18 scene loaded from S3, OR the synthetic fallback (lab still works).
- [ ] Brightness temperature converted: minimum > 200 K, maximum < 500 K (sane range).
- [ ] Threshold computed via 99.5th-percentile + 5 K (or 310 K floor).
- [ ] At least one hot-pixel cluster detected (synthetic mode injects 3; real-data mode depends on the scene).
- [ ] Two-panel plot rendered: full scene + zoom on hottest cluster.
- [ ] Quiz on the [Week 14 page](https://launchdetect.com/academy/week/14/).

## What's next

**Week 15 — Georeferencing + parallax.** Convert the GOES grid (x, y) of your hottest cluster to (lat, lon) — and correct the parallax shift caused by the plume being at altitude (it appears displaced from its real ground position by tens of km).
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-14/lab.ipynb ({len(cells)} cells)")
