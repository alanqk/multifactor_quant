"""Map composite scores to portfolio weights with risk overlays."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mf.risk.constraints import apply_name_cap, apply_sector_cap


def scores_to_weights(
    score: pd.Series,
    tradable: pd.Series,
    *,
    long_pct: float = 0.30,
    weighting: str = "equal",
    max_name_weight: float = 0.10,
    max_sector_weight: float = 0.35,
    min_names: int = 5,
    sector: pd.Series | None = None,
) -> pd.Series:
    s = pd.to_numeric(score, errors="coerce")
    s = s.where(tradable.reindex(s.index).fillna(False)).dropna()
    if s.empty:
        return pd.Series(dtype=float)

    n = max(min_names, int(np.ceil(len(s) * long_pct)))
    n = min(n, len(s))
    top = s.nlargest(n)

    if weighting == "score":
        # shift to positive
        x = top - top.min() + 1e-6
        w = x / x.sum()
    else:
        w = pd.Series(1.0 / len(top), index=top.index)

    w = apply_name_cap(w, max_name_weight)
    w = apply_sector_cap(w, sector, max_sector_weight)
    return w
