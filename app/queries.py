"""queries.py - every SQL statement the app uses, in one place."""
import pandas as pd
from db import run_query

RIDES_SQL = "SELECT * FROM ola_rides"
ICONS_SQL = "SELECT Vehicle_Type, Icon_URL FROM vehicle_icons"


def load_rides() -> pd.DataFrame:
    """All bookings from MySQL/TiDB, with clean Python types."""
    df = run_query(RIDES_SQL)
    df["Booking_DateTime"] = pd.to_datetime(df["Booking_DateTime"])
    df["Ride_Date"] = pd.to_datetime(df["Ride_Date"])
    # DECIMAL columns arrive as Python Decimal objects -> convert to normal numbers
    for col in ["Driver_Ratings", "Customer_Rating", "Fare_per_km", "Rating_Gap"]:
        df[col] = pd.to_numeric(df[col])
    return df


def load_icons() -> pd.DataFrame:
    return run_query(ICONS_SQL)