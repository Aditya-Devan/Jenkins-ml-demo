"""Synthetic dataset generator. Fixed seed => reproducible builds.
(trigger test: this comment change should start a build by itself)

The `label_noise` knob in train_config.json is the break-lever:
  0.05 simulates a normal data batch  -> accuracy ~0.95 (gate passes)
  0.4  simulates a corrupted batch    -> accuracy ~0.55 (gate FAILS)

ML CI lesson: the training config is a build input, so it lives in git.
"""
import json

import numpy as np

SEED = 42
N_TRAIN = 800
N_TEST = 200  # held-out samples used by evaluate.py


def load_config(path="train_config.json"):
    with open(path) as f:
        return json.load(f)


def make_dataset():
    cfg = load_config()
    noise = float(cfg.get("label_noise", 0.05))

    rng = np.random.default_rng(SEED)
    n = N_TRAIN + N_TEST

    # two features; true class = which side of the line x1 + x2 = 0
    X = rng.normal(0.0, 1.0, size=(n, 2))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)

    # simulate labeling-quality problems in the data batch
    flip = rng.random(n) < noise
    y = np.where(flip, 1 - y, y)

    return (X[:N_TRAIN], y[:N_TRAIN]), (X[N_TRAIN:], y[N_TRAIN:])
