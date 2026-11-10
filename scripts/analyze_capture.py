"""
Data-driven checks + overview figures for one DCA1000 capture.

  python scripts/analyze_capture.py capture.bin --config configs/ods_iq_frames.json --out outputs/analysis/run01

Writes <out>/report.md and PNGs:
  layout scores   - which int16 layout gives a one-sided, RX-consistent, loop-stable spectrum
  frame period    - envelope autocorrelation at candidate chirps-per-frame values
  zero chirps     - all-zero chirps and their position inside the frame
  range_profile   - mean range profile per RX (dB vs m)
  range_time      - per-frame range profile (TX0/RX0), raw and with the static mean removed
  rd_frameN       - framed RD map of the frame with the most change vs. the static mean
These are consistency checks, not a physical calibration (no reflector at a known range).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.build_rd_map import framed_tensor, range_doppler, save_rd_heatmap
from scripts.config_loader import RadarConfig, load_radar_config_json
from scripts.iq_frame_tensor import truncate_chirp_cube_to_full_frames
from scripts.parse_bin import find_zero_chirps, load_raw_int16, parse_complex_iq_adc


def layout_scores(raw: np.ndarray, cfg: RadarConfig, n_chirps: int = 960) -> list[dict]:
    rows = []
    for interleave in ("rx_major", "sample_rx"):
        for order in ("QI", "IQ"):
            c = replace(cfg, iq_interleave=interleave, iq_order=order)
            cube = parse_complex_iq_adc(raw[: n_chirps * 2 * cfg.num_adc_samples * cfg.num_rx], c)
            x = cube - cube.mean(axis=1, keepdims=True)                  # (chirp, S, R)
            spec = np.abs(np.fft.fft(x * np.hanning(cfg.num_adc_samples)[None, :, None], axis=1)) ** 2
            s = cfg.num_adc_samples
            pos, neg = spec[:, 1 : s // 2].sum(), spec[:, s // 2 + 1 :].sum()
            mag = np.sqrt(spec[:, : s // 2])                             # positive half
            ok = mag.reshape(mag.shape[0], -1).max(1) > 0
            prof = mag[ok].mean(0).T                                     # (R, bins)
            rxc = np.mean([np.corrcoef(prof[i], prof[j])[0, 1]
                           for i in range(cfg.num_rx) for j in range(i + 1, cfg.num_rx)])
            t = cfg.num_tx
            a, b = mag[:-t], mag[t:]
            good = ok[:-t] & ok[t:]
            a = a[good].transpose(0, 2, 1).reshape(-1, s // 2)
            b = b[good].transpose(0, 2, 1).reshape(-1, s // 2)
            a, b = a - a.mean(1, keepdims=True), b - b.mean(1, keepdims=True)
            loopc = float(np.mean((a * b).sum(1) / np.sqrt((a * a).sum(1) * (b * b).sum(1) + 1e-12)))
            rows.append(dict(layout=f"{interleave}/{order}", pos_over_neg=float(pos / neg),
                             rx_corr=float(rxc), loop_corr=loopc))
    return rows


def periodic_disturbances(cube: np.ndarray, cfg: RadarConfig, n_worst: int = 12) -> dict:
    """
    Frame-length evidence that does not depend on the scene moving:
    spacing of all-zero chirps, and where the least coherent same-TX chirp-to-chirp
    transitions fall (slot-0 chirps, 0.2-4 m bins, all RX).
    """
    zeros = find_zero_chirps(cube)
    spacing = sorted(set(np.diff(zeros).tolist())) if zeros.size > 1 else []
    s, t = cfg.num_adc_samples, cfg.num_tx
    x = cube - cube.mean(1, keepdims=True)
    rp = np.fft.fft(x * np.hanning(s)[None, :, None], axis=1)[:, 5 : s // 3, :]
    seq = rp[0::t]
    dead = np.abs(cube[0::t]).reshape(seq.shape[0], -1).max(1) == 0
    a, b = seq[:-1], seq[1:]
    coh = np.abs((a * np.conj(b)).sum((1, 2))) / (
        np.sqrt((np.abs(a) ** 2).sum((1, 2)) * (np.abs(b) ** 2).sum((1, 2))) + 1e-12)
    coh = np.where(dead[:-1] | dead[1:], np.inf, coh)
    worst = np.sort(np.argsort(coh)[:n_worst])
    return {"zero_spacing_chirps": spacing, "worst_transitions_loop_idx": worst.tolist(),
            "worst_mod_loops": sorted(set((worst % cfg.num_loops).tolist()))}


def analyze(bin_path: Path, cfg: RadarConfig, out: Path, max_range_m: float = 4.0) -> str:
    out.mkdir(parents=True, exist_ok=True)
    raw = load_raw_int16(bin_path)
    lines = [f"# Capture check: `{bin_path.name}`", "",
             f"- int16 words: {raw.size}  (min {raw.min()}, max {raw.max()})"]

    # 1. layout
    lines += ["", "## Layout hypotheses (first 960 chirps)", "",
              "| layout (interleave/word order) | E(+f)/E(-f) | RX profile corr | same-TX loop corr |",
              "|---|---|---|---|"]
    for r in layout_scores(raw, cfg):
        lines.append(f"| {r['layout']} | {r['pos_over_neg']:.3g} | {r['rx_corr']:.3f} | {r['loop_corr']:.3f} |")
    lines += ["", "A correct complex layout puts nearly all energy on one side of the spectrum "
              "(complex-1x sampling has image rejection), with the target side in the positive half "
              "under this parser's convention."]

    # 2. parse with the configured layout
    cube = parse_complex_iq_adc(raw, cfg)
    zeros = find_zero_chirps(cube)
    cpf = cfg.resolved_chirps_per_frame()
    pos_in_frame = sorted(set((zeros % cpf).tolist()))
    lines += ["", "## Parsed with the configured layout", "",
              f"- layout: {cfg.iq_interleave} / {cfg.iq_order}; chirps: {cube.shape[0]} "
              f"({cube.shape[0] / cpf:.2f} frames of {cpf})",
              f"- all-zero chirps: {zeros.size}; positions within frame: {pos_in_frame}"]

    # 3. frame-length evidence
    pdist = periodic_disturbances(cube, cfg)
    lines += ["", "## Frame-length evidence", "",
              f"- spacing between all-zero chirps (chirps): {pdist['zero_spacing_chirps']}",
              f"- least coherent same-TX transitions at loop index {pdist['worst_transitions_loop_idx']}"
              f" -> modulo {cfg.num_loops} loops: {pdist['worst_mod_loops']}",
              "- (envelope autocorrelation is not used: any lag that is a multiple of num_tx chirps "
              "scores high on a static scene, so it cannot separate 48/96/192-chirp frames)"]

    cube, dropped = truncate_chirp_cube_to_full_frames(cube, cfg)
    canon, n_filled = framed_tensor(cube, cfg)                        # (F, L, T, R, S)
    nf = canon.shape[0]
    lines.append(f"- full frames used: {nf} (dropped {dropped} tail chirps); filled {n_filled} zero chirps")

    s = cfg.num_adc_samples
    dr = cfg.range_bin_m() or 1.0
    unit = "m" if cfg.range_bin_m() else "bin"
    x = canon - canon.mean(axis=4, keepdims=True)
    rp = np.abs(np.fft.fft(x * np.hanning(s), axis=4))[..., : s // 2]  # (F, L, T, R, bins)
    rng = np.arange(s // 2) * dr
    keep = rng <= max_range_m if unit == "m" else slice(None)

    # 4. mean range profile per RX
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    for r in range(cfg.num_rx):
        ax.plot(rng[keep], 20 * np.log10(rp[:, :, 0, r].mean((0, 1))[keep] + 1e-9), label=f"RX{r}")
    ax.set_xlabel(f"Range ({unit})")
    ax.set_ylabel("dB")
    ax.set_title(f"{bin_path.stem}: mean range profile, TX0 (axis from cfg, not reflector-checked)")
    ax.legend()
    fig.savefig(out / "range_profile.png", dpi=140)
    plt.close(fig)

    # 5. range-time maps
    rt = rp[:, :, 0, 0].mean(1)                                       # (F, bins)
    dyn = np.abs(rt - rt.mean(0, keepdims=True))
    t_ax = np.arange(nf) * (cfg.frame_period_s or 1.0)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for a, img, ttl in ((axs[0], 20 * np.log10(rt[:, keep] + 1e-9), "per-frame range profile (dB)"),
                        (axs[1], dyn[:, keep], "|profile - static mean| (changes / motion)")):
        im = a.imshow(img.T, aspect="auto", origin="lower", cmap="viridis",
                      extent=(t_ax[0], t_ax[-1] if nf > 1 else 1, 0, rng[keep][-1]))
        a.set_xlabel("time (s, from inferred frame period)" if cfg.frame_period_s else "frame")
        a.set_ylabel(f"Range ({unit})")
        a.set_title(ttl)
        fig.colorbar(im, ax=a)
    fig.suptitle(f"{bin_path.stem}: range-time, TX0/RX0")
    fig.savefig(out / "range_time.png", dpi=140)
    plt.close(fig)

    # 6. RD map of the most "dynamic" frame
    fbest = int(dyn[:, keep].sum(1).argmax())
    rd = range_doppler(canon[fbest, :, 0, 0, :])
    save_rd_heatmap(rd, cfg, out / f"rd_frame{fbest}.png",
                    subtitle=f"\n{bin_path.stem}, frame {fbest}, TX0/RX0 (zero chirps filled)",
                    framed=True, max_range_m=max_range_m if unit == "m" else None)
    peak_bin = int(dyn[:, keep].max(0).argmax())
    lines += [f"- strongest change vs. static mean at ~{peak_bin * dr:.2f} {unit}; "
              f"RD figure uses frame {fbest}",
              "", "Figures: `range_profile.png`, `range_time.png`, " f"`rd_frame{fbest}.png`."]

    report = "\n".join(lines) + "\n"
    (out / "report.md").write_text(report, encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin_path", type=Path)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("outputs/analysis"))
    ap.add_argument("--max-range", type=float, default=4.0)
    args = ap.parse_args()
    cfg = load_radar_config_json(args.config)
    sys.stdout.reconfigure(encoding="utf-8")
    print(analyze(args.bin_path, cfg, args.out, args.max_range))


if __name__ == "__main__":
    main()
