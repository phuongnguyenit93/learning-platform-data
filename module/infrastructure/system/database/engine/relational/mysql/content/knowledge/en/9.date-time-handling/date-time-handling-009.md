# DATE_ADD, DATE_SUB, TIMESTAMPDIFF, and End-of-Month Handling

## Learning Objectives

After this lesson, you can:

- Add or subtract dates and times using DATE_ADD and DATE_SUB with appropriate units.
- Calculate time differences with TIMESTAMPDIFF and distinguish it from DATEDIFF.
- Understand how MySQL adjusts dates when adding or subtracting months across months with different lengths.
- Build billing schedules, expiration dates, and recurring cycles without unintended date drift.
- Determine start-of-month, end-of-month, and monthly ranges using LAST_DAY and date arithmetic.
- Write date-range filter conditions that can leverage indexes.
- Control timezones, precision, and invalid date/time data.

Date and time calculations look simple at first glance, yet contain many rules that easily cause business discrepancies. Adding one month to the 31st does not always produce the 31st of the next month. Calculating the number of months between two dates is not the same as dividing days by 30. This lesson explains common MySQL temporal functions and how to apply them to recurring schedules, payment due dates, monthly reports, and time-based queries.

## 1. DATE_ADD and DATE_SUB

### 1.1. Basic Syntax

DATE_ADD adds a time interval to a date/time value; DATE_SUB subtracts an interval:

~~~sql
DATE_ADD(date_expression, INTERVAL value unit)
DATE_SUB(date_expression, INTERVAL value unit)
~~~

Where:

- date_expression is a DATE, DATETIME, TIMESTAMP value, or a valid date/time expression.
- value is the quantity of units to add or subtract.
- unit is the time unit, such as DAY, WEEK, MONTH, YEAR, HOUR, or MINUTE.

Example:

~~~sql
SELECT
    DATE_ADD('2024-05-10', INTERVAL 7 DAY) AS after_seven_days,
    DATE_SUB('2024-05-10', INTERVAL 7 DAY) AS before_seven_days,
    DATE_ADD('2024-05-10 09:30:00', INTERVAL 2 HOUR) AS after_two_hours,
    DATE_SUB('2024-05-10 09:30:00', INTERVAL 15 MINUTE) AS before_fifteen_minutes;
~~~

The results are 2024-05-17, 2024-05-03, 11:30 on the same day, and 09:15 on the same day, respectively.

DATE_ADD and DATE_SUB return a new date/time value; they do not modify a table column directly. To persist results, use an intentional UPDATE or INSERT.

The return type depends on the first argument and the unit. For example, adding DAY to DATE still returns DATE; adding HOUR to DATE requires representing the time component, so it returns DATETIME. If your application relies on the exact returned data type, verify with a test query on the target MySQL version.

### 1.2. Commonly Used Units

| Unit | Meaning | Example |
|---|---|---|
| MICROSECOND | Microseconds | INTERVAL 500000 MICROSECOND |
| SECOND | Seconds | INTERVAL 30 SECOND |
| MINUTE | Minutes | INTERVAL 15 MINUTE |
| HOUR | Hours | INTERVAL 2 HOUR |
| DAY | Days | INTERVAL 7 DAY |
| WEEK | Weeks | INTERVAL 2 WEEK |
| MONTH | Calendar months | INTERVAL 1 MONTH |
| QUARTER | Calendar quarters, 3 months | INTERVAL 1 QUARTER |
| YEAR | Calendar years | INTERVAL 1 YEAR |

MySQL also supports compound units such as DAY_HOUR, DAY_MINUTE, DAY_SECOND, HOUR_MINUTE, HOUR_SECOND, MINUTE_SECOND, and YEAR_MONTH. With compound units, the value must follow a specific format. Example:

~~~sql
SELECT
    DATE_ADD('2024-01-01 08:00:00',
             INTERVAL '1 02:30:00' DAY_SECOND) AS result_datetime,
    DATE_ADD('2024-01-01',
             INTERVAL '1-2' YEAR_MONTH) AS result_year_month;
~~~

A compound INTERVAL value must match the unit's exact format. When business logic only requires adding a single unit, prefer simple syntax like INTERVAL 3 DAY or INTERVAL 2 MONTH for readability and easier verification.

### 1.3. Adding/Subtracting on Table Columns

Suppose an invoice has a creation timestamp and a due timestamp:

~~~sql
CREATE TABLE invoice (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    due_at DATETIME NOT NULL,
    paid_at DATETIME NULL,
    PRIMARY KEY (invoice_id),
    KEY idx_invoice_due_at (due_at)
) ENGINE = InnoDB;
~~~

Set the due date 14 days out:

~~~sql
INSERT INTO invoice (created_at, due_at)
VALUES (
    CURRENT_TIMESTAMP,
    DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 14 DAY)
);
~~~

Extend an invoice by 3 days:

~~~sql
UPDATE invoice
SET due_at = DATE_ADD(due_at, INTERVAL 3 DAY)
WHERE invoice_id = 1001;
~~~

The WHERE clause must target the exact record. If the business enforces a rule preventing extensions past a maximum limit, check that rule inside the same transaction or appropriate update logic.

### 1.4. DATE_ADD Is Not Ordinary Arithmetic Addition

Never replace DATE_ADD by adding an integer directly to a date string. For example, adding 30 to a date expression does not mean adding 30 calendar days. Using INTERVAL lets MySQL understand calendar units and handle month transitions and leap years.

Also distinguish:

- INTERVAL 1 MONTH is one calendar month, not 30 days.
- INTERVAL 1 YEAR is one calendar year, not 365 days.
- INTERVAL 1 DAY is one calendar day; in timezone and DST contexts, one calendar day may not equal exactly 24 elapsed hours.

## 2. Rules for Adding and Subtracting Months

### 2.1. Target Month Lacks the Corresponding Day

When adding months, if the day in the source month does not exist in the target month, MySQL clamps to the last day of the target month.

Example:

~~~sql
SELECT
    DATE_ADD('2024-01-31', INTERVAL 1 MONTH) AS leap_year_result,
    DATE_ADD('2023-01-31', INTERVAL 1 MONTH) AS normal_year_result,
    DATE_SUB('2024-03-31', INTERVAL 1 MONTH) AS subtract_month_result,
    DATE_ADD('2024-01-30', INTERVAL 1 MONTH) AS january_thirtieth_result;
~~~

Results:

| Operation | Result |
|---|---|
| 2024-01-31 + 1 MONTH | 2024-02-29 |
| 2023-01-31 + 1 MONTH | 2023-02-28 |
| 2024-03-31 - 1 MONTH | 2024-02-29 |
| 2024-01-30 + 1 MONTH | 2024-02-29 |

This is a calendar adjustment. MySQL does not produce February 31 and overflow into March; the result is clamped to the last valid day of the target month.

### 2.2. Leap Years

A Gregorian year is a leap year if divisible by 4, except century years not divisible by 400. Therefore:

- 2024 is a leap year: February has 29 days.
- 2023 is not a leap year: February has 28 days.
- 2000 is a leap year.
- 1900 is not a leap year.

You can use LAST_DAY to confirm the last day of a month:

~~~sql
SELECT
    LAST_DAY('2024-02-01') AS leap_february,
    LAST_DAY('2023-02-01') AS normal_february;
~~~

### 2.3. Repeatedly Adding Months Can Cause Date Drift

A common bug is taking the newly calculated due date as the base for the next cycle. When the initial anchor is at the end of a month, adding one month at a time causes the day to drift.

~~~sql
SELECT
    DATE_ADD(
        DATE_ADD('2023-01-31', INTERVAL 1 MONTH),
        INTERVAL 1 MONTH
    ) AS repeated_addition,
    DATE_ADD('2023-01-31', INTERVAL 2 MONTH) AS anchored_addition;
~~~

Results:

| Calculation | Result |
|---|---|
| 2023-01-31 + 1 month = 2023-02-28; then + 1 month | 2023-03-28 |
| Directly calculating 2023-01-31 + 2 months from the initial anchor | 2023-03-31 |

The first addition produced 2023-02-28. When adding another month from the 28th, MySQL has no idea the business originally wanted to preserve the 31st or end-of-month; it simply adds one month to the current input.

**Design rule:** store the anchor date or original schedule rule. Compute period n directly from the initial anchor rather than chaining from the previous period's clamped date if you want to preserve the anchor day.

### 2.4. Two Different Recurring Schedule Rules

A business may want one of two rules:

**Keep the same day of month, clamping to the last day if it does not exist.**

~~~sql
SELECT DATE_ADD('2023-01-31', INTERVAL 2 MONTH) AS due_date;
~~~

The result is 2023-03-31. For the February cycle, it clamps to 2023-02-28.

**Always fall due on the last day of the month.**

~~~sql
SELECT
    LAST_DAY(DATE_ADD('2023-01-01', INTERVAL 1 MONTH)) AS february_due,
    LAST_DAY(DATE_ADD('2023-01-01', INTERVAL 2 MONTH)) AS march_due;
~~~

The results are 2023-02-28 and 2023-03-31.

The two rules behave differently for an anchor date that is not the end of the month. For example, an anchor of Jan 30 yields Feb 28 then Mar 30 when preserving the anchor day; an end-of-month rule yields Feb 28 then Mar 31. Document the exact business rule explicitly rather than inferring it from one sample case.

## 3. LAST_DAY and Start/End-of-Month Boundaries

### 3.1. Getting the Last Day of the Month

LAST_DAY(date) returns the last day of the month containing date:

~~~sql
SELECT
    LAST_DAY('2024-01-10') AS january_end,
    LAST_DAY('2024-02-10') AS february_end,
    LAST_DAY('2024-04-10') AS april_end;
~~~

The results are 2024-01-31, 2024-02-29, and 2024-04-30.

If the input is NULL or invalid, the result may be NULL or emit a warning depending on the expression and SQL mode. Validate inputs before using them in business schedules.

### 3.2. Getting the First Day of the Month

You can subtract the elapsed days in the month minus one:

~~~sql
SELECT
    DATE_SUB(
        DATE('2024-05-19'),
        INTERVAL DAYOFMONTH('2024-05-19') - 1 DAY
    ) AS month_start;
~~~

The result is 2024-05-01.

For a date/time column, the general expression is:

~~~sql
DATE_SUB(
    DATE(date_expression),
    INTERVAL DAYOFMONTH(date_expression) - 1 DAY
)
~~~

### 3.3. Getting the First Day of the Next Month

Add one day to the last day of the month:

~~~sql
SELECT
    DATE_ADD(LAST_DAY('2024-02-12'), INTERVAL 1 DAY)
        AS next_month_start;
~~~

The result is 2024-03-01.

You can obtain the current month start and next month start with this pattern:

~~~sql
SET @month_start =
    DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE()) - 1 DAY);

SET @next_month_start =
    DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT @month_start, @next_month_start;
~~~

These two boundaries are very useful for filtering data by month.

## 4. TIMESTAMPDIFF: Computing the Difference Between Two Points in Time

### 4.1. Syntax and Direction

TIMESTAMPDIFF takes a unit, a start time, and an end time:

~~~sql
TIMESTAMPDIFF(unit, datetime_expr1, datetime_expr2)
~~~

The return value is the integer number of units from datetime_expr1 to datetime_expr2—that is, the second timestamp minus the first.

~~~sql
SELECT
    TIMESTAMPDIFF(DAY, '2024-05-01', '2024-05-10') AS forward_days,
    TIMESTAMPDIFF(DAY, '2024-05-10', '2024-05-01') AS backward_days;
~~~

The results are 9 and -9. Argument order matters greatly. Swapping them flips the sign of the result.

### 4.2. Supported Units

TIMESTAMPDIFF supports the following units:

- MICROSECOND
- SECOND
- MINUTE
- HOUR
- DAY
- WEEK
- MONTH
- QUARTER
- YEAR

Example:

~~~sql
SELECT
    TIMESTAMPDIFF(HOUR,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_hours,
    TIMESTAMPDIFF(MINUTE,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_minutes,
    TIMESTAMPDIFF(SECOND,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_seconds;
~~~

The results are integers in the requested unit. Fractional remainders are truncated; for example, 5 hours 45 minutes returns 5 when measured in HOUR.

### 4.3. TIMESTAMPDIFF Does Not Return Fractional Months/Years

For MONTH and YEAR, the result represents complete calendar units according to MySQL's rules, not days divided by 30 or 365.

~~~sql
SELECT
    TIMESTAMPDIFF(MONTH, '2024-01-31', '2024-02-29')
        AS completed_months_1,
    TIMESTAMPDIFF(MONTH, '2024-01-31', '2024-03-31')
        AS completed_months_2,
    TIMESTAMPDIFF(YEAR, '2020-06-15', '2024-06-14')
        AS completed_years_before_anniversary,
    TIMESTAMPDIFF(YEAR, '2020-06-15', '2024-06-15')
        AS completed_years_on_anniversary;
~~~

The results are 0, 2, 3, and 4, respectively. From Jan 31 to Feb 29 does not count as one full month under TIMESTAMPDIFF's month rule, even though a calendar month boundary was crossed.

If the business needs elapsed calendar months, billing cycles, or months measured by end-of-month rules, define an explicit rule and test boundary cases. Do not use TIMESTAMPDIFF(MONTH) as a counter of calendar month transitions.

### 4.4. Distinguishing TIMESTAMPDIFF and DATEDIFF

DATEDIFF(expr1, expr2) returns the calendar-day difference DATE(expr1) minus DATE(expr2) in argument order: expr1 - expr2. In practice, DATEDIFF(end_date, start_date) is used to get days from start to end. The function ignores the time-of-day component.

TIMESTAMPDIFF(DAY, start, end) computes complete whole days between two date/time values, taking the time-of-day component into account.

~~~sql
SELECT
    DATEDIFF(
        '2024-01-02 01:00:00',
        '2024-01-01 23:00:00'
    ) AS calendar_day_difference,
    TIMESTAMPDIFF(
        DAY,
        '2024-01-01 23:00:00',
        '2024-01-02 01:00:00'
    ) AS full_day_difference,
    TIMESTAMPDIFF(
        HOUR,
        '2024-01-01 23:00:00',
        '2024-01-02 01:00:00'
    ) AS full_hour_difference;
~~~

The results are 1 calendar day, 0 full days, and 2 hours. Choose the function matching the business question:

| Question | Appropriate Function |
|---|---|
| How many calendar days apart are two dates, ignoring time of day? | DATEDIFF(end_date, start_date) |
| How many whole hours/minutes/seconds have elapsed? | TIMESTAMPDIFF |
| How many complete months or years per MySQL calendar rules? | TIMESTAMPDIFF(MONTH/YEAR, start, end) |
| Need to add one calendar month to a date? | DATE_ADD(..., INTERVAL 1 MONTH) |

## 5. Practical Applications

### 5.1. Calculating Age in Complete Years

With date of birth stored in a DATE column:

~~~sql
SELECT
    customer_id,
    birth_date,
    TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) AS age_years
FROM customer;
~~~

TIMESTAMPDIFF(YEAR, ...) returns complete years according to calendar rules. If the business has a special policy for February 29 birthdays in non-leap years, explicitly define which date counts as the anniversary and test that case.

### 5.2. Calculating Ticket Processing Time

~~~sql
SELECT
    ticket_id,
    created_at,
    closed_at,
    TIMESTAMPDIFF(MINUTE, created_at, closed_at) AS processing_minutes
FROM support_ticket
WHERE closed_at IS NOT NULL;
~~~

If the ticket is not yet closed, closed_at is NULL and the calculation returns NULL. Do not blindly replace NULL with NOW() in every report if the metric is meant to measure only closed tickets. For open-duration reports, COALESCE or a separate expression can be used, provided the metric is named clearly.

### 5.3. Calculating Expiration Dates

~~~sql
SELECT
    subscription_id,
    started_on,
    DATE_ADD(started_on, INTERVAL 1 YEAR) AS expires_on
FROM subscription;
~~~

If the start date is February 29 in a leap year, the expiration date one year later adjusts according to the target year's February calendar. The business must decide whether expiration is the clamped date, the end of the month, or the end of that day. This is a product decision, not purely an SQL decision.

### 5.4. Monthly Revenue Report

Suppose the payment table has a DATETIME paid_at column and an index:

~~~sql
CREATE INDEX idx_payment_paid_at
ON payment (paid_at);
~~~

Filter one month using a half-open interval:

~~~sql
SELECT
    SUM(amount) AS monthly_revenue
FROM payment
WHERE paid_at >= '2024-02-01 00:00:00'
  AND paid_at <  '2024-03-01 00:00:00';
~~~

This condition captures every instant from the start of February to right before the start of March. It avoids guessing end-of-day times like 23:59:59.999999 and can utilize the index on paid_at.

Dynamically compute the start of the current month and next month:

~~~sql
SET @month_start =
    DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE()) - 1 DAY);

SET @next_month_start =
    DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT SUM(amount) AS monthly_revenue
FROM payment
WHERE paid_at >= @month_start
  AND paid_at < @next_month_start;
~~~

Avoid writing:

~~~sql
WHERE DATE(paid_at) BETWEEN '2024-02-01' AND '2024-02-29'
~~~

Wrapping an indexed column in DATE() usually prevents the optimizer from performing an ordinary index range scan on paid_at as efficiently as a range predicate. Place computations on the constant/variable side and leave the column bare in the predicate.

## 6. End-of-Month in Recurring Business Logic

### 6.1. Invoices Due on the Last Day of the Month

Some contracts stipulate invoices fall due on the last day of every month. Use LAST_DAY:

~~~sql
SELECT
    DATE('2024-01-15') AS anchor_date,
    LAST_DAY(DATE('2024-01-15')) AS first_due_date,
    LAST_DAY(DATE_ADD('2024-01-15', INTERVAL 1 MONTH))
        AS next_due_date;
~~~

This retrieves the last day of the anchor's month and the following month. For the nth month from the initial baseline, calculate directly from the anchor:

~~~sql
SELECT
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 1 MONTH)) AS period_1,
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 2 MONTH)) AS period_2,
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 3 MONTH)) AS period_3;
~~~

### 6.2. Fixed Day Due Date, Clamped to Month End When Shorter

For example, a contract starts on the 30th or 31st and keeps that day of the month, falling back to the last day if the target month lacks it. Calculate from the original anchor date:

~~~sql
SELECT
    DATE_ADD('2024-01-30', INTERVAL 1 MONTH) AS period_1,
    DATE_ADD('2024-01-30', INTERVAL 2 MONTH) AS period_2,
    DATE_ADD('2024-01-30', INTERVAL 3 MONTH) AS period_3;
~~~

The results are Feb 29, Mar 30, and Apr 30. With an anchor of 2024-01-31, the corresponding cycles are Feb 29, Mar 31, and Apr 30. Each period is computed from the same anchor date, avoiding drift from a previously clamped date.

### 6.3. Counting Days Remaining Until Due Date

~~~sql
SELECT
    invoice_id,
    due_at,
    TIMESTAMPDIFF(DAY, CURRENT_TIMESTAMP, due_at) AS whole_days_remaining
FROM invoice
WHERE due_at >= CURRENT_TIMESTAMP;
~~~

The value is the integer number of complete days remaining relative to the current timestamp. If classification by the user's calendar date is needed, convert to the business timezone and apply calendar-date rules. Do not confuse “1 calendar day remaining” with “at least 24 hours remaining”.

## 7. DATE, DATETIME, TIMESTAMP, and Timezones

### 7.1. Choosing the Right Type for the Question

| Type | Common Meaning | Notes |
|---|---|---|
| DATE | A calendar date, without time | Birthdays, issue dates, holidays |
| DATETIME | Date and time per application convention | Does not auto-convert by timezone on write/read |
| TIMESTAMP | An instant; MySQL converts between session time zone and UTC on write/read | Suitable for instants when connection timezone is controlled |
| TIME | Time of day or duration per MySQL semantics | Does not replace a full date and time |

NOW() returns the time in the session time_zone. UTC_TIMESTAMP() returns UTC time. CURRENT_DATE()/CURDATE() returns the current date in the session timezone. If connections use different timezones, current-time functions can return different dates or hours.

### 7.2. DATETIME Does Not Auto-Convert Timezones; TIMESTAMP Does

DATETIME stores the date and time components as sent. MySQL does not automatically know whether they represent UTC or local time. TIMESTAMP converts from session time_zone to UTC on write and from UTC to session time_zone on read.

Timezone inspection example:

~~~sql
SELECT
    @@session.time_zone AS session_time_zone,
    @@global.time_zone AS global_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now,
    CURDATE() AS session_date;
~~~

An application should standardize connection timezones, typically choosing UTC for flows storing instants. When displaying to users, convert to local timezone in the application layer or use CONVERT_TZ with loaded and updated timezone tables.

### 7.3. Daylight Saving Time (DST)

In timezones with DST, a local day can be 23 or 25 hours long during seasonal transitions. This must be accounted for when working with TIMESTAMP in a DST session time_zone or converting UTC instants to local time. DATETIME itself carries no timezone, and arithmetic on DATETIME operates solely on the stored date/time components. Therefore:

- A calendar day does not always equal 24 actual elapsed hours.
- Adding 1 calendar DAY can differ in absolute elapsed time from adding 24 HOUR when handling instants in a DST timezone.
- Certain local times may not exist or may occur twice during clock transitions.

If the business relies on local date/time, store the named timezone (e.g. an IANA zone) alongside the rule or user configuration. Test DST transition days. Do not use a fixed offset like +07:00 in place of a timezone with changing rules if the system serves multiple regions.

For operational schedules, holidays, or due dates by local calendar, clarify whether the calculation is by calendar days or exact elapsed duration. These are two distinct requirements.

## 8. NULL, Invalid Data, and Precision

### 8.1. NULL Propagation in Calculations

If a date/time argument is NULL, DATE_ADD, DATE_SUB, and TIMESTAMPDIFF normally return NULL. This is useful to represent “no end date yet”, though it must be handled in filter predicates and reports.

~~~sql
SELECT
    TIMESTAMPDIFF(DAY, created_at, closed_at) AS elapsed_days
FROM support_ticket;
~~~

Open tickets have a NULL closed_at, so elapsed_days is NULL rather than 0. If substituting COALESCE(closed_at, NOW()), verify that the metric genuinely measures “time elapsed up to now” and name the column accordingly.

### 8.2. Zero Dates and Invalid Dates

Avoid values such as 0000-00-00 or nonexistent calendar dates. Whether they are accepted, warned, or rejected depends on version and SQL mode. Use strict SQL mode, validate inputs, and never assume every date string automatically converts into a valid date.

Inspect dirty data before converting string columns to DATE/DATETIME. STR_TO_DATE can return NULL or warnings on invalid inputs depending on version and mode; inspect results and run SHOW WARNINGS immediately afterward.

### 8.3. Fractional Seconds Precision

DATETIME and TIMESTAMP support fractional seconds precision from 0 to 6. If a column stores microseconds, account for precision in expressions and inputs.

~~~sql
SELECT
    TIMESTAMPDIFF(
        MICROSECOND,
        '2024-05-01 10:00:00.000000',
        '2024-05-01 10:00:00.250000'
    ) AS elapsed_microseconds;
~~~

The result is 250000. When filtering time ranges, half-open intervals are generally safer than fabricating end-of-day bounds with fixed fractional digits.

## 9. Performance and Index Usage

Temporal queries typically filter on DATE, DATETIME, or TIMESTAMP columns. If the column is indexed, keep the column bare in range predicates:

~~~sql
SELECT invoice_id, due_at
FROM invoice
WHERE due_at >= CURRENT_TIMESTAMP
  AND due_at < DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY);
~~~

Inspect the execution plan:

~~~sql
EXPLAIN
SELECT invoice_id, due_at
FROM invoice
WHERE due_at >= '2024-05-01 00:00:00'
  AND due_at <  '2024-06-01 00:00:00';
~~~

Avoid wrapping columns in DATE(), YEAR(), MONTH(), or TIMESTAMPDIFF() inside WHERE when aiming for a range scan on an ordinary index. For example, instead of:

~~~sql
WHERE YEAR(created_at) = 2024
  AND MONTH(created_at) = 5
~~~

write:

~~~sql
WHERE created_at >= '2024-05-01 00:00:00'
  AND created_at <  '2024-06-01 00:00:00'
~~~

Half-open conditions also avoid end-of-day precision issues and work cleanly for both DATETIME(0) and DATETIME(6).

If you must filter frequently by calendar date on a DATETIME/TIMESTAMP column without changing queries, consider a generated column or functional index on supporting versions. However, evaluate storage overhead, write cost, and compatibility before adding them.

## 10. Workflow for Choosing the Right Calculation

Before writing SQL, identify the exact question:

| Business Requirement | Calculation |
|---|---|
| Add 10 days to creation date | DATE_ADD(created_at, INTERVAL 10 DAY) |
| Subtract 2 calendar months | DATE_SUB(value, INTERVAL 2 MONTH) |
| Get end of month | LAST_DAY(value) |
| Get start of month | DATE_SUB(DATE(value), INTERVAL DAYOFMONTH(value) - 1 DAY) |
| Get start of next month | DATE_ADD(LAST_DAY(value), INTERVAL 1 DAY) |
| Calendar days between two dates | DATEDIFF(end_date, start_date) |
| Complete hours elapsed | TIMESTAMPDIFF(HOUR, start_at, end_at) |
| Complete months/years elapsed | TIMESTAMPDIFF(MONTH/YEAR, start_at, end_at) |
| Filter all instants within a month | created_at >= month_start AND created_at < next_month_start |
| Recurring schedule on last day of month | LAST_DAY(DATE_ADD(anchor_month, INTERVAL n MONTH)) |
| Recurring schedule preserving anchor day | DATE_ADD(anchor_date, INTERVAL n MONTH) |

In particular, clarify whether “one month” means a calendar month, 30 days, or a complete anniversary interval between two points. These concepts are not interchangeable.

## 11. Practice Exercises

### Exercise 1: Testing DATE_ADD and DATE_SUB

Run additions/subtractions of 7 DAY, 2 WEEK, 1 MONTH, 1 QUARTER, and 1 YEAR. Test both DATE and DATETIME to observe the resulting return types.

### Exercise 2: Checking End-of-Month and Leap Years

Calculate 1 MONTH after January 28, 29, 30, and 31 in both leap and non-leap years. Compare with LAST_DAY.

### Exercise 3: Spotting Date Drift

Compare adding INTERVAL 1 MONTH twice sequentially versus adding INTERVAL 2 MONTH directly from the same Jan 31 anchor. Explain why the results differ.

### Exercise 4: Computing Differences

Compute TIMESTAMPDIFF(DAY), HOUR, MINUTE, MONTH, and YEAR for two instants with different times of day. Compare with DATEDIFF and explain which time portions are ignored or truncated.

### Exercise 5: Indexed Monthly Reporting

Create an index on payment.paid_at. Write a query retrieving monthly revenue using a half-open range. Use EXPLAIN to compare against a query using YEAR(paid_at) and MONTH(paid_at) in WHERE.

### Exercise 6: Designing a Billing Schedule

Design a schedule for customers signing up on the 29th, 30th, or 31st. Write both variants: preserving the anchor day and always falling due at month end. Record results in February, March, and leap years.

### Exercise 7: Testing Timezones

Set session time_zone to UTC and a local DST timezone in a test environment. Compare NOW(), UTC_TIMESTAMP(), adding 1 DAY, and adding 24 HOUR around the DST transition. Record differences and restore the original timezone.

## Conclusion

DATE_ADD and DATE_SUB perform arithmetic according to calendar units or durations specified by INTERVAL. TIMESTAMPDIFF returns integer units between two timestamps and is not a substitute for counting calendar month boundaries or calendar days. LAST_DAY together with start-of-month boundaries handles recurring cycles and month-end reporting cleanly.

For recurring schedules, preserve the anchor date and define end-of-month rules explicitly to prevent date drift. For monthly queries, use half-open ranges to preserve index usage. Finally, standardize timezones and test leap years, DST, NULLs, and fractional-second precision so SQL results match business rules.
