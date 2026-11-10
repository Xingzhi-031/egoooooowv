# Changelog

## 2026-11: hand-over review

- **Data format settled from the data.**
  - Complex, RX-major, Q-first, 96-chirp frames; TX slot order 0-2-1.
  - All-zero chirps found at chirps 4–5 of each frame.
  - Details and evidence: `docs/DATA_FORMAT.md`.
- **Fixed:**
  - I/Q word order: the April plots showed the mirrored image half.
  - Frame-tensor reshape: it mixed RX and samples, so the April `--framed` RD maps are invalid.
- **Added:**
  - `ti_cfg.py` (TI cfg reader) and `analyze_capture.py` (capture checks + figures).
  - Physical axes on RD maps, zero-chirp handling, and synthetic tests.
  - Clean TI profiles in `configs/ti/` and docs in `docs/`.
- Two captures re-analysed (`docs/figures/`).

## 2026-04-01 – 2026-04-29: frame / TX handling (pushed in Nov 2026)

- `iq_frame_tensor.py`: chirp cube → (frame, loop, TX, RX, sample), with TDM TX reorder.
- `build_rd_map.py --framed`: single-TX Doppler over loops.
- `debug_parse_pipeline.py`: staged diagnostics and `--try-layouts`.
- IQ layout option `rx_major` / `sample_rx`.
- Proposed 64-loop / 20 Hz profile for finer velocity bins.
- Second capture `egowave_trial_01` (2026-04-01).

## 2026-04-01: initial skeleton (first push)

- `config_loader.py`, `parse_bin.py`, `validate_range_fft.py`, `build_rd_map.py`, `debug_parse_compare.py`.
- Milestone plan M0–M3: parse and validate the format first, then range FFT, then RD map.

## 2026-02 – 2026-03

- TI toolchain set up: mmWave SDK 3.6, mmWave Studio 2.1, DCA1000 CLI.
- First DCA1000 raw capture `ods_dca_clean` (2026-03-28).
- First exploratory script, `test_trim_and_plot.py`: real vs. IQ guesses.
