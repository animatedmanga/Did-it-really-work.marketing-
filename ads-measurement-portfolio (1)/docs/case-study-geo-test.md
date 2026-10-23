# Case study: proving the incremental value of a Search campaign

All figures come from synthetic data produced by this repository (40 markets, seed 11, true lift 6.0%). The scenario is fictional. The point is to show the decision process, and every number can be reproduced by running the app.

## Client situation

An advertiser spends heavily on a new Search campaign and reports a strong return in its attribution dashboard. Finance asks a harder question: how many conversions would have happened anyway? The marketing lead wants a defensible answer before approving a budget increase.

Constraints: 40 markets are available, user-level randomization is not possible for this campaign, the test can run for at most 6 weeks, and about 20% of conversions go unobserved because of consent and cookie loss.

## Stage 1: test design

The target was a 5% relative lift. The design stage returned **not feasible as specified**:

- A user-level randomized study was ruled out because randomization was unavailable.
- A matched-market geo experiment with 40 markets could detect a minimum lift of **5.6%**, and simulated power at the 5% target was **70%**, below the 80% standard.
- Synthetic control on pre/post data was possible but rests on modeling assumptions.

Recommendation: raise the target effect to 5.6% or more, or add markets. If neither is possible, run the analysis as directional only. The team accepted a 6% planning effect, which sits above the detectable threshold.

The stage also flagged two risks: unobserved conversions can bias results if the loss differs by group, and the analysis plan and end date must be fixed in advance to avoid peeking.

## Stage 2: analysis

Twenty markets received the campaign and twenty matched controls did not, over 112 days with the campaign live for the final 28.

| Method | Lift | 95% interval |
|---|---|---|
| Difference-in-differences (primary) | 6.1% | 5.1% to 7.0% |
| Synthetic control | 6.2% | not reported |
| Regression counterfactual | 6.9% | 6.0% to 7.9% |

The three methods agree within 0.8 percentage points, and the true built-in effect of 6.0% sits inside the primary interval. The primary estimate implies **23,190 incremental conversions** on **$647,354** of spend, a cost of **$27.92 per incremental conversion**. With $60 of value per conversion, incremental ROAS was **2.15x** (1.83x to 2.46x).

## Stage 3: recommendation

The decision rule compares the low end of the ROAS interval with the breakeven return of 1.00x. The low end of 1.83x clears breakeven, so the readout recommended **scale investment**, with the caveats that 20% of conversions are unobserved and that market spillover would bias lift toward zero.

Suggested next step: raise budget by 20% to 30% in a subset of markets and run a follow-up geo test to confirm that returns hold at higher spend. Diminishing returns are the usual reason a strong average return does not survive scaling.

## What this shows

- A feasibility check before spend prevents an underpowered test from producing a misleading answer.
- Cross-checking estimators builds confidence and exposes model dependence.
- A decision rule tied to the interval, not the point estimate, protects against over-reading noise.
- Caveats belong in the readout, not in a footnote.
