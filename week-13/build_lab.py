"""Build week-13/lab.ipynb — GOES-R ABI scene types: full-disk, CONUS, mesoscale."""
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
"""# Week 13: GOES-R ABI products — full-disk, CONUS, mesoscale

**Track:** Remote Sensing Specialist (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/13/](https://launchdetect.com/academy/week/13/)

---

_GOES-R's Advanced Baseline Imager runs three concurrent scan products: **Full Disk (F)** every 10 min over the whole hemisphere, **CONUS (C)** every 5 min over the contiguous US, and two **Mesoscale (M1, M2)** windows every 1 min, steerable to any 1000×1000 km area. This week you fetch one example of each from `s3://noaa-goes18` and compare resolutions + cadence — the trade-off that defines what kind of detection you can run._
"""))

cells.append(md(
"""## Why this week matters

Latency is the difference between "we detected the launch" and "we predicted it 60 seconds ago". Mesoscale's 1-minute cadence is what lets LaunchDetect chase a plume as it ascends; CONUS's 5-min is too slow for the fast phase of a launch. But Mesoscale only covers a 1000×1000 km box you have to steer in advance — so you need the CONUS scan to catch a launch you weren't expecting. Each product is the answer to a different question:

| Product       | Cadence | Coverage           | Best for                            |
|---------------|---------|--------------------|-------------------------------------|
| Full Disk (F) | 10 min  | Whole hemisphere   | global weather, wildfires           |
| CONUS (C)     | 5 min   | Lower 48 + Mexico  | regional weather, broad detection   |
| Meso 1 (M1)   | 1 min   | 1000×1000 km steerable | targeted fires, launches, eruptions |
| Meso 2 (M2)   | 1 min   | 1000×1000 km steerable | second target slot                  |
"""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q s3fs xarray h5netcdf numpy matplotlib"""))

cells.append(md(
"""## Step 1 — List files for a recent hour for each scene type

The S3 layout: `s3://noaa-goes18/ABI-L1b-Rad{F|C|M}/{yyyy}/{ddd}/{hh}/`. Same path pattern for all three; only the product code changes.
"""))
cells.append(code(
"""import s3fs, datetime, re

target = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
target = target.replace(minute=0, second=0, microsecond=0)
year=target.year; doy=target.timetuple().tm_yday; hour=target.hour

s3 = s3fs.S3FileSystem(anon=True)
BUCKET='noaa-goes18'
print(f'Target: {target.isoformat()}\\n')

for product in ('ABI-L1b-RadF','ABI-L1b-RadC','ABI-L1b-RadM'):
    prefix = f'{product}/{year}/{doy:03d}/{hour:02d}/'
    try:
        cands = s3.ls(f'{BUCKET}/{prefix}')
        band7 = [c for c in cands if re.search(r'M\\dC07_G18', c)]
        meta = product.split('-')[-1]
        print(f'{meta:>5}: {len(cands):>4} files, {len(band7)} Band-7 ({len(band7)/max(len(cands),1)*100:.0f}%)')
        if band7:
            print(f'       e.g. {band7[0].split(\"/\")[-1][:70]}…')
    except Exception as e:
        print(f'{product}: error ({e})')

# Cadence: by examining timestamps. The "_s" field is start-of-scan
# 'OR_ABI-L1b-RadC-M6C07_G18_s20251310601000_e...'  → s_YYYYDDDHHMMSS
def parse_ts(p):
    m = re.search(r'_s(\\d{14})', p)
    if not m: return None
    s = m.group(1)
    return datetime.datetime.strptime(s[:13], '%Y%j%H%M%S').replace(tzinfo=datetime.timezone.utc)

# Show cadence for the CONUS-Band-7 series
conus = sorted([c for c in s3.ls(f'{BUCKET}/ABI-L1b-RadC/{year}/{doy:03d}/{hour:02d}/') if 'C07_G18' in c])
times = [parse_ts(c) for c in conus if parse_ts(c)]
if len(times) >= 2:
    diffs = [(times[i+1]-times[i]).total_seconds() for i in range(len(times)-1)]
    print(f'\\nCONUS Band-7 scan cadence (median, across the hour): {sorted(diffs)[len(diffs)//2]:.0f} s')"""))

cells.append(md(
"""## Step 2 — Open one of each and report shape

Same opening code as Week 14, three times. The resolution-vs-coverage trade-off is in the array shape.
"""))
cells.append(code(
"""import xarray as xr
import numpy as np

products = [('ABI-L1b-RadF','full-disk'),
            ('ABI-L1b-RadC','CONUS'),
            ('ABI-L1b-RadM','meso (M1)')]
opened = {}
for path_prefix, label in products:
    try:
        prefix = f'{path_prefix}/{year}/{doy:03d}/{hour:02d}/'
        cands = s3.ls(f'{BUCKET}/{prefix}')
        band7 = [c for c in cands if re.search(r'M\\dC07_G18', c)]
        if not band7: continue
        # For meso pick M1
        if 'RadM' in path_prefix:
            band7 = [c for c in band7 if 'RadM1' in c] or band7
        key = sorted(band7)[0]
        ds = xr.open_dataset(s3.open(key), engine='h5netcdf', decode_times=False)
        opened[label] = (ds, key)
        h, w = ds['Rad'].shape
        # Spatial resolution: full-disk is 2 km at nadir, CONUS 2 km, meso 2 km (Band 7).
        # Coverage area in pixels² → physical km² (very rough — fixed grid is non-uniform).
        print(f'{label:<10s}  shape {h}×{w}  ({h*w/1e6:.2f} Mpx)  file_size ~{s3.size(key)/1024/1024:.1f} MB')
    except Exception as e:
        print(f'{label}: failed ({e})')

if not opened:
    print('No real data available; the cadence/shape numbers above still illustrate the trade-off.')"""))

cells.append(md(
"""## Step 3 — Plot brightness-temperature maps side by side

If we got real data, render the three products. Each one is the same band, same instrument, same hour — but very different coverage and grid.
"""))
cells.append(code(
"""import matplotlib.pyplot as plt

def bt_from_ds(ds):
    fk1=float(ds['planck_fk1'].values); fk2=float(ds['planck_fk2'].values)
    bc1=float(ds['planck_bc1'].values); bc2=float(ds['planck_bc2'].values)
    rad = ds['Rad'].values.astype('float32')
    bt = (fk2 / np.log(fk1/rad + 1) - bc1) / bc2
    bt[~np.isfinite(bt)] = np.nan
    return bt

if opened:
    n = len(opened)
    fig, axes = plt.subplots(1, n, figsize=(6*n, 5), dpi=110)
    if n == 1: axes = [axes]
    for ax, (label, (ds, key)) in zip(axes, opened.items()):
        bt = bt_from_ds(ds)
        h, w = bt.shape
        # Subsample full-disk for plot speed
        step = max(1, h // 1000)
        bt_plot = bt[::step, ::step]
        im = ax.imshow(bt_plot, cmap='inferno',
                       vmin=np.nanpercentile(bt_plot[np.isfinite(bt_plot)], 1),
                       vmax=np.nanpercentile(bt_plot[np.isfinite(bt_plot)], 99))
        ax.set_title(f'{label}  ({h}×{w})')
        ax.set_xticks([]); ax.set_yticks([])
        plt.colorbar(im, ax=ax, shrink=0.7, label='BT (K)')
    plt.tight_layout()
    plt.show()
else:
    print('No real-data panels — see cadence table above.')"""))

cells.append(md(
"""## Common gotchas

- **Meso scene location changes hourly.** The two meso windows are repositioned at NOAA's discretion (fires, hurricanes, eruptions). Your detector can't assume the window covers a specific spot — check `geospatial_lat_lon_extent` in the NetCDF.
- **Full-disk scans run on 10-min boundaries; CONUS on 5-min; meso on 1-min.** Cross-checking timestamps when comparing across products is required.
- **Same band number → same wavelength → different file pattern.** `_C07_` is universal across F/C/M but the prefix tells you the scan extent.
- **GOES-18 vs -19.** GOES-18 = operational West, GOES-19 = operational East as of 2025. Cape Canaveral launches are on GOES-19; Vandenberg launches are on GOES-18.
"""))

cells.append(md(
"""## Self-check

- [ ] File listing returns >0 candidates for at least one of (F, C, M).
- [ ] CONUS Band-7 cadence in seconds is close to 300 (5-min cadence).
- [ ] At least one product opened and Rad shape printed.
- [ ] If multiple products were available, side-by-side BT plots render with sane temperature ranges.
- [ ] Quiz on the [Week 13 page](https://launchdetect.com/academy/week/13/).

## What's next

**Week 14** (already shipped) — Brightness-temperature math + hotspot detection.
**Week 15** — Capstone 3: georeferencing + parallax correction.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-13/lab.ipynb ({len(cells)} cells)")
