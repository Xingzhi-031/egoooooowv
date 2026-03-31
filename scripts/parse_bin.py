"""
DCA1000 int16 -> cube (num_chirps, num_adc_samples, num_rx).
TODO: optional header skip; per-frame split; LVDS/RX order vs cfg.
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
    # TODO: skip header bytes if export adds one
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
    # TODO: verify row-major (sample, rx) vs TI LVDS order
    block = int16_per_chirp_real(cfg)
    trimmed, _ = _trim_to_multiple(raw, block)
    if trimmed.size == 0:
        raise ValueError("After trim, no int16 samples left for real ADC parsing.")
    if trimmed.size % block != 0:
        raise ValueError(
            f"Real ADC: trimmed length {trimmed.size} not divisible by int16_per_chirp={block}"
        )
    num_chirps = trimmed.size // block
    return trimmed.reshape(num_chirps, cfg.num_adc_samples, cfg.num_rx).astype(np.float32)


def parse_complex_iq_adc(raw: np.ndarray, cfg: RadarConfig) -> np.ndarray:
    # TODO: confirm I,Q interleave and reshape order vs TI
    block_int16 = int16_per_chirp_complex(cfg)
    trimmed, _ = _trim_to_multiple(raw, block_int16)
    if trimmed.size % 2 != 0:
        raise ValueError(
            f"IQ path requires even int16 count after trim; got {trimmed.size}"
        )
    if trimmed.size == 0:
        raise ValueError("After trim, no int16 samples left for IQ ADC parsing.")
    if trimmed.size % block_int16 != 0:
        raise ValueError(
            f"IQ ADC: trimmed length {trimmed.size} not divisible by int16_per_chirp={block_int16}"
        )
    i = trimmed[0::2].astype(np.float32)
    q = trimmed[1::2].astype(np.float32)
    iq = i + 1j * q
    num_chirps = iq.size // (cfg.num_adc_samples * cfg.num_rx)
    return iq.reshape(num_chirps, cfg.num_adc_samples, cfg.num_rx).astype(np.complex64)


def parse_adc_cube(bin_path: Path, cfg: RadarConfig) -> tuple[np.ndarray, dict[str, int]]:
    raw = load_raw_int16(bin_path)
    if cfg.is_complex:
        block = int16_per_chirp_complex(cfg)
        _, trim_n = _trim_to_multiple(raw, block)
        cube = parse_complex_iq_adc(raw, cfg)
    else:
        block = int16_per_chirp_real(cfg)
        _, trim_n = _trim_to_multiple(raw, block)
        cube = parse_real_adc(raw, cfg)

    meta = {
        "trim_int16": trim_n,
        "int16_per_chirp": block,
        "raw_int16_count": int(raw.size),
        "num_chirps": int(cube.shape[0]),
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
    print("Meta:", meta)


if __name__ == "__main__":
    main()
