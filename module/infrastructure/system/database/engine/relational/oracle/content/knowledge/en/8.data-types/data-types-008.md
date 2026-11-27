# INTERVAL YEAR TO MONTH and INTERVAL DAY TO SECOND

In Oracle Database, the two data types **INTERVAL YEAR TO MONTH** and **INTERVAL DAY TO SECOND** represent **time durations** rather than specific points in time. They are suitable when modeling a contract with an 18-month cycle, a job taking 2 days and 3 hours, a session running for 90.5 seconds, or a term added to a start date/time.

A crucial point is that Oracle **separates calendar intervals (years, months)** from **day-to-second intervals (days, hours, minutes, seconds)**. A month does not have a fixed number of days, so these two interval groups cannot be implicitly converted into one another. Understanding the difference prevents bugs when computing contract expiration dates, renewal schedules, processing durations, deadlines, or datetime subtraction results.

## 1. How Does INTERVAL Differ from DATE and TIMESTAMP?

| Oracle Type | Expresses | Example Meaning |
| --- | --- | --- |
| **DATE** | A date/time; Oracle DATE also stores hours, minutes, and seconds | Order created at 09:30:00 on 15/01/2024 |
| **TIMESTAMP** | A date/time with fractional seconds; also has timezone variants | Event log timestamp 09:30:00.125 |
| **INTERVAL YEAR TO MONTH** | Length in years and months | Renewal cycle of 1 year 6 months |
| **INTERVAL DAY TO SECOND** | Length in days, hours, minutes, seconds, and fractional seconds | Job completed after 1 day 2 hours 30 minutes |
| **NUMBER** | Numeric quantity; carries time meaning only by explicit convention | Configured minutes = 90, or DATE minus DATE measured in days |

A **point in time** answers "when?", whereas an **interval** answers "how long?" or "by how much calendar shift?". Common operations include adding an interval to a DATE/TIMESTAMP to find another point in time, subtracting two timestamps to measure elapsed time, or comparing two intervals in the same family.

~~~text
Start TIMESTAMP                 + INTERVAL DAY TO SECOND
2024-05-10 08:00:00             + 0 days 02:30:00
                 |
                 v
End TIMESTAMP
2024-05-10 10:30:00

Start DATE                      + INTERVAL YEAR TO MONTH
2024-01-15                      + 0 years 3 months
                 |
                 v
End DATE
2024-04-15
~~~

Although both express "time", **INTERVAL YEAR TO MONTH cannot by default equal a fixed number of seconds**, and **INTERVAL DAY TO SECOND is not a way to specify calendar months**. For example, February in a leap year has 29 days, whereas March has 31 days.

## 2. INTERVAL YEAR TO MONTH: Years and Months

### 2.1. Structure and Meaning

This type contains two fields:

- **YEAR**: number of years in the interval.
- **MONTH**: remaining months in the interval component when expressed as YEAR TO MONTH.

Column declaration:

~~~sql
CREATE TABLE hop_dong_demo (
    ma_hop_dong NUMBER(6) PRIMARY KEY,
    chu_ky      INTERVAL YEAR(3) TO MONTH NOT NULL
);
~~~

In **YEAR(3)**, the 3 is the **leading field precision**: it allows up to three digits in the leading year field of the interval. It is not "three decimal places". The column can store intervals like 1 year 6 months or 125 years 11 months within the supported limits.

Full type syntax:

~~~sql
INTERVAL YEAR [(year_precision)] TO MONTH
~~~

When omitted, **year_precision defaults to 2**. In Oracle, the leading field precision limit supports up to 9 digits. Choose precision based on the data domain: contracts lasting a few months differ from a simulation dataset spanning hundreds of years.

### 2.2. YEAR TO MONTH Literals

~~~sql
-- 1 year 6 months
SELECT INTERVAL '1-6' YEAR TO MONTH AS chu_ky
FROM dual;

-- 3 years, no extra months
SELECT INTERVAL '3' YEAR AS ba_nam
FROM dual;

-- 9 months
SELECT INTERVAL '9' MONTH AS chin_thang
FROM dual;

-- 123 years 11 months: requires year precision of at least 3
SELECT INTERVAL '123-11' YEAR(3) TO MONTH AS ky_dai
FROM dual;

-- Negative interval: 6 months back
SELECT -INTERVAL '6' MONTH AS lui_sau_thang
FROM dual;
~~~

The **YEAR**, **MONTH**, and **YEAR TO MONTH** forms all construct values in the year–month interval family with their corresponding precision/representation.

For YEAR TO MONTH literals, the month component after the hyphen is **0–11**. To express 14 months, write **1 year 2 months** or use the conversion function so Oracle normalizes it:

~~~sql
SELECT INTERVAL '1-2' YEAR TO MONTH AS mot_nam_hai_thang
FROM dual;

SELECT NUMTOYMINTERVAL(14, 'MONTH') AS muoi_bon_thang
FROM dual;
~~~

Do not write literals like **INTERVAL '1-14' YEAR TO MONTH** to mean 1 year 14 months; the month component 14 exceeds the valid range for YEAR TO MONTH. Just like calendar months, subfields must stay within their valid ranges.

### 2.3. Positive, Negative, and Zero

~~~sql
SELECT INTERVAL '0-0' YEAR TO MONTH AS khong_thang,
       INTERVAL '2-3' YEAR TO MONTH AS hai_nam_ba_thang,
       -INTERVAL '2-3' YEAR TO MONTH AS am_hai_nam_ba_thang
FROM dual;
~~~

The minus sign applies to the **entire interval**, not subtracting years and adding months independently. When a UI displays or parses signed intervals, establish an explicit convention—either signed total months or signed year/month pairs—instead of splitting client-formatted display strings.

### 2.4. Suitable Use Cases

- Renewal cycles: 1 month, 6 months, 1 year.
- Ages or terms defined in **calendar years and months**.
- Warranty periods or contract terms when business rules use calendar months.
- Recurring jobs running "every N months", rather than "every N × 30 days".

Note: a contract that "expires after one month" still needs explicit rules for **month-end dates**; choosing an interval type alone does not resolve all business semantics.

## 3. INTERVAL DAY TO SECOND: Days, Hours, Minutes, Seconds

### 3.1. Structure and Precision

This type represents a time span across **DAY, HOUR, MINUTE, SECOND**, where SECOND may include fractional seconds.

~~~sql
CREATE TABLE cong_viec_demo (
    ma_cong_viec NUMBER(6) PRIMARY KEY,
    thoi_luong   INTERVAL DAY(3) TO SECOND(3) NOT NULL
);
~~~

With **DAY(3) TO SECOND(3)**:

- **DAY(3)**: the leading day field has up to three digits.
- **SECOND(3)**: fractional seconds have three digits of precision, corresponding to milliseconds.
- Hour, minute, and second components must lie within valid ranges for the interval structure; days is the leading field and can exceed one day.

Full syntax:

~~~sql
INTERVAL DAY [(day_precision)] TO SECOND [(fractional_seconds_precision)]
~~~

The common defaults are **DAY(2)** and **SECOND(6)** when precision is omitted. In Oracle, both leading precision and fractional seconds precision can be declared up to 9. If the application measures time in milliseconds, **SECOND(3)** expresses intent more clearly than keeping unnecessary extra fractional digits.

### 3.2. DAY TO SECOND Literals

~~~sql
-- 1 day, 2 hours, 3 minutes, 4 seconds, and 125 milliseconds
SELECT INTERVAL '1 02:03:04.125' DAY TO SECOND(3) AS khoang_1
FROM dual;

-- 3 days
SELECT INTERVAL '3' DAY AS ba_ngay
FROM dual;

-- 5 hours
SELECT INTERVAL '5' HOUR AS nam_gio
FROM dual;

-- 90 minutes
SELECT INTERVAL '90' MINUTE AS chin_muoi_phut
FROM dual;

-- 30.250 seconds
SELECT INTERVAL '30.250' SECOND(3) AS ba_muoi_giay
FROM dual;

-- 123 days requires sufficiently large leading precision
SELECT INTERVAL '123 04:05:06.789' DAY(3) TO SECOND(3) AS khoang_dai
FROM dual;
~~~

Literals whose leading field is HOUR, MINUTE, or SECOND still belong to the **INTERVAL DAY TO SECOND** family. When using the **DAY TO SECOND** form, the leading day field can hold many days, while hours are typically 0–23 and minutes/seconds 0–59 before fractional seconds.

Do not write **INTERVAL '1 25:00:00' DAY TO SECOND** when intending 1 day 25 hours. Normalize it to 2 days 1 hour or use **NUMTODSINTERVAL(25, 'HOUR')** so Oracle computes the equivalent interval.

### 3.3. Fractional Seconds

~~~sql
SELECT INTERVAL '0 00:00:01.250' DAY TO SECOND(3) AS mot_phay_hai_lam_giay
FROM dual;

SELECT INTERVAL '0 00:00:01.123456' DAY TO SECOND(6) AS vi_giay
FROM dual;

SELECT INTERVAL '0 00:00:01.123456789' DAY TO SECOND(9) AS nano_giay
FROM dual;
~~~

Storage precision is a property of the Oracle data type/value. It **does not prove that measuring hardware, the OS clock, or real events have nanosecond accuracy**. If the upstream source only records time to milliseconds, declaring SECOND(9) creates no extra real information.

### 3.4. Negative, Zero, and Unknown Intervals

~~~sql
SELECT -INTERVAL '0 00:15:00' DAY TO SECOND AS cham_hon_15_phut
FROM dual;

SELECT INTERVAL '0 00:00:00' DAY TO SECOND AS bang_khong
FROM dual;
~~~

**NULL** means the duration was not provided or is unknown in the data model; **INTERVAL 0** means the duration is definitively zero. The two must be handled differently in calculations and reports.

## 4. Direct Comparison of the Two INTERVAL Families

| Criterion | INTERVAL YEAR TO MONTH | INTERVAL DAY TO SECOND |
| --- | --- | --- |
| Units | Years, months | Days, hours, minutes, seconds, fractional seconds |
| Nature | Calendar interval | Elapsed interval convertible to total seconds (with 24-hour days) |
| Example | 1 year 6 months | 2 days 3 hours 15 minutes |
| Column | INTERVAL YEAR(3) TO MONTH | INTERVAL DAY(4) TO SECOND(3) |
| Literal | INTERVAL '1-6' YEAR TO MONTH | INTERVAL '2 03:15:00' DAY TO SECOND |
| Numeric constructor | NUMTOYMINTERVAL | NUMTODSINTERVAL |
| String constructor | TO_YMINTERVAL | TO_DSINTERVAL |
| Typical addition | TIMESTAMP + month cycle | TIMESTAMP + processing duration |
| Characteristic pitfall | Month-end dates, leap years | Fractional-second precision, durations, and timezones |

There is no general rule that **1 month = 30 days** or **1 year = 365 days**. Such conversions apply only when a business defines a special convention, not as default Oracle interval semantics.

## 5. Adding and Subtracting INTERVAL with DATE and TIMESTAMP

### 5.1. Adding Year–Month Intervals to a Point in Time

~~~sql
SELECT DATE '2024-01-15' + INTERVAL '2' MONTH AS sau_hai_thang
FROM dual;

SELECT TIMESTAMP '2024-01-15 09:30:00'
       + INTERVAL '1-6' YEAR TO MONTH AS sau_mot_nam_sau_thang
FROM dual;
~~~

In the first example, the date shifts from **15/01/2024** to **15/03/2024**. The second shifts the calendar by 1 year 6 months while preserving the time component when the resulting date is valid.

### 5.2. Month-End Trap: INTERVAL Differs from ADD_MONTHS

Consider January 31, 2024:

~~~sql
-- Intentionally illustrates a nonexistent-date error case:
SELECT DATE '2024-01-31' + INTERVAL '1' MONTH AS ngay_moi
FROM dual;
~~~

The date **31/02/2024** does not exist. In this case, adding an INTERVAL YEAR TO MONTH can raise an invalid-date error, such as **ORA-01839**.

Oracle provides **ADD_MONTHS** with dedicated month-end handling rules:

~~~sql
SELECT ADD_MONTHS(DATE '2024-01-31', 1) AS ngay_het_han
FROM dual;
~~~

The result is **29/02/2024** because 2024 is a leap year and the function applies month-end clamping. Similarly, adding 12 months to 29/02/2024 with ADD_MONTHS lands on the last day of February 2025 per the function's rules.

**Never treat adding `INTERVAL '1' MONTH` and `ADD_MONTHS(..., 1)` as always equivalent at boundary dates.** When implementing billing cycles, contract expirations, notification schedules, or renewals, specify month-end rules explicitly and pick the right mechanism.

### 5.3. Adding Day–Second Intervals

~~~sql
SELECT TIMESTAMP '2024-02-28 23:59:30.000'
       + INTERVAL '0 00:01:00.250' DAY TO SECOND(3) AS sau_mot_phut
FROM dual;
~~~

The result as a zoneless timestamp is **2024-02-29 00:00:30.250**. DAY TO SECOND expresses elapsed time far more cleanly than adding fractional days to a DATE when hours, minutes, and fractional seconds are involved.

~~~sql
SELECT TIMESTAMP '2024-03-10 10:00:00'
       - INTERVAL '45' MINUTE AS tru_bon_muoi_lam_phut
FROM dual;
~~~

You can place a minus sign before a literal or subtract an interval from a timestamp. Notably, **TIMESTAMP should not be manipulated by adding plain numbers the way DATE adds days**. Use intervals to state the time unit explicitly.

### 5.4. DATE Subtraction and TIMESTAMP Subtraction Differ

~~~sql
-- DATE minus DATE returns NUMBER in days.
SELECT DATE '2024-03-02' - DATE '2024-03-01' AS so_ngay
FROM dual;

-- TIMESTAMP minus TIMESTAMP returns INTERVAL DAY TO SECOND.
SELECT TIMESTAMP '2024-03-02 01:30:00'
       - TIMESTAMP '2024-03-01 00:00:00' AS khoang_thoi_gian
FROM dual;
~~~

The first query returns **NUMBER = 1**. The second returns an interval equivalent to **1 day 1 hour 30 minutes**. This is a major difference when writing SQL to measure latency:

- For two DATEs, the difference is a number of days, potentially fractional due to hours/minutes/seconds.
- For two TIMESTAMPs, the difference is an INTERVAL DAY TO SECOND value from which you can EXTRACT days, hours, minutes, and seconds.
- When mixing DATE and TIMESTAMP, cast explicitly to control the result type.

Example casting DATE to TIMESTAMP:

~~~sql
SELECT CAST(DATE '2024-03-02' AS TIMESTAMP)
       - CAST(DATE '2024-03-01' AS TIMESTAMP) AS khoang_ngay
FROM dual;
~~~

### 5.5. Notes on Timezones and Daylight Saving Time

Plain **TIMESTAMP** carries no timezone information; **TIMESTAMP WITH TIME ZONE** and **TIMESTAMP WITH LOCAL TIME ZONE** have distinct storage/conversion semantics. When adding intervals across daylight saving time (DST) boundaries on timezone-aware data, clarify the exact intent:

- "After exactly 24 elapsed hours" can differ from "at the same local clock time on the next calendar day."
- "Renew after one calendar month" differs from "after 30 days × 24 hours."
- Outcomes can depend on timezone rules, timestamp type, session settings, and transition policies.

Do not use zoneless TIMESTAMP examples to infer DST behavior in production apps. For timezone-sensitive logic, test directly with the deployed timestamp type and timezone region.

## 6. Functions for Constructing and Converting INTERVALs

Oracle provides helpful functions when inputs are numbers or strings rather than hardcoded SQL literals.

### 6.1. NUMTOYMINTERVAL: Years/Months to YEAR TO MONTH

~~~sql
SELECT NUMTOYMINTERVAL(18, 'MONTH') AS ky_mot_nam_sau_thang
FROM dual;

SELECT NUMTOYMINTERVAL(2, 'YEAR') AS ky_hai_nam
FROM dual;
~~~

This function takes a **NUMBER** and a unit such as YEAR or MONTH, returning an INTERVAL YEAR TO MONTH. For 18 months, Oracle represents the equivalent 1 year 6 months. It fits well when month counts come from configuration columns or Java bind variables.

### 6.2. NUMTODSINTERVAL: Days/Hours/Minutes/Seconds

~~~sql
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS chin_muoi_phut
FROM dual;

SELECT NUMTODSINTERVAL(1.25, 'DAY') AS mot_phay_hai_lam_ngay
FROM dual;

SELECT NUMTODSINTERVAL(5400.125, 'SECOND') AS nam_nghin_bon_tram_giay
FROM dual;
~~~

Common units include **DAY, HOUR, MINUTE, SECOND**. The input number can be fractional when semantically appropriate, such as 1.25 days or 5400.125 seconds.

Constructing intervals from numeric parameters is safer and clearer than concatenating external values into unvalidated literal strings.

### 6.3. TO_YMINTERVAL and TO_DSINTERVAL

~~~sql
SELECT TO_YMINTERVAL('01-06') AS ky_mot_nam_sau_thang
FROM dual;

SELECT TO_DSINTERVAL('1 02:03:04.125') AS khoang_ngay_gio
FROM dual;
~~~

Both functions parse properly formatted strings into the corresponding interval type. Inputs must match valid syntax. Never write custom string slicing assuming interval output always has a fixed character width across drivers and versions.

### 6.4. Similar Functions with Different Semantics

| Function / Operation | Result | Difference |
| --- | --- | --- |
| **ADD_MONTHS(date, n)** | DATE | Has dedicated month-end clamping rules |
| **MONTHS_BETWEEN(date1, date2)** | NUMBER | Returns difference in months possibly with a fractional part, not directly INTERVAL YEAR TO MONTH |
| **DATE - DATE** | NUMBER | Difference in days |
| **TIMESTAMP - TIMESTAMP** | INTERVAL DAY TO SECOND | Elapsed interval with day–second fields |
| **NUMTOYMINTERVAL(n, unit)** | INTERVAL YEAR TO MONTH | From numeric months or years |
| **NUMTODSINTERVAL(n, unit)** | INTERVAL DAY TO SECOND | From numeric days, hours, minutes, seconds |

Computing "age in years/months", "months between two dates", or "after n calendar months" must follow explicit business rules; having INTERVAL types available does not automatically decide age rounding or month-end proration.

## 7. Extracting and Calculating with INTERVALs

### 7.1. EXTRACT Each Field

The **EXTRACT** function retrieves individual components of an interval:

~~~sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-9' YEAR TO MONTH) AS so_nam,
       EXTRACT(MONTH FROM INTERVAL '2-9' YEAR TO MONTH) AS so_thang
FROM dual;

SELECT EXTRACT(DAY FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS ngay,
       EXTRACT(HOUR FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS gio,
       EXTRACT(MINUTE FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS phut,
       EXTRACT(SECOND FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS giay
FROM dual;
~~~

The first query returns **2 years** and **9 months**. The second returns **3 days, 4 hours, 5 minutes, and 6.125 seconds**. The SECOND field can include fractional digits. Do not attempt to EXTRACT YEAR from DAY TO SECOND or EXTRACT DAY from YEAR TO MONTH, because the two interval families hold different fields.

### 7.2. Converting Within the Same Interval Family

A YEAR TO MONTH interval can be converted to total months:

~~~sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-9' YEAR TO MONTH) * 12
       + EXTRACT(MONTH FROM INTERVAL '2-9' YEAR TO MONTH)
       AS tong_thang
FROM dual;
~~~

Result: **33 months**. This is helpful for comparing cycles or exporting data to systems that only understand integer month counts.

A DAY TO SECOND interval can be converted to total seconds:

~~~sql
SELECT EXTRACT(DAY FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 86400
       + EXTRACT(HOUR FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 3600
       + EXTRACT(MINUTE FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 60
       + EXTRACT(SECOND FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3))
       AS tong_giay
FROM dual;
~~~

Result: **93784.125 seconds**. The 24-hour/day formula matches DAY TO SECOND interval fields and is not a calendar-month-to-seconds conversion. For negative intervals, verify how signs are represented on extracted fields and test accordingly instead of concatenating fields as strings.

### 7.3. Comparing and Adding/Subtracting Intervals

~~~sql
-- Same YEAR TO MONTH family
SELECT CASE
         WHEN INTERVAL '1-0' YEAR TO MONTH
              > INTERVAL '9' MONTH
         THEN 'Longer'
         ELSE 'Not longer'
       END AS so_sanh_thang
FROM dual;

-- Same DAY TO SECOND family
SELECT INTERVAL '1 02:00:00' DAY TO SECOND
       + INTERVAL '0 03:30:00' DAY TO SECOND AS tong_thoi_luong
FROM dual;
~~~

The first statement shows that 1 year is **longer than 9 months in calendar months**. The second returns an interval equal to **1 day 5 hours 30 minutes**.

Do not directly apply comparisons like "1 month > 30 days" across YEAR TO MONTH and DAY TO SECOND because no global mapping exists between the two domains. If a comparison is genuinely needed, anchor both to a **concrete reference timestamp and calendar rule**, then compare the resulting points in time.

## 8. Column Design and Sample Oracle Data

Example schedule table showing that **month-based cycle** and **day–second duration** are two distinct attributes:

~~~sql
CREATE TABLE lich_dinh_ky (
    ma_lich       NUMBER(6) CONSTRAINT pk_lich_dinh_ky PRIMARY KEY,
    ten_cong_viec VARCHAR2(100 CHAR) NOT NULL,
    bat_dau       TIMESTAMP(3) NOT NULL,
    chu_ky        INTERVAL YEAR(3) TO MONTH,
    thoi_luong    INTERVAL DAY(3) TO SECOND(3)
);
~~~

Here:

- **BAT_DAU** is a start timestamp with millisecond precision.
- **CHU_KY** indicates after how many calendar years/months the next recurrence occurs.
- **THOI_LUONG** indicates how long a single job execution takes.
- `CHU_KY` or `THOI_LUONG` may be **NULL** when undefined or not applicable, depending on business semantics.

### 8.1. Load Sample Data

~~~sql
INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    1, 'Monthly renewal',
    TIMESTAMP '2024-01-15 09:30:00.000',
    INTERVAL '0-1' YEAR TO MONTH,
    INTERVAL '0 01:30:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    2, 'Leap-day maintenance',
    TIMESTAMP '2024-02-28 23:59:30.000',
    INTERVAL '1-0' YEAR TO MONTH,
    INTERVAL '1 00:00:45.125' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    3, 'One-time job',
    TIMESTAMP '2024-06-01 08:00:00.000',
    NULL,
    INTERVAL '0 00:00:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    4, 'Duration not yet estimated',
    TIMESTAMP '2024-07-01 08:00:00.000',
    INTERVAL '0-6' YEAR TO MONTH,
    NULL
);

COMMIT;
~~~

Purpose of each sample row:

| ID | Cycle | Duration | Test Case |
| --- | --- | --- | --- |
| 1 | 1 month | 1 hour 30 minutes | Calendar cycle and execution duration differ |
| 2 | 1 year | 1 day 45.125 seconds | Crosses leap day and includes fractional seconds |
| 3 | NULL | 0 seconds | No recurrence cycle, but duration is known to be 0 |
| 4 | 6 months | NULL | Has a cycle, but duration is unknown |

### 8.2. Compute Next Run and End Time

~~~sql
SELECT ma_lich,
       ten_cong_viec,
       TO_CHAR(
           bat_dau,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS bat_dau_text,
       bat_dau + chu_ky AS lan_lap_ke_tiep,
       bat_dau + thoi_luong AS thoi_diem_ket_thuc
FROM lich_dinh_ky
ORDER BY ma_lich;
~~~

For ID 1, the next run is **15/02/2024 09:30:00**, and the run ends at **15/01/2024 11:00:00**. For ID 2, the duration pushes completion to **01/03/2024 00:00:15.125** because 2024 includes 29/02. Adding **NULL** still yields NULL; Oracle does not substitute a zero duration.

When displaying timestamp columns, SQL client formatting may depend on NLS and UI settings. Use **TO_CHAR(..., 'YYYY-MM-DD HH24:MI:SS.FF3')** when you need stable formatted strings for comparison.

### 8.3. Find Jobs Whose Duration Exceeds a Threshold

~~~sql
SELECT ma_lich, ten_cong_viec
FROM lich_dinh_ky
WHERE thoi_luong > NUMTODSINTERVAL(90, 'MINUTE')
ORDER BY ma_lich;
~~~

ID **2** runs longer than 90 minutes. ID 1 is exactly 90 minutes so it does not satisfy **>**; ID 3 is 0; ID 4 is NULL so it does not match the WHERE condition.

To find jobs with a cycle of 6 months or longer:

~~~sql
SELECT ma_lich, ten_cong_viec
FROM lich_dinh_ky
WHERE chu_ky >= NUMTOYMINTERVAL(6, 'MONTH')
ORDER BY ma_lich;
~~~

Results are **2** and **4**. Both queries show comparing with the column's matching interval type.

### 8.4. Compute Total Months and Total Seconds

~~~sql
SELECT ma_lich,
       EXTRACT(YEAR FROM chu_ky) * 12
         + EXTRACT(MONTH FROM chu_ky) AS tong_thang,
       EXTRACT(DAY FROM thoi_luong) * 86400
         + EXTRACT(HOUR FROM thoi_luong) * 3600
         + EXTRACT(MINUTE FROM thoi_luong) * 60
         + EXTRACT(SECOND FROM thoi_luong) AS tong_giay
FROM lich_dinh_ky
ORDER BY ma_lich;
~~~

| ID | Total Months | Total Seconds |
| --- | ---: | ---: |
| 1 | 1 | 5400 |
| 2 | 12 | 86445.125 |
| 3 | NULL | 0 |
| 4 | 6 | NULL |

When business reporting needs **NULL displayed as 0**, apply **COALESCE** or **NVL** in the presentation layer. Do not apply that conversion by default if "unknown" and "zero" have distinct meanings.

### 8.5. Value Domain Constraints

Oracle permits negative intervals. However, execution duration of a job is normally non-negative, while schedule variance from a target deadline can be positive or negative. That is a **business rule**, not a general restriction of the data type.

For a table where absolute durations must never be negative, add a constraint such as:

~~~sql
ALTER TABLE lich_dinh_ky
ADD CONSTRAINT ck_lich_thoi_luong_khong_am
CHECK (
    thoi_luong IS NULL
    OR thoi_luong >= INTERVAL '0' SECOND
);
~~~

Declare **NOT NULL** separately if a column is mandatory. In Oracle, CHECK does not reject NULL when the condition evaluates to UNKNOWN; keep domain constraints distinct from column nullability.

## 9. PL/SQL with INTERVAL Variables

PL/SQL can declare interval variables, use them in calculations, or receive results from SQL.

~~~sql
SET SERVEROUTPUT ON

DECLARE
    v_bat_dau  TIMESTAMP(3) :=
        TIMESTAMP '2024-04-01 08:00:00.000';

    v_chu_ky   INTERVAL YEAR(3) TO MONTH :=
        INTERVAL '1-6' YEAR TO MONTH;

    v_thoi_gian INTERVAL DAY(3) TO SECOND(3) :=
        INTERVAL '0 01:30:30.500' DAY TO SECOND(3);

    v_lap_lai  TIMESTAMP(3);
    v_ket_thuc TIMESTAMP(3);
BEGIN
    v_lap_lai  := v_bat_dau + v_chu_ky;
    v_ket_thuc := v_bat_dau + v_thoi_gian;

    DBMS_OUTPUT.PUT_LINE(
        'Next run: ' ||
        TO_CHAR(v_lap_lai, 'YYYY-MM-DD HH24:MI:SS.FF3')
    );

    DBMS_OUTPUT.PUT_LINE(
        'Ends at: ' ||
        TO_CHAR(v_ket_thuc, 'YYYY-MM-DD HH24:MI:SS.FF3')
    );
END;
/
~~~

The next occurrence is **01/10/2025 08:00:00.000**, and the job ends at **01/04/2024 09:30:30.500**. The trailing **/** executes the block in tools such as SQL*Plus/SQLcl; to see `DBMS_OUTPUT`, enable output display accordingly.

There is no need to write PL/SQL loops adding seconds manually when Oracle provides native interval arithmetic; expressions with proper types are clearer and easier to control.

## 10. Java/JDBC Applications Passing and Reading INTERVALs

On the Java side, distinguish business representations **Period** and **Duration** from Oracle's interval types:

| Java | Meaning | Oracle Correspondence |
| --- | --- | --- |
| **java.time.Period** | ISO calendar years, months, and days | Year–month portion can correspond to YEAR TO MONTH if days are not used |
| **java.time.Duration** | Time span in seconds and nanoseconds | Matches DAY TO SECOND semantically |
| **java.time.LocalDateTime** | Local date/time without timezone | Commonly used for zoneless TIMESTAMP columns |
| **java.time.Instant / OffsetDateTime** | Real instant and timezone offset | Requires selecting the right Oracle timezone-aware type and JDBC binding |

**Never assume standard JDBC guarantees direct mapping in all cases** between Oracle INTERVAL and **java.time.Period/Duration**. Direct read/write support via **setObject/getObject** depends on the Oracle JDBC Driver version and supported Java types; you may encounter Oracle-specific representation classes. To minimize dependence on driver-specific APIs, a clean approach is to **bind numeric months or seconds and construct intervals using SQL functions**.

### 10.1. Example INSERT via PreparedStatement

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import javax.sql.DataSource;

public final class LichRepository {
    private final DataSource dataSource;

    public LichRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void themLich() throws SQLException {
        String sql = """
            INSERT INTO lich_dinh_ky
                (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
            VALUES (
                ?, ?, ?,
                NUMTOYMINTERVAL(?, 'MONTH'),
                NUMTODSINTERVAL(?, 'SECOND')
            )
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, 10L);
            statement.setString(2, "Job from Java application");
            statement.setTimestamp(
                3,
                Timestamp.valueOf(
                    LocalDateTime.of(2024, 7, 1, 9, 0, 0)
                )
            );
            statement.setInt(4, 18); // 18 months = 1 year 6 months
            statement.setBigDecimal(
                5,
                new BigDecimal("5400.125") // 1 hour 30 minutes 0.125 seconds
            );

            statement.executeUpdate();
        }
    }
}
~~~

**PreparedStatement** separates bound parameters from SQL structure, suited for user input and avoiding unsafe SQL string concatenation. **NUMTOYMINTERVAL** accepts numeric months, while **NUMTODSINTERVAL** accepts numeric seconds. Choosing **BigDecimal** represents fractional seconds cleanly without treating decimal arithmetic as binary floating-point.

This example assumes the table already exists, Oracle JDBC Driver is configured, `DataSource` is active, and the account has INSERT privilege. Transactions and commits are governed by `DataSource`/framework configuration; in a Spring-managed transaction, do not mix manual commits arbitrarily with Spring-owned transactions.

### 10.2. Example Reading Total Months and Total Seconds

To avoid depending on how a driver implements interval classes, let Oracle convert intervals into numeric quantities with explicit units:

~~~sql
SELECT ma_lich,
       EXTRACT(YEAR FROM chu_ky) * 12
           + EXTRACT(MONTH FROM chu_ky) AS total_months,
       EXTRACT(DAY FROM thoi_luong) * 86400
           + EXTRACT(HOUR FROM thoi_luong) * 3600
           + EXTRACT(MINUTE FROM thoi_luong) * 60
           + EXTRACT(SECOND FROM thoi_luong) AS total_seconds
FROM lich_dinh_ky
WHERE ma_lich = :ma_lich;
~~~

In standard JDBC, the named parameter **:ma_lich** is normally replaced with **?** in **PreparedStatement**, then bound with `setLong`. **TOTAL_MONTHS** can be read as months, and **TOTAL_SECONDS** can be read via `getBigDecimal` to preserve fractional seconds. When converting to **Duration**, decide rounding rules and how many nanosecond digits to retain; when converting to **Period**, never pass a day component into a column storing only YEAR TO MONTH.

### 10.3. Do Not Replace Months with Seconds in Java

A common bug is representing **Period.ofMonths(1)** as **Duration.ofDays(30)** and sending it to DAY TO SECOND. Those two spans are not calendar-equivalent. If a system calculates a one-month term, preserve the month count and apply month-end rules in business logic. If a system measures latency, job runtime, or wait time, durations in seconds are more natural.

## 11. Boundary Values and Common Errors

### 11.1. Leading Precision Too Small

~~~sql
-- Default DAY has leading precision 2:
-- 123 days exceeds the default day field length.
SELECT INTERVAL '123' DAY AS khoang_qua_lon
FROM dual;

-- Specify DAY(3) for 123 days.
SELECT INTERVAL '123' DAY(3) AS khoang_hop_le
FROM dual;
~~~

Distinguish **leading field precision** from **fractional seconds precision**. `DAY(3)` does not mean a 3-day duration; it allows up to three digits in the day field.

### 11.2. Subfield Outside Valid Range

~~~sql
-- Invalid because MONTH in YEAR TO MONTH is 12.
SELECT INTERVAL '1-12' YEAR TO MONTH
FROM dual;

-- Valid: 24 months total.
SELECT NUMTOYMINTERVAL(24, 'MONTH')
FROM dual;
~~~

Likewise, for full-form DAY TO SECOND literals, hour/minute/second fields must be valid. When input is a total of 150 minutes or 90000 seconds, **NUMTODSINTERVAL** lets Oracle convert and normalize it cleanly.

### 11.3. Unexpected Result Type Changes

~~~sql
SELECT DATE '2024-05-02'
       - DATE '2024-05-01' AS hieu_number
FROM dual;

SELECT TIMESTAMP '2024-05-02 00:00:00'
       - TIMESTAMP '2024-05-01 00:00:00' AS hieu_interval
FROM dual;
~~~

Never write application code assuming these two queries return the same JDBC object type. Inspect result type metadata or convert explicitly inside the SQL query.

### 11.4. NULL Differs from 0

~~~sql
-- Unknown duration.
SELECT ma_lich
FROM lich_dinh_ky
WHERE thoi_luong IS NULL;

-- Known duration equal to 0.
SELECT ma_lich
FROM lich_dinh_ky
WHERE thoi_luong = INTERVAL '0' SECOND;
~~~

With the seed data, the first query returns **4**, and the second returns **3**. Comparing **`= NULL`** does not work in SQL; always use **`IS NULL`**.

### 11.5. Input/Display Formatting Differs from Data Type

An INTERVAL column is stored by Oracle as an interval data type, not merely a string like **'1-6'** or **'1 02:03:04'**. How clients print intervals can include signs, zero-padding, and varying digit counts depending on precision, tool, or driver. Never rely on arbitrary UI string formatting to parse interval data in Java.

When exchanging durations via JSON or APIs, **publish a unit-explicit contract**: e.g., `totalMonths = 18`, `totalSeconds = 5400.125`, or an agreed duration string format. Avoid fields named **`duration = 18`** without specifying 18 months, days, seconds, or milliseconds.

### 11.6. Negative Intervals and Business Rules

Oracle permits negative intervals, useful for expressing offsets like "15 minutes late" or "three months back". However, **job execution duration** or **non-negative SLA terms** may require a `CHECK` constraint in the schema. Do not forbid all negative intervals across the board just to block one business case; variance columns may legitimately need both signs.

### 11.7. Month Cycles and DST

Never replace **INTERVAL '1' MONTH** with a fixed number of days. When computing on timezone-aware TIMESTAMPs, also never assume "add one local calendar day" has the same semantics as "add exactly 24 hours" across a DST transition. Recurring calendar schedules and processing durations may require separate models to preserve business intent.

## 12. Choosing Data Types in System Design

| Requirement | Type / Approach to Consider | Reason |
| --- | --- | --- |
| Contract renewal every 6 months | INTERVAL YEAR TO MONTH or explicit month count with rules | Calendar-month based |
| 2-year warranty | INTERVAL YEAR TO MONTH | Business unit is years–months |
| Job runtime 12.345 seconds | INTERVAL DAY TO SECOND or seconds with clear precision | Duration with fractional seconds |
| 5-second connection timeout | Usually milliseconds/seconds per API config; in DB can use DAY TO SECOND | Preserves units and stays distinct from timestamps |
| Difference between two TIMESTAMPs | INTERVAL DAY TO SECOND | Timestamp subtraction yields an interval |
| Start/end point in time | TIMESTAMP or timezone-aware variant | Point in time, not an interval |
| Month-end expiration terms | ADD_MONTHS or defined calendar rules | Must handle month-ends and leap years |
| API passing months and seconds from Java | Bind numbers and use NUMTOYMINTERVAL/NUMTODSINTERVAL | Separates data from SQL structure |
| Unknown duration | NULL in the model | Never arbitrarily replace with interval 0 |

Design also requires evaluating precision, value domains, privileges, timezone consistency, rounding rules, and input data formats. The same field name "duration" in code might mean a **calendar-month span** or **execution seconds**; the data model should make that distinction unambiguous.

## 13. Self-Study Exercises

1. Write an Oracle literal representing **2 years 7 months**, then use `EXTRACT` to compute total months. What is the result?
2. Create an interval of **1 day 4 hours 5 minutes 6.250 seconds** with `DAY(3) TO SECOND(3)`, then calculate total seconds.
3. Why is an `INTERVAL YEAR TO MONTH` column unsuitable if the business requirement is "run a task for at most 45 seconds"?
4. Write SQL to find the timestamp **90 minutes** after `TIMESTAMP '2024-02-29 23:30:00'`. Which calendar date does it land on?
5. Contrast **DATE - DATE** and **TIMESTAMP - TIMESTAMP** in return type and unit semantics.
6. Try adding `INTERVAL '1' MONTH` to `DATE '2024-01-31'`, then try `ADD_MONTHS` on the same date. Explain the month-end difference.
7. Write a query finding jobs with a cycle of **at least 12 months**, using only data in `LICH_DINH_KY`.
8. Write queries distinguishing durations **equal to 0** from **unknown** durations in the sample table.
9. If Java receives a month count from a user and a second count from a timer, which two interval constructor functions should pass them into Oracle?
10. Why must you never convert 1 month into 30 days when processing contracts that may start on 31/01?
11. In an API, if returning a duration in JSON, why should the unit be explicitly documented instead of returning a bare number?
12. If data has timezones and a recurring job runs at 09:00 local time, what questions must be asked before adding `DAY TO SECOND` across a daylight saving time shift?

**INTERVAL YEAR TO MONTH** expresses shifts in **calendar years and months**; **INTERVAL DAY TO SECOND** expresses **durations in days through seconds**, optionally with fractional seconds. Both types let SQL and PL/SQL represent time units directly, yet they do not replace business rules for month-ends, points in time, timezones, or numeric units exchanged with Java. When the right type and precision are chosen, calculations and data checks in Oracle stay unambiguous, consistent, and free from hidden implicit conversions.
