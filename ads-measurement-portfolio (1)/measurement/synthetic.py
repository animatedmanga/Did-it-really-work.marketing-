"""Synthetic data generators.

The geo panel simulates a campaign launched in treatment markets during a test
window, with matched control markets that receive no campaign. Because the true
lift is a parameter, every estimator in this repository can be validated against
a known answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Day-of-week multipliers, Monday first. The default panel starts on a Monday.
DOW_PATTERN = np.array([0.94, 0.97, 1.00, 1.02, 1.06, 1.10, 0.91])


def make_geo_panel(
    n_geos: int = 40,
    n_days: int = 112,
    test_start_day: int = 84,
    true_lift: float = 0.06,
    noise_sd: float = 0.04,
    seed: int = 7,
    start_date: str = "2026-01-05",
    spend_per_baseline_conversion: float = 1.8,
) -> pd.DataFrame:
    """Return a daily geo-level panel with a known treatment effect.

    Treatment markets are assigned by pairing markets of similar size and
    randomizing within each pair, which mirrors matched-market practice.

    Columns: geo, date, day_index, group, treated, post, treated_post,
    conversions, spend.
    """
    if n_geos < 4 or n_geos % 2:
        raise ValueError("n_geos must be an even number of at least 4")
    if not 0 < test_start_day < n_days:
        raise ValueError("test_start_day must fall inside the date range")
    if true_lift <= -1:
        raise ValueError("true_lift must be greater than -1")

    rng = np.random.default_rng(seed)
    scale = rng.lognormal(mean=np.log(600.0), sigma=0.55, size=n_geos)

    order = np.argsort(scale)
    treated = np.zeros(n_geos, dtype=bool)
    for i in range(0, n_geos, 2):
        treated[order[i + rng.integers(2)]] = True

    days = np.arange(n_days)
    dow = DOW_PATTERN[days % 7]
    trend = 1.0 + 0.0006 * days

    shock = np.zeros(n_days)
    eps = rng.normal(0.0, 0.02, n_days)
    for t in range(1, n_days):
        shock[t] = 0.6 * shock[t - 1] + eps[t]

    geo_slope = rng.normal(0.0, 0.0002, n_geos)
    dates = pd.date_range(start_date, periods=n_days, freq="D")
    post = days >= test_start_day

    frames = []
    for g in range(n_geos):
        base = scale[g] * dow * trend * np.exp(shock + geo_slope[g] * days)
        applied_lift = np.where(treated[g] & post, 1.0 + true_lift, 1.0)
        noise = np.exp(rng.normal(0.0, noise_sd, n_days))
        conversions = rng.poisson(base * applied_lift * noise)
        spend = np.where(
            treated[g] & post,
            scale[g] * spend_per_baseline_conversion * rng.lognormal(0.0, 0.05, n_days),
            0.0,
        )
        frames.append(
            pd.DataFrame(
                {
                    "geo": f"geo_{g + 1:02d}",
                    "date": dates,
                    "day_index": days,
                    "group": "treatment" if treated[g] else "control",
                    "treated": int(treated[g]),
                    "post": post.astype(int),
                    "treated_post": (treated[g] & post).astype(int),
                    "conversions": conversions.astype(int),
                    "spend": spend.round(2),
                }
            )
        )

    panel = pd.concat(frames, ignore_index=True)
    panel.attrs["true_lift"] = true_lift
    panel.attrs["test_start_day"] = test_start_day
    return panel
