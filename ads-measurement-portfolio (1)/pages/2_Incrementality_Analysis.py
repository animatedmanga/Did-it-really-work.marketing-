import pandas as pd
import streamlit as st

from measurement.incrementality import summarize_incrementality
from measurement.plots import counterfactual_chart, estimator_chart
from measurement.synthetic import make_geo_panel

MAX_UPLOAD_ROWS = 300_000

st.set_page_config(page_title="Incrementality Analysis", page_icon="📊", layout="wide")
st.title("2. Incrementality analysis")
st.caption("Estimate the conversions caused by a campaign using market-level experiment data.")

source = st.radio("Data source", ["Synthetic geo experiment", "Upload a CSV"], horizontal=True)

panel = None
true_lift = None

if source == "Synthetic geo experiment":
    c1, c2, c3, c4 = st.columns(4)
    true_lift = c1.slider("True lift built into the data (%)", 0.0, 20.0, 6.0, 0.5) / 100
    n_geos = c2.slider("Markets", 10, 100, 40, 2)
    noise = c3.slider("Noise level", 0.01, 0.15, 0.04, 0.01)
    seed = c4.number_input("Random seed", 0, 10_000, 7)

    @st.cache_data(show_spinner=False)
    def _panel(lift, geos, noise_sd, seed_value):
        return make_geo_panel(n_geos=geos, true_lift=lift, noise_sd=noise_sd, seed=int(seed_value))

    panel = _panel(true_lift, n_geos, noise, seed)
else:
    st.markdown(
        "Required columns: `geo`, `date`, `group` (`treatment` or `control`), `post` (0 for pre-period, 1 for test period) "
        "and `conversions`. Optional: `spend`. Use only data you are permitted to analyze."
    )
    upload = st.file_uploader("Daily market-level CSV", type="csv")
    if upload is not None:
        try:
            raw = pd.read_csv(upload, nrows=MAX_UPLOAD_ROWS + 1)
            if len(raw) > MAX_UPLOAD_ROWS:
                st.error(f"Files are limited to {MAX_UPLOAD_ROWS:,} rows.")
                st.stop()
            raw["date"] = pd.to_datetime(raw["date"])
            panel = raw
        except Exception as exc:  # noqa: BLE001 - surface any parsing problem to the user
            st.error(f"Could not read the file: {exc}")
            st.stop()

if panel is None:
    st.info("Choose a data source to continue.")
    st.stop()

st.subheader("Valuation inputs")
v1, v2 = st.columns(2)
value = v1.number_input("Value per conversion", 0.0, 1_000_000.0, 80.0, 5.0)
breakeven = v2.number_input("Breakeven incremental ROAS (x)", 0.0, 50.0, 2.0, 0.1)

if st.button("Run analysis", type="primary"):
    try:
        with st.spinner("Estimating lift with three methods"):
            summary = summarize_incrementality(panel, value_per_conversion=value or None)
    except ValueError as exc:
        st.error(f"The data could not be analyzed: {exc}")
        st.stop()
    test_rows = panel[panel["post"] == 1]
    st.session_state["summary"] = {
        "result": summary,
        "n_treatment": int(panel.loc[panel["group"] == "treatment", "geo"].nunique()),
        "n_control": int(panel.loc[panel["group"] == "control", "geo"].nunique()),
        "start": str(pd.to_datetime(test_rows["date"]).min().date()),
        "end": str(pd.to_datetime(test_rows["date"]).max().date()),
        "days": int(test_rows["date"].nunique()),
        "value": value or None,
        "breakeven": breakeven or None,
        "true_lift": true_lift,
    }

state = st.session_state.get("summary")
if not state:
    st.stop()

result = state["result"]
primary = result["primary"]

st.subheader("Results")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Measured lift", f"{primary.lift:.1%}", help="Difference-in-differences estimate")
m2.metric("95% interval", f"{primary.lift_low:.1%} to {primary.lift_high:.1%}")
m3.metric("Incremental conversions", f"{primary.incremental_conversions:,.0f}")
if result["iroas"] is not None:
    m4.metric("Incremental ROAS", f"{result['iroas']:.2f}x", help=f"Range {result['iroas_low']:.2f}x to {result['iroas_high']:.2f}x")
else:
    m4.metric("Incremental ROAS", "n/a")

if state["true_lift"] is not None:
    covered = primary.lift_low <= state["true_lift"] <= primary.lift_high
    st.caption(
        f"Validation: the synthetic data contains a true lift of {state['true_lift']:.1%}. "
        + ("The interval covers it." if covered else "The interval misses it, which happens in roughly 1 in 20 runs.")
    )

st.plotly_chart(estimator_chart(primary, result["robustness"]), width="stretch")

left, right = st.columns(2)
left.plotly_chart(counterfactual_chart(result["synthetic_series"], "Synthetic control counterfactual"), width="stretch")
right.plotly_chart(counterfactual_chart(result["regression_series"], "Regression counterfactual"), width="stretch")

table = pd.DataFrame(
    [
        {
            "Method": r.method,
            "Lift": f"{r.lift:.1%}",
            "Interval": f"{r.lift_low:.1%} to {r.lift_high:.1%}" if r.lift_low is not None else "not reported",
            "Incremental conversions": f"{r.incremental_conversions:,.0f}",
            "Notes": " ".join(r.notes),
        }
        for r in [primary, *result["robustness"]]
    ]
)
st.dataframe(table, hide_index=True, width="stretch")
st.caption(f"Largest gap between methods: {result['max_gap_pts']:.1f} percentage points of lift.")
st.info("Continue to the Executive readout page to turn this result into a recommendation.")
