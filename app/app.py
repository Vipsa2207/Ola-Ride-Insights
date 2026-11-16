"""app.py - OLA Ride Insights (Streamlit). Run from repo root: streamlit run app/app.py"""
import streamlit as st
from queries import load_rides

st.set_page_config(page_title="OLA Ride Insights", page_icon="🚖", layout="wide")


def inr(n) -> str:
    """Indian digit grouping: 103024 -> 1,03,024"""
    s = str(int(round(n)))
    last3, rest = s[-3:], s[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups + [last3]) if groups else last3


with st.spinner("Loading rides from the database..."):
    df = load_rides()

ok = df[df["Is_Success"] == 1]
st.title("OLA Ride Insights — connection test")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Bookings", inr(len(df)))
c2.metric("Completed Rides", inr(len(ok)))
c3.metric("Success Rate", f"{len(ok) / len(df):.2%}")
c4.metric("Cancellation Rate", f"{df['Cancelled_By'].isin(['Customer', 'Driver']).mean():.2%}")
c5.metric("Revenue", f"₹ {ok['Booking_Value'].sum() / 1e7:.2f} Cr")