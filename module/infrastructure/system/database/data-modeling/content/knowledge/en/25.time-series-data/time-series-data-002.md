# Series Keys, Timestamps, and Dimensions Identifying a Measurement

A temperature collection system may receive messages such as:

~~~text
08:00  Device D-101, channel INDOOR, temperature 25.2 °C
08:00  Device D-101, channel OUTDOOR, temperature 30.1 °C
08:00  Device D-102, channel INDOOR, temperature 24.8 °C
08:01  Device D-101, channel INDOOR, temperature 25.4 °C
~~~

If **timestamp** is used as the unique key, the three readings at 08:00 collide. If only **device + timestamp** is used, D-101's INDOOR and OUTDOOR channels still collide. If only **device + metric type + timestamp** is used, a sensor with two channels or two processing methods still cannot be distinguished.

The core issue is not “adding enough columns to the primary key until it stops colliding”, but defining **what a single measurement represents**, **which dimensions make it a distinct series**, and **what meaning the timestamp in the message carries**.

This lesson belongs to the **Time-Series Data** chapter of the **DATABASE_DATA_MODELING** module. Its goal is to translate data-collection requirements into a verifiable model of identities, relationships, keys, constraints, and indexes, while comparing how time series are represented across relational, document, graph, and analytical systems.

> **Principle:** The series key answers **“which stream of observations is this?”**; the timestamp answers **“when was the measurement effective/observed?”**; the measurement key answers **“is this truly one distinct observation within that stream?”** The three concepts are related, not synonymous.

## 1. Distinguishing Time Series, Measurements, and Values

A **time series** is a collection of observations of **the same quantity with consistent semantics**, ordered along a time axis. Each observation typically has:

- **Series identity:** a combination of subject, metric type, channel, method, or other dimensions distinguishing the measurement source.
- **Measurement timestamp or time interval:** when the phenomenon was recorded, or the interval the value represents.
- **Value:** numeric reading, state, tuple of values, or event.
- **Quality and provenance metadata:** measurement unit, reliability, source, version, ingestion timestamp, and correction reason.

A temperature series can be visualized as:

~~~text
Series S1001:
  tenant = 1
  device = D-101
  metric = air_temperature
  channel = INDOOR
  method = CALIBRATED
  canonical_unit = degC

Observations:
  2026-10-10T08:00:00+07:00  -> 25.2
  2026-10-10T08:01:00+07:00  -> 25.4
  2026-10-10T08:03:00+07:00  -> 25.5
~~~

All three observations belong to the **same series**, yet they are **three distinct measurements**. One device can produce multiple series; the same timestamp can appear across multiple series; and the same series can receive duplicate messages or revisions.

### 1.1. Row Grain

Before creating a table, write a complete sentence, for example:

> “One `MeasurementSample` row is **the normalized temperature value of exactly one series at exactly one observed instant**, with at most one current version per `(series, instant)` pair.”

If business rules allow two valid samples from the same series at the exact same instant, that sentence **no longer holds**. You then need another stable identifier, such as `sample_sequence` or `source_sample_id`.

| Single-Row Definition | Possible Natural Key | Can Timestamps Repeat? |
| --- | --- | --- |
| Current reading of a series at an instant | (series_id, observed_at) | No, under **this grain contract** |
| Independent sensor event | (source_system, source_event_id) | Yes |
| k-th sample emitted by a sensor at instant t | (series_id, observed_at, sample_seq) | Yes, if seq validly distinguishes them |
| 5-minute aggregation of a series | (series_id, window_start, window_length, aggregation_method, version) | Yes across types/windows |
| Correction version of the same data point | (series_id, observed_at, source_revision) | Yes, because it is **version history** |
| End-of-day device state | (device, metric, local_business_date, timezone_rule) | No by snapshot definition |

**Never choose keys from sample data before defining the grain.** Two values that happen not to collide in a test set do not prove they will remain unique forever.

### 1.2. Observation Records Differ from Transport Messages

A sensor may resend the same sample three times due to retries. The data store may receive:

~~~text
message 1 -> sample A
message 2 -> sample A   (retry)
message 3 -> sample A   (retry)
~~~

These are **three receipts**, but only **one business observation** if the ID and payload confirm it is the same sample. Conversely:

~~~text
message 1 -> sample A at 08:00:00.000
message 2 -> sample B at 08:00:00.000
~~~

can genuinely be two distinct observations if the device supports multiple measurements at the same timestamp with separate sample IDs.

Therefore, distinguish **message ID**, **source event/sample ID**, **series ID**, and **observation key**. Do not use an auto-incrementing ingestion sequence number as proof that two messages represent two new measurements.

## 2. Designing the Series Key

A series key can be a combination of identifying dimensions:

~~~text
series_business_key =
    (tenant_id, device_id, metric_id, channel_code, method_code)
~~~

In this example:

- **tenant_id:** organizational scope owning the device; `device_id` may only be unique within a tenant.
- **device_id:** the actual device or measurement point.
- **metric_id:** the quantity with defined semantics and canonical unit, e.g., `air_temperature` or `cumulative_energy`.
- **channel_code:** channel such as `INDOOR`, `OUTDOOR`, `PHASE_A`, `PHASE_B`...
- **method_code:** `RAW`, `CALIBRATED`, or another computation method with distinct semantics.

The system may generate **series_id** as a *surrogate key* for that combination. The business key must have a **UNIQUE** constraint so two write paths cannot create two `series_id` values for the same combination. A surrogate key keeps foreign keys and indexes on the sample table compact, but it must never replace business uniqueness rules.

### 2.1. Which Dimensions Belong in the Series Key?

Include a dimension in the series key only when **changing that dimension creates a semantically different stream of observations**.

| Attribute | Usually Part of Series Identity? | Rationale / Exception |
| --- | --- | --- |
| Tenant | Yes, if identifiers differ across organizations | Prevents cross-tenant data mixing |
| Device or measurement point | Yes | Distinguishes the observation source |
| Metric type | Yes | Temperature differs from humidity; power differs from energy |
| Channel / phase / axis | Yes if one device measures multiple channels of the same type | `PHASE_A` differs from `PHASE_B` |
| Method `RAW`/`CALIBRATED` | Yes **if both outputs coexist as two series** | If merely a correction to the same value, use revisions |
| Unit of measurement | Depends on metric definition | Better normalized to a canonical unit when convertible |
| Current location | Depends on what is being measured | Moving a device does not necessarily change its identity |
| Firmware version | Usually no | Usually time-varying metadata, unless it alters measurement semantics |
| Quality `OK`/`SUSPECT` | No | Belongs to each observation, not a new series |
| Ingestion timestamps | No | The same measurement arriving late must not spawn a new series |
| Measured value | No | Values change continuously; putting them in the key destroys series meaning |
| Request ID / session ID | Usually no | Ultra-high-cardinality labels cause unbounded series growth |

This is not an absolute list. If a metric “air temperature at a fixed monitoring point” treats the **monitoring point** as the primary identity while physical sensors are swapped during maintenance, the series key may use **measurement_point_id** instead of `device_id`. Conversely, when monitoring the behavior of a **specific device**, `device_id` is the key identifying dimension.

### 2.2. Units and Semantic Versions

Temperatures **25 °C** and **77 °F** represent the same physical quantity expressed differently. When measured by the same source at the same instant, do not create two independent observations and sum or count both merely because the units differ.

Typically, you should:

1. Define a **canonical_unit** tied to the metric, such as `degC`.
2. Convert at the ingestion or semantic layer, recording **source_unit** if traceability is needed.
3. Ensure conversion uses the exact formula and required precision.
4. If a metric changes **definition** (for instance, instantaneous temperature becomes a 5-minute average), introduce a new **metric version/method/aggregation** rather than silently reusing the series as if values were equivalent.

For financial metrics, currencies **VND and USD** are not equivalent without conversion at the appropriate exchange rate and timestamp; currency may be part of the metric's semantic key or a required grouping dimension.

### 2.3. Should Every Label Be Added to the Series Key?

No. A label such as `user_id`, `request_id`, or `trace_id` that changes with every message can produce nearly as many series as events. This causes **cardinality explosion**: huge numbers of sparse series consuming metadata memory, indexes, files/partitions, and query overhead.

Separate:

- **Series dimensions:** stable attributes sufficient to distinguish the measurement streams being tracked.
- **Observation attributes:** quality, `source_event_id`, clock offset, operation tags, detailed payload.
- **Contextual/time-varying dimensions:** device location, operations group, effective-dated firmware.
- **Measure values:** temperature, flow rate, cumulative energy, measured status.

If a field is only used to filter occasional investigations and has millions of distinct values, it does not need to become a series-identifying tag. Keep it on the event record or a separate lookup table.

## 3. Measurement Keys: Is Series + Timestamp Enough?

In a typical sampling model:

~~~text
PRIMARY KEY (series_id, observed_at)
~~~

is valid **if and only if** the domain confirms:

> For a given series, at most one valid sample exists as current state at any single instant.

This does not mean every device sends only one message per second. A timestamp may have microsecond precision, or multiple messages belonging to **the same sample** may be resent. You must know the source's **timestamp precision and assignment behavior**.

### 3.1. Cases Where a Two-Column Key Fails

1. **Sub-millisecond sampling:** the source truncates timestamps to milliseconds, causing distinct real samples to collide after rounding.
2. **Multi-channel sampling:** `channel_code` was omitted from the series key, forcing two distinct metrics onto the same key.
3. **Two sources measuring the same target simultaneously:** `source_id` or `measurement_method` produces two distinct series.
4. **Sensors emitting corrections:** one sample has multiple versions; a separate history table is needed if you must avoid overwriting.
5. **Interval-spanning measurements:** the true key must include the interval or window definition.
6. **Multiple events at the same timestamp:** an operational event stream is not necessarily unique by timestamp.

### 3.2. When Multiple Measurements at the Same Instant Are Valid

If the source supplies a **stable `sample_seq`** per series/instant, the grain can be:

~~~text
(series_id, observed_at, sample_seq)
~~~

If the source supplies a globally or tenant/source-unique **`source_sample_id`**, you can use:

~~~text
(source_system, source_sample_id)
~~~

as the observation business key, while `(series_id, observed_at)` serves filtering and ordering.

**Never auto-generate `sample_seq` from message arrival order** if you need retry detection, because the same sample can arrive at a different queue position. Choose a stable source ID or a verified deterministic derivation rule.

### 3.3. Does a Surrogate Key on the Sample Table Solve Duplicates?

A **`sample_id BIGINT IDENTITY`** only gives each row a technical key. It **does not prevent** two rows from representing the same business observation. You still need a `UNIQUE` constraint matching the grain, or an event table with source identifiers and deduplication logic.

For example, if the requirement is one sample per series per instant, adding `sample_id` while dropping `UNIQUE(series_id, observed_at)` weakens the invariant. Conversely, if multiple samples per instant are valid, enforcing `UNIQUE(series_id, observed_at)` is **too strict**.

## 4. The Time Axis: One Record Can Carry Multiple Timestamps

A single measurement may carry several distinct timestamps:

| Field | Meaning | Example |
| --- | --- | --- |
| **observed_at / event_time** | Instant when the phenomenon was observed | 08:00 at the sensor |
| **device_recorded_at** | Raw timestamp stamped by the device | May drift due to clock skew |
| **received_at / ingested_at** | When the system received and accepted the message | 08:05 due to network lag |
| **processed_at** | When the pipeline normalized/scored quality | 08:06 |
| **valid_from / valid_to** | Interval during which a version/attribute is effective | Device location from Oct 1 to Oct 20 |
| **bucket_start_at / bucket_end_at** | Interval represented by an aggregation | Average from 08:00 to before 08:05 |

**`observed_at` does not necessarily equal `received_at`.** Data can arrive late, be retried, or be re-ingested. When reporting “temperature by hour of occurrence”, group by `observed_at`; when analyzing “pipeline lag”, compare `received_at` and `observed_at`.

### 4.1. Instants vs. Local Time

An instant such as:

~~~text
2026-10-10T08:00:00+07:00
~~~

represents the exact same point in time as:

~~~text
2026-10-10T01:00:00Z
~~~

In PostgreSQL, **`TIMESTAMPTZ`** represents an instant that can be compared, sorted, and differenced across timezones. It **does not preserve the original timezone name** such as “Asia/Ho_Chi_Minh” or the sender's original offset formatting.

If you need the original business timezone, store **`timezone_name`** separately as an IANA zone name, or derive it from device location history. Never label a `TIMESTAMP WITHOUT TIME ZONE` column as “UTC” out of habit without an enforced convention.

### 4.2. Daylight Saving Time (DST), Non-Existent Times, and Repeated Times

In regions observing Daylight Saving Time, a local wall-clock time may **not exist** on spring-forward days or may **occur twice** on fall-back days. Thus:

~~~text
device_local_time = 01:30
~~~

**is not always enough to identify an instant** without a timezone and offset/disambiguation rule during transitions.

For local-time systems, specify the timezone region and ambiguity resolution rule. If you store only local wall-clock time without an offset, you cannot reliably infer `observed_at` in every case.

A business day can also last **23, 24, or 25 hours** depending on timezone and date. When grouping by local day, never assume every day has exactly 86,400 seconds.

### 4.3. Timestamp Resolution Is Not Sampling Frequency

Two distinct concepts:

- **Timestamp precision/resolution:** whether the source distinguishes milliseconds, microseconds, or nanoseconds.
- **Sampling interval/cadence:** whether the device is expected to measure every second, every minute, or irregularly.

A sensor sampling 100 times per second while transmitting second-level timestamps will produce collisions unless `sample_seq` is present. A device measuring every minute with microsecond timestamps can still exhibit **jitter** (`08:00:00.032`, `08:01:00.041`).

PostgreSQL `TIMESTAMPTZ` typically has **microsecond** resolution. If devices genuinely require nanosecond distinction, design an extension such as **`epoch_ns` as `BIGINT`**, source/sequence identifiers, and sample ordering while controlling value ranges and client read/write tooling—never silently truncate and overwrite other samples.

### 4.4. Clock Drift and Clock Corrections

A sensor clock may run a few seconds fast or slow; upon NTP sync, source timestamps may “jump backward”. If deduplication relies solely on device-recorded timestamps, real samples can overwrite one another.

Distinguish:

- **raw_device_time:** original timestamp for auditing.
- **corrected_observed_at:** instant adjusted according to a documented policy.
- **clock_quality/offset_estimate:** confidence level of the correction.
- **source_sample_id/sequence:** sample identity independent of the clock.

If `observed_at` is corrected, the key identity `(series_id, observed_at)` changes too. You need a migration/versioning workflow to avoid breaking references to published data.

## 5. Point-in-Time Measurements vs. Interval Measurements

An instantaneous temperature sample and a **5-minute average temperature** do not share the same grain.

### 5.1. Instantaneous Measurements

~~~text
(series_id, observed_at) -> temperature_value
~~~

For example, 25.2 °C at 08:00:00. The value describes **that instant** as defined by the sensor or algorithm.

### 5.2. Windowed Measurements

~~~text
(series_id, window_start_at, window_end_at, aggregation_method)
    -> aggregate_value
~~~

For example, the **AVG** temperature in the window:

~~~text
[08:00, 08:05)
~~~

is defined using the **half-open interval `[start, end)`**: inclusive of start, exclusive of end. A sample at exactly 08:05 belongs to the next window, never to two adjacent windows simultaneously.

Specify:

- Is the window a fixed 5-minute span or a local calendar day?
- Is `AVG` a **sample average** or a **time-weighted average**?
- How are gaps and poor-quality samples handled?
- Up to what cutoff of corrected data does the aggregation apply?
- Should **`sample_count`, `coverage`, `calculation_version`, and `watermark`** be stored?

The same series and `window_start` can have **MIN, MAX, AVG** and multiple window lengths. Therefore, **`(series_id, window_start)`** is not always a sufficient key for an aggregate table.

### 5.3. Do Not Equate a Window Timestamp with an Observation Time

One system may label aggregate rows with **`window_end_at`** instead of **`window_start_at`**. Either convention works if consistent, but it must be documented explicitly.

If a message:

~~~json
{"timestamp":"2026-10-10T08:05:00+07:00","value":25.3}
~~~

is the **AVG of `[08:00, 08:05)`**, it must not be treated as an instantaneous temperature at 08:05. Omitting aggregation type and window length leads to invalid JOINs and comparisons.

## 6. Metric Semantics Determine Allowed Computations

Having a timestamp and series key still does not tell you whether **`SUM`, `AVG`, `MAX`, or differencing** makes sense.

| Metric Type | Example | Value Semantics | Typical Operations |
| --- | --- | --- | --- |
| **Gauge** | Temperature, water level, active connections | State at an instant | `LAST`, `MIN`, `MAX`, defined `AVG` |
| **Cumulative counter** | Cumulative kWh meter, total network bytes | Cumulative total up to timestamp | `DELTA` between samples, `RATE` over time |
| **Delta/event count** | Requests in one minute | Occurrence within an interval | `SUM` over non-overlapping windows |
| **State** | `RUNNING`, `STOPPED`, `ERROR` | Categorical state over time | State duration, transition counts |
| **Histogram/distribution** | Latency distribution over a window | Multiple buckets/summaries | Merge histograms structurally; never `AVG(p95)` |
| **Transaction event** | A purchase or refund | Distinctly identified event | `COUNT`/`DISTINCT`/`SUM` by grain |

### 6.1. Gauges Are Not Additive Over Time

Temperatures of 25 °C at 08:00 and 26 °C at 08:01 **do not** mean “51 °C across two minutes”. If an average is needed, compute `AVG` as defined; under **irregular sampling**, an unweighted sample average can differ from the true time-weighted average.

For example, 25 °C lasts 9 minutes and 35 °C lasts 1 minute. The two-sample average is 30 °C, while the duration-weighted average is 26 °C assuming values hold constant between timestamps. Always state interpolation/step-function assumptions.

### 6.2. Never SUM Cumulative Counter Snapshots

An electricity meter records:

~~~text
08:00 -> 450.0 kWh (cumulative total)
08:01 -> 450.2 kWh
~~~

Consumption over the interval is **0.2 kWh**, not 900.2 kWh. If a counter resets or wraps around, differences can go negative or jump abnormally; define policies to detect resets and meter replacements.

### 6.3. Units and Numeric Precision

- Use `NUMERIC` when exact decimal arithmetic is required by the domain, such as monetary amounts; it carries higher storage and compute overhead.
- Use `DOUBLE PRECISION` when physical sensor readings suit floating point and approximate precision is acceptable; design comparisons and aggregations accordingly.
- Never mix Celsius and Fahrenheit, kW and kWh, bytes and bits, or VND and USD inside the same `SUM` simply because both are numeric columns.
- If units can change, store the **canonical unit / metric version** and conversion provenance.

A metric `power_kw` (instantaneous power) and `energy_kwh` (cumulative energy) are two **different physical quantities**, not merely two tags on the same series.

## 7. PostgreSQL Relational Schema: Series Metadata and Sample Tables

To keep business identities clear without repeating wide composite keys across millions of samples, separate:

1. **Tenant:** organizational scope.
2. **Device:** physical device or monitored subject within a tenant.
3. **MetricDefinition:** physical quantity and canonical unit.
4. **MeasurementSeries:** identity of a stable observation stream.
5. **MeasurementSamples:** timestamped values per series.

### 7.1. Identity Tables and Constraints

~~~sql
-- PostgreSQL: run the examples in a test database.
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE devices (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    device_id BIGINT NOT NULL,
    device_code TEXT NOT NULL,
    device_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, device_id),
    UNIQUE (tenant_id, device_code)
);

CREATE TABLE metric_definitions (
    metric_id BIGINT PRIMARY KEY,
    metric_code TEXT NOT NULL UNIQUE,
    canonical_unit TEXT NOT NULL,
    metric_kind TEXT NOT NULL
        CHECK (metric_kind IN ('GAUGE', 'COUNTER', 'DELTA'))
);

CREATE TABLE measurement_series (
    series_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_id BIGINT NOT NULL REFERENCES metric_definitions(metric_id),
    channel_code TEXT NOT NULL,
    method_code TEXT NOT NULL,

    CONSTRAINT fk_series_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES devices(tenant_id, device_id),

    CONSTRAINT uq_series_business_key
        UNIQUE (
            tenant_id, device_id, metric_id,
            channel_code, method_code
        )
);
~~~

Key points to note:

- The composite FK **`(tenant_id, device_id)`** prevents referencing another tenant's `device_id`. A single-column `FK(device_id)` in a system where `device_id` is not globally unique permits cross-tenant corruption or cannot even reference a composite PK.
- **`UNIQUE`** on the business key tuple prevents creating two series for the same observation stream.
- **`series_id`** is a convenient surrogate key for the sample table. It does not alter the semantics of the business key combination.
- `MetricDefinition` stores **`metric_kind`** and **`canonical_unit`**, helping prevent users from mistakenly summing gauges with counters. If a metric definition changes fundamentally, introduce a new metric ID/version.
- Channel and method are **`NOT NULL`**; if `NULL` is allowed in a `UNIQUE` key, you must account for DBMS `NULL` semantics and whether seemingly duplicate series could be inserted.

### 7.2. Sample Table with One Current Value per Series and Instant

~~~sql
CREATE TABLE measurement_samples (
    series_id BIGINT NOT NULL
        REFERENCES measurement_series(series_id),
    observed_at TIMESTAMPTZ NOT NULL,
    measurement_value NUMERIC(16, 5) NOT NULL,
    quality_code TEXT NOT NULL DEFAULT 'OK'
        CHECK (quality_code IN ('OK', 'SUSPECT', 'INVALID')),
    source_revision BIGINT NOT NULL DEFAULT 1
        CHECK (source_revision > 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    PRIMARY KEY (series_id, observed_at)
);
~~~

The primary key guarantees **at most one current row per series per instant**. It does **not** prove the source timestamp is accurate, that the series has no gaps, that the metric unit is right, or that `quality_code = 'OK'`.

We intentionally omit `CHECK (measurement_value >= 0)` because **Celsius temperatures can be negative**. If a specific metric must be non-negative (such as event counts), enforce that rule where full metric context exists; a row-level `CHECK` on samples does not see the parent's `metric_kind`.

**`received_at`** is stamped by the system upon row acceptance and may differ from `observed_at`. Choosing `NOW`/`CURRENT_TIMESTAMP` versus `clock_timestamp` relates to transaction start time versus statement execution time; this example uses `clock_timestamp()` to illustrate the actual time the statement runs.

### 7.3. Sample Data

~~~sql
INSERT INTO tenants (tenant_id, tenant_name)
VALUES (1, 'Plant A');

INSERT INTO devices
    (tenant_id, device_id, device_code, device_name)
VALUES
    (1, 101, 'D-101', 'Zone A sensor'),
    (1, 102, 'D-102', 'Zone B sensor');

INSERT INTO metric_definitions
    (metric_id, metric_code, canonical_unit, metric_kind)
VALUES
    (10, 'air_temperature', 'degC', 'GAUGE'),
    (20, 'energy_total', 'kWh', 'COUNTER');

INSERT INTO measurement_series
    (series_id, tenant_id, device_id, metric_id,
     channel_code, method_code)
VALUES
    (1001, 1, 101, 10, 'INDOOR', 'CALIBRATED'),
    (1002, 1, 101, 10, 'OUTDOOR', 'CALIBRATED'),
    (1003, 1, 102, 10, 'INDOOR', 'CALIBRATED'),
    (1004, 1, 101, 20, 'TOTAL', 'RAW');

INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value)
VALUES
    (1001, TIMESTAMPTZ '2026-10-10 08:00:00+07', 25.2),
    (1001, TIMESTAMPTZ '2026-10-10 08:01:00+07', 25.4),
    (1001, TIMESTAMPTZ '2026-10-10 08:03:00+07', 25.5),

    (1002, TIMESTAMPTZ '2026-10-10 08:00:00+07', 30.1),
    (1003, TIMESTAMPTZ '2026-10-10 08:00:00+07', 24.8),

    (1004, TIMESTAMPTZ '2026-10-10 08:00:00+07', 450.0),
    (1004, TIMESTAMPTZ '2026-10-10 08:01:00+07', 450.2);
~~~

Samples from different series share **the same `observed_at`**, which is completely valid. For series 1001, there is no row at **08:02**, representing a **gap against an expected 1-minute cadence**—assuming such a schedule applies.

**No row** at 08:02 does not mean the value was 0, nor does it necessarily mean the sensor broke; it could be network loss, reduced cadence, missing access, or unreceived telemetry.

### 7.4. Testing Uniqueness

If you execute:

~~~sql
INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value)
VALUES
    (1001, TIMESTAMPTZ '2026-10-10 08:00:00+07', 99.9);
~~~

PostgreSQL rejects it because PK **(1001, 08:00)** already exists. That is correct **under the grain of `measurement_samples`**. However, if the new message is a legitimate correction, you should neither blindly “drop as duplicate” nor blindly “overwrite because it arrived later”. You need versioning/source rules as shown in Section 11.

## 8. Querying by Series Key, Time Order, and Dimensions

### 8.1. Fetching Samples for One Series in a Half-Open Window

~~~sql
SELECT observed_at, measurement_value, quality_code
FROM measurement_samples
WHERE series_id = 1001
  AND observed_at >= TIMESTAMPTZ '2026-10-10 08:00:00+07'
  AND observed_at <  TIMESTAMPTZ '2026-10-10 08:05:00+07'
ORDER BY observed_at;
~~~

Using **`>= start` and `< end`** prevents adjacent windows from sharing a boundary sample and avoids fragile end-of-day timestamps like `23:59:59.999999`.

### 8.2. Fetching the Latest Sample per Series

~~~sql
SELECT DISTINCT ON (series_id)
       series_id, observed_at, measurement_value
FROM measurement_samples
WHERE quality_code = 'OK'
ORDER BY series_id, observed_at DESC;
~~~

On the sample dataset, this returns at most one latest `OK` sample **per series**. If a query omits tenant filtering, enforce tenant isolation through `MeasurementSeries` and access controls to prevent cross-tenant reads.

The **latest stored value** is not necessarily the **current operational value**: a sensor may have stopped reporting days ago. Dashboards must compare `observed_at` against a business-defined freshness threshold.

### 8.3. Finding INDOOR Temperature Readings for Device D-101

~~~sql
SELECT s.series_id,
       m.observed_at,
       m.measurement_value,
       md.canonical_unit
FROM measurement_samples AS m
JOIN measurement_series AS s ON s.series_id = m.series_id
JOIN devices AS d
  ON d.tenant_id = s.tenant_id
 AND d.device_id = s.device_id
JOIN metric_definitions AS md ON md.metric_id = s.metric_id
WHERE s.tenant_id = 1
  AND d.device_code = 'D-101'
  AND md.metric_code = 'air_temperature'
  AND s.channel_code = 'INDOOR'
  AND s.method_code = 'CALIBRATED'
ORDER BY m.observed_at;
~~~

Filtering on **device + metric + channel + method** isolates the exact series. Filtering only by `D-101` would mix indoor temperature, outdoor temperature, and the energy counter.

### 8.4. Averaging Samples in Fixed 5-Minute Buckets

Supported PostgreSQL versions provide **`date_bin`**, which partitions time into fixed-length buckets:

~~~sql
SELECT date_bin(
           INTERVAL '5 minutes',
           observed_at,
           TIMESTAMPTZ '1970-01-01 00:00:00+00'
       ) AS bucket_start,
       COUNT(*) AS sample_count,
       AVG(measurement_value) AS sample_average_deg_c
FROM measurement_samples
WHERE series_id = 1001
  AND quality_code = 'OK'
  AND observed_at >= TIMESTAMPTZ '2026-10-10 08:00:00+07'
  AND observed_at <  TIMESTAMPTZ '2026-10-10 08:05:00+07'
GROUP BY bucket_start
ORDER BY bucket_start;
~~~

The three samples 25.2, 25.4, and 25.5 yield **`sample_average = 25.3666... °C`**. That is a **sample-count average**, not necessarily a **time-weighted average**, because the 08:02 reading is missing and the gap between 08:01 and 08:03 is longer.

**`date_bin`** operates on fixed-length intervals anchored to an origin; do not use a fixed 24-hour bucket as a substitute for **local calendar days** in DST-observing timezones. For months or quarters, use calendar-aware functions and tooling.

### 8.5. Business Date in a Specific Timezone

To derive the local date of `observed_at` when reporting follows Vietnam time:

~~~sql
SELECT (observed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
           AS vietnam_business_date,
       COUNT(*) AS sample_count
FROM measurement_samples
WHERE series_id = 1001
GROUP BY vietnam_business_date
ORDER BY vietnam_business_date;
~~~

This illustrates assigning business dates in a query. When filtering large tables, convert local day boundaries into **two `TIMESTAMPTZ` instants** and apply range predicates directly on `observed_at` to preserve index usage and partition pruning. Never use the database server's default timezone in place of the business timezone.

## 9. Gaps, Sampling Cadence, and Data Coverage

A system with a 1-minute cadence may expect:

~~~text
08:00  -> present
08:01  -> present
08:02  -> missing
08:03  -> present
~~~

However, gap detection is valid only if you know:

- Was the series **expected to be active** during that interval?
- Is the sampling cadence fixed, or does it vary by operating mode?
- Do timestamps align exactly to minute boundaries, or is there jitter?
- Are delayed backfills allowed minutes, hours, or days later?
- Does `quality_code = 'INVALID'` count as “sample present” or “missing valid sample”?

### 9.1. Generating Expected Schedules with `generate_series`

This example **assumes timestamps align exactly to minute boundaries**:

~~~sql
WITH expected AS (
    SELECT step_at AS expected_at
    FROM generate_series(
        TIMESTAMPTZ '2026-10-10 08:00:00+07',
        TIMESTAMPTZ '2026-10-10 08:03:00+07',
        INTERVAL '1 minute'
    ) AS g(step_at)
)
SELECT e.expected_at,
       m.measurement_value,
       CASE WHEN m.observed_at IS NULL THEN 'MISSING'
            ELSE m.quality_code END AS sample_state
FROM expected AS e
LEFT JOIN measurement_samples AS m
  ON m.series_id = 1001
 AND m.observed_at = e.expected_at
ORDER BY e.expected_at;
~~~

The output flags **08:02 as `MISSING`** in the sample data. Do not wrap `measurement_value` in `COALESCE(measurement_value, 0)` just to make tables look tidy; **absent samples** differ from **measured zero**.

If a sensor reports at `08:01:00.041`, an exact equality join on `08:01:00` fails to match. You must define **tolerance/rounding/nearest-sample rules** and handle multiple samples falling into one slot. Rounding to the minute before deciding grain can discard data unless an aggregation policy or tie-breaker exists.

### 9.2. Completeness and Freshness Are Different Metrics

- **Completeness:** after waiting past the lateness window, what fraction of expected slots contain a valid sample?
- **Freshness:** how much time has elapsed since the most recent valid observation?
- **Latency:** what is the difference between `observed_at` and `received_at` or `processed_at`?
- **Quality:** what share of samples are `OK`, `SUSPECT`, and `INVALID` by source or failure mode?

A series can be **fresh** (just emitted a reading) while still **missing many past slots**; or have high completeness yesterday while having stopped sending today.

### 9.3. Interpolation and Gap Filling Do Not Create Real Observations

Common approaches include:

- **Forward fill:** carry the latest prior value up to a bounded limit.
- **Linear interpolation:** interpolate between adjacent valid points.
- **Zero fill:** only when “missing means 0” is an explicit domain rule.
- **Leave missing:** preserve `NULL`/gaps and report coverage percentage.

Derived records must be **tagged with their source/method**; never overwrite raw sensor samples. For high-risk metrics (healthcare, equipment safety, finance), never silently interpolate and mask missing telemetry.

## 10. Counters, Deltas, and Rates from Time Series

Cumulative counters require comparing consecutive samples within **the same series**.

~~~sql
WITH counters AS (
    SELECT series_id, observed_at, measurement_value,
           LAG(measurement_value) OVER (
               PARTITION BY series_id
               ORDER BY observed_at
           ) AS previous_value,
           LAG(observed_at) OVER (
               PARTITION BY series_id
               ORDER BY observed_at
           ) AS previous_at
    FROM measurement_samples
    WHERE series_id = 1004
      AND quality_code = 'OK'
)
SELECT observed_at,
       measurement_value,
       previous_value,
       CASE
           WHEN previous_value IS NULL THEN NULL
           WHEN measurement_value >= previous_value
                THEN measurement_value - previous_value
           ELSE NULL
       END AS nonnegative_delta_kwh,
       EXTRACT(EPOCH FROM observed_at - previous_at)
           AS seconds_between_samples
FROM counters
ORDER BY observed_at;
~~~

From 450.0 to 450.2 kWh, the delta is **0.2 kWh**. A decreasing counter must not automatically be treated as “negative consumption”: it may result from a reset, meter swap, reverse flow per metric definition, or out-of-order arrivals. Returning `NULL` **flags rows requiring policy-based handling** rather than guessing counter-reset math.

To compute a rate in kWh/hour:

~~~text
rate_kwh_per_hour = delta_kwh / elapsed_seconds * 3600
~~~

Verify `elapsed_seconds > 0`, quality of both endpoints, absence of resets, and actual observation timestamps. Never divide by an assumed “60 seconds” when actual spacing is 59.3 or 120 seconds.

For event counts defined per non-overlapping window, `SUM` across valid intervals may be more appropriate than subtracting counters; always align calculation with how source telemetry is recorded.

## 11. Late Data, Retries, Corrections, and Measurement Versioning

The same `(series_id, observed_at)` pair can appear multiple times in the ingestion pipeline due to:

1. **Retry:** same observation, same contents.
2. **Correction:** same observation, updated value/quality confirmed by the source.
3. **Out-of-order:** a newer revision arrives before an older revision.
4. **Clock correction:** the source corrects the sample's true timestamp.
5. **Two independent samples:** the original grain may have been defined too narrowly.

You cannot handle all five with an unconditional **`ON CONFLICT DO UPDATE`**.

### 11.1. Current-State Table with Conditional Update on `source_revision`

If the source guarantees `source_revision` **increases monotonically per `(series_id, observed_at)`**, update only when the incoming revision is newer:

~~~sql
INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value,
     quality_code, source_revision, received_at)
VALUES
    (1001,
     TIMESTAMPTZ '2026-10-10 08:00:00+07',
     25.3, 'OK', 2, clock_timestamp())
ON CONFLICT (series_id, observed_at)
DO UPDATE SET
    measurement_value = EXCLUDED.measurement_value,
    quality_code      = EXCLUDED.quality_code,
    source_revision   = EXCLUDED.source_revision,
    received_at       = EXCLUDED.received_at
WHERE EXCLUDED.source_revision > measurement_samples.source_revision
RETURNING series_id, observed_at, measurement_value, source_revision;
~~~

Revision 2 updates the value from **25.2 to 25.3**. If revision 1 is replayed later, the `WHERE` clause prevents overwriting revision 2.

Keep in mind:

- **`source_revision` must be stable and trustworthy**; never use arrival order as a revision number.
- A message with the **same revision but different payload** is a conflict requiring quarantine/inspection, not silent ignoring.
- `UPDATE` discards the prior current value unless an audit/history table exists.
- When a source corrects **`observed_at`**, that modifies a key component; you need a stable **`source_sample_id`** to know which record is being moved.
- A new incoming value is not necessarily a “new sample” that should increment observation `COUNT`; it may be a revision of an existing sample.

### 11.2. Append-Only Revision Table for “As-Known-At” Queries

If you must reproduce “what value did the system know at 09:00?”, retain all revisions:

~~~sql
CREATE TABLE measurement_sample_revisions (
    series_id BIGINT NOT NULL
        REFERENCES measurement_series(series_id),
    observed_at TIMESTAMPTZ NOT NULL,
    source_revision BIGINT NOT NULL CHECK (source_revision > 0),
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    measurement_value NUMERIC(16,5) NOT NULL,
    quality_code TEXT NOT NULL
        CHECK (quality_code IN ('OK', 'SUSPECT', 'INVALID')),
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    PRIMARY KEY (series_id, observed_at, source_revision),
    UNIQUE (source_system, source_event_id)
);
~~~

Here, the revision table is **source history**, while `measurement_samples` in Section 7 acts as a **current-state projection**. Never sum both tables as if they were two independent sources of truth.

Assuming each source guarantees an immutable payload per `source_event_id` and monotonically increasing `source_revision`, query the latest version **known before a cutoff**:

~~~sql
SELECT DISTINCT ON (series_id, observed_at)
       series_id, observed_at,
       source_revision, measurement_value, quality_code
FROM measurement_sample_revisions
WHERE received_at < TIMESTAMPTZ '2026-10-11 09:00:00+07'
ORDER BY series_id, observed_at, source_revision DESC;
~~~

If revisions arrive **out of order**, the query selects the highest revision number received prior to the cutoff rather than blindly picking the last-arrived message. This holds **under the source's increasing-revision contract**; adapt if the source uses another versioning scheme.

Never adopt a rule like “whichever message has the largest `loaded_at` is the latest truth” when stale revisions can arrive late. Reproducing full history also requires protecting the revision table against arbitrary `UPDATE`/`DELETE` and tracking dimension history.

### 11.3. Do Not Let Deduplication Mask Bad Data

A `UNIQUE` constraint blocks duplicate `INSERT`s, yet cannot automatically distinguish:

- Retry with same ID and same payload: safe to ignore.
- Same ID with different payload: **conflict**.
- Two distinct IDs for the same real measurement due to a source bug: requires business deduplication.
- Two distinct IDs at the same instant that are genuinely two measurements: **must not be dropped**.

Deduplication should record **`source_system`, `source_event_id`, `source_sample_id`, `source_revision`** and payload verification results whenever the source provides them, within the appropriate tenant scope.

## 12. Time-Varying Dimensions: Location, Ownership, and Device Revisions

A device's current location is not necessarily where a historical sample was measured. Suppose device `D-101` moved from Site A to Site B on Oct 20:

~~~text
D-101 at Site A during [Oct 01, Oct 20)
D-101 at Site B from Oct 20 onward
~~~

A sample recorded on Oct 10 belongs to Site A **as of `observed_at`**; you cannot join historical samples against a current `Devices` table holding `site_id = Site B` and retroactively attribute them to Site B.

### 12.1. Location History Model

~~~sql
CREATE TABLE sites (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    site_id BIGINT NOT NULL,
    site_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, site_id)
);

CREATE TABLE device_site_history (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,

    PRIMARY KEY (tenant_id, device_id, valid_from),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES devices(tenant_id, device_id),
    FOREIGN KEY (tenant_id, site_id)
        REFERENCES sites(tenant_id, site_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

The `CHECK` constraint prevents inverted intervals, but **does not forbid** overlapping `site-history` rows for the same device. If the rule is “a device is at most at one site at any instant”, add an exclusion constraint or transactional overlap checks.

### 12.2. Querying the Correct Site at Measurement Time

~~~sql
SELECT m.series_id,
       m.observed_at,
       m.measurement_value,
       h.site_id
FROM measurement_samples AS m
JOIN measurement_series AS s ON s.series_id = m.series_id
JOIN device_site_history AS h
  ON h.tenant_id = s.tenant_id
 AND h.device_id = s.device_id
 AND m.observed_at >= h.valid_from
 AND (h.valid_to IS NULL OR m.observed_at < h.valid_to)
WHERE s.tenant_id = 1;
~~~

If history contains **gaps**, an `INNER JOIN` **drops samples** from the report. If history **overlaps**, the `JOIN` **multiplies samples**. Validate temporal dimension integrity, and consider `LEFT JOIN` to reconcile unmapped samples rather than silently dropping them.

**Verify identity rules:** if a “series” is defined as measurements **at Site A** rather than **from device D-101**, relocating the device may require opening a new series rather than merely updating site history.

## 13. Designing Multi-Dimensional Series and Common Edge Cases

### 13.1. One Machine with Multiple Sensors Measuring the Same Quantity

If `D-101` has two temperature probes both labeled `INDOOR`, `tenant/device/metric/channel` is insufficient. You may need:

~~~text
probe_id or sensor_port
~~~

as an identifying dimension. If an old probe is replaced with a new one while tracking the same **logical measurement point**, key selection depends on reporting goals: tracking the physical hardware versus the fixed monitoring point.

### 13.2. Spatial Regions or Coordinates

Weather measurements on a coordinate grid may be identified by **`cell_id + metric + altitude/level`** instead of `device_id`. Never put floating-point `latitude`/`longitude` into a primary key without first specifying coordinate system, rounding precision, grid cells, and how moving points are handled.

### 13.3. Statistical Method as a Series Dimension

The same sensor might emit:

- Instantaneous temperature (`RAW`).
- 1-minute average temperature (`AVG_1M`).
- 1-minute maximum (`MAX_1M`).

These three streams differ in **method and grain**. Separate raw and aggregated data into distinct tables, or include statistic/window dimensions in the aggregate key. Never store them inside the same series without a distinguishing field, since timestamps will collide.

### 13.4. Multi-Valued Tags and Hierarchies

A machine may belong to multiple maintenance groups. Joining samples to **all groups** and then calling `SUM` multiplies row counts. For overlapping groupings, define whether **each sample counts once per group** or requires **weighted allocation** when group totals must sum to the grand total.

In particular, never `SUM` gauges such as temperature just because multiple rows exist; aggregation choice must match metric semantics.

### 13.5. Multi-Valued Observations (Vectors / Histograms)

One message may carry three acceleration axes `x, y, z` or a latency histogram. Two options exist:

- Keep a **vector observation** with structured components if all axes are always measured together and processed together.
- Split into three series (`metric`/`channel` `x, y, z`) if axes must be queried, quality-tagged, or updated independently.

Do not treat a vector as three independent events when they share one **`source_sample_id`** and one calibration step. Table structure and keys must reflect the semantics of the entire tuple.

## 14. Physical Modeling: Indexes, Partitioning, and Data Volume

One series emitting 60 samples/minute generates **86,400 samples/day**. With 10,000 active series at the same cadence, theoretical volume reaches **864 million samples/day** before accounting for dropped samples, compression, and metadata. That is a back-of-the-envelope capacity calculation for design, **not a benchmark**.

At scale, physical key choices directly impact writes, reads, and retention.

### 14.1. Indexing One Series Over a Time Range

The primary key:

~~~sql
PRIMARY KEY (series_id, observed_at)
~~~

on `measurement_samples` builds a B-tree over that composite key. It accelerates queries matching:

~~~text
WHERE series_id = ?
  AND observed_at >= ?
  AND observed_at < ?
~~~

and scans in either ascending or descending time order within a single series. You do not necessarily need an extra `(series_id, observed_at DESC)` index just to fetch the latest 10 samples if the existing B-tree performs backward scans efficiently.

### 14.2. Time-Range Queries Across Many Series

When dashboards fetch **all series within a short time window**, an index leading with `series_id` does not efficiently support predicates filtering only on `observed_at`. Depending on workload, consider:

~~~sql
CREATE INDEX idx_measurement_samples_time
ON measurement_samples (observed_at);
~~~

or a **`BRIN(observed_at)`** index on very large append-only tables when physical row insertion order **strongly correlates** with `observed_at`:

~~~sql
CREATE INDEX idx_measurement_samples_time_brin
ON measurement_samples USING brin (observed_at);
~~~

**Do not create both indexes out of habit.** B-trees offer finer selectivity at higher storage and write overhead; BRIN is tiny when data is physically time-ordered but may recheck many pages. Late-arriving samples insert earlier `observed_at` values out of physical order, weakening correlation and degrading BRIN effectiveness.

Evaluate using **`EXPLAIN (ANALYZE, BUFFERS)`**, row counts, page hits, latency, and ingestion cost on representative data.

### 14.3. Time Partitioning

Very large sample tables can be partitioned monthly or daily on `observed_at` to:

- Limit scans via partition pruning on `observed_at` filters.
- Simplify retention drops or archiving per time slice.
- Coordinate maintenance operations by data range.

Partitioning has costs: multiplied indexes, catalog entries, planning overhead, partition count management, and late data landing in older partitions. It does not automatically speed up queries filtering only by **`series_id`** with no time bound.

**PostgreSQL note:** `UNIQUE`/`PRIMARY KEY` constraints on partitioned tables must include all partition key columns under PostgreSQL rules. `PK(series_id, observed_at)` aligns with partitioning by `observed_at`, whereas another PK or partition column requires revisiting table-wide uniqueness enforcement.

For `event_id` values needing global `UNIQUE` enforcement across time partitions, do not assume a unique index **on `event_id` alone** works across PostgreSQL partitions when the partition key is excluded. Use an **unpartitioned deduplication/ingestion ledger table** or a different identity/partitioning strategy.

### 14.4. Retention and Downsampling

If raw samples are kept for 90 days while 5-minute aggregates are kept for 3 years:

- Define exact aggregation math, windows, units, and quality handling.
- Handle late arrivals and corrections across both raw and aggregate layers.
- Track **which windows are finalized** and when restatements are permitted.
- Never mix two resolutions under **an undifferentiated series key** where they could be summed or averaged together.
- Document recomputation limits once raw data expires.

If an aggregate was built from 20 samples and later corrections leave only 15 valid samples, decide whether to recompute, keep the old version, or publish a restatement. Never treat aggregates as immutable truth solely because raw rows have expired.

## 15. Comparing Relational, Document, Time-Series DB, Graph, and Analytical Warehouses

The same requirement—“a measurement with series identity and instant”—can be implemented across technologies, while grain and correctness rules stay the same.

| Architecture | Typical Organization | What to Verify |
| --- | --- | --- |
| **RDBMS/PostgreSQL** | Series metadata + sample tables with PK/FK and timestamps | Identity, uniqueness, partitioning/indexing, late corrections |
| **Time-series DB** | Metric name + tags/labels defining series; timestamp + value | Cardinality limits, precision, duplicate timestamps, retention/downsampling |
| **Document** | Series document embedding point arrays, or one doc per sample | Large array updates, time indexing, deduplication, history |
| **Graph** | Device/Metric/Site nodes with time-effective edges | Identity, as-of relationships, traversals without duplicating samples |
| **Warehouse/OLAP** | Fact measurements + conformed dimensions / `DimTime` | Grain, SCD2, measure semantics, rollups and coverage |

### 15.1. Document

Example series metadata document:

~~~json
{
  "seriesId": 1001,
  "tenantId": 1,
  "deviceCode": "D-101",
  "metricCode": "air_temperature",
  "channel": "INDOOR",
  "method": "CALIBRATED",
  "canonicalUnit": "degC"
}
~~~

and a measurement document:

~~~json
{
  "seriesId": 1001,
  "observedAt": "2026-10-10T08:00:00+07:00",
  "value": 25.2,
  "quality": "OK",
  "sourceRevision": 1
}
~~~

Storing one document **per observation** makes series/time indexing straightforward, though uniqueness and update semantics must be verified. Embedding **unbounded** arrays of points inside one series document risks hitting document size limits and creating write hotspots. Some document DBs offer bucketing patterns; evaluate based on the specific product.

### 15.2. Time-Series Databases and Labels

Some TSDBs treat **metric name + label/tag set** as the series identity. For example:

~~~text
air_temperature{tenant="1",device="D-101",
                channel="INDOOR",method="CALIBRATED"}
~~~

This expresses the same concept as a relational series business key. However, behavior for **duplicate timestamps**, backfills, quality flags, changing labels, and retention **depends on the specific product and version**. Never assume every TSDB shares the same duplicate policy or guarantees exactly-once ingestion out of the box.

Putting highly dynamic `request_id` or `user_id` values into labels causes cardinality to scale with requests rather than `devices × metrics × channels`. Before adding a label, estimate **active series count**, lifecycle, and combinatorial cardinality.

### 15.3. Graph and Time-Varying Context

Graphs excel when devices move across locations, have multi-tier dependencies, or require sensor-network tracing. However, a graph database alone does not solve storing billions of raw samples or computing time-weighted averages.

A hybrid approach is common:

~~~text
Graph: Device --LOCATED_AT(valid_from,valid_to)--> Site
TSDB/Fact: (series_id, observed_at) -> value
~~~

When joining or traversing the graph to attach a site to a sample, match **the edge effective at `observed_at`**, not every path linked to the device. Multiple matching edges in a graph will count the same sample multiple times.

### 15.4. Data Warehouses and Measurement Grain

In an analytical warehouse, a fact table might have keys:

~~~text
FactMeasurement(
  series_key,
  observed_time_key,
  device_version_key,
  location_version_key,
  value,
  quality_code
)
~~~

Do not assume `series_key` and all dimension versions are independent; if changing dimension attributes cause joins to fan out, KPIs get multiplied. Define conformed dimensions, SCD2 aligned to event time, and explicit grain.

A **temperature gauge** fact cannot be summed across days just because it is a numeric column. An **energy delta** fact can be summed across non-overlapping windows when units match and duplicates are eliminated.

## 16. Constraint and Data Quality Test Suite

A series model should have automated tests run before and after ingestion, especially when schemas evolve or new metrics are onboarded.

### 16.1. Verifying Data Invariants

| Invariant | How to Verify |
| --- | --- |
| Series business key uniqueness | `UNIQUE` on tenant/device/metric/channel/method |
| Current-state sample uniqueness | `PK(series_id, observed_at)` for one-sample-per-instant grain |
| Every sample references an existing series | FK to `measurement_series` |
| Every series points to a same-tenant device | Composite FK `(tenant_id, device_id)` |
| Metrics have clear units and kinds | `MetricDefinition` + domain constraints |
| Timestamps represent valid instants | `TIMESTAMPTZ`, source timezone/offset, clock checks |
| Same-revision messages do not conflict | Unique revision/source ID + payload check |
| Older revisions do not overwrite newer ones | Conditional upsert or projection from event history |
| Effective-dated sites do not overlap | Effective-dated dimension + interval checks |
| Snapshots are not summed across time | Semantic layer rules and KPI tests |
| Missing differs from zero | Gap/coverage and quality tests |
| Rollups do not mix with raw rows | Separate grain/metric/window/method keys |
| Queries do not leak across tenants | Query predicates, DB permissions / RLS where applicable |
| Late events are not silently dropped | Watermarks, retry/backfill, source-to-target reconciliation |

### 16.2. Inventory Query of Sample Counts per Series

~~~sql
SELECT series_id,
       COUNT(*) AS sample_count,
       MIN(observed_at) AS first_observed_at,
       MAX(observed_at) AS last_observed_at,
       COUNT(*) FILTER (WHERE quality_code <> 'OK')
           AS non_ok_samples
FROM measurement_samples
GROUP BY series_id
ORDER BY series_id;
~~~

This gives a high-level view of coverage and quality, yet **`COUNT(*)` does not replace expected slots**. A series sampled once daily is not missing data just because it has fewer rows than a 1-second series.

### 16.3. Finding Points with Multiple Revisions

~~~sql
SELECT series_id, observed_at,
       COUNT(*) AS revision_count,
       MIN(source_revision) AS first_revision,
       MAX(source_revision) AS last_revision
FROM measurement_sample_revisions
GROUP BY series_id, observed_at
HAVING COUNT(*) > 1
ORDER BY series_id, observed_at;
~~~

Multiple revisions are not automatically errors: they can reflect valid source corrections. However, verify that the highest revision was applied to current state, check for conflicting messages, and track whether prior values were already published.

### 16.4. Detecting High-Latency Series

~~~sql
SELECT series_id,
       COUNT(*) AS count_samples,
       AVG(EXTRACT(EPOCH FROM received_at - observed_at))
           AS avg_lag_seconds,
       MAX(EXTRACT(EPOCH FROM received_at - observed_at))
           AS max_lag_seconds
FROM measurement_samples
GROUP BY series_id;
~~~

This illustrates checking the current-state table. If `received_at` is updated when corrections arrive, it reflects the **most recent update time** rather than the **initial ingestion time**. Measuring initial source lateness requires a dedicated ingestion log.

Do not assume every negative lag indicates “future temperature”: the source clock may be skewed, or the system may emit forecast timestamps. Classify metrics and timestamp rules explicitly.

## 17. Step-by-Step Process from Requirements to Design

When modeling a new time-series source, follow these steps sequentially:

1. **Define the measured entity.** Are you tracking a physical device, logical measurement point, fixed site, user, transaction, or spatial grid cell?
2. **Define the metric.** Name, canonical unit, gauge/counter/delta/state kind, valid range, and calculation method version.
3. **Define the series business key.** Which dimensions must produce a separate series when changed? Which are merely metadata?
4. **State the observation grain.** Does `(series, instant)` allow at most one sample or multiple valid samples? Does the source provide a stable sample ID?
5. **Define time semantics.** Observed, recorded, received, effective, window start/end, timezone, resolution, and source clock behavior.
6. **Define missing data and quality.** Are unmeasured, disconnected, `INVALID`, `SUSPECT`, true zero, and interpolated values distinct states?
7. **Choose the physical model.** Metadata + sample tables, append-only events, revision logs, documents, TSDB, or a hybrid.
8. **Design keys and constraints.** PK, `UNIQUE`, tenant-scoped FK, dimension versions, and deduplication rules.
9. **Design update handling.** Retries, out-of-order arrivals, timestamp/value corrections, source versioning, and as-known-at requirements.
10. **Design queries.** Single series, all series in a window, last-known, buckets, counter deltas, gaps, and as-of site lookups.
11. **Design for scale.** Indexes, partitioning, compression, retention, downsampling, and backfills.
12. **Create edge-case test data.** Two channels at the same instant, same sample retried three times, two revisions, DST transitions, clock drift, dropped slot.
13. **Measure and reconcile.** `EXPLAIN`, representative datasets, throughput, active series count, ingestion lag, coverage, and conflict counts.
14. **Document the data contract.** Units, versions, keys, grain, timezones, quality, access control, and historical policies.

### 17.1. Sample Measurement Identity Contract

~~~text
Business entity:
  Indoor temperature monitoring point of D-101, tenant 1.

Metric:
  air_temperature; canonical_unit=degC; kind=GAUGE.

Series business key:
  (tenant_id, device_id, metric_id, channel_code, method_code)
  = (1, 101, 10, INDOOR, CALIBRATED).

Observation grain:
  One current value per observed_at per series.

Observation key:
  (series_id, observed_at)

Source identity:
  source_system + source_sample_id, if supported by source.

Time semantics:
  observed_at = normalized instant;
  received_at = pipeline ingestion timestamp;
  business timezone = effective site timezone at observed_at.

Duplicates:
  Same source ID/payload = retry;
  same source ID with different payload = error/controlled version.

Corrections:
  Higher source_revision wins;
  retain revision log if auditability is required.

Missing/quality:
  NULL/gap differs from zero; INVALID excluded from valid AVG.

Retention:
  Raw 90 days (only if policy allows);
  5-minute rollup with method and calculation_version.

Queries:
  Series timeline, latest OK, gaps, hourly AVG, site as-of.
~~~

Update this contract whenever devices, metrics, methods, or business requirements change. Never write just “timestamp + value” and hope every consumer interprets it identically.

## 18. Guided Exercises

### Exercise 1. Is Timestamp Enough as a Key?

**Prompt:** Two different sensors measure simultaneously at 08:00:00. Can `observed_at` be used as the sole `PRIMARY KEY` for the Measurement table?

**Solution hint:** No. Two observations in **two distinct series** can share the same timestamp. You need the series identity or a source sample identifier according to the defined grain.

### Exercise 2. Adding Channel to the Series Key

**Prompt:** Device `D-101` measures both `INDOOR` and `OUTDOOR` temperature at 08:00. Is `(device_id, metric_id, observed_at)` sufficient?

**Solution hint:** No, because the two channels still collide. If channel creates two distinct observation streams, it belongs in the **series business key**, or in the observation key if `series_id` is not used.

### Exercise 3. Samples with Equal Timestamps but Different IDs

**Prompt:** A high-speed sensor emits two genuinely distinct samples sharing the same millisecond timestamp, each with a stable `source_sample_id`. Should the second overwrite the first via `UPDATE`?

**Solution hint:** No. These may be **two valid observations**. Fix the grain—for example, include `source_sample_id` or a stable `sample_seq`; do not discard data merely because timestamps match.

### Exercise 4. Gauges and Counters

**Prompt:** Temperature is 25 then 26 °C; an electricity counter is 450.0 then 450.2 kWh. Which calculations apply?

**Solution hint:** Temperature is a gauge: `AVG`/`MIN`/`MAX` depending on the question, never `SUM` to 51 °C. The energy counter yields a delta of 0.2 kWh assuming no reset; never `SUM` to 900.2 kWh.

### Exercise 5. Late Arrival at the Same Observation Time

**Prompt:** A sample measured at 08:00 reaches the pipeline at 08:10. Should a dashboard grouped by measurement day assign it to 08:00 or 08:10?

**Solution hint:** Assign it by **`observed_at` = 08:00**. **`received_at` = 08:10** is used for latency tracking or as-known-at queries. Never turn late data into a new measurement at arrival time.

### Exercise 6. Correcting an Old Sample

**Prompt:** Series 1001 at 08:00 had revision 1 with value 25.2, followed by revision 2 with value 25.3. If a report asks for the “latest confirmed value”, what should it return?

**Solution hint:** Return **revision 2 = 25.3** per the source's increasing-revision rule. If prior reports must be reproducible, retain a revision log with `received_at` instead of overwriting without history.

### Exercise 7. Is Firmware Version an Identifying Tag?

**Prompt:** `D-101` updates firmware monthly without changing the measurement type. Should every firmware change automatically create a new series?

**Solution hint:** Not by default. Firmware can be a **time-varying attribute** of the device. Create a new series only if the change alters measurement **semantics/method** or analytical requirements explicitly mandate splitting.

### Exercise 8. Device Relocation

**Prompt:** `D-101` was at Site A until Oct 20, then moved to Site B. Which site should a Site A temperature report for Oct 10 join to?

**Solution hint:** Site A, using the effective interval containing the sample's **`observed_at`**. Joining on current site corrupts history; overlapping intervals must be prevented or resolved.

### Exercise 9. Are Gaps Zero?

**Prompt:** A series has 25.2 at 08:00 and 25.4 at 08:01, with no row at 08:02. Should reports automatically fill 0?

**Solution hint:** No, unless a domain rule states **missing means zero**. This is a gap. Keep `NULL`, flag missing data, or apply a clearly labeled interpolation method.

### Exercise 10. Does Window Size Belong in the Key?

**Prompt:** One series has both `AVG_1M` and `AVG_5M` labeled with timestamp 08:05. Is `(series_id, timestamp)` enough for an aggregate table?

**Solution hint:** No. Distinguish **window length, aggregation method**, and potentially `calculation_version`, or store them in separate series/tables with explicit grain.

### Exercise 11. Local Time and DST

**Prompt:** Two messages carry local time `01:30` on a DST fall-back day. If only local time is stored without offset or timezone rules, can the two instants be distinguished?

**Solution hint:** Not reliably. Store the offset or timezone plus disambiguation rules, then normalize to an instant for storage and comparison.

### Exercise 12. Which Index for Single-Series History?

**Prompt:** Queries always filter by `series_id` and an `observed_at` range with `ORDER BY observed_at DESC`. `PK(series_id, observed_at)` already exists. Is an additional `DESC` index definitely needed?

**Solution hint:** No. The existing multi-column B-tree can scan backward within a series. Inspect **`EXPLAIN (ANALYZE, BUFFERS)`** before adding a redundant index.

### Exercise 13. Multi-Tenancy

**Prompt:** Tenants 1 and 2 both have `device_id = 101`. Does a `Series` table with only `FK(device_id)` to `Device` guarantee same-tenant integrity?

**Solution hint:** No. Use a composite **`(tenant_id, device_id)`** key and composite FK, or globally unique device IDs paired with explicit tenant constraints.

### Exercise 14. Re-Ingesting the Same `source_event_id`

**Prompt:** One sample is delivered three times. If each arrival generates a new auto-increment `sample_id`, what happens?

**Solution hint:** It creates three bogus measurements, skewing `COUNT` and `AVG`. Identify **the same source event** with a stable key, deduplicate with payload checks, and handle revisions separately.

### Exercise 15. Changing Timestamps Due to Clock Correction

**Prompt:** A source updates a sample's `observed_at` from `08:00:00` to `07:59:59.950` after detecting clock drift. Why does updating just the timestamp column require extra care?

**Solution hint:** `observed_at` is part of the **observation key** in the current model. Changing it can collide with existing keys, shift reporting buckets, and break references or history. Use a stable `source_sample_id` and a verified correction/restatement workflow.

## 19. Key Takeaways

- **Series keys** are built from dimensions that make two observation streams semantically distinct: subject, metric, channel, method, and tenant scope where applicable.
- **Measurement keys** are typically **series + instant**, which holds only when at most one valid observation exists per series at an instant. If multiple real samples occur, use `source_sample_id`/sequence or a different grain.
- **Timestamp is not full identity.** Distinguish `observed_at`, `received_at`, event/valid time, window timestamps, and timezones.
- **Metric kind governs math:** gauges, counters, deltas, states, and aggregates cannot be summed or averaged interchangeably.
- **Time-varying dimensions** must be joined as of `observed_at`, not blindly against current device attributes.
- **Late arrivals, retries, and revisions** require stable source identifiers, upsert/dedup policies, versioning, and reconciliation.
- **Series cardinality and physical layout** drive scalability: avoid high-churn tags and benchmark indexes, partitions, and retention on representative loads.
- **Missing differs from zero, sample averages differ from interval aggregates, and observed time differs from ingestion time.** Losing these distinctions produces schemas that are syntactically valid yet analytically wrong.

A trustworthy time-series model stores more than **timestamp + value**. It lets you answer with certainty: **which subject does this measurement belong to, which quantity and method produced it, at which instant or interval, whether it is an original or a revision, and whether it can validly be aggregated with other measurements?**
