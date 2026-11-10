"""
DCA1000 raw .bin (int16 stream, no headers in "raw" logging mode)
-> ADC cube (num_chirps, num_adc_samples, num_rx).

Layout of one chirp for complex capture is set by two RadarConfig fields:
  iq_interleave  "rx_major" | "sample_rx"   (TI adcbufCfg chanInterleave 1 | 0)
  iq_order       "QI" | "IQ"                (TI adcbufCfg sampleSwap   1 | 0)

For the IWR6843ISK-ODS captures in this repo the data-driven check in
`scripts/analyze_capture.py` and docs/DATA_FORMAT.md supports rx_major + QI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.config_loader import RadarConfig, load_radar_config_json


def load_raw_int16(bin_path: Path) -> np.ndarray:
    bin_path = Path(bin_path)
    if not bin_path.is_file():
        raise FileNotFoundError(f"Binary not found: {bin_path}")
    return np.fromfile(bin_path, dtype=np.int16)


def _trim_to_multiple(raw: np.ndarray, block_int16: int) -> tuple[np.ndarray, int]:
    if block_int16 <= 0:
        raise ValueError("block_int16 must be positive")
    rem = int(raw.size % block_int16)
    if rem == 0:
        return raw, 0
    return raw[: raw.size - rem], rem


def int16_per_chirp_real(cfg: RadarConfig) -> int:
    return cfg.num_adc_samples * cfg.num_rx


def int16_per_chirp_complex(cfg: RadarConfig) -> int:
    return 2 * cfg.num_adc_samples * cfg.num_rx


def parse_real_adc(raw: np.ndarray, cfg: RadarConfig) -> np.ndarray:
    block = int16_per_chirp_real(cfg)
    trimmed, _ = _trim_to_multiple(raw, block)
    if trimmed.size == 0:
        raise ValueError("After trim, no int16 samples left for real ADC parsing.")
    num_chirps = trimmed.size // block
    rows = trimmed.reshape(num_chirps, block)
    if cfg.iq_interleave == "rx_major":
        return np.ascontiguousarray(
            rows.reshape(num_chirps, cfg.num_rx, cfg.num_adc_samples).transpose(0, 2, 1)
        ).astype(np.float32)
    return rows.reshape(num_chirps, cfg.num_adc_samples, cfg.num_rx).astype(np.float32)


def int16_pairs_to_complex(first: np.ndarray, second: np.ndarray, iq_order: str = "IQ") -> np.ndarray:
    """Combine the two int16 words of each complex sample according to iq_order."""
    if iq_order == "IQ":
        i_part, q_part = first, second
    elif iq_order == "QI":
        q_part, i_part = first, second
    else:
        raise ValueError(f"Unknown iq_order: {iq_order!r}; use 'IQ' or 'QI'")
    return i_part.astype(np.float32) + 1j * q_part.astype(np.float32)


def parse_complex_iq_adc(raw: np.ndarray, cfg: RadarConfig) -> np.ndarray:
    """
    Complex capture -> (num_chirps, num_adc_samples, num_rx) complex64.

    - rx_major:  per chirp, RX0 holds S complex samples (2*S int16), then RX1, ...
    - sample_rx: per chirp, complex samples in (sample, rx) C-order (rx fastest).
    Within each complex sample the two int16 words are ordered by cfg.iq_order.
    """
    block_int16 = int16_per_chirp_complex(cfg)
    trimmed, _ = _trim_to_multiple(raw, block_int16)
    if trimmed.size == 0:
        raise ValueError("After trim, no int16 samples left for IQ ADC parsing.")
    n_ch = trimmed.size // block_int16
    rows = trimmed.reshape(n_ch, block_int16)
    order = cfg.iq_order

    if cfg.iq_interleave == "rx_major":
        seg = rows.reshape(n_ch, cfg.num_rx, 2 * cfg.num_adc_samples)
        iq = int16_pairs_to_complex(seg[:, :, 0::2], seg[:, :, 1::2], order)
        return np.ascontiguousarray(iq.transpose(0, 2, 1)).astype(np.complex64)

    if cfg.iq_interleave == "sample_rx":
        iq = int16_pairs_to_complex(rows[:, 0::2], rows[:, 1::2], order)
        return iq.reshape(n_ch, cfg.num_adc_samples, cfg.num_rx).astype(np.complex64)

    raise ValueError(f"Unknown iq_interleave: {cfg.iq_interleave!r}; use 'sample_rx' or 'rx_major'")


def find_zero_chirps(cube: np.ndarray) -> np.ndarray:
    """Indices of chirps whose samples are all exactly zero (lost / zero-filled packets)."""
    flat = np.abs(cube.reshape(cube.shape[0], -1))
    return np.flatnonzero(flat.max(axis=1) == 0)


def parse_adc_cube(bin_path: Path, cfg: RadarConfig) -> tuple[np.ndarray, dict]:
    raw = load_raw_int16(bin_path)
    if cfg.is_complex:
        block = int16_per_chirp_complex(cfg)
        _, trim_n = _trim_to_multiple(raw, block)
        cube = parse_complex_iq_adc(raw, cfg)
    else:
        block = int16_per_chirp_real(cfg)
        _, trim_n = _trim_to_multiple(raw, block)
        cube = parse_real_adc(raw, cfg)

    zeros = find_zero_chirps(cube)
    meta = {
        "trim_int16": trim_n,
        "int16_per_chirp": block,
        "raw_int16_count": int(raw.size),
        "num_chirps": int(cube.shape[0]),
        "num_zero_chirps": int(zeros.size),
        "zero_chirp_indices": zeros.tolist(),
    }
    return cube, meta


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parse DCA1000 int16 .bin using RadarConfig JSON.")
    p.add_argument("bin_path", type=Path, help="Path to .bin file")
    p.add_argument("--config", type=Path, required=True, help="Radar JSON config")
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()
    cfg = load_radar_config_json(args.config)
    cube, meta = parse_adc_cube(args.bin_path, cfg)
    print("Parsed ADC cube shape:", cube.shape, "dtype:", cube.dtype)
    zi = meta.pop("zero_chirp_indices")
    print("Meta:", meta)
    if zi:
        print(f"All-zero chirps (first 20): {zi[:20]}")


if __name__ == "__main__":
    main()
