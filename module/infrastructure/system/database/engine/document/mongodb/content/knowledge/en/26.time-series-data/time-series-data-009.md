# Evaluating Time Series Collections for Sensor Data and System Observability in MongoDB

An IoT platform may ingest temperatures from thousands of sensors every minute. An operations platform may record CPU, memory, request latency, error counts, and load metrics across many services at regular intervals. These records share common traits: **values are measured continuously over time, mostly appended rather than edited, and typically queried over a time range**.

In MongoDB, a **time series collection** is the collection type optimized for this workload. MongoDB packs matching measurements into internal **buckets**, organizing, compressing, and querying time series data more efficiently than treating every measurement as an independent document in a regular collection.

However, "the data has a timestamp" is **not automatically** a reason to choose a time series collection. A full-text logging system, a continuously updated device-status table, or a transactional store requiring per-record edits/deletes has very different requirements from sensor data. This lesson belongs to the **Time Series Data** chapter of the **Database Engine Document MongoDB** module, focusing on **evaluating suitability**, designing schemas, choosing options, operating in production, and conducting grounded comparisons against regular collections.

## 1. When Is a Problem Truly Time Series?

A **measurement** is a reading taken at a point in time:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    tenantId: "tenant-01",
    deviceId: "sensor-01",
    siteId: "factory-a",
    metric: "temperature_c"
  },
  value: 24.5,
  quality: "ok"
}
```

Here:

- `measuredAt`: **measurement timestamp**.
- `meta`: relatively stable attributes identifying **the data series source**.
- `value`: **measured value**, changing over time.
- `quality`: attribute of **one specific measurement**, which may vary between readings.

Typical questions include:

1. How did `sensor-01`'s temperature fluctuate over the last 30 minutes?
2. What are the per-minute, hourly, or daily averages and peaks?
3. During which intervals did a sensor stop transmitting?
4. Which API services saw CPU or error-rate spikes after a deployment?
5. Should raw data be retained for 7, 30, or 90 days, and how long must aggregated data be kept?

When most queries follow **filter by source + time range + windowed aggregation**, a time series collection is a strong candidate to evaluate.

### Not Every Timestamped Dataset Is Time Series

| Dataset | Characteristics | Initial suitability |
| --- | --- | --- |
| Temperature, humidity, pressure per minute | Append-oriented, filtered by sensor/time, windowed rollups | **Strong candidate** |
| Periodic CPU, RAM, request counts | Uniformly structured readings, queried by host/service/time | **Strong candidate** |
| Electricity consumption every 5 minutes | Many measurements per device, hourly/daily analytics | **Worth testing** |
| Current device state | Single document repeatedly `update`d to hold latest values | **Regular collection** is usually more natural |
| Customer profiles with `createdAt` | CRUD, ID lookups, profile edits, not measurement series analytics | **Insufficient reason** for time series |
| Audit ledgers needing custom edits/deletes and unique keys | Event history, yet strict transactional/index rules | **Evaluate limits carefully** |
| High-volume text logs and stack traces | Full-text search, string/tag queries, short retention | Query-dependent; dedicated log platforms may fit better |
| Distributed traces with volatile spans/attributes | Extremely high-dimensional metadata, queried by trace/span ID | **Benchmark and compare dedicated tools** |

This table is a starting guide, **not a benchmark**. Final choices depend on device count, cadence, query shapes, MongoDB version limits, index costs, update/delete needs, and SLAs.

## 2. How Do Time Series Collections Differ from Regular Collections?

In a regular collection, each measurement is stored as an individual BSON document and indexed directly under declared indexes. In a time series collection, the application still sees and operates on **logical measurement documents**, while MongoDB **organizes multiple related measurements into internal buckets**.

```text
             APPLICATION
                  |
         insertOne / insertMany
                  |
                  v
       time series collection
         (logical interface)
                  |
        MongoDB auto-bucketing
             /     |     \
            v      v      v
         Bucket 1 Bucket 2 Bucket 3
            |      |      |
          multiple measurements
          close together in time
          with matching metadata
                  |
       compression / internal storage
                  |
                  v
            QUERY RESULTS
         returned as measurements
```

This creates opportunities to:

- **Reduce storage footprint** by compressing sequences of values sharing types and structure.
- **Read more efficiently** when predicates narrow metadata and time, pruning irrelevant buckets.
- **Lower per-measurement overhead** compared to storing completely isolated documents on matching workloads.
- **Manage retention** of measurement data through time series collection configuration.

Buckets also have trade-offs: touching a bucket requires processing data inside it; fragmented metadata or very sparse writes underutilize buckets. Neither compression ratios nor read/write speedups are **guaranteed by a fixed factor**.

### Logical Collection vs. Internal Buckets

Users interact with:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
})
```

MongoDB manages the underlying internal bucket structures. Never read or write `system.buckets.sensorReadings` directly as a business API. Bucket layouts are **implementation details** that can change across versions.

## 3. Three Core Configuration Components

When creating a time series collection, two fields and one option are pivotal:

| Component | Role | How to choose |
| --- | --- | --- |
| **`timeField`** | Field holding measurement timestamp as BSON Date | Pick the appropriate event/observation timestamp; standardize UTC and precision |
| **`metaField`** | Optional field holding series-identifying attributes | Use attributes that stay stable across many measurements |
| **`granularity`** | Hint to MongoDB about measurement time spacing | `"seconds"`, `"minutes"`, or `"hours"` matching cadence and distribution |

**`timeField` is required** when creating a time series collection. `metaField` is syntactically optional, yet usually vital when multiple sensors or services must be grouped and queried independently.

### 3.1. Choosing `timeField`: Measurement Time or Receipt Time?

A device might measure at `08:00:00` yet reach the gateway at `08:00:12`.

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  receivedAt: ISODate("2026-11-14T08:00:12Z"),
  meta: { deviceId: "sensor-01" },
  value: 24.5
}
```

If reports ask for **temperature when the device measured**, pick `measuredAt` as `timeField`. If the problem tracks when messages arrived at a collector and device clocks are untrustworthy, `receivedAt` may be more appropriate.

Clearly distinguish:

- **Event time:** when the measurement or event actually occurred.
- **Ingestion time:** when the server or gateway received the payload.
- **Processing time:** when the application processed the event and wrote it to the sink.

Never pick a generic `createdAt` field at random if it fails to reflect the time axis dashboards intend to display.

### 3.2. Choosing `metaField`: Stable Attributes

Good example:

```javascript
meta: {
  tenantId: "tenant-01",
  siteId: "factory-a",
  deviceId: "sensor-01",
  metric: "temperature_c"
}
```

These values stay constant across many consecutive readings, letting MongoDB group and filter matching series cleanly.

Example requiring caution:

```javascript
meta: {
  deviceId: "sensor-01",
  batteryPct: 87,
  currentTemperature: 24.5,
  requestId: "req-unique-every-time"
}
```

Attributes like `batteryPct`, `currentTemperature`, and `requestId` change per measurement. Placing them inside metadata spawns excessive distinct metadata groups, hurting meaningful packing and inflating bucket overhead.

Better layout:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    deviceId: "sensor-01",
    siteId: "factory-a",
    metric: "temperature_c"
  },
  value: 24.5,
  batteryPct: 87,
  requestId: "req-001"
}
```

Here `batteryPct` and `requestId` sit as **measurement fields**, not series-grouping metadata.

**Do not assume fewer fields in `meta` is always better.** If every query scopes by tenant/site/device, keeping those **stable** dimensions in metadata is very helpful. Decide based on **metadata churn rate, combination counts, and query patterns**, not field count alone.

### 3.3. Choosing `granularity`

MongoDB offers standard granularity settings:

```text
seconds   -> dense streams, cadence in seconds or faster
minutes   -> values changing every few minutes
hours     -> sparser data, hourly observations
```

This is a **bucketing hint**, not a requirement that every record's timestamp align on minute or hour boundaries. A reading at `08:00:17` inserts cleanly into a collection with `granularity: "minutes"`.

Granularity shapes bucket time spans and compression/read trade-offs. Setting granularity too wide for the actual cadence can over-read data on short-range queries; setting it too narrow can under-pack sparse series.

Some MongoDB versions allow custom bucket bounds via `bucketMaxSpanSeconds` and `bucketRoundingSeconds`. **Available options, constraints, and post-creation modifiability depend on version**; do not mix these arbitrarily with `granularity` if unsupported by your server.

## 4. Creating the Sensor Collection in `mongosh`

In a dedicated practice database:

```javascript
use mongo_time_series_lab

db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 2592000
})
```

Meaning:

- `sensorReadings` is the logical **time series collection**.
- `measuredAt` holds each measurement's BSON Date.
- `meta` distinguishes source series groups.
- `"seconds"` is the granularity chosen for a demo with 10-second intervals.
- `expireAfterSeconds: 2592000` configures roughly **30-day** retention for raw data. Actual bucket-based TTL cleanup is asynchronous and not "exact to the millisecond at 30 days".

**Note:** run this only on a **non-existent** lab collection. If the collection already exists, `createCollection()` errors out. Never drop and recreate a live collection just to swap collection types or TTL.

### Inspecting Collection Type After Creation

```javascript
db.getCollectionInfos({ name: "sensorReadings" })
```

Collection metadata shows options including `timeseries`, `expireAfterSeconds`, and related fields. In real environments, cross-check against your MongoDB server version and active retention policy.

### You Cannot Turn a Regular Collection into Time Series by Renaming

Time series collections use dedicated storage and operational rules. If data currently lives in a regular collection, **plan a migration**: create a new time series collection, load normalized data, switch queries/writers, reconcile, and cut over.

Renaming a collection or adding indexes to a regular collection **never converts** it into a time series collection.

## 5. Loading Sample Data and Reading It Back

Insert eight temperature readings from two sensors using UTC timestamps and uniform Celsius units in `value`:

```javascript
db.sensorReadings.insertMany([
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 24.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:20Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 25.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:40Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 26.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:00Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 27.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:20Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 28.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:10Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 19.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:30Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 20.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:10Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 21.0, quality: "ok"
  }
])
```

Time series collections support familiar logical read operations:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
}).sort({ measuredAt: 1 })
```

The logical result returns five measurements for `sensor-01` with values `24, 25, 26, 27, 28` in ascending chronological order. Users never unpack buckets manually.

**Never rely on insertion order for chronological display.** Real events can arrive late or out of order; any report requiring order must explicitly apply `sort({measuredAt: ...})` or an ordered aggregation.

## 6. Right Query Pattern: Metadata + Time Range

A standard query fetching one device's temperature over a half-open interval **`[start, end)`**:

```javascript
db.sensorReadings.find({
  "meta.tenantId": "tenant-01",
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:01:00Z")
  }
}, {
  _id: 0,
  measuredAt: 1,
  value: 1
}).sort({ measuredAt: 1 })
```

On the sample data, this returns three points:

```text
08:00:00Z   24.0
08:00:20Z   25.0
08:00:40Z   26.0
```

Using **`[start, end)`** ensures that querying the next minute with `$gte` new start and `$lt` new end never double-counts boundary points.

### Query Shapes to Evaluate

| Question | Predicate | Guidance |
| --- | --- | --- |
| Single sensor over 10 minutes | `meta.deviceId` + `measuredAt` range | Ideal match for the model |
| All sensors at a site | `meta.siteId` + time range | May read many series; evaluate indexes and volume |
| Temperatures over threshold in 24 hours | time range + `value > threshold` | May scan many measurements |
| Latest value of one sensor | `meta.deviceId` + descending time sort + limit | Index and data layout are critical |
| All errors in a month | `quality: "bad"` + time range | If errors are rare, evaluate index or separate summary/alert table |
| Error rate for a service | service identity + time window + aggregate | Suits monitoring when metric schema is well structured |

**Always enforce tenant predicates derived from authenticated context.** Performance optimizations never substitute for tenant authorization checks.

## 7. Indexes: Bucket Optimization Does Not Eliminate Indexes

While time series collections organize buckets by time and metadata, frequent queries still benefit from appropriate secondary indexes.

Common query example:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({ measuredAt: -1 }).limit(100)
```

On MongoDB versions supporting matching time series indexes, consider:

```javascript
db.sensorReadings.createIndex(
  { "meta.deviceId": 1, measuredAt: -1 },
  { name: "idx_device_time_desc" }
)
```

Indexes locate matching devices and time ranges, yet **do not guarantee** queries are served purely from the index. MongoDB may still unpack buckets and filter measurements.

### Do Not Blindly Create Every Possible Index

Indexes carry costs:

- Disk storage.
- CPU and I/O during ingestion.
- Memory footprint for hot index structures.
- Index maintenance overhead as retention expires data.

If queries mainly filter `tenantId + deviceId + time`, evaluate an index covering **the full filter prefix** rather than separate single-field indexes. In multi-tenant setups, identical `deviceId`s can exist across tenants; align indexes and predicates with the true identifying key.

### Depending on Version, Default Indexes May Already Exist

Different MongoDB releases create or support different time-series indexes, including default indexes on `metaField` and `timeField`. **Run `getIndexes()` on your live environment before creating duplicates**:

```javascript
db.sensorReadings.getIndexes()
```

Secondary indexes on measurement fields, partial/TTL indexes, unique indexes, and specialized structures all carry **version-specific constraints**. Never copy a regular collection's index list onto a time series collection without verifying documentation for your version.

## 8. Reading `explain()`: Bucket and Measurement Access

Run:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
}).explain("executionStats")
```

Time series `explain` output reveals bucket and unpacking steps. Exact stage names vary by server version and query engine; look for stages involving **bucket unpacking**, metadata/time filters, and index usage.

Key questions:

1. Can the server **prune buckets outside the queried time range**?
2. Does the query use an index matching `meta.deviceId` and `measuredAt`?
3. Are excessive unrelated measurements being unpacked?
4. Do multi-sensor buckets force reading more buckets than expected?
5. Do post-unpack sorts or aggregations add substantial work?

**Never compare time series `totalDocsExamined` directly 1:1 with regular-collection measurement counts without knowing what is being counted.** Depending on the plan, part of that metric reflects **internal bucket documents** rather than returned logical measurements. Evaluate the full plan, returned measurements, buckets processed, and actual latency.

### Example of Sound Interpretation

Compare two queries in `explain`:

```text
Query A:
  deviceId = sensor-01
  time range = 2 minutes
  few buckets, few measurements, small sort

Query B:
  all devices
  time range = 30 days
  many buckets and measurements
```

Query A outperforming Query B is expected due to vastly smaller read volume, not proof of a bug. Fair benchmarks compare **identical logical data volume**, query shapes, and SLA requirements.

## 9. Windowed Aggregations

A natural strength of time series is computing averages, minimums, maximums, and counts over time windows.

### 9.1. Per-Minute Average with `$dateTrunc`

```javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "tenant-01",
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:02:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        minute: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgValue: { $avg: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  { $sort: { "_id.deviceId": 1, "_id.minute": 1 } }
])
```

On the lab dataset:

| Device | Minute UTC | Samples | Average | Min | Max |
| --- | --- | ---: | ---: | ---: | ---: |
| `sensor-01` | 08:00 | 3 | 25.0 | 24 | 26 |
| `sensor-01` | 08:01 | 2 | 27.5 | 27 | 28 |
| `sensor-02` | 08:00 | 2 | 19.5 | 19 | 20 |
| `sensor-02` | 08:01 | 1 | 21.0 | 21 | 21 |

`$dateTrunc` aligns window boundaries; `$group` aggregates measurements per device and minute. `sampleCount` reveals sample coverage, essential when sensors drop readings.

### 9.2. Do Not Confuse Sample Mean with Time-Weighted Mean

If a sensor reports at `08:00`, `08:01`, and `08:50`, `$avg` weights all three readings equally. It **does not compute a time-weighted average** across the 50-minute span.

For irregularly spaced readings:

- **Sample mean:** arithmetic average of received samples.
- **Time-weighted mean:** weighted by the time duration each reading represents.
- **Integral / area under curve:** accumulated over time, suitable for power/energy conversions.

Choose the aggregation method matching **sensor physics and sampling rules**, rather than assuming `$avg` fits every metric.

### 9.3. Distinguish Counters from Gauges

In observability:

- **Gauge:** values that go up or down, e.g., CPU %, temperature, memory usage.
- **Counter:** cumulative monotonically increasing totals, e.g., total requests or total bytes, which may reset on process restarts.
- **Histogram / summary:** latency distribution structures that must never be summed or averaged like arbitrary scalars.

For example, storing cumulative `http_requests_total` and taking `$avg` to report "requests/sec" is **semantically wrong**. Throughput requires computing **deltas over time while handling counter resets**, via appropriate window logic or precomputed deltas/rates.

## 10. Recent Queries and Gap Detection

### Fetching the 10 Latest Measurements

```javascript
db.sensorReadings.find({
  "meta.tenantId": "tenant-01",
  "meta.deviceId": "sensor-01"
}, {
  _id: 0, measuredAt: 1, value: 1
}).sort({ measuredAt: -1 }).limit(10)
```

If two events share the exact same `measuredAt`, sorting by timestamp alone **leaves their relative order undefined**. When strict total ordering is required, add a reliable sequence/measurement ID and sort deterministically—never rely on physical bucket order.

### Silent Sensors

A query taking `max(measuredAt)` per device reveals the last reading only for devices **already present in the collection within retention**.

To detect sensors that have never reported or went silent before the retention window, maintain a separate device catalog:

```text
devices (regular collection):
  deviceId, expectedInterval, active, site

sensorReadings (time series):
  meta.deviceId, measuredAt, value

Monitoring service:
  compares devices.expectedInterval
  against lastSeen or latest measurement
```

Time series collections store measurement history; **a device that sends nothing** creates no document to query. Keeping **master data** in a regular collection separates registry concerns from measurement history.

### Missing Samples Are Not Zero

If a sensor transmits at `08:00` and `08:02` while missing `08:01`, never substitute `0` automatically; the device may have failed, lost connectivity, or stopped transmitting. If dashboards require continuous lines, define fill/interpolation policies explicitly, distinguishing **real values**, **imputed values**, and **missing data**.

MongoDB provides version-dependent pipeline operators for time series and window gaps; gap-filling rules must still come from business semantics.

## 11. Metadata Cardinality and Bucket Overhead

Metadata **cardinality** is the number of distinct combinations the system tracks. For sensors:

```text
10,000 devices
       x 1 metric
       = 10,000 metadata series

10,000 devices
       x 20 metrics
       = 200,000 metadata series
```

These are logical series counts. Open/created bucket counts also depend on cadence, time spans, distribution, and MongoDB's internal bucket management.

### Stable High-Cardinality Metadata

High `meta.deviceId` cardinality (one distinct value per device) **is not inherently wrong**. It is often necessary to isolate series and support per-sensor queries. Problems arise when series count and cadence combine to cause:

- Constant bucket opening and closing churn.
- Large bucket-catalog memory consumption.
- Few readings per bucket and poor compression.
- Bloated indexes and metadata overhead.
- Queries forced to touch many unrelated series.

### Metadata Changing Per Event Is Far More Dangerous

Putting `requestId` or per-event timestamps into `meta` makes nearly every measurement carry unique metadata, severely undermining bucket packing.

**A sound rule of thumb:** metadata should identify the **measurement series**, while values varying **within that series** belong in measurement fields. Balance this against real-world observability label needs.

### Beware Overly Dynamic Labels in Monitoring

Consider a CPU metric record:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    service: "checkout",
    host: "node-03",
    environment: "prod",
    metric: "cpu_percent"
  },
  value: 68.2
}
```

Contrast with:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    service: "checkout",
    host: "node-03",
    metric: "cpu_percent",
    requestId: "random-unique-1234",
    pathWithUserId: "/users/983473/orders"
  },
  value: 68.2
}
```

`requestId` and user-specific URL paths make metadata combinations nearly unique. Beyond storage cost, stuffing trace/log attributes into `meta` raises privacy, schema-consistency, and bloat issues. Pick **low-entropy, stable dimensions** for series identity and store per-event attributes elsewhere.

## 12. Event Time, Device Lag, and Late Measurements

A device may go offline for two hours and then flush buffered data:

```text
08:00 device measures 24.5 °C
08:01 device measures 24.8 °C
      network outage
10:00 connectivity restored
10:01 gateway sends both historical samples
```

With `timeField: "measuredAt"`, both documents retain `08:00` and `08:01` while ingestion time is `10:01`. Event-time queries place them accurately in history.

### What Can Be Affected?

- **Bucket efficiency:** late measurements may land in matching buckets if still eligible or trigger extra bucket work depending on state and volume.
- **Near-real-time dashboards:** latest by `measuredAt` differs from most recently ingested.
- **Rollups:** previously computed minute/hour summaries may need recomputation upon late arrivals.
- **TTL:** very old data may already approach or exceed expiration immediately on ingest.
- **Deduplication:** device retries can create duplicates without explicit dedup controls.

Never overwrite a measurement's timestamp with `new Date()` just to make late data "look fresh". If both timestamps matter, store **`measuredAt` and `receivedAt`** with clear semantics.

### Untrustworthy Sensor Clocks

A misconfigured sensor clock can emit 1970 or future dates, causing:

- Readings landing in unintended buckets.
- Real-time range queries missing the readings.
- Retention expiring valid data prematurely or keeping future data indefinitely.
- False dashboard alerts.

Add validation/normalization at the ingestion gateway: check bounds against server clock, monitor skew, verify NTP sync, and flag suspect readings. MongoDB time series collections cannot automatically detect whether a device clock is lying.

## 13. Retention via `expireAfterSeconds`

Observability data typically uses tiered retention:

```text
Raw measurements:       retain 7-30 days
1-minute rollups:       retain 90 days
1-hour rollups:         retain 1-2 years
Critical audit logs:    custom retention policy
```

Time series collections support expiration, for example:

```javascript
db.createCollection("cpuRaw", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
})
```

`604800` seconds equals 7 days. MongoDB applies time series TTL per configuration and data lifecycle.

### TTL Is Not a Per-Document Exact Deletion Clock

MongoDB manages time series by bucket. One bucket can hold measurements across different timestamps; a bucket qualifies for removal only after contained measurements pass expiration rules. The TTL process runs **asynchronously**, so visibility can lag past `timeField + expireAfterSeconds`.

Therefore:

- **Never treat TTL as an exact-to-the-second deletion SLA.**
- **Never rely on TTL alone for immediate personal-data erasure** when regulations demand prompt exact deletion.
- **Never confuse measurement time with ingest time** when sizing retention.
- **Never overlook version-specific limits on deleting/editing individual measurements** in time series collections.

If conditional deletion by tenant, device, or legal mandate is required, verify supported delete/update operations, bucket impact, and data governance—an alternative storage design may be needed.

### Modifying Retention After Creation

MongoDB supports updating certain collection options via `collMod` on supporting versions, including expiration/time-series settings. **Never assume every parameter can change freely or `granularity` can shrink arbitrarily**; exact capabilities depend on version.

Before changing production retention, evaluate data volume becoming immediately eligible for expiration, cleanup I/O, backups, and impact on downstream rollups reading raw data.

## 14. Rollups and Downsampling to Control Long-Term Costs

If dashboards primarily inspect 30-day hourly trends, scanning millions of raw points on every load is wasteful. Store **windowed summary tables** instead:

```text
sensorReadings (raw time series)
      |
      | per-minute aggregation
      v
sensorMinuteRollup (summary collection)
      |
      | hourly aggregation
      v
sensorHourRollup
      |
      v
Long-term dashboards
```

Example building per-minute rollups from ingested data:

```javascript
db.sensorReadings.aggregate([
  {
    $match: {
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:02:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        minute: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      sumValue: { $sum: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  {
    $set: {
      avgValue: {
        $divide: ["$sumValue", "$sampleCount"]
      }
    }
  },
  {
    $merge: {
      into: "sensorMinuteRollup",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
```

Here `sensorMinuteRollup` is a **regular collection** holding summaries. `$merge` replaces existing summaries sharing `_id` when windows recompute.

**Note:** re-running windowed rollups refreshes results for late arrivals. Because this pipeline recomputes strictly from the matched window, schedulers must re-run **entire affected windows** rather than feeding partial new arrivals into a `replace`.

### Why Retain `sumValue` and `sampleCount`?

When rolling up per-minute summaries to hourly summaries, never average per-minute `avgValue`s directly if sample counts differ per minute.

Example:

```text
Minute 08:00: 3 samples, avg = 25.0
Minute 08:01: 2 samples, avg = 27.5

Mean of all 5 samples = (3*25.0 + 2*27.5) / 5 = 26.0

Mean of the two minute averages = (25.0 + 27.5)/2 = 26.25
                                  (not 26.0)
```

Retaining `sumValue` and `sampleCount` enables **sample-weighted means**. Duration-weighted means require explicit time-interval weighting rules.

### Rollups Cannot Reconstruct Discarded Detail

Once raw data expires via TTL, minute/hour summaries preserve aggregates but cannot restore individual readings, exact outliers, or event order. Decide what granularity incident investigations and reports require before purging raw data.

## 15. Scale: Estimating Measurement Volume Before Benchmarking

Assuming each sensor emits one document per minute:

```text
Measurements/day = sensors × 60 min/hour × 24 hours
                 = sensors × 1,440
```

| Sensors | Cadence | Measurements/day | Over 30 days |
| ---: | --- | ---: | ---: |
| 100 | 1 minute | 144,000 | 4,320,000 |
| 1,000 | 1 minute | 1,440,000 | 43,200,000 |
| 5,000 | 1 minute | 7,200,000 | 216,000,000 |
| 10,000 | 1 minute | 14,400,000 | 432,000,000 |

If 10,000 sensors report **every second**, daily volume jumps from 14.4 million to **864 million**—dramatically shifting ingestion, indexing, retention, storage, network, and operations.

These numbers are **logical counts**, not disk bytes. Actual disk footprint depends on:

- BSON size per measurement.
- Metadata shape and cardinality.
- Bucketing and compression efficiency.
- Secondary indexes.
- Temporal distribution, late arrivals, and retention.
- Replica set copies, oplog, backups, and system overhead.

Never predict disk footprint by multiplying "measurement count × JSON text size on screen". BSON encoding, compression, buckets, and indexes behave very differently.

## 16. Fair Benchmarking: Time Series vs. Regular Collections

A rigorous engineering evaluation compares **two separate collections** holding identical logical data:

```text
sensorReadingsTs
  time series collection
  timeField=measuredAt, metaField=meta

sensorReadingsRegular
  regular collection
  identical logical measurement shape
```

Load identical realistic datasets into both—never just a few documents. Simulate production characteristics:

- Steady and burst ingest rates.
- Realistic series counts (`tenant`/`site`/`device`/`metric` combinations).
- Late and out-of-order arrival percentages.
- Mix of single-sensor, site-wide, and all-sensor queries.
- Query windows of 5 minutes, 1 hour, 1 day, and 30 days.
- Aggregation/rollup queries and latest-value lookups.
- Equivalent retention policies and query-serving secondary indexes.

### Metrics to Collect

| Group | Metric | Question |
| --- | --- | --- |
| Ingest | Documents/sec, p95/p99 latency | Can the server sustain write rates and bursts? |
| Query | p50/p95/p99 latency | Do dashboards and alerts meet SLAs? |
| Scan | Buckets/measurements examined, keys/docs examined per plan | Are excessive buckets unpacked needlessly? |
| Storage | Data size, storage size, index size | Does total footprint shrink after compression and indexes? |
| Resource | CPU, RAM, I/O, cache pressure | Does saving one resource overload another? |
| Retention | Cleanup duration and overhead | Does TTL trigger I/O spikes or hurt queries? |
| Stability | Ingest errors, backlogs, replication lag | Is the system stable under sustained load? |
| Operations | Deletes, edits, rebuilds, backups | Does the collection type fit operational workflows? |

### Two Benchmarking Mistakes That Mislead Teams

**Mistake 1:** Loading a few hundred documents and concluding time series is no faster. Tiny datasets fail to show bucketing, compression, and index differences.

**Mistake 2:** Creating many secondary indexes on the regular collection while omitting equivalent query-serving indexes on time series, then comparing storage sizes to claim time series always saves space. Compare **complete workloads with all indexes needed to meet identical SLAs**.

There is no universal compression percentage or "always X times faster" multiplier. Benchmark on representative data.

## 17. Inspecting Storage and `explain` in the Lab

Useful inspection commands:

```javascript
db.sensorReadings.stats()
```

```javascript
db.sensorReadings.getIndexes()
```

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
}).explain("executionStats")
```

When comparing sizes, inspect server-reported metrics: `count`, logical size, storage/index sizes, and any version-exposed bucket/compression stats. Never equate identically named metrics blindly if their semantics differ between regular and time series collections.

### Query Plans Do Not Equal End-to-End Endpoint Latency

`explain` reveals indexes, bucket unpacking, and examined data, whereas endpoint latency also includes:

- Server selection and network round-trips.
- Driver BSON decoding/encoding.
- Aggregation, JSON serialization, and dashboard rendering.
- Application caching.
- Concurrent load and cluster contention.

A query with an optimal plan returning millions of measurements still makes endpoints crawl over the network. Bound ranges, limits, and rollups to screen needs.

## 18. Sensor Data vs. Observability Metrics: Similarities and Differences

### 18.1. Similarities

Both domains typically:

- Require a mandatory **timestamp**.
- Are **append-oriented** at regular cadences or per event.
- Have **relatively stable source/unit/label attributes**.
- Are queried by time range and grouped.
- Require retention and downsampling policies.

Thus, both can benefit from bucketing, compression, and metadata/time queries.

### 18.2. Structural and Semantic Differences

| Factor | Physical sensors | Monitoring / observability |
| --- | --- | --- |
| Identity | `deviceId`, `siteId`, `sensorType` | `service`, `host`, `pod`, metric name, `environment` |
| Units | °C, Pa, kWh, %RH | %, bytes, requests/s, ms |
| Missing samples | Device power/network loss | Collector/exporter failure, deploys, churn |
| Timestamps | Device/gateway clocks | Collector/application clocks |
| Values | Gauges, counters, device states | Gauges, counters, histograms, tracing spans |
| Metadata churn | Physical relocations | Frequent pod/container churn |
| Common queries | Single sensor/time range, site reports | Service comparisons, label alerts, windowed aggregates |

### 18.3. Host/Pod Churn Destabilizes Metadata

In Kubernetes, `podUid` or container instances change on every deploy. Treating every pod ID as a new series rapidly multiplies series counts over time. You may need both **logical service identity** and **instance identity**, without blindly stuffing every ephemeral label into `meta`.

A common design separates:

- **Logical series:** `service`/`metric`/`environment`, ideal for aggregate dashboards.
- **Instance details:** `host`/`pod`, useful for debugging despite high churn.
- **Measurement values:** numeric metrics being analyzed.

Choosing one or multiple series levels depends on query, alerting, and aggregation requirements.

## 19. Schema Design: One Metric Per Document or Multiple Metrics?

### Approach A — One Metric Per Measurement

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    host: "api-01",
    service: "checkout",
    metric: "cpu_percent"
  },
  value: 68.2
}
```

Pros:

- Each document represents one metric with unambiguous units and semantics.
- Querying a single metric is straightforward.
- Adding new metrics requires no schema changes to existing documents.

Cons:

- Document count scales with **metrics per source**.
- `meta.metric` multiplies series counts.
- Dashboards showing multiple metrics together require joins/pivots or grouping.

### Approach B — Multiple Metrics in One Measurement

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    host: "api-01",
    service: "checkout"
  },
  cpuPercent: 68.2,
  memoryBytes: NumberLong("4294967296"),
  requestCount: NumberLong("123456"),
  errorCount: 7
}
```

Pros:

- Fewer documents when metrics are **sampled together**.
- A single read fetches multiple correlated metrics.
- Fewer metadata combinations.

Cons:

- Metrics sampled at different cadences create sparse/`null` fields or mismatched timestamps.
- Adding/removing metrics makes schemas less uniform; track units and gauge/counter types carefully.
- Per-metric queries or cross-metric aggregations need distinct projections/indexes.

Neither form wins universally. Measure **sampling synchronization**, common queries, and schema stability. For unsynchronized metrics, separate series model reality more cleanly.

## 20. Time Precision and Data Types

MongoDB BSON Date represents instants at millisecond precision. When sensors emit microsecond/nanosecond samples or multiple samples per millisecond, add an explicit **sequence or sub-millisecond field** if exact ordering is required:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00.123Z"),
  meta: { deviceId: "sensor-01" },
  sequence: NumberLong("9001"),
  value: 24.5
}
```

`sequence` is business data, not a replacement for `timeField`. Sort by `measuredAt` then `sequence` for deterministic ordering. Enforce uniqueness/deduplication separately rather than assuming time series collections offer regular unique constraints.

### Store in UTC, Display/Aggregate by Timezone

Standardize storage timestamps in UTC:

```javascript
ISODate("2026-11-14T08:00:00Z")
```

When dashboards group by local time:

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

Distinguish **UTC days** from **business-timezone days**. If a factory operates on local days, grouping by UTC and relabeling as local days introduces boundary errors.

### Missing/`null` Values and Data Quality

Never convert faulty readings into `0` when `0` is a valid physical reading. Represent NaN, unreadable sensors, or timeouts explicitly:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:02:00Z"),
  meta: { deviceId: "sensor-01" },
  value: null,
  quality: "sensor_timeout"
}
```

When computing `$avg`, understand MongoDB's `null`/missing semantics and track **valid sample count separately from error sample count**, instead of trusting an average alone.

## 21. Updates, Deletes, and Upserts: Evaluate Limitations Upfront

Time series workloads are **append-oriented**. MongoDB time series collections are not 100% drop-in equivalents to regular collections across updates, deletes, upserts, indexing, and transactions.

Across MongoDB releases, update/delete support has evolved while keeping **specific restrictions on `metaField`, document counts, and command types**. Therefore:

- **Never assume** `updateOne()`, `replaceOne()`, `findOneAndUpdate()`, `upsert`, or update pipelines behave identically on time series.
- **Never design a system editing millions of measurements daily** without verifying supported operations and benchmarking.
- **Never write directly to internal buckets** to circumvent API limits.
- If sensor errors require corrections, define a versioned correction/retraction workflow compatible with your server version.
- If business rules require immediate deletion of arbitrary individual measurements, verify delete support and retention limits—another collection type may fit better.

### When Data Corrections Happen Frequently

Consider two strategies:

1. **Append correction events:** leave raw readings untouched, log versioned correction events, and compute effective values during aggregation. Preserves full audit history at the cost of more complex queries.
2. **Edit/rebuild segments:** if supported by server and workload, delete/re-insert or rebuild affected windows while checking time series restrictions and rollup impact.

If the core workload is **looking up by ID and continuously mutating documents**, a regular collection usually fits better even if records carry timestamps.

## 22. Duplicate Measurements and Idempotent Ingestion

A gateway sends `msg-001`, misses the ACK due to timeout, and retries:

```text
Sensor --> Gateway --> MongoDB insert measurement
              |
         ACK lost on network
              |
              v
         Gateway retries
```

Without deduplication, two identical measurements are stored, skewing `$avg`, `$sum`, and `sampleCount`.

A reliable measurement identity can use:

```text
(tenantId, deviceId, metric, deviceSequence)
```

or a gateway-generated event ID. However, **never assume** time series collections support every **unique index** pattern from regular collections. Evaluate:

- Can consumers deduplicate via a durable **ingestion ledger** or queue?
- Can a **regular collection** enforce a unique constraint on event IDs alongside or ahead of measurements?
- Can duplicates be tolerated temporarily and reconciled in batch under explicit rules?
- Are retries using driver retryable writes and proper session semantics?

For billing or energy metering, duplicate counts carry financial impact—idempotency is a core architectural requirement of using time series, not an afterthought.

## 23. Sharding and Load Distribution

Time series collections work on supported sharded cluster topologies. However, **creating a time series collection does not automatically shard it**, and shard key choices face version-specific limits.

Questions to answer:

1. Do most queries filter on `tenantId`, `deviceId`, or service?
2. Can one sensor or tenant create a write **hotspot** on a single shard?
3. Are a few tenants orders of magnitude larger than others?
4. Do measurements in a metadata group need colocation for fast queries?
5. Do global cross-sensor queries require fan-out across shards?
6. Are candidate shard key fields/expressions **supported on time series in your MongoDB version**?

Prefer **metadata-based routing** so single-device queries avoid scatter-gather across shards, while balancing write spread and chunk distribution.

### Never Confuse Time Series Buckets with Shard Chunks

- **Bucket:** internal storage unit packing time series measurements.
- **Shard-key range / chunk:** distribution unit across shards.

These serve distinct goals: bucketing optimizes compression and time-series reads; sharding scales data and load across machines. Never assume "many buckets automatically means many shards".

### Shard Keys and Server Versions

Time series shard key rules have evolved across MongoDB versions—including constraints on time/metadata fields, hashed keys, and resharding. Before designing a production cluster, consult exact **time series sharding restrictions** for your server version rather than copying regular-collection patterns.

## 24. Java MongoDB Sync Driver Code

In Java, applications create time series collections with `CreateCollectionOptions` and `TimeSeriesOptions`, then insert and query documents normally.

Illustrative example with Java and a compatible MongoDB Java Sync Driver:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;

public class SensorTimeSeriesDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_time_series_lab_java");

            TimeSeriesOptions tsOptions =
                new TimeSeriesOptions("measuredAt")
                    .metaField("meta")
                    .granularity(TimeSeriesGranularity.SECONDS);

            CreateCollectionOptions createOptions =
                new CreateCollectionOptions()
                    .timeSeriesOptions(tsOptions);

            // Run once on an empty lab database.
            db.createCollection("sensorReadings", createOptions);

            MongoCollection<Document> readings =
                db.getCollection("sensorReadings");

            Document metadata = new Document(
                "tenantId", "tenant-01")
                .append("siteId", "factory-a")
                .append("deviceId", "sensor-01")
                .append("metric", "temperature_c");

            readings.insertOne(
                new Document("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T08:00:00Z")))
                    .append("meta", metadata)
                    .append("value", 24.5)
                    .append("quality", "ok")
            );

            Bson filter = Filters.and(
                Filters.eq("meta.tenantId", "tenant-01"),
                Filters.eq("meta.deviceId", "sensor-01"),
                Filters.gte("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T08:00:00Z"))),
                Filters.lt("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T09:00:00Z")))
            );

            for (Document measurement : readings
                    .find(filter)
                    .sort(Sorts.descending("measuredAt"))) {
                System.out.println(measurement.toJson());
            }
        }
    }
}
```

This avoids hardcoding credentials by reading `MONGODB_URI`. `createCollection` requires collection-creation privileges and fails if the collection already exists. In production services, manage schema, indexes, and retention via controlled migrations rather than on every application startup.

### Configuring Retention in Java

Depending on your MongoDB Java Sync Driver version, `CreateCollectionOptions` exposes APIs to configure time series expiration. If your driver version lacks a helper for a newer option, run the corresponding database command directly. **Never guess method names across driver versions**; check your actual build's API docs.

### Java `Date` and Sensor Precision

`java.util.Date` serializes to BSON Date at millisecond precision. `Instant.parse(...Z)` expresses UTC explicitly. If sources require sub-millisecond precision, persist an explicit sequence or precision field.

## 25. Comparing Time Series Against a Regular Collection Model

Suppose a system stores temperatures for 5,000 devices over 30 days, mostly serving 24-hour charts and per-minute rollups.

### Model A — Regular Collection

```javascript
db.sensorReadingsRegular.insertOne({
  measuredAt: new Date(),
  deviceId: "sensor-01",
  value: 24.5
})
```

With index:

```javascript
db.sensorReadingsRegular.createIndex({
  deviceId: 1,
  measuredAt: -1
})
```

Pros: familiar CRUD and index semantics, supporting features restricted on time series. Cons: lacks specialized time-series bucketing and columnar compression, potentially consuming more space or overhead on dense telemetry workloads.

### Model B — Time Series Collection

```javascript
db.createCollection("sensorReadingsTs", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
})
```

Pros: storage and data model purpose-built for timestamped measurements. Cons: requires thoughtful metadata/granularity design, understanding bucket/TTL behavior, and working within version-specific operational limits.

### Workload-Based Decision Matrix

| Criterion | Regular collection | Time series collection |
| --- | --- | --- |
| Continuous measurement appends | Capable | **Standout candidate** |
| Many readings per metadata group close in time | No specialized bucketing | Strong compression/optimization opportunity |
| Metadata + time range queries | Index-supported | Supported with time-series optimizations |
| Frequent single-measurement edits/deletes | Standard CRUD | Version-dependent limits; evaluate carefully |
| Diverse indexes and unique constraints | More flexible in many cases | Dedicated restrictions |
| Time-based retention | TTL index or custom purge | Built-in time series expiration |
| Permanent immutable audit events | Custom ledger design | Oplog/TTL do not replace ledgers; review requirements |
| Very sparse data with per-event changing metadata | Stores cleanly | Poor bucketing and compression |
| Streaming multi-metric queries | Supported | Supported with clean series modeling |

**Never conclude time series is always superior.** If your application depends on unique business keys, frequent field updates, or unsupported index/schema constraints, the simplicity of a regular collection can be a major advantage.

## 26. What to Verify Against Your MongoDB Version

Time series features evolve rapidly across MongoDB releases. In production, consult server and driver docs for:

1. Supported `timeseries` creation options and `collMod` changes.
2. Secondary index support, allowed types, and default indexes.
3. Update, delete, upsert, and `replaceOne` rules.
4. Transaction, change stream, schema validation, and special operation support.
5. Sharding: eligible keys, routing optimizations, resharding, and collection limits.
6. TTL, partial TTL, and bucket expiration rules.
7. Time-series-specific aggregation operators and query engine behavior.

**Never test an example on one MongoDB version and assume it works identically on every version.** If a critical feature is unsupported on your target release, choose an alternative model or plan an upgrade.

### Does Sensor Data Need Change Streams?

Monitoring architectures may want to store measurements and emit real-time events. **Never assume** regular-collection Change Stream behavior applies identically to time series collections on your version. If CDC is needed for alerts or downstream services, verify **time series Change Stream support/restrictions**. Often, emitting events from a dedicated **ingestion pipeline/queue** is simpler and more reliable than depending solely on storage-layer CDC.

## 27. Reference Architecture for IoT and Observability

```text
              Devices / Agents / Exporters
                         |
                         v
                  Ingestion Gateway
                 /       |       \
          validate   dedupe     normalize UTC
                         |
                         v
               Durable Queue (if needed)
                         |
                         v
                MongoDB Time Series
                     raw samples
                         |
              +----------+----------+
              |                     |
              v                     v
         Alert Service         Rollup Worker
       (thresholds/rates)    (min / hour / day)
              |                     |
              v                     v
           Alert Log           Summary Collections
              |                     |
              +----------+----------+
                         |
                         v
                    Dashboard API
```

This is one viable architecture, **not a mandate to add a queue everywhere**. Small, low-traffic systems can write directly from the gateway to MongoDB. When traffic spikes or sinks slow down, a durable queue decouples ingestion speed from storage/aggregation rates.

Recommended component separation:

- **Device/service catalog:** current metadata, sensor config, active status (regular collection).
- **Raw measurements:** timestamped readings (time series candidate).
- **Rollups:** precomputed time-bucketed summaries (summary collections).
- **Alerts/events:** alert history with its own business lifecycle.
- **Ingestion dedupe ledger:** tracks event IDs when strict deduplication is required.

This separation avoids cramming every timestamped requirement into one time series collection.

## 28. Pre-Selection Evaluation Process

Follow these steps before adopting a time series collection:

1. **Classify the data:** true append-only measurements or mutable state / general event log?
2. **Define timestamp semantics:** event time, ingest time, timezone, precision, and late arrivals.
3. **Design metadata:** which dimensions stay stable? How many series? Any high-churn labels?
4. **Select initial granularity:** `seconds`/`minutes`/`hours` matching cadence and query window width.
5. **Define retention:** raw retention, rollup retention, and any special deletion rules.
6. **Inventory query shapes:** device/site/time range, global analytics, latest point, alert thresholds.
7. **Check version/feature limits:** indexes, updates/deletes, transactions, CDC, sharding, and collection options.
8. **Build prototypes:** both time series and regular collections holding identical measurement payloads.
9. **Benchmark representative workloads:** ingest bursts, query p95/p99, compression, I/O, memory, and TTL sweeps.
10. **Assess operations:** backup/restore, rollup/rebuild, migration, lag monitoring, dedupe, and rollback plans.
11. **Record a conditional decision:** document expected gains, accepted limits, and scale thresholds triggering re-evaluation.

### Technical Decision Record Template

```text
Use case: temperature metrics, 5,000 sensors, 1 sample/min
Data type: append-only measurement, measuredAt = UTC Date
Series identity: tenantId + siteId + deviceId + metric
Query pattern: single device / 24h; site / 1h; hourly rollup
Raw retention: 30 days
Rollup retention: 1 year
Late arrival: up to 2 hours
Duplicate handling: ingestion event ID
Version constraints: checked against target MongoDB release
Benchmark: ingest p95, query p95, storage, CPU, bucket behavior
Decision: adopt or reject time series based on measured results
```

This template is an **evaluation input**, not a claim that a system has already met those metrics or benchmark targets.

## 29. Common Pitfalls

| Pitfall | Why it is wrong | Accurate understanding |
| --- | --- | --- |
| "Documents have `createdAt`, so use time series" | May be regular CRUD entities | Choose based on append workload and time-range queries |
| "Time series always compresses X times better" | Depends on metadata, cadence, schema, buckets | Benchmark on realistic data |
| "More fields in `metaField` is always better" | Changing metadata fragments series and buckets | Keep identity stable and query-relevant |
| "`granularity: 'hours'` rounds timestamps to the hour" | Granularity is only a bucketing hint | Timestamps remain exact measurement BSON Dates |
| "Buckets eliminate the need for indexes" | Source/time queries still benefit from indexes | Check `getIndexes()`/`explain()` and workloads |
| "Index/docs examined mean the exact same thing as regular collections" | Plans include bucket/unpack stages | Read `explain` through time series mechanics |
| "`expireAfterSeconds` deletes every sample on the exact second" | Bucket TTL and monitor run asynchronously | Approximate retention, not an exact deletion clock |
| "Late data must change its timestamp to ingest time" | Corrupts measurement history | Store event time; add `receivedAt` if needed |
| "Two measurements with the same timestamp are always duplicates" | Multiple samples can share a millisecond | Use reliable sequence or event IDs |
| "Time series blocks retry duplicates automatically" | No built-in exactly-once ingestion | Deduplicate at ingest/ledger as required |
| "`$avg` is always a time-weighted average" | Averages by sample count, not duration | Apply time weighting when physics demand it |
| "Average a counter directly to get rate" | Counters accumulate and can reset | Compute deltas/rates properly |
| "Hourly rollups equal averaging per-minute averages" | Minutes can hold varying sample counts | Store `sum` and `count` for weighted rollups |
| "Store all timestamped data in one collection" | CRUD, audits, and telemetry have different needs | Separate measurements, catalogs, alerts, and ledgers |
| "Updates/deletes work identically to regular collections" | Version-dependent time series restrictions | Verify supported operations |
| "Creating a time series collection auto-shards it" | Bucketing is not sharding | Design shard topology and shard keys separately |
| "Fetching latest sensor value needs no sort" | Insert/physical order is not business order | Query by `measuredAt` with tie-breakers |
| "No samples means the sensor does not exist" | Sensor may be offline or expired via TTL | Maintain a separate device catalog |
| "Regular collections are slower because they don't compress" | Indexes/workloads can invert results | Measure ingest, queries, storage, and operations |

## 30. Practice Exercises and Answers

### Exercise 1. Choosing Models for Two Datasets

A system tracks (A) per-minute temperatures for 1,000 sensors and (B) a current battery-status record updated every second per sensor. Which should evaluate time series?

**Answer:** (A) is a clear candidate because measurements append over time. (B) is a continuously updated current-state document, typically better suited to a regular collection. You can store battery history in time series while keeping latest battery state in a regular collection if needed.

### Exercise 2. Choosing `timeField`

A sensor measures at `08:00` yet transmits at `08:07`. Dashboards must report "temperature at 08:00". Which field should be `timeField`?

**Answer:** `measuredAt` (`08:00`) is appropriate; also store `receivedAt` (`08:07`) to monitor lag. Never overwrite measurement time with `08:07` due to a network outage.

### Exercise 3. Which Metadata Belongs in Measurement Fields?

```javascript
meta: {
  siteId: "factory-a",
  deviceId: "sensor-01",
  metric: "temperature_c",
  batteryPct: 87,
  requestId: "req-xyz"
}
```

**Answer:** `batteryPct` and `requestId` typically vary per event and belong in measurement fields. `siteId`, `deviceId`, and `metric` are relatively stable metadata candidates when they identify the business series.

### Exercise 4. Calculating Measurement Volume

5,000 sensors emit one sample per minute for 30 days with zero drops. How many logical measurements are generated?

**Answer:** `5,000 × 60 × 24 × 30 = 216,000,000` measurements. This is **not** disk size; actual storage depends on compression, buckets, indexes, and metadata.

### Exercise 5. Non-Overlapping 60-Second Query

Write a filter fetching `sensor-01` samples from `08:00:00Z` to before `08:01:00Z`.

**Answer:**

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:01:00Z")
  }
})
```

Using `$lt` on `end` assigns an exact `08:01:00Z` reading to the next window, avoiding boundary double-counting.

### Exercise 6. Per-Minute Averages

`sensor-01` has three values `24, 25, 26` in minute `08:00` and two values `27, 28` in minute `08:01`. What are the averages?

**Answer:** Minute `08:00` = `25.0` (3 samples); minute `08:01` = `27.5` (2 samples). Overall mean across all five samples = `(24+25+26+27+28)/5 = 26.0`.

### Exercise 7. Average of Averages

Why does `(25.0 + 27.5)/2 = 26.25` not equal the five-sample average in Exercise 6?

**Answer:** The two minutes have different sample counts (3 vs. 2), so a sample-weighted mean is required. The true average is `(3×25 + 2×27.5)/5 = 26.0`.

### Exercise 8. Features to Verify Before Adopting Time Series

An app runs `replaceOne` on arbitrary readings thousands of times daily and requires complex unique indexes. Can you assume time series is fully compatible because MongoDB supports CRUD?

**Answer:** No. Updates, deletes, replacements, and unique indexes carry version-specific limits. Check official docs for your target MongoDB version and benchmark, or use a regular collection.

### Exercise 9. Does TTL Delete at Exactly `12:00:00`?

A measurement crosses the retention threshold at exactly `12:00:00`. Can you guarantee it disappears from all queries immediately at that instant?

**Answer:** No. Time series TTL operates by bucket and an asynchronous TTL monitor; measurements may remain visible for some time after crossing expiration age.

### Exercise 10. Single-Device Query Yet Slow Dashboard

Query:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
})
```

returns millions of samples across a year. Why can it be slow despite good metadata design?

**Answer:** Missing time bounds and limits force reading and transferring massive data volumes. Add bounded time ranges, projections, suitable indexes, and rollups when dashboards need trends.

### Exercise 11. Counters in Monitoring

Metric `requests_total` logs `1,000`, `1,200`, `1,400` over three consecutive minutes. Can you take `$avg = 1,200` as requests per minute?

**Answer:** No. This is a cumulative counter; without resets, the delta between samples is 200 requests per minute. Compute deltas while handling resets rather than averaging raw counters directly.

### Exercise 12. Why Keep a Separate Sensor Catalog?

Dashboards must alert on sensors silent for 30 minutes, including sensors that have never sent a reading. Is querying `sensorReadings` alone enough?

**Answer:** No. Silent sensors have no measurements. You need an inventory of expected active devices—such as a regular `devices` collection—comparing `lastSeen` against expected cadence.

### Exercise 13. Selecting Deduplication

A gateway retries events on missed ACKs, while electricity billing sums samples. Can you skip deduplication because time series uses compression?

**Answer:** No. Compression does not prevent duplicates. Use stable event IDs/sequences with reliable deduplication or reconciliation matching billing accuracy requirements.

### Exercise 14. When a Regular Collection Remains Better

A maintenance-schedule app keeps one latest document per machine, frequently updating maintenance dates, assignees, and status, while needing unique asset-code constraints.

**Answer:** This is current-state CRUD rather than an append-only measurement stream. A regular collection is simpler and more fitting; if maintenance history is also required, store events in a separate collection.

## 31. Conclusion

**Time series collections** are worth evaluating when systems handle **heavy time-ordered measurement appends**, relatively stable source metadata, queries dominated by **metadata + time range**, and **aggregation/retention/rollup** workloads. MongoDB's bucketing and compression can yield real storage and query gains, though results depend on cadence, cardinality, late arrivals, indexes, and query shapes.

The three highest-impact decisions are:

1. **Semantically accurate `timeField`:** choose measurement vs. ingest time deliberately, standardize UTC, and filter invalid timestamps.
2. **Stable `metaField`:** identify series cleanly with appropriate `tenant`/`site`/`device`/`metric` keys, keeping per-event volatile tags out to avoid fragmenting buckets.
3. **Workload-aligned `granularity` and retention:** match observation cadence, configure clear TTL policies, and pre-plan rollups for long-term history.

To evaluate accurately for **sensor telemetry** and **system observability**, also verify **cardinality, ingest durability, deduplication, late arrivals, gauge/counter math, update/delete limits, version support, sharding, and recovery**. Never judge solely by the label "time series": benchmark identical logical data, identical queries, and identical SLAs, then pick the model delivering clear benefits at acceptable operational cost.

### Official References

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB Manual — Time Series Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/)
- [MongoDB Manual — Time Series Expiration](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
