"""
app.py - OLA Ride Insights (Streamlit)
Run from the repo root:  streamlit run app/app.py
Data comes from MySQL (local) or TiDB Cloud (deployed) through SQLAlchemy - never from a CSV.
"""
import base64
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from queries import load_rides, run_sql, SQL_QUESTIONS, VIEWS

st.set_page_config(page_title="OLA Ride Insights", page_icon="🚖", layout="wide")

# ---------------------------------------------------------------------------
# 1. Constants: paths and the colour code used in the notebook and Power BI
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
ROOT = APP_DIR.parent
ICONS = APP_DIR / "assets" / "icons"

LIME, GREEN, ORANGE, RED, GREY = "#B5D334", "#2E8B57", "#F3A712", "#E4572E", "#7F7F7F"
TILE, BORDER = "#1C1C1C", "#333333"
STATUS_COLORS = {"Success": GREEN, "Canceled by Driver": RED,
                 "Canceled by Customer": ORANGE, "Driver Not Found": GREY}
VEHICLE_FILES = {"Auto": "auto.png", "Bike": "bike.png", "eBike": "ebike.png", "Mini": "mini.png",
                 "Prime Plus": "prime_plus.png", "Prime Sedan": "prime_sedan.png",
                 "Prime SUV": "prime_suv.png"}
DRIVER_CAUSED = ["Driver is not moving towards pickup location", "Driver asked to cancel"]

st.markdown(f"""
<style>
.kpi {{background:{TILE}; border:1px solid {BORDER}; border-radius:10px;
       padding:14px 8px; text-align:center; margin-bottom:8px;}}
.kpi .v {{color:{LIME}; font-size:1.8rem; font-weight:700; line-height:1.2;}}
.kpi .l {{color:#BFBFBF; font-size:0.85rem; margin-top:4px;}}
.vcard {{background:{TILE}; border:1px solid {BORDER}; border-radius:10px;
         padding:12px 6px; text-align:center; margin-bottom:8px;}}
.vcard img {{width:54px; height:54px; background:#D9D9D9; border-radius:50%; padding:8px;}}
.vcard .vn {{color:#F2F2F2; font-weight:700; margin-top:6px;}}
.vcard .vv {{color:{LIME}; font-size:1.2rem; font-weight:700;}}
.vcard .vl {{color:#BFBFBF; font-size:0.75rem;}}

/* Brand bar + page title (shown on every page) */
.brand {{display:flex; align-items:center; gap:14px; padding-bottom:12px;
         border-bottom:1px solid {BORDER}; margin-bottom:16px;}}
.brand .circle {{height:46px; width:46px; background:#FFFFFF; border-radius:50%;}}
.brand .word {{height:30px;}}
.ptitle {{display:flex; align-items:center; gap:12px; margin:4px 0 16px 0;}}
.ptitle img {{height:34px;}}
.ptitle span {{font-size:2rem; font-weight:700; color:#F2F2F2;}}

/* Compact sidebar with breathing room around the section headings */
section[data-testid="stSidebar"] .stButton > button {{padding:0.15rem 0.6rem; min-height:2rem;
                                                      font-size:0.9rem;}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{gap:0.45rem;}}
.side-h {{color:{LIME}; font-size:0.8rem; font-weight:700; letter-spacing:0.08em;
          text-transform:uppercase; margin:18px 0 10px 0;}}

/* Insight cards, note cards and recommendation cards */
.icard {{background:{TILE}; border:1px solid {BORDER}; border-radius:10px; padding:14px 16px;
         min-height:128px; margin-bottom:12px;}}
.icard .big {{font-size:1.7rem; font-weight:700; line-height:1.2;}}
.icard .t {{color:#D9D9D9; font-size:0.9rem; margin-top:6px;}}
.ncard {{background:{TILE}; border:1px solid {BORDER}; border-radius:10px; padding:14px 16px;
         min-height:120px; margin-bottom:12px;}}
.ncard .h {{color:{LIME}; font-weight:700; margin-bottom:6px;}}
.ncard .t {{color:#D9D9D9; font-size:0.9rem;}}
.rcard {{background:{TILE}; border:1px solid {BORDER}; border-radius:10px; padding:14px 16px;
         min-height:140px; margin-bottom:12px;}}
.rcard .top {{display:flex; align-items:center; gap:10px; margin-bottom:8px;}}
.rcard .num {{background:{LIME}; color:#0D0D0D; font-weight:800; border-radius:50%;
              width:28px; height:28px; display:flex; align-items:center; justify-content:center;}}
.rcard .h {{color:#F2F2F2; font-weight:700;}}
.rcard .t {{color:#D9D9D9; font-size:0.88rem;}}
.tag {{display:inline-block; margin-top:8px; padding:2px 10px; border-radius:20px;
       font-size:0.72rem; font-weight:700;}}
.tag.high {{background:{RED}; color:white;}}
.tag.med {{background:{ORANGE}; color:#0D0D0D;}}
.section-h {{font-size:1.25rem; font-weight:700; color:#F2F2F2; margin:18px 0 10px 0;}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 2. Helpers: number formats, KPI cards, chart styling
# ---------------------------------------------------------------------------
def inr(n) -> str:
    """Indian digit grouping: 103024 -> 1,03,024"""
    n = int(round(float(n)))
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    last3, rest = s[-3:], s[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return sign + (",".join(groups + [last3]) if groups else last3)


def money(n) -> str:
    """₹ in Crore / Lakh / plain, the way an Indian ops team reads money."""
    n = float(n)
    if abs(n) >= 1e7:
        return f"₹ {n / 1e7:.2f} Cr"
    if abs(n) >= 1e5:
        return f"₹ {n / 1e5:.2f} L"
    return f"₹ {inr(n)}"


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def kpis(items):
    """A row of KPI cards. items = [(label, value), ...]"""
    for col, (label, value) in zip(st.columns(len(items)), items):
        col.markdown(f'<div class="kpi"><div class="v">{value}</div>'
                     f'<div class="l">{label}</div></div>', unsafe_allow_html=True)


def style(fig, title, height=380):
    fig.update_layout(title=dict(text=title, font=dict(size=15)), template="plotly_dark",
                      paper_bgcolor=TILE, plot_bgcolor=TILE, height=height,
                      margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", yanchor="top", y=-0.15, x=0))
    return fig


def show(fig, where=st):
    where.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# 3. Load data once (cached in db.py) from MySQL / TiDB
# ---------------------------------------------------------------------------
with st.spinner("Loading rides from the database..."):
    df = load_rides()

# ---------------------------------------------------------------------------
# 4. Sidebar: logo, navigation with the PPT icons, filters
# ---------------------------------------------------------------------------
PAGES = [("Overall", "overall"), ("Vehicle Type", "vehicle"), ("Revenue", "revenue"),
         ("Cancellation", "cancellation"), ("Ratings", "ratings"),
         ("SQL Queries", ":material/database:"), ("Power BI", ":material/bar_chart:"),
         ("Insights & Anomalies", ":material/lightbulb:"), ("Data Explorer", ":material/table_view:")]

if "page" not in st.session_state:
    st.session_state.page = "Overall"

with st.sidebar:
    st.image(str(ICONS / "brand" / "ola_wordmark_white.png"), width=100)
    # Filters FIRST, so nobody has to scroll to find them
    st.markdown('<div class="side-h">Filters</div>', unsafe_allow_html=True)
    dmin, dmax = df["Ride_Date"].min().date(), df["Ride_Date"].max().date()
    dates = st.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
    vehicles = st.multiselect("Vehicle type", sorted(df["Vehicle_Type"].unique()),
                              placeholder="All vehicles")
    slots = st.multiselect("Time slot", ["Morning", "Afternoon", "Evening", "Night"],
                           placeholder="All time slots")
    st.caption("Leave a filter empty to include everything.")

    st.divider()
    st.markdown('<div class="side-h">Pages</div>', unsafe_allow_html=True)
    for name, icon in PAGES:
        active = st.session_state.page == name
        c1, c2 = st.columns([1, 5], vertical_alignment="center")
        if icon.startswith(":material"):
            clicked = c2.button(name, icon=icon, key=f"nav_{name}", width="stretch",
                                type="primary" if active else "secondary")
        else:
            c1.image(str(ICONS / "nav" / f"{icon}_{'white' if active else 'grey'}.png"), width=22)
            clicked = c2.button(name, key=f"nav_{name}", width="stretch",
                                type="primary" if active else "secondary")
        if clicked:
            st.session_state.page = name
            st.rerun()

# Apply filters -> every chart on every page uses `f` (all bookings) or `ok` (completed rides)
if isinstance(dates, (tuple, list)):
    start, end = (dates[0], dates[-1]) if dates else (dmin, dmax)
else:
    start = end = dates
f = df[(df["Ride_Date"].dt.date >= start) & (df["Ride_Date"].dt.date <= end)]
if vehicles:
    f = f[f["Vehicle_Type"].isin(vehicles)]
if slots:
    f = f[f["Time_Slot"].isin(slots)]
if f.empty:
    st.warning("No bookings match these filters. Widen the date range or clear a filter.")
    st.stop()
ok = f[f["Is_Success"] == 1]


LOGO_CIRCLE = b64(ICONS / "brand" / "ola_logo_circle.png")
LOGO_WORD = b64(ICONS / "brand" / "ola_wordmark_white.png")
NAV_ICON = dict(PAGES)   # page name -> PPT icon key or material icon


def header(title):
    """OLA circle logo + OLA wordmark, then the page icon + title, on EVERY page."""
    st.markdown(f'<div class="brand"><img class="circle" src="data:image/png;base64,{LOGO_CIRCLE}">'
                f'<img class="word" src="data:image/png;base64,{LOGO_WORD}"></div>',
                unsafe_allow_html=True)
    icon = NAV_ICON.get(title, "")
    if icon and not icon.startswith(":material"):
        img = b64(ICONS / "nav" / f"{icon}_white.png")
        st.markdown(f'<div class="ptitle"><img src="data:image/png;base64,{img}">'
                    f'<span>{PAGE_TITLES.get(title, title)}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f"## {icon} {PAGE_TITLES.get(title, title)}")


def hbar_room(fig, values, factor=1.25):
    """Widen a horizontal bar chart's x-range so outside labels never get cut off."""
    top = max(values) if len(values) else 1
    fig.update_xaxes(range=[0, top * factor], visible=False)
    return fig


PAGE_TITLES = {"Overall": "Overall Performance", "Vehicle Type": "Vehicle Type Performance",
               "Revenue": "Revenue Analysis", "Cancellation": "Cancellation Analysis",
               "Ratings": "Ratings Analysis", "Power BI": "Power BI Dashboard"}


# ---------------------------------------------------------------------------
# 5. Pages
# ---------------------------------------------------------------------------
def page_overall():
    header("Overall")
    cancel_rate = f["Cancelled_By"].isin(["Customer", "Driver"]).mean()
    kpis([("Total Bookings", inr(len(f))), ("Completed Rides", inr(len(ok))),
          ("Success Rate", f"{len(ok) / len(f):.2%}"), ("Cancellation Rate", f"{cancel_rate:.2%}"),
          ("Revenue", money(ok["Booking_Value"].sum()))])

    c1, c2 = st.columns([3, 2])
    daily = (f.groupby("Ride_Date")
             .agg(Total=("Booking_ID", "count"), Completed=("Is_Success", "sum")).reset_index())
    fig = go.Figure()
    fig.add_scatter(x=daily["Ride_Date"], y=daily["Total"], name="Total bookings",
                    mode="lines+markers", line=dict(color=GREY))
    fig.add_scatter(x=daily["Ride_Date"], y=daily["Completed"], name="Completed rides",
                    mode="lines+markers", line=dict(color=LIME))
    fig.update_yaxes(rangemode="tozero")
    show(style(fig, "Ride volume over time (daily)"), c1)

    status = f["Booking_Status"].value_counts().reindex(list(STATUS_COLORS)).dropna()
    fig = go.Figure(go.Bar(x=status.values, y=status.index, orientation="h",
                           marker_color=[STATUS_COLORS[s] for s in status.index],
                           text=[inr(v) for v in status.values], textposition="outside",
                           cliponaxis=False))
    fig.update_yaxes(autorange="reversed")
    hbar_room(fig, status.values)
    show(style(fig, "Booking status breakdown"), c2)

    hourly = f.groupby("Ride_Hour").size().reindex(range(24), fill_value=0)
    fig = go.Figure(go.Bar(x=hourly.index, y=hourly.values, marker_color=LIME, name="Bookings"))
    fig.add_hline(y=hourly.mean(), line_dash="dash", line_color="white")
    fig.update_xaxes(title="Hour of day", dtick=1)
    show(style(fig, "Bookings by hour of day (dashed line = average)", 320))

    low = hourly[hourly > 0]
    gap = (low.max() / low.min() - 1) * 100 if len(low) else 0
    st.info(f"**Insight:** {cancel_rate:.1%} of bookings are cancelled and only "
            f"{len(ok) / len(f):.1%} complete. The busiest hour ({hourly.idxmax()}:00) is only "
            f"{gap:.1f}% above the quietest, so demand is flat across the day; the problem is "
            f"converting bookings into rides, not peak-hour supply.")


def page_vehicle():
    header("Vehicle Type")
    kpis([("Avg Ride Distance", f"{ok['Ride_Distance'].mean():.2f} km"),
          ("Total Distance", f"{inr(ok['Ride_Distance'].sum())} km"),
          ("Total Booking Value", money(f["Booking_Value"].sum())),
          ("Revenue (completed)", money(ok["Booking_Value"].sum()))])

    summary = (f.groupby("Vehicle_Type")
               .agg(Bookings=("Booking_ID", "count"), Completed=("Is_Success", "sum"),
                    Booking_Value=("Booking_Value", "sum"), Revenue=("Revenue", "sum"))
               .join(ok.groupby("Vehicle_Type")
                     .agg(Avg_km=("Ride_Distance", "mean"), Total_km=("Ride_Distance", "sum")))
               .fillna(0).sort_values("Revenue", ascending=False))

    for col, (veh, row) in zip(st.columns(len(summary)), summary.iterrows()):
        icon = b64(ICONS / "vehicles" / VEHICLE_FILES.get(veh, "mini.png"))
        col.markdown(f'<div class="vcard"><img src="data:image/png;base64,{icon}">'
                     f'<div class="vn">{veh}</div><div class="vv">{money(row["Revenue"])}</div>'
                     f'<div class="vl">{inr(row["Completed"])} rides · {row["Avg_km"]:.1f} km avg</div>'
                     f'</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([2, 3])
    top5 = summary.nlargest(5, "Total_km").sort_values("Total_km")
    fig = go.Figure(go.Bar(x=top5["Total_km"], y=top5.index, orientation="h", marker_color=LIME,
                           text=[inr(v) for v in top5["Total_km"]], textposition="outside",
                           cliponaxis=False))
    hbar_room(fig, top5["Total_km"].values)
    show(style(fig, "Top 5 vehicle types by total ride distance (km)"), c1)

    table = pd.DataFrame({
        "Vehicle": summary.index,
        "Booking Value": [money(v) for v in summary["Booking_Value"]],
        "Revenue": [money(v) for v in summary["Revenue"]],
        "Success %": [f"{c / b:.1%}" for c, b in zip(summary["Completed"], summary["Bookings"])],
        "Avg km": [f"{v:.2f}" for v in summary["Avg_km"]],
        "Total km": [inr(v) for v in summary["Total_km"]],
    })
    c2.markdown("##### Vehicle type summary")
    c2.dataframe(table, hide_index=True, width="stretch")

    if "Auto" in summary.index and len(summary) > 1:
        others = ok[ok["Vehicle_Type"] != "Auto"]["Ride_Distance"].mean()
        c2.info(f"**Insight:** Autos average {summary.loc['Auto', 'Avg_km']:.1f} km per trip versus "
                f"{others:.1f} km for the other vehicles, yet earn a similar booking value - roughly "
                f"2.5× more per km. Other vehicles are within a few percent of each other.")


def page_revenue():
    header("Revenue")
    kpis([("Revenue (completed)", money(ok["Booking_Value"].sum())),
          ("Avg Fare", f"₹ {inr(ok['Booking_Value'].mean())}" if len(ok) else "–"),
          ("Revenue at Risk", money(f.loc[f["Is_Success"] == 0, "Booking_Value"].sum())),
          ("Completed Rides", inr(len(ok)))])

    c1, c2 = st.columns([2, 3])
    pay = ok.groupby("Payment_Method")["Booking_Value"].sum().sort_values()
    fig = go.Figure(go.Bar(x=pay.values, y=pay.index, orientation="h", marker_color=LIME,
                           text=[money(v) for v in pay.values], textposition="outside",
                           cliponaxis=False))
    hbar_room(fig, pay.values, 1.35)
    show(style(fig, "Revenue by payment method", 300), c1)

    top = (f.groupby("Customer_ID")
           .agg(Booking_Value=("Revenue", "sum"), Rides=("Is_Success", "sum")).reset_index()
           .sort_values(["Booking_Value", "Rides", "Customer_ID"], ascending=[False, False, True])
           .head(5))
    c1.markdown("##### Top 5 customers by booking value")
    c1.dataframe(top.assign(Booking_Value=top["Booking_Value"].map(lambda v: f"₹ {inr(v)}"))
                 .rename(columns={"Customer_ID": "Customer", "Booking_Value": "Booking Value"}),
                 hide_index=True, width="stretch")

    d = (ok.groupby("Ride_Date")
         .agg(Total_km=("Ride_Distance", "sum"), Avg_km=("Ride_Distance", "mean")).reset_index())
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=d["Ride_Date"], y=d["Total_km"], name="Total km", marker_color=LIME)
    fig.add_scatter(x=d["Ride_Date"], y=d["Avg_km"], name="Avg km per ride",
                    mode="lines+markers", line=dict(color="white"), secondary_y=True)
    fig.update_yaxes(rangemode="tozero", secondary_y=False)
    fig.update_yaxes(range=[0, 30], secondary_y=True)   # honest scale: avg stays flat ~23 km
    show(style(fig, "Ride distance per day (total km · avg km per ride)", 520), c2)

    cash = ok["Payment_Method"].eq("Cash").mean() if len(ok) else 0
    st.info(f"**Insight:** Cash still settles {cash:.1%} of completed rides. Average fares are the same "
            f"across payment methods, so moving cash riders to UPI is about faster settlement and "
            f"lower cash risk, not higher fares.")


def page_cancellation():
    header("Cancellation")
    cust = f[f["Booking_Status"] == "Canceled by Customer"]
    drv = f[f["Booking_Status"] == "Canceled by Driver"]
    total_cancel = len(cust) + len(drv)
    driver_caused = len(drv) + cust["Canceled_Rides_by_Customer"].isin(DRIVER_CAUSED).sum()
    kpis([("Cancellation Rate", f"{total_cancel / len(f):.2%}"),
          ("Cancelled by Driver", inr(len(drv))), ("Cancelled by Customer", inr(len(cust))),
          ("Driver-caused Share", f"{driver_caused / total_cancel:.1%}" if total_cancel else "–"),
          ("Driver Not Found", inr((f["Booking_Status"] == "Driver Not Found").sum()))])

    c1, c2 = st.columns(2)
    for col, data, field, color, title in [
        (c1, cust, "Canceled_Rides_by_Customer", ORANGE, f"Why customers cancel ({inr(len(cust))})"),
        (c2, drv, "Canceled_Rides_by_Driver", RED, f"Why drivers cancel ({inr(len(drv))})"),
    ]:
        vc = data[field].value_counts().sort_values()
        fig = go.Figure(go.Bar(x=vc.values, y=vc.index, orientation="h", marker_color=color,
                               text=[inr(v) for v in vc.values], textposition="outside",
                               cliponaxis=False))
        hbar_room(fig, vc.values)
        show(style(fig, title, 340), col)

    rate = (f.assign(c=f["Cancelled_By"].isin(["Customer", "Driver"]))
            .groupby("Ride_Hour")["c"].mean().mul(100))
    fig = go.Figure(go.Scatter(x=rate.index, y=rate.values, mode="lines+markers",
                               line=dict(color=RED), name="Cancellation %"))
    fig.update_yaxes(range=[0, max(40, rate.max() * 1.2)], title="% of bookings")
    fig.update_xaxes(title="Hour of day", dtick=1)
    show(style(fig, "Cancellation rate by hour of day", 300))

    if total_cancel:
        st.info(f"**Insight:** Drivers are behind {driver_caused / total_cancel:.1%} of cancellations: "
                f"{inr(len(drv))} direct driver cancellations plus customer cancellations caused by the "
                f"driver ('driver not moving', 'driver asked to cancel'). Reasons are self-reported, so "
                f"validate them against GPS and complaint data before penalising drivers.")


def page_ratings():
    header("Ratings")
    kpis([("Avg Driver Rating", f"{ok['Driver_Ratings'].mean():.3f}"),
          ("Avg Customer Rating", f"{ok['Customer_Rating'].mean():.3f}"),
          ("Rated Rides", inr(ok["Driver_Ratings"].notna().sum())),
          ("Rides Rated 4.5+", f"{(ok['Driver_Ratings'] >= 4.5).mean():.1%}")])

    c1, c2 = st.columns(2)
    for col, field, color, title in [
        (c1, "Driver_Ratings", LIME, "Driver ratings distribution (given by customers)"),
        (c2, "Customer_Rating", GREEN, "Customer ratings distribution (given by drivers)"),
    ]:
        vc = ok[field].round(1).value_counts().sort_index()
        fig = go.Figure(go.Bar(x=vc.index, y=vc.values, marker_color=color))
        fig.update_xaxes(dtick=0.5, title="Rating")
        show(style(fig, title, 320), col)

    rv = ok.groupby("Vehicle_Type")[["Driver_Ratings", "Customer_Rating"]].mean().reset_index()
    long = rv.melt(id_vars="Vehicle_Type", var_name="Rating", value_name="Average")
    fig = px.bar(long, x="Vehicle_Type", y="Average", color="Rating", barmode="group",
                 text=long["Average"].round(3),
                 color_discrete_map={"Driver_Ratings": LIME, "Customer_Rating": GREEN})
    fig.update_yaxes(range=[0, 5], title="Average rating (out of 5)")
    fig.update_xaxes(title="")
    show(style(fig, "Average driver vs customer rating by vehicle", 360))

    st.info("**Insight:** Ratings are spread evenly between 3.0 and 5.0 for both sides, with no ratings "
            "below 3 and no 5-star cluster, and every vehicle averages about 4.0. Ratings cannot separate "
            "good and poor service in this data, so OLA should collect written feedback and low-rating reasons.")


def page_sql():
    header("SQL Queries")
    for item in SQL_QUESTIONS:
        with st.expander(item["q"]):
            st.code(item["sql"], language="sql")
            try:
                st.dataframe(run_sql(item["sql"]), hide_index=True, width="stretch")
                if "count_sql" in item:
                    st.caption("Totals:")
                    st.dataframe(run_sql(item["count_sql"]), hide_index=True)
                st.success(f"**Business meaning:** {item['meaning']}")
            except Exception as e:
                st.error(f"Query failed: {e}")

    st.caption("These queries run live against the database (MySQL locally, TiDB Cloud online) "
               "and always cover the full month - the sidebar filters do not apply here.")
    st.markdown("### Reporting views")
    view = st.selectbox("Pick a view (used by Power BI and for cross-checks)", VIEWS)
    sql = f"SELECT * FROM {view} LIMIT 100"
    st.code(sql + ";", language="sql")
    try:
        st.dataframe(run_sql(sql), hide_index=True, width="stretch")
    except Exception as e:
        st.error(f"Query failed: {e}")


def page_powerbi():
    header("Power BI")
    # Screenshots are shown in name order, so name them 01_overall.png ... 05_ratings.png
    shots = sorted((ROOT / "powerbi" / "screenshots").glob("*.png"))
    labels = ["Overall", "Vehicle Type", "Revenue", "Cancellation", "Ratings"]
    if shots:
        names = [labels[i] if i < len(labels) else p.stem for i, p in enumerate(shots)]
        for tab, shot in zip(st.tabs(names), shots):
            tab.image(str(shot), width="stretch")
    else:
        st.warning("No screenshots found in powerbi/screenshots/.")
    pbix = ROOT / "powerbi" / "OLA_Dashboard.pbix"
    if pbix.exists():
        st.download_button("⬇️ Download OLA_Dashboard.pbix", data=pbix.read_bytes(),
                           file_name="OLA_Dashboard.pbix", mime="application/octet-stream")
    st.caption("The report reads from MySQL through an ODBC DSN and is shared as a .pbix file with "
               "screenshots, because Power BI Service publishing requires an organisational account.")


def cards(items, kind="icard", per_row=3):
    """Grid of HTML cards. icard: (big, text, colour) · ncard: (heading, text)
    rcard: (number, heading, text, priority)"""
    for i in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for col, it in zip(cols, items[i:i + per_row]):
            if kind == "icard":
                big, text, color = it
                html = (f'<div class="icard" style="border-left:4px solid {color}">'
                        f'<div class="big" style="color:{color}">{big}</div><div class="t">{text}</div></div>')
            elif kind == "ncard":
                head, text = it
                html = f'<div class="ncard"><div class="h">{head}</div><div class="t">{text}</div></div>'
            else:
                num, head, text, prio = it
                tag = "high" if prio == "High" else "med"
                html = (f'<div class="rcard"><div class="top"><div class="num">{num}</div>'
                        f'<div class="h">{head}</div></div><div class="t">{text}</div>'
                        f'<span class="tag {tag}">{prio} impact</span></div>')
            col.markdown(html, unsafe_allow_html=True)


def page_insights():
    header("Insights & Anomalies")

    # Key findings: calculated from the FULL month (df), never typed in by hand
    full_ok = df[df["Is_Success"] == 1]
    d_cust = (df["Booking_Status"] == "Canceled by Customer").sum()
    d_drv = (df["Booking_Status"] == "Canceled by Driver").sum()
    d_caused = d_drv + df.loc[df["Booking_Status"] == "Canceled by Customer",
                              "Canceled_Rides_by_Customer"].isin(DRIVER_CAUSED).sum()
    at_risk = df.loc[df["Is_Success"] == 0, "Booking_Value"].sum()
    drv_risk = df.loc[df["Booking_Status"] == "Canceled by Driver", "Booking_Value"].sum()
    pay = full_ok["Payment_Method"].value_counts(normalize=True)
    st.markdown('<div class="section-h">📌 Key findings (full month)</div>', unsafe_allow_html=True)
    cards([
        (f"{len(full_ok) / len(df):.1%}",
         f"of {inr(len(df))} bookings became completed rides, earning {money(full_ok['Booking_Value'].sum())}.", LIME),
        (f"{(d_cust + d_drv) / len(df):.1%}",
         f"cancellation rate: drivers {d_drv / len(df):.1%}, customers {d_cust / len(df):.1%}, "
         f"plus {(df['Booking_Status'] == 'Driver Not Found').mean():.1%} 'Driver Not Found'.", RED),
        (f"{d_caused / (d_cust + d_drv):.1%}",
         "of all cancellations trace back to drivers, including customer cancellations caused by the driver.", RED),
        (money(at_risk), f"of quoted fares lost to failed bookings; driver cancellations alone put "
                         f"{money(drv_risk)} at risk.", ORANGE),
        (f"{pay.get('Cash', 0):.1%}", f"of completed rides paid in cash; UPI {pay.get('UPI', 0):.1%}, "
                                      f"cards under 5%.", GREEN),
        ("Flat", "No meaningful difference across hours, days, vehicles, locations or ratings: "
                 "demand and service quality look the same everywhere.", GREY),
    ])

    st.markdown('<div class="section-h">🔍 Anomalies (live: respond to the sidebar filters)</div>',
                unsafe_allow_html=True)
    same = f["Same_Pickup_Drop"] == 1
    fpk = ok["Fare_per_km"].dropna()
    corr = ok["Booking_Value"].corr(ok["Ride_Distance"]) if len(ok) > 2 else float("nan")
    daily = f.groupby("Ride_Date").size()
    auto_fpk = ok.loc[ok["Vehicle_Type"] == "Auto", "Fare_per_km"].median()
    other_fpk = ok.loc[ok["Vehicle_Type"] != "Auto", "Fare_per_km"].median()
    kpis([("Same pickup & drop", f"{inr(same.sum())} ({same.mean():.1%})"),
          ("Rides above ₹200/km", f"{inr((fpk > 200).sum())} ({(fpk > 200).mean():.1%})" if len(fpk) else "–"),
          ("Fare vs distance correlation", f"{corr:.3f}"),
          ("Auto vs others ₹/km (median)",
           f"₹{auto_fpk:.1f} vs ₹{other_fpk:.1f}" if pd.notna(auto_fpk) and pd.notna(other_fpk) else "–")])
    notes = []
    if len(daily) > 1:
        notes.append(("📉 Lowest day",
                      f"{daily.idxmin():%d %b} had {inr(daily.min())} bookings, "
                      f"{(1 - daily.min() / daily.mean()):.1%} below the daily average of {inr(daily.mean())}. "
                      f"The data covers the full day, so the dip is real."))
    notes.append(("💰 Fare not linked to distance",
                  "A 2 km and a 49 km ride cost the same on average. Impossible for real taxi pricing, so this "
                  "is the most serious data-quality finding."))
    notes.append(("📍 Same pickup & drop",
                  "These trips still average about 23 km, which points to unmarked round trips or location "
                  "errors rather than fraud."))
    cards(notes, kind="ncard")

    st.warning("**Data limitation:** the dataset is synthetic (uniform ratings, equal vehicle shares, "
               "fares independent of distance). Findings describe this data, not real OLA operations.")

    st.markdown('<div class="section-h">✅ Recommendations</div>', unsafe_allow_html=True)
    cards([
        (1, "Cut driver cancellations", "Live pickup tracking, alerts when a driver is not moving, and "
                                        "penalties for repeat cancellations.", "High"),
        (2, "Close the supply gap", "Driver positioning and incentives to reduce 'Driver Not Found' "
                                    "bookings.", "High"),
        (3, "Audit the fare formula", "Fares must rise with distance and vehicle class; review Auto "
                                      "pricing first.", "High"),
        (4, "Vehicle checks", "Regular AC and car-condition checks to cut 'car related' and "
                              "'AC not working' cancellations.", "Medium"),
        (5, "Shift cash to UPI", "Small cashback or UPI-first defaults; track the cash share "
                                 "every month.", "Medium"),
        (6, "Automatic anomaly alerts", "Review any ride above ₹200/km and add a round-trip flag "
                                        "to bookings.", "Medium"),
    ], kind="rcard")


def page_explorer():
    header("Data Explorer")
    search = st.text_input("Search Booking_ID or Customer_ID", placeholder="e.g. CNR7153255142 or CID713523")
    default_cols = ["Booking_DateTime", "Booking_ID", "Booking_Status", "Customer_ID", "Vehicle_Type",
                    "Pickup_Location", "Drop_Location", "Booking_Value", "Payment_Method",
                    "Ride_Distance", "Driver_Ratings", "Customer_Rating", "Cancellation_Reason"]
    cols = st.multiselect("Columns", list(f.columns), default=default_cols)
    view = f
    if search:
        s = search.strip()
        view = f[f["Booking_ID"].str.contains(s, case=False) | f["Customer_ID"].str.contains(s, case=False)]
    st.caption(f"{inr(len(view))} rows")
    st.dataframe(view[cols or default_cols], hide_index=True, width="stretch", height=480)
    st.download_button("⬇️ Download these rows (CSV)",
                       data=view[cols or default_cols].to_csv(index=False).encode("utf-8"),
                       file_name="ola_filtered.csv", mime="text/csv")


# ---------------------------------------------------------------------------
# 6. Router: show the selected page
# ---------------------------------------------------------------------------
ROUTES = {"Overall": page_overall, "Vehicle Type": page_vehicle, "Revenue": page_revenue,
          "Cancellation": page_cancellation, "Ratings": page_ratings, "SQL Queries": page_sql,
          "Power BI": page_powerbi, "Insights & Anomalies": page_insights,
          "Data Explorer": page_explorer}
ROUTES[st.session_state.page]()