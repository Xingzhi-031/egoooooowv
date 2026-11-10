"""
Frame / loop / TX layout on top of the chirp-major cube.

TDM-MIMO: each loop fires the TXs in the order given by cfg.tx_stream_order
(for the ODS captures: chirp slot 0 -> TX0, slot 1 -> TX2, slot 2 -> TX1,
i.e. chirpCfg txEnable masks 1, 4, 2). "Canonical" order is TX0, TX1, TX2.

Fix (Nov 2026): the earlier version reshaped the (chirp, sample, rx) cube as
if its last two axes were (rx, sample), which mixed samples across RX. The
reshape now keeps (sample, rx) and transposes explicitly; see tests/.
"""

from __future__ import annotations

import numpy as np

from scripts.config_loader import RadarConfig


def truncate_chirp_cube_to_full_frames(
    cube: np.ndarray,
    cfg: RadarConfig,
) -> tuple[np.ndarray, int]:
    """Keep only the first n_full * chirps_per_frame chirps. Returns (truncated_cube, n_dropped)."""
    cpf = cfg.resolved_chirps_per_frame()
    n = cube.shape[0]
    n_full = (n // cpf) * cpf
    if n_full == n:
        return cube, 0
    if n_full == 0:
        raise ValueError(f"Not enough chirps for one frame: have {n}, need {cpf}")
    return cube[:n_full].copy(), n - n_full


def chirp_cube_to_frame_tensor_stream(
    cube: np.ndarray,
    cfg: RadarConfig,
) -> np.ndarray:
    """
    (num_chirps, S, R) -> (num_frames, num_loops, num_tx[stream order], R, S).
    """
    cpf = cfg.resolved_chirps_per_frame()
    n, s, r = cube.shape
    if n % cpf != 0:
        raise ValueError(f"num_chirps {n} not divisible by chirps_per_frame {cpf}")
    if cpf != cfg.num_loops * cfg.num_tx:
        raise ValueError(f"chirps_per_frame {cpf} != num_loops*num_tx {cfg.num_loops * cfg.num_tx}")
    nf = n // cpf
    x = cube.reshape(nf, cfg.num_loops, cfg.num_tx, s, r)
    return np.ascontiguousarray(x.transpose(0, 1, 2, 4, 3))


def stream_tx_to_canonical(frame_stream: np.ndarray, stream_order: list[int] | None = None) -> np.ndarray:
    """
    Reorder the TX axis from firing order to canonical TX0, TX1, ... order.

    frame_stream: (F, L, T, R, S); stream_order[k] = TX fired in chirp slot k.
    Default [0, 2, 1] matches the ODS captures (TX1 -> TX3 -> TX2 in 1-based names).
    """
    order = [0, 2, 1] if stream_order is None else list(stream_order)
    if frame_stream.shape[2] != len(order):
        raise ValueError(f"TX axis has {frame_stream.shape[2]} slots but stream_order has {len(order)}")
    out = np.empty_like(frame_stream)
    for slot, tx in enumerate(order):
        out[:, :, tx, ...] = frame_stream[:, :, slot, ...]
    return out


def fill_zero_chirps(frames: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Replace all-zero chirps (lost packets) by the mean of the neighbouring loops
    of the same TX/RX in the same frame. frames: (F, L, T, R, S). Returns (filled, count).

    This is a display / Doppler-FFT convenience, not a recovery of the lost data.
    """
    out = frames.copy()
    dead = np.abs(frames).max(axis=(3, 4)) == 0  # (F, L, T)
    count = int(dead.sum())
    if count == 0:
        return out, 0
    nl = frames.shape[1]
    for f, l, t in zip(*np.nonzero(dead)):
        nbrs = [k for k in (l - 1, l + 1) if 0 <= k < nl and not dead[f, k, t]]
        if nbrs:
            out[f, l, t] = np.mean([frames[f, k, t] for k in nbrs], axis=0)
    return out, count


def frame_tensor_to_separate_iq(z: np.ndarray) -> np.ndarray:
    """(F, L, T, R, S) complex -> (F, L, T, R, S, 2) float32 last dim [real, imag]."""
    return np.stack([np.real(z), np.imag(z)], axis=-1).astype(np.float32)


def rd_input_single_tx_rx(
    frame_canonical: np.ndarray,
    frame_idx: int,
    tx_canonical: int,
    rx_idx: int,
) -> np.ndarray:
    """One frame, one TX (canonical), one RX: (num_loops, num_adc_samples) complex."""
    return frame_canonical[frame_idx, :, tx_canonical, rx_idx, :].astype(np.complex64)
