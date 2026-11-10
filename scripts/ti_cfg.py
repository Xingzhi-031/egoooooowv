"""
Read a TI mmWave SDK CLI .cfg (e.g. the out-of-box demo profile sent over UART)
into a RadarConfig. Only the commands that affect the raw-data layout and the
range/Doppler axes are interpreted.

Field meanings follow the mmWave SDK 3.x user guide CLI table:
  channelCfg   <rxEn> <txEn> <cascading>
  adcCfg       <numADCBits> <adcOutputFmt: 0 real, 1 complex1x, 2 complex2x>
  adcbufCfg    <subFrame> <fmt: 0 complex, 1 real> <sampleSwap: 0 I-first, 1 Q-first>
               <chanInterleave: 0 interleaved, 1 non-interleaved> <chirpThreshold>
  profileCfg   <id> <startFreq GHz> <idle us> <adcStart us> <rampEnd us> <txPower>
               <txPhase> <slope MHz/us> <txStart us> <numAdcSamples> <sampleRate ksps> ...
  chirpCfg     <start> <end> <profile> <fVar> <slopeVar> <idleVar> <adcVar> <txMask>
  frameCfg     <chirpStart> <chirpEnd> <numLoops> <numFrames> <period ms> <trigger> <delay>
Comments starting with '%' or '//' are ignored.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.config_loader import RadarConfig, validate


def read_cfg_commands(path: Path) -> dict[str, list[list[str]]]:
    cmds: dict[str, list[list[str]]] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("%", 1)[0].split("//", 1)[0].strip()
        if not line:
            continue
        name, *args = line.split()
        cmds.setdefault(name, []).append(args)
    return cmds


def _popcount(x: int) -> int:
    return bin(x).count("1")


def load_radar_config_ti_cfg(path: Path) -> RadarConfig:
    c = read_cfg_commands(path)
    for need in ("channelCfg", "adcCfg", "profileCfg", "chirpCfg", "frameCfg"):
        if need not in c:
            raise KeyError(f"{path}: missing '{need}'")

    rx_en, _tx_en = int(c["channelCfg"][0][0]), int(c["channelCfg"][0][1])
    adc_fmt = int(c["adcCfg"][0][1])
    is_complex = adc_fmt in (1, 2)

    iq_order, interleave = "IQ", "sample_rx"
    if "adcbufCfg" in c:
        a = c["adcbufCfg"][0]
        iq_order = "QI" if int(a[2]) == 1 else "IQ"
        interleave = "rx_major" if int(a[3]) == 1 else "sample_rx"

    p = c["profileCfg"][0]
    start_ghz, idle_us, ramp_end_us = float(p[1]), float(p[2]), float(p[4])
    slope_mhz_us, n_adc, fs_ksps = float(p[7]), int(p[9]), float(p[10])

    f = c["frameCfg"][0]
    chirp_start, chirp_end, loops, period_ms = int(f[0]), int(f[1]), int(f[2]), float(f[4])

    slot_tx: dict[int, int] = {}
    for args in c["chirpCfg"]:
        s, e, mask = int(args[0]), int(args[1]), int(args[7])
        if _popcount(mask) != 1:
            raise ValueError(f"chirpCfg txMask {mask} enables {_popcount(mask)} TX; only TDM (1 TX/chirp) supported")
        for k in range(s, e + 1):
            slot_tx[k] = mask.bit_length() - 1
    slots = list(range(chirp_start, chirp_end + 1))
    used = [slot_tx[k] for k in slots]
    remap = {tx: i for i, tx in enumerate(sorted(set(used)))}  # compact TX ids if a TX is unused

    cfg = RadarConfig(
        num_adc_samples=n_adc,
        num_rx=_popcount(rx_en),
        num_tx=len(slots),
        num_loops=loops,
        chirps_per_frame=len(slots) * loops,
        is_complex=is_complex,
        iq_interleave=interleave,
        iq_order=iq_order,
        tx_stream_order=[remap[t] for t in used],
        sample_rate_hz=fs_ksps * 1e3,
        freq_slope_hz_per_s=slope_mhz_us * 1e12,
        start_freq_hz=start_ghz * 1e9,
        chirp_cycle_s=(idle_us + ramp_end_us) * 1e-6,
        frame_period_s=period_ms * 1e-3,
        notes=f"generated from {Path(path).name}",
        source=str(path),
    )
    validate(cfg)
    return cfg


def summary(cfg: RadarConfig) -> dict[str, float | None]:
    return {
        "range_bin_m": cfg.range_bin_m(),
        "max_range_m (half spectrum)": (cfg.range_bin_m() or 0) * cfg.num_adc_samples / 2 or None,
        "wavelength_mm": (cfg.wavelength_m() or 0) * 1e3 or None,
        "velocity_bin_mps": cfg.velocity_bin_mps(),
        "max_velocity_mps": cfg.max_velocity_mps(),
        "frame_rate_hz": (1.0 / cfg.frame_period_s) if cfg.frame_period_s else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="TI mmWave .cfg -> RadarConfig JSON")
    ap.add_argument("cfg", type=Path)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()
    cfg = load_radar_config_ti_cfg(args.cfg)
    d = asdict(cfg)
    print(json.dumps(d, indent=2))
    print("derived:", json.dumps({k: (round(v, 4) if v else v) for k, v in summary(cfg).items()}, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(d, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
