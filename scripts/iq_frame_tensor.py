"""
Frame / loop / TX layout on top of chirp-major cube.

Stream order (as emitted per loop): chirp 0 -> TX1, chirp 1 -> TX3, chirp 2 -> TX2.
Canonical TX axis: index 0 = TX1, 1 = TX2, 2 = TX3.
"""

from __future__ import annotations

import numpy as np

from scripts.config_loader import RadarConfig


def truncate_chirp_cube_to_full_frames(
    cube: np.ndarray,
    cfg: RadarConfig,
) -> tuple[np.ndarray, int]:
    """
    Keep only the first n_full * chirps_per_frame chirps. Returns (truncated_cube, n_dropped).
    """
    cpf = cfg.resolved_chirps_per_frame()
    n = cube.shape[0]
    n_full = (n // cpf) * cpf
    if n_full == n:
        return cube, 0
    if n_full == 0:
        raise ValueError(f"Not enough chirps for one frame: have {n}, need {cpf}")
    dropped = n - n_full
    return cube[:n_full].copy(), dropped


def chirp_cube_to_frame_tensor_stream(
    cube: np.ndarray,
    cfg: RadarConfig,
) -> np.ndarray:
    """
    (num_chirps, S, R) -> (num_frames, num_loops, 3_stream, R, S) complex.

    Stream axis dim 2 is [TX1, TX3, TX2] for each loop (indices 0,1,2).
    """
    cpf = cfg.resolved_chirps_per_frame()
    n = cube.shape[0]
    if n % cpf != 0:
        raise ValueError(
            f"num_chirps {n} not divisible by chirps_per_frame {cpf}"
        )
    nf = n // cpf
    # chirp-major cube is (chirp, sample, rx); frame layout [F,L,T,R,S]
    x = cube[: nf * cpf].reshape(
        nf, cfg.num_loops, cfg.num_tx, cfg.num_rx, cfg.num_adc_samples
    )
    return np.ascontiguousarray(x)


def stream_tx_to_canonical(frame_stream: np.ndarray) -> np.ndarray:
    """
    Permute stream axis [TX1, TX3, TX2] -> canonical [TX1, TX2, TX3].

    frame_stream: (F, L, 3, R, S)
    returns:      (F, L, 3, R, S)
    """
    if frame_stream.shape[2] != 3:
        raise ValueError("Expected num_tx=3 on axis 2 for this reorder")
    out = np.empty_like(frame_stream, dtype=frame_stream.dtype)
    out[:, :, 0, ...] = frame_stream[:, :, 0, ...]  # TX1
    out[:, :, 1, ...] = frame_stream[:, :, 2, ...]  # TX2 <- stream idx 2
    out[:, :, 2, ...] = frame_stream[:, :, 1, ...]  # TX3 <- stream idx 1
    return out


def frame_tensor_to_separate_iq(
    z: np.ndarray,
) -> np.ndarray:
    """(F, L, T, R, S) complex -> (F, L, T, R, S, 2) float32 last dim [real, imag]."""
    return np.stack([np.real(z), np.imag(z)], axis=-1).astype(np.float32)


def rd_input_single_tx_rx(
    frame_canonical: np.ndarray,
    frame_idx: int,
    tx_canonical: int,
    rx_idx: int,
) -> np.ndarray:
    """
    One frame, one TX (canonical), one RX: (num_loops, num_adc_samples) complex for RD.

    Doppler is across loops (32); range FFT across adc.
    """
    return frame_canonical[frame_idx, :, tx_canonical, rx_idx, :].astype(np.complex64)
