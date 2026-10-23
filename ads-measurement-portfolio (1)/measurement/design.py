"""Experiment design and feasibility (Project 1).

Given a baseline conversion rate, a minimum detectable effect, available traffic
and the number of markets, this module sizes the test, estimates its duration,
and recommends a method with explicit risks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, sqrt

import numpy as np
import pandas as pd
from scipy import stats

MIN_TEST_DAYS = 14


def _check_rate(name: str, value: float) -> None:
    if not 0 < value < 1:
        raise ValueError(f"{name} must be between 0 and 1 (exclusive)")


def sample_size_per_arm(
    baseline_rate: float,
    mde_relative: float,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Users required in each arm for a two-sided two-proportion z-test."""
    _check_rate("baseline_rate", baseline_rate)
    if mde_relative <= 0:
        raise ValueError("mde_relative must be greater than 0")
    _check_rate("alpha", alpha)
    _check_rate("power", power)

    p1 = baseline_rate
    p2 = baseline_rate * (1 + mde_relative)
    if p2 >= 1:
        raise ValueError("baseline_rate * (1 + mde_relative) must be below 1")

    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    p_bar = (p1 + p2) / 2
    numerator = (
        z_alpha * sqrt(2 * p_bar * (1 - p_bar))
        + z_beta * sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return int(ceil(numerator / (p2 - p1) ** 2))


def duration_days(
    n_per_arm: int,
    daily_eligible_users: float,
    traffic_share: float = 1.0,
    min_days: int = MIN_TEST_DAYS,
) -> int:
    """Test length in days, rounded up to whole weeks to cover weekly cycles."""
    if daily_eligible_users <= 0:
        raise ValueError("daily_eligible_users must be greater than 0")
    if not 0 < traffic_share <= 1:
        raise ValueError("traffic_share must be in (0, 1]")
    per_arm_daily = daily_eligible_users * traffic_share / 2
    days = max(int(ceil(n_per_arm / per_arm_daily)), min_days)
    return int(ceil(days / 7) * 7)


def achievable_user_mde(
    baseline_rate: float,
    daily_eligible_users: float,
    max_days: int,
    alpha: float = 0.05,
    power: float = 0.80,
) -> float | None:
    """Smallest relative effect detectable within max_days, or None if none exists."""
    _check_rate("baseline_rate", baseline_rate)
    per_arm_cap = daily_eligible_users * max_days / 2
    upper = min(5.0, 0.999 / baseline_rate - 1)
    if upper <= 0:
        return None
    if sample_size_per_arm(baseline_rate, upper, alpha, power) > per_arm_cap:
        return None
    lower = 1e-4
    for _ in range(60):
        mid = (lower + upper) / 2
        if sample_size_per_arm(baseline_rate, mid, alpha, power) <= per_arm_cap:
            upper = mid
        else:
            lower = mid
    return float(upper)


def geo_mde_relative(
    n_geos: int,
    geo_noise_sd: float,
    alpha: float = 0.05,
    power: float = 0.80,
    treat_share: float = 0.5,
) -> float:
    """Approximate minimum detectable relative lift for a geo experiment.

    geo_noise_sd is the standard deviation of a market's log change in outcome
    between the pre and test periods when no treatment is applied.
    """
    if geo_noise_sd <= 0:
        raise ValueError("geo_noise_sd must be greater than 0")
    n_treat = int(round(n_geos * treat_share))
    n_control = n_geos - n_treat
    if n_treat < 2 or n_control < 2:
        return float("inf")
    df = n_geos - 2
    multiplier = stats.t.ppf(1 - alpha / 2, df) + stats.t.ppf(power, df)
    se = geo_noise_sd * sqrt(1 / n_treat + 1 / n_control)
    return float(np.expm1(multiplier * se))


def geo_experiment_power(
    n_geos: int,
    mde_relative: float,
    geo_noise_sd: float,
    treat_share: float = 0.5,
    alpha: float = 0.05,
    n_sim: int = 4000,
    seed: int = 0,
) -> float:
    """Simulated power of a Welch t-test on market-level log changes."""
    n_treat = int(round(n_geos * treat_share))
    n_control = n_geos - n_treat
    if n_treat < 2 or n_control < 2:
        return 0.0
    rng = np.random.default_rng(seed)
    effect = np.log1p(mde_relative)
    treated = rng.normal(effect, geo_noise_sd, size=(n_sim, n_treat))
    control = rng.normal(0.0, geo_noise_sd, size=(n_sim, n_control))
    p_values = stats.ttest_ind(treated, control, axis=1, equal_var=False).pvalue
    return float(np.mean(p_values < alpha))


@dataclass(frozen=True)
class DesignInputs:
    baseline_rate: float
    mde_relative: float
    daily_eligible_users: int
    n_geos: int
    geo_noise_sd: float = 0.06
    can_randomize_users: bool = True
    max_weeks: int = 6
    signal_loss_pct: float = 0.0
    alpha: float = 0.05
    power: float = 0.80


@dataclass
class DesignOption:
    name: str
    feasible: bool
    detail: str


@dataclass
class DesignRecommendation:
    method: str
    feasible: bool
    rationale: str
    n_per_arm: int
    duration_days: int
    geo_mde_relative: float
    geo_power_at_target: float
    options: list[DesignOption] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _validate(inp: DesignInputs) -> None:
    _check_rate("baseline_rate", inp.baseline_rate)
    if inp.mde_relative <= 0:
        raise ValueError("mde_relative must be greater than 0")
    if inp.daily_eligible_users <= 0:
        raise ValueError("daily_eligible_users must be greater than 0")
    if inp.n_geos < 0:
        raise ValueError("n_geos cannot be negative")
    if not 0 <= inp.signal_loss_pct < 1:
        raise ValueError("signal_loss_pct must be in [0, 1)")
    if inp.max_weeks < 1:
        raise ValueError("max_weeks must be at least 1")


def recommend_design(inp: DesignInputs) -> DesignRecommendation:
    """Recommend a test method and report the constraints that drive the choice."""
    _validate(inp)

    effective_rate = inp.baseline_rate * (1 - inp.signal_loss_pct)
    n_per_arm = sample_size_per_arm(effective_rate, inp.mde_relative, inp.alpha, inp.power)
    days = duration_days(n_per_arm, inp.daily_eligible_users)
    max_days = inp.max_weeks * 7

    geo_mde = geo_mde_relative(inp.n_geos, inp.geo_noise_sd, inp.alpha, inp.power)
    geo_power = geo_experiment_power(
        inp.n_geos, inp.mde_relative, inp.geo_noise_sd, alpha=inp.alpha
    )

    user_ok = inp.can_randomize_users and days <= max_days
    geo_ok = inp.n_geos >= 20 and geo_mde <= inp.mde_relative

    user_detail = (
        f"Needs {n_per_arm:,} users per arm, about {days} days at current traffic "
        f"(limit {max_days} days)."
    )
    if not inp.can_randomize_users:
        user_detail = "User-level randomization is not available for this campaign."
    geo_detail = (
        f"{inp.n_geos} markets give a minimum detectable lift of {geo_mde:.1%} "
        f"(target {inp.mde_relative:.1%}); simulated power at target is {geo_power:.0%}."
        if np.isfinite(geo_mde)
        else "Too few markets to form treatment and control groups."
    )
    options = [
        DesignOption("User-level randomized lift study", user_ok, user_detail),
        DesignOption("Geo experiment (matched markets)", geo_ok, geo_detail),
        DesignOption(
            "Pre/post with synthetic control (observational)",
            True,
            "Always possible, but the estimate rests on modelling assumptions. "
            "Use only when randomization is not available.",
        ),
    ]

    risks: list[str] = []
    suggestions: list[str] = []

    if user_ok:
        method = "User-level randomized lift study"
        rationale = (
            "Randomizing at user level gives the cleanest causal estimate and the "
            "traffic is sufficient to reach the target effect within the allowed window."
        )
    elif geo_ok:
        method = "Geo experiment (matched markets)"
        rationale = (
            "User-level testing is unavailable or too slow at current traffic. "
            "The available markets can detect the target effect, so a matched-market "
            "geo experiment is the most credible design."
        )
    else:
        method = "Not feasible as specified"
        reasons = []
        if inp.can_randomize_users:
            reasons.append(
                f"user-level testing needs about {days} days against a {max_days} day limit"
            )
        else:
            reasons.append("user-level randomization is not available")
        if np.isfinite(geo_mde):
            reasons.append(
                f"the geo design can only detect {geo_mde:.1%} with {inp.n_geos} markets"
            )
        else:
            reasons.append("there are too few markets for a geo design")
        rationale = "The target effect cannot be measured reliably because " + " and ".join(reasons) + "."

        achievable = achievable_user_mde(
            effective_rate, inp.daily_eligible_users, max_days, inp.alpha, inp.power
        )
        if inp.can_randomize_users and achievable is not None:
            suggestions.append(
                f"Raise the target effect to {achievable:.1%} or more to fit a {max_days} day user-level test."
            )
        if inp.can_randomize_users:
            suggestions.append(f"Allow {ceil(days / 7)} weeks to test the current target effect.")
        if np.isfinite(geo_mde) and geo_mde > inp.mde_relative:
            suggestions.append(
                f"Raise the target effect to {geo_mde:.1%} or more, or add markets, to use a geo design."
            )
        suggestions.append(
            "If neither is possible, use a synthetic control analysis and label the result as directional."
        )

    if days > max_days and inp.can_randomize_users:
        risks.append(f"Required duration of {days} days exceeds the {max_days} day limit.")
    if inp.signal_loss_pct >= 0.20:
        risks.append(
            f"{inp.signal_loss_pct:.0%} of conversions are unobserved. This inflates required sample size "
            "and can bias results if the loss differs by group."
        )
    if inp.mde_relative < 0.02:
        risks.append("Effects below 2% are difficult to separate from normal volatility.")
    if inp.n_geos and inp.n_geos < 20:
        risks.append("Fewer than 20 markets leaves a geo design sensitive to a single outlier market.")
    if inp.geo_noise_sd > 0.10:
        risks.append("High market-level volatility reduces geo experiment power. Consider covariate adjustment.")
    if days < 21:
        risks.append("A short test may miss the full conversion delay. Check the typical time to convert.")
    risks.append("Fix the analysis plan and end date in advance. Early peeking inflates false positives.")

    return DesignRecommendation(
        method=method,
        feasible=user_ok or geo_ok,
        rationale=rationale,
        n_per_arm=n_per_arm,
        duration_days=days,
        geo_mde_relative=geo_mde,
        geo_power_at_target=geo_power,
        options=options,
        risks=risks,
        suggestions=suggestions,
    )


def sensitivity_table(inp: DesignInputs, mdes: list[float] | None = None) -> pd.DataFrame:
    """Sample size, duration and geo power across a range of target effects."""
    _validate(inp)
    if mdes is None:
        mdes = [0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20]
    effective_rate = inp.baseline_rate * (1 - inp.signal_loss_pct)
    rows = []
    for mde in mdes:
        if effective_rate * (1 + mde) >= 1:
            continue
        n = sample_size_per_arm(effective_rate, mde, inp.alpha, inp.power)
        rows.append(
            {
                "target_lift": mde,
                "n_per_arm": n,
                "duration_days": duration_days(n, inp.daily_eligible_users),
                "geo_power": geo_experiment_power(
                    inp.n_geos, mde, inp.geo_noise_sd, alpha=inp.alpha, n_sim=1500
                ),
            }
        )
    return pd.DataFrame(rows)
