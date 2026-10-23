import streamlit as st

from measurement.audit import SAMPLE_PAGES, audit_html, fetch_html
from measurement.plots import audit_chart

st.set_page_config(page_title="Measurement Audit", page_icon="🔍", layout="wide")
st.title("4. Measurement readiness audit")
st.caption("Score a page for resilience to privacy changes and signal loss.")

st.markdown(
    "This is a static check of page source. Settings held inside a Tag Manager container, or injected after the page loads, "
    "cannot be seen. Those items are marked unverifiable and earn no credit until you confirm them."
)

mode = st.radio("Input", ["Sample pages", "Public URL", "Paste HTML"], horizontal=True)

html, url = None, ""
if mode == "Sample pages":
    choice = st.selectbox("Sample", list(SAMPLE_PAGES))
    url, html = SAMPLE_PAGES[choice]
    st.caption("Sample pages use fictitious identifiers.")
elif mode == "Public URL":
    target = st.text_input("Page URL", placeholder="https://www.example.com/")
    st.caption("Audit only sites you own or have permission to review. Private and local addresses are blocked.")
    if st.button("Fetch and audit") and target:
        try:
            with st.spinner("Fetching page source"):
                st.session_state["fetched"] = fetch_html(target)
        except (ValueError, Exception) as exc:  # noqa: BLE001 - show any network failure plainly
            st.error(f"Could not fetch the page: {exc}")
    if "fetched" in st.session_state:
        html, url = st.session_state["fetched"]
else:
    url = st.text_input("Page URL (used for the HTTPS check)", "https://www.example.com/")
    html = st.text_area("Page source", height=220)

if not html:
    st.stop()

first_pass = audit_html(html, url)
unverifiable = [c.name for c in first_pass.checks if c.status == "unverifiable" and c.name != "Secure transport"]
confirmed = set()
if unverifiable:
    confirmed = set(
        st.multiselect(
            "Items you have verified in the Tag Manager container",
            unverifiable,
            help="Only select items you have personally confirmed. They will be scored as passing.",
        )
    )

result = audit_html(html, url, confirmed=confirmed)
st.session_state["audit"] = result

c1, c2 = st.columns([1, 3])
c1.metric("Score", f"{result.score:.0f} / 100")
c1.markdown(f"**{result.grade}**")
c2.plotly_chart(audit_chart(result.checks), width="stretch")

st.subheader("Priorities")
priorities = result.priorities()
if priorities:
    for check in priorities:
        st.markdown(f"- **{check.name}** (up to {check.weight - check.points:.0f} points): {check.recommendation}")
else:
    st.success("No open items detected.")

st.subheader("Scorecard")
st.dataframe(result.to_frame(), hide_index=True, width="stretch")

with st.expander("Raw signals detected"):
    st.json(result.signals)
