# Capture check: `egowave_trial_01_Raw_0.bin`

- int16 words: 9996896  (min -2763, max 2937)

## Layout hypotheses (first 960 chirps)

| layout (interleave/word order) | E(+f)/E(-f) | RX profile corr | same-TX loop corr |
|---|---|---|---|
| rx_major/QI | 431 | 0.924 | 0.979 |
| rx_major/IQ | 0.00232 | 0.983 | 0.970 |
| sample_rx/QI | 5.23 | 0.992 | 0.986 |
| sample_rx/IQ | 0.191 | 0.957 | 0.980 |

A correct complex layout puts nearly all energy on one side of the spectrum (complex-1x sampling has image rejection), with the target side in the positive half under this parser's convention.

## Parsed with the configured layout

- layout: rx_major / QI; chirps: 4881 (50.84 frames of 96)
- all-zero chirps: 11; positions within frame: [4, 5]

## Frame-length evidence

- spacing between all-zero chirps (chirps): [1, 95, 96]
- least coherent same-TX transitions at loop index [0, 1, 128, 129, 160, 161, 192, 193, 224, 225, 256, 257] -> modulo 32 loops: [0, 1]
- (envelope autocorrelation is not used: any lag that is a multiple of num_tx chirps scores high on a static scene, so it cannot separate 48/96/192-chirp frames)
- full frames used: 50 (dropped 81 tail chirps); filled 11 zero chirps
- strongest change vs. static mean at ~0.66 m; RD figure uses frame 4

Figures: `range_profile.png`, `range_time.png`, `rd_frame4.png`.
