import pytest
import requests

from measurement.incrementality import summarize_incrementality
from measurement.readout import (
    ReadoutContext,
    build_readout,
    decide,
    numbers_preserved,
    polish_with_llm,
)
from measurement.synthetic import make_geo_panel


@pytest.fixture(scope="module")
def summary():
    return summarize_incrementality(make_geo_panel(true_lift=0.06, seed=7), value_per_conversion=80.0)


def ctx(**overrides):
    base = dict(
        test_name="Search holdout test",
        objective="The test measured the conversions caused by a new Search campaign.",
        n_treatment_geos=20,
        n_control_geos=20,
        start_date="2026-03-30",
        end_date="2026-04-26",
        test_days=28,
        breakeven_roas=2.0,
        value_per_conversion=80.0,
    )
    base.update(overrides)
    return ReadoutContext(**base)


def test_scale_when_low_end_clears_breakeven(summary):
    decision, _ = decide(summary, ctx(breakeven_roas=2.0))
    assert decision == "scale"


def test_hold_when_only_central_estimate_clears_breakeven(summary):
    decision, reasons = decide(summary, ctx(breakeven_roas=2.3))
    assert decision == "hold"
    assert any("not yet conclusive" in r for r in reasons)


def test_reduce_when_below_breakeven(summary):
    assert decide(summary, ctx(breakeven_roas=3.5))[0] == "reduce"


def test_valuation_needed_without_breakeven(summary):
    assert decide(summary, ctx(breakeven_roas=None))[0] == "valuation_needed"


def test_inconclusive_when_no_effect_exists():
    flat = summarize_incrementality(make_geo_panel(true_lift=0.0, seed=11), value_per_conversion=80.0)
    decision, reasons = decide(flat, ctx())
    assert decision == "inconclusive"
    assert any("includes zero" in r for r in reasons)


def test_readout_structure_and_style(summary):
    out = build_readout(summary, ctx())
    for heading in [
        "## Headline",
        "## What we tested",
        "## What we found",
        "## How confident we are",
        "## Recommendation",
        "## Caveats",
        "## Suggested next test",
    ]:
        assert heading in out.markdown
    assert "\u2014" not in out.markdown  # no em dashes
    assert "%" in out.headline
    assert out.caveats


def test_short_test_and_signal_loss_add_caveats(summary):
    out = build_readout(summary, ctx(test_days=14, signal_loss_pct=0.3))
    text = " ".join(out.caveats)
    assert "14 days" in text
    assert "30%" in text


def test_numbers_preserved_detects_changes():
    original = "Lift was 5.3% and conversions were 16,874."
    assert numbers_preserved(original, "The lift reached 5.3% with 16,874 conversions.")
    assert not numbers_preserved(original, "The lift reached about 5% with roughly 17,000 conversions.")


def test_polish_without_key_returns_original(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, status = polish_with_llm("Lift was 5.3%.")
    assert text == "Lift was 5.3%."
    assert "no API key" in status


class FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        return None

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


def test_polish_accepts_output_that_preserves_numbers(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse("Conversions rose 5.3% in the test."))
    text, status = polish_with_llm("Lift was 5.3%.", api_key="test-key")
    assert text == "Conversions rose 5.3% in the test."
    assert status == "language model polished"


def test_polish_rejects_output_that_alters_numbers(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse("Conversions rose about 5% in the test."))
    text, status = polish_with_llm("Lift was 5.3%.", api_key="test-key")
    assert text == "Lift was 5.3%."
    assert "rejected" in status


def test_polish_falls_back_on_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "post", boom)
    text, status = polish_with_llm("Lift was 5.3%.", api_key="test-key")
    assert text == "Lift was 5.3%."
    assert "failed" in status
