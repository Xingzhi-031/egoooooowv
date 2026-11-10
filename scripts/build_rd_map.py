"""
Single-RX |RD| map: range FFT on ADC, then Doppler FFT on chirps. No angle / virtual array.
TODO: Doppler axis in Hz; optional full complex chain vs |.| only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.config_loader import RadarConfig, load_radar_config_json
from scripts.iq_frame_tensor import (
    chirp_cube_to_frame_tensor_stream,
    rd_input_single_tx_rx,
    stream_tx_to_canonical,
    truncate_chirp_cube_to_full_frames,
)
from scripts.parse_bin import parse_adc_cube


def build_rd_map_single_rx(
    adc_cube: np.ndarray,
    cfg: RadarConfig,
    rx_index: int,
) -> np.ndarray:
    if adc_cube.ndim != 3:
        raise ValueError(f"Expected adc_cube ndim=3, got {adc_cube.ndim}")
    n_ch, n_adc, n_rx = adc_cube.shape
    if rx_index < 0 or rx_index >= n_rx:
        raise IndexError(f"rx_index {rx_index} out of [0, {n_rx})")
    if n_adc != cfg.num_adc_samples:
        raise ValueError(
            f"cube num_adc_samples {n_adc} != cfg.num_adc_samples {cfg.num_adc_samples}"
        )

    sig = adc_cube[:, :, rx_index].astype(np.complex128, copy=False)
    window = np.hanning(cfg.num_adc_samples).astype(np.float64)
    range_fft = np.fft.fft(sig * window[np.newaxis, :], axis=1)

    n_r = cfg.num_adc_samples // 2
    range_half = range_fft[:, :n_r]

    doppler_fft = np.fft.fftshift(np.fft.fft(range_half, axis=0), axes=0)
    return np.abs(doppler_fft)


def build_rd_map_framed_single_tx(
    adc_cube: np.ndarray,
    cfg: RadarConfig,
    frame_idx: int,
    tx_canonical: int,
    rx_index: int,
) -> np.ndarray:
    """
    Doppler only across loops for one TX (canonical 0=TX1,1=TX2,2=TX3), one frame.
    Input (loops, adc) = (32, 256) after indexing.
    """
    stream = chirp_cube_to_frame_tensor_stream(adc_cube, cfg)
    canon = stream_tx_to_canonical(stream)
    sig = rd_input_single_tx_rx(canon, frame_idx, tx_canonical, rx_index).astype(np.complex128)
    window = np.hanning(cfg.num_adc_samples).astype(np.float64)
    range_fft = np.fft.fft(sig * window[np.newaxis, :], axis=1)
    n_r = cfg.num_adc_samples // 2
    range_half = range_fft[:, :n_r]
    doppler_fft = np.fft.fftshift(np.fft.fft(range_half, axis=0), axes=0)
    return np.abs(doppler_fft)


def save_rd_heatmap(
    rd_mag: np.ndarray,
    cfg: RadarConfig,
    output_path: Path,
    subtitle: str = "",
) -> None:
    label = "VERIFIED (config flag)" if cfg.config_verified else "EXPLORATORY / UNVERIFIED"
    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    im = ax.imshow(rd_mag, aspect="auto", origin="lower", cmap="viridis")
    ax.set_title(f"Single-RX range–Doppler [{label}]{subtitle}")
    ax.set_xlabel("Range bin (first half)")
    ax.set_ylabel("Doppler bin (fftshift)")
    fig.colorbar(im, ax=ax, label="|RD|")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Single-RX range–Doppler map.")
    p.add_argument("bin_path", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--output", type=Path, default=Path("outputs/figures/rd_map_single_rx.png"))
    p.add_argument(
        "--framed",
        action="store_true",
        help="One TX per TDM group: Doppler across 32 loops only (canonical TX order TX1,TX2,TX3).",
    )
    p.add_argument("--frame", type=int, default=0, help="Frame index (with --framed).")
    p.add_argument(
        "--tx-canonical",
        type=int,
        default=0,
        metavar="N",
        help="0=TX1, 1=TX2, 2=TX3 (with --framed).",
    )
    p.add_argument(
        "--drop-partial-frames",
        action="store_true",
        help="With --framed: drop trailing chirps so count is multiple of chirps_per_frame.",
    )
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    cube, meta = parse_adc_cube(args.bin_path, cfg)
    print("Parsed meta:", meta)
    sub = ""
    if args.framed:
        if cube.shape[0] % cfg.resolved_chirps_per_frame() != 0:
            if args.drop_partial_frames:
                cube, dropped = truncate_chirp_cube_to_full_frames(cube, cfg)
                print(f"drop-partial-frames: dropped {dropped} chirps; num_chirps={cube.shape[0]}")
            else:
                raise ValueError(
                    f"num_chirps {cube.shape[0]} not divisible by {cfg.resolved_chirps_per_frame()}; "
                    "use --drop-partial-frames or fix cfg."
                )
        rd = build_rd_map_framed_single_tx(
            cube, cfg, args.frame, args.tx_canonical, args.rx
        )
        sub = f" framed f={args.frame} tx={args.tx_canonical}"
    else:
        rd = build_rd_map_single_rx(cube, cfg, args.rx)
    print("RD map shape (doppler, range):", rd.shape)
    save_rd_heatmap(rd, cfg, args.output, subtitle=sub)
    print(f"Saved figure: {args.output}")


if __name__ == "__main__":
    main()
