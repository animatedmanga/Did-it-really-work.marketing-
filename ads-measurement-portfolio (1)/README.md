# Ads Measurement Portfolio

A connected workflow that covers the full lifecycle of an advertising experiment: **design it, analyze it, communicate it, and audit the data foundation underneath it.**

Each stage is a page in one Streamlit app, and the output of one stage feeds the next. All data is synthetic, so every estimator can be checked against a known true effect.

> **Live demo:** _add your Streamlit Community Cloud link here_

## The four stages

| Stage | Business question | What it does |
|---|---|---|
| 1. Experiment design | Can this effect be measured at all, and with which method? | Sample size, duration and power for a user-level lift study and a geo experiment. Recommends a method, lists risks, and says plainly when a test is not feasible. |
| 2. Incrementality analysis | How many conversions did the campaign actually cause? | Difference-in-differences (primary), synthetic control and a regression counterfactual (cross-checks). Reports lift, interval, incremental conversions, cost per incremental conversion and incremental ROAS. |
| 3. Executive readout | What should the business do next? | One page summary with a transparent decision rule, automatic caveats and a suggested follow-up test. Rule based by default. An optional language model can refine the wording, and the result is rejected if any number changes. |
| 4. Measurement audit | Is the measurement foundation resilient to signal loss? | Scores a page for Google tag setup, Consent Mode v2, enhanced conversions, first-party or server-side tagging, and tag hygiene. Returns a prioritized fix list. |

## Screenshots

| Design | Analysis |
|---|---|
| ![Experiment design](docs/images/1-experiment-design.png) | ![Incrementality analysis](docs/images/2-incrementality.png) |
| **Readout** | **Audit** |
| ![Executive readout](docs/images/3-executive-readout.png) | ![Measurement audit](docs/images/4-measurement-audit.png) |

## Worked example

The full walkthrough is in [docs/case-study-geo-test.md](docs/case-study-geo-test.md). In brief, a 40 market synthetic test with 20% of conversions unobserved:

- The design stage found that a 5% target lift was **not detectable** (the geo design could detect 5.6%), and recommended raising the target or adding markets.
- The analysis recovered a **6.1% lift** (95% interval 5.1% to 7.0%) against a true effect of 6.0%, with synthetic control at 6.2% and the regression counterfactual at 6.9%.
- Incremental ROAS was **2.15x** (1.83x to 2.46x), so the readout recommended scaling because even the low end cleared the breakeven threshold.

A second case study, [docs/case-study-measurement-audit.md](docs/case-study-measurement-audit.md), covers the audit.

## Validation

The estimators are tested against data where the true effect is known.

- Over 200 simulated experiments with a true lift of 6.0%, the primary estimator had a bias of -0.02 percentage points, a standard deviation of 0.59 points, and a 95% interval that contained the truth in 93.5% of runs.
- The test suite has 58 checks covering sample size formulas, power, estimator behavior, input validation, readout decision logic, the number-preservation guard and the audit rules.

Run the suite with `pytest`.

## Run it locally

```bash
git clone https://github.com/<your-username>/ads-measurement-portfolio.git
cd ads-measurement-portfolio
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Optional: language model polish

The readout works without any key. To let a language model refine the wording, paste your own Anthropic API key into the expander on the readout page. The key is held in session memory only and is never written to disk. The refined text is accepted only if every number in the original is preserved exactly.

## Method notes and limitations

Stating limitations is part of the method, so they are listed here.

- **Sizing.** User-level sizing uses a two-proportion z-test. Geo power is simulated on market-level log changes, so it depends on the volatility input.
- **Primary estimator.** Two-way fixed effects difference-in-differences with market-clustered standard errors. It assumes parallel trends, which the synthetic data satisfies by construction. Real data needs a pre-period check.
- **Regression counterfactual.** This is a simplified frequentist analogue of CausalImpact with a block bootstrap interval. It is not the Bayesian structural time series model.
- **Synthetic control.** Reported as a point estimate only, with no interval.
- **Not modeled.** Spillover between markets, conversion delay, and seasonality that differs by market. The readout lists spillover as a caveat.
- **Audit scope.** The audit reads static page source. Settings that live inside a Tag Manager container, or are injected after page load, cannot be seen, so they are reported as unverifiable and earn no credit until confirmed. A static check is a screening tool, not a replacement for a tag debugging session.
- **Synthetic data.** Results show that the tooling works, not how a real campaign performs.

## Repository layout

```
app.py                      Home page and pipeline status
pages/                      One Streamlit page per stage
measurement/
  design.py                 Sample size, power, method recommendation
  incrementality.py         DiD, synthetic control, regression counterfactual
  readout.py                Decision rule, caveats, optional model polish
  audit.py                  Signal detection, scoring, safe URL fetch
  synthetic.py              Geo panel generator with a known true effect
  plots.py                  Charts
tests/                      Pytest suite
docs/                       Case studies and screenshots
```

## Where the production tools fit

This project teaches the logic. For production work on real accounts, use the platform tools built for scale: Google Ads conversion lift and geo experiments, Meridian or Robyn for marketing mix modeling, and a tag debugging workflow for audits.

## License

MIT. See [LICENSE](LICENSE).
