# Designing `timeField`, `metaField`, and `granularity` in MongoDB Time Series

## 1. Problem Statement and Learning Objectives

Time series data is a collection of measurements or events attached to timestamps: temperature every 5 minutes, CPU usage every second, electricity consumption every hour, trade prices, API request counts, or device location telemetry.

A measurement typically has three components:

- **Measurement time:** when the event actually occurred.
- **Measurement source:** sensor, device, tenant, region, or metric type.
- **Values:** temperature, humidity, power consumption, latency, request count.

MongoDB time series collections optimize storage in **buckets**, suited to measurements inserted sequentially and queried by series + time range.

This lesson belongs to the **Time Series Data** chapter of the **Database Engine Document MongoDB** module, focusing on **Designing `timeField`, `metaField`, and `granularity`**.

After this lesson, you will be able to:

1. Choose a `timeField` with the BSON Date type and accurate business time semantics.
2. Distinguish event time from ingestion time, and handle UTC, late events, and clock skew.
3. Design a stable `metaField` to identify series and optimize bucketing efficiency.
4. Understand metadata cardinality, bucket fragmentation, field order, and object-shaped metadata.
5. Choose `granularity` based on the **per-series** measurement cadence, not total insert rate.
6. Distinguish bucket span from timestamp rounding and aggregation time bins.
7. Use custom bucketing (`bucketMaxSpanSeconds`/`bucketRoundingSeconds`) starting in MongoDB 6.3.
8. Create a time series collection, insert, filter, aggregate, and inspect metadata and indexes.
9. Understand limitations around TTL, unique indexes, updates, sharding, and transactions.
10. Write MongoDB Java Sync Driver examples and construct a practical checklist.

**Key takeaway:** `timeField` defines the time axis, `metaField` identifies which series a measurement belongs to, and `granularity` guides the time span a bucket can cover. All three choices must follow actual measurement cadence, metadata structure, and query patterns.

## 2. Structure of a Time Series Document

A temperature measurement document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: {
    tenantId: "tenant-A",
    sensorId: "sensor-001",
    siteId: "warehouse-HCM",
    metricType: "temperature"
  },
  temperatureC: 27.4,
  humidityPct: 69.2,
  batteryPct: 91
}
~~~

Field roles:

| Field | Role | Notes |
|---|---|---|
| `measuredAt` | `timeField` | BSON Date, required |
| `meta` | `metaField` | Relatively stable attributes identifying the measurement source |
| `temperatureC` | measurement | Varies on each reading |
| `humidityPct` | measurement | Varies on each reading |
| `batteryPct` | measurement | May fluctuate; avoid putting in `meta` by default |
| `receivedAt` (if present) | event/measurement metadata | Server receipt time, distinct from event time |
| `eventId` (if present) | event identifier | Used for ingestion deduplication; time series has no unique indexes |

Create the collection:

~~~javascript
db.createCollection("sensorMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

`timeField` and `metaField` are **option names**, while `measuredAt` and `meta` are **document field names**.

## 3. MongoDB's Bucketing Mechanism

Instead of storing time series data in randomly scattered documents, MongoDB groups measurements into **buckets** by shared metadata and nearby timestamps.

~~~text
Document ingest
      |
      +--> meta = sensor-001
      |        |
      |        +--> bucket for time window A
      |        |
      |        +--> bucket for time window B
      |
      +--> meta = sensor-002
               |
               +--> bucket for time window A
~~~

Two measurements can share a bucket only if:

- They have equivalent `metaField` values under bucketing rules.
- Their timestamps fall within the bucket's allowed time span.
- The bucket has not reached its document count or byte limits.
- The bucket remains eligible given server buffer/cache state.

Example:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.0
}

{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}

{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S2" },
  temperatureC: 24.0
}
~~~

The two S1 documents share identical metadata and close timestamps, so they **can** be grouped in one bucket. S2 has different metadata and therefore belongs to a separate group of buckets.

### 3.1. Physical Bucket Limits

Per MongoDB documentation, a bucket holds at most roughly **1,000 measurements or 125 KB**, whichever is reached first. The server may also close a bucket earlier due to memory, cache, or other internal conditions.

Therefore:

- `granularity: "hours"` does not mean all measurements across 30 days fit in a single bucket.
- You cannot compute exact bucket counts with "hours divided by granularity".
- A high-volume series can produce many buckets within the same time window.
- A sparse series with only a few measurements can create many sparsely populated buckets.

### 3.2. Why Bucketing Improves Compression

Measurements in the same series typically repeat field names, metadata, and data types. Grouping readings into buckets helps MongoDB optimize storage, indexing, and compression.

Compression works well when:

- Metadata changes rarely.
- Measurements for the same series arrive regularly.
- Field names and types remain relatively stable.
- Data arrives roughly in chronological order.

Compression suffers when:

- Metadata changes on every request.
- There are many series that each emit only a single measurement.
- Data arrives very late or heavily out of order.
- Measurement documents fluctuate wildly in size and schema.

### 3.3. Never Modify the `system.buckets` Namespace Directly

The time series collection is the user-facing interface. MongoDB stores buckets in related internal namespaces. Applications should insert/find/aggregate on the **time series collection**, never write directly to `system.buckets.*`.

## 4. Required `timeField` and BSON Date Type

`timeField` specifies the top-level field holding the measurement timestamp. Every document must provide a valid **BSON Date** value in this field.

Create collection:

~~~javascript
db.createCollection("voltageSamples", {
  timeseries: {
    timeField: "observedAt",
    metaField: "source",
    granularity: "seconds"
  }
});
~~~

Valid document:

~~~javascript
db.voltageSamples.insertOne({
  observedAt: ISODate("2026-11-14T08:30:00Z"),
  source: { deviceId: "D1" },
  voltage: 220.5
});
~~~

Data types **not** to use:

~~~javascript
// Not a BSON Date.
{
  observedAt: "2026-11-14T08:30:00Z",
  source: { deviceId: "D1" },
  voltage: 220.5
}

// Epoch milliseconds as a Number, not a BSON Date.
{
  observedAt: 1794645000000,
  source: { deviceId: "D1" },
  voltage: 220.5
}

// Missing timeField.
{
  source: { deviceId: "D1" },
  voltage: 220.5
}
~~~

**Do not confuse BSON Timestamp with BSON Date.** The `Timestamp(...)` type serves internal purposes such as replication; `timeField` requires BSON Date.

### 4.1. Event Time vs. Ingestion Time

A sensor sending delayed data might produce:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  receivedAt: ISODate("2026-11-14T08:07:12Z"),
  meta: { sensorId: "S1" },
  temperatureC: 27.1
}
~~~

- `measuredAt`: when the sensor **actually measured**.
- `receivedAt`: when the server **received the message**.

If users need a temperature chart by actual measurement time, pick `measuredAt` as `timeField`. If analyzing message-processing SLA latency, `receivedAt` may be suitable for a separate collection or workload.

**Never replace event time with ingestion time just to avoid late events** if doing so corrupts business data.

### 4.2. Out-of-Order Data and Backfills

A gateway offline for 15 minutes that later sends older measurements may encounter closed or incompatible buckets. MongoDB can still insert valid historical timestamps, though doing so may open more buckets or increase write cost.

To handle this:

1. Store the true event time.
2. Also store `receivedAt` when tracking latency is needed.
3. Distinguish delayed measurements from corrupted timestamps.
4. When batching historical data, sort by series/time if SLA permits.
5. Monitor compression efficiency and bucket density under real late-arrival rates.

### 4.3. UTC and Timezones

BSON Date stores an absolute point in time. In `mongosh`, it can be written in ISO UTC:

~~~javascript
ISODate("2026-11-14T08:30:00Z")
~~~

This corresponds to **15:30** on November 14, 2026 in Vietnam (UTC+7).

Do not add 7 hours and store the shifted value as UTC; that introduces a double-timezone bug.

To report by calendar day in Vietnam:

~~~javascript
db.sensorMeasurements.aggregate([
  {
    $project: {
      localDay: {
        $dateToString: {
          date: "$measuredAt",
          timezone: "Asia/Ho_Chi_Minh",
          format: "%Y-%m-%d"
        }
      },
      temperatureC: 1
    }
  }
]);
~~~

Display or reporting timezone is separate from choosing `timeField`. One collection can store UTC while analyzing per site's local timezone.

### 4.4. Precision

BSON Date has **millisecond** precision. If a source produces microseconds or nanoseconds, add an explicit sub-millisecond precision or sequence field rather than turning `timeField` into a Number.

### 4.5. Clock Skew

A sensor with a misconfigured clock may send timestamps far in the future or far in the past. Consequences:

- Data lands in unexpected time ranges.
- TTL behaves unexpectedly.
- Bucket grouping fragments.
- Reports misorder events.

Validate reasonable timestamp bounds at ingestion, quarantine invalid records, and retain `receivedAt` for auditing.

## 5. Choosing `timeField` Name and Position

Clear, descriptive names include:

~~~text
measuredAt
observedAt
eventTime
recordedAt
~~~

Avoid ambiguous `date` when documents carry multiple timestamps.

Good structure:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}
~~~

Filter:

~~~javascript
db.sensorMeasurements.find({
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
});
~~~

### 5.1. `timeField` Cannot Be Renamed After Creation

`timeField` is fixed at collection creation. You cannot switch `measuredAt` to `receivedAt` via a standard `collMod`.

If you need to change it:

1. Create a new time series collection with the proper configuration.
2. Copy/backfill data with the required timestamp transformation.
3. Build indexes and configure retention on the new collection.
4. Reconcile counts, time ranges, and spot checks.
5. Cut over application reads/writes via a safe runbook.
6. Drop old data only after verification and with a rollback plan in place.

## 6. `metaField`: Measurement Source and Stable Attributes

`metaField` is optional, yet critical for bucketing efficiency.

~~~javascript
db.createCollection("weatherMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

Document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: {
    tenantId: "tenant-A",
    sensorId: "S1",
    siteId: "plant-01",
    metricType: "temperature"
  },
  value: 26.4
}
~~~

Metadata describes **which series**, not the value measured at a given instant.

### 6.1. What Belongs in `meta`?

- `sensorId`, `deviceId`, `meterId`.
- `tenantId` in multi-tenant systems.
- `siteId` or `plantId` if rarely changed and commonly filtered.
- `metricType` if the collection stores multiple metric types.
- Stable tags aligned with query predicates.

Reasonable example:

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

### 6.2. What Does Not Belong in `meta`?

- `temperatureC`, `humidityPct`, `voltage`.
- Frequently changing `batteryPct` or `signalRssi`.
- `measuredAt` or `receivedAt`.
- `requestId`, `eventId`, or per-submission `traceId`.
- Monotonically increasing sequence numbers per measurement.
- Continuously changing status fields.

Poor example:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    sensorId: "S1",
    requestId: "req-000001",
    batteryPct: 91
  },
  temperatureC: 26.0
}
~~~

On the next reading, a different `requestId` or `batteryPct` creates a different metadata combination. MongoDB cannot reuse the existing open bucket for S1 even though it belongs to the same physical sensor.

### 6.3. Why Stable Metadata Reduces Bucket Fragmentation

Suppose 100 sensors each record 100 measurements:

~~~text
Metadata = {sensorId}
   => ~100 series, each with many measurements.

Metadata = {sensorId, requestId}
   => nearly 10,000 metadata combinations, many sparse buckets.
~~~

Exact bucket counts vary by server version and physical limits, but the architectural effect is clear: dynamic metadata multiplies group counts rapidly.

### 6.4. `metaField` Can Be an Object

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1"
}
~~~

It can hold subfields rather than just a single string.

### 6.5. `metaField` Cannot Be `_id` or Equal to `timeField`

Invalid:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "measuredAt"
}
~~~

or:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "_id"
}
~~~

### 6.6. `metaField` Can Be Omitted

~~~javascript
db.createCollection("systemWideReadings", {
  timeseries: {
    timeField: "measuredAt",
    granularity: "seconds"
  }
});
~~~

Without `metaField`, bucketing is purely time-based. This may fit a single global series, but is usually suboptimal when thousands of sources must be queried individually.

## 7. Cardinality and `metaField` Trade-Offs

**Cardinality** is the number of distinct metadata values.

Consider two factors:

- **Total** distinct series.
- **Concurrently active** series.

For instance, 50,000 sensors where only 500 transmit continuously exhibit different bucketing behavior from 50,000 sensors transmitting simultaneously.

### 7.1. Meta Too Granular

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  sampleId: "unique-every-time"
}
~~~

Creates a new series per sample, causing many sparse buckets and poor compression.

### 7.2. Meta Too Coarse

~~~javascript
meta: {
  tenantId: "tenant-A"
},
sensorId: "S1"
~~~

All sensors for `tenant-A` share the same `meta`. If dashboards frequently query a single sensor, the server must inspect many measurements belonging to other sensors in those buckets.

### 7.3. Balanced Meta

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

Identifies the source while aligning with tenant/sensor/metric filters.

### 7.4. Should Location Be in `meta`?

If a sensor stays in one room permanently, `roomId` can live in metadata.

If sensors move frequently:

- Putting `roomId` in `meta` splits the series along its location history.
- Keeping `roomId` on the measurement preserves a continuous per-sensor series, though room-based queries require different handling.
- Storing room-assignment history in a `devices` registry is another option.

Decide based on series semantics and product queries; there is no universal rule.

### 7.5. Avoid Unnecessary Sensitive Fields

Do not repeat access tokens, passwords, or unnecessary PII inside metadata across millions of measurements. Metadata should hold identifiers/labels needed for grouping, filtering, and data security.

## 8. Object Metadata, Field Order, and Consistency

A metadata object:

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

should keep consistent structure and types across all writers.

### 8.1. Data Types Matter

Two examples:

~~~javascript
meta: { sensorId: 101 }
~~~

and:

~~~javascript
meta: { sensorId: "101" }
~~~

have different BSON types and can produce two distinct metadata values.

### 8.2. Query Subfields Instead of the Whole Object

Although MongoDB normalizes metadata during bucketing, BSON object equality in queries can depend on field order.

Instead of:

~~~javascript
db.weatherMeasurements.find({
  meta: {
    sensorId: "S1",
    tenantId: "tenant-A"
  }
});
~~~

prefer:

~~~javascript
db.weatherMeasurements.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1"
});
~~~

This avoids coupling to subfield order and count, and aligns cleanly with indexes.

### 8.3. Avoid Arrays in Metadata

~~~javascript
meta: {
  tags: ["warehouse", "hot"]
}
~~~

and:

~~~javascript
meta: {
  tags: ["hot", "warehouse"]
}
~~~

are arrays with different element ordering. Placing mutable tag arrays in `meta` can create unexpected series groups.

### 8.4. You Can Add Subfields, Not Rename `metaField`

After creating a collection with `metaField: "meta"`, new documents may include an additional `meta.floor` subfield if your schema allows. However, you cannot alter the collection option to `metaField: "labels"`.

Fundamental metadata schema changes require a migration plan.

## 9. `granularity`: `seconds`, `minutes`, and `hours`

`granularity` describes data cadence and helps MongoDB select the bucket interval.

Valid values:

~~~text
seconds
minutes
hours
~~~

The default is `seconds`.

| `granularity` | Maximum bucket span | Illustrative workload |
|---|---:|---|
| `seconds` | **1 hour** | Multiple readings per second or every few seconds |
| `minutes` | **24 hours** | One reading every few minutes |
| `hours` | **30 days** | One reading per hour or less frequently |

**Do not misunderstand:** `granularity: "minutes"` does not round timestamps to the start of the minute. It defines the **bucketing time span** without losing Date precision.

### 9.1. Per-Series Cadence, Not Total Ingestion Rate

Suppose 10,000 sensors each send one measurement every 5 minutes. Total collection insert rate is substantial, yet the gap between consecutive points for any single `sensorId` remains 5 minutes.

`granularity: "minutes"` is usually better than picking `seconds` solely because aggregate insert rate is high.

### 9.2. Per-Second Cadence

~~~text
S1: 08:00:00, 08:00:01, 08:00:02, ...
~~~

Choose `seconds`. Buckets have a 1-hour max span, though under dense workloads they may hit document/byte limits sooner.

### 9.3. Every-5-Minutes Cadence

~~~text
S1: 08:00, 08:05, 08:10, 08:15, ...
~~~

Choose `minutes`. Buckets have a 24-hour max span and may close earlier.

### 9.4. Every-6-Hours Cadence

~~~text
S1: 00:00, 06:00, 12:00, 18:00, ...
~~~

You can choose `hours`, especially when queries typically scan weeks or months.

### 9.5. Look Beyond Write Frequency Alone

Evaluate concurrently:

- Interval between measurements **with identical `meta`**.
- Whether queries typically fetch 10 minutes, 1 day, or 1 month.
- Size of a single measurement.
- Number of active series.
- Late/out-of-order data.
- How precise TTL/retention must be.
- Cache, index, storage, and query latency costs.

## 10. How `granularity` Affects Query Efficiency

A dashboard query fetching 5 minutes:

~~~javascript
db.weatherMeasurements.find({
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:05:00Z")
  }
});
~~~

If buckets span an overly wide window, the server may read buckets holding many measurements outside those 5 minutes and filter them out.

Conversely, a 30-day report over tiny buckets may need to scan a very large number of buckets.

~~~text
30-day range query

Small bucket span:
[ ][ ][ ][ ][ ][ ][ ] ... many bucket ranges

Well-matched bucket span:
[=====][=====][=====] ... fewer bucket ranges

Overly wide bucket span:
[==============================]
may over-read for many short queries
~~~

**Granularity is a trade-off**—no single setting is universally optimal.

### 10.1. Granularity Does Not Pre-Build Hourly Reports

Choosing `hours` does not mean MongoDB automatically calculates hourly averages. To group measurements into time bins, use aggregation operators such as `$dateTrunc` and `$group`.

### 10.2. Granularity Does Not Guarantee One Full Interval Per Bucket

Buckets have measurement-count and byte limits. At very high write rates, multiple buckets may be created within a single hour even with `granularity: "seconds"`.

## 11. Custom Bucketing Starting in MongoDB 6.3

From MongoDB 6.3 onward, you can replace `granularity` with two parameters:

- `bucketMaxSpanSeconds`: maximum time span between timestamps grouped in a bucket.
- `bucketRoundingSeconds`: step size used to round **bucket start times** when opening a new bucket.

**Both must be set to equal values** and cannot be combined with `granularity`.

### 11.1. 4-Hour Buckets

~~~javascript
db.createCollection("weather4h", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    bucketMaxSpanSeconds: 14400,
    bucketRoundingSeconds: 14400
  }
});
~~~

14,400 seconds = 4 hours. When opening a new bucket for:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T10:24:35Z"),
  meta: { sensorId: "S1" },
  temperatureC: 27
}
~~~

the bucket start time rounds down to **08:00 UTC**, aligning with 4-hour boundaries. The document retains `measuredAt: 10:24:35Z`; rounding **does not alter the user's timestamp**.

### 11.2. Custom 5-Minute Window

~~~javascript
db.createCollection("fiveMinuteMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    bucketMaxSpanSeconds: 300,
    bucketRoundingSeconds: 300
  }
});
~~~

300 seconds = 5 minutes. Worth testing when queries target fixed 5-minute blocks. Benchmark against `granularity: "minutes"` to verify actual gains.

### 11.3. Do Not Mix Both Mechanisms

Invalid:

~~~javascript
db.createCollection("invalidCombined", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes",
    bucketMaxSpanSeconds: 300,
    bucketRoundingSeconds: 300
  }
});
~~~

### 11.4. Parameter Bounds

Per MongoDB documentation, `bucketMaxSpanSeconds` allows values from **1 to 31,536,000 seconds**; `bucketRoundingSeconds` must equal the same value. Check server version/FCV, as older releases lack these parameters.

## 12. Can `granularity` Be Changed Later?

`timeField` and `metaField` names cannot be changed after collection creation. For granularity, MongoDB allows **increasing the bucket span**, not decreasing it, via `collMod` on supported versions.

Example increasing from `minutes` to `hours`:

~~~javascript
db.runCommand({
  collMod: "sensorMeasurements",
  timeseries: {
    granularity: "hours"
  }
});
~~~

You cannot decrease from `hours` to `minutes` or `minutes` to `seconds` via this mechanism.

### 12.1. Increasing the Custom Parameter Pair

~~~javascript
db.runCommand({
  collMod: "weather4h",
  timeseries: {
    bucketMaxSpanSeconds: 28800,
    bucketRoundingSeconds: 28800
  }
});
~~~

Example increasing from 4 hours to 8 hours. Both parameters must be passed with identical values.

### 12.2. Does Not Automatically Reorganize Existing Buckets

Changing granularity updates the bucketing definition/strategy; do not assume all historical buckets are rewritten as if into a fresh collection. To evaluate a new design across the full dataset, create a test collection, backfill, and compare.

### 12.3. Version Constraints

- Changing granularity after creation requires MongoDB 5.0.1 or later per documentation.
- Adjusting granularity on a **sharded** time series collection requires an appropriate version (MongoDB 6.0+ per docs).
- Custom bucketing in MongoDB 6.3+ carries downgrade/FCV considerations.

If `meta`/`time` design is wrong, you must create a new collection and migrate; `collMod` is not a catch-all fix for schema mistakes.

## 13. Creating Practice Data

Use a dedicated database:

~~~javascript
use time_series_design_lab
~~~

Create the collection in the fresh environment:

~~~javascript
db.createCollection("roomReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

Insert 8 sample documents:

~~~javascript
const samples = [
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.0,
    humidityPct: 61
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.4,
    humidityPct: 60
  },
  {
    measuredAt: ISODate("2026-11-14T08:10:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.8,
    humidityPct: 60
  },
  {
    measuredAt: ISODate("2026-11-14T08:15:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 27.1,
    humidityPct: 59
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 24.0,
    humidityPct: 66
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 24.5,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:10:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 25.0,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:15:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 25.5,
    humidityPct: 64
  }
];

db.roomReadings.insertMany(samples);
~~~

On a fresh/empty collection:

- There are **8 measurements**.
- S1 has 4 points, spaced 5 minutes apart.
- S2 has 4 points, also spaced 5 minutes apart.
- Each sensor has stable metadata.
- Each reading records both temperature and humidity.

**Note:** There is no unique index preventing duplicate timestamp inserts. Re-running `insertMany(samples)` inserts duplicate contents (with new IDs), so run it only once in the practice database or use a fresh database on retries.

### 13.1. Reading S1 Measurements

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1"
}).sort({ measuredAt: 1 });
~~~

Expected results are 08:00, 08:05, 08:10, and 08:15 UTC.

### 13.2. Reading a Half-Open Interval

~~~javascript
db.roomReadings.find({
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:05:00Z"),
    $lt: ISODate("2026-11-14T08:15:00Z")
  }
}).sort({ measuredAt: 1 });
~~~

Returns only 08:05 and 08:10. `$lt` excludes the upper bound 08:15, preventing double-counting across consecutive windows.

### 13.3. Query Without a Metadata Filter

~~~javascript
db.roomReadings.find({
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:10:00Z")
  }
});
~~~

This returns readings from both S1 and S2. On large workloads, omitting metadata filters can scan many more buckets and series.

## 14. Inspecting Created Configuration

~~~javascript
db.getCollectionInfos({
  name: "roomReadings"
});
~~~

Illustrative output:

~~~javascript
[
  {
    name: "roomReadings",
    type: "timeseries",
    options: {
      timeseries: {
        timeField: "measuredAt",
        metaField: "meta",
        granularity: "minutes"
      }
    }
  }
]
~~~

Actual output may contain extra fields or server-added parameters.

You can also use:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "roomReadings" }
});
~~~

Check:

- Is `type` equal to `"timeseries"`?
- Is `options.timeseries.timeField` correct?
- Is `options.timeseries.metaField` correct?
- Are `granularity` or custom options correct?
- What is `expireAfterSeconds`, if configured?

Do not infer collection type solely from seeing a `measuredAt` field in a document; regular collections can also contain Dates.

## 15. Indexes for `meta` and `time` Queries

Common pattern:

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
}).sort({ measuredAt: 1 });
~~~

Starting in **MongoDB 6.3**, newly created time series collections with a `metaField` automatically receive a default compound index involving `metaField` and `timeField`.

For specific queries, you can add an index:

~~~javascript
db.roomReadings.createIndex(
  {
    "meta.tenantId": 1,
    "meta.sensorId": 1,
    measuredAt: 1
  },
  {
    name: "idx_tenant_sensor_time"
  }
);
~~~

### 15.1. Equality on `meta`, Range on `time`

Equality predicates on `meta` narrow the series; the range predicate on `time` selects the required window. This is a consistently useful pattern.

### 15.2. `explain` and `getIndexes`

~~~javascript
db.roomReadings.getIndexes();
~~~

~~~javascript
db.roomReadings.explain("executionStats").find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
});
~~~

Execution plans may display bucket scan, index scan, and unpack stages depending on version and query engine. In production evaluations, examine scanned documents/buckets, latency, and index utilization.

### 15.3. Do Not Assume Every Index Is Needed

Indexes carry storage and write overhead. Add indexes only when query patterns and `explain` demonstrate clear value. A default `meta`+`time` index may already suffice for straightforward queries.

## 16. Aggregation Time Bins vs. Storage Buckets

Compute average temperature per sensor:

~~~javascript
db.roomReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "tenant-A",
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T09:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$meta.sensorId",
      n: { $sum: 1 },
      avgTemp: { $avg: "$temperatureC" },
      minTemp: { $min: "$temperatureC" },
      maxTemp: { $max: "$temperatureC" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

On the sample dataset:

| Sensor | n | Average | Min | Max |
|---|---:|---:|---:|---:|
| S1 | 4 | 26.575 | 26.0 | 27.1 |
| S2 | 4 | 24.75 | 24.0 | 25.5 |

### 16.1. Grouping into 5-Minute Bins

~~~javascript
db.roomReadings.aggregate([
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        fiveMinutes: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            binSize: 5,
            timezone: "UTC"
          }
        }
      },
      averageC: { $avg: "$temperatureC" },
      n: { $sum: 1 }
    }
  },
  { $sort: { "_id.sensorId": 1, "_id.fiveMinutes": 1 } }
]);
~~~

`$dateTrunc` builds **reporting bins**; it does not alter `granularity` or create new internal physical buckets.

### 16.2. Reporting by Vietnam Local Date

~~~javascript
db.roomReadings.aggregate([
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        day: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        }
      },
      avgTemp: { $avg: "$temperatureC" }
    }
  }
]);
~~~

Raw timestamps stay in UTC; grouping uses business timezone semantics.

## 17. TTL: Automatic Expiration of Time Series Data

A collection can configure retention:

~~~javascript
db.createCollection("sevenDayReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 604800
});
~~~

604,800 seconds equals 7 days.

### 17.1. TTL Operates by Bucket, Not Exact Second

MongoDB deletes time series data by **bucket** once all measurements in a bucket qualify for expiration. Deletion runs as a background process with inherent delay.

Therefore, a document whose `measuredAt + expireAfterSeconds` has elapsed can still exist until its bucket becomes eligible for removal.

### 17.2. `granularity` Affects Retention

If bucket spans are too wide relative to the retention period, older measurements may remain stored longer than desired.

For example, a workload reporting every few hours with a 7-day retention that chooses `granularity: "hours"` (up to 30-day span) must be evaluated carefully because wide buckets can delay deletion.

### 17.3. TTL Does Not Replace Data-Deletion Compliance

If legal requirements mandate exact-time erasure, verify how TTL behaves and add an approved retention/purge procedure; never claim TTL removes each measurement on the exact second of expiration.

### 17.4. Partial TTL by Metadata

Starting in MongoDB 7.0, partial TTL indexes based on `metaField` are supported for scenarios requiring distinct retention periods per metadata group. Specific rules depend on server version—check the documentation before adopting.

## 18. Other Limitations Compared to Regular Collections

| Aspect | Time series characteristics |
|---|---|
| `timeField` | Required; must be BSON Date |
| `metaField` | Optional; field name fixed after creation |
| `granularity` | Span can be increased; cannot be decreased |
| Unique indexes | Not supported |
| Default `_id` index | Not automatically created like on regular collections |
| Document size | Time series documents have dedicated limits (4 MB per current Manual) |
| Updates | Restricted; primarily matching/modifying `metaField` under supported conditions |
| Transaction writes | Writing to time series collections in multi-document transactions is not supported |
| Collection type | Cannot directly convert a regular collection into a time series collection |
| Schema validation | Certain validation features are unsupported |
| Change streams | Not supported on time series collections per current Manual |
| Capped | Cannot create capped time series collections |

Verify current policies and version documentation before relying on advanced features.

### 18.1. Why Is There No Unique Index on `(sensor, time)`?

Time series collections do not support unique indexes. If a reading is sent twice, you cannot rely on:

~~~javascript
// Not supported on time series collections.
db.roomReadings.createIndex(
  { "meta.sensorId": 1, measuredAt: 1 },
  { unique: true }
);
~~~

To prevent duplicates:

- Maintain an idempotency registry in a regular collection with a unique key.
- Deduplicate upstream by event ID in the ingestion pipeline.
- Design retry protocols to preserve identical request IDs.
- Or write aggregations tolerant of duplicates if business rules permit.

**Never assume default `_id` is unique**, because time series collections do not create a default unique `_id_` index like regular collections.

### 18.2. Do Not Use Time Series for Frequently Updated Data

If documents represent mutable current state that changes frequently, a regular collection is more suitable. Time series fits mostly append-only measurement history.

### 18.3. Separating the Device Registry

A clean model separates:

~~~text
devices (regular collection)
  _id, tenantId, model, owner, currentStatus

roomReadings (time series)
  measuredAt, meta, temperatureC, humidityPct
~~~

Current device state lives in `devices`; historical measurements live in the time series collection.

## 19. Time Series and Multi-Tenant Systems

Reasonable metadata:

~~~javascript
meta: {
  tenantId: "tenant-A",
  plantId: "plant-01",
  sensorId: "S1"
}
~~~

Query:

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.plantId": "plant-01",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});
~~~

### 19.1. Metadata Does Not Enforce Authorization

The application tier must derive `tenantId` from the authenticated session/token and inject the filter. Unique keys, indexes, and grouping do not prevent cross-tenant access on their own.

### 19.2. Sensors Moving Between Tenants or Sites

If a sensor transfers from `tenant-A` to `tenant-B` on the 14th, prior data may need to retain `tenant-A` metadata to preserve historical ownership.

Do not rewrite all historical measurements to the new owner if doing so invalidates historical reports.

### 19.3. Global `sensorId` vs. Tenant-Scoped `sensorId`

If `sensorId` is unique only within a tenant, `meta: { tenantId, sensorId }` is a sound series ID. If `sensorId` is globally unique, `sensorId` alone can serve as the series ID while keeping `tenantId` for authorization, though you should still evaluate query and bucket cardinality costs.

## 20. Sharding Time Series Collections

Time series collections can be sharded subject to server/version limits.

Shard keys are commonly built from:

- `metaField`.
- Subfields of `metaField`.
- `timeField` under version constraints, though using `timeField` in a time series shard key is **deprecated** starting in MongoDB 8.0.

Metadata-based examples:

~~~javascript
{ "meta.sensorId": "hashed" }
~~~

or:

~~~javascript
{ "meta.tenantId": 1, "meta.sensorId": 1 }
~~~

### 20.1. Why Not Shard Solely by `timeField`?

Timestamps generally increase monotonically. A range shard key on `timeField` alone directs all new writes to a single chunk/shard, creating a write hotspot.

### 20.2. Very Low Metadata Cardinality

Sharding by `tenantId` when there are only two tenants—with one huge tenant—produces imbalanced distribution. Consider subfields like `sensorId` and query patterns.

### 20.3. Sharding Does Not Fix a Bad `metaField`

If `meta` contains a fresh `requestId` on every insert, adding shards will not stabilize series. Bucket fragmentation remains.

### 20.4. Version-Conditional Resharding

MongoDB 8.0.10+ adds support for resharding time series collections under certain conditions; do not blindly apply regular-collection runbooks across all versions.

## 21. Three Real-World Design Scenarios

### Scenario A — Per-Second Temperature

- Each sensor sends 1 measurement/second.
- Dashboard queries the last 15 minutes.
- Stable `meta` with `tenantId`, `sensorId`, and `metricType`.

Recommendation:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "meta",
  granularity: "seconds"
}
~~~

### Scenario B — Smart Meters Every 5 Minutes

- Each meter sends 1 measurement every 5 minutes.
- Hourly/daily reporting.
- `meta` contains `tenantId` and `meterId`.

Recommendation:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "meter",
  granularity: "minutes"
}
~~~

Starting in MongoDB 6.3, you can test custom `300/300` if fixed 5-minute bucket windows benefit your queries.

### Scenario C — KPIs Every 6 Hours

- A service/metric emits 1 measurement every 6 hours.
- Weekly/quarterly reporting.
- `hours` is viable if TTL/query ranges raise no issues.

Avoid `hours` if retention is very short and tight expiration precision is expected without accounting for bucket TTL semantics.

### 21.1. Should All Metrics Share One Collection?

If metrics differ markedly in cadence, retention, schema, and query patterns, separate collections are often easier to tune than one shared `granularity`.

## 22. Out-of-Order Data and Backfills

~~~text
S1 measuredAt = 08:00 -> ingested 08:00
S1 measuredAt = 08:10 -> ingested 08:10
S1 measuredAt = 08:05 -> ingested 08:30 (late arrival)
~~~

Late events should keep `measuredAt = 08:05` if that is the true event time.

### 22.1. Storing `receivedAt` to Monitor Delay

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  receivedAt: ISODate("2026-11-14T08:30:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}
~~~

Lag calculation:

~~~javascript
db.roomReadings.aggregate([
  { $match: { receivedAt: { $type: "date" } } },
  {
    $project: {
      sensorId: "$meta.sensorId",
      lagMs: {
        $subtract: ["$receivedAt", "$measuredAt"]
      }
    }
  }
]);
~~~

The sample dataset in Section 13 lacks `receivedAt`; run this pipeline only on data containing that field.

### 22.2. Backfills May Create Extra Buckets

Loading historical data in random order can increase bucketing overhead. On large datasets, evaluate sorting by series/time prior to bulk insertion, provided latency requirements allow.

## 23. Measuring Performance, Compression, and Bucket Density

You cannot pick `granularity` purely on theory. Test candidate configurations against a representative workload.

### 23.1. Metrics to Track

- Total measurement count.
- Distinct `meta` value count.
- Concurrently active series count.
- Measurements per series per hour.
- Average measurement size.
- Late-event percentage.
- Total storage and index sizes.
- Query p50/p95/p99 latency.
- Insert throughput and ingest latency.
- CPU/RAM/I/O and WiredTiger cache pressure.
- TTL efficiency and retention accuracy.

### 23.2. Testing Multiple Configurations

Create three otherwise identical test collections differing only in bucket policy:

~~~text
roomReadingsSeconds
roomReadingsMinutes
roomReadingsCustom300
~~~

Load the same representative dataset into each, create equivalent indexes, and compare:

- 15-minute per-sensor query.
- 1-day per-sensor query.
- 30-day per-tenant query.
- Average by `metricType` query.
- Data arriving 1 hour late.
- High-cardinality metadata data.

### 23.3. Look Beyond Total Document Count

Two systems each holding 10 million measurements:

~~~text
System A: 100 sensors, 100,000 measurements per sensor.
System B: 10 million sensor IDs, 1 measurement per sensor.
~~~

Bucket density differs dramatically. System A compresses well, while System B creates massive metadata overhead and sparse buckets.

### 23.4. Benchmark on Your Target Server Version

MongoDB evolves bucketing, compression, query optimization, and defaults across releases. Optimal behavior on MongoDB 6.x does not automatically match MongoDB 8.x/9.x.

## 24. Java Sync Driver: Creating a Time Series Collection

The MongoDB Java Sync Driver provides `TimeSeriesOptions` and `CreateCollectionOptions`.

Example assuming `client` is an already-connected `MongoClient`:

~~~java
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;

MongoDatabase database =
    client.getDatabase("time_series_design_lab");

TimeSeriesOptions tsOptions =
    new TimeSeriesOptions("measuredAt")
        .metaField("meta")
        .granularity(TimeSeriesGranularity.MINUTES);

CreateCollectionOptions options =
    new CreateCollectionOptions()
        .timeSeriesOptions(tsOptions);

database.createCollection("roomReadingsJava", options);
~~~

Collection creation requires a compatible MongoDB Server/FCV and driver; do not re-run if the collection already exists.

### 24.1. Inserting a Measurement from Java

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.Date;

MongoCollection<Document> readings =
    database.getCollection("roomReadingsJava");

Document meta = new Document("tenantId", "tenant-A")
    .append("sensorId", "S1")
    .append("roomId", "101");

Document measurement = new Document("measuredAt", new Date())
    .append("meta", meta)
    .append("temperatureC", 26.4)
    .append("humidityPct", 60);

readings.insertOne(measurement);
~~~

`java.util.Date` serializes to BSON Date. If your application uses `Instant`, ensure an appropriate codec/mapping so the field is stored as BSON Date.

### 24.2. Querying Metadata and Time Range

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Sorts.ascending;

import java.time.Instant;
import java.util.Date;

Date from = Date.from(
    Instant.parse("2026-11-14T08:00:00Z")
);

Date to = Date.from(
    Instant.parse("2026-11-14T09:00:00Z")
);

for (Document item : readings.find(
        and(
            eq("meta.tenantId", "tenant-A"),
            eq("meta.sensorId", "S1"),
            gte("measuredAt", from),
            lt("measuredAt", to)
        )
    ).sort(ascending("measuredAt"))) {

    System.out.println(item.toJson());
}
~~~

### 24.3. Custom Bucketing API Depends on Driver Version

Driver versions differ in the methods exposed for setting custom bucketing parameters. If your version lacks a dedicated helper method, pass a supported BSON Document command to create the collection or upgrade the driver per official docs—never guess method names.

### 24.4. Do Not Create a Unique Index on `sensor + time`

Time series collections do not support unique indexes. Your Java application must enforce deduplication separately if strict uniqueness is required.

## 25. MongoDB Compass

Compass can create and query time series collections, though option placement and availability vary by Compass version.

Practice workflow:

1. Connect to a MongoDB Server supporting time series.
2. Open the `time_series_design_lab` database.
3. Create a new collection and select **Time Series** if supported by the UI.
4. Set `timeField` to `measuredAt`, `metaField` to `meta`, and `granularity` to `minutes`.
5. If the UI does not expose all options, run `db.createCollection` in `mongosh`.
6. Browse documents and filter on `meta.sensorId`.
7. Run an aggregation by day/hour.
8. Inspect indexes and options via `mongosh`.
9. Never edit internal bucket storage directly.
10. Cross-check UI views against actual data on your running version.

## 26. Common Errors and Misconceptions

| Misconception | Reality |
|---|---|
| "Granularity minutes rounds `measuredAt` to the minute" | It affects bucket span without losing timestamp precision |
| "Minutes means each bucket is exactly 1 minute long" | Maximum span is 24 hours |
| "Hours means all 30 days of measurements sit in one bucket" | Buckets still have count/byte limits and can close early |
| "Pick granularity from total inserts/sec" | Pick based on **per-series** cadence |
| "More metadata is always better" | Dynamic metadata increases cardinality and bucket fragmentation |
| "`batteryPct` belongs in `meta`" | It is typically a changing measurement |
| "`timeField` can be an ISO string" | Must be a BSON Date |
| "Epoch millis Number is a Date" | No; construct a BSON Date |
| "Late events cannot be ingested" | They can, though they affect bucketing and write performance |
| "`timeField` is always `receivedAt`" | Base it on business event time |
| "Change `metaField` with `collMod`" | Configuration field names cannot be renamed after creation |
| "Decrease granularity hours -> seconds" | Not permitted via `collMod` |
| "Custom 300 can be combined with `minutes`" | Must pick one mechanism |
| "TTL deletes individual points at exact expiration" | Deletes by bucket via background monitor |
| "Time series has unique `_id` like regular collections" | Does not create a default `_id` index like regular collections |
| "Unique `sensor+timestamp` index is supported" | Unique indexes are not supported |
| "Transaction writes to time series work normally" | Write transactions are not supported |
| "Hourly aggregation comes automatically from `granularity: hours`" | Aggregation bins come from `$dateTrunc`/`$group` |
| "Sharding by `timeField` is always good" | Causes write hotspots; deprecated for time series since MongoDB 8.0 |
| "Buckets eliminate the need for indexes" | `meta`/`time` indexes remain important |
| "All metrics belong in one collection" | Depends on cadence, schema, retention, and queries |
| "Clock-skewed data is auto-corrected by the server" | Requires validation/quarantine at ingest |

## 27. Practice Exercises

Exercises use the dataset from Section 13; do not re-run `insertMany` on the existing collection if you want expected outputs.

### Exercise 1 — Identify the Three Field Groups

In this document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { tenantId: "A", sensorId: "S1" },
  temperatureC: 26.1,
  batteryPct: 87
}
~~~

Which fields are time, meta, and measurement? Why should `batteryPct` not go into `meta`?

### Exercise 2 — Check Date Types

~~~javascript
{ measuredAt: "2026-11-14T08:00:00Z" }
{ measuredAt: ISODate("2026-11-14T08:00:00Z") }
{ measuredAt: 1794643200000 }
{ measuredAt: Timestamp(1760000000, 1) }
~~~

**Answer:** Only the BSON Date `ISODate(...)` value is valid for `timeField`.

### Exercise 3 — 5-Minute Cadence Per Sensor

10,000 sensors each send 1 measurement every 5 minutes. Should `granularity` be chosen from total insert rate or per-sensor spacing? Choose `seconds`, `minutes`, or `hours`?

### Exercise 4 — Bucket Span

Fill in the maximum spans:

| `granularity` | Span |
|---|---|
| `seconds` | ? |
| `minutes` | ? |
| `hours` | ? |

**Answer:** 1 hour, 24 hours, 30 days.

### Exercise 5 — Two Sensors at the Same Timestamp

S1 and S2 measure at exactly 08:05. If `meta.sensorId` differs, do both measurements land in the same bucket? Why or why not?

### Exercise 6 — Dynamic Metadata

~~~javascript
meta: { sensorId: "S1", requestId: "R001" }
meta: { sensorId: "S1", requestId: "R002" }
~~~

Explain why this schema creates sparse buckets; propose an improved design.

### Exercise 7 — Query Interval

Write a query for S1 from 08:05 up to before 08:15 UTC. **Expected:** two measurements, 08:05 and 08:10.

### Exercise 8 — Average

Write an aggregation computing average temperature per sensor. **Expected:** S1=26.575 and S2=24.75.

### Exercise 9 — `$dateTrunc`

Use `$dateTrunc` with 5-minute bins. Does it change physical bucket storage or only generate reporting bins?

### Exercise 10 — Custom 4-Hour Buckets

Write `createCollection` using `bucketMaxSpanSeconds: 14400` and `bucketRoundingSeconds: 14400`. What start timestamp can a reading at `10:24:35Z` round down to for its bucket?

### Exercise 11 — Inspect Configuration

Run:

~~~javascript
db.getCollectionInfos({ name: "roomReadings" });
~~~

Read `timeField`, `metaField`, and `granularity`.

### Exercise 12 — Which Options Can Change?

- `minutes` -> `hours`?
- `hours` -> `minutes`?
- `timeField: measuredAt` -> `receivedAt`?
- `metaField: meta` -> `source`?

Explain which can use `collMod` and which require a new collection.

### Exercise 13 — TTL

A collection has `expireAfterSeconds: 604800`. Why might readings older than 7 days not be deleted immediately?

### Exercise 14 — Event Time

A sensor reads at 08:05, but the server receives it at 08:40. When charting temperature trends, should `timeField` store 08:05 or 08:40?

### Exercise 15 — Multi-Tenant

Design `meta` for 100 tenants, each with 1,000 sensors. Which `meta` filters should queries include for both security and accurate series selection?

### Exercise 16 — Unique Sensor/Time

Why can you not create a unique index on `{"meta.sensorId": 1, measuredAt: 1}` in a time series collection? Propose an external idempotency mechanism.

### Exercise 17 — Sharding

Why can a shard key consisting solely of `measuredAt` cause a hotspot? Why is `meta.sensorId` a better candidate in many workloads?

### Exercise 18 — Ingest Lag

Store both `measuredAt` and `receivedAt`, and compute the difference using `$subtract`. How do you detect a gateway with clock skew?

### Exercise 19 — Java Driver

Create `TimeSeriesOptions("measuredAt")`, set `metaField("meta")` and `MINUTES` granularity; insert a measurement using `new Date()`.

### Exercise 20 — Workload Comparison

Select schema and granularity for:

1. API latency every second, queried over 15 minutes.
2. Electric meters every 5 minutes, queried over 7 days.
3. Aggregated KPIs every 12 hours, queried per quarter.

Also explain retention, indexes, and metadata.

## 28. Step-by-Step Design Workflow

### Step 1 — Define What a Measurement Is

Is it a raw event or a 5-minute aggregate? Avoid mixing metrics with vastly different cadences or retentions if doing so complicates `granularity`.

### Step 2 — Choose Event Time

Does the timestamp represent when the reading occurred or when the system received it? If both are needed, store both separately.

### Step 3 — Define a Series

For example:

~~~text
tenantId + sensorId + metricType
~~~

These fields should stay stable across many measurements.

### Step 4 — Remove Dynamic Fields from `meta`

Keep `batteryPct`, `requestId`, measured values, and volatile status fields out of metadata.

### Step 5 — Measure Spacing Between Measurements in the Same Series

Do not use total inserts/sec as your sole proxy.

### Step 6 — Choose `granularity` and TTL

Use `seconds`/`minutes`/`hours` or 6.3+ custom options; weigh query intervals and retention.

### Step 7 — Design Indexes

Use `meta` equality + `time` range, inspect server version defaults, and run `explain`.

### Step 8 — Check Collection Limitations

If unique indexes, transactional writes, change streams, or frequent measurement edits are needed, reconsider collection type.

### Step 9 — Test with Representative Data

Measure read latency, storage, bucket density, and late events on a realistically sized dataset.

### Step 10 — Lock Schema Before Production

`timeField`/`metaField` cannot be changed after creation; mistakes require a migration plan.

## 29. Production Checklist

### Data Correctness

- [ ] `timeField` is required and contains a BSON Date in every measurement.
- [ ] Event time and ingest time are clearly separated when distinct.
- [ ] UTC/timezones are standardized.
- [ ] Clock skew and future timestamps are handled.
- [ ] `metaField` accurately represents the series.
- [ ] `requestId`, `batteryPct`, and measured values are kept out of `meta`.
- [ ] `meta` types and structure are consistent across all writers.
- [ ] Subfield filters are used instead of full-object `meta` equality where appropriate.
- [ ] Unnecessary sensitive data is not repeated in `meta`.
- [ ] Queries enforce tenant filters from authenticated credentials.

### Granularity and Operations

- [ ] `granularity` is based on per-meta cadence, not just total insert rate.
- [ ] Bucket spans of 1h / 24h / 30d are understood.
- [ ] Span is not confused with Date rounding or aggregation bins.
- [ ] 6.3+ custom pair values are equal and not mixed with `granularity`.
- [ ] Understood that `collMod` can only increase bucket span.
- [ ] Bucket-based TTL deletion semantics have been evaluated.
- [ ] Indexes cover `meta` equality and `time` range.
- [ ] Out-of-order and high-cardinality workloads have been measured.
- [ ] Storage, CPU/RAM/I/O, and latency monitoring are in place.
- [ ] Tested on the target MongoDB version/FCV.

### Limitations and Maintenance

- [ ] Not relying on unique indexes on time series collections.
- [ ] Not assuming a default `_id` unique index.
- [ ] Deduplication/idempotency exists for ingestion retries.
- [ ] Not writing to time series inside multi-document transactions.
- [ ] Never modifying internal buckets directly.
- [ ] Migration plan exists if `timeField`/`metaField` must change.
- [ ] Sharding, if used, follows supported fields and version rules.
- [ ] Considered separating a regular device registry from time series history.
- [ ] Staging load tests completed with representative data.

## 30. Summary

Designing a time series collection takes more than three lines of configuration.

- **`timeField`** must be a BSON Date matching business timing. Store event time consistently and keep ingestion time separate if needed.
- **`metaField`** serves as the series identifier; keep it stable and aligned with filters. Dynamic metadata proliferates sparse buckets.
- **`granularity`** is chosen from **per-series** cadence. `seconds`/`minutes`/`hours` correspond to maximum bucket spans of 1 hour, 24 hours, and 30 days—never measurement rounding.
- **Custom bucketing** from MongoDB 6.3 lets you specify exact bucket intervals via two equal parameters.
- **Post-creation changes** are constrained: `timeField`/`metaField` cannot be renamed, and `collMod` can only increase bucket span on supported versions.
- **Real queries** still require metadata filters, time ranges, proper indexes, and aggregation stages to group by 5-minute/hourly/daily bins.
- **Operations** must account for bucket-level TTL deletion, late events, cardinality, and time series collection limitations.

A well-designed schema gives measurements an accurate time axis and clear source identity, packs correlated readings into efficient buckets, and keeps query and storage costs sustainable as data scales over the long term.

## Official References

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB Manual — About Time Series Data](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/)
- [MongoDB Manual — Time Series Considerations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-considerations/)
- [MongoDB Manual — Best Practices for Time Series](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/)
- [MongoDB Manual — Set Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/)
- [MongoDB Manual — Time Series Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Java Sync Driver — Time Series Collections](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/time-series/)
