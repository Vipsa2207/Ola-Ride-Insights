"""
load_to_mysql.py
Loads the cleaned OLA data (CSV) into MySQL database `ola_db`.
Run from the repo root:  python pipeline/load_to_mysql.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, URL
from sqlalchemy.types import (VARCHAR, INTEGER, SMALLINT, FLOAT, DECIMAL, DATE, DATETIME)

# ---------- 1. Paths (relative to the repo, so it works on any machine) ----------
ROOT = Path(__file__).resolve().parent.parent          # .../Ola-Ride-Insights
DATA = ROOT / "data" / "processed"
load_dotenv(ROOT / ".env")                             # read DB_* settings from .env

# ---------- 2. Connect (URL.create handles special characters in passwords) ----------
url = URL.create(
    "mysql+pymysql",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 3306)),
    database=os.getenv("DB_NAME", "ola_db"),
    query={"charset": "utf8mb4"},
)
engine = create_engine(url, pool_pre_ping=True)

# ---------- 3. Read the CSV with correct date types ----------
df = pd.read_csv(DATA / "ola_cleaned.csv", parse_dates=["Booking_DateTime"])
df["Ride_Date"] = pd.to_datetime(df["Ride_Date"]).dt.date
icons = pd.read_csv(DATA / "vehicle_icons.csv")
print(f"CSV loaded: {df.shape[0]:,} rows × {df.shape[1]} columns")

# ---------- 4. Explicit MySQL column types (no guessing) ----------
dtypes = {
    "Booking_DateTime": DATETIME(), "Booking_ID": VARCHAR(20), "Booking_Status": VARCHAR(30),
    "Customer_ID": VARCHAR(20), "Vehicle_Type": VARCHAR(20),
    "Pickup_Location": VARCHAR(60), "Drop_Location": VARCHAR(60),
    "V_TAT": FLOAT(), "C_TAT": FLOAT(),
    "Canceled_Rides_by_Customer": VARCHAR(100), "Canceled_Rides_by_Driver": VARCHAR(100),
    "Incomplete_Rides": VARCHAR(20), "Incomplete_Rides_Reason": VARCHAR(50),
    "Booking_Value": INTEGER(), "Payment_Method": VARCHAR(20), "Ride_Distance": INTEGER(),
    "Driver_Ratings": DECIMAL(2, 1), "Customer_Rating": DECIMAL(2, 1),
    "Ride_Date": DATE(), "Ride_Hour": SMALLINT(), "Day_Name": VARCHAR(10), "Week_No": SMALLINT(),
    "Is_Weekend": SMALLINT(), "Time_Slot": VARCHAR(10), "Is_Success": SMALLINT(),
    "Cancelled_By": VARCHAR(30), "Cancellation_Reason": VARCHAR(100), "Revenue": INTEGER(),
    "Fare_per_km": DECIMAL(8, 2), "Distance_Band": VARCHAR(20), "Rating_Gap": DECIMAL(3, 1),
    "Route": VARCHAR(130), "Same_Pickup_Drop": SMALLINT(),
}

# ---------- 5. Load both tables (replace = safe to re-run) ----------
df.to_sql("ola_rides", engine, if_exists="replace", index=False,
          dtype=dtypes, chunksize=2000, method="multi")
icons.to_sql("vehicle_icons", engine, if_exists="replace", index=False,
             dtype={"Vehicle_Type": VARCHAR(20), "Icon_URL": VARCHAR(255)})
print("Tables written: ola_rides, vehicle_icons")

# ---------- 6. Primary keys + indexes (faster filters in Power BI / Streamlit) ----------
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE ola_rides ADD PRIMARY KEY (Booking_ID)"))
    conn.execute(text("ALTER TABLE vehicle_icons ADD PRIMARY KEY (Vehicle_Type)"))
    for col in ["Booking_Status", "Vehicle_Type", "Ride_Date", "Payment_Method", "Pickup_Location"]:
        conn.execute(text(f"CREATE INDEX idx_{col.lower()} ON ola_rides ({col})"))
print("Primary keys and indexes added")

# ---------- 7. Verify: numbers must match the notebook ----------
with engine.connect() as conn:
    checks = conn.execute(text("""
        SELECT COUNT(*)                                   AS total_rows,
               SUM(Is_Success)                            AS successful,
               SUM(Revenue)                               AS revenue,
               ROUND(AVG(CASE WHEN Is_Success = 1 THEN Ride_Distance END), 1) AS avg_km_success,
               SUM(Driver_Ratings IS NULL)                AS null_ratings
        FROM ola_rides
    """)).mappings().one()

expected = {"total_rows": 103024, "successful": 63967, "revenue": 35080467,
            "avg_km_success": 22.9, "null_ratings": 39057}
print("\nVerification:")
for k, v in expected.items():
    got = checks[k]
    status = "OK" if float(got) == float(v) else "MISMATCH"
    print(f"  {k:<15} expected {v:>12,}  got {float(got):>14,}  -> {status}")