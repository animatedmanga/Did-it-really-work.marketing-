"""Incrementality analysis on geo-level data (Project 2).

Three estimators are provided so that a result can be cross-checked:

1. Difference-in-differences with market and date fixed effects and
   market-clustered standard errors (primary estimator).
2. Synthetic control on the aggregate treated series (robustness check).
3. A regression counterfactual in the spirit of CausalImpact, with a block
   bootstrap interval (robustness check with uncertainty).

The regression counterfactual is a simplified frequentist analogue. It is not
the Bayesian structural time series model used by the CausalImpact package.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import optimize

REQUIRED_COLUMNS = {"geo", "date", "group", "post", "conversions"}


@dataclass
class ImpactResult:
    method: str
    lift: float
    lift_low: float | None
    lift_high: float | None
    incremental_conversions: float
    p_value: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def significant(self) -> bool | None:
        if self.lift_low is None or self.lift_high is None:
            return None
        return self.lift_low > 0 or self.lift_high < 0


def _validate_panel(panel: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(panel.columns)
    if missing:
        raise ValueError(f"Panel is missing columns: {sorted(missing)}")
    if set(panel["group"].unique()) - {"treatment", "control"}:
        raise ValueError("group must contain only 'treatment' and 'control'")
    for group in ("treatment", "control"):
        if panel.loc[panel["group"] == group, "geo"].nunique() < 2:
            raise ValueError(f"At least two {group} markets are required")
    if panel["post"].nunique() < 2:
        raise ValueError("Panel must contain both pre and post period rows")
    if (panel["conversions"] < 0).any():
        raise ValueError("conversions cannot be negative")


def _aggregate(panel: pd.DataFrame) -> pd.DataFrame:
    """Daily totals for treatment and control, plus the post flag."""
    daily = (
        panel.pivot_table(index="date", columns="group", values="conversions", aggfunc="sum")
        .sort_index()
        .rename(columns={"treatment": "treated_total", "control": "control_total"})
    )
    post = panel.groupby("date")["post"].max()
    daily["post"] = post.reindex(daily.index).astype(int)
    return daily


def _regression_design(daily: pd.DataFrame) -> pd.DataFrame:
    """Intercept, control total and day-of-week indicators (Monday is the base)."""
    dow = daily["dow"].astype(pd.CategoricalDtype(categories=list(range(7))))
    dummies = pd.get_dummies(dow, prefix="dow", drop_first=True, dtype=float)
    design = pd.concat(
        [
            pd.Series(1.0, index=daily.index, name="const"),
            daily["control_total"].astype(float),
            dummies,
        ],
        axis=1,
    )
    return design


def difference_in_differences(panel: pd.DataFrame, alpha: float = 0.05) -> ImpactResult:
    """Two-way fixed effects DiD on log conversions with clustered errors."""
    _validate_panel(panel)
    data = panel.copy()
    data["treated_post"] = ((data["group"] == "treatment") & (data["post"] == 1)).astype(int)
    data["log_y"] = np.log1p(data["conversions"].astype(float))
    data["geo"] = data["geo"].astype(str)
    data["date_key"] = data["date"].astype(str)

    model = smf.ols("log_y ~ treated_post + C(geo) + C(date_key)", data=data).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(data["geo"])[0]}
    )
    coef = float(model.params["treated_post"])
    low, high = (float(x) for x in model.conf_int(alpha=alpha).loc["treated_post"])
    p_value = float(model.pvalues["treated_post"])

    lift = float(np.expm1(coef))
    lift_low, lift_high = float(np.expm1(low)), float(np.expm1(high))

    treated_post = data[data["treated_post"] == 1]["conversions"].sum()
    counterfactual = treated_post / (1 + lift)
    return ImpactResult(
        method="Difference-in-differences",
        lift=lift,
        lift_low=lift_low,
        lift_high=lift_high,
        incremental_conversions=float(treated_post - counterfactual),
        p_value=p_value,
        notes=["Log outcome with market and date fixed effects; errors clustered by market."],
    )


def synthetic_control(panel: pd.DataFrame) -> tuple[ImpactResult, pd.DataFrame]:
    """Synthetic control for the aggregate treated series.

    Control markets are weighted (non-negative, summing to one) to reproduce the
    treated market pre-period path. Returns the result and a frame with the
    actual and counterfactual daily series.
    """
    _validate_panel(panel)
    wide = panel.pivot_table(index="date", columns="geo", values="conversions", aggfunc="sum").sort_index()
    groups = panel.drop_duplicates("geo").set_index("geo")["group"]
    post_flag = panel.groupby("date")["post"].max().reindex(wide.index).astype(bool)

    treated_cols = [g for g in wide.columns if groups[g] == "treatment"]
    control_cols = [g for g in wide.columns if groups[g] == "control"]

    y = wide[treated_cols].sum(axis=1)
    donors = wide[control_cols]

    # Scale donors by their pre-period mean so weights act on comparable series.
    pre = ~post_flag
    scale = donors[pre].mean()
    y_pre = y[pre].to_numpy()
    x_pre = (donors[pre] / scale).to_numpy()
    k = x_pre.shape[1]

    def loss(w: np.ndarray) -> float:
        return float(np.sum((y_pre - x_pre @ w * y_pre.mean()) ** 2))

    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    result = optimize.minimize(
        loss,
        x0=np.full(k, 1.0 / k),
        bounds=[(0.0, 1.0)] * k,
        constraints=constraints,
        method="SLSQP",
        options={"maxiter": 500, "ftol": 1e-10},
    )
    weights = np.clip(result.x, 0, None)
    weights = weights / weights.sum()

    synthetic = (donors / scale).to_numpy() @ weights * y_pre.mean()
    series = pd.DataFrame({"actual": y.to_numpy(), "counterfactual": synthetic}, index=wide.index)
    series["post"] = post_flag.to_numpy()

    actual_post = series.loc[series["post"], "actual"].sum()
    cf_post = series.loc[series["post"], "counterfactual"].sum()
    lift = float(actual_post / cf_post - 1)

    pre_mape = float(
        np.mean(np.abs(series.loc[~series["post"], "actual"] - series.loc[~series["post"], "counterfactual"])
                / series.loc[~series["post"], "actual"])
    )
    notes = [f"Pre-period fit error (MAPE): {pre_mape:.1%}."]
    if pre_mape > 0.10:
        notes.append("Pre-period fit is weak. Treat this estimate as directional.")
    if not result.success:
        notes.append("Weight optimization did not fully converge.")

    return (
        ImpactResult(
            method="Synthetic control",
            lift=lift,
            lift_low=None,
            lift_high=None,
            incremental_conversions=float(actual_post - cf_post),
            notes=notes,
        ),
        series,
    )


def regression_counterfactual(
    panel: pd.DataFrame,
    alpha: float = 0.05,
    n_boot: int = 2000,
    block: int = 7,
    seed: int = 0,
) -> tuple[ImpactResult, pd.DataFrame]:
    """Counterfactual from a pre-period regression on control markets.

    Treated daily conversions are regressed on control daily conversions and
    day-of-week indicators using the pre-period. Post-period predictions form
    the counterfactual. The interval combines parameter uncertainty with a
    block bootstrap of pre-period residuals to respect serial correlation.
    """
    _validate_panel(panel)
    daily = _aggregate(panel)
    daily["dow"] = pd.DatetimeIndex(daily.index).dayofweek
    pre = daily[daily["post"] == 0]
    post = daily[daily["post"] == 1]
    if len(pre) < 28:
        raise ValueError("At least 28 pre-period days are required")

    x_all = _regression_design(daily)
    x_pre = x_all.loc[pre.index]
    x_post = x_all.loc[post.index]
    model = sm.OLS(pre["treated_total"].astype(float), x_pre).fit()
    predicted = pd.Series(x_all.to_numpy() @ model.params.to_numpy(), index=daily.index)
    series = pd.DataFrame(
        {"actual": daily["treated_total"], "counterfactual": predicted, "post": daily["post"].astype(bool)}
    )

    actual_post = float(post["treated_total"].sum())
    cf_post = float(predicted[daily["post"] == 1].sum())
    lift = actual_post / cf_post - 1

    rng = np.random.default_rng(seed)
    resid = model.resid.to_numpy()
    n_post = len(post)
    params = rng.multivariate_normal(model.params.to_numpy(), model.cov_params().to_numpy(), size=n_boot)
    cf_sims = x_post.to_numpy() @ params.T  # (n_post, n_boot)

    n_blocks = int(np.ceil(n_post / block))
    starts = rng.integers(0, len(resid) - block + 1, size=(n_boot, n_blocks))
    noise = np.stack(
        [np.concatenate([resid[s : s + block] for s in row])[:n_post] for row in starts], axis=1
    )
    cf_totals = (cf_sims + noise).sum(axis=0)
    lifts = actual_post / cf_totals - 1
    low, high = np.quantile(lifts, [alpha / 2, 1 - alpha / 2])

    r2 = float(model.rsquared)
    notes = [f"Pre-period R-squared: {r2:.2f}."]
    if r2 < 0.5:
        notes.append("Control markets explain little of the pre-period pattern. Interpret with caution.")

    return (
        ImpactResult(
            method="Regression counterfactual",
            lift=float(lift),
            lift_low=float(low),
            lift_high=float(high),
            incremental_conversions=actual_post - cf_post,
            notes=notes,
        ),
        series,
    )


def summarize_incrementality(
    panel: pd.DataFrame,
    value_per_conversion: float | None = None,
    alpha: float = 0.05,
) -> dict:
    """Run all estimators and compute spend-based efficiency metrics."""
    primary = difference_in_differences(panel, alpha=alpha)
    synth, synth_series = synthetic_control(panel)
    reg, reg_series = regression_counterfactual(panel, alpha=alpha)

    spend = float(panel["spend"].sum()) if "spend" in panel.columns else 0.0
    summary: dict = {
        "primary": primary,
        "robustness": [synth, reg],
        "synthetic_series": synth_series,
        "regression_series": reg_series,
        "spend": spend,
        "icpa": None,
        "iroas": None,
        "iroas_low": None,
        "iroas_high": None,
    }

    if spend > 0:
        summary["icpa"] = spend / primary.incremental_conversions if primary.incremental_conversions > 0 else None
        if value_per_conversion:
            def iroas(lift: float) -> float:
                treated_post = panel.loc[(panel["group"] == "treatment") & (panel["post"] == 1), "conversions"].sum()
                incremental = treated_post - treated_post / (1 + lift)
                return incremental * value_per_conversion / spend

            summary["iroas"] = iroas(primary.lift)
            summary["iroas_low"] = iroas(primary.lift_low)
            summary["iroas_high"] = iroas(primary.lift_high)

    # Agreement between estimators, in percentage points of lift.
    others = [r.lift for r in summary["robustness"]]
    summary["max_gap_pts"] = float(max(abs(primary.lift - o) for o in others) * 100)
    return summary
