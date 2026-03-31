"""
Single chirp / single RX range FFT diagnostic. Not validated unless cfg + reflector check done.
TODO: confirm FMCW range formula vs TI chirp model.
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


def range_axis_meters(cfg: RadarConfig, num_bins: int) -> np.ndarray | None:
    # R = c * f_b / (2*S), f_b = k*fs/N; TODO: validate against your waveform
    fs = cfg.sample_rate_hz
    s = cfg.freq_slope_hz_per_s
    if fs is None or s is None or s == 0:
        return None
    c = 299792458.0
    n = cfg.num_adc_samples
    k = np.arange(num_bins, dtype=np.float64)
    f_b = k * float(fs) / float(n)
    return (c * f_b) / (2.0 * float(s))


def range_fft_single_chirp_rx(
    adc_cube: np.ndarray,
    cfg: RadarConfig,
    chirp_index: int,
    rx_index: int,
) -> tuple[np.ndarray, np.ndarray]:
    if adc_cube.ndim != 3:
        raise ValueError(f"Expected adc_cube ndim=3, got {adc_cube.ndim}")
    n_ch, n_adc, n_rx = adc_cube.shape
    if chirp_index < 0 or chirp_index >= n_ch:
        raise IndexError(f"chirp_index {chirp_index} out of [0, {n_ch})")
    if rx_index < 0 or rx_index >= n_rx:
        raise IndexError(f"rx_index {rx_index} out of [0, {n_rx})")
    if n_adc != cfg.num_adc_samples:
        raise ValueError(
            f"cube num_adc_samples {n_adc} != cfg.num_adc_samples {cfg.num_adc_samples}"
        )

    sig = adc_cube[chirp_index, :, rx_index].astype(np.complex128, copy=False)
    window = np.hanning(cfg.num_adc_samples).astype(np.float64)
    fft_c = np.fft.fft(sig.astype(np.complex128) * window)
    half = cfg.num_adc_samples // 2
    fft_mag_half = np.abs(fft_c[:half])
    return fft_c, fft_mag_half


def save_diagnostic_figure(
    adc_cube: np.ndarray,
    cfg: RadarConfig,
    chirp_index: int,
    rx_index: int,
    output_path: Path,
) -> None:
    _, mag_half = range_fft_single_chirp_rx(adc_cube, cfg, chirp_index, rx_index)

    label = "VERIFIED (config flag)" if cfg.config_verified else "DEBUG / UNVERIFIED"
    n_bins = mag_half.size
    x_axis = np.arange(n_bins)
    xlabel = "Range bin index"
    rng_m = range_axis_meters(cfg, n_bins)
    if rng_m is not None:
        x_axis = rng_m
        xlabel = "Range (m, approx — TODO validate cfg)"

    fig, axes = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True)
    fig.suptitle(f"Range FFT diagnostic [{label}]")

    t_sig = adc_cube[chirp_index, :, rx_index]
    axes[0].plot(np.real(t_sig), label="real")
    if np.iscomplexobj(t_sig):
        axes[0].plot(np.imag(t_sig), label="imag")
    axes[0].set_title(f"Time — chirp {chirp_index}, RX {rx_index}")
    axes[0].set_xlabel("ADC sample")
    axes[0].set_ylabel("Amplitude")
    axes[0].legend()

    axes[1].plot(x_axis, mag_half)
    axes[1].set_title("Range FFT magnitude (first half)")
    axes[1].set_xlabel(xlabel)
    axes[1].set_ylabel("Magnitude")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Single-chirp RX range FFT diagnostic.")
    p.add_argument("bin_path", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--chirp", type=int, default=0)
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--output", type=Path, default=Path("outputs/figures/range_fft_diagnostic.png"))
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    cube, meta = parse_adc_cube(args.bin_path, cfg)
    print("Parsed meta:", meta)
    save_diagnostic_figure(cube, cfg, args.chirp, args.rx, args.output)
    print(f"Saved figure: {args.output}")


if __name__ == "__main__":
    main()
