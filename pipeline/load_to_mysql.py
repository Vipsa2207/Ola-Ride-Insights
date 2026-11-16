"""
load_to_mysql.py
Loads the cleaned OLA data into MySQL (local) or TiDB Cloud, then creates the SQL views.
Run from the repo root:
    python pipeline/load_to_mysql.py            -> local MySQL
    python pipeline/load_to_mysql.py --tidb     -> TiDB Cloud
"""
import os
import sys
from pathlib import Path

import certifi
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import (create_engine, text, URL, MetaData, Table, Column, Index,
                        VARCHAR, INTEGER, SMALLINT, FLOAT, DECIMAL, DATE, DATETIME)

# ---------- 1. Paths + settings ----------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
load_dotenv(ROOT / ".env")
USE_TIDB = "--tidb" in sys.argv

if USE_TIDB:
    S = dict(host=os.getenv("TIDB_HOST"), port=int(os.getenv("TIDB_PORT", 4000)),
             user=os.getenv("TIDB_USER"), password=os.getenv("TIDB_PASSWORD"),
             db=os.getenv("TIDB_DB", "ola_db"))
else:
    S = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 3306)),
             user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
             db=os.getenv("DB_NAME", "ola_db"))

def make_engine(database=None):
    url = URL.create("mysql+pymysql", username=S["user"], password=S["password"],
                     host=S["host"], port=S["port"], database=database,
                     query={"charset": "utf8mb4"})
    ssl = {"ssl": {"ca": certifi.where()}} if USE_TIDB else {}   # TiDB Cloud requires SSL
    return create_engine(url, pool_pre_ping=True, connect_args=ssl)

print("Target:", "TiDB Cloud" if USE_TIDB else "Local MySQL", "|", S["host"])

# ---------- 2. Create the database if it doesn't exist ----------
with make_engine().begin() as conn:
    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {S['db']} CHARACTER SET utf8mb4"))
engine = make_engine(S["db"])

# ---------- 3. Read the cleaned CSV ----------
df = pd.read_csv(DATA / "ola_cleaned.csv", parse_dates=["Booking_DateTime"])
df["Ride_Date"] = pd.to_datetime(df["Ride_Date"]).dt.date
icons = pd.read_csv(DATA / "vehicle_icons.csv")
print(f"CSV loaded: {df.shape[0]:,} rows x {df.shape[1]} columns")

# ---------- 4. Table design: explicit types + primary key + indexes ----------
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
meta = MetaData()
rides = Table("ola_rides", meta,
              *[Column(n, t, primary_key=(n == "Booking_ID")) for n, t in dtypes.items()])
for col in ["Booking_Status", "Vehicle_Type", "Ride_Date", "Payment_Method", "Pickup_Location"]:
    Index(f"idx_{col.lower()}", rides.c[col])
Table("vehicle_icons", meta,
      Column("Vehicle_Type", VARCHAR(20), primary_key=True),
      Column("Icon_URL", VARCHAR(255)))

# ---------- 5. Recreate tables, then load the rows ----------
with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS ola_rides, vehicle_icons"))
meta.create_all(engine)
df.to_sql("ola_rides", engine, if_exists="append", index=False, chunksize=2000, method="multi")
icons.to_sql("vehicle_icons", engine, if_exists="append", index=False)
print("Tables loaded: ola_rides, vehicle_icons (with primary keys + indexes)")

# ---------- 6. Create the views straight from sql/ola_queries.sql ----------
sql_text = (ROOT / "sql" / "ola_queries.sql").read_text(encoding="utf-8")
views = 0
with engine.begin() as conn:
    for chunk in sql_text.split(";"):
        stmt = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if stmt.upper().startswith("CREATE OR REPLACE VIEW"):
            conn.execute(text(stmt))
            views += 1
print(f"Views created: {views}")

# ---------- 7. Verify against the notebook ----------
with engine.connect() as conn:
    c = conn.execute(text("""
        SELECT COUNT(*) AS total_rows, SUM(Is_Success) AS successful, SUM(Revenue) AS revenue,
               ROUND(AVG(CASE WHEN Is_Success = 1 THEN Ride_Distance END), 2) AS avg_km_success,
               SUM(Driver_Ratings IS NULL) AS null_ratings,
               (SELECT SUM(revenue) FROM vw_revenue_payment) AS view_revenue
        FROM ola_rides
    """)).mappings().one()

expected = {"total_rows": 103024, "successful": 63967, "revenue": 35080467,
            "avg_km_success": 22.85, "null_ratings": 39057, "view_revenue": 35080467}
print("\nVerification:")
ok = True
for k, v in expected.items():
    match = float(c[k]) == float(v)
    ok &= match
    print(f"  {k:<15} expected {v:>12,}  got {float(c[k]):>14,}  -> {'OK' if match else 'MISMATCH'}")
print("\nALL CHECKS PASSED" if ok and views == 8 else "\nSOMETHING IS WRONG - stop and check")