"""Combine factor ranks into a composite score."""

from __future__ import annotations

import pandas as pd


def combine_factors(
    factors: dict[str, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Equal-weight (or custom) average of CS rank panels. Missing factors skipped per date/name."""
    if not factors:
        raise ValueError("No factors to combine")
    weights = weights or {k: 1.0 / len(factors) for k in factors}
    # normalize over available keys
    keys = [k for k in factors if k in weights]
    wsum = sum(weights[k] for k in keys)
    acc = None
    w_acc = None
    for k in keys:
        f = factors[k]
        w = weights[k] / wsum
        piece = f * w
        mask = f.notna().astype(float) * w
        acc = piece if acc is None else acc.add(piece, fill_value=0)
        w_acc = mask if w_acc is None else w_acc.add(mask, fill_value=0)
    out = acc.div(w_acc.replace(0, float("nan")))
    return out.astype(float)
