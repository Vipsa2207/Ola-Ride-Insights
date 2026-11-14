-- =====================================================================
-- OLA Ride Insights · SQL Analysis (MySQL 8.0, database: ola_db)
-- Business rules used everywhere:
--   Revenue            = SUM(Booking_Value) WHERE Booking_Status = 'Success'
--   Distance / ratings = successful rides only (cancelled rides have 0 km, NULL ratings)
-- =====================================================================
USE ola_db;

-- Q1. Retrieve all successful bookings
SELECT * FROM ola_rides WHERE Booking_Status = 'Success';
SELECT COUNT(*) AS successful_bookings FROM ola_rides WHERE Booking_Status = 'Success';

-- Q2. Average ride distance for each vehicle type (successful rides only)
SELECT Vehicle_Type,
       ROUND(AVG(Ride_Distance), 2) AS avg_distance_km,
       COUNT(*)                     AS rides
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Vehicle_Type
ORDER BY avg_distance_km DESC;

-- Q3. Total number of rides cancelled by customers
SELECT COUNT(*) AS cancelled_by_customer
FROM ola_rides
WHERE Booking_Status = 'Canceled by Customer';

-- Q4. Top 5 customers who booked the highest number of rides
--     Ties broken by total revenue (desc), then Customer_ID (asc)
SELECT Customer_ID,
       COUNT(*)        AS total_bookings,
       SUM(Is_Success) AS completed_rides,
       SUM(Revenue)    AS total_revenue
FROM ola_rides
GROUP BY Customer_ID
ORDER BY total_bookings DESC, total_revenue DESC, Customer_ID ASC
LIMIT 5;

-- Q5. Number of rides cancelled by drivers due to personal and car-related issues
SELECT COUNT(*) AS driver_cancel_personal_car
FROM ola_rides
WHERE Canceled_Rides_by_Driver = 'Personal & Car related issue';

-- Q6. Maximum and minimum driver ratings for Prime Sedan bookings
SELECT MAX(Driver_Ratings) AS max_driver_rating,
       MIN(Driver_Ratings) AS min_driver_rating
FROM ola_rides
WHERE Vehicle_Type = 'Prime Sedan' AND Booking_Status = 'Success';

-- Q7. Retrieve all rides where payment was made using UPI
SELECT * FROM ola_rides WHERE Payment_Method = 'UPI';
SELECT COUNT(*) AS upi_rides, SUM(Revenue) AS upi_revenue
FROM ola_rides WHERE Payment_Method = 'UPI';

-- Q8. Average customer rating per vehicle type
SELECT Vehicle_Type,
       ROUND(AVG(Customer_Rating), 3) AS avg_customer_rating
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Vehicle_Type
ORDER BY avg_customer_rating DESC;

-- Q9. Total booking value of rides completed successfully
SELECT SUM(Booking_Value) AS total_success_booking_value
FROM ola_rides
WHERE Booking_Status = 'Success';

-- Q10. All incomplete rides along with the reason
SELECT Booking_ID, Booking_DateTime, Vehicle_Type, Incomplete_Rides_Reason
FROM ola_rides
WHERE Incomplete_Rides = 'Yes'
ORDER BY Booking_DateTime;
SELECT Incomplete_Rides_Reason, COUNT(*) AS rides
FROM ola_rides
WHERE Incomplete_Rides = 'Yes'
GROUP BY Incomplete_Rides_Reason
ORDER BY rides DESC;

-- =====================================================================
-- VIEWS: one source of truth for Power BI pages and Streamlit
-- =====================================================================

-- Overall page: daily bookings, completed rides and revenue
CREATE OR REPLACE VIEW vw_overall_daily AS
SELECT Ride_Date, Day_Name, Booking_Status,
       COUNT(*)      AS bookings,
       SUM(Revenue)  AS revenue
FROM ola_rides
GROUP BY Ride_Date, Day_Name, Booking_Status;

-- Vehicle Type page: per-vehicle summary + icon
CREATE OR REPLACE VIEW vw_vehicle_summary AS
SELECT r.Vehicle_Type, i.Icon_URL,
       COUNT(*)                                                    AS total_bookings,
       SUM(r.Is_Success)                                           AS completed_rides,
       ROUND(AVG(r.Is_Success) * 100, 2)                           AS success_rate_pct,
       SUM(r.Booking_Value)                                        AS total_booking_value,
       SUM(r.Revenue)                                              AS success_booking_value,
       ROUND(AVG(CASE WHEN r.Is_Success = 1 THEN r.Ride_Distance END), 2) AS avg_distance_km,
       SUM(CASE WHEN r.Is_Success = 1 THEN r.Ride_Distance ELSE 0 END)    AS total_distance_km
FROM ola_rides r
LEFT JOIN vehicle_icons i ON r.Vehicle_Type = i.Vehicle_Type
GROUP BY r.Vehicle_Type, i.Icon_URL;

-- Revenue page (1): revenue by payment method
CREATE OR REPLACE VIEW vw_revenue_payment AS
SELECT Payment_Method,
       COUNT(*)                        AS rides,
       SUM(Booking_Value)              AS revenue,
       ROUND(AVG(Booking_Value), 2)    AS avg_fare
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Payment_Method;

-- Revenue page (2): top 5 customers by total booking value (completed rides)
--   Ties broken by number of rides, then Customer_ID
CREATE OR REPLACE VIEW vw_top_customers AS
SELECT Customer_ID,
       SUM(Revenue)    AS total_booking_value,
       SUM(Is_Success) AS completed_rides
FROM ola_rides
GROUP BY Customer_ID
ORDER BY total_booking_value DESC, completed_rides DESC, Customer_ID ASC
LIMIT 5;

-- Revenue page (3): ride distance per day (completed rides)
CREATE OR REPLACE VIEW vw_daily_distance AS
SELECT Ride_Date,
       COUNT(*)                      AS completed_rides,
       SUM(Ride_Distance)            AS total_distance_km,
       ROUND(AVG(Ride_Distance), 2)  AS avg_distance_km
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Ride_Date;

-- Cancellation page: reasons by who cancelled
CREATE OR REPLACE VIEW vw_cancellation_reasons AS
SELECT Cancelled_By, Cancellation_Reason,
       COUNT(*)            AS cancellations,
       SUM(Booking_Value)  AS quoted_value_lost
FROM ola_rides
WHERE Booking_Status IN ('Canceled by Customer', 'Canceled by Driver')
GROUP BY Cancelled_By, Cancellation_Reason;

-- Ratings page (1): rating distributions (driver and customer side by side)
CREATE OR REPLACE VIEW vw_rating_distribution AS
SELECT d.rating,
       d.driver_rating_count,
       COALESCE(c.customer_rating_count, 0) AS customer_rating_count
FROM (SELECT Driver_Ratings AS rating, COUNT(*) AS driver_rating_count
      FROM ola_rides WHERE Booking_Status = 'Success' GROUP BY Driver_Ratings) d
LEFT JOIN
     (SELECT Customer_Rating AS rating, COUNT(*) AS customer_rating_count
      FROM ola_rides WHERE Booking_Status = 'Success' GROUP BY Customer_Rating) c
ON d.rating = c.rating;

-- Ratings page (2): average driver vs customer rating by vehicle
CREATE OR REPLACE VIEW vw_ratings_by_vehicle AS
SELECT Vehicle_Type,
       ROUND(AVG(Driver_Ratings), 3)   AS avg_driver_rating,
       ROUND(AVG(Customer_Rating), 3)  AS avg_customer_rating
FROM ola_rides
WHERE Booking_Status = 'Success'
GROUP BY Vehicle_Type;

-- ---------------------------------------------------------------------
-- View checks: totals must match the notebook
-- ---------------------------------------------------------------------
SELECT SUM(bookings) AS total_bookings, SUM(revenue) AS total_revenue FROM vw_overall_daily;   -- 103024 | 35080467
SELECT SUM(success_booking_value) AS revenue, SUM(completed_rides) AS rides FROM vw_vehicle_summary;  -- 35080467 | 63967
SELECT SUM(revenue) AS revenue FROM vw_revenue_payment;                                         -- 35080467
SELECT * FROM vw_top_customers;
SELECT SUM(cancellations) AS cancels FROM vw_cancellation_reasons;                               -- 28933
SELECT SUM(driver_rating_count) AS d, SUM(customer_rating_count) AS c FROM vw_rating_distribution; -- 63967 | 63967