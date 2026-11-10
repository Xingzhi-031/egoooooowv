"""
Step-by-step ADC parse debugger: raw -> IQ -> chirp cube -> frame tensor -> TX order.

Run from repo root. Does not assume physical correctness; finds where signal goes to ~0.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.config_loader import RadarConfig, load_radar_config_json
from scripts.iq_frame_tensor import (
    chirp_cube_to_frame_tensor_stream,
    rd_input_single_tx_rx,
    stream_tx_to_canonical,
    truncate_chirp_cube_to_full_frames,
)
from scripts.parse_bin import (
    int16_per_chirp_complex,
    load_raw_int16,
    parse_complex_iq_adc,
    parse_real_adc,
    _trim_to_multiple,
)


def stage_raw(raw: np.ndarray) -> None:
    print("\n=== 1) Raw buffer ===")
    print("total int16:", raw.size)
    print("first 20 int16:", raw[:20].tolist())
    zc = int(np.sum(raw == 0))
    print("zero int16 count:", zc, "/", raw.size)
    if zc == raw.size:
        print("BUG: raw buffer is all zeros (file empty/wrong path/wrong dtype).")
    print("min/max int16:", int(raw.min()), int(raw.max()))


def stage_iq(raw: np.ndarray, cfg: RadarConfig) -> np.ndarray:
    print("\n=== 2) IQ reconstruction ===")
    if not cfg.is_complex:
        print("cfg.is_complex is False — real path (skip IQ stats).")
        cube = parse_real_adc(raw, cfg)
        print("real cube |max|:", float(np.max(np.abs(cube))))
        return cube.astype(np.complex64)

    block = int16_per_chirp_complex(cfg)
    trimmed, trim_n = _trim_to_multiple(raw, block)
    print(f"trim_int16: {trim_n}, iq_interleave: {cfg.iq_interleave!r}")
    cube = parse_complex_iq_adc(raw, cfg)
    mag = np.abs(cube)
    print(
        "complex |z| mean/std/max:",
        float(np.mean(mag)),
        float(np.std(mag)),
        float(np.max(mag)),
    )
    if float(np.max(mag)) < 1e-6:
        print("BUG: complex magnitude ~0 after IQ parse — wrong layout or wrong is_complex.")
    return cube


def stage_reshape_chirp(cube: np.ndarray, cfg: RadarConfig) -> None:
    print("\n=== 3) Chirp cube reshape ===")
    print("cube shape (chirps, adc, rx):", cube.shape, cube.dtype)
    cpf = cfg.resolved_chirps_per_frame()
    n_ch = cube.shape[0]
    expected_int16 = n_ch * int16_per_chirp_complex(cfg) if cfg.is_complex else n_ch * cfg.num_adc_samples * cfg.num_rx
    print("chirps_per_frame (cfg):", cpf, "num_chirps:", n_ch)
    if n_ch % cpf != 0:
        rem = n_ch % cpf
        n_full = (n_ch // cpf) * cpf
        print(
            f"WARN: num_chirps {n_ch} % chirps_per_frame {cpf} = {rem} "
            f"(incomplete tail). Full frames only: {n_full // cpf} frames × {cpf} = {n_full} chirps."
        )
        print("Re-run with --drop-partial-frames to continue frame/FFT stages.")
    if cfg.is_complex:
        ne = n_ch * cfg.num_adc_samples * cfg.num_rx * 2
        print("expected int16 if no trim (approx):", ne)


def stage_frame_tensor(cube: np.ndarray, cfg: RadarConfig) -> tuple[np.ndarray, np.ndarray]:
    print("\n=== 4) Frame tensor [F,L,stream_tx,R,S] ===")
    cpf = cfg.resolved_chirps_per_frame()
    n_ch = cube.shape[0]
    if n_ch % cpf != 0:
        raise ValueError(f"Cannot form frames: {n_ch} % {cpf} != 0")
    n_f = n_ch // cpf
    total_c = n_f * cpf * cfg.num_rx * cfg.num_adc_samples * (2 if cfg.is_complex else 1)
    print("frames:", n_f, "elements (complex):", cube.size, "expected frames*96*4*256:", n_f * 96 * 4 * 256)
    stream = chirp_cube_to_frame_tensor_stream(cube, cfg)
    print("stream tensor shape:", stream.shape, "= (F, L, stream[TX1,TX3,TX2], R, S)")
    canon = stream_tx_to_canonical(stream)
    print("canonical tensor shape:", canon.shape, "= (F, L, [TX1,TX2,TX3], R, S)")
    print("per-TX chirps per frame (canonical): each TX has", cfg.num_loops, "chirps")
    return stream, canon


def stage_per_rx_chirp(canon: np.ndarray, cfg: RadarConfig) -> None:
    print("\n=== 5) Spot check rx=0, first chirp in frame (TX1 @ loop0) ===")
    z = canon[0, 0, 0, 0, :10]
    print("samples 0..9 (TX1, loop0, rx0):", z)
    if cfg.is_complex:
        print("real:", np.real(z))
        print("imag:", np.imag(z))


def stage_fft_energy(canon: np.ndarray, cfg: RadarConfig) -> None:
    print("\n=== 6) Range FFT input energy (TX1, rx0, frame0, all loops) ===")
    x = rd_input_single_tx_rx(canon, 0, 0, 0)
    print("RD slice shape (loops, adc):", x.shape)
    e = float(np.sum(np.abs(x)))
    print("sum(abs(x)) over slice:", e)
    if e < 1e-6:
        print("BUG: energy ~0 before FFT — upstream parse/index wrong.")
    window = np.hanning(cfg.num_adc_samples).astype(np.float64)
    spec = np.fft.fft(x * window[np.newaxis, :], axis=1)
    em = float(np.max(np.abs(spec)))
    print("max |range FFT| (any loop):", em)
    if em < 1e-6:
        print("BUG: range FFT flat — input time domain likely wrong.")


def try_layouts(raw: np.ndarray, cfg: RadarConfig) -> None:
    print("\n=== Compare IQ layouts (is_complex only) ===")
    if not cfg.is_complex:
        return
    for name in ("sample_rx", "rx_major"):
        c = replace(cfg, iq_interleave=name)
        try:
            cube = parse_complex_iq_adc(raw, c)
            m = float(np.max(np.abs(cube)))
            e0 = float(np.sum(np.abs(cube[0])))
            print(f"  {name:12s} max|cube|={m:.4g}  sum|chirp0|={e0:.4g}")
        except Exception as ex:
            print(f"  {name:12s} FAILED: {ex}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Debug mmWave raw parse pipeline.")
    p.add_argument("bin_path", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--try-layouts", action="store_true", help="Compare sample_rx vs rx_major energy")
    p.add_argument(
        "--drop-partial-frames",
        action="store_true",
        help="Drop trailing chirps so num_chirps is a multiple of chirps_per_frame.",
    )
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    raw = load_raw_int16(args.bin_path)

    stage_raw(raw)
    if args.try_layouts and cfg.is_complex:
        try_layouts(raw, cfg)

    cube = stage_iq(raw, cfg)
    stage_reshape_chirp(cube, cfg)

    cpf = cfg.resolved_chirps_per_frame()
    if cube.shape[0] % cpf != 0:
        if args.drop_partial_frames:
            cube, dropped = truncate_chirp_cube_to_full_frames(cube, cfg)
            print(f"\n--drop-partial-frames: dropped {dropped} trailing chirps; cube now {cube.shape[0]} chirps.")
        else:
            print("\nAbort frame stages: chirp count mismatch (use --drop-partial-frames).")
            return

    stream, canon = stage_frame_tensor(cube, cfg)
    stage_per_rx_chirp(canon, cfg)
    stage_fft_energy(canon, cfg)
    print("\nDone.")


if __name__ == "__main__":
    main()
