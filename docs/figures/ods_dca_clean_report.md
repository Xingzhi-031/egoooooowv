# Capture check: `ods_dca_clean_Raw_0.bin`

- int16 words: 5955768  (min -3271, max 3205)

## Layout hypotheses (first 960 chirps)

| layout (interleave/word order) | E(+f)/E(-f) | RX profile corr | same-TX loop corr |
|---|---|---|---|
| rx_major/QI | 387 | 0.930 | 0.971 |
| rx_major/IQ | 0.00258 | 0.983 | 0.964 |
| sample_rx/QI | 5.32 | 0.994 | 0.983 |
| sample_rx/IQ | 0.188 | 0.910 | 0.975 |

A correct complex layout puts nearly all energy on one side of the spectrum (complex-1x sampling has image rejection), with the target side in the positive half under this parser's convention.

## Parsed with the configured layout

- layout: rx_major / QI; chirps: 2908 (30.29 frames of 96)
- all-zero chirps: 25; positions within frame: [4, 5]

## Frame-length evidence

- spacing between all-zero chirps (chirps): [1, 95, 96]
- least coherent same-TX transitions at loop index [288, 289, 320, 321, 416, 417, 448, 449, 450, 451, 480, 481] -> modulo 32 loops: [0, 1, 2, 3]
- (envelope autocorrelation is not used: any lag that is a multiple of num_tx chirps scores high on a static scene, so it cannot separate 48/96/192-chirp frames)
- full frames used: 30 (dropped 28 tail chirps); filled 25 zero chirps
- strongest change vs. static mean at ~0.31 m; RD figure uses frame 9

Figures: `range_profile.png`, `range_time.png`, `rd_frame9.png`.
