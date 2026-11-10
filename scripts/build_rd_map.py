"""
Range-Doppler (RD) maps.

--framed (recommended): one frame, one TX, one RX; range FFT over ADC samples,
Doppler FFT over the loops of that TX. Axes in metres / m/s when the config
has timing fields.

Default (no --framed): Doppler FFT over *all* chirps in the file for one RX.
That mixes the three TDM TXs and spans frame gaps, so it is only a quick look,
not a physical Doppler spectrum.
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
from scripts.iq_frame_tensor import (
    chirp_cube_to_frame_tensor_stream,
    fill_zero_chirps,
    rd_input_single_tx_rx,
    stream_tx_to_canonical,
    truncate_chirp_cube_to_full_frames,
)
from scripts.parse_bin import parse_adc_cube


def range_doppler(sig: np.ndarray, num_range_bins: int | None = None) -> np.ndarray:
    """
    sig: (num_slow, num_adc) complex. Hann window on fast time, range FFT,
    then Doppler FFT along slow time with fftshift. Returns |RD| (doppler, range).
    """
    n_slow, n_adc = sig.shape
    sig = sig.astype(np.complex128, copy=False)
    sig = sig - sig.mean(axis=1, keepdims=True)  # remove per-chirp DC
    rng = np.fft.fft(sig * np.hanning(n_adc)[np.newaxis, :], axis=1)
    rng = rng[:, : (num_range_bins or n_adc // 2)]
    dop = np.fft.fftshift(np.fft.fft(rng * np.hanning(n_slow)[:, np.newaxis], axis=0), axes=0)
    return np.abs(dop)


def build_rd_map_single_rx(adc_cube: np.ndarray, cfg: RadarConfig, rx_index: int) -> np.ndarray:
    if adc_cube.ndim != 3:
        raise ValueError(f"Expected adc_cube ndim=3, got {adc_cube.ndim}")
    if not 0 <= rx_index < adc_cube.shape[2]:
        raise IndexError(f"rx_index {rx_index} out of [0, {adc_cube.shape[2]})")
    return range_doppler(adc_cube[:, :, rx_index])


def framed_tensor(adc_cube: np.ndarray, cfg: RadarConfig) -> tuple[np.ndarray, int]:
    """Chirp cube -> canonical (F, L, T, R, S) with zero chirps filled. Returns (tensor, n_filled)."""
    stream = chirp_cube_to_frame_tensor_stream(adc_cube, cfg)
    canon = stream_tx_to_canonical(stream, cfg.tx_stream_order)
    return fill_zero_chirps(canon)


def build_rd_map_framed_single_tx(
    adc_cube: np.ndarray,
    cfg: RadarConfig,
    frame_idx: int,
    tx_canonical: int,
    rx_index: int,
) -> np.ndarray:
    canon, _ = framed_tensor(adc_cube, cfg)
    return range_doppler(rd_input_single_tx_rx(canon, frame_idx, tx_canonical, rx_index))


def rd_axes(cfg: RadarConfig, rd_shape: tuple[int, int], framed: bool):
    """Return (x_extent, xlabel, y_extent, ylabel) for imshow."""
    n_dop, n_rng = rd_shape
    dr = cfg.range_bin_m()
    # extents are pixel edges, so bin k is centred on k*dr (range) and (k - n/2)*dv (Doppler)
    if dr is not None:
        x = (-0.5 * dr, (n_rng - 0.5) * dr)
        xl = "Range (m)"
    else:
        x = (-0.5, n_rng - 0.5)
        xl = "Range bin"
    dv = cfg.velocity_bin_mps() if framed else None
    if dv is not None:
        # sign convention (approaching = + or -) still to be checked with a target of known direction
        y = ((-n_dop / 2 - 0.5) * dv, (n_dop / 2 - 0.5) * dv)
        yl = "Radial velocity (m/s)"
    else:
        y = (-n_dop / 2 - 0.5, n_dop / 2 - 0.5)
        yl = "Doppler bin (fftshift)"
    return x, xl, y, yl


def save_rd_heatmap(
    rd_mag: np.ndarray,
    cfg: RadarConfig,
    output_path: Path,
    subtitle: str = "",
    framed: bool = False,
    max_range_m: float | None = None,
) -> None:
    label = "VERIFIED (config flag)" if cfg.config_verified else "EXPLORATORY"
    (x0, x1), xl, (y0, y1), yl = rd_axes(cfg, rd_mag.shape, framed)
    db = 20 * np.log10(rd_mag + 1e-9)
    fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
    im = ax.imshow(db, aspect="auto", origin="lower", cmap="viridis",
                   extent=(x0, x1, y0, y1), vmin=np.percentile(db, 5), vmax=db.max())
    if max_range_m is not None and xl.startswith("Range (m)"):
        ax.set_xlim(0, max_range_m)
    ax.set_title(f"Range-Doppler [{label}]{subtitle}")
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    fig.colorbar(im, ax=ax, label="|RD| (dB)")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Range-Doppler map.")
    p.add_argument("bin_path", type=Path)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--rx", type=int, default=0)
    p.add_argument("--output", type=Path, default=Path("outputs/figures/rd_map.png"))
    p.add_argument("--framed", action="store_true",
                   help="Doppler over the loops of one TX within one frame (recommended).")
    p.add_argument("--frame", type=int, default=0, help="Frame index (with --framed).")
    p.add_argument("--tx-canonical", type=int, default=0, metavar="N",
                   help="Canonical TX index 0..num_tx-1 (with --framed).")
    p.add_argument("--drop-partial-frames", action="store_true",
                   help="Drop trailing chirps so the count is a multiple of chirps_per_frame.")
    p.add_argument("--max-range", type=float, default=None, help="Clip plot at this range (m).")
    return p


def main() -> None:
    args = _parser().parse_args()
    cfg = load_radar_config_json(args.config)
    cube, meta = parse_adc_cube(args.bin_path, cfg)
    meta.pop("zero_chirp_indices", None)
    print("Parsed meta:", meta)
    sub = ""
    if args.framed:
        cpf = cfg.resolved_chirps_per_frame()
        if cube.shape[0] % cpf != 0:
            if not args.drop_partial_frames:
                raise ValueError(f"num_chirps {cube.shape[0]} not divisible by {cpf}; "
                                 "use --drop-partial-frames or fix cfg.")
            cube, dropped = truncate_chirp_cube_to_full_frames(cube, cfg)
            print(f"drop-partial-frames: dropped {dropped} chirps; num_chirps={cube.shape[0]}")
        canon, n_filled = framed_tensor(cube, cfg)
        if n_filled:
            print(f"filled {n_filled} all-zero chirps from neighbouring loops")
        rd = range_doppler(rd_input_single_tx_rx(canon, args.frame, args.tx_canonical, args.rx))
        sub = f"\nframe {args.frame}, TX{args.tx_canonical}, RX{args.rx}"
    else:
        print("WARNING: non-framed Doppler mixes TDM TXs and frame gaps (quick look only).")
        rd = build_rd_map_single_rx(cube, cfg, args.rx)
    print("RD map shape (doppler, range):", rd.shape)
    save_rd_heatmap(rd, cfg, args.output, subtitle=sub, framed=args.framed, max_range_m=args.max_range)
    print(f"Saved figure: {args.output}")


if __name__ == "__main__":
    main()
