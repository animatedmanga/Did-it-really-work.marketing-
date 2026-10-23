import streamlit as st

from measurement.design import DesignInputs, recommend_design, sensitivity_table
from measurement.plots import duration_chart, power_chart

st.set_page_config(page_title="Experiment Design", page_icon="🧪", layout="wide")
st.title("1. Experiment design and feasibility")
st.caption("Size a test, estimate its duration and choose a method before spending budget.")

with st.sidebar:
    st.header("Inputs")
    baseline = st.number_input("Baseline conversion rate (%)", 0.1, 50.0, 3.0, 0.1) / 100
    mde = st.number_input("Target relative lift (%)", 0.5, 100.0, 8.0, 0.5) / 100
    users = st.number_input("Eligible users per day", 100, 5_000_000, 20_000, 500)
    n_geos = st.number_input("Available markets", 0, 500, 30, 2)
    noise = st.slider("Market-level volatility (SD of log change)", 0.02, 0.20, 0.06, 0.01)
    randomize = st.checkbox("User-level randomization is available", value=True)
    max_weeks = st.slider("Maximum test length (weeks)", 1, 12, 6)
    loss = st.slider("Share of conversions not observed (%)", 0, 60, 0) / 100

try:
    inputs = DesignInputs(
        baseline_rate=baseline,
        mde_relative=mde,
        daily_eligible_users=int(users),
        n_geos=int(n_geos),
        geo_noise_sd=noise,
        can_randomize_users=randomize,
        max_weeks=int(max_weeks),
        signal_loss_pct=loss,
    )
    rec = recommend_design(inputs)
except ValueError as exc:
    st.error(f"Check the inputs: {exc}")
    st.stop()

st.session_state["design"] = {"inputs": inputs, "recommendation": rec}

if rec.feasible:
    st.success(f"Recommended method: {rec.method}")
else:
    st.warning(f"{rec.method}")
st.write(rec.rationale)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Users per arm", f"{rec.n_per_arm:,}")
c2.metric("User-level duration", f"{rec.duration_days} days")
geo_mde = "n/a" if rec.geo_mde_relative == float("inf") else f"{rec.geo_mde_relative:.1%}"
c3.metric("Geo minimum detectable lift", geo_mde)
c4.metric("Geo power at target", f"{rec.geo_power_at_target:.0%}")

st.subheader("Options considered")
for option in rec.options:
    icon = "✅" if option.feasible else "⛔"
    st.markdown(f"{icon} **{option.name}**: {option.detail}")

if rec.suggestions:
    st.subheader("How to make this test feasible")
    for item in rec.suggestions:
        st.markdown(f"- {item}")

st.subheader("Risks to manage")
for risk in rec.risks:
    st.markdown(f"- {risk}")

st.subheader("Sensitivity to the target lift")
table = sensitivity_table(inputs)
left, right = st.columns(2)
left.plotly_chart(duration_chart(table, inputs.max_weeks * 7), width="stretch")
right.plotly_chart(power_chart(table), width="stretch")
with st.expander("View as table"):
    shown = table.copy()
    shown["target_lift"] = shown["target_lift"].map("{:.1%}".format)
    shown["geo_power"] = shown["geo_power"].map("{:.0%}".format)
    st.dataframe(shown, hide_index=True, width="stretch")
