"""
Radar JSON config. TODO: parse TI mmWave `.cfg` when field mapping is fixed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RadarConfig:
    num_adc_samples: int
    num_rx: int
    num_tx: int
    num_loops: int
    # TODO: confirm vs cfg; if None -> num_tx * num_loops
    chirps_per_frame: int | None = None
    is_complex: bool = False
    # TODO: map from cfg (e.g. digOutSampleRate)
    sample_rate_hz: float | None = None
    # TODO: map from cfg (e.g. freqSlope)
    freq_slope_hz_per_s: float | None = None
    notes: str = ""
    source: str = ""
    # manual flag after validation
    config_verified: bool = False

    def resolved_chirps_per_frame(self) -> int:
        if self.chirps_per_frame is not None:
            return self.chirps_per_frame
        return self.num_tx * self.num_loops


def load_radar_config_json(path: Path) -> RadarConfig:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    # TODO: schema validation / optional keys
    required = ("num_adc_samples", "num_rx", "num_tx", "num_loops")
    missing = [k for k in required if k not in data]
    if missing:
        raise KeyError(f"Missing required keys in JSON: {missing}")

    chirps = data.get("chirps_per_frame")
    if chirps is not None:
        chirps = int(chirps)

    return RadarConfig(
        num_adc_samples=int(data["num_adc_samples"]),
        num_rx=int(data["num_rx"]),
        num_tx=int(data["num_tx"]),
        num_loops=int(data["num_loops"]),
        chirps_per_frame=chirps,
        is_complex=bool(data.get("is_complex", False)),
        sample_rate_hz=_optional_float(data.get("sample_rate_hz")),
        freq_slope_hz_per_s=_optional_float(data.get("freq_slope_hz_per_s")),
        notes=str(data.get("notes", "")),
        source=str(data.get("source", str(path.resolve()))),
        config_verified=bool(data.get("config_verified", False)),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)

# TODO: load_radar_config_ti_cfg(path) -> RadarConfig
