# Processing pipeline: milestones and status

Plan written in April 2026. Status updated in November 2026.
Rule kept from the original plan: no figure is called "reliable range" or "calibrated" until the matching milestone passes.

```
.bin (int16)  ──parse_bin──▶  chirp cube (chirp, sample, rx)
              ──iq_frame_tensor──▶  frames (frame, loop, tx, rx, sample)
              ──range FFT (fast time)──▶  range profiles
              ──Doppler FFT (loops of one TX)──▶  range-Doppler map per frame / TX / RX
              ──(later) angle FFT over the 12 virtual channels──▶  range-angle / point cloud
```

## Milestones

| ID | Milestone | Acceptance criterion | Status (Nov 2026) |
|---|---|---|---|
| M0 | Scope freeze and data lineage | each `.bin` has its cfg and metadata; scope is IWR6843ISK-ODS + DCA1000 only | **partly done**: cfg reconstructed for the two captures (`configs/ti/`); per-run metadata not recorded at capture time |
| M1.1–1.2 | Collect cfg and write the parsing spec | parser reads only documented parameters | **done**: `RadarConfig` fields; `ti_cfg.py` reads TI cfg |
| M1.3 | Decide real vs. IQ | decided by cfg plus data, not by "the plot looks nicer" | **done**: complex, RX-major, Q-first (`DATA_FORMAT.md`) |
| M1.4 | Length divisibility | payload = whole chirps (tail explained) | **done**: 2048 words per chirp; tails of 184 / 608 words |
| M1.5 | List unknowns | open list | **done**: frame-start offset, zero-chirp cause, Doppler sign |
| M2.1 | One formal parse path | no unresolved real/IQ branches in the formal path | **done**: layout fully set by config; debug scripts kept separate |
| M2.2 | Range FFT with documented window and length | Hann window, N = 256, first half | **done** |
| M2.3 | Reflector test at a known distance | peak within ±1–2 bins of the cfg prediction | **not done** (needs the radar) |
| M2.4 | Multi-RX consistency | same peak bins on all RX | **done** on both captures |
| M3.1 | Single-RX RD map with documented axis order | | **done**: `build_rd_map.py --framed` |
| M3.2 | Static target at zero Doppler; mover at a plausible Doppler | | **half done**: static energy at 0 m/s; no moving-target capture yet |
| M3.3 | Axis labels | m and m/s from cfg, marked unverified | **done** |
| — | Angle / virtual array / point cloud | deferred | not started |

## Bugs found and fixed during the November 2026 review

1. **I/Q word order.**
   - *Problem:* the data is Q-first. Reading it I-first mirrors every target into the negative half of the FFT, so the first-half range plots from April showed the image side (~20–40 dB lower).
   - *Fix:* `iq_order` config field.
2. **Frame tensor reshape.**
   - *Problem:* `(chirp, sample, rx)` was reshaped directly into `(…, rx, sample)`, which mixed samples across receivers. The April `--framed` RD maps were therefore not valid.
   - *Fix:* reshape to `(…, sample, rx)` and transpose. Regression test in `tests/`.
3. **Non-framed RD map.**
   - *Problem:* its Doppler FFT runs over all chirps in the file, mixing the three TDM transmitters and spanning frame gaps.
   - *Fix:* it is kept as a quick look and now prints a warning. Use `--framed`.

## Next steps (if the project continues on this hardware)

1. M2.3 reflector test (3 distances), then set `config_verified` in the JSON.
2. Moving-target capture (walk towards the radar at a known speed) to fix the Doppler sign.
3. Switch to the 64-loop profile, or longer, for finer velocity bins.
4. Record an empty-scene background per mounting.
5. Angle processing over the 12 virtual channels: needs the TX slot labelling to be confirmed first (`DATA_FORMAT.md`, open item 3).
