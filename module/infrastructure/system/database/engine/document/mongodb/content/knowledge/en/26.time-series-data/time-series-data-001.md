# Time Series Problems and Differences from Regular Collections in MongoDB

A building management system receives temperatures from thousands of sensors every minute. An e-commerce platform records API latency over time. An energy company collects electricity consumption every 15 minutes. These datasets differ from typical customer profiles or orders: **each record is a measurement or event attached to a point in time**, continuously appended, frequently queried by time range, and then aggregated into charts or reports.

MongoDB provides **time series collections** optimized for this type of data. From the application's perspective, you still run `insertMany()`, `find()`, and `aggregate()` on measurement documents. Internally, however, MongoDB organizes measurements into **buckets** by time and metadata, using compression/storage mechanisms and query optimizations that differ from regular collections.

Crucially: **a time series collection is not merely a regular collection with a date/time index**. Conversely, not every dataset with a `createdAt` field belongs in a time series collection. An order whose status changes frequently, requires unique business keys, and participates in multi-document update transactions has completely different requirements from a nearly append-only sequence of measurements.

This lesson belongs to the **Time Series Data** chapter of the *Database Engine Document MongoDB* module. The examples use **mongosh** with the `time_series_lab` database. Features related to updates/deletes, indexing, sharding, bucket configuration, TTL, and support for certain specialized operations vary across MongoDB versions. The examples here primarily use core capabilities; when deploying, verify your actual **MongoDB server version, Feature Compatibility Version, driver, and managed service**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify a time series workload: timestamped measurements, stable metadata, continuous writes, windowed queries, and aggregations.
2. Distinguish **event time**, **ingestion time**, valid timestamps, and late-arriving data scenarios.
3. Design measurement documents with a required `timeField` and an optional `metaField`.
4. Create a time series collection using `createCollection()` and choose an appropriate `granularity`.
5. Understand the internal bucketing mechanism, data compression, and why metadata cardinality affects compression efficiency.
6. Compare time series collections with regular collections across storage, indexes, queries, updates, deletes, TTL, and constraints.
7. Write time-range queries, fetch the latest measurement, and aggregate by minute/hour/day.
8. Know how to use `$dateTrunc`, `$group`, `$setWindowFields`, `$densify`, and `$fill` for supported use cases.
9. Design indexes for metadata and time queries without assuming regular collection indexes apply identically.
10. Choose a retention policy and understand that TTL deletes by bucket rather than immediately per individual measurement.
11. Detect incorrect timestamps, missing/null values, duplicates, out-of-order arrivals, and unit mismatches.
12. Decide when to keep a regular collection, when to use a time series collection, or when to combine both.
13. Plan data ingestion, migration, operations, backup, and monitoring for a telemetry system.

## 2. What Kind of Problem Is Time Series?

A **time series** is a sequence of values or events ordered by time, usually consisting of multiple **series** distinguished by one or more attributes.

Example:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:00:00Z"),
  meta: {
    sensorId: "sensor-01",
    buildingId: "building-A",
    metric: "temperature"
  },
  value: 25.6,
  unit: "C"
}
~~~

Here:

- `observedAt` is the **observation timestamp**.
- `sensorId` and `metric` identify the series.
- `buildingId` describes an analytical dimension or sensor group.
- `value` is the measurement.
- `unit` clarifies the exact meaning of the value.

Every minute, a new document is added for the same sensor, rather than continuously updating a single document containing an array of all data points.

### 2.1. Suitable Use Cases

| Problem | Timestamp | Relatively stable metadata | Values changing over time |
|---|---|---|---|
| Room temperature | Time recorded by sensor | Sensor, building, measurement type | Temperature, humidity |
| Server CPU | Scrape time | Host, cluster, metric | CPU %, load average |
| Stock prices | Tick time | Ticker symbol, exchange | Price, volume |
| Electricity usage | Meter reading interval | Meter, customer, measurement type | kWh |
| GPS tracker | Time reported by device | Device, vehicle type | Latitude, longitude, speed |
| Air quality | Sample time | Station, region, sensor type | PM2.5, CO₂ |
| Event telemetry | Event time | Service, event type | Latency, request size |

### 2.2. Problems That Merely "Have a Date/Time" Are Not Necessarily Time Series

~~~javascript
{
  _id: "order-123",
  customerId: "c-01",
  createdAt: ISODate("2026-10-01T08:00:00Z"),
  status: "CREATED",
  total: NumberDecimal("150.00")
}
~~~

An order has `createdAt`, yet the record also:

- Gets updated multiple times: CREATED → PAID → SHIPPED.
- Requires a unique order ID, foreign references, and consistency controls.
- May participate in inventory-hold/payment transactions.
- Is looked up primarily by `orderId` or customer, not just by time window.

This is typically a **regular collection** case. If you want to track state changes over time, you can keep `orders` as a regular collection and write **append-only order events** to an appropriate collection (a time series collection if event characteristics and feature limits allow).

### 2.3. Quick Identification Rules

Ask yourself:

1. Is each document a **new observation/event** or a **mutable entity requiring frequent edits**?
2. Are queries primarily "range from T1 to T2 for device X", "hourly average", or "30-day chart"?
3. Are writes arriving steadily from many sources with a largely uniform schema?
4. Is historical data mostly read/aggregated or expired via retention, with rare edits to individual points?
5. Is the metadata identifying the series stable enough for measurements to be bucketed effectively?

If most answers are yes, a time series collection is worth considering. If the business requires arbitrary edits/deletes, complex unique constraints, or transactions on individual records, consider a regular collection.

## 3. Concepts of Measurement, Series, and Time Windows

Suppose three sensors record:

~~~text
sensor-01: 08:00 25.2°C -> 08:15 25.6°C -> 08:30 26.0°C
sensor-02: 08:00 24.1°C -> 08:15 24.4°C -> 08:30 24.8°C
sensor-03: 08:00 28.0°C -> 08:15 27.8°C -> 08:30 27.5°C
~~~

Each sensor is a **series**. A measurement is a document with a timestamp and values. A report might:

- Fetch raw measurements for `sensor-01` over 24 hours.
- Compute the average hourly temperature for each building.
- Find the daily min/max.
- Detect sensors that have lost signal for over 30 minutes.
- Trigger alerts when temperature exceeds a threshold.
- Roll up 1-minute data into 15-minute or 1-hour intervals for long-term storage.

### 3.1. Raw vs. Aggregated

~~~mermaid
flowchart LR
    S["Sensors send readings every minute"] --> Raw["Raw measurements"]
    Raw --> Agg["15-minute / hourly aggregation"]
    Agg --> Dash["Dashboard / alerting"]
    Raw --> Ret["TTL / retention"]
    Agg --> Hist["Long-term summary storage"]
~~~

**You do not need to query hundreds of millions of raw points** for every dashboard. You can maintain time-aggregated summary tables to improve latency and control costs.

### 3.2. Business-Meaningful Time Axis

A day in Vietnam's time zone does not align with a UTC day. When reporting "October 1 in Vietnam", you must determine the corresponding UTC range or specify a timezone in date operators. Never group arbitrarily by `"YYYY-MM-DD"` strings if global data spans multiple timezones.

## 4. Event Time vs. Ingestion Time: Two Different Fields

A device takes a reading at 08:00, loses network connectivity, and only sends the data at 08:20.

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:20:00Z"),
  meta: { sensorId: "sensor-01" },
  temperatureC: 25.2
}
~~~

Where:

- **Event time (`observedAt`):** the time the measurement actually occurred.
- **Ingestion/processing time (`receivedAt`):** the time the system received or processed the measurement.

If the requirement is a temperature chart by sensor measurement time, `observedAt` should usually be the `timeField`. If the requirement is API requests received per second by the backend, the backend receipt time may be the appropriate `timeField`.

### 4.1. Consequences of Using the Wrong Time Field

If you use `receivedAt` for sensor reporting, delayed readings are placed at 08:20 instead of 08:00. A temperature chart "by observation time" becomes distorted, and windowed min/max calculations can be wrong.

### 4.2. Device Clocks Are Not Always Trustworthy

A sensor whose clock is skewed by 12 hours might produce:

~~~javascript
observedAt: ISODate("2026-10-01T20:00:00Z")
receivedAt: ISODate("2026-10-01T08:00:03Z")
~~~

You need to check:

- Is the timestamp unreasonably far in the future?
- Does the ingestion delay exceed an acceptable threshold?
- Is the device synchronized via NTP/clock?
- Do you need to store `clockQuality`, `firmwareVersion`, or timestamp source?

A time series collection optimizes storage; **it does not automatically verify clock quality**.

### 4.3. BSON Date

The `timeField` of a time series collection must contain a valid **BSON Date** value. A string:

~~~javascript
observedAt: "2026-10-01T08:00:00Z"
~~~

is not a substitute for:

~~~javascript
observedAt: ISODate("2026-10-01T08:00:00Z")
~~~

The application must parse and validate timezone/format before writing. In `mongosh`, `ISODate()` creates a BSON Date; other language drivers provide corresponding Date/Instant types.

## 5. How Is a Time Series Collection Declared?

When creating a collection, pass the `timeseries` option:

~~~javascript
use time_series_lab

db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})
~~~

Three key options:

| Option | Required? | Meaning |
|---|---|---|
| `timeField` | Yes | Name of the field containing the BSON Date of the measurement |
| `metaField` | No | Name of the field containing metadata used to organize series/buckets |
| `granularity` | Optional | Hint for expected interval spacing between measurements, affecting bucket organization |

### 5.1. `timeField`

`observedAt` is a real document field written by the application. MongoDB uses it to organize measurements chronologically. Do not choose a continuously changing field like `lastUpdatedAt` when the requirement is a fixed observation time.

### 5.2. `metaField`

`meta` can be an object:

~~~javascript
meta: {
  tenantId: "t-01",
  buildingId: "building-A",
  sensorId: "sensor-01"
}
~~~

These fields describe the measurement source and typically remain unchanged across readings. MongoDB uses `metaField` values to group buckets; therefore, place **series identity and relatively stable attributes** here.

### 5.3. `granularity`

Typical choices are `"seconds"`, `"minutes"`, and `"hours"`. This describes the expected measurement frequency/spacing so MongoDB can organize buckets appropriately; **it does not mean the server only accepts timestamps rounded to whole minutes or hours**.

For example:

- Readings every few seconds: consider `seconds`.
- Readings every few minutes: consider `minutes`.
- Readings several hours apart: consider `hours`.

The choice depends on actual frequency, event distribution, and query ranges. Setting `granularity="hours"` does not automatically aggregate data into one document per hour.

### 5.4. Custom Bucket Options

In supported versions, MongoDB also provides options such as `bucketMaxSpanSeconds` and `bucketRoundingSeconds` to control bucket time span width and rounding rules. These can be useful for specialized workloads, but they come with value constraints and cannot be mixed arbitrarily with traditional `granularity` settings. Start with the easier-to-manage `granularity`; only tune custom buckets after gathering metrics on bucket fill and query latency.

### 5.5. Creating an Equivalent Regular Collection for Comparison

~~~javascript
db.createCollection("sensorReadingsRegular")

db.sensorReadingsRegular.createIndex(
  { "meta.sensorId": 1, observedAt: -1 },
  { name: "idx_regular_sensor_time" }
)
~~~

Both collections can hold **the exact same measurement schema**. The main difference is not that the application writes differently structured documents, but **how MongoDB organizes/stores/indexes the data and restricts operations**.

## 6. Lab Dataset: Three Sensors, Two Buildings

The sample dataset is designed to be small enough to verify results by hand. Each sensor sends temperature and humidity at 15-minute marks; one interval includes a late-arriving measurement by receipt time.

~~~javascript
const samples = [
  // sensor-01: building-A, room-101
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 25.0, humidityPct: 55, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 25.4, humidityPct: 56, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.0, humidityPct: 55, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T09:07:00Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.6, humidityPct: 54, quality: "LATE" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 27.0, humidityPct: 53, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.4, humidityPct: 54, quality: "OK" },

  // sensor-02: building-A, room-102
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.0, humidityPct: 61, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:04Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.2, humidityPct: 60, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.4, humidityPct: 60, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T08:45:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.6, humidityPct: 59, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:04Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.8, humidityPct: 58, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 25.0, humidityPct: 58, quality: "OK" },

  // sensor-03: building-B
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:05Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 28.0, humidityPct: 48, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:04Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.7, humidityPct: 49, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:05Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.5, humidityPct: 49, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T08:45:04Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.3, humidityPct: 50, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:03Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.1, humidityPct: 51, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.0, humidityPct: 51, quality: "OK" }
]

db.sensorReadings.insertMany(samples)
db.sensorReadingsRegular.insertMany(samples)
~~~

Notes:

- Run on two **empty** lab collections; re-running creates duplicate measurements, as no unique constraint for logical measurements is demonstrated here.
- Timestamps are all in UTC (`Z` suffix), making range comparisons straightforward.
- `sensor-01` has an 08:45 measurement received 22 minutes late, yet its `observedAt` remains accurate.
- The schemas of the regular and time series collections are identical from **the application's perspective**.
- All three sensors share `tenantId: "t-01"`; this lab does not demonstrate authorization controls. In production, `tenantId` must come from authentication.

### 6.1. Checking Document Counts

~~~javascript
db.sensorReadings.countDocuments({})        // 18
db.sensorReadingsRegular.countDocuments({}) // 18
~~~

Measurements per sensor:

| Sensor | Building | Readings | Min Temp | Max Temp |
|---|---|---:|---:|---:|
| `sensor-01` | A | 6 | 25.0 | 27.0 |
| `sensor-02` | A | 6 | 24.0 | 25.0 |
| `sensor-03` | B | 6 | 27.0 | 28.0 |

Because the dataset is tiny, this lab teaches **semantics**. You cannot extrapolate production compression ratios, throughput, or query latency from 18 measurements.

## 7. Applications See Documents; MongoDB Stores Buckets

In a regular collection, one measurement document corresponds to one stored document in the standard storage model along with its corresponding index entries.

In a time series collection, MongoDB organizes multiple measurements into **internal bucket documents** based on metadata and time intervals. Each bucket stores metadata, min/max timestamps, and field values in a layout favorable for compression and analytical scans. Users still query logical measurements.

~~~mermaid
flowchart TD
    App["Application inserts measurements"] --> TS["Time series collection: sensorReadings"]
    TS --> Group{"Group by meta + time window"}
    Group --> B1["Bucket sensor-01 / time window"]
    Group --> B2["Bucket sensor-02 / time window"]
    Group --> B3["Bucket sensor-03 / time window"]
    B1 --> Compress["Column-oriented storage/compression inside buckets"]
    B2 --> Compress
    B3 --> Compress
    Compress --> Query["find / aggregate returns logical measurements"]
~~~

### 7.1. Why Is Bucketing Useful?

Multiple measurements from the same sensor typically share:

- Identical metadata.
- Identical value fields (`temperatureC`, `humidityPct`).
- Closely spaced timestamps.
- Numeric values varying over relatively small deltas.

These are ideal conditions for columnar/sequential compression within a bucket, while reducing repeated metadata overhead compared to storing each measurement independently as a regular document.

### 7.2. Do Not Query `system.buckets` Directly as a Business API

MongoDB maintains internal storage for time series collections, typically using a namespace like `system.buckets.<collectionName>`. However, applications **should never directly read, write, or modify bucket documents** as a substitute for `db.sensorReadings.find()`. The internal representation can change across versions, and improper writes can corrupt data.

Always query through the **logical time series collection**; use supported statistics and explain commands to inspect storage.

### 7.3. Buckets Do Not Mean One Document Per Hour

Choosing `granularity: "minutes"` does not create a new bucket at the start of every minute, nor does it guarantee exactly one bucket per hour per sensor. The system determines bucket placement based on metadata, time, document count/size, and engine policies. Therefore:

> `granularity` organizes storage buckets; `$dateTrunc`/`$group` is how the application produces **one aggregated value per hour**.

### 7.4. Bucket Pruning

A query filtering by `meta.sensorId` and an `observedAt` range allows the optimizer to skip irrelevant buckets using metadata and time min/max bounds. This is one reason time series reads can be efficient on matching workloads. Actual effectiveness still depends on indexes, bucket sizes, selectivity, and query shape.

### 7.5. Queries That Need to "Unpack" Measurements

When returning raw measurements, the engine may have to decompress/"unpack" logical documents from buckets. Execution plans may show an internal unpacking stage. For summary reports that can be optimized at the bucket level in certain cases, the engine may reduce how many measurements need materializing; however, never assume every computation skips unpacking.

## 8. Compression Mechanism: How Time Series Differs from Regular Collections

Suppose each measurement contains:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  meta: {
    tenantId: "t-01",
    buildingId: "building-A",
    sensorId: "sensor-01"
  },
  temperatureC: 25.4,
  humidityPct: 56
}
~~~

In a regular collection, metadata is repeated in every document under standard document storage. **Collection compression** and indexes can be enabled, so regular collections are not "uncompressed". However, time series collections use **bucket-oriented/columnar compression** tailored specifically to sequences of measurements with repeating schemas and metadata.

### 8.1. Potential Advantages

- Reduced disk space for repetitive raw measurements.
- Less storage overhead from repeating metadata.
- Opportunities to read measurement ranges/groups more efficiently.
- Time-range aggregation queries can benefit from bucket-level optimizations.
- Built-in time-based retention on time series collections.

### 8.2. There Is No Fixed Compression Ratio

Never claim "time series always saves 90%" or "is always 10x faster". Results vary depending on:

- Number of measurements per bucket.
- Cardinality and stability of metadata.
- Whether schemas/fields repeat consistently.
- Value types and variance/deltas.
- Time spacing between events.
- Late/out-of-order measurements.
- MongoDB version, compressor, and workload.

A dataset where each `meta` value has only **one measurement** may miss out on most bucket compression benefits.

### 8.3. Size Estimation Example

Suppose one sensor sends 1 point/minute:

~~~text
60 points / hour
1,440 points / day
525,600 points / 365 days
~~~

With 10,000 sensors:

~~~text
5,256,000,000 measurements / 365 days (assuming steady transmission with no lost points)
~~~

At this scale, disk usage, index entry counts, TTL overhead, and raw-history queries become critical concerns. These figures only reflect write rate, **not actual disk usage**; you must benchmark bytes/measurement on your own schema.

## 9. Designing `metaField`: One of the Most Important Decisions

The `metaField` describes the **source** or **measurement group**. For example:

~~~javascript
meta: {
  tenantId: "t-01",
  buildingId: "building-A",
  sensorId: "sensor-01"
}
~~~

Measurements from the same sensor over time can be grouped into buckets sharing the same metadata.

### 9.1. Metadata Should Be Stable

Good candidates:

- `tenantId`.
- `sensorId`/`deviceId`.
- `siteId`/`buildingId` if the relationship is relatively stable.
- `metricType` if multiple series types share a compatible schema.

Values should have standardized data types and naming conventions.

### 9.2. Metadata Changing Per Measurement Can Break Bucketing Efficiency

Avoid:

~~~javascript
meta: {
  sensorId: "sensor-01",
  requestId: "req-unique-for-every-reading",
  receivedAt: ISODate("2026-10-01T08:15:03Z")
}
~~~

Because `requestId` and `receivedAt` change on every write, each measurement may produce a distinct metadata value, fragmenting bucket grouping into many nearly empty buckets and degrading compression and ingestion efficiency.

Put those on regular measurement fields instead:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  receivedAt: ISODate("2026-10-01T08:15:03Z"),
  eventId: "req-123",
  meta: { sensorId: "sensor-01" },
  temperatureC: 25.4
}
~~~

### 9.3. High Cardinality Is Not Automatically Wrong

If there are **one million sensors** and each sensor writes thousands of points, `sensorId` is still a valid series identity despite high cardinality: each sensor accumulates many measurements over time.

What matters is **the number of measurements per meta value/bucket and the write rate distribution**, not merely the count of distinct `sensorId` values.

### 9.4. Do Not Merge Unrelated Metadata Sources Just for Compression

If you remove `sensorId` from `meta` so that all sensors in a building share buckets, querying "sensor-01 over 7 days" may have to filter through measurements from many other sensors in the same buckets. That lowers cardinality at the expense of read amplification and harder data management.

The goal is a balance between **series identity, query predicates, and bucket fill**, not minimizing unique meta values at all costs.

### 9.5. What If Metadata Changes Over Time?

A sensor may be moved from `building-A` to `building-B`. You must define:

- Does metadata on a measurement describe **location at the time of measurement** or **current location**?
- If `buildingId` is in `meta`, new measurements after the move carry the new metadata and naturally belong to a new series grouping.
- If you need current device info, keep a separate `devices` table (regular collection) and join or look up in the application.

Do not bulk-update all historical records just to reflect current location if historical analysis requires the original context.

## 10. Time Series Collections Do Not Automatically Enforce Logical Measurement Uniqueness

A measurement may have a business identity:

~~~text
(tenantId, sensorId, observedAt, metricType)
~~~

If a device retries the same packet, the database may receive two equivalent measurements:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  meta: { tenantId: "t-01", sensorId: "sensor-01" },
  temperatureC: 25.4,
  eventId: "evt-001"
}
~~~

Time series collections are optimized for appends and **do not by default guarantee a single measurement per business key**. Unique index constraints on time series collections carry strict limitations compared to regular collections; never design ingestion assuming arbitrary unique indexes work just like on regular collections.

### 10.1. Safe Retries at the Ingestion Layer

You can maintain a regular collection `ingestLedger` with a unique index on `tenantId + eventId` to track processed packets, or deduplicate in a broker/stream processor. However, you must account for **crash risks between writing the ledger and writing the measurement**, version-specific transaction limits on time series collections, and your actual at-least-once/exactly-once contract.

A common pattern:

~~~text
Sensor event with fixed eventId
  -> Queue/stream ingestion
  -> Dedupe by eventId with appropriate storage
  -> Insert measurement into time series
  -> Checkpoint/reconciliation
~~~

If the workload demands **strict uniqueness + multi-document atomicity** per point, a regular collection or specialized data model/ingestion protocol may guarantee correctness more easily.

### 10.2. Do Not Rely on `_id` as the Sole Answer

Do not assume `_id` uniqueness, unique indexes, and upserts on time series collections behave identically to regular collections across all versions. When exactly-once semantics are required at the business-event level, explicitly define which deduplication layer enforces uniqueness and how retries recover.

## 11. Querying Raw Measurements by Sensor and Time Range

Common query:

~~~javascript
db.sensorReadings.find(
  {
    "meta.tenantId": "t-01",
    "meta.sensorId": "sensor-01",
    observedAt: {
      $gte: ISODate("2026-10-01T08:00:00Z"),
      $lt: ISODate("2026-10-01T09:00:00Z")
    }
  },
  {
    _id: 0,
    observedAt: 1,
    temperatureC: 1,
    humidityPct: 1
  }
).sort({ observedAt: 1 })
~~~

In our lab, this returns the 08:00, 08:15, 08:30, and 08:45 entries for `sensor-01`. The 08:45 measurement with `receivedAt=09:07` **is still returned** because the filter uses event time.

### 11.1. Use Half-Open Intervals

Typically write:

~~~javascript
observedAt: { $gte: start, $lt: end }
~~~

instead of `$lte: end` to avoid double-counting boundary measurements when stitching consecutive windows:

~~~text
[08:00, 09:00)
[09:00, 10:00)
~~~

The 09:00 point belongs solely to the second window.

### 11.2. Filter Metadata Early

If a collection holds millions of sensors, filtering only by time may scan buckets belonging to unrelated sensors. Filtering by `meta.sensorId` and `observedAt` narrows both the **series** and the **time window**.

### 11.3. Projection

If an API only renders a temperature chart, do not return the entire document including technical payloads, signatures, or raw device JSON. Projection reduces network bytes, though you should not assume every projected query becomes a covered query; inspect the actual execution plan.

### 11.4. Pagination and Streaming

A charting API should never return 20 million measurements in one call. Use:

- Bounded time ranges.
- Cursors or timestamp-based pagination with a tie-breaker key when needed.
- Downsampling/aggregation matched to screen resolution.
- Maximum point limits per chart.

Deep `$skip` over a very long series is expensive; keyset pagination with a stable key is better suited for sequential reading.

## 12. Fetching the Latest Measurement for a Sensor

A query:

~~~javascript
db.sensorReadings.find(
  {
    "meta.tenantId": "t-01",
    "meta.sensorId": "sensor-01"
  },
  {
    _id: 0,
    observedAt: 1,
    temperatureC: 1,
    humidityPct: 1
  }
).sort({ observedAt: -1 }).limit(1)
~~~

In the lab, the latest point by `observedAt` is **09:15, 26.4°C**.

### 12.1. "Latest" Has Two Meanings

If a query sorts by `receivedAt`, the late 08:45 point (`receivedAt` 09:07) sits in a different position than when sorting by `observedAt`. In the lab, both sorts yield 09:15 as the latest record, but real-world cases with data arriving hours late can differ.

Define explicitly:

- **Latest observed:** the measurement with the greatest event time.
- **Latest received:** the packet most recently received by the backend.

Never let an API return one when users expect the other.

### 12.2. Latest-State Caching Is a Different Problem

If a dashboard must display the current state of 100,000 sensors every second, querying raw time series per sensor can create heavy read load. You can maintain a **regular `sensorLatest` collection** holding one document per sensor, updated as newer events arrive:

~~~javascript
{
  _id: "t-01:sensor-01",
  observedAt: ISODate("2026-10-01T09:15:00Z"),
  temperatureC: 26.4,
  humidityPct: 54
}
~~~

The raw history collection serves time-based analysis; the latest-state collection serves low-latency current lookups. Late arrivals must be handled so older records **do not overwrite current state**.

## 13. Windowed Aggregation: Hourly Average Temperature

A typical report:

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      avgC: { $avg: "$temperatureC" },
      minC: { $min: "$temperatureC" },
      maxC: { $max: "$temperatureC" }
    }
  },
  { $sort: { "_id.hour": 1 } }
])
~~~

### 13.1. Lab Results

For `sensor-01`:

~~~text
08:00–08:59:
  25.0, 25.4, 26.0, 26.6
  count = 4
  avg   = 25.75°C
  min   = 25.0°C
  max   = 26.6°C

09:00–09:59:
  27.0, 26.4
  count = 2
  avg   = 26.7°C
  min   = 26.4°C
  max   = 27.0°C
~~~

### 13.2. Timezone in `$dateTrunc`

To group by "hours in Vietnam", specify:

~~~javascript
{
  $dateTrunc: {
    date: "$observedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Store timestamps as UTC Dates, then group and display in the required timezone. This prevents daily/monthly reporting drift across international datasets.

### 13.3. Grouping by Sensor and Time

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      avgC: { $avg: "$temperatureC" },
      measurements: { $sum: 1 }
    }
  },
  { $sort: { "_id.sensorId": 1, "_id.hour": 1 } }
])
~~~

One query can summarize all three sensors. With millions of series, the number of groups can grow huge; filter by time range, partition appropriately, and consider pre-aggregation.

## 14. `$dateTrunc` Computation vs. Time Series Storage Buckets

Two concepts that are easily confused:

| Concept | Where it is used | Purpose |
|---|---|---|
| Internal storage bucket | MongoDB time series engine | Group/compress measurements by metadata and time |
| `$dateTrunc` | Aggregation pipeline | Truncate timestamps to the start of a minute/hour/day |
| `$group` on `$dateTrunc` output | Aggregation | Produce one summary row per window |
| Materialized hourly summary | Separate collection | Persist aggregated results for fast future reads |

There is no guarantee that **each storage bucket** aligns with one calendar hour, and storage buckets must not be accessed directly to build charts. Aggregate using **business time semantics**.

## 15. Sliding Windows with `$setWindowFields`

Sometimes you need smoothing or a rolling average—for example, the average of **three consecutive measurements**.

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: { observedAt: 1 },
      output: {
        movingAvg3: {
          $avg: "$temperatureC",
          window: {
            documents: [-2, "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      observedAt: 1,
      temperatureC: 1,
      movingAvg3: 1
    }
  }
])
~~~

For `sensor-01`:

~~~text
08:00: avg(25.0)                   = 25.0
08:15: avg(25.0,25.4)              = 25.2
08:30: avg(25.0,25.4,26.0)         = 25.466...
08:45: avg(25.4,26.0,26.6)         = 26.0
09:00: avg(26.0,26.6,27.0)         = 26.533...
09:15: avg(26.6,27.0,26.4)         = 26.666...
~~~

### 15.1. Document Windows vs. Time Windows

`documents: [-2, "current"]` takes up to two **prior measurement documents** plus the current one—not necessarily exactly 30 minutes. If a sensor drops offline for an hour, the three nearest points could span a wide gap.

If the business requires the **average over the last 30 minutes by event time**, choose a range-based window with appropriate syntax and data; never conflate "three records" with "three 15-minute intervals".

### 15.2. Duplicate Timestamps

If the same sensor has two measurements with identical `observedAt`, sorting by time alone does not produce a deterministic order. For position-based window functions, define a tie-breaker/measurement identity policy so results remain deterministic. Time series collections do not resolve duplicates or ordering ambiguity on their own.

## 16. Missing Data and Gaps Without Measurements

Time series collections do not guarantee a document exists for every minute. A sensor may lose connectivity, undergo maintenance, or fail validation.

Example:

~~~text
10:00 -> 25.0
10:15 -> 25.5
10:30 -> [missing point]
10:45 -> 26.2
~~~

When plotting a chart, the application must decide whether to:

- Leave a **gap** rather than synthesizing a value.
- Fill with the previous observation (LOCF).
- Linearly interpolate.
- Flag values as "estimated/imputed" so they are not mistaken for real measurements.

### 16.1. `$densify` Generates Missing Timestamps

In versions supporting `$densify` (MongoDB 5.1+), you can generate timestamps at a fixed step within an aggregation pipeline. Example using a single series and a bounded hour range:

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  { $project: { _id: 0, observedAt: 1, temperatureC: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-10-01T08:00:00Z"),
          ISODate("2026-10-01T10:00:00Z")
        ]
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

Because the lab has six points from 08:00 to 09:15 and none at 09:30 or 09:45, you can observe the additional synthesized timestamps within those bounds. They are not stored measurements; they are **generated inside the pipeline**.

### 16.2. `$fill` Populates Data According to Policy

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  { $project: { _id: 0, observedAt: 1, temperatureC: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-10-01T08:00:00Z"),
          ISODate("2026-10-01T10:00:00Z")
        ]
      }
    }
  },
  {
    $fill: {
      sortBy: { observedAt: 1 },
      output: {
        temperatureC: { method: "locf" }
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

`locf` (last observation carried forward) carries the nearest prior value into empty slots. **This is a modeling assumption**, not a real measurement. For room temperature, it may be reasonable in the short term; for asset prices or alert events, the same rule can distort analysis.

### 16.3. Avoid Generating Millions of Unnecessary Points

Running `$densify` across several years at a 1-second step can generate an enormous number of documents. Bound:

- Time range.
- Number of selected series.
- Step/resolution.
- Maximum returned points.

Aggregate or downsample to an appropriate level before returning chart data.

## 17. Data Quality Indicators: Never Treat Missing as 0

A sensor fails to send a reading at 08:30. If the system substitutes `0°C`, the average drops artificially.

In telemetry systems:

- **0** can be a valid measured value.
- **null** can indicate an invalid measurement.
- **missing document** means no measurement was recorded at that timestamp.
- **estimated** is an interpolated value.
- **outlier** is a recorded value that is suspect.

These are distinct states.

### 17.1. Example Aggregation Excluding Poor-Quality Measurements

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      quality: "OK",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$meta.sensorId",
      validCount: { $sum: 1 },
      avgC: { $avg: "$temperatureC" }
    }
  }
])
~~~

In the lab, `sensor-01` has an 08:45 point with `quality: "LATE"`. Whether to exclude it depends on **policy**: arriving late does not mean the measurement itself is inaccurate. A retrospective report may **keep** late measurements, while a real-time dashboard computes only from points received by that time.

### 17.2. Coverage

If 4 points/hour are expected and only 3 arrive, coverage = 75%. You can compute coverage against each sensor's schedule, accounting for downtime/maintenance windows, timezones, and irregular-interval sensors. Time series collections do not inherently know a device's expected frequency.

## 18. Indexes: Time Series Differ from Regular Collections

On a regular collection, you can create an index:

~~~javascript
db.sensorReadingsRegular.createIndex(
  { "meta.sensorId": 1, observedAt: -1 },
  { name: "idx_regular_sensor_time" }
)
~~~

On time series collections, modern MongoDB versions support various secondary indexes, but **indexing operates over storage buckets with specific constraints**. Never assume every index type, unique index, text index, or index option from regular collections is identically supported.

### 18.1. Indexing by Metadata and Time

~~~javascript
db.sensorReadings.createIndex(
  {
    "meta.sensorId": 1,
    observedAt: -1
  },
  { name: "idx_ts_sensor_time" }
)
~~~

This is a candidate index for:

~~~javascript
db.sensorReadings.find({
  "meta.sensorId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})
~~~

In some MongoDB versions, the system automatically creates a meta/time index when creating a collection with `metaField`. Check `getIndexes()` to **avoid creating duplicate indexes**. Do not treat a specific default index as an immutable guarantee across all versions.

### 18.2. Indexing by Tenant / Building / Sensor

If queries commonly filter on:

~~~javascript
{
  "meta.tenantId": "t-01",
  "meta.buildingId": "building-A",
  "meta.sensorId": "sensor-01",
  observedAt: { $gte: start, $lt: end }
}
~~~

you might consider an index:

~~~javascript
db.sensorReadings.createIndex(
  {
    "meta.tenantId": 1,
    "meta.buildingId": 1,
    "meta.sensorId": 1,
    observedAt: -1
  },
  { name: "idx_ts_tenant_building_sensor_time" }
)
~~~

However, base this on **query frequency, selectivity, cardinality, and explain plans**. Wide indexes carry write and storage costs; do not index every field simply because it exists in the schema.

### 18.3. Time-Range-Only Queries

A query:

~~~javascript
db.sensorReadings.find({
  observedAt: { $gte: start, $lt: end }
})
~~~

reads across many sensors within a time window. This can still be efficient for short windows, but with millions of sensors and long spans, scan volume becomes large. An index leading with `sensorId` is not optimal for all `timeField`-only queries; design indexes around the actual workload.

### 18.4. Unique Indexes and Logical Deduplication

Time series collections have **significant restrictions on unique indexing** compared to regular collections. If the business must enforce uniqueness on:

~~~text
tenantId + sensorId + observedAt + metricType
~~~

do not assume you can create an arbitrary unique compound index on a time series collection. Review your version's rules, and if the required constraint is unsupported, design ingestion deduplication or an appropriate regular collection.

### 18.5. Indexes Do Not Make Data Clean

A well-indexed query can return results quickly even if the dataset contains duplicate measurements, wrong-timezone timestamps, or physically impossible values. Indexes optimize the **access path**, not schema validation or data quality checks.

## 19. Reading `explain()` and Storage Statistics

Compare equivalent queries:

~~~javascript
const predicate = {
  "meta.sensorId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
}

db.sensorReadings.explain("executionStats").find(predicate)
db.sensorReadingsRegular.explain("executionStats").find(predicate)
~~~

For time series, plans may show:

- Scans over indexes or buckets.
- Time/metadata predicates pushed down to the bucket level.
- An internal stage that decompresses/unpacks measurements.
- Additional stages processing logical documents.

For regular collections, plans typically show `IXSCAN`, `FETCH`, or `COLLSCAN` on the corresponding document/index storage.

**Stage names and paths in `explain` depend on the server version and query engine**; avoid brittle checks tied to a single stage name.

### 19.1. Metrics to Measure

| Category | Useful metric | Question |
|---|---|---|
| Query | `nReturned` | How many logical measurements are returned? |
| Index | `totalKeysExamined` | How many index keys were scanned? |
| Document | `totalDocsExamined` | How many storage documents/buckets did the plan examine? |
| Time | Execution duration, p95/p99 | Does it meet the SLO? |
| Storage | `storageSize` / compressed bytes | Did disk footprint shrink? |
| Index | `totalIndexSize` | How much disk do indexes consume? |
| Ingest | Measurements/sec, insert latency | Are writes sustainable under load? |
| Bucket | Bucket count/fill/compression (if exposed by tools) | Are metadata and granularity well suited? |

**Note:** `docsExamined` in some time series plans reflects **bucket documents** rather than logical measurements. Do not compare this 1:1 against `docsExamined` from a regular collection to claim time series is X times better. Interpret the plan properly and compare latency, bytes, and CPU on a representative workload.

### 19.2. `stats()` and Storage

~~~javascript
db.sensorReadings.stats()
db.sensorReadingsRegular.stats()
~~~

Or run the collection statistics command in supported versions:

~~~javascript
db.runCommand({ collStats: "sensorReadings" })
~~~

Inspect storage/index stats and time-series-specific fields if provided by your version. Fields like bucket counts or bucket compression metrics may not appear identically across every version.

### 19.3. Do Not Benchmark with 18 Documents

With 18 measurements, MongoDB may choose a `COLLSCAN` because an index offers no advantage and bucket overhead has not amortized. For a real evaluation:

- Generate data with production-like sensor counts and frequencies.
- Include both in-order and late-arriving data.
- Run queries matching real patterns (per-sensor, per-building, all-sensor rollups).
- Measure concurrent ingestion and reads.
- Measure after buckets fill up, across warm/cold cache, and with active retention.
- Break out throughput, disk bytes/measurement, and p95/p99 latency.

## 20. Late Arrivals and Out-of-Order Data

A time series does not inherently receive measurements in strictly ascending `observedAt` order. In the lab:

~~~text
09:00: received point observedAt=09:00
09:07: received point observedAt=08:45
09:15: received point observedAt=09:15
~~~

This is **out-of-order ingestion**. MongoDB can ingest such measurements within feature limits, though late arrivals may increase bucket openings/creations, reduce compression efficiency, or impact write performance depending on the engine/version and lateness span.

### 20.1. Choosing a Lateness Budget

Example:

~~~text
Within 2 minutes: normal
2–60 minutes:     late, still accepted
After 60 minutes: route to backfill/reconciliation pipeline
Over 7 days:      requires dedicated policy
~~~

This is an **example business policy**, not an automatic MongoDB limit. Choose thresholds based on SLA, retention, and sensor type.

### 20.2. Backfilling Historical Data

When importing data from three years ago:

- Batch by time range and metadata where helpful.
- Preserve original timestamps rather than overwriting them with import time.
- Measure compression and insert throughput.
- Check retention policy: if the collection's TTL is shorter than the age of the data, older measurements may soon be purged.
- Do not run one giant transaction to import the entire historical dataset.

### 20.3. Watermarks in Analytics Pipelines

An "end-of-hour revenue" or "previous-hour average temperature" report may be incomplete if late events are still arriving. You can:

1. Delay closing the window by a lateness budget.
2. Allow corrections/recomputations when late events arrive.
3. Version the summaries.
4. Separate **provisional** numbers from **finalized** numbers.

A MongoDB time series collection is a storage/processing engine; watermark policy is the responsibility of ingestion and analytics.

## 21. Retention and TTL on Time Series

Telemetry data often does not require keeping raw measurements forever. Example:

~~~text
Raw 15-minute readings: retain 30 days
Hourly summary:         retain 2 years
Daily summary:          retain 7 years
~~~

MongoDB supports TTL on time series collections, typically via collection-level `expireAfterSeconds`:

~~~javascript
// Example of creating a time series collection with a 30-day retention.
db.createCollection("shortLivedReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
})
~~~

`2592000 = 30 × 24 × 60 × 60` seconds. This collection is a separate example and does not modify the existing `sensorReadings` collection.

### 21.1. Time Series TTL Does Not Delete Individual Documents to the Exact Second

Time series TTL is tied to **timestamps within buckets**, and data in a bucket may only be purged once the relevant bucket span satisfies the expiration semantics. The TTL monitor runs in the background, so deletion is not guaranteed at the exact second of expiration.

Example:

~~~text
Policy: retain 30 days
A bucket holds measurements from 08:00 to 08:59
=> Do not assume the 08:00 point vanishes at the exact second 30 days pass
=> Bucket cleanup depends on bucket time bounds and the TTL monitor
~~~

### 21.2. TTL Is Not a Data Security Deletion SLA

If compliance requires erasing personal data **within N minutes** or "immediately deleting a sensor on request", time series TTL does not satisfy that on its own. You must design a purge/rewrite/correction workflow consistent with version limits, backup retention, and access controls.

### 21.3. TTL and Incorrect `timeField` Values

If a device records `observedAt` with a wrong year far in the past, the measurement may immediately become eligible for cleanup. If the timestamp is in the future, data may persist longer than intended. Timestamp validation therefore directly affects retention.

### 21.4. Downsampling Before Expiring Raw Data

When the business requires long-term analytics:

~~~mermaid
flowchart LR
    Ingest["Raw readings"] --> TS["Raw time series: 30-day TTL"]
    TS --> Job["Hourly/daily aggregation job"]
    Job --> Summary["Hourly/Daily summary collection"]
    Summary --> BI["Historical dashboards"]
~~~

Jobs must ensure summaries are published only once a window is sufficiently stable, and support recomputation if late events arrive. Never let TTL purge raw data before required summaries are computed and reconciled.

## 22. Updates and Deletes: A Major Difference from Regular Collections

Regular collections are built for mutating document state:

~~~javascript
db.sensorReadingsRegular.updateOne(
  { _id: someId },
  { $set: { temperatureC: 26.0 } }
)
~~~

On time series collections, **update/delete capabilities and permitted filters/updates are restricted**, especially in older versions. Restrictions may govern:

- Which fields may be modified (`metaField` vs. measurement fields).
- How filters must constrain `metaField`.
- Whether updates can target one or multiple logical measurements.
- Whether upserts are supported.
- Whether arbitrary measurements can be deleted and via which operations.
- Whether operations can run inside multi-document transactions.

These conditions **vary across MongoDB versions**, so never write a regular-collection update/delete API and assume it transfers verbatim to a time series collection.

### 22.1. Designing Data as Nearly Append-Only

In many telemetry systems, **do not mutate already-stored raw points**. If corrections are needed, you can:

- Store a separate correction event linked by `eventId`/time.
- Attach a quality flag or superseding measurement according to policy.
- Recompute summaries from raw + corrections.
- Design a regular correction/current-state collection to support upserts and unique constraints.

When choosing time series, proactively define a **data correction policy**.

### 22.2. When Is a Regular Collection Better?

If the application must run:

~~~text
findOneAndUpdate({_id})
continuous per-device upserts
deleteOne by business ID
arbitrary unique indexes
transactions updating multiple distinct entities
~~~

then a regular collection for **mutable state** is usually more appropriate. You can store **measurement history** in a time series collection and **current device state** in a regular collection, coordinating them at the application/service layer.

### 22.3. Do Not Use "Updates Supported in Newer Versions" as a Reason to Convert Every Collection

Even as newer versions expand update/delete support for time series collections, storage and query execution remain optimized for time-ordered measurements rather than CRUD-heavy workloads. Evaluate the update/insert ratio, query patterns, indexes, workload latency, and exact version limits.

## 23. Direct Comparison: Time Series vs. Regular Collection

| Aspect | Time series collection | Regular collection |
|---|---|---|
| Typical data | Timestamped measurements/events | Entities, business records, general documents |
| Write pattern | Typically append-heavy, rare raw history edits | Flexible inserts, updates, and deletes |
| Collection creation | `timeseries: { timeField, metaField, granularity }` | Standard `createCollection()` |
| Metadata | `metaField` groups measurements | Arbitrary fields without special bucket semantics |
| Storage | Internal buckets with time series compression optimizations | Standard document storage with general compression |
| Common queries | Metadata + time range, rollups/windows | ID lookups, joins, state updates, pattern-dependent |
| Indexes | Time/meta indexes supported with version-specific limits | Broader indexing feature set |
| Unique constraints | Significantly restricted | Powerful, flexible unique indexes |
| Per-record updates | Subject to version-dependent constraints/support | Rich update operator support |
| Per-record deletes | Subject to time series restrictions | Standard `deleteOne`/`deleteMany` |
| TTL | Time/bucket-based retention mechanism | TTL index on Date field with regular semantics |
| Transactions | Restricted for time series, especially writes | Supported when topology qualifies |
| Schema evolution | Keep measurement structure stable for good compression | Flexible document modeling |
| Late arrivals | Can be ingested, with bucket tradeoffs | No time series bucket organization |
| "Latest value" lookup | Possible via sort/time index, but measure cost across many series | Current-state doc/upsert is often convenient |
| Compression benefit | Often strong for repeated schemas/metadata | Depends on compressor and schema; not tied to one workload |
| Query optimization | Bucket pruning/unpacking and specialized pipeline optimizations | Standard document index planner |
| Best suited for | Telemetry, metrics, sensor history, event measurements | Orders, customer profiles, mutable inventory, transaction ledgers |

**There is no universal winner.** An optimal design often combines both so each serves its proper role.

## 24. Case Study 1: Building Sensors

Requirements:

- 20,000 sensors.
- Each sensor sends 1 measurement every 15 seconds.
- Dashboard needs current temperature and a 24-hour chart.
- Retain raw data for 30 days and hourly summaries for 2 years.

### 24.1. Estimated Write Rate

~~~text
20,000 sensors × (60 / 15) measurements/minute
= 80,000 measurements/minute
≈ 1,333 measurements/second, assuming steady arrival
~~~

This is **average throughput**, excluding bursts when many devices reconnect simultaneously. The system must test peak ingestion, not just averages.

### 24.2. Data Architecture

~~~mermaid
flowchart LR
    Devices["20,000 sensors"] --> Queue["Ingestion API / queue"]
    Queue --> Validate["Validate timestamp / meta / value"]
    Validate --> Raw["Raw time series"]
    Validate --> Latest["Regular sensorLatest"]
    Raw --> Rollup["Hourly aggregate"]
    Rollup --> Hist["Summary history"]
    Raw --> Graph["24h chart"]
    Latest --> Live["Current state"]
~~~

### 24.3. Why Two Collections?

**Raw time series**:

- Append-only measurement writes.
- Time-range queries.
- Data compression.
- 30-day TTL.

**Regular `sensorLatest`**:

- One document per sensor.
- Upsert/update latest state.
- Unique business identity.
- Easy point lookups for dashboard APIs.

When a late measurement arrives, updating `sensorLatest` requires a **conditional comparison** so it never regresses the current timestamp:

~~~javascript
// Conceptual pattern in a regular collection.
db.sensorLatest.updateOne(
  {
    _id: "t-01:sensor-01",
    observedAt: { $lt: ISODate("2026-10-01T09:15:00Z") }
  },
  {
    $set: {
      observedAt: ISODate("2026-10-01T09:15:00Z"),
      temperatureC: 26.4
    }
  }
)
~~~

This only covers the **update branch when the current-state document already exists**. If upserting new records is required, design it separately to avoid races on missing documents and preserve unique keys. Do not treat an `updateOne` with `observedAt: $lt` as a complete upsert pattern.

## 25. Case Study 2: API Metrics

Example measurement:

~~~javascript
{
  observedAt: ISODate("2026-10-01T09:00:00Z"),
  meta: {
    service: "checkout",
    environment: "production",
    region: "asia"
  },
  latencyMs: 42,
  statusCode: 200
}
~~~

Metrics needed:

- Requests/sec or requests/minute.
- Average/max latency.
- Error rate.
- P95/P99 latency.

### 25.1. Cardinality Explosion in Metadata

Avoid putting into `meta`:

~~~javascript
meta: {
  service: "checkout",
  requestId: "unique-per-http-request",
  userId: "unique-high-cardinality-user"
}
~~~

because `requestId` changes on every event, easily fragmenting bucket grouping. Keep `requestId` as a measurement field if needed for tracing/debugging with short retention and privacy limits. Normalize route paths: replace `/orders/123` and `/orders/456` with route pattern `/orders/:id` when tracking metrics per endpoint.

### 25.2. Percentiles Are Not Averages

A 42 ms average does not reveal p99. Use statistical operators supported by your server version (such as percentile operators in modern versions) or a dedicated metrics store. Weigh the tradeoffs of retaining raw request events for exact percentiles against histograms/aggregates with bounded error.

### 25.3. Low-Latency Alerting

Time series collections excel at storing history, but if alerts must fire within 2 seconds, compute streaming counters on the ingestion/queue path rather than scanning millions of raw records for every alert rule.

## 26. Case Study 3: Logs/Events and Time Series Boundaries

Application logs carry `timestamp`, `hostname`, `severity`, and `message`. Should you use a time series collection?

It depends on the workload:

**Better fit when**:

- Logs share a largely uniform schema.
- Queries mostly filter by host/service + time range.
- Documents are rarely modified and retention is clear.
- Diverse index types or full-text search over log bodies are unnecessary.

**Consider a regular collection or dedicated search/log platform when**:

- Strong full-text search or highly varied semi-structured log parsing is required.
- Per-event updates, deletes, or custom retention exceed time series constraints.
- Unique constraints or transactional business events are needed.
- Queries filter across many dimensions outside metadata.

Do not dump all JSON logs into a time series collection solely because they have a `timestamp`. Evaluate access patterns, index support, and search requirements.

## 27. Choosing `granularity` Based on Measurement Frequency and Queries

A quick guide:

| Frequency | Candidate choice | What to measure |
|---|---|---|
| Several times/second | `seconds` | Bucket efficiency, peak write rate |
| Every 15 seconds | `seconds` | Steady rate, late arrivals |
| Every 5 minutes | `minutes` | Bucket span, query ranges |
| Hourly | `hours` | Bucket overhead and retention |
| Sparse, irregular events | Benchmark first | If few points per series, bucket overhead may be high |

### 27.1. Why `granularity` Is Not Chart Resolution

A collection created with `granularity: "seconds"` can still compute hourly averages. Likewise, a `granularity: "hours"` collection still accepts readings at `08:13:42`. Granularity governs how the engine **buckets** data, whereas chart resolution is determined by `$dateTrunc`/`$group` and the UI.

### 27.2. Changing `granularity`

MongoDB permits certain adjustments to `granularity`/bucket settings per version rules, but do not assume you can freely raise or lower every parameter after data is stored. Major changes may require creating a new collection and migrating. Check `collMod` and supported options for your version before planning.

### 27.3. When Using Custom Buckets

For highly specialized workloads, custom `bucketMaxSpanSeconds`/`bucketRoundingSeconds` can tune the bucket window. However, you must:

- Choose based on actual time distribution.
- Account for late/out-of-order measurements.
- Verify allowed parameter bounds.
- Measure compression ratio and read latency.
- Have a migration plan if settings prove suboptimal.

Never tune buckets by intuition alone.

## 28. Time Series and Sharding

When data outgrows a single replica set, consider **sharding the time series collection** on supported versions (MongoDB 5.1+, with version-specific improvements and restrictions).

### 28.1. Shard Key Design Questions

- Do queries usually filter by `tenantId + sensorId + observedAt`?
- Are some sensors or tenants significantly hotter than others?
- Should a large tenant span multiple shards?
- Will newly arriving data concentrate on a single time range / hot shard?
- Does the shard key comply with time series restrictions in your current version?

Do not pick a monotonically increasing `timeField` as the key in a way that funnels all new inserts onto one shard merely because "it's time series so shard by time". Valid shard keys for time series and support for hashed/meta/time fields depend on version; design and verify explicitly.

### 28.2. Sharding Does Not Make Every Aggregation Fast

A per-sensor query can be targeted cleanly if the shard key supports it, whereas "max temperature across all sensors over one year" still requires a distributed aggregation and global merge. Data volume/time range, indexes, and bytes transferred still govern performance.

### 28.3. Shard Key vs. Metadata Grouping

`metaField` controls bucket grouping; the **shard key** determines data placement across shards. They are related, not identical. Never assume identical `meta.sensorId` values always reside on one shard under every design.

## 29. Replica Sets / Read Preference for Time Series

A telemetry workload may:

- Write to the replica set primary.
- Read historical dashboards from secondaries when replication lag is acceptable.
- Read current state immediately after a write from the primary if read-your-writes is required.

However, if a secondary runs heavy aggregations, CPU/disk contention against replication apply can increase lag. `secondary` read preference **does not guarantee the freshest data**, and offloading queries to a secondary does not reduce the number of raw measurements scanned.

### 29.1. Late Arrivals + Replication Lag

There are two separate delays:

~~~text
Device reading -> ingestion service: 5 minutes delay
Primary -> secondary:                10 seconds delay
~~~

A dashboard reading from a secondary can lag behind event time due to **both layers**. Never rely on a single `replicationLag` metric to explain end-to-end data freshness.

### 29.2. Read Concern

`readConcern: "majority"` refers to observing majority-committed data per MongoDB semantics, yet a secondary may still not have applied the latest write. If a dashboard needs "read immediately after write", read from the primary or use appropriate causal consistency rather than merely setting `majority`.

## 30. Retention, Schema, and Compliance

Before enabling TTL:

1. Identify data categories and minimum contractual/legal retention periods.
2. Separate raw data from summaries if trends must outlive raw points.
3. Define per-tenant data access policies.
4. Validate past/future timestamps.
5. Set up TTL and storage monitoring.
6. Define procedures for on-demand deletion outside TTL.
7. Account for retention in backups, logs, and downstream analytics stores.

### 30.1. Personal Data in `metaField`

Avoid placing emails, phone numbers, or sensitive data directly inside `metaField` unless strictly necessary. Metadata is repeated and used for indexing/routing, widening PII exposure. Prefer low-sensitivity stable IDs, enforce access controls, and store detailed metadata in a separate regular collection if needed.

### 30.2. Schema Evolution

New sensor firmware might rename fields:

~~~text
temperatureC -> temp_c
humidityPct -> relativeHumidity
~~~

Without normalization, `$avg: "$temperatureC"` ignores documents carrying only `temp_c` or undercounts. You can:

- Normalize at ingestion.
- Store a `schemaVersion`.
- Use controlled adaptive aggregations.
- Run backfills/migrations when needed.

Prefer a stable measurement schema so queries and compression stay predictable.

### 30.3. Measurement Units

Do not mix Celsius and Fahrenheit inside the same `temperature` field without tracking units or converting. Better yet, standardize on one unit (e.g., °C) in storage and convert for display in the UI.

## 31. Comparing Ingestion Across Both Collection Types

To evaluate real performance, measure:

~~~text
Measurements/second
Average and p95 insert latency
MongoDB CPU / I/O / cache
Total collection bytes
Index bytes
Actual compression ratio
Lag during write bursts
p95 time-range query latency
Impact of late arrivals
TTL overhead and purged data
~~~

### 31.1. Fair Benchmarking

When comparing regular and time series collections:

- Write identical measurement content with identical field types.
- Choose indexes **appropriate to each type** rather than forcing the exact same suboptimal index.
- Separate data disk usage from index disk usage.
- Test both steady inserts and late arrivals.
- Use representative series counts and points per series.
- Run multiple rounds; measure warm and cold cache.
- Monitor concurrent reads.
- Benchmark raw range queries, hourly groupings, and latest-measurement lookups separately.

### 31.2. Do Not Infer Disk Savings from Document Counts

The application still reads 100 million logical measurements even though the engine stores far fewer internal bucket documents. Comparing internal document counts between the two collection types **does not mean** the compression ratio equals the document-count ratio.

### 31.3. Index Overhead

Time series can save storage on raw measurements, yet creating too many secondary indexes increases index bytes and write amplification. Index design must serve critical read workloads—not "index every metadata field just in case".

## 32. Migrating from a Regular Collection to Time Series

If your system already has `sensorReadingsRegular`, do not treat enabling `timeseries` on an existing collection as a simple metadata toggle. The standard process is to **create a new time series collection and copy the data**.

### 32.1. Sample Migration Workflow

1. Measure existing document counts, indexes, schema variants, and active queries.
2. Normalize `observedAt` to BSON Date and fix invalid/unknown timestamps.
3. Define `metaField` and `granularity`.
4. Create the new time series collection with supported settings.
5. Ingest data in batches, ordered by event time/metadata where beneficial.
6. Verify counts, sample min/max, aggregations, and deduplication policies.
7. Run shadow queries comparing logical outputs between old and new collections.
8. Decide how to handle live writes during cutover (dual-write, queue replay, cutoff).
9. Shift read traffic behind a feature flag.
10. Keep a rollback window/backup before decommissioning the old collection.

### 32.2. Do Not Rely on Unconditional Dual-Writes

~~~text
Application inserts into regular collection -> succeeds
Time series insert times out
=> The two sources diverge
~~~

If dual-writing is required, implement retry/reconciliation mechanisms and stable event IDs rather than calling two `insertOne()` operations and assuming both always succeed together.

### 32.3. Batch Copying

Conceptual example (pseudocode):

~~~javascript
// Pseudocode: do not run across an entire large collection in an unbounded loop.
for await (const batch of readRegularByRangeWithCheckpoint()) {
  const normalized = batch.map(normalizeMeasurement)
  await writeTimeSeriesBatch(normalized)
  await storeCheckpointAfterSuccessfulWrite()
}
~~~

Choose batch size and checkpoint frequency based on throughput, memory, and timeouts; define duplicate handling on retry. Never use one giant multi-document transaction to migrate an entire history.

### 32.4. Cutover and Statistical Accuracy

Because late measurements may arrive after cutover, define a policy to accept older data and recompute rollups. Marking a collection "migrated" does not automatically mean all late arrivals have been accounted for.

## 33. Production Operations and Monitoring

A healthy time series system monitors both the database and the ingestion pipeline.

### 33.1. Key Metrics

| Category | Metric | Why it matters |
|---|---|---|
| Ingestion | Measurements/sec, burst rate | Write demand and capacity headroom |
| Freshness | Event-to-ingest delay p95/p99 | Source-to-system latency |
| Replication | Per-member lag | Secondary read staleness |
| Quality | Invalid timestamp, bad unit, null/outlier rate | Data reliability |
| Dedupe | Duplicate event IDs, replay attempts | Prevent double-counting |
| Storage | Data/index bytes, bytes/measurement | Cost control |
| Buckets | Bucket count/fill/compression (if available) | Detect poor metadata cardinality |
| Query | p95/p99 per-sensor range query | Charting SLO |
| Aggregation | Hourly rollup latency, spill | Detect reporting bottlenecks |
| Retention | Oldest event, TTL progress, backlog | Verify policy-compliant cleanup |
| Resource | CPU/disk/cache/network | Prevent ingestion from starving reads |
| App | Dashboard stale age, missing coverage | User-visible data quality |

Metric names are **instrumentation suggestions**, not exact names guaranteed to exist natively in MongoDB.

### 33.2. Detecting Silent Sensors

If the goal is "flag sensors silent for 30 minutes", simply querying measurements from the last 30 minutes and assuming presence/absence is not enough:

- Maintain a regular `devices` registry to know **which sensors are active**.
- Use current-state/`lastSeen` to find sensors lacking recent measurements.
- Distinguish sensors paused for maintenance from sensors experiencing outages.

A raw time series collection cannot by itself list sensors that **should have reported** but never sent a point.

### 33.3. Operational Alarms

Alert when:

- Ingestion backlog grows.
- p99 event-to-ingest delay breaches SLO.
- Invalid timestamp rate spikes after a firmware deploy.
- Data/index size grows abnormally.
- Bucket compression degrades after a metadata schema change.
- TTL falls behind write rate or purges too much data due to bad timestamps.
- Rollup jobs fail or summaries go stale.
- Query p95/p99 climbs as new sensors are onboarded.

### 33.4. Backup and Recovery

TTL is not backup; backup is not archival/retention. Define:

- Backup snapshots and point-in-time recovery capabilities.
- Coverage of raw, summary, device registry, and dedupe ledger collections.
- Backup retention policies aligned with compliance.
- Whether restore preserves consistency across raw/summary/ledger or requires reconciliation.
- For sharded clusters, a sharding/metadata-aware backup strategy.

## 34. Practice 1: Identify Collection Types

Classify five scenarios:

1. Each device sends temperature every minute; history is read only by time range.
2. A customer profile frequently updates name and address.
3. Each payment transaction has a unique `orderId`, requiring status updates and transactional guarantees.
4. Each server sends CPU usage every 10 seconds, needing hourly rollups.
5. Each sensor has **one current-state document** updated every minute.

Explain why 1 and 4 are time series candidates, while 2, 3, and 5 generally fit regular collections better.

## 35. Practice 2: Create and Insert Measurements

Create another time series collection:

~~~javascript
db.createCollection("powerReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

db.powerReadings.insertMany([
  {
    measuredAt: ISODate("2026-10-02T08:00:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.50")
  },
  {
    measuredAt: ISODate("2026-10-02T08:15:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.65")
  },
  {
    measuredAt: ISODate("2026-10-02T08:30:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.55")
  }
])
~~~

Note that `kwh` represents **electricity consumed during the 15-minute interval**, not a cumulative meter index. Hence the sum across the three points is `1.70 kWh`. If the field were a cumulative meter reading, consumption over a period would be computed from the **difference between two readings**, not by summing all readings.

## 36. Practice 3: Time-Range Query

Using the `sensorReadings` lab collection, write a query:

- Fetch `sensor-02` from 08:15 to before 09:00.
- Return only `observedAt` and `temperatureC`.
- Sort ascending by time.

Expected temperatures: **24.2, 24.4, 24.6°C**.

## 37. Practice 4: Hourly Rollup

Write a pipeline computing:

~~~text
sensorId
hour (UTC)
measurements
avgTemperatureC
minTemperatureC
maxTemperatureC
~~~

for `t-01` data on `2026-10-01` across hours 08 and 09. Hint: use `$dateTrunc` and `$group`. Compare the `sensor-01` results with Section 13.

## 38. Practice 5: Latest Measurement and Late Arrival

Run two queries:

~~~javascript
db.sensorReadings.find(
  { "meta.sensorId": "sensor-01" }
).sort({ observedAt: -1 }).limit(1)

db.sensorReadings.find(
  { "meta.sensorId": "sensor-01" }
).sort({ receivedAt: -1 }).limit(1)
~~~

On the current lab dataset, both may return the 09:15 point. Describe what happens if an additional packet with `observedAt=08:30` and `receivedAt=12:00` is ingested: how do **latest observed** and **latest received** differ?

## 39. Practice 6: Poorly Designed Metadata

A development team puts:

~~~javascript
meta: {
  sensorId: "sensor-01",
  requestId: "random-uuid-every-point"
}
~~~

Explain the consequences for bucket grouping and compression. Propose a revised schema that still retains `requestId` for tracing.

## 40. Practice 7: TTL

Design a retention policy:

~~~text
Raw: 14 days
Hourly summary: 2 years
Daily summary: 5 years
~~~

Identify the required collections, TTL settings, and late-arrival policy. Explain why you must not promise that a measurement is deleted at the exact second 14 days elapse.

## 41. Practice 8: Deduplication

A sensor sends the same packet twice due to a retry after a timeout:

~~~text
eventId = E123
sensorId = sensor-01
observedAt = 08:15
temperatureC = 25.4
~~~

Propose a stable ID/deduplication mechanism outside the time series collection and a way to detect a differing payload fingerprint for the same `eventId`. Why can you not simply create an arbitrary unique compound index like on a regular collection without verifying version support?

## 42. Practice 9: Explain and Benchmark

Run:

~~~javascript
db.sensorReadings.explain("executionStats").find({
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})

db.sensorReadingsRegular.explain("executionStats").find({
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})
~~~

Record the plans and metrics **actually produced**. Why can you not claim time series is faster based solely on 18 measurements or by comparing `docsExamined` without understanding bucket vs. logical docs?

## 43. Practice 10: Complete Architecture Design

A system has 50,000 sensors, each sending a reading every 30 seconds, retaining raw data for 60 days, with a live dashboard and 3 years of daily reporting.

Propose:

- Raw time series schema.
- `metaField` and `timeField`.
- Primary indexes and queries.
- Regular current-state collection.
- Raw TTL and summary retention.
- Packet ID deduplication.
- Quality and late-event policies.
- Downsampling and dashboard API.
- Metrics to monitor.

Explain why you cannot simply create one time series collection and satisfy every requirement with `find().sort().limit(1)` and unbounded raw-history queries.

## 44. Practice Solution Hints

### Exercise 1

1 and 4 are time series workloads: time-ordered append measurements, time-window reads, and aggregations. 2 and 3 are mutable entities needing CRUD/constraints/transactions. 5 can use a regular current-state collection while also writing raw history to a time series collection if needed.

### Exercise 2

If `kwh` is per-interval consumption, total = `0.50 + 0.65 + 0.55 = 1.70 kWh`. If it were a cumulative meter index, subtract consecutive readings.

### Exercise 3

Filter:

~~~javascript
{
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:15:00Z"),
    $lt: ISODate("2026-10-01T09:00:00Z")
  }
}
~~~

Projection `{ _id: 0, observedAt: 1, temperatureC: 1 }` and sort `{ observedAt: 1 }` returns 24.2, 24.4, 24.6.

### Exercise 4

Group by `$dateTrunc: { date: "$observedAt", unit: "hour", timezone: "UTC" }` and `$meta.sensorId`. `sensor-01`: hour 08 average 25.75, hour 09 average 26.7, with 4 and 2 measurements respectively.

### Exercise 5

The late packet received at 12:00 with `observedAt=08:30` is not the latest observed if a 09:15 point already exists. However, it can become the latest received; the API must explicitly state which metric it returns.

### Exercise 6

A unique `requestId` per point changes meta cardinality on every write, producing many sparsely populated buckets and reducing compression efficiency. Keep `meta: { sensorId: "sensor-01" }` and move `eventId`/`requestId` to regular measurement fields.

### Exercise 7

The raw time series has a 14-day TTL, while summary collections keep separate 2-year and 5-year retentions. TTL deletes by bucket via a background monitor, not immediately per measurement. Late events need watermarks/recomputation before raw data expires.

### Exercise 8

Use a stable `eventId`, a canonical payload fingerprint, and a durable deduplication layer (queue state or regular unique ledger). Design for crash recovery rather than assuming two-collection writes are atomic across all versions.

### Exercise 9

Actual `explain` output varies by plan and version; you may observe index/bucket pruning and unpacking stages. A tiny dataset is insufficient to conclude throughput or storage savings.

### Exercise 10

50,000 sensors × 2 measurements/min = 100,000/min ≈ 1,667/sec average, excluding bursts. Use raw time series with stable source metadata and a 60-day TTL; a regular latest-state collection for the live dashboard; hourly/daily summaries for 3 years; quality/dedupe/out-of-order policies; sensor/time indexes; and ingestion/replication/query metrics.

## 45. Common Pitfalls

| Pitfall | Why it is dangerous | Remedy |
|---|---|---|
| Choosing time series just because `createdAt` exists | Business entities may need CRUD/transactions | Evaluate access patterns and mutability |
| Using `receivedAt` instead of event time | Charts and time windows become inaccurate | Separate `observedAt` and `receivedAt` |
| Storing timestamps as strings | Fails BSON Date requirement for `timeField` | Parse and validate into Date |
| Putting random `eventId` in `meta` | Fragmented buckets, poor compression | Stable metadata; `eventId` as measurement field |
| Using only `buildingId` in `meta` when querying by sensor | Buckets mix multiple series | Choose identity matching query workload |
| Believing `granularity` auto-aggregates hourly | Storage buckets are not hourly summaries | Use `$dateTrunc + $group` |
| Querying `system.buckets` directly | Relies on internals; risk of data corruption | Query the logical collection |
| Assuming time series always compresses 90% | Depends on schema and series density | Benchmark on realistic data |
| Copying all regular indexes blindly to time series | Different index options and restrictions | Verify support and check `explain` |
| Assuming unique business measurements are auto-enforced | Duplicates from retries | Dedupe with stable IDs and suitable constraints |
| Using time series for mutable current state | Update/upsert limits, unsuitable query patterns | Regular current-state collection |
| Editing/deleting raw points arbitrarily | Time series has version-specific limits | Dedicated correction policy |
| Assuming TTL deletes exact documents to the second | TTL operates on buckets and background monitor | Align retention SLAs and monitoring |
| Skipping past/future timestamp validation | Data purged prematurely or kept too long | Validate timestamps |
| Treating missing measurements as 0 | Corrupts charts and averages | Define gap/imputation policy |
| Interpolating without flagging | Estimated values mistaken for real readings | Store/display provenance |
| Running `$densify` over multi-year windows at 1s step | Result set explodes | Bound time range and resolution |
| Computing latest by `receivedAt` when `observedAt` is needed | Late packets overwrite current state | Compare event timestamps |
| Fetching full raw history for charts | Wastes network, CPU, and memory | Downsample / roll up |
| Comparing only `docsExamined` across storage types | Bucket docs and logical docs mean different things | Measure latency, bytes, and plans |
| Picking a hashed key just because data is time series | Can cause hot shards or scatter queries | Choose shard key by workload |
| Reading secondaries expecting immediate write visibility | Replication lag | Use primary or causal consistency when needed |
| Dual-writing two collections without reconciliation | Data diverges when one write fails | Queues, checkpoints, and stable event IDs |

## 46. Review Questions

**1. What problem do time series collections solve?**

They optimize storing and processing large volumes of timestamped measurements/events that are typically appended sequentially and queried by metadata + time range.

**2. How does `timeField` differ from `metaField`?**

`timeField` holds the measurement's BSON Date. `metaField` describes the source/series and organizes buckets by metadata.

**3. Is `metaField` required?**

No. However, for multi-series datasets, a well-designed `metaField` generally improves filtering and bucket organization.

**4. Why should you not put a new `requestId` per submission inside `metaField`?**

It makes metadata change on every write, fragmenting bucket grouping and degrading compression.

**5. Is high `sensorId` cardinality always bad?**

No. If each sensor produces many measurements, `sensorId` remains a sensible series identity. What matters is points per series, distribution, and bucket fill.

**6. Does `granularity="minutes"` mean only round-minute timestamps can be inserted?**

No. It configures how the engine organizes buckets for expected cadence; it does not restrict timestamp precision.

**7. Is a time series collection just a regular collection plus an index on `observedAt`?**

No. Time series collections use bucket storage/compression and specialized query optimizations, along with distinct indexing/update/delete limits.

**8. Does MongoDB automatically create hourly summaries when using time series?**

No. Use `$dateTrunc`/`$group`, window operators, or materialized rollup jobs.

**9. Can a measurement arrive late?**

Yes. Event time and receipt time differ. Define a lateness policy and benchmark its impact on bucket efficiency.

**10. Does TTL on time series delete individual measurements the exact second they expire?**

No. It relies on bucket expiration and a background TTL monitor, introducing monitor delay and bucket granularity.

**11. Are time series collections suitable for storing customer profiles?**

Usually not if profiles require frequent updates, unique indexes, and transactions. A regular collection is more suitable.

**12. Which field should you sort by to get the latest point?**

Sort by `observedAt` for the most recent measurement in observation time; sort by `receivedAt` for the packet most recently received by the system.

**13. Why is a meta + time index helpful?**

It narrows both the series and the time window, improving bucket selection and access paths for matching queries.

**14. Why is `docsExamined` not always directly comparable between regular and time series collections?**

Because the time series storage engine operates on bucket documents while applications view logical measurements. You must understand the explain path.

**15. What do `$densify` and `$fill` do?**

`$densify` generates missing timestamps in the pipeline; `$fill` populates missing values per a chosen policy. Filled values do not become real measurements.

**16. Why do time series collections not automatically guarantee exactly-once measurements?**

Network retries can resend the same packet. You need a stable event ID and an appropriate deduplication/constraint mechanism; time series unique indexing differs from regular collections.

**17. Should you shard a time series collection by ascending timestamp?**

Not by default. Evaluate hot ranges, query targeting, metadata cardinality, and version-specific shard key rules.

**18. Does reading from a secondary make data fresher?**

No. Replication is asynchronous so secondaries can lag; choose read concern and causal consistency according to requirements.

**19. Is a separate current-state collection always required?**

Not always, but it is very useful for latest-value dashboards or mutable device state with frequent point lookups.

**20. When can a time series collection perform worse than a regular collection?**

When data is sparse with few points per meta value, schemas vary widely, metadata changes per record, queries target unique business IDs, flexible updates/deletes/transactions are required, or needed index patterns are unsupported.

## 47. Quick Reference Table

| Goal | Technique |
|---|---|
| Create time series | `db.createCollection("x",{timeseries:{timeField:"observedAt",metaField:"meta",granularity:"minutes"}})` |
| Filter sensor + time range | `{"meta.sensorId":"s-01",observedAt:{$gte:start,$lt:end}}` |
| Get latest observed | `sort({observedAt:-1}).limit(1)` |
| Group by hour | `$dateTrunc + $group` |
| Rolling average | `$setWindowFields` |
| Generate missing timestamps | `$densify` |
| Fill missing values | `$fill` |
| Enforce retention | `expireAfterSeconds` at creation / per version configuration |
| Inspect indexes | `getIndexes()` |
| Inspect execution plan | `explain("executionStats")` |
| Inspect storage | `stats()` / `collStats` |
| Maintain live state | Regular `sensorLatest` collection |
| Deduplicate events | Stable `eventId` + ledger/stream consumer |
| Long-term history | Hourly/daily rollups |
| Late events | Event time + receipt time + watermark/recompute |
| Optimize storage | Stable meta, right granularity, benchmark buckets |
| Very large datasets | Evaluate sharding, query targeting, analytics summaries |

## 48. Pre-Deployment Design Checklist

- [ ] Is each document a timestamped measurement/event rather than a mutable business entity?
- [ ] Have **event time** and **ingestion time** been accurately distinguished?
- [ ] Is `timeField` a BSON Date with timestamps normalized to UTC?
- [ ] Are past/future timestamp skew and timezones validated?
- [ ] Does `metaField` hold stable attributes identifying the series?
- [ ] Have per-record varying `requestId`/`receivedAt` fields been kept out of `meta`?
- [ ] Have cardinality and measurements per meta value been evaluated?
- [ ] Are `granularity`/bucket options matched to actual write cadence?
- [ ] Do primary meta + time-range queries have suitable indexes and execution plans?
- [ ] Is there a deduplication policy for duplicate measurements from retries?
- [ ] Are latest observed and latest received clearly separated?
- [ ] Does TTL retention account for bucket-level expiration and monitor delay?
- [ ] Are any per-measurement deletion needs compatible with version constraints?
- [ ] Are there update/upsert/unique/transaction requirements that make a regular collection more suitable?
- [ ] Do dashboards bound time ranges/points and use rollups where appropriate?
- [ ] Does `$densify/$fill` follow an explicit imputation policy rather than masquerading as raw data?
- [ ] Are data quality, missing coverage, outliers, and measurement units tracked?
- [ ] Is there a process for backfills and late arrivals, especially after summaries finalize?
- [ ] If sharded, is the shard key chosen for query targeting, throughput, and version support?
- [ ] Is event-to-ingest lag monitored separately from replication lag?
- [ ] Have compression, latency, and ingestion been benchmarked on a representative workload?
- [ ] Is there a migration/dual-write/reconciliation/cutover plan when switching storage types?
- [ ] Are backups, compliance retention, and downstream data stores accounted for?

## 49. Conclusion

**A time series collection is a storage model optimized for timestamped measurement history**, not a decorative label for any collection with a date field. MongoDB organizes logical measurements into **buckets** by timestamp and metadata, leveraging repeating schemas and series to compress data and accelerate certain time-range and aggregation queries. Realizing those gains requires choosing the right `timeField`, `metaField`, `granularity`, queries, indexes, and retention settings.

The biggest difference from a **regular collection** lies in **data organization and operational model**: time series collections fit append-heavy measurements and historical rollups; regular collections offer greater flexibility for mutable state, unique business records, and transactional workflows. A pragmatic design often stores **raw measurements in a time series collection**, **latest/current state in a regular collection**, and **hourly/daily summaries** in a separate read model.

Finally, treat timestamps, data quality, duplicate packets, late arrivals, TTL, and compression as integral parts of system design—not mere database flags. **The deciding benchmarks** are temporal correctness, bytes per measurement, ingestion throughput, query latency, and operational cost measured on a representative workload.
