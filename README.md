# IWR6843ISK-ODS + DCA1000 offline processing (skeleton)

## Current project stage

This repository is a **minimal, modular skeleton** for offline processing of **raw DCA1000-captured** binary data from **IWR6843ISK-ODS**. It is **not** a fully validated radar pipeline.

**We are in: raw binary parsing and format validation.**

Do **not** assume:

- FFT outputs are already “reliable range”
- `.bin` layout is fully verified
- real vs IQ is confirmed
- chirp / RX / TX ordering is confirmed

Anything that depends on mmWave **cfg** or **capture-side format** is either **configurable via JSON** or marked **TODO** in code.

## Intended milestone order

1. **Confirm raw format** — align JSON parameters with TI profile / capture settings; fix parsing assumptions.
2. **Reliable range FFT** — reflector test + optional range axis; set `config_verified` only after deliberate validation.
3. **Single-RX range–Doppler map** — exploratory RD heatmap; not claimed physically correct until timing/cfg checks pass.

**Deferred in this phase:** angle processing, virtual array, beamforming, point cloud.

## Layout

```
.
├── configs/
│   └── example_radar.json    # template JSON — copy per capture
├── data/
│   ├── raw/                  # place .bin captures here (not tracked by default)
│   ├── cfg/                  # optional: mirror of TI .cfg exports
│   └── metadata/             # run notes, JSON sidecars, etc.
├── outputs/
│   └── figures/              # script-generated PNGs
├── scripts/
│   ├── config_loader.py       # RadarConfig + JSON load (TODO: TI .cfg)
│   ├── parse_bin.py           # int16 → chirp cube; IQ: `sample_rx` or `rx_major`
│   ├── iq_frame_tensor.py     # chirp cube → [F,L,T,R,S], TX1/TX3/TX2 → canonical order
│   ├── debug_parse_pipeline.py # staged prints (raw → IQ → frames → FFT energy)
│   ├── validate_range_fft.py  # single-chirp RX range FFT diagnostic
│   ├── build_rd_map.py        # RD map; add `--framed` for single-TX TDM Doppler
│   └── debug_parse_compare.py # real vs IQ compare
├── requirements.txt
└── README.md
```

## Setup

- Python **3.11+**
- `pip install -r requirements.txt`

Run all CLI commands from the **repository root** so imports resolve (`scripts` package).

## How to run

Replace paths with your files. Use a **copy** of `configs/example_radar.json` with values that match your capture (when known).

### Parse `.bin` (formal path = `is_complex` in JSON)

```bash
python scripts/parse_bin.py path/to/capture.bin --config configs/my_radar.json
```

### Range FFT diagnostic (DEBUG / UNVERIFIED unless you validated)

```bash
python scripts/validate_range_fft.py path/to/capture.bin --config configs/my_radar.json --chirp 0 --rx 0 --output outputs/figures/range_fft.png
```

### Single-RX range–Doppler map (exploratory)

```bash
python scripts/build_rd_map.py path/to/capture.bin --config configs/my_radar.json --rx 0 --output outputs/figures/rd_map.png
```

### Developer: compare real vs IQ parsing (not formal pipeline)

```bash
python scripts/debug_parse_compare.py path/to/capture.bin --config configs/my_radar.json --output outputs/figures/compare.png
```

**Note:** `debug_parse_compare.py` ignores `is_complex` and runs **both** parsers for comparison.

### IQ + frame / TX order (`configs/ods_iq_frames.json`)

- Set `is_complex: true` and `chirps_per_frame: 96` (3×32).
- `iq_interleave`: `"rx_major"` (per-RX I,Q blocks) or `"sample_rx"` (global I,Q then reshape S×R). If RD is flat or near-zero, run  
  `python scripts/debug_parse_pipeline.py your.bin --config configs/ods_iq_frames.json --try-layouts`  
  and pick the layout with sane `max|cube|` / energy.  
  If `num_chirps % 96 != 0`, add **`--drop-partial-frames`** to drop the incomplete tail and run frame stages (e.g. your file: 2908 chirps → 30×96, drop 28).
- Stream TX order per loop is **TX1 → TX3 → TX2**; code maps to canonical **TX1, TX2, TX3** for `--framed` RD.
- **Framed RD** (Doppler only across 32 loops for one TX):  
  `py -3 scripts/build_rd_map.py your.bin --config configs/ods_iq_frames.json --framed --drop-partial-frames --tx-canonical 0 --rx 0 --output outputs/figures/rd_framed.png`

## JSON fields (`RadarConfig`)

| Field | Meaning |
|--------|--------|
| `num_adc_samples` | ADC samples per chirp |
| `num_rx` | RX channels |
| `num_tx`, `num_loops` | Used to reason about chirps; `chirps_per_frame` defaults to `num_tx * num_loops` if omitted |
| `is_complex` | If `true`, I/Q int16 interleaving |
| `iq_interleave` | `"sample_rx"` or `"rx_major"` (TI LVDS often `rx_major`) |
| `chirps_per_frame` | e.g. `96` for 3×32; required for frame tensor / `--framed` |
| `sample_rate_hz`, `freq_slope_hz_per_s` | Optional range-in-meters in diagnostics |
| `config_verified` | Manual flag only — set after **your** validation process |

## Exploratory script

If present, `test_trim_and_plot.py` is **legacy / exploratory** and not the formal pipeline.

## Safety wording

Comments and figures use **DEBUG / UNVERIFIED** or **EXPLORATORY** unless `config_verified` is true — this does **not** replace physical validation; it only changes labels.
