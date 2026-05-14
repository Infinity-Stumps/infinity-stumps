"""Sim ML — fit initializer + per-timestep corrector for tail reduction.

Adds two learned components on top of sim_realistic, both designed to
collapse the tail of the error distribution at 100 Hz:

  #3 fit_initializer  — MLP mapping first 10 raw multilat samples
     (40 features) to (release_pos, v0, spin). Seeds the physics LM
     in the correct basin so it can't wander into a bad local min.
     This alone would have killed the 619 mm outlier seen in n=6.

  #2 corrector        — MLP mapping per-timestep features
     (raw multilat xyz, 8 ranges, valid mask, first-pass residuals
     = 27 features) to (Δx, Δy, Δz). Applied BEFORE the physics fit
     so the global consistency guarantee from drag+Magnus+gravity
     still holds.

Same 100 Hz protocol as sim_realistic, evaluated on the same
30 seeds (1500..1529) so before/after is a like-for-like comparison.

Training data is generated with multiprocessing. Models and data are
cached to outputs/ so re-running is fast.
"""

from __future__ import annotations
import argparse
import multiprocessing as mp
from pathlib import Path

import joblib
import numpy as np
import matplotlib.pyplot as plt
from sklearn.compose import TransformedTargetRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from cricket_uwb import (ANCHORS_8, RANGE_SIGMA_DEFAULT,
                          solve_position, fit_trajectory)
from cricket_uwb.physics import integrate_trajectory, make_delivery
from cricket_uwb.skeleton import (sample_batter, Bone,
                                    line_bone_chord_length,
                                    CHORD_BLOCK_THRESHOLD_M)

# Re-use the realistic occluder + measurement model verbatim.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from sim_realistic import (  # noqa: E402
    static_bones_realistic, bowler_bones_realistic, measure,
    HUBER_FSCALE, UWB_RATE_HZ,
)

N_TRAIN_DELIVERIES = 500
N_INIT_SAMPLES = 10
EVAL_SEEDS = list(range(1500, 1530))
DATA_CACHE = Path("outputs/sim_ml_traindata.npz")
MODEL_CACHE = Path("outputs/sim_ml_models.joblib")


# ---------- training data generation ----------

def simulate_one_delivery(seed: int):
    """One delivery — returns truth params + per-sample raw observations.

    All physics params are randomised so the initializer has real
    variance to learn across all 9 output dims. (With fixed params
    6 of 9 outputs have zero variance and StandardScaler explodes.)
    """
    rng = np.random.default_rng(seed)
    speed = float(rng.uniform(28.0, 42.0))
    release_h = float(rng.uniform(2.10, 2.50))
    release_x = float(rng.uniform(-9.5, -8.0))
    release_y = float(rng.uniform(-0.3, 0.5))
    ang_h = float(rng.uniform(-3.0, 3.0))
    ang_v = float(rng.uniform(3.0, 9.0))
    spin_axis = rng.normal(size=3)  # random orientation
    spin_rps = float(rng.uniform(15.0, 35.0))
    rp, v0, spin = make_delivery(
        speed_mps=speed,
        release_height=release_h,
        release_x=release_x,
        release_y=release_y,
        angle_horizontal_deg=ang_h,
        angle_vertical_deg=ang_v,
        spin_axis=spin_axis,
        spin_rev_per_sec=spin_rps,
    )
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 1.0 / UWB_RATE_HZ)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]

    static = static_bones_realistic(rng)
    last = None
    times, true_xyz, raw_xyz, rng_arr = [], [], [], []
    for t, true_pos in zip(sample_t, sample_p):
        bones = static + bowler_bones_realistic(t)
        ranges = measure(true_pos, ANCHORS_8, bones, rng)
        if (~np.isnan(ranges)).sum() < 4:
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, ANCHORS_8, x0)
        except Exception:
            continue
        times.append(t)
        true_xyz.append(true_pos)
        raw_xyz.append(est)
        rng_arr.append(ranges)
        last = est
    if len(times) < N_INIT_SAMPLES + 5:
        return None
    return {
        "release": np.asarray(rp, dtype=np.float64),
        "v0": np.asarray(v0, dtype=np.float64),
        "spin": np.asarray(spin, dtype=np.float64),
        "t": np.asarray(times, dtype=np.float64),
        "true_xyz": np.asarray(true_xyz, dtype=np.float64),
        "raw_xyz": np.asarray(raw_xyz, dtype=np.float64),
        "ranges": np.asarray(rng_arr, dtype=np.float64),  # NaN preserved
    }


def generate_training_data(n: int, workers: int):
    seeds = list(range(10_000, 10_000 + n))
    print(f"Generating {n} training deliveries with {workers} workers...",
          flush=True)
    out = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(simulate_one_delivery,
                                                  seeds, chunksize=4)):
            if r is not None:
                out.append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{n}  kept={len(out)}", flush=True)
    print(f"Kept {len(out)}/{n} deliveries", flush=True)
    return out


# ---------- featurization ----------

def featurize(deliveries):
    X_init, y_init = [], []
    X_corr, y_corr = [], []
    for d in deliveries:
        n = len(d["t"])
        if n < N_INIT_SAMPLES:
            continue
        # --- initializer features: first N (t, x, y, z)
        feat_i = np.empty(N_INIT_SAMPLES * 4)
        for k in range(N_INIT_SAMPLES):
            feat_i[4*k] = d["t"][k]
            feat_i[4*k+1:4*k+4] = d["raw_xyz"][k]
        X_init.append(feat_i)
        y_init.append(np.concatenate([d["release"], d["v0"], d["spin"]]))
        # --- corrector features: per-timestep
        valid = (~np.isnan(d["ranges"])).astype(np.float64)
        rng_filled = np.where(valid > 0, d["ranges"], 0.0)
        # First-pass residuals: ||A - raw|| - r, masked
        dists = np.linalg.norm(ANCHORS_8[None, :, :]
                               - d["raw_xyz"][:, None, :], axis=2)
        resid = (dists - rng_filled) * valid
        for k in range(n):
            feat_c = np.concatenate([
                d["raw_xyz"][k],   # 3
                rng_filled[k],     # 8
                valid[k],          # 8
                resid[k],          # 8
            ])
            X_corr.append(feat_c)
            y_corr.append(d["true_xyz"][k] - d["raw_xyz"][k])
    return (np.asarray(X_init), np.asarray(y_init),
            np.asarray(X_corr), np.asarray(y_corr))


# ---------- training ----------

def train_models(X_init, y_init, X_corr, y_corr):
    # Initializer outputs span very different scales (pos ~10 m, v0 ~30,
    # spin ~50), so wrap with TransformedTargetRegressor + StandardScaler
    # to also normalise the targets — otherwise spin loss dominates.
    sc_i = StandardScaler(); X_init_s = sc_i.fit_transform(X_init)
    inner_i = MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=400,
                            early_stopping=True, validation_fraction=0.15,
                            random_state=0, verbose=False)
    init_mdl = TransformedTargetRegressor(regressor=inner_i,
                                           transformer=StandardScaler())
    print("Training initializer...", flush=True)
    init_mdl.fit(X_init_s, y_init)
    print(f"  Init   R²={init_mdl.score(X_init_s, y_init):.3f}  "
          f"iters={init_mdl.regressor_.n_iter_}", flush=True)

    # Corrector targets are well-scaled (deltas ~cm), no wrapper needed.
    sc_c = StandardScaler(); X_corr_s = sc_c.fit_transform(X_corr)
    corr_mdl = MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=200,
                            early_stopping=True, validation_fraction=0.15,
                            random_state=0, verbose=False)
    print("Training corrector...", flush=True)
    corr_mdl.fit(X_corr_s, y_corr)
    print(f"  Corr   R²={corr_mdl.score(X_corr_s, y_corr):.3f}  "
          f"iters={corr_mdl.n_iter_}", flush=True)
    return {"init": (sc_i, init_mdl), "corr": (sc_c, corr_mdl)}


# ---------- evaluation ----------

def run_one(seed: int, models: dict | None = None):
    rng = np.random.default_rng(seed)
    rp, v0, spin = make_delivery(speed_mps=38.0)
    ts, st = integrate_trajectory(rp, v0, spin)
    sample_t = np.arange(0.01, ts[-1] - 0.01, 1.0 / UWB_RATE_HZ)
    idx = np.clip(np.searchsorted(ts, sample_t), 0, len(ts) - 1)
    sample_p = st[idx, :3]
    static = static_bones_realistic(rng)

    times, raw_p, rng_arr = [], [], []
    last = None
    n_total = n_blocked = 0
    for t, true_pos in zip(sample_t, sample_p):
        bones = static + bowler_bones_realistic(t)
        ranges = measure(true_pos, ANCHORS_8, bones, rng)
        n_total += len(ranges)
        n_blocked += int(np.isnan(ranges).sum())
        if (~np.isnan(ranges)).sum() < 4:
            continue
        x0 = (true_pos + rng.normal(0, 0.05, 3)) if last is None else last
        try:
            est = solve_position(ranges, ANCHORS_8, x0)
        except Exception:
            continue
        times.append(t); raw_p.append(est); rng_arr.append(ranges); last = est

    if len(times) < 20:
        return float("nan")
    times = np.asarray(times); raw_p = np.asarray(raw_p)
    rng_arr = np.asarray(rng_arr)

    # Corrector: nudge raw positions BEFORE the physics fit.
    if models and "corr" in models:
        sc, mdl = models["corr"]
        valid = (~np.isnan(rng_arr)).astype(np.float64)
        rng_f = np.where(valid > 0, rng_arr, 0.0)
        dists = np.linalg.norm(ANCHORS_8[None, :, :]
                               - raw_p[:, None, :], axis=2)
        resid = (dists - rng_f) * valid
        feats = np.concatenate([raw_p, rng_f, valid, resid], axis=1)
        delta = mdl.predict(sc.transform(feats))
        pos_in = raw_p + delta
    else:
        pos_in = raw_p

    # Initializer: seed for the physics LM.
    x0_fit = None
    if models and "init" in models and len(times) >= N_INIT_SAMPLES:
        sc, mdl = models["init"]
        feat_i = np.empty(N_INIT_SAMPLES * 4)
        for k in range(N_INIT_SAMPLES):
            feat_i[4*k] = times[k]
            feat_i[4*k+1:4*k+4] = pos_in[k]
        x0_fit = mdl.predict(sc.transform(feat_i.reshape(1, -1)))[0]

    idx_m = np.clip(np.searchsorted(ts, times), 0, len(ts) - 1)
    truth_m = st[idx_m, :3]
    fitted, _ = fit_trajectory(times, pos_in, loss="huber",
                                 f_scale=HUBER_FSCALE, x0=x0_fit)
    err = fitted - truth_m
    return float(np.sqrt((err**2).sum(axis=1)).mean() * 1000)


# ---------- parallel eval helpers ----------
# Using fork mode: children inherit the parent's loaded models via COW,
# avoiding the 11s/worker joblib.load and the simultaneous-mmap-load
# race that deadlocked spawn mode.

_EVAL_CFGS: dict | None = None


def _set_eval_cfgs(cfgs):
    global _EVAL_CFGS
    _EVAL_CFGS = cfgs


def _eval_worker(task):
    seed, cfg_name = task
    m = _EVAL_CFGS[cfg_name]
    return cfg_name, run_one(seed, m)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=N_TRAIN_DELIVERIES)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--retrain", action="store_true")
    args = ap.parse_args()

    Path("outputs").mkdir(exist_ok=True)

    if DATA_CACHE.exists() and not args.regen:
        print(f"Loading cached training data from {DATA_CACHE}", flush=True)
        d = np.load(DATA_CACHE)
        X_init, y_init = d["X_init"], d["y_init"]
        X_corr, y_corr = d["X_corr"], d["y_corr"]
    else:
        deliveries = generate_training_data(args.n_train, args.workers)
        X_init, y_init, X_corr, y_corr = featurize(deliveries)
        np.savez_compressed(DATA_CACHE,
                            X_init=X_init, y_init=y_init,
                            X_corr=X_corr, y_corr=y_corr)
    print(f"  Init set: {X_init.shape} -> {y_init.shape}", flush=True)
    print(f"  Corr set: {X_corr.shape} -> {y_corr.shape}", flush=True)

    if MODEL_CACHE.exists() and not args.retrain:
        print(f"Loading cached models from {MODEL_CACHE}", flush=True)
        models = joblib.load(MODEL_CACHE)
    else:
        models = train_models(X_init, y_init, X_corr, y_corr)
        joblib.dump(models, MODEL_CACHE)

    print(f"\nEvaluating on n=30 seeds (1500..1529), {args.workers} workers...",
          flush=True)
    cfgs = {
        "baseline":  None,
        "init only": {"init": models["init"]},
        "corr only": {"corr": models["corr"]},
        "init+corr": models,
    }
    # Flatten (seed, cfg_name) tasks for one big parallel pass.
    # Fork mode: load models once in the parent, children inherit via COW.
    _set_eval_cfgs(cfgs)
    all_tasks = [(s, name) for name in cfgs for s in EVAL_SEEDS]
    ctx = mp.get_context("fork")
    with ctx.Pool(args.workers) as pool:
        results_raw = list(pool.imap_unordered(_eval_worker, all_tasks,
                                                chunksize=2))
    # Aggregate.
    by_cfg: dict = {name: [] for name in cfgs}
    for name, r in results_raw:
        if not np.isnan(r):
            by_cfg[name].append(r)
    results = {name: np.asarray(v) for name, v in by_cfg.items()}
    for name in cfgs:
        r = results[name]
        print(f"  {name:10s}  mean={r.mean():>6.1f}  "
              f"med={np.median(r):>6.1f}  "
              f"p95={np.percentile(r, 95):>6.1f}  "
              f"max={r.max():>6.1f}  (n={len(r)})", flush=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    labels = list(results.keys())
    data = [results[k] for k in labels]
    bp = ax.boxplot(data, widths=0.6, patch_artist=True, tick_labels=labels)
    for patch, c in zip(bp["boxes"], ["#888", "#4a8", "#48a", "#8a4"]):
        patch.set_alpha(0.7); patch.set_facecolor(c)
    ax.set_ylabel("Fit 3D RMS (mm) @ 100 Hz")
    ax.set_title("Sim ML — physics fit + learned init + learned corrector")
    ax.grid(alpha=0.3, axis="y")
    plt.tight_layout()
    out = "outputs/sim_ml.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\nSaved: {out}", flush=True)


if __name__ == "__main__":
    main()
