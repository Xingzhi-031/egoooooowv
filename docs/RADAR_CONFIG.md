# Radar configuration

Device: TI **IWR6843ISK-ODS** (60–64 GHz, 3 TX × 4 RX, wide-FoV antenna) with a **DCA1000EVM** streaming raw ADC data over LVDS → Ethernet.

Configuration files:
- `configs/ti/*.cfg`: TI CLI profiles
- `configs/ti/dca1000_cf.json`: DCA1000 CLI settings
- `configs/*.json`: parser sidecars

`python scripts/ti_cfg.py <file.cfg>` prints the parsed values and the derived quantities below.

## Profiles

Both profiles use `profileCfg 0 60 7 3 24 0 0 166 1 256 12500 0 0 158`:
- start frequency 60 GHz;
- idle 7 µs, ADC start 3 µs, ramp end 24 µs;
- slope 166 MHz/µs;
- 256 complex samples at 12.5 Msps.

| | Capture profile (32 loops, used for both `.bin` files) | Proposed profile (64 loops, Apr 2026, not yet used) |
|---|---|---|
| frameCfg | `0 2 32 0 100 1 0` (reconstructed) | `0 2 64 0 50 1 0` |
| Chirps / frame | 96 | 192 |
| Frame rate | 10 Hz (inferred) | 20 Hz |
| Sampled bandwidth | 3.40 GHz | 3.40 GHz |
| Range bin | 4.41 cm | 4.41 cm |
| Max range (first half of FFT) | 5.6 m | 5.6 m |
| Loop period (3 TX) | 93 µs | 93 µs |
| Velocity bin | **0.82 m/s** | **0.41 m/s** |
| Max unambiguous velocity | ±13.1 m/s | ±13.1 m/s |

## Notes for near-field, head-mounted use

- **Velocity resolution is the weak point** of the capture profile: 0.82 m/s per bin is too coarse for walking-speed motion (about 0.5–1.5 m/s).
  - It improves with more loops per frame: 64 loops → 0.41 m/s, 128 loops → 0.20 m/s.
  - It also improves by running Doppler across frames for slow motion.
  - The ±13 m/s limit is far more than needed, so loop count can grow without aliasing problems.
- **Range**: 5.6 m and 4.4 cm bins already cover the near field.
  - A shorter ramp or a lower sample rate would save power and data rate without hurting the 0.2–4 m region.
- **Near-range leakage**: TX→RX coupling dominates the first 2–4 bins (~0.1 m).
  - Keep `calibDcRangeSig` on.
  - Plan an empty-scene (no target) recording per mounting so the static leakage and the head/headset reflection can be subtracted.
- **`clutterRemoval` is off** on purpose, so static reflectors stay in the raw data.
- **TX power / saturation**: monitor `CQRxSatMonitor` when strong reflectors are within ~0.3 m.
- The DCA1000 needs a tethered PC, so it is a lab setup only.
  - Head-worn prototypes in the literature use smaller boards (e.g. Infineon BGT60 series, TI IWR6843AOP).
