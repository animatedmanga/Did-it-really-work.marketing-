import streamlit as st

st.set_page_config(page_title="Ads Measurement Portfolio", page_icon="📈", layout="wide")

st.title("Ads Measurement Portfolio")
st.caption("A connected workflow for designing, analyzing, communicating and auditing advertising measurement.")

st.markdown(
    """
This application demonstrates the full lifecycle of an advertising experiment. Each stage is a page in the sidebar,
and results flow forward from one stage to the next.

All data in this application is **synthetic**. No client data is used or stored.
"""
)

stages = [
    ("1. Experiment design", "design", "Size a test, estimate its duration and choose between a user-level lift study and a geo experiment."),
    ("2. Incrementality analysis", "summary", "Estimate causal lift with difference-in-differences, synthetic control and a regression counterfactual."),
    ("3. Executive readout", "readout", "Convert the analysis into a one page recommendation with a transparent decision rule."),
    ("4. Measurement audit", "audit", "Score a page for signal-loss resilience: consent, enhanced conversions and server-side tagging."),
]

cols = st.columns(4)
for col, (title, key, text) in zip(cols, stages):
    with col:
        done = key in st.session_state
        st.subheader(title)
        st.write(text)
        st.markdown(":green[Completed in this session]" if done else ":gray[Not run yet]")

with st.expander("Methods and limitations"):
    st.markdown(
        """
- Experiment sizing uses a two-proportion z-test. Geo power is simulated on market-level log changes.
- The primary lift estimate is a two-way fixed effects difference-in-differences with market-clustered errors.
- Synthetic control and the regression counterfactual are robustness checks. The regression counterfactual is a simplified
  analogue of CausalImpact, not the Bayesian structural time series model.
- The audit inspects static page source. Settings held inside a Tag Manager container are reported as unverifiable.
- Synthetic data lets every estimator be checked against a known true effect. Real campaigns require more care, including
  spillover between markets and conversion delay.
"""
    )
