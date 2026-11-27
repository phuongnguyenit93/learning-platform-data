# Datetime Arithmetic, Intervals, and End-of-Month Rules

In Oracle Database, datetime arithmetic is not as simple as adding a number to a column. **Adding one day, adding 24 hours, and adding one calendar month** can each mean something different. This matters especially around month-end dates, leap years, timestamps with fractional seconds, time zones, and when inputs arrive as strings affected by NLS settings.

For example, suppose a contract starts on **January 31, 2024** with a **1-month** term. Should the expiration date be February 29, 2024, March 2, 2024, or another date? The answer depends on **business rules** and **which Oracle operation you choose**. Meanwhile, a job starting at **23:45** that runs for 30 minutes can be computed with day-to-second intervals without any end-of-month rules.

This lesson clarifies how to use **DATE**, **TIMESTAMP**, both **INTERVAL** types, **ADD_MONTHS**, **LAST_DAY**, **MONTHS_BETWEEN**, **TRUNC**, **EXTRACT**, and NLS principles when performing datetime arithmetic.

## 1. Choose the right data type before calculating

| Oracle data type | What it stores/represents | Suitable use cases |
| --- | --- | --- |
| **DATE** | Year, month, day, hour, minute, second; no fractional seconds or time zone info | Order dates, business dates, timestamps needing second precision |
| **TIMESTAMP(p)** | Date and time with fractional seconds, no time zone | Log entries or internal processing metrics needing milliseconds |
| **TIMESTAMP WITH TIME ZONE** | Instant with time zone/offset info in supported representation | Events occurring across different time zones |
| **TIMESTAMP WITH LOCAL TIME ZONE** | Value normalized to database time zone and displayed in session time zone | Instant data rendered per session |
| **INTERVAL YEAR TO MONTH** | Duration in calendar years and months | Contract terms, monthly renewals |
| **INTERVAL DAY TO SECOND** | Duration in days, hours, minutes, seconds, and fractional seconds | Execution duration, latency, 90-minute windows |
| **NUMBER** | Numeric value; carries temporal meaning only when unit is defined | Difference between two DATEs as days, or configured month counts |

A **point in time** tells *when*, whereas an **interval** tells *how long*. In Oracle, **DATE - DATE** returns a `NUMBER` of days, whereas **TIMESTAMP - TIMESTAMP** returns an **INTERVAL DAY TO SECOND**.

~~~text
Start date/time               Operation                      Result
---------------------         -------------------------      ---------------------
2024-01-15                    + 1 calendar month             2024-02-15
2024-01-31                    + 1 month via ADD_MONTHS       2024-02-29
2024-02-28 23:30:00           + 90 minutes                   2024-02-29 01:00:00
2024-03-01 12:00:00           - 2024-02-29 12:00:00          1 day
~~~

These example results assume the **Gregorian calendar**, zone-less data, and no custom `NLS_CALENDAR` away from standard Gregorian settings.

## 2. Adding and subtracting NUMBER with Oracle DATE

Oracle's **DATE** type stores values to second precision, even though default display formats may show only the date. When adding or subtracting a **NUMBER** with a `DATE`, that number is interpreted in **units of days**.

### 2.1. Adding whole days

~~~sql
SELECT DATE '2024-02-28' + 1 AS ngay_sau
FROM dual;

SELECT DATE '2024-03-01' - 2 AS hai_ngay_truoc
FROM dual;
~~~

The results correspond to **2024-02-29** and **2024-02-28** respectively. Oracle handles leap-year calendar rules automatically; you never need custom code to decide whether February has 28 or 29 days.

### 2.2. Adding hours, minutes, and seconds as fractions of a day

~~~sql
SELECT DATE '2024-02-28' + (6 / 24) AS sau_sau_gio
FROM dual;

SELECT DATE '2024-02-28' + (90 / 1440) AS sau_chin_muoi_phut
FROM dual;

SELECT DATE '2024-02-28' + (45 / 86400) AS sau_bon_muoi_lam_giay
FROM dual;
~~~

These conversions come from:

- **1 day = 24 hours**.
- **1 day = 1,440 minutes**.
- **1 day = 86,400 seconds**.

Because **DATE stores time only to the second**, fractional-day addition is unsuitable when you need exact milliseconds or microseconds. When expressing sub-second durations, use `TIMESTAMP` and `INTERVAL DAY TO SECOND`.

The **1 day = 24 hours** formula here applies to zone-less datetime arithmetic. For local wall-clock workflows affected by daylight saving time (DST), use time-zone-aware types and real zone rules rather than applying this formula blindly in every context.

### 2.3. Subtracting two DATEs: result is a number of days

~~~sql
SELECT DATE '2024-03-02' - DATE '2024-02-29' AS so_ngay
FROM dual;

SELECT (
    TO_DATE('2024-03-01 09:30:00', 'YYYY-MM-DD HH24:MI:SS')
    - TO_DATE('2024-03-01 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
) * 24 * 60 AS so_phut
FROM dual;
~~~

The first query returns **2 days**; the second returns **90 minutes**. Wrapping the subtraction in parentheses makes clear that the returned `NUMBER` is **days**, which is then converted to the target unit.

If the result is negative, the left timestamp is earlier than the right timestamp:

~~~sql
SELECT DATE '2024-03-01' - DATE '2024-03-05' AS chenhlech_am
FROM dual;
~~~

The result is **-4**, not `NULL` or an error.

### 2.4. DATE literals avoid session format dependency

~~~sql
SELECT DATE '2024-02-29' AS ngay_nhuan
FROM dual;
~~~

The syntax **DATE 'YYYY-MM-DD'** creates a DATE literal with an explicit date and time `00:00:00`, without relying on `NLS_DATE_FORMAT` to parse an input string.

Its limitation is that the DATE literal only specifies the date part. When time is needed, use `TO_DATE` with an explicit format model or an appropriate `TIMESTAMP` literal.

## 3. TIMESTAMP and INTERVAL DAY TO SECOND

**TIMESTAMP** stores fractional seconds. **INTERVAL DAY TO SECOND** expresses a span in days, hours, minutes, seconds, and fractional seconds. Combine them to express latencies or durations with explicit units.

### 3.1. Adding and subtracting intervals

~~~sql
SELECT TIMESTAMP '2024-02-28 23:30:00.000'
       + INTERVAL '0 01:30:00.250' DAY TO SECOND(3)
       AS ket_thuc
FROM dual;

SELECT TIMESTAMP '2024-03-01 10:00:00'
       - INTERVAL '45' MINUTE
       AS tru_bon_muoi_lam_phut
FROM dual;
~~~

The first example yields **2024-02-29 01:00:00.250**; the second yields **2024-03-01 09:15:00**. These operations respect day, month, and year rollovers without manual string math.

### 3.2. Commonly used interval literals

~~~sql
SELECT INTERVAL '2' DAY AS hai_ngay,
       INTERVAL '5' HOUR AS nam_gio,
       INTERVAL '90' MINUTE AS chin_muoi_phut,
       INTERVAL '1 02:03:04.125' DAY TO SECOND(3) AS mot_ngay_hai_gio
FROM dual;
~~~

The **DAY TO SECOND** literal has a leading day field, and subfields must remain within valid bounds—for example, hours in a full day-to-second literal are 0–23. To construct an interval from **90 hours** or **150 minutes** input, `NUMTODSINTERVAL` is usually more convenient than building a literal with out-of-range hour/minute components.

### 3.3. NUMTODSINTERVAL for computed or bound values

~~~sql
SELECT TIMESTAMP '2024-02-28 23:30:00'
       + NUMTODSINTERVAL(90, 'MINUTE') AS ket_thuc
FROM dual;

SELECT TIMESTAMP '2024-01-01 08:00:00.000'
       + NUMTODSINTERVAL(1.25, 'SECOND') AS sau_mot_phay_hai_lam_giay
FROM dual;
~~~

**NUMTODSINTERVAL** accepts a numeric value and a unit such as `DAY`, `HOUR`, `MINUTE`, or `SECOND`, returning `INTERVAL DAY TO SECOND`. It is especially useful when a Java application passes a numeric timeout, duration, or delay into SQL via a bind variable.

### 3.4. Subtracting two TIMESTAMPs

~~~sql
SELECT TIMESTAMP '2024-03-01 01:00:00.125'
       - TIMESTAMP '2024-02-28 23:59:59.000'
       AS thoi_luong
FROM dual;
~~~

The result is an **INTERVAL DAY TO SECOND** equal to **1 day, 1 hour, 0 minutes, and 1.125 seconds**. You cannot directly treat this interval as a `NUMBER` of days the way `DATE - DATE` works.

To obtain total seconds from an interval, extract its components using `EXTRACT`:

~~~sql
WITH khoang AS (
    SELECT TIMESTAMP '2024-03-01 01:00:00.125'
           - TIMESTAMP '2024-02-28 23:59:59.000'
           AS dt
    FROM dual
)
SELECT EXTRACT(DAY FROM dt) * 86400
       + EXTRACT(HOUR FROM dt) * 3600
       + EXTRACT(MINUTE FROM dt) * 60
       + EXTRACT(SECOND FROM dt) AS tong_giay
FROM khoang;
~~~

Total seconds equal **90,001.125** for the two chosen timestamps (1 day + 1 hour + 1.125 seconds). This converts interval components into total seconds and does not account for time zones or DST transitions if the inputs carry no time zone.

### 3.5. Distinguishing operations on DATE vs. TIMESTAMP

| Expression | Result type typically handled | Caveat |
| --- | --- | --- |
| **DATE + NUMBER** | Date/time value | `NUMBER` is in days |
| **DATE - DATE** | `NUMBER` | Number of days; can be negative or fractional |
| **TIMESTAMP - TIMESTAMP** | `INTERVAL DAY TO SECOND` | Duration with fractional seconds |
| **TIMESTAMP + INTERVAL DAY TO SECOND** | Shifted date/time value | Keeps day, hour, minute, second semantics explicit |
| **DATE/TIMESTAMP + INTERVAL YEAR TO MONTH** | Value shifted by calendar years–months | Must consider nonexistent month-end dates |

When designing JDBC access, do not assume every time difference reads back as a Java **long** or **double**. Know whether Oracle returns a `NUMBER` or an `INTERVAL`, and use the appropriate driver mapping or SQL conversion.

## 4. INTERVAL YEAR TO MONTH and calendar-month math

**INTERVAL YEAR TO MONTH** expresses counts of years and months, such as 1 year 6 months. Unlike days or seconds, **the actual length of a month depends on the calendar month and year**.

~~~sql
SELECT INTERVAL '1-6' YEAR TO MONTH AS mot_nam_sau_thang
FROM dual;

SELECT NUMTOYMINTERVAL(18, 'MONTH') AS muoi_tam_thang
FROM dual;
~~~

Both expressions represent an interval of **18 calendar months**. However, when adding to a date, the effect on month-end dates depends on the start date and on which operator/function you use for nonexistent dates.

Examples that do not hit boundary dates:

~~~sql
SELECT DATE '2024-01-15' + INTERVAL '1' MONTH AS thang_sau
FROM dual;

SELECT TIMESTAMP '2024-01-15 10:30:00'
       + INTERVAL '1-2' YEAR TO MONTH AS sau_mot_nam_hai_thang
FROM dual;
~~~

The calendar results are **2024-02-15** and **2025-03-15 10:30:00** respectively. When the starting day number exists in the target month, adding months is straightforward. For days 29, 30, or 31, examine end-of-month rules carefully.

## 5. End-of-month rules: ADD_MONTHS vs. INTERVAL addition

This is the single biggest source of business-logic bugs when renewing contracts, computing due dates, or generating recurring schedules.

### 5.1. How does ADD_MONTHS handle end-of-month dates?

**ADD_MONTHS(date, n)** shifts a `DATE` value forward or backward by **n calendar months**. Under Oracle's rules:

- If the input date is **the last day of its month**, the result is **the last day of the target month**.
- If the target month has **fewer days than the input day-of-month**, the result is clamped to **the last day of the target month**.
- Otherwise, Oracle preserves the **same day of the month**.
- The hour/minute/second portion of the input `DATE` is preserved under month addition, subject to `DATE` limits and semantics.
- `ADD_MONTHS` returns type **DATE**.

~~~sql
SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-01-31', 1),
           'YYYY-MM-DD'
       ) AS tu_31_thang_1
FROM dual;

SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-01-30', 1),
           'YYYY-MM-DD'
       ) AS tu_30_thang_1
FROM dual;

SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-02-29', 12),
           'YYYY-MM-DD'
       ) AS tu_29_thang_2
FROM dual;
~~~

Results in the Gregorian calendar:

| Calculation | Result | Explanation |
| --- | --- | --- |
| **ADD_MONTHS(31/01/2024, 1)** | 29/02/2024 | Source is month-end; target month has 29 days |
| **ADD_MONTHS(30/01/2024, 1)** | 29/02/2024 | Day 30 does not exist in February |
| **ADD_MONTHS(29/02/2024, 12)** | 28/02/2025 | Source is month-end; February 2025 has 28 days |
| **ADD_MONTHS(15/01/2024, 1)** | 15/02/2024 | Day 15 exists in target month |
| **ADD_MONTHS(31/03/2024, -1)** | 29/02/2024 | Stepping back from March month-end to leap-year February month-end |

**Oracle's end-of-month rule in ADD_MONTHS is a function design choice**, not automatically the legal rule of every contract. Some domains want to snap to month-end; some want to stay on day 30 or 31 whenever possible; others expire one day prior. Lock down the business policy before coding.

### 5.2. Adding INTERVAL '1' MONTH can raise an error

~~~sql
-- Example illustrating a nonexistent date error.
SELECT DATE '2024-01-31' + INTERVAL '1' MONTH AS ket_qua
FROM dual;
~~~

When adding months this way, **2024-02-31** does not exist, so Oracle raises **ORA-01839: date not valid for month specified**. This is the practical difference between **INTERVAL YEAR TO MONTH** addition and **ADD_MONTHS** on boundary dates.

Therefore, when the requirement is "always return a valid month-end date" upon adding months, `ADD_MONTHS` is the option to consider. When the model requires preserving the exact day number and failing if the target day does not exist, `INTERVAL` addition enforces that stricter semantics.

### 5.3. Getting the last day of a month with LAST_DAY

~~~sql
SELECT TO_CHAR(
           LAST_DAY(DATE '2024-02-10'),
           'YYYY-MM-DD'
       ) AS cuoi_thang_hai
FROM dual;

SELECT TO_CHAR(
           LAST_DAY(DATE '2025-02-10'),
           'YYYY-MM-DD'
       ) AS cuoi_thang_hai_khong_nhuan
FROM dual;
~~~

The results are **2024-02-29** and **2025-02-28** respectively. `LAST_DAY` returns a `DATE` representing the last day of the month containing the input date, preserving `DATE` time semantics.

To find **the last day of next month**, combine them:

~~~sql
SELECT LAST_DAY(
           ADD_MONTHS(DATE '2024-01-15', 1)
       ) AS cuoi_thang_sau
FROM dual;
~~~

The result is **2024-02-29**.

**LAST_DAY** and **ADD_MONTHS** use the month definition of the Oracle session's **NLS_CALENDAR** parameter. The examples above assume the Gregorian calendar. In environments using a different calendar, inspect `NLS_CALENDAR` rather than assuming every session follows the same month rules.

### 5.4. Adding months sequentially does not always equal adding all at once

A subtle issue: **ADD_MONTHS is not always associative in the way applications expect** when crossing month-end dates.

~~~sql
SELECT TO_CHAR(
           ADD_MONTHS(
               ADD_MONTHS(DATE '2024-01-30', 1),
               1
           ),
           'YYYY-MM-DD'
       ) AS cong_tung_thang,

       TO_CHAR(
           ADD_MONTHS(DATE '2024-01-30', 2),
           'YYYY-MM-DD'
       ) AS cong_hai_thang_mot_lan
FROM dual;
~~~

Results:

- **One month at a time:** 30/01 → 29/02 → **2024-03-31**. After the first step, 29/02 is month-end, so the second step continues "snapping to month-end."
- **Two months at once:** 30/01 → **2024-03-30**, because March has a 30th day.

This matters greatly for billing schedules. Computing the next period from **the previous period's date** can permanently drift a schedule to month-end. Computing from **start_date + n months** preserves the original day whenever the target month supports it.

**No single rule is automatically right for every domain.** For example:

- **Anchor to the original day when possible:** compute each period as `ADD_MONTHS(start_date, elapsed_months)`.
- **Always end-of-month:** flag end-of-month contracts explicitly and apply month-end rules consistently.
- **Chain from the previous period:** accept that the schedule snaps to month-end once an intermediate period hits month-end.
- **Expire the day before the anniversary:** subtract one day as well, depending on contract policy.

### 5.5. Designing recurring schedules from an anchor date

For a contract starting **2024-01-30** with a one-month cycle, the following query generates billing dates anchored to **the original start date**:

~~~sql
WITH moc AS (
    SELECT DATE '2024-01-30' AS ngay_goc
    FROM dual
)
SELECT LEVEL AS ky_so,
       TO_CHAR(
           ADD_MONTHS(ngay_goc, LEVEL),
           'YYYY-MM-DD'
       ) AS ngay_den_han
FROM moc
CONNECT BY LEVEL <= 4
ORDER BY ky_so;
~~~

Illustrative output:

| Period | Due date computed from anchor |
| --- | --- |
| 1 | 2024-02-29 |
| 2 | 2024-03-30 |
| 3 | 2024-04-30 |
| 4 | 2024-05-30 |

This query evaluates **ADD_MONTHS(ngay_goc, n)** rather than feeding the previous month's date into the next step. If the rule requires **always month-end**, the schedule generation logic differs.

## 6. MONTHS_BETWEEN: month difference is not days divided by 30

**MONTHS_BETWEEN(date1, date2)** returns a **NUMBER** representing the difference in months between two `DATE`s. It is not an `INTERVAL YEAR TO MONTH`, and the fractional part is not computed by dividing actual days by each month's length in all cases.

Under Oracle's rules:

- If both dates share the same day of the month or **both are the last day of their months**, the result is an **integer number of months**.
- Otherwise, the fractional portion is calculated based on a **31-day month**, and can also reflect time-of-day components.
- Month semantics depend on the session's **NLS_CALENDAR**.

~~~sql
SELECT MONTHS_BETWEEN(
           DATE '2024-02-29',
           DATE '2024-01-31'
       ) AS so_thang_cuoi_thang
FROM dual;

SELECT MONTHS_BETWEEN(
           DATE '2024-04-15',
           DATE '2024-01-15'
       ) AS so_thang_cung_ngay
FROM dual;
~~~

The two results are **1** and **3** respectively. Even though 29 days separate Jan 31 and Feb 29, `MONTHS_BETWEEN` returns 1 because both are month-end dates.

For mismatched day numbers, such as the 10th to the 21st, the function returns a fractional month count. If a system requires "completed full months," "age in months," or "completed billing cycles," specify exact rounding/truncation rules and handle month-end cases explicitly. Never call `MONTHS_BETWEEN` and round arbitrarily.

### 6.1. Day difference and month difference are two distinct measures

~~~sql
SELECT DATE '2024-03-31' - DATE '2024-02-29' AS so_ngay,
       MONTHS_BETWEEN(
           DATE '2024-03-31',
           DATE '2024-02-29'
       ) AS so_thang
FROM dual;
~~~

In the Gregorian calendar, the results are **31 days** yet **1 month**. There is no contradiction: `DATE` subtraction measures elapsed days, while `MONTHS_BETWEEN` measures calendar month difference under its own rules.

## 7. TRUNC and ROUND: normalizing to day/month boundaries

Oracle provides **TRUNC(date, format)** to truncate temporal components smaller than a given unit and **ROUND(date, format)** to round to the nearest boundary.

### 7.1. Stripping time for day-level comparisons

~~~sql
SELECT TO_CHAR(
           TRUNC(
               TO_DATE('2024-03-15 16:45:30',
                       'YYYY-MM-DD HH24:MI:SS')
           ),
           'YYYY-MM-DD HH24:MI:SS'
       ) AS dau_ngay
FROM dual;
~~~

The result is **2024-03-15 00:00:00**. Use `TRUNC` when you need to normalize a `DATE` with a time component to the start of the day, such as when storing a reporting date key.

### 7.2. Start of month and start of year

~~~sql
SELECT TO_CHAR(
           TRUNC(DATE '2024-03-19', 'MM'),
           'YYYY-MM-DD'
       ) AS dau_thang,

       TO_CHAR(
           TRUNC(DATE '2024-03-19', 'YYYY'),
           'YYYY-MM-DD'
       ) AS dau_nam
FROM dual;
~~~

The results are **2024-03-01** and **2024-01-01** respectively. You can find the start of the next month with:

~~~sql
SELECT ADD_MONTHS(
           TRUNC(DATE '2024-03-19', 'MM'),
           1
       ) AS dau_thang_ke_tiep
FROM dual;
~~~

### 7.3. ROUND is not TRUNC

~~~sql
SELECT TO_CHAR(
           ROUND(
               TO_DATE('2024-03-15 16:00:00',
                       'YYYY-MM-DD HH24:MI:SS')
           ),
           'YYYY-MM-DD HH24:MI:SS'
       ) AS ngay_duoc_lam_tron
FROM dual;
~~~

With default day-level `ROUND`, **16:00** is past noon, so it rounds forward to **00:00 the next day**. By contrast, `TRUNC` returns **00:00 the same day**.

For reporting filters, `TRUNC` is typically used to find boundary dates; `ROUND` is for genuine rounding. Keep one critical performance note in mind: wrapping an indexed column directly in `TRUNC` inside a `WHERE` clause can prevent standard index usage. When querying a date range, **half-open range predicates** are usually much easier for the optimizer to optimize.

## 8. Querying by date using half-open intervals

A common mistake when filtering dates that carry time components:

~~~sql
-- May miss rows on March 31 after 00:00:00.
SELECT *
FROM don_hang
WHERE ngay_dat BETWEEN DATE '2024-03-01'
                   AND DATE '2024-03-31';
~~~

Because both `DATE` literals sit at **00:00:00**, this query misses orders on March 31 from 00:00:01 onward.

Clearer expression:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-03-01'
  AND ngay_dat <  DATE '2024-04-01';
~~~

The interval **[2024-03-01, 2024-04-01)** includes every instant from the start of March 1 up to immediately before April 1. It also works when columns store `TIMESTAMP` fractional seconds (with matching literals/casts) without inventing `23:59:59.999...` constants.

To select the month containing an input date, compute the start of the month and the start of the next month:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= TRUNC(DATE '2024-03-19', 'MM')
  AND ngay_dat <  ADD_MONTHS(
                        TRUNC(DATE '2024-03-19', 'MM'),
                        1
                   );
~~~

Similarly, when filtering a single day:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-03-15'
  AND ngay_dat <  DATE '2024-03-16';
~~~

Using half-open intervals preserves exact semantics when time components exist and keeps predicates index-friendly compared to wrapping the column in a function, though the final execution plan is chosen by the optimizer.

## 9. How NLS affects datetime input and display

**NLS (National Language Support)** controls many internationalization settings in an Oracle session, including date formats, month-name languages, and calendar rules. Calculations performed on explicitly typed `DATE`/`TIMESTAMP` values are far more reliable than calculations relying on implicitly parsed strings.

### 9.1. NLS_DATE_FORMAT

Different sessions can have different default date display/parse formats. For instance, the exact same `DATE` can display as:

~~~text
15-MAR-24
2024-03-15
15/03/2024
~~~

All three strings can represent the exact same `DATE` value. Display formatting **never alters the date stored in the column**.

Inspect several session settings:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_CALENDAR',
    'NLS_TERRITORY'
)
ORDER BY parameter;
~~~

Never deduce the true stored value solely from UI-rendered output without knowing the format in use.

### 9.2. Avoid implicit conversion

Error-prone example:

~~~sql
-- Unsafe if the session's NLS_DATE_FORMAT is unknown.
SELECT *
FROM don_hang
WHERE ngay_dat = '03/04/2024';
~~~

The string **03/04/2024** can be interpreted as day/month or month/day in different environments, or fail to parse altogether.

Prefer:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-04-03'
  AND ngay_dat <  DATE '2024-04-04';
~~~

Or when the input must be a string with time:

~~~sql
SELECT TO_DATE(
           '2024-04-03 14:05:06',
           'YYYY-MM-DD HH24:MI:SS'
       ) AS thoi_diem
FROM dual;
~~~

In Java applications, **bind typed datetime values** instead of concatenating strings and relying on the connection's NLS.

### 9.3. TO_CHAR and TO_DATE with explicit formats

~~~sql
SELECT TO_CHAR(
           DATE '2024-02-29',
           'YYYY-MM-DD'
       ) AS ngay_iso
FROM dual;

SELECT TO_CHAR(
           TIMESTAMP '2024-02-29 23:59:59.125',
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS thoi_diem_chi_tiet
FROM dual;
~~~

`TO_CHAR` is for presentation; `TO_DATE`/`TO_TIMESTAMP` are for parsing strings into datetime types. Choose format elements such as **YYYY, MM, DD, HH24, MI, SS, FF3** carefully to match the data type.

Textual month names are affected by **NLS_DATE_LANGUAGE**. When deliberately parsing English month names:

~~~sql
SELECT TO_DATE(
           '15-MAR-2024',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS ngay_co_ten_thang
FROM dual;
~~~

Purely numeric formats such as **YYYY-MM-DD** are simpler and far less language-dependent.

### 9.4. NLS_CALENDAR and month rules

**ADD_MONTHS**, **LAST_DAY**, and **MONTHS_BETWEEN** depend on the month definition of the **NLS_CALENDAR** setting. All examples in this lesson use the Gregorian calendar. If an application connects across sessions that permit differing `NLS_CALENDAR` configurations, month-based calculations may diverge from business assumptions.

Conversely, **TRUNC(date, 'MM')** follows Gregorian calendar semantics defined by Oracle rather than simply adopting every `NLS_CALENDAR` month rule. Therefore, do not assume every function taking `'MM'` shares identical calendar semantics when `NLS_CALENDAR` changes.

For systems requiring uniform behavior across environments, establish an approved calendar policy, control session configuration, and test on your actual Oracle environment.

## 10. SYSDATE, CURRENT_DATE, and system reference points

When calculating relative to "now," know the time source and time zone of each function:

| Function | Primary meaning | Caveat |
| --- | --- | --- |
| **SYSDATE** | Current date/time of the database server as `DATE` | Stores no fractional seconds and carries no time zone in `DATE` |
| **SYSTIMESTAMP** | Current timestamp of the database server with time zone info | Useful when sub-second precision and offset are needed |
| **CURRENT_DATE** | Current date/time in the session's time zone, returning `DATE` | Can differ from `SYSDATE` when session and server time zones differ |
| **CURRENT_TIMESTAMP** | Current timestamp in the session's time zone | Suitable when retaining session time zone metadata |
| **LOCALTIMESTAMP** | Current timestamp in the session's time zone without time zone metadata | Cannot replace an absolute instant with offset |

~~~sql
SELECT SYSDATE,
       SYSTIMESTAMP,
       CURRENT_DATE,
       CURRENT_TIMESTAMP,
       LOCALTIMESTAMP
FROM dual;
~~~

Do not expect the returned values to match in data type or formatting. For applications spanning multiple regions, standardize on a clear instant and time zone model rather than mixing server clock, session clock, and browser clock.

## 11. Zoned timestamps and daylight saving time transitions

A calendar month, a calendar day, and a 24-hour duration can all diverge when operating in a **local time zone with DST**:

- A meeting schedule "09:00 local time every day" requires preserving civil wall-clock time in that time zone region.
- A task "run again after exactly 24 elapsed hours" requires elapsed-duration semantics.
- "23:59 on the last day of the month in the customer's time zone" requires identifying the time zone before comparing against absolute instants.

A plain **TIMESTAMP** carries no time zone, so a value like **2024-03-31 02:30:00** does not tell you which region it belongs to or whether it is valid there. In some regions, that hour can be skipped or repeated due to DST.

When representing an instant in a specific region, consider **TIMESTAMP WITH TIME ZONE** with appropriate display/comparison rules. Never blindly substitute "30 days" for "one month" or "24 hours" for "one calendar day" when time zones and civil calendars apply.

In a Java application, distinguish:

- **LocalDate**: calendar date without time or time zone.
- **LocalDateTime**: local date/time, not an absolute global instant.
- **Instant**: point on the UTC timeline.
- **OffsetDateTime / ZonedDateTime**: instant with offset or time zone region and its rules.
- **Period**: span in calendar years/months/days.
- **Duration**: span in seconds/nanoseconds.

Choose Oracle types and Java types from **business semantics**, not merely from the length of a datetime string in a payload.

## 12. Sample dataset to practice DATE, TIMESTAMP, and month-end rules

Practice in a **dedicated Oracle schema** with table-creation privileges and no real production data. Use fixed IDs and dates so results are predictable.

### 12.1. Create the table

~~~sql
CREATE TABLE lich_gia_han_demo (
    ma_lich           NUMBER(5)
                      CONSTRAINT pk_lich_gia_han_demo PRIMARY KEY,
    ten_lich          VARCHAR2(100 CHAR) NOT NULL,
    ngay_bat_dau      DATE NOT NULL,
    thoi_diem_xu_ly   TIMESTAMP(3),
    chu_ky_thang      NUMBER(3) NOT NULL,
    thoi_luong_xu_ly  INTERVAL DAY(3) TO SECOND(3),
    CONSTRAINT ck_chu_ky_thang
        CHECK (chu_ky_thang BETWEEN 1 AND 36)
);
~~~

In this table:

- **NGAY_BAT_DAU** is the contract/cycle start date as `DATE`.
- **THOI_DIEM_XU_LY** is the job execution timestamp to millisecond precision.
- **CHU_KY_THANG** is the whole calendar month cycle for `ADD_MONTHS`.
- **THOI_LUONG_XU_LY** is the duration in days/hours/minutes/seconds.
- **NULL** in either optional column means no timestamp/duration yet, distinct from a 0 duration.

### 12.2. Load sample data

~~~sql
INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    101,
    'Bat dau cuoi thang 1',
    DATE '2024-01-31',
    TIMESTAMP '2024-01-31 22:40:00.000',
    1,
    INTERVAL '0 02:30:00.250' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    102,
    'Bat dau ngay 30',
    DATE '2024-01-30',
    TIMESTAMP '2024-01-30 10:00:00.000',
    1,
    INTERVAL '0 01:00:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    103,
    'Bat dau ngay nhuan',
    DATE '2024-02-29',
    TIMESTAMP '2024-02-29 23:59:00.000',
    12,
    INTERVAL '0 00:02:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    104,
    'Chua co thoi diem xu ly',
    DATE '2024-03-15',
    NULL,
    2,
    NULL
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    105,
    'Chuyen giao nam moi',
    DATE '2024-12-31',
    TIMESTAMP '2024-12-31 23:45:00.000',
    1,
    INTERVAL '0 00:30:00.000' DAY TO SECOND(3)
);

COMMIT;
~~~

These dates are chosen deliberately: end of January, the 30th before February, leap day, an ordinary day, and New Year's Eve.

### 12.3. Calculate monthly renewal dates

~~~sql
SELECT ma_lich,
       TO_CHAR(ngay_bat_dau, 'YYYY-MM-DD') AS ngay_goc,
       chu_ky_thang,
       TO_CHAR(
           ADD_MONTHS(ngay_bat_dau, chu_ky_thang),
           'YYYY-MM-DD'
       ) AS ngay_gia_han
FROM lich_gia_han_demo
ORDER BY ma_lich;
~~~

Expected Gregorian calendar results:

| ID | Anchor date | Cycle | Renewal date |
| --- | --- | ---: | --- |
| 101 | 2024-01-31 | 1 | 2024-02-29 |
| 102 | 2024-01-30 | 1 | 2024-02-29 |
| 103 | 2024-02-29 | 12 | 2025-02-28 |
| 104 | 2024-03-15 | 2 | 2024-05-15 |
| 105 | 2024-12-31 | 1 | 2025-01-31 |

Rows **101** and **102** yield the same result next month despite starting on different days. This demonstrates the clamping rule when the target month has fewer days.

### 12.4. Calculate processing end timestamps

~~~sql
SELECT ma_lich,
       TO_CHAR(
           thoi_diem_xu_ly,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS bat_dau_xu_ly,
       TO_CHAR(
           thoi_diem_xu_ly + thoi_luong_xu_ly,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS ket_thuc_xu_ly
FROM lich_gia_han_demo
ORDER BY ma_lich;
~~~

Results:

| ID | End timestamp |
| --- | --- |
| 101 | **2024-02-01 01:10:00.250** |
| 102 | **2024-01-30 11:00:00.000** |
| 103 | **2024-03-01 00:01:00.000** |
| 104 | **NULL** |
| 105 | **2025-01-01 00:15:00.000** |

Example 101 shows adding 2 hours 30 minutes crossing into a new month. Example 103 crosses leap day; example 105 crosses into a new year. Row 104 represents unknown data and cannot default to ending at the start time.

### 12.5. Distinguish NULL from a zero interval

~~~sql
SELECT ma_lich
FROM lich_gia_han_demo
WHERE thoi_luong_xu_ly IS NULL;
~~~

Returns ID **104**. To find rows with a zero duration, query:

~~~sql
SELECT ma_lich
FROM lich_gia_han_demo
WHERE thoi_luong_xu_ly = INTERVAL '0' SECOND;
~~~

This dataset has no rows with a zero duration; that state differs from `NULL`. Keep this distinction in reports unless business specs explicitly require coalescing.

### 12.6. Filter schedules starting in leap-year February

~~~sql
SELECT ma_lich, ten_lich
FROM lich_gia_han_demo
WHERE ngay_bat_dau >= DATE '2024-02-01'
  AND ngay_bat_dau <  DATE '2024-03-01';
~~~

Returns **103**. Using a half-open interval keeps the SQL accurate even when `NGAY_BAT_DAU` carries hours/minutes/seconds.

### 12.7. Generate billing periods anchored to the start date

~~~sql
SELECT l.ma_lich,
       ky.so_ky,
       TO_CHAR(
           ADD_MONTHS(l.ngay_bat_dau,
                      l.chu_ky_thang * ky.so_ky),
           'YYYY-MM-DD'
       ) AS ngay_ky
FROM lich_gia_han_demo l
CROSS JOIN (
    SELECT LEVEL AS so_ky
    FROM dual
    CONNECT BY LEVEL <= 3
) ky
WHERE l.ma_lich = 102
ORDER BY ky.so_ky;
~~~

For ID **102**, with a 1-month cycle and start date 2024-01-30, the output is:

| Period | Date |
| --- | --- |
| 1 | 2024-02-29 |
| 2 | 2024-03-30 |
| 3 | 2024-04-30 |

The query computes directly from the anchor date. If it took the prior period's date and added one month, period 2 would become **2024-03-31**. Choose the calendar model based on business requirements.

### 12.8. Clean up practice data

When you are certain this sandbox table can be dropped:

~~~sql
DROP TABLE lich_gia_han_demo PURGE;
~~~

**PURGE** bypasses the recycle bin per standard behavior; never run this on business tables. DDL follows its own implicit-commit rules and cannot be rolled back like a normal `DELETE`.

## 13. Java applications: where to calculate and how to pass values?

Two common approaches:

1. **Compute inside Oracle** when anchor dates, cycles, and business data already reside in the database, especially when a single SQL statement updates many rows consistently.
2. **Compute inside Java** with **java.time** types when the application owns calendar rules and coordinates across multiple systems. In that case, verify exact equivalence between Java and Oracle rules.

### 13.1. JDBC: bind dates/times with explicit types

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import java.time.LocalDate;
import javax.sql.DataSource;

public final class LichGiaHanRepository {
    private final DataSource dataSource;

    public LichGiaHanRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public LocalDate tinhNgayGiaHan(LocalDate ngayGoc, int soThang)
            throws SQLException {
        String sql = """
            SELECT ADD_MONTHS(?, ?) AS ngay_gia_han
            FROM dual
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setDate(1, Date.valueOf(ngayGoc));
            statement.setInt(2, soThang);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException("No result from ADD_MONTHS");
                }
                return rows.getDate("NGAY_GIA_HAN").toLocalDate();
            }
        }
    }
}
~~~

**PreparedStatement** passes values independently of SQL syntax, avoiding date string concatenation and reducing NLS dependency when the driver transmits typed binds. This example uses **java.sql.Date** because the input is strictly a calendar date without time or time zone.

Important caveat: Java's **LocalDate.plusMonths** also clamps nonexistent target days to the last valid day of the month, yet its "snap-to-month-end" behavior when the starting date is already month-end **differs from ADD_MONTHS**. For example, **2023-02-28** is month-end; `ADD_MONTHS` by 1 month yields **2023-03-31**, whereas `LocalDate.plusMonths(1)` yields **2023-03-28**. If Java and Oracle results must agree, explicitly specify the business rule and test month-end dates.

### 13.2. Do not silently convert Period to Duration

In Java:

- **Period.ofMonths(1)** represents one calendar month.
- **Duration.ofDays(30)** represents exactly 30 days as a duration.
- **Duration.ofHours(24)** represents 24 hours.

They are not interchangeable merely because a few test cases happen to land on the same date. Keep **month counts** for renewal schedules, and keep **seconds/milliseconds** for processing durations.

If a driver lacks a convenient direct mapping from `java.time.Duration` to Oracle `INTERVAL DAY TO SECOND`, bind numeric seconds and call **NUMTODSINTERVAL(?, 'SECOND')**. For month counts, use **NUMTOYMINTERVAL(?, 'MONTH')** or **ADD_MONTHS(?, ?)** as appropriate.

## 14. Typical errors in datetime calculations

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Adding one month to Jan 31 raises an error | `INTERVAL` addition produces a nonexistent date | Clarify business rule; consider `ADD_MONTHS` if clamping to month-end |
| Adding months step-by-step differs from adding from start date | Month-end snapping effect of `ADD_MONTHS` | Specify whether periods chain from prior period or anchor date |
| `BETWEEN` filter up to March 31 misses some March 31 orders | Upper `DATE` literal sits at `00:00:00` | Use `>= start_day AND < next_day` |
| `DATE - DATE` returns a number instead of an interval | Oracle defines `DATE` difference as a `NUMBER` of days | Convert units explicitly or `CAST` to `TIMESTAMP` before subtracting |
| Two environments yield different results for the same date string | `NLS_DATE_FORMAT`/`NLS_DATE_LANGUAGE` and implicit conversion | Use `DATE`/`TIMESTAMP` literals, binds, or explicit format models |
| `ADD_MONTHS`/`LAST_DAY` behave unexpectedly in multi-calendar systems | `NLS_CALENDAR` differs from assumed calendar | Check and standardize calendar policy |
| Results across DST are off by one hour | Confused calendar day with absolute duration or dropped time zone | Use `TIMESTAMP WITH TIME ZONE` and calendar rules |
| Large gap between `SYSDATE` and `CURRENT_DATE` | Server and session time zones differ | Establish the application's standard time source |
| `TIMESTAMP` loses milliseconds | Converted to `DATE` or formatted without `FF` | Preserve `TIMESTAMP` and matching precision |
| Java date diverges from Oracle after adding months | Month-end rule differs between `LocalDate.plusMonths` and `ADD_MONTHS` | Test 28/29/30/31 dates and standardize business logic |
| Calling `LAST_DAY` and treating it as end-of-day `23:59:59` | `LAST_DAY` retains the input's time component rather than setting end-of-day | Filter using half-open intervals instead of fabricating last seconds |
| Query slows down when wrapping an indexed column in `TRUNC` | Function on column inhibits standard index range scans | Use range predicates or an appropriate index when needed |

In real systems, fixes must be grounded in **data semantics and execution plans**, not by swapping functions until one test input happens to look right.

## 15. Practice exercises

1. Explain why **DATE '2024-02-29' + 1** is valid and what date it evaluates to.
2. Write SQL calculating **90 minutes** after **2024-02-28 23:30:00** using `NUMTODSINTERVAL`.
3. Subtract two `DATE`s, **2024-03-02** and **2024-02-29**, and identify the result's data type and unit.
4. Subtract two `TIMESTAMP`s with milliseconds and convert the resulting interval to total seconds using `EXTRACT`.
5. Compare **ADD_MONTHS(DATE '2024-01-31', 1)** with **DATE '2024-01-31' + INTERVAL '1' MONTH**. Why do they behave differently?
6. Why does **ADD_MONTHS(ADD_MONTHS(DATE '2024-01-30', 1), 1)** differ from **ADD_MONTHS(DATE '2024-01-30', 2)**?
7. A schedule must always fall due on **the last day of the month**. Show how to use `LAST_DAY` and `ADD_MONTHS` to generate the next three periods starting from 2024-01-31.
8. Use `MONTHS_BETWEEN` to compute the span between **2024-02-29** and **2024-01-31**. Why do you not divide the day difference by 30?
9. Write a query finding all orders in **March 2024** without missing rows with non-zero times on March 31.
10. State the difference between `TRUNC` and `ROUND` for a `DATE` with time **16:00:00**.
11. How do you display a `DATE` as **YYYY-MM-DD** regardless of `NLS_DATE_FORMAT`?
12. When using textual month names, why must you pay attention to `NLS_DATE_LANGUAGE`?
13. Why must `ADD_MONTHS`, `LAST_DAY`, and `TRUNC(..., 'MM')` be checked individually when an application allows changing `NLS_CALENDAR`?
14. Distinguish `SYSDATE` from `CURRENT_DATE` when the database server and application use different time zones.
15. For a requirement "run at 09:00 local time daily," why must you distinguish calendar days from 24 absolute hours?
16. For a contract starting **2023-02-28**, compare the month-addition semantics of Oracle `ADD_MONTHS` with Java `LocalDate.plusMonths`; which rule would you pick for warranty coverage?
17. Write SQL finding rows in `LICH_GIA_HAN_DEMO` whose processing end timestamp lands on **the next day**.
18. Why should an unknown duration (`NULL`) never be stored by default as a zero interval?

**Datetime arithmetic in Oracle must start from units and calendar rules**: a `NUMBER` added to `DATE` represents days, `INTERVAL DAY TO SECOND` models day–second durations, and `INTERVAL YEAR TO MONTH` and `ADD_MONTHS` model calendar months with critical differences at month-end. Understanding `LAST_DAY`, `MONTHS_BETWEEN`, `TRUNC`, and NLS enables consistent queries, while time zone and `DATE`/`TIMESTAMP` boundaries ensure results match business intent rather than merely passing a few sample cases.
