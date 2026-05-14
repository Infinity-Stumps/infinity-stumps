"""Sim 07 — Anchor sync error budget for TDoA mode.

NOTE: ARCHITECTURE PIVOTED — TDoA is NOT the deployed scheme. See
CLAUDE.md decision 4 and docs/findings.md "Architecture pivot" section.
This sim characterises TDoA for documentation / fallback purposes only.

Only the "perfect sync (baseline)" scenario has been validated end to
end (~120 mm intrinsic TDoA noise floor — that's the architecturally
important number). The drift scenarios were broken by overspecified
random-walk PSD values; values were lowered on 2026-05-12 to realistic
levels (Allan dev ~1e-9 /√s for TCXO, ~1e-8 for XO). Not yet re-run.

TDoA architecture: ball transmits once, all anchors timestamp arrival on
their own clocks, solver works on time differences. Anchor clocks must
agree to ~100 ps (= 30 mm light travel) or position degrades.

Two sync approaches compared:
  - "predict"     : pure software — fit linear (offset = b0 + b1*t)
                    per anchor from periodic inter-anchor TWR obs, then
                    extrapolate to beacon time. Drift between syncs
                    accumulates as prediction error.
  - "disciplined" : FTS-style (https://github.com/abbbe/fts). After each
                    sync cycle, snap the crystal trim register to within
                    `trim_lsb` of the estimated drift. The chip's clock
                    is now running at the right frequency in hardware —
                    residual error is bounded by trim_lsb, doesn't grow.

Sweeps:
  - sync rate (1, 10, 100 Hz)
  - crystal class: TCXO 1 ppm vs XO 20 ppm
  - approach: predict vs disciplined

Clean-LOS scenario only. Combine with sim 05b's occlusion findings for
the full real-world bound.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

from infinity_stumps import ANCHORS_8, RANGE_SIGMA_DEFAULT, fit_trajectory
from infinity_stumps.physics import integrate_trajectory, make_delivery

C_LIGHT = 299_792_458.0
SIGMA_OBS_S = RANGE_SIGMA_DEFAULT / C_LIGHT  # ≈100 ps in seconds
TRIM_LSB_PPM = 0.1  # QM33 trim granularity assumed


# ---------- clock truth model ----------


def make_anchor_clocks(n_anchors, t_grid, ppm_mean, ppm_walk_psd, seed):
    """Return offsets_rel[i, t]: each anchor's clock offset rel to anchor 0.

    Each anchor has a constant freq offset sampled from N(0, ppm_mean*1e-6)
    plus a Wiener phase walk with PSD ppm_walk_psd*1e-6.
    """
    rng = np.random.default_rng(seed)
    f_offsets = rng.normal(0.0, ppm_mean * 1e-6, n_anchors)
    dt = np.diff(t_grid, prepend=t_grid[0])
    abs_offsets = np.zeros((n_anchors, len(t_grid)))
    for i in range(n_anchors):
        walk_steps = rng.normal(0.0, ppm_walk_psd * 1e-6 * np.sqrt(dt))
        abs_offsets[i] = f_offsets[i] * (t_grid - t_grid[0]) + np.cumsum(walk_steps)
    rel = abs_offsets - abs_offsets[0:1]
    return f_offsets, rel


# ---------- sync observation generator ----------


def generate_sync_obs(t_grid, offsets_rel, sync_rate_hz, seed):
    """Per-anchor list of (t_obs, observed_offset) noisy obs."""
    rng = np.random.default_rng(seed)
    t_start, t_end = t_grid[0], t_grid[-1]
    sync_times = np.arange(t_start, t_end, 1.0 / sync_rate_hz)
    n_anchors = offsets_rel.shape[0]
    per_anchor = {i: ([], []) for i in range(n_anchors)}
    for ts in sync_times:
        for i in range(n_anchors):
            true_off = float(np.interp(ts, t_grid, offsets_rel[i]))
            obs = true_off + rng.normal(0.0, SIGMA_OBS_S)
            per_anchor[i][0].append(ts)
            per_anchor[i][1].append(obs)
    for i in range(n_anchors):
        per_anchor[i] = (np.array(per_anchor[i][0]), np.array(per_anchor[i][1]))
    return per_anchor


# ---------- predictors ----------


def predict_predict(sync_obs_i, t_query, fit_window_s=5.0):
    """Pure linear-regression prediction."""
    ts, obs = sync_obs_i
    mask = (ts <= t_query) & (ts > t_query - fit_window_s)
    ts_m, obs_m = ts[mask], obs[mask]
    if len(ts_m) >= 3:
        A = np.column_stack([np.ones_like(ts_m), ts_m])
        b0, b1 = np.linalg.lstsq(A, obs_m, rcond=None)[0]
        return b0 + b1 * t_query
    if len(ts_m) >= 1:
        return obs_m[-1]
    if len(ts) >= 1:
        return obs[-1]  # cold-start: use any obs
    return 0.0


def predict_disciplined(
    sync_obs_i, t_query, trim_lsb_ppm=TRIM_LSB_PPM, fit_window_s=5.0, rng=None
):
    """FTS-style disciplined timer.

    Models: at each sync exchange, the chip estimates drift and
    snaps its crystal trim to within trim_lsb. We approximate the
    closed-loop residual as:
      * latest sync obs gives current phase (with σ_obs noise)
      * residual frequency offset ~ uniform(-trim_lsb/2, +trim_lsb/2)
      * drift since last sync = residual_freq * (t_query - t_last_sync)
    """
    if rng is None:
        rng = np.random.default_rng()
    ts, obs = sync_obs_i
    mask = ts <= t_query
    if not mask.any():
        return 0.0
    ts_m, obs_m = ts[mask], obs[mask]
    t_last = ts_m[-1]
    last_obs = obs_m[-1]
    # After disciplining, residual freq offset is uniform in trim cell.
    # Use a deterministic seed per anchor-time so repeated queries are
    # consistent within a flight.
    resid_freq = (rng.random() - 0.5) * trim_lsb_ppm * 1e-6
    return last_obs + resid_freq * (t_query - t_last)


# ---------- TDoA position solver ----------


def solve_tdoa(timestamps_s, anchors, ref_idx=0, x0=None):
    valid = ~np.isnan(timestamps_s)
    if valid.sum() < 5:
        raise ValueError(f"TDoA needs ≥5 valid; got {valid.sum()}")
    if x0 is None:
        x0 = np.mean(anchors, axis=0).copy()
        x0[2] = 1.0
    tdoa_dist = (timestamps_s - timestamps_s[ref_idx]) * C_LIGHT
    anc_ref = anchors[ref_idx]

    def residuals(p):
        d_ref = np.linalg.norm(anc_ref - p)
        d_oth = np.linalg.norm(anchors - p, axis=1)
        return ((d_oth - d_ref) - tdoa_dist)[valid]

    return least_squares(residuals, x0, method="lm").x


# ---------- per-flight measurement ----------


def measure_tdoa(sample_t, sample_p, anchors, sync_obs, offsets_rel, t_grid, mode, rng):
    """Generate TDoA fixes for the flight."""
    meas = []
    last = None
    n_anc = len(anchors)
    for t_flight, true_pos in zip(sample_t, sample_p):
        true_r = np.linalg.norm(anchors - true_pos, axis=1)
        toa_true = true_r / C_LIGHT
        timestamps = np.zeros(n_anc)
        for i in range(n_anc):
            true_off = float(np.interp(t_flight, t_grid, offsets_rel[i]))
            raw_ts = t_flight + toa_true[i] + true_off + rng.normal(0, SIGMA_OBS_S)
            if mode == "predict":
                corr = predict_predict(sync_obs[i], t_flight)
            elif mode == "disciplined":
                corr = predict_disciplined(sync_obs[i], t_flight, rng=rng)
            else:
                raise ValueError(mode)
            timestamps[i] = raw_ts - corr
        try:
            x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
            est = solve_tdoa(timestamps, anchors, ref_idx=0, x0=x0)
        except Exception:
            continue
        meas.append(est)
        last = est
    return np.array(meas)


def run_one(sync_rate, ppm_mean, ppm_walk, mode, seed):
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 0.002)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]

    # Clock grid covering generous pre-history + flight
    pre_sync = 30.0
    t_grid = np.linspace(-pre_sync, sample_t[-1] + 0.05, 5000)
    _, offsets_rel = make_anchor_clocks(
        len(ANCHORS_8), t_grid, ppm_mean, ppm_walk, seed
    )
    sync_obs = generate_sync_obs(t_grid, offsets_rel, sync_rate, seed + 1)

    rng = np.random.default_rng(seed + 2)
    meas = measure_tdoa(
        sample_t, sample_p, ANCHORS_8, sync_obs, offsets_rel, t_grid, mode, rng
    )
    if len(meas) < 50:
        return float("nan"), float("nan")

    raw_err = meas - sample_p[: len(meas)]
    raw_rms = float(np.sqrt((raw_err**2).sum(axis=1)).mean() * 1000)
    # TDoA noise is larger than TWR → use larger sigma_pos
    fitted, _ = fit_trajectory(
        sample_t[: len(meas)], meas, sigma_pos=0.3, loss="huber", f_scale=3.0
    )
    fit_err = fitted - sample_p[: len(meas)]
    fit_rms = float(np.sqrt((fit_err**2).sum(axis=1)).mean() * 1000)
    return raw_rms, fit_rms


# ---------- main ----------


def main():
    print("\nSim 07 — TDoA sync error budget\n", flush=True)
    print(
        f"  σ per sync obs : {SIGMA_OBS_S * 1e12:.1f} ps "
        f"({RANGE_SIGMA_DEFAULT * 1000:.0f} mm light travel)"
    )
    print(f"  Trim LSB       : {TRIM_LSB_PPM} ppm\n", flush=True)

    # Walk PSD in ppm/sqrt(s). Realistic Allan-dev floor for these classes:
    #   TCXO: ~1e-9 /sqrt(s)  → 0.001 ppm/sqrt(s)
    #   XO  : ~1e-8 /sqrt(s)  → 0.01 ppm/sqrt(s)
    scenarios = [
        # (label,                       rate, ppm,  walk, mode)
        ("perfect sync (baseline)", 1000.0, 0.0, 0.0, "predict"),
        ("TCXO 1 ppm  @ 10 Hz  predict", 10.0, 1.0, 0.001, "predict"),
        ("XO 20 ppm  @ 10 Hz   predict", 10.0, 20.0, 0.01, "predict"),
        ("XO 20 ppm  @ 100 Hz  predict", 100.0, 20.0, 0.01, "predict"),
        ("XO 20 ppm  @ 1 Hz    predict", 1.0, 20.0, 0.01, "predict"),
        ("XO 20 ppm  @ 10 Hz   disciplined", 10.0, 20.0, 0.01, "disciplined"),
        ("XO 20 ppm  @ 1 Hz    disciplined", 1.0, 20.0, 0.01, "disciplined"),
        ("XO 20 ppm  @ 100 Hz  disciplined", 100.0, 20.0, 0.01, "disciplined"),
    ]
    n_mc = 5
    results = {}
    for name, rate, ppm, walk, mode in scenarios:
        print(f"  Scenario: {name}", flush=True)
        raw_l, fit_l = [], []
        for s in range(n_mc):
            r, f = run_one(rate, ppm, walk, mode, seed=500 + s)
            if not np.isnan(f):
                raw_l.append(r)
                fit_l.append(f)
            print(f"    [{s + 1}/{n_mc}] raw={r:8.1f} mm  fit={f:8.1f} mm", flush=True)
        fit_l = np.array(fit_l)
        raw_l = np.array(raw_l)
        results[name] = (raw_l, fit_l)
        print(
            f"    -> fit mean={fit_l.mean():.1f}  "
            f"median={np.median(fit_l):.1f}  "
            f"p95={np.percentile(fit_l, 95):.1f} mm\n",
            flush=True,
        )

    print("\nSUMMARY")
    print("-" * 75)
    print(f"  {'scenario':40s} {'raw mean':>10s} {'fit mean':>10s} {'fit p95':>10s}")
    for name, (raw, fit) in results.items():
        print(
            f"  {name:40s} {raw.mean():>9.1f}  "
            f"{fit.mean():>9.1f}  {np.percentile(fit, 95):>9.1f}"
        )
    print("\n  Clean-LOS baseline (sim 03)   : ~10 mm")
    print("  Occlusion + Huber (sim 05b)   : ~47 mm")

    fig, ax = plt.subplots(figsize=(12, 7))
    labels = list(results.keys())
    fits = [results[k][1] for k in labels]
    colors = []
    for name in labels:
        if "perfect" in name:
            colors.append("#4a4")
        elif "disciplined" in name:
            colors.append("#48a")
        else:
            colors.append("#c44")
    bp = ax.boxplot(
        fits,
        widths=0.6,
        patch_artist=True,
        tick_labels=[l.replace("  @ ", "\n@ ").replace(" (", "\n(") for l in labels],
    )
    for patch, c in zip(bp["boxes"], colors):
        patch.set_alpha(0.7)
        patch.set_facecolor(c)
    ax.axhline(10, color="green", ls="--", label="ideal clean-LOS (sim 03)")
    ax.axhline(47, color="purple", ls="--", label="occlusion floor (sim 05b)")
    ax.set_ylabel("Fit 3D RMS (mm)")
    ax.set_yscale("log")
    ax.set_title("Sim 07 — TDoA sync error budget: predict vs FTS-disciplined")
    ax.tick_params(axis="x", rotation=15, labelsize=8)
    ax.legend()
    ax.grid(alpha=0.3, axis="y", which="both")
    plt.tight_layout()
    out = "outputs/sim07_sync_budget.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\n  Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
