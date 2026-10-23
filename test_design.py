import pytest

from measurement.design import (
    DesignInputs,
    achievable_user_mde,
    duration_days,
    geo_experiment_power,
    geo_mde_relative,
    recommend_design,
    sample_size_per_arm,
    sensitivity_table,
)


def test_sample_size_matches_reference_value():
    # 5% baseline, 10% relative lift, alpha 0.05, power 0.80 is about 31,200 per arm.
    n = sample_size_per_arm(0.05, 0.10)
    assert 31_000 <= n <= 31_500


def test_smaller_effects_need_more_users():
    assert sample_size_per_arm(0.05, 0.05) > sample_size_per_arm(0.05, 0.10)


def test_lower_baseline_needs_more_users():
    assert sample_size_per_arm(0.02, 0.10) > sample_size_per_arm(0.05, 0.10)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(baseline_rate=0, mde_relative=0.1),
        dict(baseline_rate=1.2, mde_relative=0.1),
        dict(baseline_rate=0.05, mde_relative=0),
        dict(baseline_rate=0.6, mde_relative=1.0),
    ],
)
def test_sample_size_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        sample_size_per_arm(**kwargs)


def test_duration_is_whole_weeks_with_minimum():
    assert duration_days(100, 10_000) == 14
    assert duration_days(500_000, 10_000) % 7 == 0
    assert duration_days(500_000, 10_000) >= 14


def test_achievable_mde_fits_within_window():
    mde = achievable_user_mde(0.03, 20_000, 28)
    assert mde is not None
    n = sample_size_per_arm(0.03, mde)
    assert n <= 20_000 * 28 / 2 * 1.001


def test_geo_power_is_near_target_at_analytic_mde():
    mde = geo_mde_relative(40, 0.06)
    power = geo_experiment_power(40, mde, 0.06, n_sim=6000)
    assert 0.74 <= power <= 0.86


def test_geo_power_grows_with_more_markets():
    low = geo_experiment_power(12, 0.05, 0.06, n_sim=2000)
    high = geo_experiment_power(60, 0.05, 0.06, n_sim=2000)
    assert high > low


def test_too_few_geos_has_no_power():
    assert geo_experiment_power(3, 0.10, 0.05) == 0.0
    assert geo_mde_relative(3, 0.05) == float("inf")


def test_recommends_user_level_when_traffic_is_ample():
    rec = recommend_design(
        DesignInputs(baseline_rate=0.05, mde_relative=0.10, daily_eligible_users=50_000, n_geos=30)
    )
    assert rec.feasible
    assert rec.method == "User-level randomized lift study"


def test_recommends_geo_when_user_randomization_is_unavailable():
    rec = recommend_design(
        DesignInputs(
            baseline_rate=0.05,
            mde_relative=0.08,
            daily_eligible_users=50_000,
            n_geos=60,
            geo_noise_sd=0.04,
            can_randomize_users=False,
        )
    )
    assert rec.feasible
    assert rec.method == "Geo experiment (matched markets)"


def test_reports_infeasible_with_actionable_suggestions():
    rec = recommend_design(
        DesignInputs(
            baseline_rate=0.01,
            mde_relative=0.02,
            daily_eligible_users=2_000,
            n_geos=10,
            geo_noise_sd=0.08,
            max_weeks=4,
        )
    )
    assert not rec.feasible
    assert rec.method == "Not feasible as specified"
    assert rec.suggestions
    assert any("synthetic control" in s for s in rec.suggestions)


def test_signal_loss_increases_requirement_and_raises_risk():
    base = DesignInputs(baseline_rate=0.05, mde_relative=0.10, daily_eligible_users=50_000, n_geos=30)
    lossy = DesignInputs(
        baseline_rate=0.05,
        mde_relative=0.10,
        daily_eligible_users=50_000,
        n_geos=30,
        signal_loss_pct=0.30,
    )
    assert recommend_design(lossy).n_per_arm > recommend_design(base).n_per_arm
    assert any("unobserved" in r for r in recommend_design(lossy).risks)


def test_invalid_design_inputs_raise():
    with pytest.raises(ValueError):
        recommend_design(
            DesignInputs(baseline_rate=0.05, mde_relative=0.1, daily_eligible_users=0, n_geos=10)
        )


def test_sensitivity_table_is_monotonic():
    table = sensitivity_table(
        DesignInputs(baseline_rate=0.05, mde_relative=0.10, daily_eligible_users=20_000, n_geos=30)
    )
    assert table["n_per_arm"].is_monotonic_decreasing
    assert table["geo_power"].iloc[-1] >= table["geo_power"].iloc[0]
