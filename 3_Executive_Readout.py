import streamlit as st

from measurement.readout import DECISIONS, ReadoutContext, build_readout, polish_with_llm

st.set_page_config(page_title="Executive Readout", page_icon="📝", layout="wide")
st.title("3. Executive readout")
st.caption("A one page summary for marketing leaders, with a transparent decision rule.")

state = st.session_state.get("summary")
if not state:
    st.info("Run the Incrementality analysis page first. The readout is built from its result.")
    st.stop()

result = state["result"]

with st.sidebar:
    st.header("Readout settings")
    name = st.text_input("Test name", "Search campaign geo test")
    objective = st.text_area("Objective", "The test measured the conversions caused by a new Search campaign.")
    currency = st.selectbox("Currency symbol", ["$", "₹", "€", "£"])
    loss = st.slider("Share of conversions not observed (%)", 0, 60, 0) / 100

ctx = ReadoutContext(
    test_name=name,
    objective=objective,
    n_treatment_geos=state["n_treatment"],
    n_control_geos=state["n_control"],
    start_date=state["start"],
    end_date=state["end"],
    test_days=state["days"],
    breakeven_roas=state["breakeven"],
    value_per_conversion=state["value"],
    signal_loss_pct=loss,
    currency=currency,
)
readout = build_readout(result, ctx)
st.session_state["readout"] = readout

badge = {"scale": "green", "hold": "orange", "reduce": "red", "inconclusive": "gray", "valuation_needed": "blue"}[readout.decision]
st.markdown(f"### :{badge}[{DECISIONS[readout.decision]}]")

with st.expander("Optional: refine the wording with a language model"):
    st.markdown(
        "The default readout is rule based and deterministic. If you provide your own API key, a language model can "
        "improve the prose. The result is accepted only if every number is preserved exactly. The key is used for this "
        "request only and is not stored."
    )
    key = st.text_input("Anthropic API key", type="password")
    if st.button("Refine wording") and key:
        with st.spinner("Refining"):
            text, status = polish_with_llm(readout.markdown, api_key=key)
        st.session_state["polished"] = (text, status)

final_text, status = st.session_state.get("polished", (readout.markdown, "rule-based"))
if final_text != readout.markdown and st.session_state.get("polished"):
    st.caption(f"Source: {status}")

st.markdown(final_text)
st.download_button("Download as Markdown", final_text, file_name="executive_readout.md", mime="text/markdown")
