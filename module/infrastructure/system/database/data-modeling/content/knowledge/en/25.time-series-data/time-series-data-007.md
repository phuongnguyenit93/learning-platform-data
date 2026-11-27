# Storing Raw Data, Multi-Level Rollups, and Downsampling

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **raw data** (*raw measurements/events*), **time-bucket rollup tables**, and **downsampled series**.
- Define **grain**, identifying keys, event timestamps, ingestion timestamps, and authoritative sources for a measurement before creating tables or indexes.
- Design a multi-tier rollup chain **raw → 5 minutes → 1 hour → 1 day** using mathematically sound merge formulas, even under uneven sample counts.
- Explain why **AVG of AVGs**, **SUM of balances/inventory**, **AVG of percentages**, **SUM of percentiles**, and summing cumulative counter values produce wrong answers.
- Build PostgreSQL schemas and queries for temperature telemetry, idempotent rollups, reconciliation, late-data handling, and boundary protection.
- Choose retention windows, query resolutions, gap representations, and data-reduction criteria while keeping sufficient evidence for supported business decisions.
- Compare time-series storage across relational, document, graph, and analytical models along with trade-offs in read/write cost, precision, and schema evolution.

This lesson belongs to the **Time-Series Data** chapter of **DATABASE_DATA_MODELING**. In this module, translating business requirements into entities, relationships, keys, indexes, and physical schemas begins with asking: **what does each data point mean, at which timestamp, and what does an aggregation preserve or discard?**

## 1. Scenario: A Sensor Producing Millions of Samples

A factory runs numerous temperature sensors sending readings every few seconds. The system must:

1. Display **the last 15 minutes** at high resolution to track fluctuations.
2. Let shift supervisors inspect **the last 24 hours** in 5-minute intervals.
3. Let managers inspect **the last 90 days** hourly, including minimum and maximum temperatures.
4. Let operations analyze multi-year daily or weekly trends.
5. Investigate specific incidents using **raw samples and original measurement timestamps** while still within retention.
6. Accept retransmitted samples after network outages, some arriving minutes or hours late.

One naive approach stores every raw reading forever and scans hundreds of millions of points for every chart—often infeasible at scale. Another keeps only **hourly averages**; storage stays tiny, yet every brief spike and exact reading timestamp disappears.

A sound design typically combines **multiple representation tiers for the same data stream**:

~~~text
Devices / event sources
         |
         v
Raw measurement store (grain: one sample)
         |
         +--------> Recent incident lookup
         |
         v
5-minute rollup: count, sum, min, max, ...
         |
         +--------> Shift charts
         |
         v
1-hour rollup: merged from 5-minute buckets
         |
         +--------> Daily / 90-day dashboards
         |
         v
1-day rollup: by business date
         |
         +--------> Long-term trends

Each tier has its own retention, freshness, and reconciliation rules.
~~~

**Raw** is the source of truth for received and accepted measurements. The 5-minute, hourly, and daily tables are **derived data** rebuildable whenever raw rows remain intact. Once raw expires past retention, individual samples generally cannot be reconstructed from rollups: that is the information intentionally traded away.

## 2. State the Grain Before Choosing Keys and Measures

For time series, three entities usually require separation:

- **Device/sensor**: a measurement source with stable identity, quantity kind, unit, location, or calibration state.
- **Raw sample**: a single reading measured and emitted by a device, with **event time** and an ID or sequence to detect retries.
- **Rollup bucket**: a group of samples matching **sensor × time interval × quality rule**, storing mergeable statistical state.

Example grain declarations:

> **`raw_temperature`:** each row is one temperature reading emitted by one sensor, identified by `(sensor_id, source_sample_id)`; `observed_at` is measurement time.

> **`temperature_5m`:** each row summarizes valid samples of **one sensor** whose `observed_at` falls in **one half-open 5-minute UTC bucket**.

> **`temperature_hourly`:** each row summarizes valid samples of **one sensor** in **one half-open UTC hour**, merged from completed 5-minute buckets.

This prevents four common mistakes:

1. **Timestamps are not automatically unique keys.** A device can emit two distinct measurements at the same timestamp with different IDs.
2. **Arrival time differs from measurement time.** Never bucket late samples by server arrival date when reports ask when events happened.
3. **A bucket is not a sample.** Average values are conditional derivations, never substitutes for raw readings.
4. **An absent row is not automatically 0.** It may mean no sample was taken, the device stopped, transmission failed, or a pipeline job hasn't run yet.

### 2.1. Temporal Concepts Required in the Contract

| Name | Meaning | Example |
| --- | --- | --- |
| **observed_at / event time** | When the measurement occurred per source | 08:01:04 |
| **received_at / ingestion time** | When the system received the record | 08:04:32 |
| **processed_at** | When the pipeline processed or wrote the rollup | 08:05:10 |
| **bucket_start** | Inclusive start boundary of the aggregation interval | 08:00:00 |
| **watermark** | Event-time mark deemed sufficiently complete per lateness policy | 07:55:00, config-dependent |
| **business date** | Calendar date under business timezone and reporting rules | Calendar day at a specific plant |

If a device clock drifts, event time may be untrustworthy. Track clock source, skew tolerance, and anomaly flags. **Never overwrite event time wholesale with `received_at` without documenting that the temporal semantics changed.**

### 2.2. Sensor Metadata Is a Dimension, Not Fields to Copy Endlessly

A sensor carries `sensor_id`, location, quantity type, unit, calibration date, and operational status. Raw tables should carry only attributes needed to preserve sample semantics and serve hot filters; current metadata belongs in **`dim_sensor`** or a device registry.

If a sensor moves from zone A to zone B, historical reports may ask for **location at measurement time** or **current location**. When historical location matters, use effective-dated snapshots/versions rather than retroactively attributing old samples to the current zone.

## 3. Raw, Rollups, and Downsampling Are Not Synonymous

| Type | What One Row Represents | What Is Preserved? | What Is Lost / Risks |
| --- | --- | --- | --- |
| **Raw event/measurement** | One event or measured sample | Exact value, timestamp, and source ID | Storage, index size, and long-range scan cost |
| **5-minute rollup** | One sensor × one 5-minute bucket | `COUNT`/`SUM`/`MIN`/`MAX` and chosen state | Exact second-level positions inside the bucket |
| **1-hour rollup** | One sensor × one hour | Statistics mergeable from finer buckets | Intra-hour ordering of changes |
| **Daily rollup** | One sensor × business date | Daily trends and statistics | Cannot reconstruct multi-second incidents |
| **Downsampled chart point** | Point chosen/aggregated for display span | Detail suited to pixel width or reading target | Discards granularity; risks hiding spikes and volatility |

**Rollups** typically store **statistical state** such as `sample_count`, `value_sum`, `min`, and `max`. **Downsampling** intentionally represents a series at lower resolution. Rollups are one way to downsample, though not the only one: systems may select representative points, retain min/max envelopes, or apply shape-preserving algorithms.

Never treat aggregate tables as “smaller copies of raw”. They are **models with a new grain, new formulas, and intentional information loss**.

## 4. Half-Open Buckets: Placing Each Sample in Exactly One Place

For 5-minute UTC buckets:

~~~text
[08:00:00, 08:05:00)    accepts samples 08:00:00 ... 08:04:59.999...
[08:05:00, 08:10:00)    accepts samples at exact 08:05:00
[08:10:00, 08:15:00)    accepts samples at exact 08:10:00
~~~

The bracket **`[)`** means inclusive of start and **exclusive of end**. A sample at exactly **08:05:00** belongs solely to the 08:05 bucket, never to two buckets at once.

For fixed width `w` and origin `origin`:

$$
b(t) = \mathrm{origin} + \left\lfloor \frac{t-\mathrm{origin}}{w} \right\rfloor w
$$

This maps an absolute timestamp to `bucket_start`; in PostgreSQL, use `date_bin` for fixed intervals. Example:

~~~sql
SELECT date_bin(
    INTERVAL '5 minutes',
    TIMESTAMPTZ '2026-11-22 08:07:23+00',
    TIMESTAMPTZ '1970-01-01 00:00:00+00'
) AS bucket_start;
-- 2026-11-22 08:05:00+00
~~~

**Note:** `date_bin` works for fixed durations like minutes or hours; never pass month intervals because calendar months vary in length. A “UTC day” also differs from a “local business day” in DST regions; clarify the bucket type before choosing functions.

### 4.1. UTC Days and Business Days Do Not Always Share Boundaries

Raw storage should retain unambiguous absolute timestamps, usually `TIMESTAMPTZ` with consistent conventions. When reporting by **local calendar day**—such as `Asia/Ho_Chi_Minh`—convert event times to local time before extracting the date:

~~~sql
SELECT
    (TIMESTAMPTZ '2026-11-22 00:30:00+07'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
    AS business_date;
-- 2026-11-22
~~~

In many regions, DST transitions create 23-hour or 25-hour local days. Therefore, **a local-day rollup does not always equal 24 UTC hourly rollups**. In multi-timezone systems, select hourly buckets spanning from **local midnight** to **next local midnight** converted into absolute instants.

## 5. Which Measures Can Aggregate Across Multiple Levels?

Correct multi-tier rollups depend on **statistical mergeability**, not SQL function names alone.

### 5.1. Mergeable Statistical State

Suppose bucket A stores `count_A, sum_A, min_A, max_A`, and bucket B stores matching state. Merging two **non-overlapping** sets:

$$
\operatorname{count}_{A\cup B}=\operatorname{count}_A+\operatorname{count}_B
$$

$$
\operatorname{sum}_{A\cup B}=\operatorname{sum}_A+\operatorname{sum}_B
$$

$$
\min_{A\cup B}=\min(\min_A,\min_B),\quad \max_{A\cup B}=\max(\max_A,\max_B)
$$

$$
\operatorname{avg}_{A\cup B}=\frac{\operatorname{sum}_A+\operatorname{sum}_B}{\operatorname{count}_A+\operatorname{count}_B}
$$

Key preconditions: buckets share **the same unit, the same sample-filtering rules, and zero overlap**. `count` is the number of valid samples, not the number of minutes in the bucket.

You can store additional mergeable state such as `sum_of_squares` for variance, or numerically stable parallel variance state (e.g., Chan's/Welford's merge). Never compute combined variance by summing separate per-bucket **variances**; merging requires counts, means, and sum-of-squared deviations to control numerical error.

### 5.2. Example: AVG of AVGs Gives the Wrong Answer

A sensor emits four samples:

| `observed_at` (UTC) | Temperature (°C) | 5-Min Bucket |
| --- | ---: | --- |
| 08:00 | 18 | 08:00 |
| 08:01 | 20 | 08:00 |
| 08:04 | 22 | 08:00 |
| 08:06 | 30 | 08:05 |

Bucket 08:00 has **count = 3, sum = 60, avg = 20 °C, min = 18 °C, max = 22 °C**. Bucket 08:05 has **count = 1, sum = 30, avg = 30 °C, min = max = 30 °C**.

Averaging the two bucket averages gives:

$$
\frac{20+30}{2}=25\,^\circ\mathrm{C}
$$

That **is not the average of the four samples**. The exact result is:

$$
\frac{60+30}{3+1}=22.5\,^\circ\mathrm{C}
$$

**Retain at least `sum` and `count`** to roll up sample averages accurately across tiers. For floating-point measures, also watch rounding drift and numerical stability.

### 5.3. Irregular Sampling: Sample Mean Differs from Time-Weighted Mean

In that example, three samples clustered closely and one sat farther away. **22.5 °C** is the **arithmetic mean of four samples**; it **does not automatically represent the time-weighted average over all 10 minutes**.

If the requirement is “average temperature over the time span” under irregular sampling, specify how the signal is reconstructed between points:

- **Last observation carried forward** (*step / LOCF*), bounded by a maximum gap limit.
- **Linear interpolation** between points if physics and domain rules allow.
- Device-reported time-integrated measurements.
- Explicit gap marking rather than guessing values during unmonitored periods.

A time-weighted mean integrates **value × duration / total valid duration**, never `sum(sample_values) / count(samples)`. That requires storing time-weighted state, handling bucket boundaries, and enforcing gap rules. **Never label a sample-count average as a time-weighted average without weighting.**

### 5.4. Gauges, Counters, and Event Counts Are Different Quantities

| Data Type | Examples | Aggregation Approach to Consider |
| --- | --- | --- |
| **Gauge** | Temperature, water level, instantaneous CPU % | Sample `AVG`/`MIN`/`MAX`; possibly time-weighted `AVG` |
| **Cumulative counter** | Total bytes since boot, electricity meter | Compute **deltas/rates** between readings and handle resets/wraps |
| **Event count** | Each completed order is an event | `COUNT` over windows, with deduplication |
| **End-of-period state** | End-of-day balance, end-of-hour inventory | Take **last valid** with clear ordering; never `SUM` across time |
| **Flow quantity in period** | kWh consumed over an interval or captured payment amount | `SUM` if intervals and units do not overlap |

**Never directly `SUM` cumulative counter readings.** If a counter climbs from 100 to 110 then resets to 3, taking `MAX - MIN` or `last - first` across the hour fails. You need reset/wrap metadata, sampling context, and clear distinction between resets and glitches. Without enough evidence, flag data quality instead of publishing fake precision.

**Never `SUM` hourly closing inventory balances** to compute end-of-day inventory. End-of-day stock is a point-in-time state at period end, whereas daily inbound/outbound movements are additive flow quantities.

### 5.5. Percentiles and Distinct Counts Cannot Merge via Simple Addition

If each 5-minute bucket keeps only **p95**, you cannot average those p95 values to get hourly p95. Likewise, summing per-minute **`COUNT(DISTINCT user_id)`** double-counts users active in multiple minutes.

Valid approaches include:

- Recomputing from **raw** while raw data remains available and volume permits.
- Storing **mergeable statistical summaries** such as well-defined histograms or sketches (quantile/distinct estimators), documenting error bounds and merge rules.
- Reporting per-bucket values **without** fabricating an exact hourly p95 when underlying detail is absent.

A rollup storing only `avg`, `p95`, and `distinct_count` is generally **insufficient for accurate rollup to the next tier**.

## 6. PostgreSQL Schema: Raw as Authoritative, Rollups as Derived

Examples use temperature in **°C**, where each sample carries a source-issued ID, absolute timestamp, and quality status. This schema is **illustrative**, omitting calibration tables, device signatures, multi-tenant isolation, and sensitive-data policies.

### 6.1. Sensor and Raw Sample Tables

~~~sql
CREATE TABLE sensors (
    sensor_id TEXT PRIMARY KEY,
    unit_code TEXT NOT NULL CHECK (unit_code = 'C'),
    installed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw_temperature (
    raw_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    source_sample_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    temperature_c NUMERIC(9, 3) NOT NULL,
    quality_status TEXT NOT NULL
        CHECK (quality_status IN ('VALID', 'REJECTED')),
    CONSTRAINT uq_raw_source_sample
        UNIQUE (sensor_id, source_sample_id)
);

CREATE INDEX ix_raw_sensor_observed_at
    ON raw_temperature (sensor_id, observed_at);
~~~

**Keys and grain:**

- `raw_id` is a technical surrogate key.
- `UNIQUE(sensor_id, source_sample_id)` enforces one-sample-per-sensor grain; `observed_at` is **not** used alone as a unique constraint.
- `observed_at` drives **event-time** bucketing; `received_at` tracks lag and backfills.
- `quality_status` controls rollup eligibility; rejected samples can stay in raw during retention for diagnostics.
- The index on `(sensor_id, observed_at)` serves single-sensor range scans; multi-sensor time scans may require different indexes or physical layouts.

If the source **does not supply stable sample IDs**, build identifiers from sequences, natural keys, or collision-aware fingerprints. Generating a fresh `UUID` per server receipt fails to detect retransmissions.

**Designing tables for millions of samples/day requires addressing partitioning, retention, and write throughput.** This example intentionally uses an unpartitioned table for clean unique constraints rather than silently promising global uniqueness on a partitioned table with different key rules.

### 6.2. Safe Ingestion on Device Retries

~~~sql
INSERT INTO raw_temperature (
    sensor_id,
    source_sample_id,
    observed_at,
    temperature_c,
    quality_status
)
VALUES (
    $1, $2, $3::TIMESTAMPTZ, $4::NUMERIC, $5
)
ON CONFLICT (sensor_id, source_sample_id) DO NOTHING;
~~~

`DO NOTHING` is **safe only when retries carry identical contents**. If the same `source_sample_id` arrives with a different `observed_at` or `temperature_c`, that is a **conflict requiring investigation**, not a harmless retry. Production pipelines compare payload fingerprints and log traceable correction events.

An **append-only** model preserves received telemetry for auditability. If a source legitimately corrects a published reading, store a separate revision/correction record; updating raw rows in place requires an audit policy and **invalidating affected rollups**. “Raw” does not exempt data from legal or retention deletion rules.

## 7. Designing 5-Minute Rollups with Mergeable State

~~~sql
CREATE TABLE temperature_5m (
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    temperature_sum NUMERIC(25, 3) NOT NULL,
    temperature_min NUMERIC(9, 3) NOT NULL,
    temperature_max NUMERIC(9, 3) NOT NULL,
    recalculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, bucket_start),
    CHECK (temperature_min <= temperature_max)
);

CREATE TABLE temperature_hourly (
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    temperature_sum NUMERIC(27, 3) NOT NULL,
    temperature_min NUMERIC(9, 3) NOT NULL,
    temperature_max NUMERIC(9, 3) NOT NULL,
    recalculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, bucket_start),
    CHECK (temperature_min <= temperature_max)
);
~~~

Grain of `temperature_5m`: **one row per sensor per 5-minute bucket containing at least one valid sample**. When zero valid samples exist, this table holds **no row** for that bucket; never insert `sample_count = 0` with `temperature_min = 0`, because 0 °C is a valid temperature rather than evidence of a reading.

To tell whether an absent rollup row means “no sensor samples” versus “pipeline hasn't run yet”, track **window completion status** in job checkpoints or a separate coverage table. The rollup metrics table alone **does not prove pipeline completeness**.

### 7.1. Computing Rollups Over an Aligned Window

Example refreshing the entire **`[08:00, 09:00)` UTC** window, where `$1` and `$2` are verified by the application to be **5-minute aligned** with `$1 < $2`. The transaction clears existing buckets in range and reinserts from raw:

~~~sql
BEGIN;

DELETE FROM temperature_5m
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ;

INSERT INTO temperature_5m (
    sensor_id,
    bucket_start,
    sample_count,
    temperature_sum,
    temperature_min,
    temperature_max
)
SELECT
    r.sensor_id,
    date_bin(
        INTERVAL '5 minutes',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    COUNT(*)::BIGINT AS sample_count,
    SUM(r.temperature_c) AS temperature_sum,
    MIN(r.temperature_c) AS temperature_min,
    MAX(r.temperature_c) AS temperature_max
FROM raw_temperature AS r
WHERE r.quality_status = 'VALID'
  AND r.observed_at >= $1::TIMESTAMPTZ
  AND r.observed_at <  $2::TIMESTAMPTZ
GROUP BY
    r.sensor_id,
    date_bin(
        INTERVAL '5 minutes',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    );

COMMIT;
~~~

**Why `DELETE` then `INSERT` instead of blind incremental addition?**

- Job retries over the same window **never double-count**.
- Prior samples downgraded to `REJECTED` or retracted reduce counts cleanly, even deleting buckets that drop to zero valid samples.
- Using `INSERT ... ON CONFLICT DO UPDATE` alone leaves stale rows behind for **buckets that previously had rows but now have zero valid samples**.
- Wrapping in a transaction commits all changes atomically in PostgreSQL; readers under suitable isolation never see an empty half-refreshed gap.

**Critical limitation:** an orchestrator must ensure **no two refresh jobs run concurrently on overlapping windows**, and account for concurrent raw commits. A transaction on the rollup table **does not freeze `raw_temperature`** during execution. Under `READ COMMITTED`, `INSERT` sees a snapshot of raw as of statement start; samples committing milliseconds later require a follow-up refresh. Completeness comes from watermarks/lookbacks and job coordination, not SQL syntax alone.

If 5-minute rollups refresh per sensor, scope `DELETE`/`INSERT` by sensor to reduce locks and I/O. At high scale, full-window refreshes cause **write amplification** and table bloat; benchmark and switch to compensating incremental aggregation if needed.

### 7.2. Reading Accurate Averages from Rollup State

~~~sql
SELECT
    sensor_id,
    bucket_start,
    temperature_min,
    temperature_max,
    temperature_sum / NULLIF(sample_count, 0)
        AS sample_mean_temperature_c,
    sample_count
FROM temperature_5m
WHERE sensor_id = $1
  AND bucket_start >= $2::TIMESTAMPTZ
  AND bucket_start <  $3::TIMESTAMPTZ
ORDER BY bucket_start;
~~~

Naming the column **`sample_mean_temperature_c`** clarifies it is a **valid-sample mean**, not a time-weighted mean. Given `CHECK (sample_count > 0)`, `NULLIF` is defensive hygiene preventing division by zero.

## 8. Multi-Level Rollups: 5 Minutes → 1 Hour → 1 Day

One UTC hour holds **12 5-minute buckets**, though perhaps only 9 contain **valid samples**. Those three missing rows must be interpreted via completeness policy rather than assuming 0 °C for those 15 minutes.

### 8.1. Rolling Up an Hour from 5-Minute States

Assuming `temperature_5m` is refreshed and verified complete up to the target cutoff, run the hourly job on **hour-aligned bounds**:

~~~sql
BEGIN;

DELETE FROM temperature_hourly
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ;

INSERT INTO temperature_hourly (
    sensor_id,
    bucket_start,
    sample_count,
    temperature_sum,
    temperature_min,
    temperature_max
)
SELECT
    sensor_id,
    date_bin(
        INTERVAL '1 hour',
        bucket_start,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    SUM(sample_count) AS sample_count,
    SUM(temperature_sum) AS temperature_sum,
    MIN(temperature_min) AS temperature_min,
    MAX(temperature_max) AS temperature_max
FROM temperature_5m
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ
GROUP BY
    sensor_id,
    date_bin(
        INTERVAL '1 hour',
        bucket_start,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    );

COMMIT;
~~~

Using Section 5's samples, the hour totals `sum = 90`, `count = 4`, giving `average = 22.5 °C`, even though the two 5-minute buckets averaged 20 °C and 30 °C.

**Never compute `AVG(temperature_sum / sample_count)`** for hourly mean: that weights every bucket equally instead of weighting every sample. For hourly min/max, take **`MIN` of mins** and **`MAX` of maxes**.

### 8.2. Daily Rollups: Choose the Right Definition of Day

If reports require **UTC days**, roll up hourly buckets over `[00:00 UTC, next 00:00 UTC)`.

If reports require **plant local business days**, derive `business_date` in the plant's timezone and group matching buckets. When UTC hourly boundaries cross half-hour or 45-minute offset timezones, **you cannot assign an entire UTC hourly bucket to one local day cleanly**. In such timezones, aggregate from a finer grain (e.g., 15-minute buckets or raw) or align bucket boundaries to the timezone contract.

An illustrative daily table might use grain **`(sensor_id, business_date, timezone_id)`**, storing `count, sum, min, max` plus completeness status. Do not put `timezone_id` in the key purely decoratively: if a sensor relocates across timezones, date attribution rules must reflect effective location history.

### 8.3. Multi-Tier Chains Need Checkpoints and Dependencies

If the hourly job runs before the 5-minute job incorporates late data, the hourly table turns stale despite bug-free SQL. Every tier needs:

- Clear source definitions and formulas.
- A **completed** timestamp watermark from the upstream tier.
- A mechanism to flag altered buckets (*dirty buckets*) and cascade refreshes upward.
- Re-execution and republication policies.
- End-to-end **freshness tracking from raw commit to rollup API**.

Never equate a cron clock trigger with bucket “completeness”. When sensors transmit late, wall-clock cron timing proves nothing about sample arrival.

## 9. Late Events, Out-of-Order Delivery, and Historical Corrections

Suppose at 08:20 the system receives a sample with `observed_at = 08:02`:

- It belongs in **bucket 08:00–08:05**, not 08:20.
- If `temperature_5m` for 08:00 already ran, that bucket must be **refreshed/adjusted**.
- If `temperature_hourly` for 08:00 already ran, it may need refreshing too.
- If raw data for that span has already expired, exact recomputation from raw may be impossible.

### 9.1. Watermarks and Allowed-Lateness Windows

An operational contract might state:

> The system accepts late arrivals up to **2 hours** past event time for routine rollup updates; older events route into a controlled investigation/backfill workflow.

**Two hours is just an example**, not a universal default. Watermarks can derive from per-source observations, server time, and lateness bounds; explicitly document calculation rules and clock assumptions.

A bucket can move through states:

- **OPEN**: actively receiving valid data; shown as incomplete.
- **PROVISIONAL**: computed, still inside the allowed-lateness window.
- **FINALIZED per policy**: routine auto-edits stop; special correction paths remain possible.

**FINALIZED is not a mathematical proof that late events cannot arrive.** It merely records an accepted operational risk boundary. Retroactive corrections require restatement or marking published outputs as revised.

### 9.2. Dirty-Bucket Propagation Workflow

~~~text
Receive raw sample:
  validate identity + content + quality
  persist raw successfully
            |
            v
Identify affected finest-grain event-time bucket
  e.g., sensor=S1, 5m bucket=08:00
            |
            v
Mark dirty bucket / enqueue refresh
            |
            v
Refresh 5m from raw (full span)
            |
            v
Mark + refresh corresponding hourly bucket
            |
            v
Mark + refresh business-day bucket if needed
            |
            v
Reconcile + update freshness/checkpoint
~~~

If a change in `temperature_c` or `quality_status` removes a sample from statistics, net deltas can be negative. **Purely additive updates from incoming events** fail on edits and removals. Recomputing small buckets from raw is simpler to prove right, while incremental pipelines must retain prior state and compensating entries.

Guard against **lost notifications**: if raw commits while dirty-bucket signaling fails, rollups stay stale indefinitely. Emit outbox/queue intents **inside the same source transaction**, use CDC, or sweep changed intervals periodically; best-effort post-commit messaging without retries fails to converge.

### 9.3. Re-Runs Must Not Double-Count

Idempotency applies at distinct layers:

1. **Raw:** receiving the same `source_sample_id` does not insert a duplicate row.
2. **5-minute job:** refreshing the same bucket does not add numbers twice.
3. **Hourly/daily jobs:** re-running does not multiply lower-tier counts.
4. **Consumers:** reprocessing the same recompute request creates no duplicate rows at the same grain.
5. **Corrections:** each edit carries an ID/version so it applies at most once.

A `PRIMARY KEY (sensor_id, bucket_start)` on rollups protects row identity, yet **does not automatically protect arithmetic**. Calling `ON CONFLICT DO UPDATE SET sum = sum + incoming_sum` on retry double-counts that bucket; apply incremental deltas only when exactly-once delta application is guaranteed.

## 10. Multi-Tier Retention: Intentional Information Trade-Offs

Raw telemetry is invaluable for investigations, yet keeping full resolution for years can be costly. An *illustrative* policy:

| Data Tier | Resolution | Example Retention | Primary Access Pattern |
| --- | --- | --- | --- |
| Raw | Every source sample, with ID and event time | 30 days | Root-cause investigation, debugging, recent rollup rebuilds |
| `temperature_5m` | 5 minutes | 180 days | Shift, weekly, recent monthly views |
| `temperature_hourly` | 1 hour | 2 years | Medium-term trends, dashboards |
| `temperature_daily` | 1 business day | 5 years | Multi-year trends |

**These windows are examples, not legal advice or default standards.** Derive retention from analytics, incident investigation, compliance, privacy, backfill windows, and storage budgets.

### 10.1. Safe Order for Purging Raw Data

Never purge raw data purely because a calendar date passed if dependent rollups haven't succeeded. A safe checklist:

1. Verify every bucket in the target span was processed per policy, including empty slots.
2. Check checkpoints, failed jobs, dirty buckets, and reconciliation reports.
3. Confirm 5-minute/hourly/daily tiers depending on that raw span are complete.
4. Close out pending late arrivals or corrections.
5. Execute retention—deletion or cold archival per policy—and record the purge watermark.
6. Document which statistics **can no longer be recalculated accurately** once raw is gone.

After raw expires, if the 5-minute table holds only `count, sum, min, max`, you can still roll those metrics up to hours and days; you **cannot** reconstruct raw samples to compute arbitrary percentiles or detect 2-second spikes. If needed, store richer summaries, archive raw to cold object storage, or extend retention.

### 10.2. Back-of-the-Envelope Capacity Math

Suppose **1,000 sensors** each emit **one sample every 10 seconds** continuously:

$$
1000\times6\times60\times24=8\,640\,000\ \text{samples/day}
$$

Over 30 days: roughly **259.2 million raw samples** before accounting for retries, indexes, metadata, row headers, compression, or replication.

A 5-minute rollup produces at most:

$$
1000\times12\times24=288\,000\ \text{buckets/day}
$$

An hourly rollup produces at most **24,000 buckets/day**. These upper bounds assume every sensor reports in every bucket; intermittent sensors produce fewer rows. **Never multiply a single temperature byte size by sample count and call it database size**: account for tuple overhead, keys, WAL, indexes, retention padding, and backups.

A rollup table storing one row per bucket **does not automatically cut disk size by 30×** if metadata and indexes dominate small rows. Benchmark on realistic configurations.

### 10.3. Privacy and Time-Bounded Data

Time-series data is not always benign. Device locations, operating schedules, user activity, or production telemetry can be sensitive. Avoid copying unnecessary identifying tags across every rollup tier. Deletion and anonymization schedules must cover **raw, rollups, caches, backups, event logs, and exports** within policy scope.

## 11. Downsampling for Charts: Picking Meaningful Display Points

A 1,200-pixel screen cannot render **one million points** legibly on one line. Downsampling reduces network transfer and rendering overhead, yet the selection algorithm shapes what viewers see.

### 11.1. Mean-Only Hides Alerts

Suppose one minute has 59 readings at **20 °C** and one reading at **80 °C**. The minute average is:

$$
\frac{59\times20+80}{60}=21\,^\circ\mathrm{C}
$$

If a chart plots only **21 °C**, operators miss the 80 °C spike that may warrant an alarm. For spike-sensitive telemetry, return **average alongside min/max** envelopes, or preserve salient peaks and range bands.

Still, **`min/max` does not tell you how long a peak lasted** or intra-bucket ordering. If safety requires “above 70 °C for 10 consecutive seconds”, `max = 80` in a bucket cannot prove duration. You need raw samples or a dedicated exceedance-duration counter.

### 11.2. Comparing Point-Reduction Methods

| Method | Preserved | Lost / Risks | Best Used When |
| --- | --- | --- | --- |
| **Every N-th sample** | Periodic raw samples by position | Can skip spikes between chosen points | Band-limited signals with few sudden spikes |
| **Mean per bucket** | Average trend | Masks spikes/breaches; misleads if buckets averaged unweighted | Trend analysis, never replacing alerts |
| **Min + max + mean** | Trend plus intra-bucket envelope | Loses spike ordering and duration | Monitoring range-bound dashboards |
| **First + last per bucket** | Open and close points | Can miss interior extremes | Step-change telemetry |
| **Shape-preserving selection** | Visual peaks and inflection points | Algorithm-dependent; does not preserve exact statistics | Dense visual line charts |
| **Histograms / sketches** | Approximate distribution; mergeable quantiles/distincts | Approximation error and bounds | Long-term distribution analytics |

**Display downsampling must never become the source of truth for business calculations.** Safety alarms, billing, and compliance checks must run on full-fidelity data and validated aggregations—never on points dropped solely to fit screen pixels.

### 11.3. Never Draw Fake Lines Across Missing Data

If a sensor goes silent for 30 minutes, connecting the point before the gap straight to the point after misleads viewers into thinking temperature drifted smoothly in between.

Establish a display contract:

- Buckets with **no samples** are **`NULL`/gaps**, not 0.
- **Incomplete** buckets are styled differently or flagged.
- Forward-fill or interpolation happens **only when domain rules permit**, within strict time bounds.
- Device states and event counts follow different gap semantics than continuous gauges.

In the data model, `sample_count` helps gauge coverage yet **does not prove continuous sensor operation**. If 6 samples per minute were expected and only 1 arrived, you can still compute an average of 1 sample, but confidence is low.

## 12. Selecting Data Tiers by Query Range and Resolution

An API can pick the storage tier from query span and target point count:

~~~text
GET /sensor/{id}/series?from=...&to=...&targetPoints=1200

Query planner:
  15 minutes -> raw (if retained and load permits)
  24 hours   -> 5 minutes
  90 days    -> 1 hour
  3 years    -> 1 day
~~~

These are **illustrative rules**, not rigid mappings. Also weigh **spike-detection resolution**, rollup freshness, retention, and bucket width. A 90-day query aiming for ~1,200 points may pick a different resolution depending on UI needs.

### 12.1. Never Mix Overlapping Time Ranges

If an API returns raw points for **the last 15 minutes** and 5-minute rollups for **24 hours**, split the timeline into **non-overlapping intervals**. Never sum a rollup that already includes raw samples together with those raw samples.

Example:

~~~text
[from, cutoff)   -> finalized 5-minute rollups only
[cutoff, to)     -> fresher raw, aggregated on the fly under same rules
~~~

`cutoff` must align cleanly to bucket boundaries, and queries slicing across partial leading/trailing buckets must define **partial-bucket** semantics. A full 5-minute bucket can include samples outside the user's `[from, to)` span if `from` is misaligned—never return it disguised as an exact statistic for the narrower slice.

If rollups lag behind, APIs can serve stale rollups tagged with their watermark or fall back to raw for bounded ranges. **Always reading raw** is not a free fix for lag under millions of requests.

### 12.2. Defining Result Completeness Metadata

A well-designed response may include:

- `resolution = '5m'`, `timezone = 'UTC'`.
- `from`, `to`, `bucket_start`, and half-open bucket semantics.
- `sourceWatermark` / completed rollup timestamp.
- `isProvisional` when the bucket sits inside the allowed-lateness window.
- `sampleCount` to indicate sample density.
- `min, max, mean` with units and calculation method.

Not every endpoint needs every metadata field on every point, yet the system must be able to **explain freshness and meaning** during audits.

## 13. Physical Design: Partitioning, Indexes, Compression, and Update Cost

Select physical organization only after locking down grain and access patterns.

### 13.1. Time Partitioning

Large raw tables are commonly partitioned by `observed_at` (daily/weekly/monthly depending on throughput and partition size) to:

- Prune out-of-range partitions during queries.
- Enforce retention via partition drops/detaches.
- Bound index maintenance and bulk load footprints.

In PostgreSQL declarative partitioning, **`UNIQUE`/`PRIMARY KEY` constraints on partitioned tables normally must include all partition key columns** per engine rules. Therefore, never convert Section 6's raw table to time partitioning and assume `UNIQUE(sensor_id, source_sample_id)` still protects globally if `observed_at` is absent from the constraint. Handle global deduplication explicitly—for instance, via date-scoped source IDs, an unpartitioned identity registry, or tested idempotent ingestion flows.

Too-small partitions multiply catalog metadata, indexes, and planning time; too-large partitions slow purges and maintenance. Size partitions based on write rates, sensor distribution, retention, and operations.

### 13.2. Indexes Must Match Queries

- “Sensor S1 over `[t1, t2)`” typically suits `(sensor_id, observed_at)`.
- “All sensors over a short range” may require different index order or partition pruning depending on selectivity.
- Rollups use `PRIMARY KEY (sensor_id, bucket_start)` for per-sensor timelines and grain uniqueness.
- Large append-mostly tables can leverage append-friendly indexes and clustering where supported; avoid piling up unused B-trees.
- Queries filtering by sensor metadata belong with dimension tables or controlled tag keys rather than cloning rare tags onto every raw row.

**High cardinality** (too many combined IDs/tags) multiplies series counts, group counts, rows, and indexes. Putting a unique `request_id` or `session_id` into rollup keys turns a “5-minute × sensor” table into nearly “one row × event”, defeating rollups entirely.

### 13.3. Compression and Storage Tiers Do Not Replace Measure Definitions

Compression shrinks raw byte storage **without reducing temporal resolution**. Downsampling drops points and **intentionally discards detail**. Cold archival shifts storage cost and access latency without necessarily erasing samples.

These three techniques work well together:

1. Recent raw on hot storage.
2. Older raw compressed or archived if audits demand it.
3. Long-term rollups on fast read tiers.

Never treat “compression” and “downsampling” as the same operation. The difference decides whether you can recompute metrics when dashboard formulas change.

## 14. Reconciling Raw Against Every Rollup Tier

To verify accuracy, compare **the same sensor, same window, same quality filter, and same watermark**. A 5-minute reconciliation query in PostgreSQL:

~~~sql
WITH expected AS (
    SELECT
        sensor_id,
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        ) AS bucket_start,
        COUNT(*)::BIGINT AS sample_count,
        SUM(temperature_c) AS temperature_sum,
        MIN(temperature_c) AS temperature_min,
        MAX(temperature_c) AS temperature_max
    FROM raw_temperature
    WHERE quality_status = 'VALID'
      AND observed_at >= $1::TIMESTAMPTZ
      AND observed_at <  $2::TIMESTAMPTZ
    GROUP BY
        sensor_id,
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        )
),
stored AS (
    SELECT *
    FROM temperature_5m
    WHERE bucket_start >= $1::TIMESTAMPTZ
      AND bucket_start <  $2::TIMESTAMPTZ
)
SELECT
    COALESCE(e.sensor_id, s.sensor_id) AS sensor_id,
    COALESCE(e.bucket_start, s.bucket_start) AS bucket_start,
    e.sample_count AS expected_count,
    s.sample_count AS stored_count,
    e.temperature_sum AS expected_sum,
    s.temperature_sum AS stored_sum,
    CASE
        WHEN e.sensor_id IS NULL THEN 'EXTRA_ROLLUP'
        WHEN s.sensor_id IS NULL THEN 'MISSING_ROLLUP'
        WHEN e.sample_count IS DISTINCT FROM s.sample_count
          OR e.temperature_sum IS DISTINCT FROM s.temperature_sum
          OR e.temperature_min IS DISTINCT FROM s.temperature_min
          OR e.temperature_max IS DISTINCT FROM s.temperature_max
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_status
FROM expected AS e
FULL OUTER JOIN stored AS s
    ON s.sensor_id = e.sensor_id
   AND s.bucket_start = e.bucket_start;
~~~

**Reconciliation limitations:**

- Raw may still be ingesting new points; comparing unsynchronized snapshots causes transient mismatches. **Pin a checkpoint or reconcile only buckets older than the watermark.**
- Once raw expires, raw-to-rollup reconciliation is impossible. Comparing **hourly against 5-minute** checks tier consistency if 5-minute data remains, yet cannot catch flaws shared across both tiers.
- Matching `COUNT`/`SUM`/`MIN`/`MAX` does not prove individual raw rows are valid; offsetting errors or upstream quality bugs can still hide.
- With floating-point arithmetic, exact equality may fail; define justified tolerances. The SQL above uses `NUMERIC` for exact illustration.
- On mismatch, trace root cause across raw, quality filters, time windows, jobs, duplicates, or corrections, then **recompute from the authoritative tier available**.

### 14.1. Multi-Tier Reconciliation Needs Explicit Invariants

A contract can assert invariants such as:

- Sum of 5-minute `sample_count`s within an hour equals hourly `sample_count` **provided** all constituent buckets were processed without overlap.
- Corresponding `temperature_sum` totals match, and min/max merge properly.
- `bucket_start` aligns strictly to resolution boundaries.
- Each grain key appears at most once.
- No bucket marked finalized still has pending dirty flags.
- Lower and higher tiers share checkpoints proving identical source scope at publication time.

Monitoring only “job exit code = 0” without verifying invariants and freshness lets silent rollup drift persist for weeks.

## 15. Making Trade-Offs Using Workload, Precision, and Cost

Suppose a dashboard displays 90 days for one sensor with requirements:

- API p95 latency ≤ **300 ms**.
- Roughly **1,000–2,000 points** with **min/max** so extremes stay visible.
- Hourly metrics lag at most **10 minutes** after policy completeness.
- Raw investigation retained for **30 days**.
- Support recomputation when late events arrive within published windows.

Numbers below are **purely hypothetical for practicing trade-off analysis**, not actual benchmarks:

| 90-Day Read Option | Points Returned for 1 Sensor | Illustrative p95 | Trade-Off |
| --- | ---: | ---: | --- |
| Direct raw, 10s samples | ~777,600 | 2,200 ms | Preserves every point, yet overloads UI/DB and exceeds 30-day raw retention |
| 5-minute rollup | 25,920 | 540 ms | Keeps min/max, far more points than UI needs |
| 1-hour rollup | 2,160 | 170 ms | Meets API SLO while preserving hourly extremes |
| 1-day rollup | 90 | 95 ms | Too coarse to inspect intra-day swings |

**Conditional decision:** hourly rollups fit the 90-day chart if hourly variation and min/max meet user needs. Still verify **freshness**, late arrivals, sensor coverage, and statistical accuracy. If the business must catch 5-second spikes, hourly rollups alone cannot suffice—pair them with raw alerting paths.

Never pick based on p95 alone: hourly tables cut read latency while adding write, index, queue, storage, reprocessing, and operational overhead. Track key dimensions:

| Dimension | Examples |
| --- | --- |
| **Raw ingestion** | Samples/sec, duplicate rate, validation errors, p95/p99 ingest latency |
| **Rollups** | Buckets/sec, job runtime, CPU/I/O, write amplification |
| **Freshness** | Source commit → 5m → hourly → API lag, oldest dirty bucket |
| **Late arrivals** | Rate, lateness distribution, restated bucket count |
| **Correctness** | Missing/extra/mismatched rollups, `sample_count`, and coverage |
| **Storage** | Footprint across raw/5m/hourly/daily, indexes, backups, compression, retention |
| **Queries** | p95/p99 across 15m, 24h, 90d, and 3y ranges |
| **Recovery** | Time to rebuild a day/week, backfill capability post-purge |

## 16. Choosing Data Models by Access Pattern

### 16.1. Relational and Time-Series Extensions

PostgreSQL cleanly stores raw, rollup, and sensor dimension tables with strong keys, indexes, and transactions. Its strength lies in declarative constraints, SQL reconciliation, and joining metadata with telemetry.

At higher scale, specialized time-series databases or extensions automate chunk/partition management, compression, retention drops, and continuous aggregates. However, **exact capabilities vary by product and version**—verify late-data handling, refresh triggers, unique keys, and timezone semantics rather than assuming identical behavior.

### 16.2. Document

Document stores fit when each sample is an event document or when storing **bounded sample blocks per sensor × time window**. Unbounded arrays inside a single document grow unwieldy and create write contention; never embed years of raw history into one sensor document.

When batching samples inside documents, still define **logical per-sample grain**, deduplication keys, and how late events update the right bucket. Nesting documents does not replace statistical rules.

### 16.3. Graph

Graphs excel at **relationships among sensors, equipment, locations, plants, and production lines** or fault-dependency tracing. Storing billions of scalar readings as individual graph edges rarely outperforms dedicated time-series stores.

A common pairing keeps samples in a time-series store and equipment topology in a graph, linked via `sensor_id`. When sensor locations or ownership change, model temporal validity on graph edges for historical analysis.

### 16.4. Analytical / Columnar Warehouses

Analytical warehouses model facts at **one sample** grain or **sensor × bucket** grain alongside sensor and time dimensions, feeding multi-tier rollups for BI and long-term reporting.

Distinguish **state gauges/balances** from **additive flows**. An hourly fact with `count, sum, min, max` rolls up cleanly to daily/monthly; a fact storing only `avg` cannot. Columnar formats like Parquet do not automatically fix invalid aggregation math.

## 17. Pre-Deployment Checklist

| Question | Required Evidence |
| --- | --- |
| What defines one raw sample? | `sensor_id + source_sample_id`, timestamp, and unit |
| What happens on device retries? | Idempotency key and payload-conflict policy |
| What kind of measure is it? | Gauge, cumulative counter, event count, end-of-period state |
| What are bucket boundaries? | `[start, end)`, origin, timezone, fixed vs. calendar |
| What defines a valid sample? | Quality rules plus correction/reconciliation paths |
| Which metrics can merge? | `count`/`sum`/`min`/`max`, specialized states, never AVG of AVGs |
| What happens when samples are absent? | Explicit missing/gap handling, never auto-zeroed |
| How much lateness is tolerated? | Watermarks, allowed-lateness windows, provisional/finalized states |
| How do recomputations behave? | Deduplication, dirty buckets, multi-tier dependencies |
| What drives retention? | Incident investigation, reporting, regulations/policy, backfill needs |
| What is lost when raw expires? | Exact percentiles, individual samples, brief spikes |
| How does the API pick resolution? | Query span, pixel density, min/max, partial buckets |
| Can tiers be reconciled? | Synchronized snapshot, `count`/`sum`/`min`/`max`, and coverage |
| What are physical costs? | Partitioning/indexes/compression, cardinality, query and write SLOs |
| Who owns raw and rollups? | Clear ownership for raw fixes, pipelines, dashboards, and alerts |

## 18. Practice Exercises

### Exercise 1 — Averaging Two Buckets

Bucket A has **3 samples**: 18, 20, and 22 °C. Bucket B has **1 sample**: 30 °C.

**Questions:** What is the overall `avg` across the span? Why is `AVG(avg_A, avg_B)` wrong?

### Exercise 2 — Sample on a Bucket Boundary

A system uses 5-minute UTC buckets, and a sample has `observed_at = 08:05:00`.

**Questions:** Does it belong to the 08:00 bucket or the 08:05 bucket? What goes wrong with `BETWEEN 08:00 AND 08:05` paired with `BETWEEN 08:05 AND 08:10`?

### Exercise 3 — Resetting Network Counter

A cumulative transmitted-bytes counter climbs steadily and resets when the device reboots. A team runs hourly `SUM(counter_value)` to report total bytes transmitted.

**Questions:** Why is that wrong? What metadata and formula are required?

### Exercise 4 — Missed Alarm When Keeping Only Averages

A sensor records 59 samples at 20 °C and one sample at 80 °C within a minute. The dashboard stores only the per-minute `avg`.

**Questions:** What do users see? How do you preserve visibility into spikes? Can spike duration be inferred from `min/max` alone?

### Exercise 5 — Late Event After All Three Tiers Ran

Jobs already built 5-minute, hourly, and daily rollups for a sensor. Later, a valid sample arrives whose event time lands in a 5-minute bucket from yesterday.

**Questions:** Which tables and checkpoints must be updated? If yesterday's raw data was already purged, what can still be done and what cannot be recovered?

### Exercise 6 — Missing Row in a Bucket

`temperature_5m` has no row for sensor S1 at 09:10. The frontend renders 0 °C while surrounding readings sit near 25 °C.

**Questions:** Is rendering 0 °C valid? List possible root causes for the missing bucket row.

### Exercise 7 — Picking Data Tiers for Goals

A dashboard plots 90 days of temperature with ~1,500–2,500 points; 5-minute, hourly, and daily rollups exist. Extremes must stay visible, though individual samples across the whole 90 days are unnecessary.

**Questions:** Which tier is the best candidate? Which measures/metadata should be stored and returned, and what must be verified beforehand?

### Exercise 8 — Sample Average vs. Time-Weighted Average

A sensor bursts several readings within 5 seconds, stays silent for 20 minutes, then sends one reading. A team runs `SUM(value) / COUNT(*)` and labels it time-averaged temperature.

**Questions:** Why is that semantically wrong? What contract rules and data are needed if a true time-weighted average is required?

### Exercise 9 — Retention and Percentile Recomputation

Raw is kept 30 days; 5-minute rollups store only `count, sum, min, max` and stay for 1 year. Six months later, stakeholders ask for exact hourly p99 from original samples.

**Questions:** Can exact p99 be recovered from those rollup fields? What options support the new requirement going forward?

### Solution Hints

1. Bucket A has `sum = 60, count = 3`; bucket B has `sum = 30, count = 1`. The **four-sample mean** is **`(60 + 30) / (3 + 1) = 22.5 °C`**. Averaging the two bucket averages gives **25 °C** by weighting unequal buckets equally.
2. It belongs to **`[08:05, 08:10)`**. Using closed `BETWEEN` ranges double-counts the 08:05 sample in both buckets. Always use **`[start, end)`**.
3. A cumulative counter is not per-sample incremental bytes. Compute **ordered inter-sample deltas**, use metadata/rules to handle **resets/wraps** and missing spans, and never `SUM` absolute counter readings.
4. The average is **21 °C**, hiding the 80 °C peak. Store **`min/max`** or preserve extreme points and dedicated alert events. From `min/max` alone, **spike duration cannot be inferred**; retain raw or dedicated exceedance-duration state.
5. Refresh the **5-minute** bucket, then **hourly**, then **daily**, updating dirty flags, checkpoints, freshness, and reconciliation. If raw was purged, you can apply **evidence-backed deltas** where contract and state allow, yet you cannot reconstruct raw samples or exact percentiles from `count/sum/min/max`.
6. No: **absent sample ≠ 0 °C**. Display a gap/`NULL` and check whether the sensor stopped, samples were `REJECTED`, delivery lagged, jobs missed a run, partitions/retention dropped data, or ingestion errored.
7. **Hourly rollups** over 90 days yield ~**2,160 points**, fitting the target. Return `mean` from `sum/count`, **`min/max`**, `count`, and freshness metadata. Verify late-arrival handling, coverage, API SLOs, and whether hourly detail loss is acceptable.
8. **`SUM/COUNT`** is a **sample-count average**, over-weighting dense bursts. Define interpolation/carry-forward between points, **gap limits**, duration-weighted integration, and boundary clipping rules.
9. **No**, exact p99 cannot be recovered from `count/sum/min/max`. You must retain raw/archive data, store **sufficient distribution state** or mergeable histograms/sketches with documented error bounds, or revise retention and reporting definitions.

## 19. Key Takeaways

**Raw data preserves individual observations; rollups preserve mergeable bucket statistics; downsampling lowers resolution for queries and charts.** These three representations differ in **grain, time semantics, completeness, and information-loss trade-offs**.

For accurate multi-level rollups, retain **mergeable components** such as `count, sum, min, max` where valid rather than mechanically averaging averages. Counters, balances, percentiles, distinct counts, and time-weighted means require distinct formulas or statistical state.

**Reducing resolution is a business trade-off that discards information**, not lossless file compression. Before purging raw data, know which investigations users need, which metrics stay recomputable, how late arrivals propagate, and how gaps must appear. Only when **correctness, freshness, recoverability, and cost** are all explicit does a time-series model remain safe to maintain and evolve.
