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


# ---------------------------------------------------------------------------
# The 10 required SQL questions (shown and run live on the "SQL Queries" page)
# "sql" is what we display and run; "count_sql" gives the true total when
# the main query only previews rows (LIMIT 100).
# ---------------------------------------------------------------------------
SQL_QUESTIONS = [
    {
        "q": "1. Retrieve all successful bookings",
        "sql": """SELECT Booking_ID, Booking_DateTime, Vehicle_Type, Pickup_Location,
       Drop_Location, Booking_Value, Payment_Method
FROM ola_rides
WHERE Booking_Status = 'Success'
LIMIT 100;""",
        "count_sql": "SELECT COUNT(*) AS successful_bookings FROM ola_rides WHERE Booking_Status = 'Success';",
        "meaning": "63,967 of 103,024 bookings (62.1%) became completed, paying rides.",
    },
    {
        "q": "2. Average ride distance for each vehicle type",
        "sql": """SELECT Vehicle_Type,
       ROUND(AVG(Ride_Distance), 2) AS avg_distance_km,
       COUNT(*) AS rides
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Vehicle_Type
ORDER BY avg_distance_km DESC;""",
        "meaning": "Autos average about 10 km per trip versus about 25 km for every other vehicle.",
    },
    {
        "q": "3. Total number of rides cancelled by customers",
        "sql": """SELECT COUNT(*) AS cancelled_by_customer
FROM ola_rides
WHERE Booking_Status = 'Canceled by Customer';""",
        "meaning": "10,499 bookings (10.2%); over half of these were caused by the driver.",
    },
    {
        "q": "4. Top 5 customers by number of rides booked",
        "sql": """SELECT Customer_ID,
       COUNT(*)        AS total_bookings,
       SUM(Is_Success) AS completed_rides,
       SUM(Revenue)    AS total_revenue
FROM ola_rides
GROUP BY Customer_ID
ORDER BY total_bookings DESC, total_revenue DESC, Customer_ID ASC
LIMIT 5;""",
        "meaning": ("Only 1 customer booked 5 times; 26 customers tie at 4 bookings, so ties are broken "
                    "by revenue, then Customer_ID. 91.6% of customers booked only once."),
    },
    {
        "q": "5. Rides cancelled by drivers due to personal and car-related issues",
        "sql": """SELECT COUNT(*) AS driver_cancel_personal_car
FROM ola_rides
WHERE Canceled_Rides_by_Driver = 'Personal & Car related issue';""",
        "meaning": "6,542 rides: the single biggest reason drivers cancel (35.5% of driver cancellations).",
    },
    {
        "q": "6. Maximum and minimum driver ratings for Prime Sedan",
        "sql": """SELECT MAX(Driver_Ratings) AS max_driver_rating,
       MIN(Driver_Ratings) AS min_driver_rating
FROM ola_rides
WHERE Vehicle_Type = 'Prime Sedan' AND Booking_Status = 'Success';""",
        "meaning": "Ratings span the full 3.0 to 5.0 range; no Prime Sedan driver is rated below 3.",
    },
    {
        "q": "7. All rides paid using UPI",
        "sql": """SELECT Booking_ID, Booking_DateTime, Vehicle_Type, Booking_Value
FROM ola_rides
WHERE Payment_Method = 'UPI'
LIMIT 100;""",
        "count_sql": "SELECT COUNT(*) AS upi_rides, SUM(Revenue) AS upi_revenue FROM ola_rides WHERE Payment_Method = 'UPI';",
        "meaning": "25,881 rides (40.5% of completed rides), worth ₹1.42 Cr.",
    },
    {
        "q": "8. Average customer rating per vehicle type",
        "sql": """SELECT Vehicle_Type,
       ROUND(AVG(Customer_Rating), 3) AS avg_customer_rating
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Vehicle_Type
ORDER BY avg_customer_rating DESC;""",
        "meaning": "All vehicles fall between 3.988 and 4.009: no meaningful difference.",
    },
    {
        "q": "9. Total booking value of successfully completed rides",
        "sql": """SELECT SUM(Booking_Value) AS total_success_booking_value
FROM ola_rides
WHERE Booking_Status = 'Success';""",
        "meaning": "₹3,50,80,467 (≈ ₹3.51 Cr): the master revenue KPI used by every tool.",
    },
    {
        "q": "10. All incomplete rides with their reason",
        "sql": """SELECT Booking_ID, Booking_DateTime, Vehicle_Type, Incomplete_Rides_Reason
FROM ola_rides
WHERE Incomplete_Rides = 'Yes'
ORDER BY Booking_DateTime
LIMIT 100;""",
        "count_sql": """SELECT Incomplete_Rides_Reason, COUNT(*) AS rides
FROM ola_rides
WHERE Incomplete_Rides = 'Yes'
GROUP BY Incomplete_Rides_Reason
ORDER BY rides DESC;""",
        "meaning": "3,926 rides: customer demand (1,601) and vehicle breakdown (1,591) are almost equal.",
    },
]

# Reporting views (created by pipeline/load_to_mysql.py from sql/ola_queries.sql)
VIEWS = [
    "vw_overall_daily", "vw_vehicle_summary", "vw_revenue_payment", "vw_top_customers",
    "vw_daily_distance", "vw_cancellation_reasons", "vw_rating_distribution", "vw_ratings_by_vehicle",
]


def run_sql(sql: str) -> pd.DataFrame:
    """Run one of the SQL strings above (trailing semicolon removed)."""
    return run_query(sql.strip().rstrip(";"))
