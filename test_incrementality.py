import pandas as pd
import pytest

from measurement.incrementality import (
    difference_in_differences,
    regression_counterfactual,
    summarize_incrementality,
    synthetic_control,
)
from measurement.synthetic import make_geo_panel


@pytest.fixture(scope="module")
def panel():
    return make_geo_panel(true_lift=0.06, seed=7)


def test_panel_structure(panel):
    assert panel["geo"].nunique() == 40
    assert set(panel["group"]) == {"treatment", "control"}
    assert panel.groupby("group")["geo"].nunique().nunique() == 1  # balanced groups
    assert panel.loc[panel["post"] == 0, "spend"].sum() == 0
    assert panel.attrs["true_lift"] == 0.06


def test_did_recovers_true_lift_within_interval(panel):
    res = difference_in_differences(panel)
    assert res.lift_low <= 0.06 <= res.lift_high
    assert abs(res.lift - 0.06) < 0.025
    assert res.significant


def test_did_reports_no_effect_when_none_exists():
    flat = make_geo_panel(true_lift=0.0, seed=11)
    res = difference_in_differences(flat)
    assert res.lift_low <= 0.0 <= res.lift_high
    assert not res.significant


def test_synthetic_control_is_close_to_truth(panel):
    res, series = synthetic_control(panel)
    assert abs(res.lift - 0.06) < 0.04
    assert {"actual", "counterfactual", "post"} <= set(series.columns)
    assert res.lift_low is None


def test_regression_counterfactual_covers_truth(panel):
    res, _ = regression_counterfactual(panel)
    assert res.lift_low <= 0.06 <= res.lift_high


def test_summary_includes_efficiency_metrics(panel):
    out = summarize_incrementality(panel, value_per_conversion=80.0)
    # True iROAS is lift * value / spend-per-baseline-conversion, about 0.06 * 80 / 1.8 = 2.67.
    assert 1.5 < out["iroas"] < 4.0
    assert out["iroas_low"] < out["iroas"] < out["iroas_high"]
    assert out["icpa"] > 0
    assert out["max_gap_pts"] < 4.0


def test_summary_without_value_skips_roas(panel):
    out = summarize_incrementality(panel)
    assert out["iroas"] is None
    assert out["spend"] > 0


def test_validation_errors():
    with pytest.raises(ValueError, match="missing columns"):
        difference_in_differences(pd.DataFrame({"geo": ["a"]}))
    bad = make_geo_panel()
    bad["group"] = "treatment"
    with pytest.raises(ValueError, match="control"):
        difference_in_differences(bad)
    neg = make_geo_panel()
    neg.loc[0, "conversions"] = -1
    with pytest.raises(ValueError, match="negative"):
        difference_in_differences(neg)


def test_interval_coverage_across_seeds():
    # With a 95% interval, truth should be covered in most replications.
    covered = 0
    runs = 12
    for seed in range(100, 100 + runs):
        res = difference_in_differences(make_geo_panel(true_lift=0.05, seed=seed))
        covered += res.lift_low <= 0.05 <= res.lift_high
    assert covered >= runs - 2
