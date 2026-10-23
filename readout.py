"""Executive readout generator (Project 3).

Turns the structured output of the incrementality analysis into a one page,
non-technical summary with an explicit decision rule and automatic caveats.
The default path is fully rule based and deterministic. An optional language
model pass can improve the prose, but it is accepted only if every number in the
original readout is preserved exactly.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import numpy as np
import requests

DECISIONS = {
    "scale": "Scale investment",
    "hold": "Hold budget and refine",
    "reduce": "Reduce or restructure spend",
    "inconclusive": "Inconclusive: do not change budget yet",
    "valuation_needed": "Effect confirmed: add value and breakeven to size the budget decision",
}


@dataclass
class ReadoutContext:
    test_name: str
    objective: str
    n_treatment_geos: int
    n_control_geos: int
    start_date: str
    end_date: str
    test_days: int
    breakeven_roas: float | None = None
    value_per_conversion: float | None = None
    signal_loss_pct: float = 0.0
    currency: str = "$"


@dataclass
class Readout:
    decision: str
    headline: str
    markdown: str
    caveats: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def _money(x: float, currency: str) -> str:
    return f"{currency}{x:,.0f}"


def _pre_mape(series) -> float | None:
    pre = series[~series["post"]]
    if pre.empty:
        return None
    return float(np.mean(np.abs(pre["actual"] - pre["counterfactual"]) / pre["actual"]))


def decide(summary: dict, ctx: ReadoutContext) -> tuple[str, list[str]]:
    """Apply the decision rule and return the decision key with its reasons."""
    primary = summary["primary"]
    iroas, iroas_low = summary.get("iroas"), summary.get("iroas_low")
    breakeven = ctx.breakeven_roas

    if primary.lift_high is not None and primary.lift_high < 0:
        return "reduce", ["The campaign had a negative measured effect on conversions."]

    if not primary.significant:
        return "inconclusive", [
            f"The interval for lift ({_pct(primary.lift_low)} to {_pct(primary.lift_high)}) includes zero.",
            "The result cannot distinguish a real effect from normal variation.",
        ]

    if iroas is None or breakeven is None:
        return "valuation_needed", [
            "The lift is statistically distinguishable from zero.",
            "Value per conversion and a breakeven return are needed to judge profitability.",
        ]

    if iroas_low >= breakeven:
        return "scale", [
            f"Even the low end of the interval ({iroas_low:.2f}x) clears breakeven ({breakeven:.2f}x).",
        ]
    if iroas >= breakeven:
        return "hold", [
            f"The central estimate ({iroas:.2f}x) clears breakeven ({breakeven:.2f}x), "
            f"but the low end ({iroas_low:.2f}x) does not.",
            "The evidence is positive but not yet conclusive on profitability.",
        ]
    return "reduce", [
        f"The central estimate ({iroas:.2f}x) is below breakeven ({breakeven:.2f}x).",
    ]


def _caveats(summary: dict, ctx: ReadoutContext) -> list[str]:
    notes: list[str] = []
    if ctx.test_days < 21:
        notes.append(
            f"The test ran for {ctx.test_days} days. Conversions with a long delay may not be fully captured."
        )
    mape = _pre_mape(summary["synthetic_series"])
    if mape is not None and mape > 0.10:
        notes.append(f"The control markets reproduced the pre-period only loosely (error {_pct(mape)}).")
    gap = summary.get("max_gap_pts")
    if gap is not None and gap > 3.0:
        notes.append(
            f"The three estimation methods differ by up to {gap:.1f} percentage points of lift. "
            "Treat the central figure as approximate."
        )
    if ctx.signal_loss_pct >= 0.20:
        notes.append(
            f"About {_pct(ctx.signal_loss_pct, 0)} of conversions are not observed. "
            "If that loss differs between markets, the result may be biased."
        )
    notes.append(
        "Markets are not perfectly isolated. Exposure across borders would bias the measured lift toward zero."
    )
    return notes


def _next_test(decision: str) -> str:
    return {
        "scale": "Increase budget in a controlled step of 20 to 30 percent in a subset of markets and "
        "run a follow-up geo test to confirm returns hold at higher spend.",
        "hold": "Repeat the test with more markets or a longer window to narrow the interval, "
        "or test a higher spend level to learn the shape of the response curve.",
        "reduce": "Test a restructured campaign, for example a different audience or creative, "
        "before committing further budget.",
        "inconclusive": "Rerun with more markets, a longer window, or a larger spend contrast so the "
        "test can detect the lift that would change the decision.",
        "valuation_needed": "Agree the value per conversion and the breakeven return with finance, "
        "then rerun the decision rule on this result.",
    }[decision]


def build_readout(summary: dict, ctx: ReadoutContext) -> Readout:
    """Create the readout from an incrementality summary and test context."""
    primary = summary["primary"]
    decision, reasons = decide(summary, ctx)
    caveats = _caveats(summary, ctx)
    cur = ctx.currency

    share = primary.lift / (1 + primary.lift)
    headline = (
        f"{DECISIONS[decision]}. The campaign lifted conversions by {_pct(primary.lift)} "
        f"(plausible range {_pct(primary.lift_low)} to {_pct(primary.lift_high)})."
    )

    found = [
        f"- Measured lift in conversions: {_pct(primary.lift)}, with a 95% interval of "
        f"{_pct(primary.lift_low)} to {_pct(primary.lift_high)}.",
        f"- Incremental conversions: {primary.incremental_conversions:,.0f}. In plain terms, about "
        f"{share * 100:.0f} of every 100 conversions in the exposed markets were caused by the campaign.",
    ]
    if summary.get("spend"):
        found.append(f"- Media spend in treatment markets: {_money(summary['spend'], cur)}.")
    if summary.get("icpa"):
        found.append(f"- Cost per incremental conversion: {cur}{summary['icpa']:,.2f}.")
    if summary.get("iroas") is not None:
        found.append(
            f"- Incremental return on ad spend: {summary['iroas']:.2f}x "
            f"(range {summary['iroas_low']:.2f}x to {summary['iroas_high']:.2f}x)."
        )
        if ctx.breakeven_roas is not None:
            found.append(f"- Breakeven return used for the decision: {ctx.breakeven_roas:.2f}x.")

    robustness = [
        f"- {r.method}: {_pct(r.lift)}"
        + (f" ({_pct(r.lift_low)} to {_pct(r.lift_high)})" if r.lift_low is not None else "")
        for r in summary["robustness"]
    ]

    sections = [
        f"# {ctx.test_name}",
        "## Headline",
        headline,
        "## What we tested",
        f"{ctx.objective} The campaign ran in {ctx.n_treatment_geos} treatment markets, with "
        f"{ctx.n_control_geos} comparable control markets receiving no campaign, from "
        f"{ctx.start_date} to {ctx.end_date} ({ctx.test_days} days).",
        "## What we found",
        "\n".join(found),
        "## How confident we are",
        f"The primary estimate comes from a difference-in-differences analysis. Two alternative methods "
        f"were run on the same data as cross-checks:\n" + "\n".join(robustness),
        "## Recommendation",
        f"**{DECISIONS[decision]}.** " + " ".join(reasons),
        "## Caveats",
        "\n".join(f"- {c}" for c in caveats),
        "## Suggested next test",
        _next_test(decision),
    ]
    return Readout(
        decision=decision,
        headline=headline,
        markdown="\n\n".join(sections),
        caveats=caveats,
        reasons=reasons,
    )


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?x?")


def numbers_preserved(original: str, polished: str) -> bool:
    """True if every numeric token in the original also appears in the polished text."""
    tokens = {t.rstrip(".,") for t in _NUMBER.findall(original)}
    return all(t in polished for t in tokens if t)


def polish_with_llm(
    markdown: str,
    api_key: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> tuple[str, str]:
    """Optionally refine the prose with a language model.

    Returns (text, status). The original text is returned unchanged whenever the
    key is missing, the call fails, or the model alters any number.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return markdown, "rule-based (no API key provided)"
    model_name = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    instruction = (
        "Rewrite the following measurement readout for a senior marketing executive. "
        "Keep the same headings and structure. Keep every number, percentage and date exactly as written. "
        "Use clear, professional prose, avoid jargon, and do not add facts that are not present. "
        "Do not use em dashes. Return only the rewritten readout.\n\n"
        f"<readout>\n{markdown}\n</readout>"
    )
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model_name,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": instruction}],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        return markdown, f"rule-based (language model call failed: {type(exc).__name__})"

    if not numbers_preserved(markdown, text):
        return markdown, "rule-based (language model output altered a number and was rejected)"
    return text, "language model polished"
