# Modeling Device Temperature or Operational Metrics by Read Pattern

## 1. Ask Query Questions Before Choosing a Time-Series Storage Structure

In the `DATABASE_DATA_MODELING` module, learners practice turning business requirements into clear data models—from entities, relationships, constraints, and normalization to keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical storage approaches. For the **Time-Series Data** chapter, the critical decision is not merely “having a `timestamp` column,” but **what needs to be read, over what range, at what resolution, and with what level of accuracy**.

Suppose a factory monitors 20,000 devices. Each device measures temperature every 10 seconds, and some devices also report humidity, RPM, cumulative energy, and connection state. The operations team asks different questions:

- “What is the **latest** temperature of device D-100? Is that value stale?”
- “Over the **past 24 hours**, how did device D-100's temperature fluctuate to plot a 5-minute chart?”
- “Did any device **exceed 85 °C** in the last 10 minutes?”
- “Last month, what was the **highest temperature** of each production line?”
- “What is the hourly energy consumption, given that the sensor sends a **cumulative meter reading**?”
- “When data arrives late or a device changes location, how must historical reports be recomputed?”

A table storing only the “latest value” can answer the first question very quickly, but **lacks history** to build trends. A raw table containing every measurement can answer historical queries, but is not necessarily suitable for continuously scanning billions of rows for a dashboard. A 5-minute aggregation table reduces read cost, but can hide brief temperature spikes or lose event ordering.

The goal is to design **representations suited to specific read paths** and to know which dataset is the **source of truth**.

### Learning Outcomes

After this lesson, learners can:

1. Define the grain of a measurement sample by tenant, device, metric type, and timestamp; distinguish new samples from retries or corrections.
2. Distinguish **gauge**, **counter**, **delta**, and **state** metric kinds, avoiding incorrect sums or averages.
3. Choose among **wide** tables, **narrow/long** tables, document payloads, and rollup tables based on workload.
4. Design queries for **latest value**, detailed history, 5-minute buckets, threshold detection, and device/group statistics.
5. Handle event time, received time, timezones, gaps, late data, duplicates, faulty sensors, and metadata changes.
6. Build constraints, partitions, indexes, and rollups in PostgreSQL 16; state the limits when moving to a time-series engine or analytical warehouse.
7. Verify using `EXPLAIN`, boundary testing, sample-count reconciliation, and retention/recovery strategies.

## 2. Read-Pattern Matrix Drives the Physical Model

Before writing DDL, gather **access patterns**, frequencies, and filter predicates:

| Read Pattern | Scope | Time Range / Resolution | Typically Useful Structure |
|---|---|---|---|
| A. Latest value for one device | One `device_id` and `metric_code` | One latest point, requires freshness check | Index on device–metric–time; `latest` table if dashboards poll heavily |
| B. Temperature curve of one device | One device/metric | 24 hours, 5-minute chart | Time-filtered raw readings or 5-minute rollup |
| C. Threshold breach detection | A group of devices/tenant | Last 10 minutes, must preserve peaks | Raw or rollup with `MAX` and quality metadata |
| D. Daily production-line report | Hundreds/thousands of devices | One month, aggregated | Hourly/daily rollup + device line-assignment history |
| E. Total energy consumption | One or more meters | Hourly counter difference, reset detection | Ordered counter data; normalized delta/rate |
| F. Incident investigation | One device, multiple metrics | Raw around a timestamp, exact event order | Append/immutable raw, timestamps, source, and provenance |
| G. Retention management | Entire factory | Drop raw after 90 days, keep rollups 2 years | Time partitioning, archive workflow, and verification tests |

**No single index or single table optimizes A–G equally well.** A design may include a raw table, a latest-state table, rollup tables, and device dimensions. That is not arbitrary duplication if each representation has a clear **purpose, update source, and reconciliation process**.

## 3. Metric Classification: Temperature Is Not a Utility Meter Reading

Units, measurement semantics, and aggregation operators must be tied to the metric definition—not guessed from a column name.

| Metric Kind | Examples | Correct Read / Aggregation | Common Mistake |
|---|---|---|---|
| **Gauge** – instantaneous value | Temperature °C, humidity %, pressure, CPU usage | Latest, `MIN`, `MAX`, average per **sampling rule** | Summing all temperature readings and calling it “shift temperature” |
| **Cumulative counter** – running total | Total kWh, total network bytes, total units produced | Take **valid difference between two points**, handling resets/rollovers | `SUM(counter_value)` to compute consumption |
| **Delta/event count** – incremental amount | Errors in an interval, units just completed | `SUM` over non-overlapping intervals at the right grain | Summing the same delta multiple times due to retries or overlapping windows |
| **State** – discrete status | ONLINE/OFFLINE, RUNNING/STOPPED, fault codes | As-of state, duration per state, transition counts | `AVG(state_code)` interpreted as a physical metric |
| **Distribution/histogram** | Latency histogram, frequency by bucket | Merge compatible buckets, then derive percentiles | Averaging per-machine p95 values to derive system-wide p95 |

**Gauges can have negative values** (such as temperature), whereas cumulative counters are typically non-negative and can reset. Domain validation must follow the **specific metric kind**. A generic `value >= 0` constraint will drop temperature measurements below 0 °C.

### Units and Calibration Provenance

A device might send 86 °F while the system normalizes it to 30 °C, or send raw ADC values requiring conversion using the active calibration configuration. You must store explicitly:

- The **canonical unit** of each metric, e.g., `degC`, `percent`, `Wh`, `rpm`.
- The **original unit**, raw value, and conversion-rule version when reconciliation is needed.
- **Physical/business bounds** and how suspect values are flagged.
- The **calibration version** if restating historical measurements is a requirement.

Never mix °C with °F or Wh with kWh in the same series and plot them as homogeneous data. A unit-converted value stored without provenance can be hard to reconcile when a sensor misconfiguration is discovered.

## 4. Grain and Identity of a Measurement Sample

One option for a temperature series:

> One raw row represents **one normalized measurement sample** for one tenant, one device, and one metric type at one device-reported event timestamp; resending the same sample must not create additional rows.

Assuming the device emits **at most one measurement per** (`tenant_id`, `device_id`, `metric_code`, `observed_at`), the grain can use that unique key. This is a **source-contract assumption**, not a universal truth of time-series data.

### When Timestamp Alone Is Not Enough for Identity

There are exceptions:

- A device emits **two valid samples with the same timestamp** because its clock resolution is only 1 second.
- Two internal sensors in one device measure the same metric at different positions.
- The source system corrects the timestamp of the same event after clock sync.
- A telemetry packet carries multiple metrics or multiple samples, and requires **message ID** tracing.

In those cases, the grain must evolve to include `sensor_id`/`channel_id`, `source_sample_id`, or `sequence_number` under the appropriate namespace. **Do not arbitrarily include `received_at` in the unique key**, because the same event resent later will have a different receive time and be double-counted.

| Key | Role | What Does It Not Guarantee? |
|---|---|---|
| (`tenant_id`, `device_id`, `metric_code`, `observed_at`) | Identifies one point under a one-sample-per-timestamp contract | Unsuitable if the source emits multiple valid samples at the same timestamp |
| (`source_system`, `source_message_id`) within tenant | Idempotency of the source packet | A single packet may contain **multiple** samples/metrics |
| `source_sample_id` or (`message_id`, `item_index`) | Identifies each sample when timestamps collide | Does not by itself describe date/metric or ensure correct units |
| Warehouse-generated `reading_sk` | Physical row identifier | Does not detect retries when the source resends |

Distinguish the **sample unique key** from the **incoming packet key**. A packet containing 12 readings may need one ledger record for the packet and 12 sample rows; both levels have their own idempotency rules.

## 5. Three Time Axes to Control

| Field | Meaning | Example |
|---|---|---|
| `observed_at` | **Event time:** when the sensor measured it | 08:00:10 UTC |
| `received_at` | **Ingestion time:** when the server received/stored it | 08:02:30 UTC |
| `processed_at` or `rollup_refreshed_at` | When the pipeline validated/aggregated it | 08:03:00 UTC |
| `business_date` | Factory/tenant reporting calendar date | Date in `Asia/Ho_Chi_Minh` |
| `calibration_valid_from` | When a calibration configuration takes effect | May differ from when it was entered into the system |

A reading taken at 08:00 but ingested at 08:02 **belongs to the 08:00 bucket** if the chart is defined by event time. Bucketing by `received_at` answers “when did data arrive,” which is suitable for pipeline monitoring, not for analyzing actual temperature at 08:00.

### Device Clocks Are Not Completely Trustworthy

If a device's clock drifts and emits a timestamp 30 minutes ahead of server time, do not silently overwrite `observed_at := received_at`. Flag it as `SUSPECT`/quarantine it and detect the skew:

\[
\mathrm{ingestion\_delay}=received\_at-observed\_at
\]

Negative delay may indicate clock skew, clock sync prior to recording, or timezone conversion bugs. Distinguish acceptable drift from cases that must be corrected with evidence. If a timestamp is corrected, define clearly how **the same original sample** is identified after correction.

### Timezones and DST

`TIMESTAMPTZ` in PostgreSQL stores an absolute instant; display depends on the session timezone. To compute a factory's calendar date, convert the instant to the business timezone and extract the date. In regions with DST, **a calendar day may not be exactly 24 hours long**. Do not hardcode `+ interval '24 hours'` to represent every calendar day worldwide.

## 6. Choosing Wide, Narrow, or Document Based on Read Patterns

### 6.1. Wide Row: Multiple Metrics in One Row

```text
device_snapshot_raw
tenant_id | device_id | observed_at | temperature_c | humidity_pct | rpm
----------+-----------+-------------+---------------+--------------+-----
42        | 100       | 08:00:10    | 31.2          | 60.0         | 1450
42        | 100       | 08:00:20    | 31.4          | NULL         | 1460
```

**Suitable when** channels are sampled on the same cadence, belong to the same device, are frequently read together, and have a stable metric set. Fetching data for a multi-column dashboard can be simpler and involve fewer rows.

**Trade-offs:** if metrics have independent cadences, many columns will be `NULL`; adding a new metric usually requires a schema migration; you must clarify whether `NULL` means not sampled, not yet arrived, or sensor fault. A row may also be updated multiple times when channels arrive out of phase.

### 6.2. Narrow/Long Row: One Metric per Row

```text
sensor_reading
tenant_id | device_id | metric_code | observed_at | metric_value
----------+-----------+-------------+-------------+-------------
42        | 100       | temp_c      | 08:00:10    | 31.2
42        | 100       | humidity    | 08:00:10    | 60.0
42        | 100       | rpm         | 08:00:20    | 1460
```

**Suitable when** devices have heterogeneous metric sets, irregular cadences, queries typically fetch one metric over time, and you want to add new metric types without altering table columns.

**Trade-offs:** row counts and index sizes grow; reading multiple metrics at the same timestamp may require pivoting, joining, or aggregation; numeric, state, and histogram metrics cannot be forced into a single `NUMERIC` column without losing semantics. Separate tables by **data type or metric kind** may be needed.

### 6.3. JSON/Document Event: One Packet, Multiple Fields

```json
{
  "source_message_id": "gw-42-100-000018",
  "device_code": "D-100",
  "observed_at": "2027-01-15T08:00:10Z",
  "measurements": {
    "temp_c": 31.2,
    "humidity_pct": 60.0,
    "rpm": 1450
  }
}
```

**Suitable when** preserving the exact source payload is required, schemas are unstable, and multiple metrics arrive in one communication packet. It works well as **raw ingestion/staging**, before transforming into canonical metric rows for querying and testing.

**Trade-offs:** valid JSON does not guarantee each metric is valid in type, unit, or domain; per-metric FKs are hard to enforce, and JSON `null` differs from a missing key; querying nested values requires expression/GIN indexes or ETL. Do not treat a document containing an array of readings as a canonical time-series schema without defining per-element grain.

### Quick Selection Matrix

| Primary Requirement | Wide | Narrow | Document/Raw |
|---|---|---|---|
| Read 5 fixed metrics together at the same timestamp | Favorable | Requires pivot or aggregation | Convenient payload read if packet is synchronous |
| Each device has a varying set of metrics | Many sparse columns | Favorable | Flexible |
| Query history of one metric for one device | Works with time index | Very natural with device–metric–time key | Requires path/index/extraction |
| Per-metric FKs and unit policies | Columns have dedicated types/constraints | Metric definition table + FK | Explicit validator/pipeline |
| Store raw payload intact for reconciliation | Insufficient alone | Insufficient alone | Very suitable |
| Counter math and complex rollups | Possible | Easy to standardize by metric type | Usually requires unpacking/parsing |

**A practical common choice:** short-term raw documents for audit, narrow canonical observations for historical analysis, plus latest-state and rollup tables for fast reads. You do not have to build all four layers for a small system; always start from workload and operational cost.

## 7. PostgreSQL 16 Example: Constrained Raw Metric Schema

The following example assumes **one valid sample per** (`tenant_id`, `device_id`, `metric_code`, `observed_at`). The system may ingest negative temperatures; counter metrics require additional pipeline validation. All partition boundaries use explicit UTC.

```sql
CREATE TABLE device (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT GENERATED ALWAYS AS IDENTITY,
    device_code VARCHAR(80) NOT NULL,
    device_name TEXT NOT NULL,
    CONSTRAINT pk_device PRIMARY KEY (tenant_id, device_id),
    CONSTRAINT uq_device_code UNIQUE (tenant_id, device_code),
    CONSTRAINT ck_device_code_nonblank
        CHECK (char_length(btrim(device_code)) > 0)
);

CREATE TABLE metric_definition (
    tenant_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    metric_name TEXT NOT NULL,
    measure_kind VARCHAR(12) NOT NULL,
    canonical_unit VARCHAR(30) NOT NULL,
    expected_period_seconds INTEGER,
    CONSTRAINT pk_metric_definition
        PRIMARY KEY (tenant_id, metric_code),
    CONSTRAINT ck_metric_kind
        CHECK (measure_kind IN ('GAUGE', 'COUNTER', 'DELTA')),
    CONSTRAINT ck_metric_period
        CHECK (expected_period_seconds IS NULL
               OR expected_period_seconds > 0)
);

CREATE TABLE sensor_reading (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_value NUMERIC(20, 6) NOT NULL,
    quality_code VARCHAR(12) NOT NULL DEFAULT 'GOOD',
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    source_system VARCHAR(40) NOT NULL,
    source_message_id VARCHAR(120) NOT NULL,

    CONSTRAINT pk_sensor_reading
        PRIMARY KEY (tenant_id, device_id, metric_code, observed_at),
    CONSTRAINT fk_reading_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT fk_reading_metric
        FOREIGN KEY (tenant_id, metric_code)
        REFERENCES metric_definition (tenant_id, metric_code),
    CONSTRAINT ck_reading_quality
        CHECK (quality_code IN ('GOOD', 'SUSPECT', 'INVALID')),
    -- Illustrative technical range, not the physical limit for every metric.
    -- Also blocks NaN / Infinity in PostgreSQL via finite bounds.
    CONSTRAINT ck_reading_finite_bounded
        CHECK (metric_value BETWEEN -1000000000 AND 1000000000)
) PARTITION BY RANGE (observed_at);

CREATE TABLE sensor_reading_2027_01
    PARTITION OF sensor_reading
    FOR VALUES FROM ('2027-01-01 00:00:00+00')
               TO ('2027-02-01 00:00:00+00');

CREATE TABLE sensor_reading_2027_02
    PARTITION OF sensor_reading
    FOR VALUES FROM ('2027-02-01 00:00:00+00')
               TO ('2027-03-01 00:00:00+00');
```

**DDL Walkthrough:**

1. `PRIMARY KEY(tenant_id, device_id, metric_code, observed_at)` enforces the grain **under the one-point-per-timestamp assumption**. Because PostgreSQL 16 partitions by `observed_at`, any unique key on a partitioned table must include the partition key; this schema satisfies that rule.
2. The PK creates a B-tree over the listed columns. With equality on `tenant_id`, `device_id`, and `metric_code`, PostgreSQL can perform a **backward index scan** on `observed_at` to find the latest point. **Do not immediately create a redundant DESC index on the full PK prefix** before measuring the workload.
3. FKs to `device` and `metric_definition` ensure valid device and metric codes within the right tenant. However, FKs **do not verify** that gauge/counter metrics are aggregated properly, that units were converted accurately, or that source timestamps are trustworthy.
4. `metric_value NUMERIC(20,6)` fits fixed-precision decimal examples, **not every high-throughput sensor**. Where maximum throughput is critical, `DOUBLE PRECISION` may be used, provided NaN/Infinity, rounding error, and aggregation rules are controlled. Very large counters may need different types or bounds.
5. `quality_code` must be factored into aggregations. Defaulting to `GOOD` is only convenient for already-validated sources; never assign `GOOD` automatically to unvalidated payloads.
6. `source_message_id` records provenance and is **not declared UNIQUE** here because one packet can carry multiple metrics. If message-level deduplication is needed, build a separate delivery ledger keyed by source namespace.
7. There is no `DEFAULT PARTITION` in this example. Measurements outside created monthly partitions will be rejected; you need a job to pre-create partitions and handle late arrivals.

### Why Not Enforce One Global Temperature Range on Every Row?

A bound like `temperature_c BETWEEN -50 AND 150` may make sense for one sensor, but is meaningless for `rpm` or `energy_total_wh`. You can store bounds in `metric_definition` and validate in ingestion or via properly locked triggers, or split tables by metric type to apply tailored `CHECK` constraints. **A row-level `CHECK` constraint cannot safely reference the metric-definition table** to validate business domains.

## 8. Sample Loading, Unit Normalization, and Idempotency

On a clean test schema:

```sql
INSERT INTO device (tenant_id, device_code, device_name)
VALUES (42, 'D-100', 'Furnace sensor #1')
RETURNING tenant_id, device_id;

INSERT INTO metric_definition (
    tenant_id, metric_code, metric_name, measure_kind,
    canonical_unit, expected_period_seconds
)
VALUES
    (42, 'temperature_c', 'Temperature', 'GAUGE', 'degC', 10),
    (42, 'humidity_pct', 'Humidity', 'GAUGE', 'percent', 10),
    (42, 'energy_total_wh', 'Cumulative energy', 'COUNTER', 'Wh', 60);
```

Assume the returned ID for the device is `device_id = 1`. Run the following statements only after verifying that ID:

```sql
INSERT INTO sensor_reading (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, quality_code, source_system, source_message_id
)
VALUES
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:10+00', 31.20, 'GOOD', 'GATEWAY-A', 'msg-1001'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:20+00', 31.40, 'GOOD', 'GATEWAY-A', 'msg-1002'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:30+00', 85.10, 'GOOD', 'GATEWAY-A', 'msg-1003'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:40+00', 31.30, 'GOOD', 'GATEWAY-A', 'msg-1004'),
    (42, 1, 'energy_total_wh',
     '2027-01-15 08:00:10+00', 15000, 'GOOD', 'GATEWAY-A', 'msg-1001'),
    (42, 1, 'energy_total_wh',
     '2027-01-15 08:01:10+00', 15025, 'GOOD', 'GATEWAY-A', 'msg-1005');
```

Two rows sharing `source_message_id = 'msg-1001'` are valid because one packet carries both temperature and meter readings. The 85.10 °C reading lasted briefly, yet it must be **preserved in `MAX`**—never smoothed away just to make a dashboard look tidy.

### Retries and Conflicting Records

If the same sample is resent:

```sql
-- A retry with the same grain will hit the PK and be ignored.
-- Use only if ingestion has already verified the payload is identical to the existing row.
INSERT INTO sensor_reading (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, source_system, source_message_id
)
VALUES (
    42, 1, 'temperature_c',
    '2027-01-15 08:00:10+00', 31.20, 'GATEWAY-A', 'msg-1001'
)
ON CONFLICT (tenant_id, device_id, metric_code, observed_at)
DO NOTHING;
```

**Critical condition:** `ON CONFLICT DO NOTHING` also silently ignores the case where **the sample key matches, but the value changed** from 31.20 to 37.20. Never blindly treat every conflict as a valid retry. The pipeline must compare incoming data against the existing row, check source/revision, and classify it as an **identical retry**, a **correction**, or an **anomalous duplicate**. For timestamp corrections or multiple samples at the same timestamp, design a different grain/source ID before using this statement.

### Message Ledger Table

One approach for an ingestion path carrying multiple metrics per packet:

```sql
CREATE TABLE ingestion_message_ledger (
    tenant_id BIGINT NOT NULL,
    source_system VARCHAR(40) NOT NULL,
    source_message_id VARCHAR(120) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_ingestion_message_ledger
        PRIMARY KEY (tenant_id, source_system, source_message_id)
);
```

The ledger must be written **in the same transaction** as all samples from a message, or managed via an explicit state machine in distributed ingestion. On retry, if the ID already exists, compare the hash/payload and decide whether to return ACK or route to an error path; **matching hashes do not replace collision/untrusted-source protections when strict auditability is required**. The ledger also has its own storage cost and retention lifecycle; purging the ledger too early can allow an old message to be replayed after raw data has been dropped.

## 9. Query A: Latest Value with Freshness Check

Querying the “current temperature” actually returns the **latest recorded value**, not proof of the true temperature **at the moment of reading**. You must return both the timestamp and quality status.

```sql
SELECT
    device_id,
    metric_code,
    observed_at,
    metric_value,
    quality_code,
    received_at
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at <= '2027-01-15 08:01:00+00'::timestamptz
ORDER BY observed_at DESC
LIMIT 1;
```

With the sample data, this returns 31.30 °C at 08:00:40 (after the 85.10 spike). The upper-bound time predicate avoids picking up data **after the assumed query time**, especially in historical analysis; a real-time UI should use a normalized current server timestamp.

**Staleness check:** if the requested instant is 08:01:00 and the metric policy specifies that the latest sample must be no older than 15 seconds, the value from 08:00:40 must be flagged **STALE**. Never display it as “current temperature 31.30 °C” while hiding its timestamp.

Example computing age relative to a query timestamp:

```sql
WITH latest AS (
    SELECT observed_at, metric_value, quality_code
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND observed_at <= '2027-01-15 08:01:00+00'::timestamptz
    ORDER BY observed_at DESC
    LIMIT 1
)
SELECT
    observed_at,
    metric_value,
    EXTRACT(EPOCH FROM (
        '2027-01-15 08:01:00+00'::timestamptz - observed_at
    )) AS age_seconds,
    CASE
        WHEN quality_code <> 'GOOD' THEN 'NOT_TRUSTED'
        WHEN observed_at <
             '2027-01-15 08:01:00+00'::timestamptz - INTERVAL '15 seconds'
             THEN 'STALE'
        ELSE 'FRESH'
    END AS freshness_state
FROM latest;
```

If no row exists, the result is empty: this is **NO_DATA**, not 0 °C. If you need to distinguish **offline**, **metric not configured**, and **no samples received yet**, combine connection state or a device capability catalog.

## 10. Multi-Device Dashboards: Dedicated Latest-State Table

If a dashboard continuously fetches the latest point for tens of thousands of device–metric pairs, scanning or sorting across many raw partitions every few seconds can be expensive. A **latest-state table** can serve as an appropriate read model:

```sql
CREATE TABLE device_metric_latest (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_value NUMERIC(20,6) NOT NULL,
    quality_code VARCHAR(12) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_device_metric_latest
        PRIMARY KEY (tenant_id, device_id, metric_code),
    CONSTRAINT fk_latest_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT fk_latest_metric
        FOREIGN KEY (tenant_id, metric_code)
        REFERENCES metric_definition (tenant_id, metric_code)
);

-- After a sample has been accepted into the raw table:
INSERT INTO device_metric_latest (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, quality_code, received_at
)
VALUES (
    42, 1, 'temperature_c',
    '2027-01-15 08:00:40+00', 31.30, 'GOOD',
    '2027-01-15 08:00:45+00'
)
ON CONFLICT (tenant_id, device_id, metric_code)
DO UPDATE SET
    observed_at = EXCLUDED.observed_at,
    metric_value = EXCLUDED.metric_value,
    quality_code = EXCLUDED.quality_code,
    received_at = EXCLUDED.received_at
WHERE EXCLUDED.observed_at > device_metric_latest.observed_at;
```

**Ordering rule:** the clause `WHERE EXCLUDED.observed_at > ...` prevents a **late-arriving sample with an older event time** from overwriting a newer value. It does not by itself resolve two samples with the same timestamp and different payloads: that case must be classified as a correction/revision and handled through an explicit protocol.

In multi-source write architectures, updating raw and latest should be **transactionally consistent**, or backed by an event/outbox and reconciliation mechanism to repair the read model if the pipeline fails after committing raw. `device_metric_latest` is **derived data**, not a new source of truth replacing raw.

A dashboard read query:

```sql
SELECT
    d.device_code, l.metric_code,
    l.metric_value, l.observed_at, l.quality_code
FROM device_metric_latest AS l
JOIN device AS d
  ON d.tenant_id = l.tenant_id
 AND d.device_id = l.device_id
WHERE l.tenant_id = 42
  AND l.metric_code = 'temperature_c';
```

If the workload frequently queries all devices **for a single metric**, a PK ordered tenant–device–metric may be suboptimal. A secondary index `(tenant_id, metric_code, device_id)` is a benchmark candidate—do not blindly index every column by default.

## 11. Query B: Detailed History and 5-Minute Buckets

A 24-hour chart rarely needs to transmit 8,640 points per device when the display only has a few hundred pixel columns. However, you must pick the right **aggregation**:

```sql
-- Actual measurements for a device/metric within a range.
SELECT observed_at, metric_value, quality_code
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
ORDER BY observed_at;
```

In PostgreSQL 16, `date_bin` aligns timestamps into fixed-step buckets (not calendar months):

```sql
WITH bucketed AS (
    SELECT
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            '2000-01-01 00:00:00+00'::timestamptz
        ) AS bucket_start,
        metric_value
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
)
SELECT
    bucket_start,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS sample_mean_c,
    MIN(metric_value) AS min_c,
    MAX(metric_value) AS max_c
FROM bucketed
GROUP BY bucket_start
ORDER BY bucket_start;
```

**Metric semantics:** `AVG` here is the **sample mean** within the bucket. It is appropriate if every sample carries equal weight. With irregular sampling (for example, 10 samples in 1 minute followed by a 4-minute signal outage), it **does not automatically represent** the time-weighted mean temperature.

`MIN`/`MAX` preserves spikes such as 85.10 °C in our sample, even when the bucket average looks completely normal. If a dashboard only plots `AVG`, it must have an independent threshold-breach path or display the `MIN/MAX` band.

### Empty Buckets Must Still Be Represented

`GROUP BY` does not emit rows for completely empty buckets. On a chart, an interval with no data should appear as **missing/gap**, not drop down to 0 °C:

```sql
WITH bins AS (
    SELECT generate_series(
        '2027-01-15 08:00:00+00'::timestamptz,
        '2027-01-15 08:55:00+00'::timestamptz,
        INTERVAL '5 minutes'
    ) AS bucket_start
),
aggregated AS (
    SELECT
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            '2000-01-01 00:00:00+00'::timestamptz
        ) AS bucket_start,
        COUNT(*) AS n,
        AVG(metric_value) AS avg_c,
        MAX(metric_value) AS max_c
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
    GROUP BY 1
)
SELECT
    b.bucket_start,
    COALESCE(a.n, 0) AS sample_count,
    a.avg_c,
    a.max_c
FROM bins AS b
LEFT JOIN aggregated AS a USING (bucket_start)
ORDER BY b.bucket_start;
```

`sample_count = 0` and `avg_c IS NULL` indicate a bucket with **no good samples**, not a temperature of zero. If you want interpolation or *last observation carried forward*, you must define an explicit **maximum staleness/gap limit**, mark interpolated values, and avoid carrying values across disconnect periods.

## 12. Sample Mean Differs from Time-Weighted Mean

Suppose a device records:

| Timestamp | Temperature |
|---|---:|
| 08:00 | 20 °C |
| 08:01 | 20 °C |
| 08:02 | 20 °C |
| 08:59 | 80 °C |

The **sample mean** is:

\[
\frac{20+20+20+80}{4}=35\,^\circ\mathrm C
\]

If a measurement is assumed to hold until the next measurement (*step/hold interpolation*), a time-weighted mean over 08:00–09:00 can differ sharply from 35 °C because the three 20 °C samples are clustered closely together while the 08:02–08:59 span is very long.

However, from four samples alone you cannot conclude that the temperature stayed at 20 °C for all 57 minutes. The sensor might have lost connectivity while the actual process changed. Therefore, every KPI must have an explicit contract:

- **Sample mean:** each sample is an equally weighted observation.
- **Time-weighted mean:** applies an explicit between-point rule (step-hold, linear interpolation, etc.), with gap limits and *coverage* tracking.
- **Observed min/max:** extrema among actually observed samples; does not claim to have captured every extremum between samples.
- **Percentile:** specifies whether percentiles are sample-based or duration-based, and how missing/anomalous data is handled.

With step-hold, you can compute:

\[
\overline{T}_{time} =
\frac{\sum_i T_i\Delta t_i}{\sum_i\Delta t_i}
\]

where `Δt` is accumulated only across **intervals with acceptable coverage**. Intervals between samples exceeding the gap threshold may be excluded from the denominator or reported separately, rather than silently pretending full measurement coverage.

**Do not average bucket averages** when buckets contain different numbers of samples. When aggregating from rollups, use `SUM(sample_sum)/SUM(sample_count)` for the sample mean. For a time-weighted mean, you must store **weighted_sum and covered_duration** under a defined rule—it cannot be reconstructed from sample mean and sample count once interval durations are lost.

## 13. Cumulative Counters: Reading Deltas, Detecting Resets and Gaps

The `energy_total_wh` metric in our example is a **cumulative meter**. If the reading at 08:00 is 15,000 Wh and at 08:01 is 15,025 Wh, valid consumption between the two timestamps is **25 Wh**, not 30,025 Wh.

Query pattern:

```sql
WITH ordered AS (
    SELECT
        observed_at,
        metric_value AS current_counter,
        LAG(observed_at) OVER (ORDER BY observed_at) AS previous_at,
        LAG(metric_value) OVER (ORDER BY observed_at) AS previous_counter
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'energy_total_wh'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
)
SELECT
    observed_at,
    previous_at,
    previous_counter,
    current_counter,
    CASE
        WHEN previous_counter IS NULL THEN NULL
        WHEN observed_at - previous_at > INTERVAL '10 minutes' THEN NULL
        WHEN current_counter >= previous_counter
             THEN current_counter - previous_counter
        ELSE NULL
    END AS delta_wh
FROM ordered
ORDER BY observed_at;
```

The first value has no prior sample within the filter range, so `delta_wh = NULL`. If you need consumption **starting right at the top-of-hour boundary**, look up the **last valid sample immediately before the hour** as a baseline rather than only filtering inside the hour and calling `LAG`. Without a sufficiently recent baseline sample, the result must flag incomplete coverage.

If a counter drops from 15,025 to 2:

- It may have **reset** due to a reboot.
- It may have **rolled over** after reaching the device's register limit.
- The device may have been replaced, or the meter sent faulty/out-of-order data.

Do not use `GREATEST(current - previous, 0)` and treat negative differences as “zero consumption,” because that hides resets and loses real consumption during that interval. Define a counter-reset policy, maximum bounds, device rollover width, and quality flags; some systems can infer the post-reset delta if counter semantics are **exact**, while others must mark the segment indeterminate.

**Rate** is computed from `delta / duration` with explicit units. For instance, Wh/s differs from W in physical definition, though they convert cleanly; never compute `counter_value / observed_at` or `AVG(counter_value)` to represent power.

## 14. Operational States and Events Need a Different Model from Gauges

States like `RUNNING`/`STOPPED` are meaningless under `AVG(1,2,3)` unless the business deliberately defines a numeric encoding, and even then an average of codes is not automatically uptime percentage.

Two options:

1. **State events:** one row per state transition, recording `effective_at`, new state, reason, and event ID; computing duration requires pairing consecutive transitions and clamping to the reporting window.
2. **State samples:** a series of state readings at a fixed cadence; sample-based uptime ratio is only an approximation when samples are lost or cadence changes.

Event-oriented DDL example:

```sql
CREATE TABLE device_state_event (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    source_event_id VARCHAR(120) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    state_code VARCHAR(20) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_state_event
        PRIMARY KEY (tenant_id, device_id, source_event_id),
    CONSTRAINT fk_state_event_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT ck_device_state
        CHECK (state_code IN ('RUNNING', 'STOPPED', 'OFFLINE'))
);
```

`source_event_id` identifies the state-transition event; if the source does not provide a durable ID, resolve the grain before adopting this DDL. An event with an older `effective_at` arriving late can alter historical uptime calculations; preserving closed reports requires versioning or an explicit correction policy.

## 15. Data Quality: Missing, Suspect, Invalid, and Alert Thresholds

A missing measurement does not mean zero. A sample exceeding an alert threshold is not necessarily a sensor error—especially in incident monitoring.

| Condition | Example | How to Store / Read |
|---|---|---|
| **GOOD** | 32.1 °C passed source checks | Included in charts/aggregates per contract |
| **SUSPECT** | 250 °C exceeds expected physical range but unconfirmed | Store for investigation, exclude from default KPIs or display separately |
| **INVALID** | Payload `"temperature": "unknown"`, checksum failure | Quarantine raw payload; never insert into numeric table as 0 |
| **MISSING** | No samples from 08:01 to 08:07 | Represent **by absence** or coverage/gap metadata, never fabricate 0 °C rows |
| **LATE** | Measured at 08:00, received at 08:09 | Preserve event time, track ingestion delay |
| **CORRECTED** | Revised reading sent after recalibration | Requires ID/revision and policy for preserving originals/restating |

Do not add `CHECK(temp_c < 85)` if the goal is **overheat detection**. Such a constraint would reject the very 85.10 °C sample the system needs to raise an alert. **Physical validity bounds** are distinct from **operational alert thresholds**; model the two separately.

### Threshold Breach Detection Cannot Rely Only on Averages

```sql
SELECT
    device_id,
    MAX(metric_value) AS max_temp_c,
    COUNT(*) AS high_samples
FROM sensor_reading
WHERE tenant_id = 42
  AND metric_code = 'temperature_c'
  AND quality_code = 'GOOD'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 08:10:00+00'::timestamptz
  AND metric_value > 85
GROUP BY device_id;
```

With the sample data, device 1 shows up with a peak of 85.10 °C. However, a **single sample** above a threshold differs from “temperature continuously above 85 °C for at least 2 minutes”: sustained conditions require coverage, duration, and between-sample semantics, which cannot be inferred from a single `MAX`.

**Real-time alerting** must also account for ingestion latency, late events, idempotency on retries, and alert retraction/update policies. A SQL max query over raw data does not by itself constitute a reliable alerting system.

## 16. Time Partitioning, B-Tree, and BRIN: Optimizing by Read Predicates

### 16.1. Partition Pruning by Event Time

With `sensor_reading` partitioned by `observed_at`, a query containing:

```sql
WHERE observed_at >= '2027-01-15 00:00:00+00'::timestamptz
  AND observed_at <  '2027-01-16 00:00:00+00'::timestamptz
```

can prune all partitions except January. By contrast, a query filtering only on `device_id = 1` **without a time predicate** may have to probe many partitions, even though each partition has an index. That is why `device_metric_latest` is a strong candidate for high-frequency latest-value lookups.

### 16.2. Choosing B-Tree Column Order

The current PK indexes:

```text
(tenant_id, device_id, metric_code, observed_at)
```

This fits “one device, one metric, one time range” and supports backward scans for latest value within tenant/device/metric. However, “same metric across all devices in the last 10 minutes” may benefit from a different index:

```sql
-- Candidate: ONLY CREATE if multi-device queries for a single metric are important enough.
CREATE INDEX idx_reading_tenant_metric_time_device
    ON sensor_reading (tenant_id, metric_code, observed_at DESC, device_id);
```

This index can support time predicates combined with `metric_code` filters. Still, adding another B-tree across billions of rows is costly: every insert must update an extra index in the target partition, increasing disk, cache pressure, WAL volume, and index build time. Do not create it just because “someone checks factory-wide temperature” once a quarter.

### 16.3. BRIN on Time

If raw data is mostly appended in event-time order, PostgreSQL can benefit from **BRIN**:

```sql
-- Compact candidate for wide time-range scans.
CREATE INDEX idx_reading_observed_brin
    ON sensor_reading USING BRIN (observed_at);
```

BRIN summarizes page ranges; it suits data correlated with physical storage order and range-scan queries, and is typically much smaller than a full B-tree. However, BRIN **does not replace a B-tree** for single-device latest lookups or `ORDER BY ... LIMIT`; rows fetched from candidate pages still require rechecking.

**Late arrivals** break strict correlation between physical write order and `observed_at`, reducing BRIN selectivity if data that is months old is interleaved into a partition. Measure physical correlation, pages read, and actual query plans.

### 16.4. Partition Granularity

A 90-day raw retention policy might suggest daily or monthly partitions, but the choice depends on partition size, creation/drop timing, object count, indexes, backups, and queries. At millions of samples per day, monthly partitions may become huge; at low write rates, daily partitions create too many objects. There is no universal row-count threshold across all DBMSs.

In PostgreSQL 16, `PRIMARY KEY`/`UNIQUE` constraints on a partitioned table must include the partition key by engine design. If you need uniqueness on `source_message_id` **across all time**, a per-partition unique index is insufficient; use a separate ledger as in Section 8 or another mechanism. Never add a timestamp to a unique message ID just to make DDL compile, as duplicate messages arriving at different times would slip through.

## 17. 5-Minute Rollups: Serving Long-Term Historical Reads

When monthly screens only need 5-minute or hourly points, you can use a derived rollup table:

```sql
CREATE TABLE metric_5m_rollup (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL,
    sample_sum NUMERIC(30,6) NOT NULL,
    sample_min NUMERIC(20,6) NOT NULL,
    sample_max NUMERIC(20,6) NOT NULL,
    first_sample_at TIMESTAMPTZ NOT NULL,
    last_sample_at TIMESTAMPTZ NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    rollup_revision BIGINT NOT NULL DEFAULT 1,
    CONSTRAINT pk_metric_5m_rollup
        PRIMARY KEY (tenant_id, device_id, metric_code, bucket_start),
    CONSTRAINT ck_rollup_sample_count CHECK (sample_count > 0),
    CONSTRAINT ck_rollup_min_max CHECK (sample_min <= sample_max),
    CONSTRAINT ck_rollup_sample_order
        CHECK (
            first_sample_at <= last_sample_at
            AND first_sample_at >= bucket_start
            AND last_sample_at < bucket_start + INTERVAL '5 minutes'
        ),
    CONSTRAINT ck_rollup_revision CHECK (rollup_revision > 0)
);
```

For gauges, `sample_sum`, `sample_count`, `sample_min`, and `sample_max` suffice for **sample mean**, min/max, and merging non-overlapping buckets. They are **not sufficient** to reconstruct exact percentiles, per-sample trajectories, or time-weighted means without additional information.

### 17.1. Recomputing a Bucket from Raw

```sql
-- Recompute bucket 08:00-08:05 state from retained raw data.
INSERT INTO metric_5m_rollup (
    tenant_id, device_id, metric_code, bucket_start,
    sample_count, sample_sum, sample_min, sample_max,
    first_sample_at, last_sample_at
)
SELECT
    tenant_id, device_id, metric_code,
    date_bin(
        INTERVAL '5 minutes',
        observed_at,
        '2000-01-01 00:00:00+00'::timestamptz
    ) AS bucket_start,
    COUNT(*) AS sample_count,
    SUM(metric_value) AS sample_sum,
    MIN(metric_value) AS sample_min,
    MAX(metric_value) AS sample_max,
    MIN(observed_at) AS first_sample_at,
    MAX(observed_at) AS last_sample_at
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND quality_code = 'GOOD'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 08:05:00+00'::timestamptz
GROUP BY tenant_id, device_id, metric_code, bucket_start
ON CONFLICT (tenant_id, device_id, metric_code, bucket_start)
DO UPDATE SET
    sample_count = EXCLUDED.sample_count,
    sample_sum = EXCLUDED.sample_sum,
    sample_min = EXCLUDED.sample_min,
    sample_max = EXCLUDED.sample_max,
    first_sample_at = EXCLUDED.first_sample_at,
    last_sample_at = EXCLUDED.last_sample_at,
    rollup_revision = metric_5m_rollup.rollup_revision + 1,
    refreshed_at = clock_timestamp();
```

**Why recompute instead of blindly incrementing:** if a raw sample is resent or corrected, simply incrementing `sample_count += 1` and `sample_sum += value` double-counts or leaves stale values behind. Recomputing a bucket from the source of truth is **content-idempotent**, provided raw data is deduplicated and the read snapshot is consistent.

The `UPSERT` above illustrates the mechanism, **not full production orchestration**. If two workers concurrently recompute a rollup from different snapshots, an older update could still overwrite a newer state. You need bucket-level locking/coordination, watermarks, batch/version gating, or monotonic update rules, plus reconciliation.

### 17.2. Reading Rollups Correctly When Aggregating to Hours or Days

```sql
SELECT
    device_id,
    metric_code,
    SUM(sample_sum) / NULLIF(SUM(sample_count), 0) AS sample_mean,
    MIN(sample_min) AS observed_min,
    MAX(sample_max) AS observed_max,
    SUM(sample_count) AS total_samples
FROM metric_5m_rollup
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND bucket_start >= '2027-01-15 08:00:00+00'::timestamptz
  AND bucket_start <  '2027-01-15 09:00:00+00'::timestamptz
GROUP BY device_id, metric_code;
```

Do not use `AVG(sample_sum / sample_count)` when buckets have different sample counts. Also never reuse this temperature rollup for `energy_total_wh` and compute energy via `SUM(sample_sum)`: counters require dedicated delta, reset, and gap handling **before aggregation**.

**Empty buckets** have no row in this rollup table because `sample_count > 0`. For charts, join against a bucket calendar / `generate_series` to show missing intervals instead of filling with 0.

## 18. When Data Arrives Late: Closing Windows and Watermarks

Suppose the pipeline computed the 08:00–08:05 rollup at 08:06. At 08:08, a gateway delivers a measurement taken at 08:03. That raw row belongs to the **08:00 bucket**, not 08:05–08:10. If the rollup is not recomputed, both the chart and `MAX` will be wrong.

A late-data policy might include:

- **Allowed lateness:** accept readings arriving up to 2 hours late and automatically update raw and rollups.
- **Watermark:** a business boundary beyond which the pipeline provisionally considers earlier intervals complete enough to publish, based on observed time, lag, and source health.
- **Revision:** recomputed buckets receive a revision/`refreshed_at` so downstream consumers can refresh or explain changed numbers.
- **Very late data:** events outside the window are routed to exception handling—neither silently dropped nor stealthily mutating finalized numbers.

**A watermark is not a guarantee that zero late data remains.** It is a policy trading off completeness against latency. If SLAs require immutable published results after close, late-arriving data must generate versioned corrections rather than quietly altering published figures.

### Idempotency Across All Three Layers

| Layer | Invariant | Verification Method |
|---|---|---|
| Message/ingestion | One source message is never processed into two sets of samples | Namespaced ledger, payload comparison, and transactions |
| Raw reading | One sample per grain never produces two rows | Unique key/PK; handle revisions differently from identical retries |
| Rollup | One bucket never adds the same raw sample twice | Recompute or use delta ledger; test replays and late data |

If raw data has already been purged when a very late event arrives, **you cannot simply recompute the bucket accurately from raw**. Keep source/archived data long enough, emit corrections, or exclude with an audit trail. Retention is part of correctness, not just storage optimization.

## 19. Device, Location, and Calibration Changes Over Time

A device may move from production line A to line B on July 1. To report “average temperature by production line at measurement time,” never join raw readings to `device.current_line` and retroactively assign all March samples to line B.

A temporal assignment table can look like:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE device_assignment_period (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    valid_during TSTZRANGE NOT NULL,
    production_line_code VARCHAR(60) NOT NULL,
    CONSTRAINT fk_assignment_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT ck_assignment_window
        CHECK (
            NOT isempty(valid_during)
            AND NOT lower_inf(valid_during)
        ),
    CONSTRAINT ex_device_one_line_at_time
        EXCLUDE USING GIST (
            tenant_id WITH =,
            device_id WITH =,
            valid_during WITH &&
        )
);
```

This example enforces that a device belongs to **at most one production line** at any instant. If the business allows simultaneous assignments to multiple lines, a different design (such as a temporal bridge table) is needed. `EXCLUDE` prevents overlaps, but does not by itself prevent **gaps**.

To resolve the line active at measurement time:

```sql
SELECT
    a.production_line_code,
    r.device_id,
    r.observed_at,
    r.metric_value
FROM sensor_reading AS r
JOIN device_assignment_period AS a
  ON a.tenant_id = r.tenant_id
 AND a.device_id = r.device_id
 AND a.valid_during @> r.observed_at
WHERE r.tenant_id = 42
  AND r.metric_code = 'temperature_c'
  AND r.quality_code = 'GOOD'
  AND r.observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND r.observed_at <  '2027-01-15 09:00:00+00'::timestamptz;
```

If there are **0 matching assignments**, an inner join drops samples; if there are **2 assignments** due to dirty legacy data, the join duplicates samples. Reconcile sample counts before and after joining, and block or explicitly flag unmapped samples.

### Calibration and Normalized Measurements

If calibration coefficients are updated after data has been ingested, decide between:

- **As measured/as processed:** preserve the canonical value published at ingestion, along with `calibration_version_id`, formula, and source.
- **Restated:** recompute history under retroactive calibration and publish versioned outputs, avoiding silent overwrites when prior reports must remain reproducible.
- **Raw sensor value:** retain original readings and units to audit transformations during disputes.

An FK to `calibration_version_id` only verifies that the version exists—not that it was active at `observed_at`. This is the same temporal mapping problem as device assignment.

## 20. Retention, Downsampling, and Storage Cost

Assume 20,000 devices, each measuring **one metric** every 10 seconds:

\[
20\,000\times 6\ \mathrm{samples/min}
\times 60\times24
=172\,800\,000\ \mathrm{samples/day}
\]

If each device measures three metrics at the same cadence, narrow row counts grow roughly threefold, **provided** all metrics arrive without gaps. This is a row-count sizing calculation, not an exact byte estimate: index size, heap, TOAST, metadata, WAL, replication, and compression depend on the DBMS.

An illustrative retention policy:

| Tier | Resolution | Retention | Read Purpose |
|---|---|---|---|
| Normalized raw | Every 10-second sample | 90 days | Incident investigation, spike/gap analysis, rollup recomputation |
| 5-minute rollup | Count/sum/min/max | 2 years | Daily–monthly charts, historical temperature tracking |
| Daily rollup | Semantically defined KPIs | 5 years if contract allows | Multi-year trend reporting |
| Ingestion ledger / raw payload | Per source and audit rules | Depends on dedup/reconciliation needs | Traceability and replay |

**No single retention period fits every system.** If you must detect 2-second spikes, keeping only a 5-minute rollup with `MAX` tells you **a spike occurred in that bucket**, but cannot reconstruct exact waveform shape or spike timestamp unless `argmax_at` or raw data is kept.

If you need year-long p99 percentiles, sum/count/min/max cannot derive them accurately; you must retain raw longer, use bounded-error histogram/sketch structures, or store technology-appropriate percentile rollups. Averaging hourly p95 values with `AVG` is statistically invalid.

### Retention Is an Operational Workflow

In PostgreSQL, you can run `DETACH PARTITION`/`DROP` after archiving, checking dependencies, and obtaining approval. However, detaching or dropping partitions affects FKs, CDC, historical reports, and replay capability. Never call dropping raw “safe” while rollups are still missing late data or remain unreconciled.

If rollups are rebuilt from raw, calculate the **last modifiable date** from both retention and allowed lateness; never purge raw immediately after a provisional rollup is written.

## 21. Measure Performance by Read Path Rather Than Index Count

Before finalizing a structure, test multiple scenarios:

```sql
-- A: latest value for a device/metric.
EXPLAIN (ANALYZE, BUFFERS)
SELECT observed_at, metric_value
FROM sensor_reading
WHERE tenant_id = 42 AND device_id = 1
  AND metric_code = 'temperature_c'
ORDER BY observed_at DESC
LIMIT 1;

-- B: history within a time range.
EXPLAIN (ANALYZE, BUFFERS)
SELECT observed_at, metric_value
FROM sensor_reading
WHERE tenant_id = 42 AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at >= '2027-01-15 00:00:00+00'::timestamptz
  AND observed_at <  '2027-01-16 00:00:00+00'::timestamptz
ORDER BY observed_at;

-- C: inspect existing partitions.
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('public.sensor_reading'::regclass)
ORDER BY level, relid;
```

`EXPLAIN (ANALYZE, BUFFERS)` executes the `SELECT` and can consume substantial resources on large tables; benchmark in a controlled environment or maintenance window. Observe:

- **Partition pruning:** does a query for January 15 actually skip other monthly partitions?
- **Index scan vs. seq scan:** do device/metric/time filters select a cheaper access path?
- **Estimated vs. actual rows**, `shared hit/read` buffers, and p95/p99 latency under concurrent multi-device reads.
- **Fanout from metadata joins:** are samples multiplied or dropped when resolving historical production lines?
- **Write throughput:** samples/s, insert latency, WAL/redo, page/cache pressure, index size, vacuum/compaction, and partition creation overhead.
- **Rollup freshness:** lag from event/ingestion to chart, reprocessed bucket counts, and unreconciled errors.

A fast query against two empty partitions proves nothing about performance when each partition holds billions of rows. Test datasets must include hot tenants/devices, late arrivals, missing gaps, counter resets, and multiple metric kinds.

## 22. Comparing PostgreSQL, TSDB, Document, Graph, and Analytical Warehouses

| Storage Option | Strengths | What Must Be Verified |
|---|---|---|
| **Relational PostgreSQL + partitioning** | Strong FKs/constraints, rich SQL, application-controlled raw/rollups | Partition/index/retention overhead and heavy write cost; lacks native specialized time-series features out of the box |
| **Time-series database or extension** | May provide chunking, compression, retention, continuous aggregates/downsampling, and time-series functions | Licensing/extension policies, late data handling, indexes, uniqueness, and exact version refresh semantics |
| **Document/event store** | Flexible payload storage, convenient source-message auditing | Sample extraction, per-element idempotency, time/metric indexing, and validation |
| **Columnar warehouse** | Large historical scans, multi-device grouping, columnar compression | Ingestion latency, refresh cost, PK/FK constraints may not be enforced |
| **Graph** | Traversing device–line–part–incident relationships | Does not replace storing/rolling up billions of samples; metadata traversal still needs effective-time bounds |

A TSDB offering `time_bucket`, compression, and continuous aggregates can be more convenient than core PostgreSQL at extreme scale. **Do not assume those functions exist in vanilla PostgreSQL 16**: this lesson uses `date_bin`, which is built into PostgreSQL 16, whereas extensions and other products have their own APIs, limits, and refresh behaviors.

If the primary bottleneck is **querying latest state**, a latest-state read model may cut latency more effectively than migrating to another DBMS. If the workload is **scanning billions of samples across years**, analytical/columnar storage may make more sense than adding more B-trees. Base the choice on workload and consistency goals—not technology buzzwords.

## 23. Common Mistakes

| Misconception | Why It Is Wrong | Corrective Approach |
|---|---|---|
| “Time-series data only needs timestamp and value.” | Missing tenant, device, metric, unit, quality, source, and grain | Define measurement contract, keys, and provenance |
| “Last received equals latest value.” | Late arrivals have a new `received_at` but an old `observed_at` | Distinguish latest by event time from latest ingested |
| “One timestamp is always one unique sample.” | Sources may emit multiple channels/sequences in the same second | Design proper sample IDs or timestamp resolution |
| “Missing samples have value 0.” | Zero is a meaningful reading, not missing data | Preserve `NULL`/gaps and display coverage |
| “A 5-minute `AVG` is the time-weighted mean temperature.” | Irregular sampling and gaps distort weights | Define sample mean vs. time-weighted mean explicitly |
| “Storing only the average is enough for overheat detection.” | Short spikes are smoothed away | Keep raw or `MAX` along with timestamp/quality |
| “`SUM(counter_value)` gives energy consumed.” | Counters are cumulative totals | Compute deltas with reset/rollover/gap detection |
| “Readings above 85 °C must be rejected by `CHECK`.” | Drops the exact evidence of overheating | Separate physical validity bounds from alert thresholds |
| “`ON CONFLICT DO NOTHING` is always right for idempotency.” | Masks conflicts with the same ID but different payloads | Compare payloads/revisions and handle corrections explicitly |
| “One new B-tree solves a 20,000-device dashboard.” | Multi-series latest lookups may still touch many partitions | Benchmark indexes and consider a latest-state table |
| “Rollups only need incremental additions on each message.” | Retries and late corrections double-count samples | Recompute from raw or maintain a delta ledger |
| “SCD2 / line reassignments don't affect measurement facts.” | Joining current metadata misattributes historical data | Use as-of joins and verify no gaps/overlaps |
| “Monthly partitions appear automatically at month rollover.” | Writes fail if the partition is missing | Pre-create partitions and monitor boundaries |
| “Dropped raw data can always be rolled up accurately later.” | Source samples, percentiles, gaps, and revisions are lost | Align retention with late-data policy and archiving |
| “Hourly p95 histograms can be combined using AVG(p95).” | Percentiles are not additive like sums | Store histograms/sketches or raw data as needed |

## 24. Practice Exercise: Designing Factory Temperature and Energy Monitoring

**Scenario:** Three factories, 12,000 devices; half report temperature every 5 seconds and the rest every 30 seconds. 2,000 devices also report a cumulative energy counter in Wh every minute. Gateways can go offline for 30 minutes and backfill later; 0.5% of samples carry future timestamps due to clock drift; 2% of temperature samples are missing during network drops. Devices can move between production lines and are recalibrated quarterly.

Read requirements:

- **R1:** latest temperature status of every device in one factory, 3-second refresh, alert when data is older than 30 seconds.
- **R2:** 5-minute device temperature chart over 30 days, showing missing buckets and overheat spikes.
- **R3:** total Wh energy consumption per 8-hour shift, without miscounting across counter resets.
- **R4:** highest temperature per production line **at measurement time**, reported daily.
- **R5:** incident investigation with full raw samples over 60 days.
- **R6:** keep raw 90 days; 5-minute rollups 2 years; monthly summary metrics 5 years.

### Tasks

1. **Define grain:** specify unique keys for raw temperature and counters, handling same-timestamp collisions and multi-metric packets. Distinguish event ID from source message ID.
2. **Select schema:** compare wide row, narrow row, and raw JSON; propose a formal design with tables, tenant-scoped FKs, metric metadata, quality flags, and units.
3. **Optimize R1:** present the raw latest query and latest-state table design; explain why late arrivals must not overwrite newer points.
4. **Optimize R2:** build 5-minute event-time buckets retaining `COUNT`, `SUM`, `MIN`, `MAX`, expose gaps, and contrast sample mean vs. time-weighted mean.
5. **Optimize R3:** compute `delta_wh` from counters, fetch pre-shift boundary baselines, and handle resets/rollovers and missing intervals.
6. **Optimize R4:** model device → production line history with effective intervals, as-of joins, and test cases preventing row multiplication or loss.
7. **Data quality:** handle future timestamps, out-of-range spikes, JSON nulls, missing values, °F/°C units, and retroactive calibration updates.
8. **Late data:** define watermark and allowed lateness; design an idempotent 5-minute bucket refresh algorithm and post-close handling.
9. **Retention:** choose daily vs. monthly partition granularity, pre-creation schedule, archive/rollup/reconcile/drop sequence, and replay strategy after raw purge.
10. **Benchmark:** simulate skewed device traffic, measure p95 latency for R1/R2/R4, ingest throughput, partitions scanned, index/WAL size, and rollup lag.

### Delivery Checklist

- [ ] Read patterns, time ranges, resolutions, SLAs, and freshness policies are documented.
- [ ] Raw grain unambiguously identifies device, metric, timestamp, and source key; retries create no duplicates.
- [ ] Gauge, counter, delta, and state metrics do not share invalid aggregation operators.
- [ ] Units, validity bounds, quality codes, event time, received time, and timezones are standardized.
- [ ] Fast latest-read path exists and late arrivals cannot overwrite newer state.
- [ ] Missing buckets, coverage, min/max, and late data are represented transparently.
- [ ] Sampling weights, delta math, resets, and interpolation follow explicit business contracts.
- [ ] Device metadata/calibration is versioned with effective periods; historical reports use as-of joins where needed.
- [ ] Partitions, indexes, rollups, and retention match the workload and are tested on representative data.
- [ ] Backfill, replay, correction, watermark, reconciliation, and rollback procedures are designed.

**A sound time-series model preserves not only every measurement, but also how that measurement must be interpreted across time and read patterns.** Temperature needs latest reads, peaks, and coverage; counters need deltas and reset handling; states need durations; and raw, latest, and rollup tables each need an explicit source of truth, grain, and synchronization policy. When these choices are verified against real queries, the system delivers fast dashboards without corrupting operational history.
