"""
Synthetic end-to-end checks: build a TDM-MIMO cube with one target at a known
range bin / Doppler bin, pack it into the DCA1000 int16 layout, then parse it
back and check where the RD peak lands. Run: python -m pytest -q
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_rd_map import framed_tensor, range_doppler  # noqa: E402
from scripts.config_loader import RadarConfig, load_radar_config_json  # noqa: E402
from scripts.iq_frame_tensor import (  # noqa: E402
    chirp_cube_to_frame_tensor_stream,
    rd_input_single_tx_rx,
    stream_tx_to_canonical,
)
from scripts.parse_bin import find_zero_chirps, parse_adc_cube, parse_complex_iq_adc  # noqa: E402
from scripts.ti_cfg import load_radar_config_ti_cfg  # noqa: E402

S, R, T, L, F = 64, 4, 3, 16, 2
RANGE_BIN, DOPPLER_BIN = 11, 3


def _cfg(**kw) -> RadarConfig:
    base = RadarConfig(num_adc_samples=S, num_rx=R, num_tx=T, num_loops=L, chirps_per_frame=T * L,
                       is_complex=True, iq_interleave="rx_major", iq_order="QI", tx_stream_order=[0, 2, 1])
    return replace(base, **kw)


def _truth() -> np.ndarray:
    """Canonical (F, L, T, R, S) complex signal; TX/RX give distinct constant phases."""
    s = np.arange(S)
    l = np.arange(L)
    fast = np.exp(2j * np.pi * RANGE_BIN * s / S)
    slow = np.exp(2j * np.pi * DOPPLER_BIN * l / L)
    tx_ph = np.exp(1j * np.array([0.0, 0.7, 1.9]))
    rx_ph = np.exp(1j * np.array([0.0, 0.4, 1.1, 2.3]))
    x = (slow[:, None, None, None] * tx_ph[None, :, None, None]
         * rx_ph[None, None, :, None] * fast[None, None, None, :])
    return np.broadcast_to(1000 * x, (F, L, T, R, S)).copy()


def _pack(truth: np.ndarray, cfg: RadarConfig) -> np.ndarray:
    """Canonical truth -> int16 stream in the layout described by cfg."""
    stream = truth[:, :, cfg.tx_stream_order]                      # firing order
    chirps = stream.reshape(F * L * T, R, S)                       # (chirp, rx, sample)
    i, q = np.round(chirps.real), np.round(chirps.imag)
    a, b = (q, i) if cfg.iq_order == "QI" else (i, q)
    if cfg.iq_interleave == "rx_major":
        words = np.stack([a, b], axis=-1)                          # (chirp, rx, sample, 2)
    else:
        words = np.stack([a, b], axis=-1).transpose(0, 2, 1, 3)    # (chirp, sample, rx, 2)
    return words.astype(np.int16).ravel()


@pytest.mark.parametrize("interleave", ["rx_major", "sample_rx"])
@pytest.mark.parametrize("order", ["QI", "IQ"])
def test_parse_round_trip(interleave, order):
    cfg = _cfg(iq_interleave=interleave, iq_order=order)
    truth = _truth()
    cube = parse_complex_iq_adc(_pack(truth, cfg), cfg)            # (chirp, S, R)
    canon = stream_tx_to_canonical(chirp_cube_to_frame_tensor_stream(cube, cfg), cfg.tx_stream_order)
    assert canon.shape == (F, L, T, R, S)
    assert np.allclose(canon, np.round(truth.real) + 1j * np.round(truth.imag))


def test_rd_peak_at_known_bins():
    cfg = _cfg()
    cube = parse_complex_iq_adc(_pack(_truth(), cfg), cfg)
    canon, _ = framed_tensor(cube, cfg)
    for tx in range(T):
        rd = range_doppler(rd_input_single_tx_rx(canon, 0, tx, 2))
        d, r = np.unravel_index(rd.argmax(), rd.shape)
        assert r == RANGE_BIN
        assert d == L // 2 + DOPPLER_BIN


def test_wrong_iq_order_mirrors_range():
    """Reading Q-first data as I-first moves the target to the negative-frequency half."""
    cfg = _cfg()
    wrong = replace(cfg, iq_order="IQ")
    cube = parse_complex_iq_adc(_pack(_truth(), cfg), wrong)
    spec = np.abs(np.fft.fft(cube[0, :, 0]))
    assert spec.argmax() == S - RANGE_BIN


def test_old_reshape_bug_is_gone():
    """The pre-fix reshape (cube -> [..., R, S] directly) breaks the RX/sample split."""
    cfg = _cfg()
    truth = _truth()
    cube = parse_complex_iq_adc(_pack(truth, cfg), cfg)
    old = cube.reshape(F, L, T, R, S)                               # what the old code did
    new = chirp_cube_to_frame_tensor_stream(cube, cfg)
    assert not np.allclose(old, new)
    assert np.allclose(new[:, :, 0], np.round(truth.real[:, :, 0]) + 1j * np.round(truth.imag[:, :, 0]))


def test_zero_chirps_detected_and_filled(tmp_path):
    cfg = _cfg()
    raw = _pack(_truth(), cfg).reshape(F * L * T, -1)
    raw[4] = 0
    p = tmp_path / "x.bin"
    raw.ravel().tofile(p)
    cube, meta = parse_adc_cube(p, cfg)
    assert meta["num_zero_chirps"] == 1 and meta["zero_chirp_indices"] == [4]
    assert find_zero_chirps(cube).tolist() == [4]
    canon, n = framed_tensor(cube, cfg)
    assert n == 1
    assert np.abs(canon).max(axis=(3, 4)).min() > 0


def test_ti_cfg_matches_json():
    a = load_radar_config_ti_cfg(ROOT / "configs/ti/iwr6843ods_capture_32loops_reconstructed.cfg")
    b = load_radar_config_json(ROOT / "configs/ods_iq_frames.json")
    for k in ("num_adc_samples", "num_rx", "num_tx", "num_loops", "chirps_per_frame", "is_complex",
              "iq_interleave", "iq_order", "tx_stream_order", "sample_rate_hz", "freq_slope_hz_per_s",
              "start_freq_hz", "frame_period_s"):
        assert getattr(a, k) == getattr(b, k), k
    assert a.chirp_cycle_s == pytest.approx(b.chirp_cycle_s)
    assert a.range_bin_m() == pytest.approx(0.0441, abs=1e-4)
