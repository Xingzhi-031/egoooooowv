"""
Dev only: same .bin with real vs IQ parse side-by-side. Not the formal pipeline.
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
from scripts.parse_bin import load_raw_int16, parse_complex_iq_adc, parse_real_adc


def compare_and_plot(
    bin_path: Path,
    cfg: RadarConfig,
    chirp_index: int,
    rx_index: int,
    output_path: Path,
) -> None:
    raw = load_raw_int16(bin_path)
    real_cube = parse_real_adc(raw, cfg)
    iq_cube = parse_complex_iq_adc(raw, cfg)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    fig.suptitle("DEBUG: real vs IQ parse")

    r0 = real_cube[chirp_index, :, rx_index].astype(np.float32)
    axes[0, 0].plot(r0)
    axes[0, 0].set_title(f"Real — time, chirp {chirp_index}, RX {rx_index}")

    iq0 = iq_cube[chirp_index, :, rx_index]
    axes[0, 1].plot(np.real(iq0), label="I")
    axes[0, 1].plot(np.imag(iq0), label="Q")
    axes[0, 1].set_title("IQ — time")
    axes[0, 1].legend()

    window = np.hanning(cfg.num_adc_samples)
    fft_r_mag = np.abs(np.fft.fft(r0 * window)[: cfg.num_adc_samples // 2])
    axes[1, 0].plot(fft_r_mag)
    axes[1, 0].set_title("Real — range FFT mag (half)")

    fft_iq_mag = np.abs(np.fft.fft(iq0.astype(np.complex128) * window)[: cfg.num_adc_samples // 2])
    axes[1, 1].plot(fft_iq_mag)
    axes[1, 1].set_title("IQ — range FFT mag (half)")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Debug: compare real vs IQ parse.")
    p.add_argument("bin_path", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--chirp", type=int, default=0)
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--output", type=Path, default=Path("outputs/figures/debug_parse_compare.png"))
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    compare_and_plot(args.bin_path, cfg, args.chirp, args.rx, args.output)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
