"""Build week-23/lab.ipynb — SAR: Sentinel-1, polarimetry, InSAR."""
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
"""# Week 23: Synthetic Aperture Radar — Sentinel-1, polarimetry, InSAR

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/23/](https://launchdetect.com/academy/week/23/)

---

_SAR is the all-weather, day-or-night sensor that optical EO can't replace. **Sentinel-1** is the public workhorse — 5 m × 20 m resolution, VV + VH polarization, 6-12 day revisit globally. This week covers the three concepts that matter: **backscatter** (what the image actually shows), **polarimetry** (why VV and VH look different), and **InSAR** (how to measure cm-scale ground deformation from two SAR passes weeks apart)._
"""))

cells.append(md("""## Why this week matters

Optical EO needs sunlight and a cloud-free sky. SAR needs neither. For:
- Detecting **ground deformation** after an earthquake or volcano (no other technique gives mm-cm accuracy globally)
- Monitoring **ship traffic** at night (active illumination, all-weather)
- Tracking **ice extent** through polar night
- Mapping **flood extent** under cloud cover

…it's the only choice. The trade-off: SAR images look weird (speckle noise, no human-intuitive colors), and InSAR processing is a steeper learning curve than NDVI."""))

cells.append(code("""!pip install -q numpy matplotlib"""))

cells.append(md("""## Step 1 — Synthetic SAR amplitude image

A real Sentinel-1 GRD scene is ~1 GB. For this lab we generate a synthetic 256×256 amplitude image with the characteristic SAR features: **speckle** (multiplicative noise) and **specular vs diffuse scatterers** (sharp bright points like ships on a dark ocean)."""))
cells.append(code(
"""import numpy as np, matplotlib.pyplot as plt

rng = np.random.default_rng(2)
H = W = 256

# Background: 'ocean' — Rayleigh-distributed speckle
sar = rng.rayleigh(scale=20, size=(H, W)).astype('f4')

# 'Land' — higher mean backscatter
sar[:H//3, :] += rng.normal(80, 20, (H//3, W))

# Ships: bright point scatterers
ship_locs = [(40, 180), (90, 140), (130, 60), (180, 200), (200, 100)]
for (y, x) in ship_locs:
    sar[y:y+2, x:x+2] = rng.uniform(300, 600, (2, 2))

# Clip negative values (amplitude is non-negative)
sar = np.clip(sar, 0, None)

print(f'SAR scene: {sar.shape}')
print(f'Mean amplitude: {sar.mean():.1f}')
print(f'Speckle stdev / mean (Rayleigh): {sar[100:, :].std()/sar[100:,:].mean():.2f}  (theory: 0.522)')

fig, ax = plt.subplots(figsize=(7,7), dpi=110)
ax.imshow(sar, cmap='gray', vmin=0, vmax=np.percentile(sar, 99))
ax.set_title('Synthetic SAR amplitude (ocean + land + 5 ships)')
ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout(); plt.show()"""))

cells.append(md(
"""## Step 2 — Despeckling: the constant fight

Speckle (Rayleigh-distributed multiplicative noise) is intrinsic to coherent imaging. Every SAR processing chain spends real CPU on despeckling. The Lee filter and Lee-Sigma filter are classical; modern pipelines use BM3D or U-Net denoisers.

Below we apply a simple 5×5 box filter and a Lee-style adaptive filter, then measure SNR improvement on a known-flat ocean region.
"""))
cells.append(code(
"""from scipy.ndimage import uniform_filter

def lee_filter(img, kernel=5, noise_var=None):
    mean = uniform_filter(img, kernel)
    sqr_mean = uniform_filter(img*img, kernel)
    var = sqr_mean - mean*mean
    if noise_var is None:
        noise_var = var.mean()
    weight = var / (var + noise_var)
    return mean + weight * (img - mean)

box = uniform_filter(sar, 5)
lee = lee_filter(sar, 5)

# Measure SNR on the ocean strip (rows 100:, all cols — known to be 'flat ocean')
def snr(arr, region=slice(120, None)):
    s = arr[region, :]
    return s.mean() / s.std()
print(f'Ocean SNR  (raw SAR):     {snr(sar):.2f}')
print(f'Ocean SNR  (5x5 box):     {snr(box):.2f}')
print(f'Ocean SNR  (Lee filter):  {snr(lee):.2f}')
# Box smears edges; Lee preserves them. Both improve SNR vs raw.
assert snr(box) > snr(sar), 'box filter should improve SNR'
assert snr(lee) > snr(sar), 'lee filter should improve SNR'"""))

cells.append(md(
"""## Step 3 — Polarimetry: VV vs VH

Sentinel-1 transmits H or V polarization and receives both. The standard 'IW' mode delivers VV (vertical xmt, vertical recv) + VH (vertical xmt, horizontal recv) co-registered.

- **VV** is strong over smooth surfaces (calm water specular-reflects, ships specular-reflect off the hull).
- **VH** is strong over rough/volume scatterers (forests, urban areas).

Cross-pol ratios `VV/VH` or `VH/VV` flag ship vs ocean (ships have high VV; ocean has low everywhere) or vegetation type (forest has high VH; bare ground has high VV).
"""))
cells.append(code(
"""# Synthesize a 'VH' channel: lower mean, less specular at ships, more 'speckle'
vh = rng.rayleigh(scale=12, size=(H, W)).astype('f4')
vh[:H//3, :] += rng.normal(50, 14, (H//3, W))
# Ships much dimmer in VH
for (y, x) in ship_locs:
    vh[y:y+2, x:x+2] = rng.uniform(70, 130, (2, 2))
vh = np.clip(vh, 0, None)

# Cross-pol ratio
ratio = sar / np.maximum(vh, 1)

# Threshold ratio > 3 to flag 'high-VV, low-VH' i.e. specular-likely ships
flagged = ratio > 3

fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=110)
axes[0].imshow(sar, cmap='gray', vmax=np.percentile(sar,99)); axes[0].set_title('VV')
axes[1].imshow(vh,  cmap='gray', vmax=np.percentile(vh,99));  axes[1].set_title('VH')
axes[2].imshow(flagged, cmap='hot'); axes[2].set_title('VV/VH > 3 (candidate ships)')
for a in axes: a.set_xticks([]); a.set_yticks([])
plt.tight_layout(); plt.show()
print(f'Flagged pixels (likely ships/specular): {flagged.sum()} of {sar.size} ({flagged.mean()*100:.2f}%)')"""))

cells.append(md(
"""## Step 4 — InSAR: the phase difference

When two SAR passes image the same scene with slightly different geometry, the **interferogram** (complex-conjugate product) encodes ground deformation between the two epochs in its phase. One full 2π fringe = one half-wavelength of line-of-sight shift (≈ 2.8 cm at C-band).

Real InSAR pipelines (SNAP, GMTSAR, ISCE2) take hours per scene pair. We just demo the math: build two synthetic complex SAR scenes, multiply, look at the phase.
"""))
cells.append(code(
"""# Two synthetic complex SAR images. The second has a small phase ramp = uniform LOS deformation
def make_complex_sar(size=128, phase_field=None, rng=None):
    rng = rng or np.random.default_rng()
    amp = rng.rayleigh(scale=30, size=(size, size))
    phase = phase_field if phase_field is not None else rng.uniform(-np.pi, np.pi, (size, size))
    return amp * np.exp(1j * phase)

rng2 = np.random.default_rng(11)
size = 128
phase1 = rng2.uniform(-np.pi, np.pi, (size, size))
# Second pass: same speckle, plus a smooth deformation gradient (5 fringes across the scene)
ys, xs = np.indices((size, size))
deformation_phase = 5 * 2 * np.pi * xs / size   # 5 fringes across X
phase2 = phase1 + deformation_phase

scene1 = make_complex_sar(size, phase1, rng2)
scene2 = make_complex_sar(size, phase2, rng2)

# Interferogram = complex-conjugate product
interf = scene1 * np.conj(scene2)
ifgram_phase = np.angle(interf)

# Coherence (correlation between the two SLCs)
def coherence(a, b, win=5):
    num = uniform_filter(np.real(a * np.conj(b)), win) + 1j * uniform_filter(np.imag(a * np.conj(b)), win)
    den = np.sqrt(uniform_filter(np.abs(a)**2, win) * uniform_filter(np.abs(b)**2, win))
    return np.abs(num) / np.maximum(den, 1e-9)

coh = coherence(scene1, scene2)
print(f'Mean coherence: {coh.mean():.3f}  (1 = perfectly correlated, 0 = noise)')

fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=110)
axes[0].imshow(np.abs(scene1), cmap='gray'); axes[0].set_title('|SLC1| (amplitude)')
axes[1].imshow(ifgram_phase, cmap='twilight', vmin=-np.pi, vmax=np.pi); axes[1].set_title('Interferogram phase (rad)')
axes[2].imshow(coh, cmap='magma', vmin=0, vmax=1); axes[2].set_title('Coherence')
for a in axes: a.set_xticks([]); a.set_yticks([])
plt.tight_layout(); plt.show()

# Count fringes in the interferogram
import math
unwrapped = np.unwrap(ifgram_phase, axis=1)
total_radians = unwrapped[:, -1].mean() - unwrapped[:, 0].mean()
n_fringes = abs(total_radians) / (2*np.pi)
print(f'Detected fringes across X: ~{n_fringes:.1f}  (expected 5)')"""))

cells.append(md(
"""## Common gotchas

- **SAR amplitude is logarithmic** in any sensible display. Use `10·log10(amp²)` to convert to **σ⁰ (dB)** — that's what real-world Sentinel-1 products look like.
- **Despeckling is loss vs preservation.** Lee preserves edges; box smears; modern ML denoisers can hallucinate. Always check on a known-clean strip.
- **InSAR pair selection matters.** Temporal baseline > 30 days → coherence drops (vegetation/soil decorrelation). Perpendicular baseline > ~250 m → coherence drops (geometric decorrelation). Pick pairs carefully or use SBAS time-series.
- **Phase unwrapping is the hard part.** Wrapped phase ∈ [-π, π] hides absolute deformation. Algorithms (Goldstein, SNAPHU) unwrap by following gradients — they fail on areas of low coherence and ramps that exceed 2π / pixel.
- **C-band vs L-band.** Sentinel-1 is C-band (5.6 GHz, λ=5.5 cm). ALOS-2 is L-band (1.27 GHz, λ=23.5 cm). L-band penetrates vegetation better; C-band is what's free.
"""))

cells.append(md(
"""## Self-check
- [ ] Speckle stdev/mean ratio is close to 0.522 (Rayleigh-distribution theoretical value).
- [ ] Lee filter improves SNR over raw without smearing the land/sea boundary.
- [ ] Cross-polarization (VV/VH > 3) flags the synthetic ship locations and few false positives.
- [ ] Interferogram phase shows ~5 fringes across X (matches the injected deformation).
- [ ] Coherence map is high (> 0.7) because the two SLCs share the same speckle realization.
- [ ] Quiz on the [Week 23 page](https://launchdetect.com/academy/week/23/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-23/lab.ipynb ({len(cells)} cells)")
