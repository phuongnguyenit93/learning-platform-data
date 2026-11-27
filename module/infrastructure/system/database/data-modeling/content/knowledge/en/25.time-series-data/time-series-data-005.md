# Partitioning Time Intervals for Storage and Querying

## 1. Why Does Time-Series Data Need Interval Partitioning?

In the **DATABASE_DATA_MODELING** module, the goal is to turn business requirements into a clear data model: identifying entities, relationships, keys, constraints, indexes, and physical schemas, then verifying that the model answers the important questions correctly. For the **Time-Series Data** chapter, a prominent physical decision is **partitioning data into time intervals** (*time-based partitioning*).

Consider an IoT device monitoring platform with 100,000 sensors. Each device sends one reading per minute. The system needs to store temperature, humidity, battery level, and connection status; operators frequently ask:

- What was the average temperature of device 101 over **the last 15 minutes**?
- How many times did the temperature exceed the threshold in **July 2026**?
- On July 15, how many times did devices in a region experience data loss?
- Which detailed data must be retained for **90 days**, and which hourly aggregated data must be retained for **two years**?
- Where should late-arriving events from last month be written?
- When the data store holds billions of readings, how do we avoid scanning irrelevant years?

If all readings are stored in a single huge table, every time-based query risks having to process too much data, while deleting expired data and rebuilding indexes also becomes expensive. **Time-based partitioning** splits a logical dataset into physical parts based on a time column, such as by day or by month.

Example:

~~~text
Logical table: telemetry_reading

Partition 2026-06: [2026-06-01 00:00 UTC, 2026-07-01 00:00 UTC)
Partition 2026-07: [2026-07-01 00:00 UTC, 2026-08-01 00:00 UTC)
Partition 2026-08: [2026-08-01 00:00 UTC, 2026-09-01 00:00 UTC)
...
~~~

A query with the predicate "from the start of July to before August in UTC" may only need to inspect the July partition instead of the entire logical table. When the retention period arrives, the system can manage/drop expired partitions according to a defined policy.

**Partitioning does not by itself change the business meaning of data.** It is solely a storage organization approach. Issues such as exact timestamps, late arrivals, uniqueness, duplicate events, timezone mismatches, and aggregation formulas must still be designed separately.

### Learning Objectives

After this lesson, learners can:

1. Distinguish **event time**, **ingestion time**, **valid time**, and **processing time**, and determine the appropriate time column as the partition key.
2. Design **[from, to)** intervals without overlaps or boundary gaps.
3. Choose partition sizes based on data volume, query patterns, and retention lifecycles.
4. Build `RANGE`-partitioned tables in PostgreSQL, insert data, and verify row placement.
5. Write queries capable of **partition pruning**, avoiding predicates that hinder the planner.
6. Distinguish **storage partitions** from **aggregation time buckets**.
7. Handle late-arriving events, backfills, retention, uniqueness, idempotency, indexes, and operational testing.

## 2. Before Partitioning: What Does One Row Represent?

Good partitions cannot be designed if the **grain** and keys of a row are unclear.

In the sensor example:

> One row is one reading of one metric sent by one device and accepted by the system, at a defined event timestamp.

A reading may contain:

| Field | Meaning | Example |
|---|---|---|
| **tenant_id** | Customer/organization scope | 1 |
| **device_id** | Device sending the metric | 101 |
| **event_id** | Unique identifier assigned by source/ingest within a defined scope | UUID |
| **event_ts** | Timestamp when the event was measured or occurred | 2026-07-15 08:05 UTC |
| **received_at** | Timestamp when the system received or recorded the reading | 2026-07-15 08:06 UTC |
| **metric_code** | Metric type | temperature_c |
| **metric_value** | Measured value | 28.3 |
| **quality_code** | Quality/reliability | OK |
| **metadata** | Governed additional attributes | Firmware, transport source |

If a message contains both temperature and humidity, you can choose the **one device message** grain with multiple measurement columns or the **one metric in a message** grain with `metric_code` and `metric_value`. The two choices lead to differences in row counts, keys, and queries.

For example, a device message has two metrics; if split into two rows using the same `event_id`, the unique key **(event_id)** is not enough to distinguish them. There must be `metric_code` or a separate `measurement_id` in the key. In this lesson, **event_id** is assumed to be the **ID of each individual reading**, not the ID of a packet containing multiple readings.

### 2.1. Data Time Does Not Have a Single Meaning

| Time Axis | Question | How Should It Be Understood? |
|---|---|---|
| **event_ts** | When did the device measure it? | Event time, may arrive late |
| **received_at** | When did the system receive the reading? | Ingestion time |
| **processed_at** | When did the worker finish processing? | Pipeline processing time |
| **valid_period** | During which period is a state/rule effective? | Business time, usually an interval |
| **known_period** | During which period did the system accept an assertion? | Supports bitemporal history if needed |
| **snapshot_at** | Which cutoff point does the snapshot represent? | Depends on source/cutoff definition |

For example, a sensor measures at **23:55 on June 30**, but due to network loss only sends at **00:15 on July 1**. Partitioning by `event_ts` places the reading in the June partition. Partitioning by `received_at` places it in the July partition.

No single choice is always right for every system:

- **Partitioning by event time** fits "when did it happen?" queries, historical data windows, and reports aligned to actual measurement dates.
- **Partitioning by ingestion time** can be useful when write volumes are high, source clocks are unreliable, or queries primarily filter by receipt time.
- The system must have a dedicated strategy if queries frequently filter **both timestamps**, or if reports need to know "what did the system know at time K?"

**Principle:** choose the partition key from **authoritative queries and data lifecycles**, not merely because a column is named timestamp.

## 3. Half-Open Intervals [from, to): The Foundation of All Boundaries

For two time boundaries A and B, the standard convention is:

~~~text
[A, B)

t belongs to the interval when:
A <= t AND t < B
~~~

The left boundary is included; the right boundary is excluded. Two consecutive intervals can share the same end/start instant without **overlapping**:

~~~text
June partition: [06/01 00:00, 07/01 00:00)
July partition: [07/01 00:00, 08/01 00:00)

07/01 00:00 does not belong to June.
07/01 00:00 belongs to July.
~~~

If using the predicate **event_ts BETWEEN A AND B**, PostgreSQL interprets `BETWEEN` as **inclusive of both ends**. An event at exactly `08/01 00:00` could be counted in both July and August if both reports write `BETWEEN` using the start of the next month.

Write correctly:

~~~sql
WHERE event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
~~~

Do not invent a synthetic end boundary **23:59:59.999** and hope it fits every precision. A system with microsecond resolution can have multiple records after that instant and before `00:00`.

### 3.1. Boundaries by Absolute Instant or Local Calendar Date?

July in **UTC** is:

~~~text
[2026-07-01 00:00+00, 2026-08-01 00:00+00)
~~~

July in **Vietnam calendar, UTC+07** is:

~~~text
[2026-07-01 00:00+07, 2026-08-01 00:00+07)

Equivalent in UTC:
[2026-06-30 17:00+00, 2026-07-31 17:00+00)
~~~

A reading at **2026-07-01 00:30+07** is **2026-06-30 17:30 UTC**. If physical partitions are split by UTC month, this reading belongs to the **June partition**, even though a Vietnam calendar monthly report counts it in July.

This is **not a partitioning bug**. It shows that **storage boundaries** and **business calendar reporting boundaries** can differ. A Vietnam July report query may need to read the end of the June partition and most of the July UTC partition.

### 3.2. Temporal Types and Timezones

For events that are **absolute instants**, prefer **timestamptz** in PostgreSQL and specify the timezone when inserting/comparing. PostgreSQL stores the semantics of an instant; display formatting depends on the session timezone.

For business dates such as "closing balance on July 31", you can use **date** and define the corresponding business calendar. Do not derive a transaction's business date by taking the UTC date when the business actually uses a local calendar.

In regions observing daylight saving time, a local day may not last exactly 24 hours. When computing local day intervals, use the **start of local day for two consecutive days** in the defined timezone rather than always adding 24 hours to a timestamp.

## 4. Choosing Partition Size: Hourly, Daily, Weekly, or Monthly?

Partition size must balance data volume, partition count, query patterns, and operational actions.

| Partition Period | Fits Scenarios | Benefits | Risks |
|---|---|---|---|
| **Hourly** | Very high write rate, hourly retention, short hot window | Small segments, drop by hour | Many partitions/indexes, complex management |
| **Daily** | Many events/day, queries commonly by day | Convenient daily retention and backfill | Child table count grows rapidly over years |
| **Weekly** | Moderate volume, weekly retention schedule | Balance between daily/monthly | Week boundaries require ISO/business calendar definition |
| **Monthly** | Moderate volume, multi-year retention, monthly queries | Fewer partitions, easy maintenance | Partitions may grow too large if traffic increases |
| **Quarterly/Yearly** | Small data or long-term archive | Little metadata | Poor pruning for short queries, hard to drop small periods |

There is no law that "1 partition must equal N GB." Choose based on actual row/byte counts, index size, concurrently open partitions, query span, vacuum/maintenance duration, retention cost, and the DBMS's ability to handle query planning.

### 4.1. Volume Estimation Example

Suppose:

~~~text
100,000 devices
1 reading/minute/device
1,440 minutes/day

=> 144,000,000 readings/day
=> roughly 4.32 billion readings / 30 days
~~~

If one reading plus overhead and indexes consumes an average of **200 bytes** in a rough estimate, payload plus estimated overhead is already around **28.8 GB/day** and **864 GB/30 days**. This is not an actual PostgreSQL measurement; actual size must be measured with real data, column types, compression, WAL, indexes, replication, and retention policies.

At that throughput, **monthly** partitions may be too large for some maintenance operations; **daily** partitions or adding a secondary split by tenant/device may make more sense. However, if each daily partition still holds too many rows, partitioning alone does not solve all storage and write-throughput requirements.

### 4.2. When Should You Avoid Over-Partitioning?

If there are 10,000 partitions each holding a few hundred records, metadata, planning, index counts, and management operations can become significant overhead. More partitions **do not automatically guarantee faster queries**.

Increasing partition count should only be done when there is evidence that the previous size causes trouble for queries or data lifecycles. At small scale, a single table indexed on **(tenant_id, device_id, event_ts)** may already be sufficient.

## 5. What Is Partition Pruning?

**Partition pruning** is the ability of the query planner or executor to eliminate partitions that cannot contain rows matching the query predicates.

Suppose a table has 36 monthly partitions storing three years of data. A query:

~~~sql
SELECT COUNT(*)
FROM telemetry_reading
WHERE event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00';
~~~

may only have to inspect the July partition if partitioned by **RANGE(event_ts)** with those exact bounds.

The query still has to scan the necessary rows **inside** the July partition. Pruning only eliminates irrelevant partitions; **it does not replace indexes inside a partition** and does not make `GROUP BY` free.

### 5.1. Keep the Partition Key Column in Direct Comparisons

A partitioning-friendly query predicate:

~~~sql
WHERE event_ts >= :start_ts
  AND event_ts <  :end_ts
~~~

Application parameter binding for **:start_ts** and **:end_ts** must pass parameters of the right type; in this illustrative SQL these are not built-in PostgreSQL variables.

Avoid predicates such as:

~~~sql
WHERE DATE(event_ts) = DATE '2026-07-15'
~~~

if the optimization goal is pruning based on `RANGE(event_ts)`. Wrapping the partition column in a function can make it harder or impossible for the planner to infer which partitions to read in certain plans/versions, and **DATE(event_ts)** on `timestamptz` also depends on the session timezone.

Change it to:

~~~sql
WHERE event_ts >= TIMESTAMPTZ '2026-07-15 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-07-16 00:00:00+00'
~~~

For a **Vietnam day**, use the **+07** boundaries of two consecutive days. Do not cast the column to `date` and apply a UTC cutoff outside the business meaning.

### 5.2. Device Queries Without a Time Range

~~~sql
SELECT *
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101;
~~~

Without bounding **event_ts**, the system may have to inspect **every partition** because device 101 could appear in every period. Per-partition device indexes can still help, but the number of partitions visited may be large.

This shows that a time predicate should be **part of the historical data lookup API** when workloads typically request only recent intervals.

### 5.3. Verifying with Execution Plans

You can use:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00';
~~~

Inspect the scan nodes, partitions touched, buffer reads, and execution time. On empty or very small tables, PostgreSQL may choose a sequential scan on the partition even while pruning properly; that is not automatically an error.

Do not conclude performance from a single plan on a few sample rows. Benchmark with realistic data volumes, per-device query selectivity, and actual partition counts.

## 6. Two Distinct Decisions: Storage Partitioning vs. Aggregation Grouping

**Storage partitions** and **time buckets used in GROUP BY** are often confused.

- **Partition storage**: determines which physical structure stores the rows, e.g., the July partition.
- **Time bucket / tumbling window**: groups events falling into intervals such as 5 minutes, 15 minutes, or one hour to compute `AVG`, `SUM`, `MIN`, `MAX`.
- **Sliding window**: a moving analysis interval, e.g., the last 15 minutes updated every minute.
- **Session window**: groups activity separated by inactivity gaps.
- **Retention window**: how long data is kept.

For example, July's data resides in **one monthly partition**, yet a query may divide it into **2,976 15-minute buckets** for a 31-day month (31 × 24 × 4). Conversely, an hourly bucket at a month boundary may also fall within a single partition depending on timezone conventions.

~~~text
Storage partition (month):
[---------------------- July ----------------------)

Reporting buckets:
[15m)[15m)[15m)[15m)...[15m)
~~~

**Partitioning does not automatically compute bucketed AVG values.** You still need aggregation queries, rollup tables/materialized views, or a time-series engine with corresponding aggregation features.

## 7. PostgreSQL Schema: Telemetry Table Partitioned by Event Time

PostgreSQL supports declarative partitioning with **PARTITION BY RANGE**. The following example uses **event_ts timestamptz** and **UTC monthly** partitions.

Assumptions:

- Each `event_id` identifies **one reading** within a defined source scope.
- One tenant has many devices; one device sends many metrics.
- Detailed readings are queried by **when the device recorded them**, so `event_ts` is chosen as the partition key.
- Each reading stores one numeric value; unit information for the metric is determined via **metric_code** and external metadata/catalogs outside this example.
- Operations correcting/amending old data must go through a dedicated workflow rather than assuming measurements are always strictly accurate.

### 7.1. Creating the Parent Table with Baseline Constraints

~~~sql
CREATE TABLE telemetry_reading (
    tenant_id     bigint NOT NULL,
    device_id     bigint NOT NULL,
    event_id      uuid NOT NULL,
    event_ts      timestamptz NOT NULL,
    received_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    metric_code   text NOT NULL CHECK (length(metric_code) > 0),
    metric_value  numeric(18, 4) NOT NULL,
    quality_code  text NOT NULL DEFAULT 'OK',

    CONSTRAINT pk_telemetry_reading
        PRIMARY KEY (event_ts, tenant_id, device_id, event_id)
)
PARTITION BY RANGE (event_ts);
~~~

Characteristics:

- **The parent table `telemetry_reading`** is the logical surface for `INSERT` and `SELECT`.
- **event_ts** selects the target partition.
- **PRIMARY KEY** includes **event_ts**, respecting PostgreSQL's unique constraint restriction on `RANGE`-partitioned tables.
- That key **does not prove `event_id` is unique across all time intervals**. The same `event_id` with two different `event_ts` values can still exist; idempotency must be designed if required by business rules.
- There is no **CHECK(received_at >= event_ts)** because device clocks may run fast/slow, data may arrive late, or clocks may be adjusted; anomalous timestamp checks should be separated into data-quality rules rather than enforcing an invariant that may not hold.

A numeric value can represent negative temperatures, so do not put `CHECK(metric_value >= 0)` globally across all metrics. For humidity percentage, battery level, or rainfall, each metric has a different valid domain; validate per **metric_code** or via dedicated schemas/validators.

### 7.2. Creating UTC Monthly Partitions

~~~sql
CREATE TABLE telemetry_2026_06
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-06-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-07-01 00:00:00+00');

CREATE TABLE telemetry_2026_07
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-07-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-08-01 00:00:00+00');

CREATE TABLE telemetry_2026_08
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-08-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-09-01 00:00:00+00');
~~~

PostgreSQL validates partition bounds under the same parent to prevent overlapping ranges. At exactly `07/01 00:00 UTC`, rows go into **telemetry_2026_07**, not June.

These partitions only cover June–August 2026. If you `INSERT` September data before a matching partition exists, PostgreSQL will **raise a no-partition-found error**. The application must schedule future partition creation or have a clear policy for unmapped data. Never treat this error as a successfully saved reading.

A `DEFAULT` partition can be created as a buffer, but you must manage invalid-timestamp sources, backfills, splitting data from `DEFAULT` into target partitions, buffer growth, and operations that may incur locks/scans. A `DEFAULT` partition must not become a permanent dumping ground where bad data goes undetected.

### 7.3. Indexing for Device Query Patterns

~~~sql
CREATE INDEX idx_telemetry_tenant_device_time
ON telemetry_reading (tenant_id, device_id, event_ts DESC);
~~~

In PostgreSQL versions supporting partitioned indexes, creating an index on the parent creates corresponding indexes on each partition. It targets queries for **one tenant/device within a time range**, or fetching the latest reading.

This index does not replace partition pruning. If queries filter only by `metric_code` without `device_id`, another index may be needed after measuring the workload; do not index every imaginable column combination and slow down ingestion.

## 8. Writing Data and Verifying Which Partition Holds Each Row

Insert data through the parent table:

~~~sql
INSERT INTO telemetry_reading (
    tenant_id, device_id, event_id,
    event_ts, metric_code, metric_value
)
VALUES
(
    1, 101, '00000000-0000-4000-8000-000000000001',
    TIMESTAMPTZ '2026-06-30 23:59:00+00',
    'temperature_c', 29.5
),
(
    1, 101, '00000000-0000-4000-8000-000000000002',
    TIMESTAMPTZ '2026-07-01 00:00:00+00',
    'temperature_c', 29.7
),
(
    1, 101, '00000000-0000-4000-8000-000000000003',
    TIMESTAMPTZ '2026-07-01 00:15:00+00',
    'temperature_c', 30.1
),
(
    1, 102, '00000000-0000-4000-8000-000000000004',
    TIMESTAMPTZ '2026-07-15 08:05:00+00',
    'temperature_c', 28.3
),
(
    1, 101, '00000000-0000-4000-8000-000000000005',
    TIMESTAMPTZ '2026-08-01 00:00:00+00',
    'temperature_c', 27.0
),
(
    1, 101, '00000000-0000-4000-8000-000000000006',
    TIMESTAMPTZ '2026-07-01 00:30:00+07',
    'temperature_c', 29.0
);
~~~

The last record is expressed in Vietnam local time, which equals **2026-06-30 17:30 UTC**, so it belongs to the June UTC partition.

Check physical partition names using **tableoid** in PostgreSQL:

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS row_count
FROM telemetry_reading
GROUP BY tableoid::regclass
ORDER BY physical_partition;
~~~

With the exact six readings above, expected output:

| Physical Partition | Row Count |
|---|---:|
| telemetry_2026_06 | 2 |
| telemetry_2026_07 | 3 |
| telemetry_2026_08 | 1 |

Key points to remember:

- Placement depends on the **UTC instant of the timestamp**, not the device's display date string.
- When inserting via the parent table, the DBMS routes rows; the application does not need to build partition names manually as strings.
- If an `UPDATE` changes **event_ts** across a partition boundary, the database may have to move the row between partitions. For telemetry readings, avoid mutating timestamps unless part of an explicit correction workflow.
- **Late-arriving** readings from an older month are routed back to the old partition if that partition still exists.

## 9. Writing Time-Bounded Queries to Leverage Pruning

### 9.1. Latest Reading of a Device in July UTC

~~~sql
SELECT event_ts, metric_code, metric_value
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND metric_code = 'temperature_c'
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
ORDER BY event_ts DESC
LIMIT 1;
~~~

In the sample data, device 101's last temperature reading in July UTC is **00:15 UTC on July 1**, value **30.1**. The **00:30+07** reading does not belong to July UTC; the **08/01 00:00 UTC** reading does not belong either because the right boundary is excluded.

### 9.2. Monthly Average and Sample Count

~~~sql
SELECT
    tenant_id,
    device_id,
    metric_code,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS avg_value,
    MIN(metric_value) AS min_value,
    MAX(metric_value) AS max_value
FROM telemetry_reading
WHERE tenant_id = 1
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
GROUP BY tenant_id, device_id, metric_code
ORDER BY device_id, metric_code;
~~~

**AVG** is computed over **present readings**. If devices report irregularly, the sample average does not necessarily equal a time-weighted average. You must specify the business goal: average of observations, average per minute, or time-continuous average.

### 9.3. Querying July on the Vietnam Calendar

~~~sql
SELECT COUNT(*) AS july_vietnam_samples
FROM telemetry_reading
WHERE tenant_id = 1
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+07';
~~~

The corresponding UTC bounds span **two UTC partitions**: the end of June and most of July. This is the correct consequence of a local calendar; never "optimize" by forcing a Vietnam July query to read only the July UTC partition, as that would miss data from the first 7 hours of July 1 in Vietnam time.

## 10. Time Buckets: Grouping Data by 5 Minutes, 15 Minutes, Hours, or Days

Partitioning is a storage layout; reporting typically needs **time buckets**.

In PostgreSQL 14+, **date_bin** can group instants into fixed-length intervals such as 15 minutes. Grouping temperature values for a device:

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        event_ts,
        TIMESTAMPTZ '2026-01-01 00:00:00+00'
    ) AS bucket_start_utc,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS avg_temperature_c
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND metric_code = 'temperature_c'
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-07-02 00:00:00+00'
GROUP BY bucket_start_utc
ORDER BY bucket_start_utc;
~~~

Sample data for device 101:

| Bucket UTC | Present Value | AVG |
|---|---|---:|
| [00:00, 00:15) | 29.7 | 29.7 |
| [00:15, 00:30) | 30.1 | 30.1 |

**date_bin** does not automatically generate empty buckets. If you need a point for every 15 minutes to render a chart, generate a **time series** and `LEFT JOIN` the aggregated results. Intervals without samples should remain **NULL / no data** unless an interpolation or zero-fill policy is explicitly defined.

### 10.1. Why Not Default Empty Buckets to 0?

For temperature, having no reading does not mean the temperature is 0°C. For network throughput, "no traffic recorded" differs from "measured 0 traffic." A dashboard that blindly fills 0 can trigger false alerts or skew averages downward.

You can choose one of these policies:

- **Null:** no observation yet.
- **Last observation carried forward:** retain the most recent value prior to the bucket, if allowed for the metric and bounded by a staleness limit.
- **Interpolation:** interpolate if the quantity, sampling, and model justify it.
- **Zero-fill:** only for metric types where absence of events truly means 0 and source conditions are verified.

These approaches yield **metrics with different semantics** and must be documented in the metric definition.

### 10.2. Local Calendar Buckets vs. Fixed-Length Buckets

A **15-minute bucket** is a fixed-length interval on the absolute timeline. **A local day or month** is a calendar interval with timezone-aligned boundaries; where DST applies, a local day can be 23 or 25 hours long.

Do not use **date_bin(INTERVAL '1 month', ...)** in PostgreSQL for calendar months; `date_bin` does not support strides containing months or larger units. For monthly grouping, use **date_trunc** with a timezone or a calendar dimension table, while keeping `WHERE` predicates with prunable time bounds.

## 11. Choosing Indexes Within Each Partition

Partition pruning skips irrelevant partitions. **Indexes** speed up finding rows within partitions that still must be read.

| Query Pattern | Strategy Commonly Considered |
|---|---|
| One tenant + device in a time range | B-tree `(tenant_id, device_id, event_ts)` |
| Device and metric by time range | B-tree `(tenant_id, device_id, metric_code, event_ts)` |
| Full-month scan to aggregate all devices | Partition scan / parallel scan depending on volume |
| Large time ranges, physically `event_ts`-correlated rows | `BRIN(event_ts)` can save space |
| Lookup `event_id` to prevent duplicates | Separate dedup/registry structure if global uniqueness needed |
| Analysis by region/device type | Dimension mapping and appropriate rollups, not telemetry indexes alone |

Example BRIN index depending on workload:

~~~sql
CREATE INDEX idx_telemetry_event_ts_brin
ON telemetry_reading USING brin (event_ts);
~~~

BRIN is typically small and helpful when timestamps **correlate with physical row order**. If ingestion inserts many scattered late-arriving readings or data gets reorganized, effectiveness can drop. Never assume BRIN is always better than B-tree.

Create both B-tree and BRIN only when real queries need both; every index increases `INSERT`, WAL, and storage overhead. Use `EXPLAIN`, statistics, and write-throughput measurements to decide.

### 11.1. Index Column Ordering Must Follow Workload

B-tree **(tenant_id, device_id, event_ts DESC)** helps queries scoped to a tenant/device fetching recent points. If most queries filter **metric_code** without filtering `device_id`, that ordering may not be optimal.

Do not add every conceivable index variant. Prioritize high-frequency, high-latency-impact query patterns, then measure total cost.

## 12. Uniqueness, Idempotency, and Global Key Limitations

**Time-series data frequently experiences event retries.** A gateway may time out after the database commits, then resend the same reading. Without idempotency, a reading may appear twice, corrupting `COUNT`, `SUM`, or `AVG`.

For example, the key on the partitioned table:

~~~sql
PRIMARY KEY (event_ts, tenant_id, device_id, event_id)
~~~

lets the database block two rows with the **same four values**, but **does not prevent the same `event_id` from being written with a different `event_ts`**.

In PostgreSQL, `UNIQUE`/`PRIMARY KEY` constraints on a partitioned table must include the partition key columns so the engine can enforce uniqueness across partitions. Thus a global **UNIQUE(event_id)** on a `RANGE(event_ts)` table cannot simply be replaced by individual `UNIQUE` indexes per partition while preserving the same semantics.

### 12.1. Preventing Duplicate event_id Regardless of event_ts

You can use a non-time-partitioned registry table with a unique business key:

~~~sql
CREATE TABLE ingest_event_registry (
    tenant_id      bigint NOT NULL,
    source_system  text NOT NULL,
    event_id       uuid NOT NULL,
    first_event_ts timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, source_system, event_id)
);
~~~

A write protocol:

1. Start transaction.
2. Insert the idempotency key into the registry. If duplicate, inspect the already-processed record and return the appropriate status, **without inserting telemetry again**.
3. Insert the reading into `telemetry_reading`.
4. Commit in the **same transaction** if both tables reside in the same database.
5. Retries must identify the same `event_id`, source, and tenant; if payload differs while ID matches, treat as a **conflict** to investigate rather than blindly overwriting.

If using **INSERT ... ON CONFLICT DO NOTHING** on the registry, the application must check whether a new row was actually inserted rather than proceeding to insert telemetry even when the registry entry already existed.

A registry adds write cost and maintains a global key. If idempotency is only needed within a retry window, a separate retention strategy can apply, but dropping registry entries means accepting/handling the risk of receiving old events again. Never choose a registry TTL without accounting for how long sources can retry.

### 12.2. Event Timestamp Is Not a Reliable Identity Key

Two sensors can send two measurements in the same microsecond. One device may replay a reading with an altered timestamp after a clock adjustment. Therefore **(device_id, event_ts)** is only a unique key if the source protocol **truly guarantees** at most one reading at that exact instant for that metric type.

For multi-metric streams, `event_id` or a source sequence number also helps distinguish readings independently of timestamps.

## 13. Late-Arriving Events and Data with Invalid Timestamps

A reading with a June **event_ts** but July **received_at** is normal when a device loses connectivity. When partitioned by `event_ts`:

- If the June partition still exists and allows writes, the reading is inserted there.
- If the June partition has been dropped per retention, `INSERT` may fail for lack of a partition.
- If `event_ts` falls outside valid bounds (a device sending year 1970 or 2099), never silently create arbitrary partitions and treat the data as valid.

### 13.1. Explicit Late-Arrival Policy

| Scenario | Possible Handling Option | What Must Be Published |
|---|---|---|
| 5 minutes late | Ingest into existing partition | Delay relative to `received_at` |
| 2 days late | Ingest into older daily/monthly partition | Affected rollups/aggregates |
| 2 months late, raw already archived | Controlled restore/backfill or staging area | Recovery scope and cost |
| Far-future timestamp | Quarantine, alert on clock skew | Acceptable clock-skew threshold |
| Timestamp before allowed data era | Reject or store in exception table | Do not break retention |
| Same `event_id`, different timestamp | Conflict/dedup by source | Do not create two readings |

A **watermark** can represent a timestamp prior to which the pipeline expects data to be complete per SLA. However, a watermark is a **latency and processing commitment**, not logical proof that no older event will ever arrive. You need an exception-handling policy for post-watermark events.

### 13.2. Backfills and Aggregate Correctness

If a June temperature reading arrives in July, the raw June partition can be updated, but pre-built June summary tables may **no longer be accurate**.

Options:

- Mark affected buckets and **recompute** from raw.
- Apply incremental adjustments if the formula supports safe updates.
- Track rollup version, recomputation timestamp, and source.
- Close periods after an SLA cutoff, then handle exceptions via published adjustment records.

`AVG` cannot rely on just a stored average value; incremental updates typically require **SUM and COUNT** of valid readings. When an older reading is corrected/deleted, you also need its prior contribution to subtract from totals.

## 14. Retention, Lifecycle, and Dropping Partitions

Time-series data typically follows an **age-based lifecycle**:

~~~text
Raw hot (0–7 days):
  queried frequently, heavy writes

Raw warm (8–90 days):
  detailed storage, queried less often

Rollup hourly (0–2 years):
  retained hourly aggregates

Archive cold (after 90 days if policy allows):
  reconciliation/recovery at higher cost
~~~

This is only an example. Actual retention periods must be based on business requirements, contracts, regulations, budgets, and data types.

### 14.1. Dropping a Partition Instead of Row-by-Row DELETE

Once the entire June partition has expired, you can consider:

~~~sql
-- Illustrates a destructive data operation.
-- Execute only after completing retention workflow,
-- verifying period, permissions, backup/archive, and dependencies.

ALTER TABLE telemetry_reading
DETACH PARTITION telemetry_2026_06;

-- DROP TABLE telemetry_2026_06; -- Only after deletion approval.
~~~

**DETACH** separates the child table from the parent without deleting the detached table's data. **DROP TABLE** physically deletes that table's data. These operations require checking permissions, locks, and impact on active queries; concurrent detach syntax/support depends on PostgreSQL version and context.

If data moves to an archive after `DETACH`, record the archive location and guaranteed queryable range. If late-arriving events for that period still occur, route them to a historical-data handling workflow; do not assume data was saved into a detached partition.

### 14.2. Partition Boundaries Must Align with Retention Policies

If policy requires retaining raw data for **exact 90 calendar days**, yet partitions are **monthly**, you cannot drop a partial month using monthly partition drops alone. You can:

- Choose daily partitions for finer-grained retention.
- Accept keeping extra days until the partition finishes, if policy allows.
- Combine deleting boundary rows with dropping whole older partitions, accepting `DELETE`/vacuum overhead.

Retention should never rely on manually named partition strings; verify **actual partition bounds**, expired data periods, and any legal holds/audit requirements before deleting.

### 14.3. Raw and Rollup Have Independent Retention

Keeping hourly averages for two years does not mean **individual readings** can be recovered once raw data is deleted. If the business requires inspecting a specific event at a given minute last year, hourly aggregates cannot replace raw data.

APIs should therefore clearly state windows:

- Reading-level detail: 90 days.
- Hourly statistics: two years.
- Daily statistics: possibly longer per contract.

Never advertise detailed historical queries for timeframes where raw data has already expired.

## 15. Pre-Aggregate, Partition, or Both?

At scale, systems commonly combine multiple tiers:

~~~mermaid
flowchart TD
    A["Devices / event sources"] --> B["Ingest + timestamp / event_id checks"]
    B --> C["Raw telemetry partitioned by event_ts"]
    C --> D["15-minute rollup"]
    D --> E["Hourly / daily rollup"]
    E --> F["Dashboards and historical reports"]
    C --> G["Detailed event lookup"]
    C --> H["Archive / retention"]
~~~

Each tier answers different questions:

- **Raw**: recover individual readings, diagnose anomalies at full resolution.
- **15-minute rollup**: near-real-time dashboards with far fewer rows.
- **Hourly/daily rollup**: long-term trend analysis.
- **Archive**: compliance evidence or on-demand recovery under slower SLAs.

Raw and rollup tables can use **different partition periods**—for example, daily partitions for raw and monthly partitions for rollups. There is no reason to force every tier onto the same partition size.

### 15.1. Rollup Table with Its Own Grain

Example grain: **one tenant–device–metric–15-minute bucket**:

~~~sql
CREATE TABLE telemetry_15m_rollup (
    tenant_id     bigint NOT NULL,
    device_id     bigint NOT NULL,
    metric_code   text NOT NULL,
    bucket_start  timestamptz NOT NULL,
    sample_count  bigint NOT NULL CHECK (sample_count >= 0),
    sample_sum    numeric(24, 4) NOT NULL,
    min_value     numeric(18, 4),
    max_value     numeric(18, 4),

    PRIMARY KEY (
        bucket_start, tenant_id, device_id, metric_code
    )
)
PARTITION BY RANGE (bucket_start);
~~~

This table requires **child partitions** before inserting; it illustrates grain rather than a complete rollup pipeline. Giving rollups their own parent table allows independent lifecycles and indexes.

`AVG` across buckets is computed as:

~~~sql
SELECT
    tenant_id,
    device_id,
    metric_code,
    SUM(sample_sum) /
        NULLIF(SUM(sample_count), 0) AS avg_from_rollup
FROM telemetry_15m_rollup
WHERE bucket_start >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND bucket_start <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
GROUP BY tenant_id, device_id, metric_code;
~~~

Taking **`AVG(sample_avg)` across buckets** is wrong whenever buckets hold unequal sample counts. Compute **`SUM(sample_sum) / SUM(sample_count)`** instead.

If the metric represents a **time-weighted** temperature average rather than sample-count average, store time-weight totals instead of `sample_count`. For percentiles, medians, or distinct counts, `SUM`/`COUNT` is insufficient; store mergeable sketches/aggregate states or recompute from raw.

### 15.2. Rollups May Lag Behind Fresh Raw Telemetry

If an aggregation worker runs hourly, new raw rows exist before the latest hourly rollup finishes. APIs should expose **`watermark`/`last_refreshed_at`** and blend raw rows only for unclosed buckets—never summing finalized rollups together with raw rows from the same period and double-counting.

## 16. Time Partitioning Plus a Second Dimension

When a single daily partition grows too huge across thousands of tenants, you can sub-partition by **tenant, device, or hash**. This is composite partitioning or sharding—not a free optimization.

Conceptual layout:

~~~text
RANGE(event_ts by day)
    -> HASH(tenant_id) or HASH(device_id)
~~~

Benefits include smaller per-shard sizes and distributed write load. Trade-offs include:

- More physical tables, indexes, and catalog metadata.
- Cross-tenant or cross-device queries must scan multiple shards.
- Cross-shard aggregations and transactions grow more complex.
- Unique keys must align with the partitioning layout.
- Hotspots persist if one tenant or device generates most of the traffic.
- Retention and archiving must act across every shard of an expired period.

Do not pick hash bucket counts blindly from device counts. Measure skew, write rate, physical partition count, tenant/device filter selectivity, and engine limits.

### 16.1. Time Partitioning vs. System-Wide Sharding

**Partitioning** splits data under one logical table within a single DBMS instance. **Sharding** distributes data across independent nodes/databases, introducing distributed routing, transactions, and cross-shard query coordination.

Dedicated time-series databases often automate **chunks/hypertables** over time and space dimensions. Regardless of engine, you must still define event time, retention, data contracts, identity keys, and aggregate correctness.

## 17. Relational, Document, Graph, and Analytical Models

The mindset of **choosing time slices from query patterns and lifecycle** applies across storage engines.

| Model | Common Organization | What to Watch Carefully |
|---|---|---|
| **Relational / PostgreSQL** | `RANGE` partitions by timestamp, per-partition indexes | Global unique keys, pruning, DDL/maintenance |
| **Time-series database** | Chunks/hypertables, time buckets, compression, retention policies | Event vs. ingest time, late arrivals, continuous-aggregate refreshes |
| **Document** | Monthly collections or partition keys embedding time | Cross-collection queries, TTLs, indexes, duplicate events |
| **Graph** | Effective-dated or event-time edges/nodes | Temporal path queries, consistency across edges |
| **Analytical warehouse / lakehouse** | Partitioned by ingest/business date, clustering, file pruning | Small files, late data, partition rewrites, metadata |
| **Event stream / log** | Topic-partitions/segments by offset or sequence | Offset order is not event date; event times arrive out of order |

### 17.1. Document: Monthly Collections Can Create Technical Debt

A simple approach creates **`readings_2026_06`**, **`readings_2026_07`**. However, forcing applications to concatenate collection names per query requires managing:

- Multi-period queries.
- Consistent schemas and indexes across collections.
- Writing late events into archived collections.
- Consistent timezone alignment.
- Retention and access control per collection.
- Unbounded collection growth over time.

Built-in document partitioning or TTL mechanisms are usually cleaner than manual month-named collections. Even then, TTLs do not replace audit requirements or late-data handling.

### 17.2. Graph: Time May Live on Relationships

A device graph may model **`DEVICE_LOCATED_IN_SITE`** edges that change over time. Reporting regional temperatures for July 15 requires resolving which site each device belonged to **on July 15**, not its current site.

Even when readings are cleanly partitioned by `event_ts`, joining against a non-historical location edge corrupts past reports.

### 17.3. Lakehouse: Date Partitioning and Small Files

Columnar/file systems partition by **`event_date`** or **`ingestion_date`** and skip files via metadata. Frequent micro-batches create tiny files that inflate metadata and file-open overhead, requiring compaction, clustering, and rewrite schedules.

Partitioning by `event_date` optimizes historical event queries; partitioning by `ingestion_date` simplifies batch tracking. Under late arrivals, choose priority based on actual query access patterns rather than copying generic configs.

## 18. Partition Operations: Pre-Creation, Monitoring, Reconciliation, and Recovery

Partitioning is an **ongoing operational process**, not a one-time `CREATE TABLE`.

### 18.1. Pre-Creating Future Partitions

Run a scheduled job creating partitions **ahead** of upcoming periods with buffer for clock skew and ingestion schedules. Before August begins, the August partition must already exist.

The job must be **idempotent**: re-running it must neither duplicate partitions nor alter existing bounds. Failures must alert operators well before writes start failing.

Scripts deriving partition names and bounds from timestamps must respect timezones, leap years, and 28/29/30/31-day months—never assume every month has 30 days.

### 18.2. Operational Monitoring Metrics

| Operational Metric | Significance |
|---|---|
| Future partitions ready | Prevents write failures at period boundaries |
| Partition count and per-partition size | Tracks growth and skew |
| Rows rejected due to missing partition | Catches scheduling failures |
| Lag `received_at − event_ts` | Shows late-arrival distribution and clock skew |
| Deduplicated event count | Tracks retry rates |
| Queryable raw time span | Verifies retention compliance |
| Watermark / last rollup refresh | Tracks dashboard freshness |
| Rows/bytes per tenant/device | Detects hot tenants |
| Query latency and buffer reads | Verifies pruning and indexing |
| Active backfills/rebuilds | Prevents publishing incomplete numbers |

**`received_at − event_ts`** can be negative when a device clock runs fast; treat it as a data-quality signal to investigate, not necessarily a hard `CHECK` constraint on raw ingestion.

### 18.3. Recovery Requirements

When a partition is missing or data lands in the wrong slice due to timezone errors, your runbook must answer:

1. Is raw input still available in logs, brokers, or object storage?
2. Does an idempotency key allow re-importing without duplicates?
3. Which rows landed in the wrong partition, and which were never written?
4. Which rollups are affected and can be recomputed from raw?
5. Do published dashboards/reports require formal revisions?
6. Can writes to the affected period be paused or fenced during remediation to prevent races?

Never merely “rename a partition” to fix a boundary mistake: table names do not govern `RANGE` bounds, and rows may need relocation by timestamp.

## 19. Mandatory Test Matrix

### 19.1. Time Boundaries

| Event Timestamp | Expected UTC Partition |
|---|---|
| `2026-06-30 23:59:59+00` | June |
| `2026-07-01 00:00:00+00` | July |
| `2026-07-31 23:59:59+00` | July |
| `2026-08-01 00:00:00+00` | August |
| `2026-07-01 00:30:00+07` | June |
| `2026-09-01 00:00:00+00` | Error if September or `DEFAULT` partition missing |
| June event arriving in July | June if partitioned by `event_ts` |

### 19.2. Queries

1. July UTC queries include only `[07/01 00:00 UTC, 08/01 00:00 UTC)`.
2. July 01 Vietnam queries span `[06/30 17:00 UTC, 07/01 17:00 UTC)`, even across two UTC partitions.
3. Per-device `COUNT` does not double-count retries sharing `event_id`.
4. A 15-minute bucket starting at `00:15` contains `00:15`, not the bucket ending at `00:15`.
5. Empty buckets follow defined `NULL`/zero/interpolation rules.
6. Multi-bucket `AVG` uses `SUM(sum) / SUM(count)`, not unweighted `AVG` of bucket averages when counts differ.
7. Queries omitting time predicates are measured to expose multi-partition scan costs.
8. Inspect `EXPLAIN` and buffers on large datasets rather than treating toy datasets as benchmarks.

### 19.3. Operations and Integrity

1. Missing target partition causes `INSERT` to fail loudly, never succeeding silently.
2. Concurrent workers creating the same partition do not break the schema; provisioning is idempotent.
3. Late events targeting archived or dropped partitions follow a defined policy.
4. Duplicate `event_id` with a different timestamp is caught by business-level idempotency rather than relying solely on the composite PK.
5. Registry and telemetry writes occur in the same transaction or verified consistency boundary.
6. Backfills altering older data trigger rollup recomputation or stale flags.
7. Retention never drops partitions before expiration or while legal holds apply.
8. Migration from an unpartitioned table loses zero rows at exact month-start boundaries.
9. Switching device formatting from local offset to UTC does not alter event instant semantics.
10. Tenant and source isolation boundaries remain intact across all partitioned tiers.

## 20. Practical Exercise: Designing a 2-Billion-Readings-per-Month System

A cold-chain monitoring business ingests roughly **2 billion readings per month** across multiple tenants; 70% of queries inspect **the last 24 hours** of a single device, 25% generate **monthly regional reports**, and 5% investigate incidents over **the past 90 days**.

Requirements:

- Detailed readings retained **90 days**; hourly summaries retained **two years**.
- Devices occasionally lose connectivity and deliver readings delayed **up to 48 hours**.
- Devices may resend an old `event_id` on retries.
- Dashboards refresh every 15 minutes while explicitly surfacing intervals with missing data.
- Device zone assignments can change, so historical reports must use **the zone effective on the measurement date**.
- Some devices exhibit multi-day clock skew requiring quarantine and verification.

Design the solution:

1. **Choose raw grain:** one measurement for one metric of one device. Specify key attributes (tenant, device, `event_id` or source version) and valid domains.
2. **Distinguish timestamps:** `event_ts`, `received_at`, `processed_at`, source clock. Explain why `event_ts` or `received_at` fits the stated query patterns.
3. **Choose partition period:** daily or monthly? Estimate average readings/day and analyze the partition count vs. size trade-off quantitatively.
4. **Set UTC boundaries:** define half-open daily/monthly intervals; write a Vietnam-day query and identify which UTC partitions it must read.
5. **Write PostgreSQL DDL:** parent table `PARTITION BY RANGE(event_ts)`, PK compatible with unique-constraint rules, child partitions, and tenant–device–time indexes.
6. **Prevent duplicates:** specify registry or source-sequence deduplication; handle retries where `event_id` matches but payload differs.
7. **Handle 48-hour late arrivals:** keep older partitions writable, define watermark handling and 15-minute rollup recomputation.
8. **Aggregates:** define 15-minute rollup grain storing `sample_sum`/`sample_count`, compute `AVG` from sums, and handle empty buckets with `NULL` or explicit rules.
9. **Retention:** enforce 90-day raw retention and two-year hourly rollups without losing data via premature partition drops.
10. **Historical zones:** model device–zone assignments with `valid_period`, joining temporally on `event_ts` or business date as required.
11. **Queries:** fetch trailing 24 hours for a device, monthly event `COUNT`, daily `MAX` temperature, and effective-zone reports.
12. **Quality tests:** test `00:00` boundaries, clock skew, duplicates, missing partitions, late arrivals, and zone history changes.
13. **Reconciliation:** compare raw readings against rollups after a backfill; publish reports only once data versions are verified.
14. **Limitations:** explain why an hourly aggregate cannot pinpoint the exact threshold breach at `12:30:15` once raw data has expired.

**Passing criteria:** partition granularity driven by queries and retention; zero boundary data loss; source-backed uniqueness; consistent late-event and rollup handling; explicit awareness of downsampling limits; queries never conflate storage partitions with reporting time buckets or ingestion timestamps.

## 21. Design Checklist and Conclusion

Before deploying time-series partitioning, confirm:

- **Grain:** is each row a measurement, an event, a state, or a snapshot?
- **Timestamps:** are event time, ingestion time, valid time, and business date clearly separated?
- **Intervals:** do partitions use `[from, to)` with zero overlaps and zero boundary gaps?
- **Timezones:** are physical boundaries UTC or local calendar? Are cross-timezone reports computed accurately?
- **Size:** was hourly/daily/monthly chosen from data volume, queries, and maintenance rather than guesswork?
- **Pruning:** do APIs supply direct `event_ts` predicates enabling partition elimination?
- **Indexes:** do per-partition indexes match real queries without crippling ingestion?
- **Uniqueness:** do PK/`UNIQUE` constraints include the partition key as required, and is global `event_id` deduplication addressed?
- **Late arrivals:** do backfills and late events have an explicit workflow instead of silent drops?
- **Rollups:** are buckets, windows, sum/count, missing data, recomputation, and watermarks clear?
- **Retention:** are drop/detach/archival steps verified with independent raw vs. aggregate windows?
- **Operations:** are future partitions pre-created, missing-partition errors monitored, `EXPLAIN` verified, and skew/retries tracked?
- **Other engines:** if using document, graph, TSDB, or lakehouse systems, are temporal and data invariants still preserved?
- **Testing:** have you tested month-start/end boundaries, local timezones, late timestamps, duplicates, and empty buckets?

**Core principle:** time partitioning is a **storage organization decision**, not a transformation that alters business truth. Choose **the right time axis**, enforce **half-open boundaries**, size **partitions from queries and retention lifecycles**, and pair pruning, indexing, retention, and rollups with crisp semantics. A trustworthy time-series model reads efficiently, preserves boundary accuracy, and explains exactly what happens when telemetry arrives late or gets revised.
