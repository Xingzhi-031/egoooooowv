"""
Radar parameters used by the parsers and plots.

Load from a JSON sidecar (`load_radar_config_json`) or straight from a TI
mmWave CLI `.cfg` (`scripts.ti_cfg.load_radar_config_ti_cfg`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

C = 299_792_458.0


@dataclass
class RadarConfig:
    num_adc_samples: int
    num_rx: int
    num_tx: int
    num_loops: int
    #: if None -> num_tx * num_loops
    chirps_per_frame: int | None = None
    is_complex: bool = False
    #: per-chirp layout of complex samples:
    #:   "rx_major"  = RX0 all samples, then RX1, ... (TI adcbufCfg chanInterleave=1)
    #:   "sample_rx" = sample 0 of every RX, then sample 1, ... (chanInterleave=0)
    iq_interleave: str = "sample_rx"
    #: order of the two int16 words of one complex sample:
    #:   "IQ" = I first; "QI" = Q first (TI adcbufCfg sampleSwap=1)
    iq_order: str = "IQ"
    #: TX index (0-based) fired by each chirp slot of one loop, e.g. [0, 2, 1]
    tx_stream_order: list[int] = field(default_factory=lambda: [0, 2, 1])
    sample_rate_hz: float | None = None
    freq_slope_hz_per_s: float | None = None
    start_freq_hz: float | None = None
    #: idle + ramp-end time of one chirp (s); one TDM loop lasts num_tx * this
    chirp_cycle_s: float | None = None
    frame_period_s: float | None = None
    notes: str = ""
    source: str = ""
    #: manual flag, set only after a physical check (e.g. corner reflector)
    config_verified: bool = False

    def resolved_chirps_per_frame(self) -> int:
        if self.chirps_per_frame is not None:
            return self.chirps_per_frame
        return self.num_tx * self.num_loops

    # ---- derived quantities (None when the needed fields are missing) ----

    def range_bin_m(self) -> float | None:
        """Range per FFT bin: c * fs / (2 * S * N)."""
        if not (self.sample_rate_hz and self.freq_slope_hz_per_s):
            return None
        return C * self.sample_rate_hz / (2.0 * self.freq_slope_hz_per_s * self.num_adc_samples)

    def wavelength_m(self) -> float | None:
        if not self.start_freq_hz:
            return None
        f = self.start_freq_hz
        if self.freq_slope_hz_per_s and self.sample_rate_hz:
            # centre of the sampled sweep (ignores ADC start time; < 1 % effect at 60 GHz)
            f += 0.5 * self.freq_slope_hz_per_s * self.num_adc_samples / self.sample_rate_hz
        return C / f

    def loop_period_s(self) -> float | None:
        if not self.chirp_cycle_s:
            return None
        return self.num_tx * self.chirp_cycle_s

    def velocity_bin_mps(self) -> float | None:
        """Velocity per Doppler bin when Doppler runs over the loops of one TX."""
        lam, tl = self.wavelength_m(), self.loop_period_s()
        if lam is None or tl is None:
            return None
        return lam / (2.0 * self.num_loops * tl)

    def max_velocity_mps(self) -> float | None:
        lam, tl = self.wavelength_m(), self.loop_period_s()
        if lam is None or tl is None:
            return None
        return lam / (4.0 * tl)


def load_radar_config_json(path: Path) -> RadarConfig:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    required = ("num_adc_samples", "num_rx", "num_tx", "num_loops")
    missing = [k for k in required if k not in data]
    if missing:
        raise KeyError(f"Missing required keys in JSON: {missing}")

    chirps = data.get("chirps_per_frame")
    if chirps is not None:
        chirps = int(chirps)

    cfg = RadarConfig(
        num_adc_samples=int(data["num_adc_samples"]),
        num_rx=int(data["num_rx"]),
        num_tx=int(data["num_tx"]),
        num_loops=int(data["num_loops"]),
        chirps_per_frame=chirps,
        is_complex=bool(data.get("is_complex", False)),
        iq_interleave=str(data.get("iq_interleave", "sample_rx")),
        iq_order=str(data.get("iq_order", "IQ")).upper(),
        tx_stream_order=[int(t) for t in data.get("tx_stream_order", [0, 2, 1])],
        sample_rate_hz=_optional_float(data.get("sample_rate_hz")),
        freq_slope_hz_per_s=_optional_float(data.get("freq_slope_hz_per_s")),
        start_freq_hz=_optional_float(data.get("start_freq_hz")),
        chirp_cycle_s=_optional_float(data.get("chirp_cycle_s")),
        frame_period_s=_optional_float(data.get("frame_period_s")),
        notes=str(data.get("notes", "")),
        source=str(data.get("source", str(path.resolve()))),
        config_verified=bool(data.get("config_verified", False)),
    )
    validate(cfg)
    return cfg


def validate(cfg: RadarConfig) -> None:
    if cfg.iq_interleave not in ("sample_rx", "rx_major"):
        raise ValueError(f"iq_interleave must be 'sample_rx' or 'rx_major', got {cfg.iq_interleave!r}")
    if cfg.iq_order not in ("IQ", "QI"):
        raise ValueError(f"iq_order must be 'IQ' or 'QI', got {cfg.iq_order!r}")
    if sorted(cfg.tx_stream_order) != list(range(cfg.num_tx)):
        raise ValueError(
            f"tx_stream_order {cfg.tx_stream_order} must be a permutation of 0..{cfg.num_tx - 1}"
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
