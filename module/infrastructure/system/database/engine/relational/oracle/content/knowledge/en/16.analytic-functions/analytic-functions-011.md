# IGNORE NULLS, RESPECT NULLS, and Time-Series Data Imputation in Oracle

In time-series data, a sensor may miss a reading; a sales system may lack revenue for a day; a status table may only record rows when values change. As a result, a sequence of data often contains rows where the measured value is NULL. During analysis, the question is not just "which value is missing?" but also **when looking at a preceding or following row, should Oracle stop at NULL or skip past it to find the next non-NULL value?**

Oracle provides two NULL-handling options for several analytic functions: **RESPECT NULLS** and **IGNORE NULLS**. RESPECT NULLS preserves NULLs when locating positions; IGNORE NULLS skips rows where the evaluated expression is NULL when determining the first, last, previous, or next value. These options are especially useful with LAG, LEAD, FIRST_VALUE, and LAST_VALUE, enabling **sequential data imputation** (*forward fill*, *backfill*).

This lesson belongs to the **Analytic Functions** topic of *Database Engine Relational Oracle*. The content focuses on:

- The meaning and default behavior of RESPECT NULLS/IGNORE NULLS.
- How analytic functions locate values when encountering NULLs.
- Filling values forward (forward fill) and backward (backfill).
- Handling series with multiple groups, duplicate timestamps, and missing time intervals.
- Distinguishing carry-forward from linear interpolation.
- Notes on window frames, deterministic ordering, data quality, and performance.

## 1. NULLs in a Data Series Can Carry Multiple Meanings

A row with a NULL value does not necessarily mean the measurement is 0. It can represent:

- A device failing to transmit data during that period.
- A value not yet collected or entered.
- A field not applicable to that record.
- An event that occurred without a measurement value.
- Data filtered out during quality checks.

Example temperature series:

| SENSOR_ID | MEASURED_AT | TEMPERATURE |
| ---: | --- | ---: |
| 7 | 09:00 | 24.5 |
| 7 | 10:00 | NULL |
| 7 | 11:00 | NULL |
| 7 | 12:00 | 25.2 |
| 7 | 13:00 | NULL |

If a report needs to display the "most recent known value", we can fill 24.5 into 10:00 and 11:00, and fill 25.2 into 13:00. However, this is a **business rule**: it assumes the latest value can still represent the missing timestamp.

For status data (for instance, device state logged only on change), forward fill is usually appropriate because the prior state remains valid until a new event arrives. For temperature, stock prices, or rainfall, carrying an old value into the future can introduce distortion. Before filling, define the meaning of NULL and any expiration policy.

## 2. What Are RESPECT NULLS and IGNORE NULLS?

Several Oracle analytic functions allow specifying how NULLs are treated in the evaluated expression:

- **RESPECT NULLS**: do not skip NULL values. If the target position contains NULL, the function's result can be NULL.
- **IGNORE NULLS**: skip rows where the input expression is NULL when locating the target position; the function keeps searching for a non-NULL value.

For functions supporting this option, RESPECT NULLS is the default when unspecified. Writing it explicitly can help readers understand the NULL policy:

~~~sql
LAG(measurement) RESPECT NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
)
~~~

Compare with:

~~~sql
LAG(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
)
~~~

The first expression takes the value of the immediately preceding row in order, even if that value is NULL. The second expression searches for the nearest non-NULL value before the current row.

### Which Functions Support It?

In Oracle, the NULL-treatment clause is supported by several analytic functions, most commonly:

| Function | RESPECT NULLS | IGNORE NULLS | Meaning with IGNORE |
| --- | --- | --- | --- |
| LAG | Yes | Yes | Finds the nearest non-NULL value preceding the current row. |
| LEAD | Yes | Yes | Finds the nearest non-NULL value following the current row. |
| FIRST_VALUE | Yes | Yes | Takes the first non-NULL value in the frame. |
| LAST_VALUE | Yes | Yes | Takes the last non-NULL value in the frame. |
| NTH_VALUE | Yes | Yes | Takes the Nth non-NULL value in the frame in FIRST/LAST direction. |

Not every analytic function accepts the IGNORE NULLS clause. Only use it with functions whose syntax supports it in your Oracle release.

### NULL Treatment Does Not Modify Source Data

IGNORE NULLS only controls how the analytic function locates values. It does not:

- UPDATE columns in the table.
- Delete rows containing NULL.
- Turn NULL into 0.
- Generate additional rows for timestamps that do not exist.
- Prove that a filled value was actually measured.

The result remains an expression in the SELECT output. If filled data must be persisted, perform a separate DML step after confirming the policy and target data.

## 3. RESPECT NULLS: Preserving NULL Positions

Suppose a sequence is ordered chronologically:

| SEQ_NO | VALUE |
| ---: | ---: |
| 1 | 10 |
| 2 | NULL |
| 3 | 30 |
| 4 | NULL |
| 5 | 50 |

Query:

~~~sql
SELECT seq_no,
       value,
       LAG(value) RESPECT NULLS OVER (
           ORDER BY seq_no
       ) AS previous_value
FROM lab_sequence
ORDER BY seq_no;
~~~

Result:

| SEQ_NO | VALUE | PREVIOUS_VALUE |
| ---: | ---: | ---: |
| 1 | 10 | NULL |
| 2 | NULL | 10 |
| 3 | 30 | NULL |
| 4 | NULL | 30 |
| 5 | 50 | NULL |

LAG picks the exact preceding row. On row 3, the preceding row has VALUE NULL, so the result is NULL; the function does not step further back to row 1.

This is the right behavior when **row position** carries meaning and NULL must be preserved. For example, when you need to know whether the immediately prior entry had data, or when detecting gaps between events.

## 4. IGNORE NULLS: Finding the Nearest Non-NULL Value

Using the same data, switch to:

~~~sql
SELECT seq_no,
       value,
       LAG(value) IGNORE NULLS OVER (
           ORDER BY seq_no
       ) AS previous_non_null
FROM lab_sequence
ORDER BY seq_no;
~~~

Result:

| SEQ_NO | VALUE | PREVIOUS_NON_NULL |
| ---: | ---: | ---: |
| 1 | 10 | NULL |
| 2 | NULL | 10 |
| 3 | 30 | 10 |
| 4 | NULL | 30 |
| 5 | 50 | 30 |

On row 3, LAG IGNORE NULLS skips row 2 because VALUE is NULL and finds row 1 with value 10. On row 5, the function skips row 4 to find value 30 at row 3.

### Offset Counts Qualifying Values

With IGNORE NULLS, the offset is counted over non-NULL values rather than simply physical rows:

~~~sql
LAG(value, 2) IGNORE NULLS OVER (
    ORDER BY seq_no
)
~~~

This expression finds the second non-NULL value preceding the current row. Under RESPECT NULLS, an offset of 2 means the row two positions back in order, even if its expression is NULL.

### LAG/LEAD Default Is Not a Universal NULL Replacement

Syntax:

~~~sql
LAG(value_expr [, offset [, default_value]])
    [{RESPECT | IGNORE} NULLS]
    OVER (analytic_clause)
~~~

Default is only used when no row exists at the corresponding offset under the chosen search mode. It does not mean "if the located row's value is NULL, substitute default".

~~~sql
SELECT seq_no,
       value,
       LAG(value, 1, -1) RESPECT NULLS OVER (
           ORDER BY seq_no
       ) AS previous_respect,
       LAG(value, 1, -1) IGNORE NULLS OVER (
           ORDER BY seq_no
       ) AS previous_ignore
FROM lab_sequence
ORDER BY seq_no;
~~~

- On the first row, there is no preceding row, so both expressions use default -1.
- On row 3, the preceding row has a NULL value: RESPECT returns NULL; IGNORE continues searching and finds 10.
- Default is not used on row 3 in the RESPECT case because the preceding row **exists**, it just happens to have a NULL value.

This is often confused with `NVL(LAG(...), default)`. The two are not equivalent:

~~~sql
NVL(
    LAG(value) RESPECT NULLS OVER (ORDER BY seq_no),
    -1
)
~~~

NVL replaces every NULL result, including NULL returned because the preceding row genuinely had a NULL value; the default argument inside LAG only handles the case where no row exists at that offset.

## 5. FIRST_VALUE and LAST_VALUE with IGNORE NULLS

FIRST_VALUE and LAST_VALUE locate the first/last value within the current row's **window frame**. When combined with IGNORE NULLS, they skip NULL values within the frame.

### FIRST_VALUE

~~~sql
FIRST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

The expression returns the first non-NULL value across the entire partition and repeats it on all rows in the partition. If no non-NULL value exists, the result remains NULL.

### LAST_VALUE

~~~sql
LAST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

The expression returns the last non-NULL value across the entire partition. If you only want the most recent non-NULL value **up to the current row**, restrict the frame to end at current row:

~~~sql
LAST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

This is the key structure for forward fill.

### Why Must You Specify the Frame Explicitly?

When an analytic function has ORDER BY without a specified frame, many functions use a default frame equivalent to:

`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`

LAST_VALUE may therefore look only up to the current row/current peers instead of the entire partition. Conversely, for forward fill, ending the frame at CURRENT ROW is intentional; if you want the last value across the entire partition, extend the frame to UNBOUNDED FOLLOWING.

Do not rely on default frames in critical reports. Write ROWS/RANGE and both frame boundaries explicitly so readers know the exact window evaluated.

## 6. Forward Fill: Filling NULLs with the Nearest Preceding Non-NULL Value

Forward fill (also called *last observation carried forward*, LOCF) uses the most recent valid prior value to fill the current row. For a chronologically ordered series, the core formula is:

~~~sql
LAST_VALUE(value) IGNORE NULLS OVER (
    PARTITION BY series_id
    ORDER BY event_time, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Example sensor table:

| SENSOR_ID | READING_ID | READING_TIME | MEASURE |
| ---: | ---: | --- | ---: |
| 7 | 1 | 09:00 | 24.5 |
| 7 | 2 | 10:00 | NULL |
| 7 | 3 | 11:00 | NULL |
| 7 | 4 | 12:00 | 25.2 |
| 7 | 5 | 13:00 | NULL |

~~~sql
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS measure_filled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Result:

| READING_TIME | MEASURE | MEASURE_FILLED |
| --- | ---: | ---: |
| 09:00 | 24.5 | 24.5 |
| 10:00 | NULL | 24.5 |
| 11:00 | NULL | 24.5 |
| 12:00 | 25.2 | 25.2 |
| 13:00 | NULL | 25.2 |

On each row, the frame spans from the start of the partition to the current row. LAST_VALUE IGNORE NULLS picks the most recent non-NULL measurement in the frame.

### Forward Fill Cannot Fill Leading NULLs

If a partition starts with:

| SEQ_NO | VALUE |
| ---: | ---: |
| 1 | NULL |
| 2 | NULL |
| 3 | 15 |
| 4 | NULL |

On rows 1 and 2, there is no prior non-NULL value. True forward fill returns NULL for those two rows; from row 3 onward, it can fill with 15. Do not automatically pull future values if business logic requires strict carry-forward.

## 7. Backfill: Filling NULLs with the Nearest Following Non-NULL Value

Backfill uses the first non-NULL future value to fill missing rows. Formula:

~~~sql
FIRST_VALUE(value) IGNORE NULLS OVER (
    PARTITION BY series_id
    ORDER BY event_time, event_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
~~~

~~~sql
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       FIRST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
       ) AS measure_backfilled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

With series 24.5, NULL, NULL, 25.2, NULL, the backfill result is:

| READING_TIME | MEASURE | MEASURE_BACKFILLED |
| --- | ---: | ---: |
| 09:00 | 24.5 | 24.5 |
| 10:00 | NULL | 25.2 |
| 11:00 | NULL | 25.2 |
| 12:00 | 25.2 | 25.2 |
| 13:00 | NULL | NULL |

Trailing NULL rows have no future non-NULL value and remain NULL. This is the expected property of backfill.

| Technique | Common function | Frame | Selected value |
| --- | --- | --- | --- |
| Forward fill | LAST_VALUE IGNORE NULLS | UNBOUNDED PRECEDING to CURRENT ROW | Nearest valid past or current value |
| Backfill | FIRST_VALUE IGNORE NULLS | CURRENT ROW to UNBOUNDED FOLLOWING | Nearest valid future or current value |
| Series first value | FIRST_VALUE IGNORE NULLS | Entire partition | First non-NULL value |
| Series last value | LAST_VALUE IGNORE NULLS | Entire partition | Last non-NULL value |

## 8. Filling Leading, Middle, and Trailing NULLs Together

A common policy is **prefer past values**, and if no past value exists yet, fall back to the first future value. You can combine forward fill and backfill:

~~~sql
WITH filled_candidates AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure,
           FIRST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_measure
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       COALESCE(previous_measure, next_measure) AS measure_filled
FROM filled_candidates
ORDER BY sensor_id, reading_time, reading_id;
~~~

COALESCE prefers `previous_measure`. Only when no non-NULL past value exists does the expression fall back to `next_measure`. Consequently:

- Leading NULLs are backfilled using the first following non-NULL value.
- Middle NULLs are forward filled from the nearest preceding value.
- Trailing NULLs are forward filled from the nearest preceding value.
- If the entire partition is NULL, the result remains NULL.

This is a **past-priority rule**, not selecting the nearest value by time distance. If a missing row lies between two irregularly spaced points, the past value might be farther away in time than the future value. When nearest-neighbor by time is needed, calculate both past and future distances and compare them.

## 9. Imputing Across Multiple Independent Series

When there are multiple sensors, customers, or accounts, always specify the partition key so data from one series never bleeds into another:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

If PARTITION BY sensor_id is omitted, Oracle can pull a non-NULL value from another sensor in the global ordering. The result would be wrong for the business even though the syntax is valid.

Example adding site and device:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY site_id, sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Include all columns identifying the series. If SENSOR_ID is only unique within each site, partitioning by sensor alone will mix data across sites.

## 10. Ordering Must Be Deterministic: ORDER BY and ROWS

Forward fill and backfill depend on ordering. If two rows share the same timestamp, ordering by timestamp alone may leave the order between them undetermined:

~~~sql
ORDER BY reading_time
~~~

If two readings share the same READING_TIME, Oracle may order peers unstably across runs or plans. Add a distinguishing key:

~~~sql
ORDER BY reading_time, reading_id
~~~

### Why Should You Usually Use ROWS?

With ORDER BY and no specified frame, the default frame for many analytic functions is RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW. RANGE treats rows with the same sort value as peers. In data with duplicate timestamps, peer rows share the same current frame.

Forward fill usually needs a deterministic row order, so write:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

ROWS with a tie-breaker clarifies the logical sequence within the series. If business rules treat all records at the same timestamp as a single point receiving the same value, design with RANGE or aggregate to one row per timestamp first; do not let the default frame decide for you.

### Duplicate Timestamps and Business Rules

If the same sensor has two readings at the exact same timestamp, decide:

- Keep both and order by READING_ID/sequence?
- Aggregate into a single value (AVG, MAX, source priority)?
- Pick the latest record by INGESTED_AT?
- Treat them as peers sharing a single frame?

No technical tie-breaker automatically knows the right business rule. The secondary key only stabilizes order once the priority policy has been chosen.

## 11. IGNORE NULLS Does Not Generate Rows for Missing Timestamps

A critical point: IGNORE NULLS only skips NULL values on **existing rows**. If the table has no row at 10:00, an analytic function cannot fabricate a 10:00 row to fill.

Suppose the data only contains:

| READING_TIME | MEASURE |
| --- | ---: |
| 09:00 | 24.5 |
| 12:00 | 25.2 |

There are no rows for 10:00 and 11:00, so forward fill on the raw table returns only the two rows 09:00 and 12:00. To produce an hourly series, build a **time spine/calendar** first and LEFT JOIN the measurement data.

### Generating a Time Spine with CONNECT BY

Example generating 24 hourly timestamps from a start date:

~~~sql
SELECT DATE '2026-01-01' + (LEVEL - 1) / 24 AS hour_start
FROM dual
CONNECT BY LEVEL <= 24;
~~~

In Oracle, DATE supports adding days; 1/24 is one hour. For large calendars, many sensors, or multiple time zones, use a managed calendar/time dimension table rather than generating unbounded series in every query.

### Joining the Time Spine with Data

Suppose `LAB_SENSOR_READINGS` has at most one record per sensor per hour:

~~~sql
WITH hours AS (
    SELECT DATE '2026-01-01' + (LEVEL - 1) / 24 AS hour_start
    FROM dual
    CONNECT BY LEVEL <= 24
),
sensor_list AS (
    SELECT DISTINCT sensor_id
    FROM lab_sensor_readings
),
dense_series AS (
    SELECT s.sensor_id,
           h.hour_start,
           r.reading_id,
           r.measure
    FROM sensor_list s
    CROSS JOIN hours h
    LEFT JOIN lab_sensor_readings r
      ON r.sensor_id = s.sensor_id
     AND r.reading_time = h.hour_start
)
SELECT sensor_id,
       hour_start,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY hour_start
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS measure_filled
FROM dense_series
ORDER BY sensor_id, hour_start;
~~~

This SQL illustrates the case where source data is already normalized to exact hour timestamps. If multiple readings occur within the same hour, aggregate or pick one representative reading before joining so the time spine is not multiplied. Also build the sensor list according to the desired reporting scope; taking DISTINCT from the readings table will exclude sensors that have never sent data.

## 12. Carry-Forward Differs from Linear Interpolation

Forward fill carries the prior value into missing timestamps. It does not compute intermediate values. For example:

| TIMESTAMP | KNOWN VALUE |
| --- | ---: |
| 09:00 | 10 |
| 10:00 | NULL |
| 11:00 | 30 |

Forward fill gives 10:00 the value 10. Backfill gives 10:00 the value 30. **Linear interpolation** assumes uniform change between two known points and yields 20 at 10:00.

With a DATE column and a numeric value, you can retrieve the nearest preceding/following non-NULL rows using LAST_VALUE/FIRST_VALUE and compute the time proportion:

~~~sql
WITH neighbors AS (
    SELECT series_id,
           sample_id,
           sample_time,
           value,
           LAST_VALUE(value) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_value,
           LAST_VALUE(
               CASE WHEN value IS NOT NULL THEN sample_time END
           ) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_time,
           FIRST_VALUE(value) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_value,
           FIRST_VALUE(
               CASE WHEN value IS NOT NULL THEN sample_time END
           ) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_time
    FROM lab_series
)
SELECT series_id,
       sample_id,
       sample_time,
       value,
       CASE
         WHEN value IS NOT NULL THEN value
         WHEN prev_value IS NOT NULL
          AND next_value IS NOT NULL
          AND next_time > prev_time
         THEN prev_value
              + (next_value - prev_value)
                * ((sample_time - prev_time)
                   / NULLIF(next_time - prev_time, 0))
         ELSE NULL
       END AS interpolated_value
FROM neighbors
ORDER BY series_id, sample_time, sample_id;
~~~

In this example SAMPLE_TIME is of type DATE; subtracting two DATEs returns days. The formula computes the fraction of elapsed time between the two valid measurement points. With TIMESTAMP, subtraction returns an interval, which must be converted to a compatible numeric unit before applying the formula.

Linear interpolation is only sensible if the quantity can be assumed to vary approximately linearly across the gap. It is not automatically appropriate for discrete statuses, events, transaction-driven balances, or step-function series. In those cases, forward fill, backfill, a default value, or leaving NULL may be more accurate.

## 13. Time-Bounded Filling (Max-Age Limit)

An old value should not be carried forward indefinitely. For example, if a sensor reports 24.5 at 09:00 and then loses connectivity all day, filling 24.5 at 23:00 can produce misleading data.

You can carry the timestamp of the nearest known value alongside the value:

~~~sql
WITH carried AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure,
           LAST_VALUE(
               CASE WHEN measure IS NOT NULL THEN reading_time END
           ) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure_time
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       CASE
         WHEN measure IS NOT NULL THEN measure
         WHEN reading_time - previous_measure_time <= 1/24
         THEN previous_measure
         ELSE NULL
       END AS measure_filled_max_1_hour
FROM carried;
~~~

Here, forward fill is applied only if the most recent valid reading is within one hour of the current timestamp. `1/24` of a day equals one hour in Oracle DATE arithmetic. If the column uses TIMESTAMP, compute the interval difference in appropriate units.

An expiration condition prevents carrying stale state too far forward. The threshold must come from business requirements or device specifications, not an arbitrary guess.

## 14. Persisting Filled Results Back to a Table

The analytic queries above only return filled results. If you want to persist them, start with a SELECT/CTE to preview which rows will change. After confirming the rule, you can use MERGE or UPDATE by unique key.

Example where the target table has READING_ID as primary key and only updates rows that are currently NULL:

~~~sql
MERGE INTO lab_sensor_readings target
USING (
    SELECT reading_id,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS filled_measure
    FROM lab_sensor_readings
) source
ON (target.reading_id = source.reading_id)
WHEN MATCHED THEN
    UPDATE SET target.measure = source.filled_measure
    WHERE target.measure IS NULL
      AND source.filled_measure IS NOT NULL;
~~~

This is a forward-fill example that writes past values into eligible NULL rows. Before running on real data:

1. Run the SELECT with the CTE to preview the expected row count and values.
2. Confirm the JOIN key is unique so one target row cannot match multiple source rows.
3. Decide whether a max-age limit is needed for carried values.
4. Record provenance/audit logs if imputed values need to be traced.
5. Execute inside a controlled transaction and deployment process; verify updated row counts before committing.

Do not overwrite existing actual measurements. The condition `TARGET.MEASURE IS NULL` protects rows that already have values, though you should still verify concurrency and application write policies.

## 15. Performance and Execution Plans

IGNORE NULLS does not make a query faster on its own. Cost depends primarily on row count, partition count, sorting requirements, frame type, and how much data must be held in the workarea.

Factors to watch:

- **Input row count:** analytics run over the row set after WHERE/GROUP BY/HAVING of the query block.
- **Partition size:** a very large partition may require significant memory and sorting work.
- **ORDER BY:** Oracle may need to organize rows by partition key and sort key.
- **Frame:** full-partition frames or frames looking forward may need to buffer/access additional rows.
- **Multiple analytics with different orders:** functions sharing the same partition/order can reuse the sort order; differing specifications may require extra sorts.
- **PGA and TEMP:** insufficient workarea memory can spill to the temporary tablespace.

### Observing the Actual Plan

~~~sql
SELECT /*+ gather_plan_statistics */
       sensor_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS filled_measure
FROM lab_sensor_readings;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Observe window/sort operations, actual row counts, buffer gets, physical reads, and TEMP/workarea information if present. ALLSTATS LAST requires execution statistics to be gathered, such as via the `GATHER_PLAN_STATISTICS` hint or appropriate configuration. Permissions to inspect cursors/plans depend on user privileges and database settings.

EXPLAIN PLAN provides only an estimated plan; it does not execute the query to measure elapsed time, actual rows, or TEMP usage.

### Indexes Can Help, But Do Not Guarantee Eliminating a Sort

An index on partition/order columns can be helpful in some queries. For sensor series, an index like:

~~~sql
CREATE INDEX ix_lab_sensor_time
ON lab_sensor_readings (sensor_id, reading_time, reading_id);
~~~

can assist access by sensor and chronological order. However, the optimizer still evaluates full scans, clustering factor, row count, number of selected columns, and index read cost. Do not create an index based solely on analytic syntax; measure the actual plan on representative data.

## 16. Common Pitfalls and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| LAG returns NULL even though a valid value exists further back | Using RESPECT NULLS or default | Use IGNORE NULLS if NULLs should be skipped. |
| LAG IGNORE NULLS pulls a value more than one row away | Offset counts non-NULL values | Expected behavior; verify whether you want row offset or valid-value offset. |
| LAG's default does not replace NULL from the preceding row | Row at offset exists, but its expression is NULL | Use IGNORE NULLS or NVL if policy requires replacing all NULL results. |
| Forward fill does not fill leading NULLs | No prior non-NULL value exists | Keep NULL, or add backfill if business rules permit. |
| Backfill does not fill trailing NULLs | No future non-NULL value exists | Keep NULL or use forward fill. |
| LAST_VALUE returns only the current value | Frame ends at CURRENT ROW or default frame | Specify frame explicitly; forward fill needs UNBOUNDED PRECEDING to CURRENT ROW. |
| Values mid-series are filled out of order | ORDER BY lacks a tie-breaker | Add a unique key and a rule for duplicate timestamps. |
| One sensor's values leak into another sensor | Incomplete PARTITION BY | Partition by all columns identifying the series. |
| Timestamps with no rows are still missing | IGNORE NULLS does not create new rows | Generate a calendar/time spine and LEFT JOIN source before filling. |
| Stale values carry forward for too long | Forward fill has no expiration limit | Carry the source value's timestamp and apply a max-age check. |
| Results are computed, yet the table does not change | Analytic SELECT does not modify data | Run a separate DML statement after previewing and confirming policy. |
| TEMP usage spikes on large series | Sort/window workarea lacks memory | Check actual plan, row count, partitions, PGA/TEMP, and concurrent workload. |

## 17. Comprehensive Hands-On Lab

Run in a learning schema with `CREATE TABLE` privileges and appropriate quota. DDL performs an implicit commit in Oracle; do not run on real business tables.

### Step 1: Create Measurement Series

~~~sql
CREATE TABLE lab_sensor_readings (
    reading_id   NUMBER(8) PRIMARY KEY,
    sensor_id    NUMBER(8) NOT NULL,
    reading_time DATE NOT NULL,
    measure      NUMBER(10,2)
);

INSERT INTO lab_sensor_readings VALUES
    (1, 7, TO_DATE('2026-01-01 09:00', 'YYYY-MM-DD HH24:MI'), 24.5);
INSERT INTO lab_sensor_readings VALUES
    (2, 7, TO_DATE('2026-01-01 10:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (3, 7, TO_DATE('2026-01-01 11:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (4, 7, TO_DATE('2026-01-01 12:00', 'YYYY-MM-DD HH24:MI'), 25.2);
INSERT INTO lab_sensor_readings VALUES
    (5, 7, TO_DATE('2026-01-01 13:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (6, 8, TO_DATE('2026-01-01 09:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (7, 8, TO_DATE('2026-01-01 10:00', 'YYYY-MM-DD HH24:MI'), 18.0);
INSERT INTO lab_sensor_readings VALUES
    (8, 8, TO_DATE('2026-01-01 11:00', 'YYYY-MM-DD HH24:MI'), NULL);
COMMIT;
~~~

### Step 2: Compare RESPECT and IGNORE

~~~sql
SELECT sensor_id,
       reading_id,
       measure,
       LAG(measure) RESPECT NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_respect,
       LAG(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_ignore
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Focus on sensor 7 at row 3 and row 5. Explain why the two LAG columns differ.

### Step 3: Forward Fill

~~~sql
SELECT sensor_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS forward_filled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Observe sensor 8: the first row stays NULL because no prior value exists.

### Step 4: Backfill

~~~sql
SELECT sensor_id,
       reading_time,
       measure,
       FIRST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
       ) AS backfilled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Observe sensor 7 at 10:00 and 11:00; the first following value is 25.2. The final row at 13:00 remains NULL because no future value exists.

### Step 5: Combine Forward Fill and Backfill

~~~sql
WITH candidates AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_value,
           FIRST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_value
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       COALESCE(prev_value, next_value) AS filled_value
FROM candidates
ORDER BY sensor_id, reading_time, reading_id;
~~~

Explain the past-priority policy and how an all-NULL partition is handled.

### Step 6: Observe LAG Default Behavior

~~~sql
SELECT reading_id,
       measure,
       LAG(measure, 1, -1) RESPECT NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_respect_default,
       LAG(measure, 1, -1) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_ignore_default
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Distinguish the case where no preceding row exists from the case where a preceding row exists with `MEASURE` NULL.

### Step 7: Clean Up Data

~~~sql
DROP TABLE lab_sensor_readings PURGE;
~~~

Run only if you have finished the lab and no longer need the data. `PURGE` bypasses the Recycle Bin; DROP TABLE is DDL and cannot be rolled back like uncommitted DML.

## 18. Self-Check Questions

1. **What does RESPECT NULLS mean?** Preserves NULLs when locating positions; if the selected row has a NULL expression, the result can be NULL.
2. **What does IGNORE NULLS mean?** Skips rows with a NULL expression when searching for a value by offset/position within the function's scope.
3. **What is the default option?** RESPECT NULLS for functions supporting NULL treatment.
4. **How does LAG IGNORE NULLS differ from LAG RESPECT NULLS?** One searches for the prior non-NULL value; the other takes the exact preceding row, even if its value is NULL.
5. **When is LAG's default value used?** When no row exists at the target offset under the chosen search mode, not simply whenever the expression value is NULL.
6. **Which function is typically used for forward fill?** `LAST_VALUE(expr) IGNORE NULLS` with a frame from `UNBOUNDED PRECEDING` to `CURRENT ROW`.
7. **Which function is typically used for backfill?** `FIRST_VALUE(expr) IGNORE NULLS` with a frame from `CURRENT ROW` to `UNBOUNDED FOLLOWING`.
8. **Why must you PARTITION BY sensor_id?** So values from another sensor do not carry into the current series.
9. **Why is a tie-breaker needed in ORDER BY?** To determine ordering among rows with identical timestamps.
10. **How does ROWS differ from RANGE?** ROWS operates by row position; RANGE operates by sort value and includes peers.
11. **Does IGNORE NULLS create rows for missing timestamps?** No; a time spine/calendar and LEFT JOIN are needed first.
12. **Is forward fill equivalent to linear interpolation?** No; forward fill carries the prior value, whereas interpolation computes an intermediate value between two points.
13. **How do you limit the age of a carried value?** Carry the timestamp of the nearest non-NULL value and compare the elapsed interval against a business threshold.
14. **Does IGNORE NULLS UPDATE the table?** No; it only computes values in SELECT. Separate DML is needed to persist changes.
15. **When should you avoid forward fill?** When old values no longer represent the current state or when filling distorts measurement semantics.

When using RESPECT NULLS and IGNORE NULLS, first determine whether NULL is a state to preserve or a gap to skip when locating values. For sequential data imputation, choose the right partition, deterministic ordering, and explicit frame. Forward fill, backfill, and interpolation are three distinct policies; they can yield different results even on the same dataset. Impute only when business rules allow it, and preserve provenance if inferred values are used for reports or critical decisions.
