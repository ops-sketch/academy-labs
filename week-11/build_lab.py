"""Build week-11/lab.ipynb — EM spectrum, sensors, and radiometry.

Upgrade implements the old TODO: overlay Planck blackbody emission curves
for 290 K (Earth) and 1500 K (rocket plume) — and prove WHY GOES ABI
Band 7 (3.9 µm) is the canonical band for plume detection.
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
"""# Week 11: EM spectrum, sensor types, and radiometry — why Band 7 detects plumes

**Track:** Remote Sensing Specialist (Intermediate)
**Full primer + quiz:** [https://launchdetect.com/academy/week/11/](https://launchdetect.com/academy/week/11/)

---

_Every remote-sensing decision starts from one equation: the **Planck function**, which gives the spectral radiance of a blackbody at temperature T. This week you'll plot Earth's emission (290 K) and a rocket plume's emission (~1500 K) on the same graph, integrate over GOES ABI Band 7's bandpass (3.7-4.1 µm), and prove the plume is **two orders of magnitude brighter** than the background. That ratio is what every thermal launch detector exploits._
"""))

cells.append(md(
"""## Why this week matters

GOES-18, GOES-19, Himawari-9 — every operational geostationary weather satellite has a 3.9 µm "mid-wave IR" band. They put it there specifically because the Planck curve for hot objects (~1500 K plumes, ~2000 K fires) peaks near 3 µm, while Earth's surface peaks near 10 µm. At 3.9 µm a hot source can sit on a single pixel and lift its brightness temperature by 30-50 K — visible against the cold background.

This is **why thermal launch detection works**. The physics today; the pipeline that uses it through Week 15.
"""))

cells.append(md(
"""## Learning objectives

- Read and use the Planck function `B_λ(T)` for spectral radiance
- Identify Wien's displacement law: λ_peak = 2898 / T (µm·K)
- Plot blackbody curves for Earth, plume, and Sun on one graph
- Integrate spectral radiance over a sensor's bandpass to get in-band radiance
- Compute brightness temperature ratios between plume and background
- Map ABI band centers to physical reasons (cloud, sfc, plume, ozone, …)
"""))

cells.append(code(
"""!pip install -q numpy matplotlib scipy"""))

cells.append(md(
"""## Step 1 — The Planck function

For a blackbody at temperature T, the spectral radiance at wavelength λ is:

$$B_λ(T) = \\frac{2 h c^2}{λ^5} \\cdot \\frac{1}{e^{hc/(λkT)} - 1}$$

where `h=6.626×10⁻³⁴ J·s`, `c=3×10⁸ m/s`, `k=1.381×10⁻²³ J/K`. We code it once and use it everywhere.
"""))
cells.append(code(
"""import numpy as np
import matplotlib.pyplot as plt

H = 6.62607015e-34   # Planck constant, J·s
C = 2.99792458e8     # speed of light, m/s
K = 1.380649e-23     # Boltzmann, J/K

def planck_lambda(wavelength_m, T):
    \"\"\"Spectral radiance B_lambda in W·m^-2·sr^-1·m^-1.\"\"\"
    a = 2 * H * C**2 / wavelength_m**5
    x = H * C / (wavelength_m * K * T)
    # Stable form for large x (long wavelength, cold)
    return a / (np.exp(x) - 1)

# Quick sanity check at 10 µm for 290 K (Earth surface)
B = planck_lambda(10e-6, 290)
print(f'B_lambda(10 µm, 290 K) = {B:.3e} W m^-2 sr^-1 m^-1')
# Convert to the more common units W m^-2 sr^-1 µm^-1 (multiply by 1e-6)
print(f'                       = {B * 1e-6:.3e} W m^-2 sr^-1 µm^-1')

# Wien's displacement: peak wavelength = 2898 / T µm·K
for T in (290, 1500, 5778):
    lam_peak_um = 2898 / T
    print(f'T = {T:5} K  →  peak wavelength {lam_peak_um:6.3f} µm')"""))

cells.append(md(
"""## Step 2 — Plot Earth, plume, and Sun on one graph

This is the picture every remote-sensing textbook starts with. Three blackbodies, three orders of magnitude apart in temperature, peaking in three completely different parts of the spectrum.
"""))
cells.append(code(
"""wavelengths_um = np.logspace(np.log10(0.2), np.log10(50), 600)
wavelengths_m  = wavelengths_um * 1e-6

scenes = [
    ('Sun (5778 K)',  5778, '#fde047'),
    ('Plume (1500 K)',1500, '#dc2626'),
    ('Plume (1000 K)',1000, '#ea580c'),
    ('Earth (290 K)',  290, '#0891b2'),
    ('Antarctic (250 K)', 250, '#1e40af'),
]

fig, ax = plt.subplots(figsize=(11, 5.5), dpi=110)
for label, T, color in scenes:
    B = planck_lambda(wavelengths_m, T) * 1e-6  # → per µm
    ax.plot(wavelengths_um, B, label=label, color=color, linewidth=2)

# GOES ABI band centers
ABI_BANDS = {
    1:0.47, 2:0.64, 3:0.86, 4:1.378, 5:1.61, 6:2.25,
    7:3.9, 8:6.19, 9:6.95, 10:7.34,
    11:8.5, 12:9.61, 13:10.35, 14:11.2, 15:12.3, 16:13.3,
}
ax.axvspan(3.7, 4.1, color='#dc2626', alpha=0.15, label='ABI Band 7 (3.7–4.1 µm)')

ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlim(0.2, 50); ax.set_ylim(1e-3, 1e10)
ax.set_xlabel('Wavelength (µm)')
ax.set_ylabel('Spectral radiance  (W m$^{-2}$ sr$^{-1}$ µm$^{-1}$)')
ax.set_title('Planck blackbody curves — why Band 7 detects rocket plumes')
ax.legend(loc='upper right', fontsize=9)
ax.grid(True, which='both', alpha=0.3)

# Annotate the peaks
for label, T, color in scenes:
    lam_peak = 2898 / T
    if 0.3 <= lam_peak <= 30:
        B_peak = planck_lambda(lam_peak * 1e-6, T) * 1e-6
        ax.scatter([lam_peak], [B_peak], color=color, s=40, zorder=5, edgecolor='white', linewidth=1.5)

plt.tight_layout()
plt.show()"""))

cells.append(md(
"""## Step 3 — Integrate radiance over GOES ABI Band 7 (3.7-4.1 µm)

GOES sees in-band radiance, not spectral radiance at a single wavelength. So what matters is the integral `∫ B_λ(T) dλ` over the band's wavelength range. Below we compute this for each scene and report the ratio plume/background — the contrast a thermal detector needs.
"""))
cells.append(code(
"""from scipy.integrate import quad

BAND7_LOW_UM, BAND7_HIGH_UM = 3.7, 4.1
BAND7_LOW_M, BAND7_HIGH_M = BAND7_LOW_UM*1e-6, BAND7_HIGH_UM*1e-6

def in_band_radiance(T, low_m=BAND7_LOW_M, high_m=BAND7_HIGH_M):
    \"\"\"Integrate planck_lambda over a sensor band. Returns W m^-2 sr^-1.\"\"\"
    val, _ = quad(planck_lambda, low_m, high_m, args=(T,), limit=200)
    return val

print(f'In-band radiance integrated over ABI Band 7 ({BAND7_LOW_UM}-{BAND7_HIGH_UM} µm)')
print('-'*60)
results = {}
for label, T, _ in scenes:
    L = in_band_radiance(T)
    results[T] = L
    print(f'  {label:<20s}  {L:.4e} W m^-2 sr^-1')

print()
plume_1500 = results[1500]
earth      = results[290]
ratio_15   = plume_1500 / earth
print(f'Plume (1500 K) / Earth (290 K) = {ratio_15:>10,.0f}× brighter in Band 7')

plume_1000 = results[1000]
ratio_10   = plume_1000 / earth
print(f'Plume (1000 K) / Earth (290 K) = {ratio_10:>10,.0f}× brighter in Band 7')

# Sanity: ratios should be order-of-magnitude or larger.
assert ratio_15 > 1000, f'plume should be >1000x brighter, got {ratio_15:.1f}'
assert ratio_10 > 50,   f'1000-K plume should be >50x brighter, got {ratio_10:.1f}'
print()
print('That ratio — 4-5 orders of magnitude — is why a sub-pixel plume')
print('still moves a 2-km GOES pixel\\'s brightness temperature by tens of K.')"""))

cells.append(md(
"""## Step 4 — From in-band radiance to brightness temperature

GOES doesn't actually report W m⁻² sr⁻¹. It reports **brightness temperature** — the temperature a perfect blackbody would need to emit the observed in-band radiance. The inverse mapping is a lookup table, but for a single wavelength approximation we can invert Planck analytically using the band's center wavelength.

This is the same conversion GOES Ground System does for every pixel, every minute, of every CONUS scan.
"""))
cells.append(code(
"""def brightness_temperature(radiance_W_m2_sr, wavelength_m):
    \"\"\"Inverse Planck — convert spectral radiance back to a temperature.

    Uses the single-wavelength approximation (assumes band is narrow).
    The exact GOES brightness-temperature LUT is a per-band 3rd-order polynomial,
    documented in the GOES ABI Algorithm Theoretical Basis Document.
    \"\"\"
    return (H * C / (wavelength_m * K)) / np.log(
        1 + (2 * H * C**2) / (radiance_W_m2_sr * wavelength_m**5)
    )

# Sanity check the round-trip: plug in radiance from Step 3 → recover T
band_center_um = (BAND7_LOW_UM + BAND7_HIGH_UM) / 2
band_center_m  = band_center_um * 1e-6
for T_true in (290, 1000, 1500):
    spectral_at_center = planck_lambda(band_center_m, T_true)
    T_recovered = brightness_temperature(spectral_at_center, band_center_m)
    print(f'T_true = {T_true} K   T_recovered (Band 7 center {band_center_um:.2f} µm) = {T_recovered:.1f} K   '
          f'err = {abs(T_recovered - T_true):.2f} K')

# A more realistic case: cold background pixel + tiny plume contribution.
# Suppose 1% of a 2km GOES pixel is at 1500 K and 99% is at 290 K.
plume_fraction = 0.01
L_mixed = plume_fraction * planck_lambda(band_center_m, 1500) + (1 - plume_fraction) * planck_lambda(band_center_m, 290)
T_mixed = brightness_temperature(L_mixed, band_center_m)
T_baseline = brightness_temperature(planck_lambda(band_center_m, 290), band_center_m)
print()
print(f'Background pixel (100% at 290 K):                 T_B = {T_baseline:6.2f} K')
print(f'Mixed pixel (1% at 1500 K, 99% at 290 K):         T_B = {T_mixed:6.2f} K')
print(f'Δ brightness temperature (idealized):              {T_mixed - T_baseline:+6.2f} K')
print()
print('That upper-bound is striking — assuming a 1500-K BLACKBODY plume')
print('uniformly filling 1% of the pixel. In practice three things bring')
print('the observed ΔT down to a more typical 10-50 K:')
print()
print('  · emissivity. A rocket exhaust plume is not a blackbody (ε < 1).')
print('  · non-uniform plume temperature. The flame core may hit 1500-2000 K')
print('    but the 2-km GOES pixel averages over the cooler outer plume.')
print('  · atmospheric attenuation, instrument SRF, GOES quantization.')
print()
print('Even after all that — a 10-50 K lift on a single pixel is what')
print('LaunchDetect (and every thermal detector) hunts.')"""))

cells.append(md(
"""## Step 5 — Which GOES ABI band for which job?

The 16 ABI bands aren't arbitrary — each one targets a specific physical phenomenon. The full table:
"""))
cells.append(code(
"""ABI_PURPOSE = [
    ( 1, 0.47,  'Blue', 'aerosols, ocean color'),
    ( 2, 0.64,  'Red', 'land surface, daytime imagery (highest res, 0.5 km)'),
    ( 3, 0.86,  'Veggie', 'vegetation health'),
    ( 4, 1.378, 'Cirrus', 'thin cloud detection (water-vapor absorption)'),
    ( 5, 1.61,  'Snow/Ice', 'distinguishes ice from water clouds'),
    ( 6, 2.25,  'Cloud Particle Size', 'precipitation forecasting'),
    ( 7, 3.9,   'Shortwave IR', '*** rocket plumes, wildfires, hot-spot detection ***'),
    ( 8, 6.19,  'Upper-Level Water Vapor', 'jet streams'),
    ( 9, 6.95,  'Mid-Level Water Vapor', 'moisture transport'),
    (10, 7.34,  'Low-Level Water Vapor', 'low-troposphere moisture'),
    (11, 8.5,   'Cloud-top Phase', 'ice/water cloud differentiation'),
    (12, 9.61,  'Ozone', 'atmospheric ozone'),
    (13, 10.35, 'Clean IR Longwave', 'cloud-top temperature (least atmospheric correction)'),
    (14, 11.2,  'IR Longwave (Dirty)', 'classical IR weather imagery'),
    (15, 12.3,  'Dirty Longwave IR', 'low-cloud detection'),
    (16, 13.3,  'CO2', 'air-temperature profile, cloud heights'),
]
for band, wl, name, purpose in ABI_PURPOSE:
    marker = '👁' if band == 7 else '  '
    print(f'{marker} Band {band:>2}  {wl:>5.2f} µm  {name:<24s} — {purpose}')

print()
print('Band 7 is the canonical "hot stuff" channel. Weeks 14-15 build')
print('the detector around it.')"""))

cells.append(md(
"""## Common gotchas

- **Spectral vs band-integrated radiance.** A sensor reports the integral, not a single-wavelength value. Confusing these by a factor of ~Δλ is the most common Planck mistake.
- **Wien peak is in *wavelength* space.** In frequency space the peak is at a different value (5.879×10¹⁰ Hz/K). Both are correct; they're answers to different questions.
- **Brightness temperature is a fiction.** Real surfaces aren't blackbodies — they have emissivity ε < 1. Concrete is ε≈0.93, vegetation ε≈0.97, polished metal ε≈0.05. Brightness T ≠ kinetic T unless you know ε.
- **Atmospheric absorption.** Earth's atmosphere has CO₂, H₂O, O₃ absorption bands that eat into the bands you'd otherwise want. GOES Band 7 sits in a window that's mostly transparent — that's why 3.9 µm and not 4.3 µm (CO₂ absorption).
- **Bandpass isn't a box.** Real sensors have spectral response functions. GOES ABI Band 7 has a defined SRF (look up the L1b ATBD); the 3.7-4.1 µm box is a useful approximation.
"""))

cells.append(md(
"""## Self-check

- [ ] Planck curves plotted for Sun, plume (1000 K and 1500 K), Earth, Antarctic.
- [ ] Wien peak for Sun ≈ 0.5 µm, for plume ≈ 2 µm, for Earth ≈ 10 µm — visible on the graph.
- [ ] In-band integration shows plume (1500 K) is ≥ 1000× brighter than Earth (290 K) in Band 7.
- [ ] Round-trip planck → brightness_temperature recovers within <1 K.
- [ ] A 1% plume fill at 1500 K (blackbody-idealized) raises brightness T by 100+ K — and the lab text explains why real-world ΔT is 10-50 K.
- [ ] Quiz on the [Week 11 page](https://launchdetect.com/academy/week/11/).

## What's next

**Week 12 — Landsat / Sentinel-2.** Same physics, different bands, optical instead of thermal. Where vegetation indices and band-math operations come from.
"""))

nb = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-11/lab.ipynb ({len(cells)} cells)")
