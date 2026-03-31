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


def save_rd_heatmap(
    rd_mag: np.ndarray,
    cfg: RadarConfig,
    output_path: Path,
) -> None:
    label = "VERIFIED (config flag)" if cfg.config_verified else "EXPLORATORY / UNVERIFIED"
    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    im = ax.imshow(rd_mag, aspect="auto", origin="lower", cmap="viridis")
    ax.set_title(f"Single-RX range–Doppler [{label}]")
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
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    cube, meta = parse_adc_cube(args.bin_path, cfg)
    print("Parsed meta:", meta)
    rd = build_rd_map_single_rx(cube, cfg, args.rx)
    print("RD map shape (doppler, range):", rd.shape)
    save_rd_heatmap(rd, cfg, args.output)
    print(f"Saved figure: {args.output}")


if __name__ == "__main__":
    main()
