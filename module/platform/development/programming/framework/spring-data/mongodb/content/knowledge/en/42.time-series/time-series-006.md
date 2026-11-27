# Time-Range Queries and Reporting Aggregations

> **Chapter:** Time series  
> **Module:** `SPRING_DATA_MONGODB`  
> **Language:** English

Imagine an IoT service storing temperature readings sent every minute by thousands of sensors. Users want to see "average temperature of device S-01 during 09:00–10:00", "minimum and maximum values per 15-minute window", or "daily measurement counts at a site". These questions combine **time-range queries** and **reporting aggregations** on time-series data.

In MongoDB, **time-series collections** optimize storing many measurements that carry timestamps and metadata. In Spring Data MongoDB, you still interact through `MongoTemplate`, repositories, and aggregation pipelines; however, you must understand the differences between **measurement time**, **ingestion time**, **display timezone**, **reporting time windows**, and **internal storage buckets**. A single off-by-one mistake between `<=` and `<`, or taking an unweighted average of bucket averages without sample counts, can produce wrong reports even when the code runs without error.

This lesson belongs to module `SPRING_DATA_MONGODB`: connecting and mapping documents, querying with `MongoTemplate` or repositories, aggregations, indexes, transactions, reactive access, testing, and performance analysis. The direct topic is **time-range filtering and designing semantically accurate reporting aggregations**; collection creation and operational topics appear only where needed to support that topic.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Model measurements with a BSON Date `timeField`, `metaField`, and numeric value fields.
2. Use `Instant`/`Date` in Java and distinguish user display timezones from stored UTC instants.
3. Write **half-open** range filters `[startInclusive, endExclusive)` combined with tenant/device/quality predicates.
4. Avoid double-counting when stitching adjacent hour/day intervals and avoid "dropping the last day".
5. Build `$match` → `$group` with `$dateTrunc` → `$sort` → `$project` pipelines to compute `count`, `sum`, `avg`, `min`, and `max`.
6. Use `MongoTemplate.aggregate(...)` with `Aggregation`/`Criteria` and raw BSON stages when the DSL does not expose all server operators.
7. Distinguish storage buckets (managed by MongoDB) from **reporting buckets** (such as 15-minute windows created by `$dateTrunc`).
8. Compute accurate weighted averages across multiple buckets and handle gaps, null measurements, late arrivals, and duplicates.
9. Design reports in local timezones, including Daylight Saving Time (DST) transitions.
10. Test against real MongoDB: BSON `Date`, boundary conditions, tenant isolation, expected numbers, and bucket ordering.
11. Analyze `explain`, indexes, and retention, measure performance, and decide when rollups/pre-aggregation are needed.

## 2. What Does a Time-Series Collection Store?

Example measurement:

```javascript
{
  _id: ObjectId("..."),
  measuredAt: ISODate("2026-11-20T09:02:00Z"),
  meta: {
    tenantId: "TENANT-A",
    deviceId: "S-01",
    sensorType: "temperature",
    unit: "C"
  },
  value: 20.0,
  quality: "OK"
}
```

Components:

| Field | Role | Key detail |
| --- | --- | --- |
| `measuredAt` | **Measurement time** / event time | Must be a BSON Date, not a datetime string |
| `meta` | Metadata describing the measurement series | Readings from the same device and stable attributes share metadata |
| `meta.tenantId` | Business data partitioning | Must be filtered/authorized in the query itself |
| `meta.deviceId` | Source identifier | Used for filtering or grouping by device |
| `value` | Measured value | Should use a consistent numeric type and unit |
| `quality` | Observation quality | Can filter `OK` before computing reports |
| `_id` | Measurement identifier | Must not be assumed to represent event time or canonical measurement order |

### 2.1. `timeField` Differs from System Ingestion Time

An offline sensor may measure at 09:02 and only reach the server at 11:30:

```text
Sensor measuredAt: 2026-11-20T09:02:00Z
Server receivedAt: 2026-11-20T11:30:00Z
```

If a report asks for **temperature during 09:00–10:00**, filter on `measuredAt`. If a report asks "how many events were received in the past hour", use a separate `receivedAt` field and a different query. Never swap fields just because `receivedAt` is closer to the server clock.

### 2.2. `metaField` Expresses Series Identity and Source Filtering

In a time-series collection, metadata can be an object. For example, `meta` holds `tenantId`, `deviceId`, and `sensorType`. These fields should stay relatively **stable across the measurement series**, because changing metadata continuously reduces bucket packing efficiency.

**Do not put per-reading timestamps or random request IDs into `metaField`** just "for completeness": ultra-high-cardinality metadata that changes on every sample defeats bucketing benefits.

If units actually change from °C to °F, never mix both units in the same `$avg`. Normalize units on ingestion or split groups by unit before aggregating.

### 2.3. Storage Buckets Differ from Reporting Buckets

```text
Logical time-series collection: sensor_measurements
   |
   +-- Document measuredAt=09:02, value=20
   +-- Document measuredAt=09:07, value=22
   +-- Document measuredAt=09:14, value=24
   +-- Document measuredAt=09:16, value=26
   |
   v
MongoDB manages internal compressed storage buckets
   (implementation detail)

Aggregation report:
   [09:00,09:15): 20,22,24 => count 3, avg 22
   [09:15,09:30): 26,... => another reporting bucket
```

**Storage buckets** are managed by MongoDB according to its configuration and storage engine algorithms; no application should query `system.buckets.<collection>` directly to build ordinary dashboards. **Reporting buckets** are business time intervals (5 minutes, 15 minutes, 1 hour, 1 day) produced by aggregation over the **logical collection**.

## 3. Creating a Properly Structured Test Collection

On MongoDB supporting time-series collections (MongoDB 5.0+; feature sets and limits vary by version), you can create:

```javascript
// Run only on a TEST database or via an approved migration.
db.createCollection("sensor_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  }
})
```

This creates a **logical time-series collection** with application-defined fields. MongoDB handles internal storage layout; `granularity: "seconds"` is a storage organization hint, **not** an instruction to round measurements to whole seconds or default report grouping to seconds.

### 3.1. Inspecting Collection Options

```javascript
db.getCollectionInfos({ name: "sensor_measurements" })
```

Verify the created collection's `type` and `options.timeseries`; do not rely solely on the collection name or a Java class annotation. A regular collection with the same name and external schema still is not a time-series collection.

### 3.2. Creating via Spring Data / MongoDB Java Code

Spring Data MongoDB provides the `CollectionOptions` API for time series in supporting versions. If a project must enforce exact configuration across multiple major versions, you can run a BSON server command **once during migration**:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

// Example migration/admin code; do not run on every HTTP request.
Document command = new Document("create", "sensor_measurements")
    .append("timeseries",
        new Document("timeField", "measuredAt")
            .append("metaField", "meta")
            .append("granularity", "seconds"));

mongoTemplate.getDb().runCommand(command);
```

`mongoTemplate` is an injected `MongoTemplate` bean; the command fails if the collection already exists or the account lacks permissions. Production systems should use an **idempotent migration** that inspects options and reconciles schema rather than swallowing errors and assuming the collection is correct.

### 3.3. Indexes and Version-Dependent Feature Support

MongoDB supports specialized index types and optimizations for time-series collections that vary across versions. Do not blindly port all index or unique-constraint commands from regular collections without checking server version support. In this lesson, the **foundation** is querying the logical collection via `timeField` and `metaField`; performance and indexing are covered later.

## 4. A Hand-Calculable Test Dataset

To avoid building a report you cannot verify, use a fixed fixture:

```javascript
const metaA = {
  tenantId: "TENANT-A",
  deviceId: "S-01",
  sensorType: "temperature",
  unit: "C"
};
const metaOtherDevice = {
  tenantId: "TENANT-A",
  deviceId: "S-02",
  sensorType: "temperature",
  unit: "C"
};
const metaOtherTenant = {
  tenantId: "TENANT-B",
  deviceId: "S-01",
  sensorType: "temperature",
  unit: "C"
};

db.sensor_measurements.insertMany([
  { measuredAt: ISODate("2026-11-20T09:02:00Z"),
    meta: metaA, value: 20.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:07:00Z"),
    meta: metaA, value: 22.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:14:00Z"),
    meta: metaA, value: 24.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:16:00Z"),
    meta: metaA, value: 26.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:26:00Z"),
    meta: metaA, value: 28.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:32:00Z"),
    meta: metaA, value: 30.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:46:00Z"),
    meta: metaA, value: 32.0, quality: "OK" },
  // Exact 10:00 — must be excluded from [09:00, 10:00).
  { measuredAt: ISODate("2026-11-20T10:00:00Z"),
    meta: metaA, value: 100.0, quality: "OK" },
  // Different device, same tenant — must be excluded.
  { measuredAt: ISODate("2026-11-20T09:04:00Z"),
    meta: metaOtherDevice, value: 99.0, quality: "OK" },
  // Different tenant, same deviceId — must be excluded.
  { measuredAt: ISODate("2026-11-20T09:08:00Z"),
    meta: metaOtherTenant, value: 888.0, quality: "OK" }
])
```

**Task:** report for device `S-01` under `TENANT-A`, only `quality="OK"` readings, from 09:00 up to **before** 10:00 UTC on 2026-11-20.

Expected after filtering: **7 measurements**, sum `182`, average `26.0`. The value 100 at 10:00, 99 from the other device, and 888 from the other tenant must **never** enter the report.

### 4.1. Manual 15-Minute Calculation Table

| UTC reporting bucket | Values | count | sum | avg | min | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `09:00–09:15` | 20, 22, 24 | 3 | 66 | 22 | 20 | 24 |
| `09:15–09:30` | 26, 28 | 2 | 54 | 27 | 26 | 28 |
| `09:30–09:45` | 30 | 1 | 30 | 30 | 30 | 30 |
| `09:45–10:00` | 32 | 1 | 32 | 32 | 32 | 32 |
| **Entire range** | 7 samples | **7** | **182** | **26** | **20** | **32** |

We will use this table to verify both the `mongosh` pipeline and the Java integration test. The sample dataset is small for easy verification; query design, grouping, and load limits must still scale to large collections.

## 5. Half-Open Time-Range Queries `[start, end)`

For time-series reporting, **standardize all query intervals on this convention**:

```text
startInclusive <= measuredAt < endExclusive
          [09:00, 10:00)
```

MongoDB:

```javascript
db.sensor_measurements.find({
  "meta.tenantId": "TENANT-A",
  "meta.deviceId": "S-01",
  quality: "OK",
  measuredAt: {
    $gte: ISODate("2026-11-20T09:00:00Z"),
    $lt: ISODate("2026-11-20T10:00:00Z")
  }
})
```

`$gte` includes samples at `09:00:00.000`, while `$lt` **excludes** samples at exactly `10:00:00.000`. The next interval `[10:00, 11:00)` includes that boundary sample. Adjacent intervals **never double-count** a sample sitting on the boundary.

### 5.1. Why Avoid `$lte` at the Upper Bound?

Consider stitching two reports together:

```javascript
// Risk of double-counting a sample at exactly 10:00:00:
{ measuredAt: {
    $gte: ISODate("2026-11-20T09:00:00Z"),
    $lte: ISODate("2026-11-20T10:00:00Z")
}}

{ measuredAt: {
    $gte: ISODate("2026-11-20T10:00:00Z"),
    $lte: ISODate("2026-11-20T11:00:00Z")
}}
```

Using `$lte` includes a `10:00` sample **twice** across both windows. When stitching multi-hour or multi-day reports, double-counting bugs become much harder to spot.

**Rule:** start inclusive, end exclusive for time filters; when a user specifies "through the end of Nov 20", convert it to the **start of Nov 21 in the chosen timezone**, rather than subtracting a millisecond to form `23:59:59.999`.

### 5.2. Avoid Comparing Datetime Strings

Counter-example:

```javascript
// WRONG with a BSON Date timeField schema:
{ measuredAt: { $gte: "2026-11-20T09:00:00Z" } }
```

Strings are compared by MongoDB under **BSON type/string semantics**, which are not equivalent to a `Date`. For `timeField`, pass true BSON Dates: `ISODate(...)` in `mongosh`, or `java.util.Date`/`Instant` handled by Spring converters in Java.

### 5.3. Time Conventions to Standardize

| Concept | Example | Handling |
| --- | --- | --- |
| Event time | `measuredAt` | Used to filter/group readings by measurement time |
| Ingest time | `receivedAt` | Used for ingestion lag and throughput tracking |
| UTC instant | `2026-11-20T09:00:00Z` | Standard exchange format with MongoDB |
| Local wall-clock | `2026-11-20 16:00` in Vietnam | Requires a timezone to convert into an instant |
| Reporting range | `[start,end)` | Prevents boundary overlap |
| Reporting bucket | `[09:00,09:15)` | Generated via `$dateTrunc` |
| Storage bucket | Managed automatically by MongoDB | Not a reporting group |

### 5.4. Queries Returning No Data

When `find` returns an empty list:

- There may genuinely be no measurements in that interval.
- Tenant, device, or quality filters may not match.
- Source timestamps may have timezone skew or clock drift.
- Retention/TTL may have already purged older data.
- Late-arriving data may not have been ingested yet.
- `start/end` inputs may be wrong.

Do not blindly convert an empty result into "average = 0". **No samples** and **one sample equal to 0** are completely different conditions.

## 6. Java: `Instant`, `Date`, `LocalDate`, and Timezones

In Java, prefer `Instant` for an **absolute point in time** and `ZoneId`/`LocalDate` for selecting calendar days in a user's timezone.

```java
import java.time.Instant;
import java.util.Date;

Instant start = Instant.parse("2026-11-20T09:00:00Z");
Instant end = Instant.parse("2026-11-20T10:00:00Z");

Date bsonStart = Date.from(start);
Date bsonEnd = Date.from(end);
```

`Date.from(Instant)` makes the value used inside raw `Criteria` explicit. Spring Data also includes converters for supported Java time types; use `Instant` in domain models, and verify serialization against your active converter configuration and version.

### 6.1. Java Model for a Measurement

File `SensorMeasurement.java`:

```java
package com.example.timeseries;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sensor_measurements")
public record SensorMeasurement(
    @Id String id,
    Instant measuredAt,
    SensorMeta meta,
    double value,
    String quality
) {
    public record SensorMeta(
        String tenantId,
        String deviceId,
        String sensorType,
        String unit
    ) {}
}
```

This record fits when **a measurement is an immutable fact**. If a source can send missing or invalid readings, never coerce them to primitive `double 0.0` and feed them into averages. Use input validation and a nullable type such as `Double` when the domain must distinguish "not measured" from "measured 0".

### 6.2. Querying with `MongoTemplate`

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class MeasurementRangeReader {

    private final MongoTemplate template;

    public MeasurementRangeReader(MongoTemplate template) {
        this.template = template;
    }

    public List<SensorMeasurement> read(
            String permittedTenantId,
            String deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException(
                "Missing tenant or device");
        }
        if (startInclusive == null || endExclusive == null
                || !startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                "Invalid time range");
        }

        Criteria predicate = Criteria
            .where("meta.tenantId").is(permittedTenantId)
            .and("meta.deviceId").is(deviceId)
            .and("quality").is("OK")
            .and("measuredAt")
                .gte(Date.from(startInclusive))
                .lt(Date.from(endExclusive));

        return template.find(
            new Query(predicate),
            SensorMeasurement.class);
    }
}
```

In production, add a **maximum time-span limit**, result-count cap, pagination/streaming for raw sample queries, and authorization derived from the security context. This method illustrates correct filter expression, not returning millions of measurements as a single HTTP `List`.

### 6.3. Querying with a Repository

When the method name remains readable:

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SensorMeasurementRepository
        extends MongoRepository<SensorMeasurement, String> {

    List<SensorMeasurement>
        findByMetaTenantIdAndMetaDeviceIdAndMeasuredAtGreaterThanEqualAndMeasuredAtLessThan(
            String tenantId,
            String deviceId,
            Instant start,
            Instant end);
}
```

This is a **derived query** using property paths `meta.tenantId`/`meta.deviceId` and two bounds. Once business queries also include `quality`, `sensorType`, permissions, projections, and optional ranges, a custom repository or `MongoTemplate` is usually **easier to maintain and review** than overly long method names. Notice also that the derived method above does not filter `quality="OK"`, so it is **not fully equivalent** to `MeasurementRangeReader.read` above.

### 6.4. Avoid Misusing `LocalDateTime` for Event Time

`LocalDateTime` **carries no timezone or offset**. For example, `2026-11-20T09:00` alone does not know whether it means 09:00 UTC or 09:00 Ho Chi Minh time. Using it as a query bound without a `ZoneId` can shift queries by 7 hours or break during DST transitions.

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate localDay = LocalDate.of(2026, 11, 20);

Instant startUtc = localDay
    .atStartOfDay(vietnam)
    .toInstant();
Instant endUtc = localDay.plusDays(1)
    .atStartOfDay(vietnam)
    .toInstant();
```

November 20, 2026 in Vietnam time begins at **2026-11-19T17:00:00Z** and ends just before **2026-11-20T17:00:00Z**. This local day range is **not** `[2026-11-20T00:00Z, 2026-11-21T00:00Z)`.

### 6.5. A DST Day Can Be 23 or 25 Hours Long

In timezones observing Daylight Saving Time, a local day is not always 24 hours long. Do not write:

```java
// ANTI-PATTERN when a local day with DST is requested.
Instant end = start.plus(24, ChronoUnit.HOURS);
```

Instead use `localDay.plusDays(1).atStartOfDay(zone).toInstant()` so `end` aligns with the local calendar. Also pass the same `timezone` into `$dateTrunc` when grouping by day so bucket boundaries match the query range.

## 7. Aggregation: From Range Query to Reporting Table

A solid pipeline for "per 15 minutes":

```text
sensor_measurements (logical time-series collection)
           |
           v
$match  meta.tenantId, meta.deviceId, quality, measuredAt range
           |
           v
$group  _id = $dateTrunc(measuredAt, minute, binSize=15, UTC)
        count = $sum(1)
        sumValue = $sum(value)
        avgValue = $avg(value)
        minValue = $min(value)
        maxValue = $max(value)
           |
           v
$sort   _id ascending
           |
           v
$project bucketStart, count, sum, avg, min, max
           |
           v
4 rows for the hour
```

**Stage order matters**: filter tenant/device/time early to shrink the stream entering grouping; group first, then sort the groups; project only needed fields. Never sort millions of raw documents when the report only needs to sort a handful of reporting buckets.

### 7.1. `$match` Comes First

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    "meta.deviceId": "S-01",
    quality: "OK",
    measuredAt: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  }
}
```

This lets the server use metadata and time predicates to prune which buckets must be read. Do not rewrite simple predicates into complex `$expr` expressions and assume the query planner will push them down to the bucket layer.

### 7.2. `$dateTrunc` Creates 15-Minute Buckets

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
```

For `09:02`, `09:07`, and `09:14`, the result is `09:00`; `09:16` and `09:26` map to `09:15`. `$dateTrunc` computes the **start of each reporting bucket** as a BSON Date without mutating `measuredAt` on stored samples.

`$dateTrunc` was introduced in MongoDB 5.0. If a backend runs an older server version, you must use an alternative grouping strategy or upgrade the server; do not copy this pipeline assuming MongoDB 4.4 understands it.

### 7.3. `$group` and Accumulators

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$measuredAt",
        unit: "minute",
        binSize: 15,
        timezone: "UTC"
      }
    },
    samples: { $sum: 1 },
    sumValue: { $sum: "$value" },
    avgValue: { $avg: "$value" },
    minValue: { $min: "$value" },
    maxValue: { $max: "$value" }
  }
}
```

`$sum: 1` counts **documents passing `$match`**. If `value` is null, missing, or non-numeric, `$avg` and `$sum: "$value"` follow specific server rules; document count does not necessarily equal the count of valid numeric readings. If `count` must reflect valid numeric measurements, filter/validate numeric values **before** grouping or compute a dedicated accumulator.

In our fixture, every `value` is numeric and every selected record has `quality="OK"`, so `samples=7` also matches the valid measurement count.

### 7.4. `$sort` After Grouping

```javascript
{ $sort: { _id: 1 } }
```

`$group` does not guarantee output ordering of buckets. If a chart expects 09:00, 09:15, 09:30, 09:45 in order, add `$sort` on the bucket timestamp. Never rely on natural order or BSON insertion order.

### 7.5. `$project` Produces Clean Field Names

```javascript
{
  $project: {
    _id: 0,
    bucketStart: "$_id",
    samples: 1,
    sumValue: 1,
    avgValue: 1,
    minValue: 1,
    maxValue: 1
  }
}
```

Keep bucket timestamps as `Date`. Format into `"09:00"` only at the presentation/frontend boundary. Converting timestamps to formatted strings too early discards timezone context and complicates sorting or comparison downstream.

## 8. Complete Pipeline in `mongosh`

Combining the stages:

```javascript
db.sensor_measurements.aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      quality: "OK",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      avgValue: { $avg: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      bucketStart: "$_id",
      samples: 1,
      sumValue: 1,
      avgValue: 1,
      minValue: 1,
      maxValue: 1
    }
  }
])
```

Expected output from the fixture:

```javascript
[
  {
    bucketStart: ISODate("2026-11-20T09:00:00Z"),
    samples: 3, sumValue: 66, avgValue: 22,
    minValue: 20, maxValue: 24
  },
  {
    bucketStart: ISODate("2026-11-20T09:15:00Z"),
    samples: 2, sumValue: 54, avgValue: 27,
    minValue: 26, maxValue: 28
  },
  {
    bucketStart: ISODate("2026-11-20T09:30:00Z"),
    samples: 1, sumValue: 30, avgValue: 30,
    minValue: 30, maxValue: 30
  },
  {
    bucketStart: ISODate("2026-11-20T09:45:00Z"),
    samples: 1, sumValue: 32, avgValue: 32,
    minValue: 32, maxValue: 32
  }
]
```

This is the **expected result** from the sample data, not captured live output during authoring. Depending on server formatting, integers, `double`, or `Decimal128` BSON numbers may render differently, yet **numeric values and bucket boundaries** must match.

### 8.1. Never Put `$limit` Before `$group`

Broken reporting logic:

```javascript
[
  { $match: { /* time + tenant filter */ } },
  { $limit: 100 },
  { $group: { _id: "...", avgValue: { $avg: "$value" } } }
]
```

`$limit: 100` before `$group` aggregates at most the first 100 **samples entering the pipeline**; it no longer summarizes the entire range. If the UI only wants 20 reporting buckets, place `$limit` **after** grouping and sorting and document pagination/bucket limits clearly. Distinguish **limiting returned rows** from **truncating the input dataset**.

### 8.2. Never Label an Average of a Filtered Subset as "Full Hour"

If you filter `quality: "OK"`, the average reflects **OK-quality measurements**, not all raw events. If the collection also stores `quality: "INVALID"` or `value: null`, reports must state which samples were excluded and which contributed to accumulators.

### 8.3. Why `09:14` Belongs to Bucket `09:00`

With `unit: "minute"` and `binSize: 15`, the intervals are:

```text
[09:00:00.000, 09:15:00.000)
[09:15:00.000, 09:30:00.000)
[09:30:00.000, 09:45:00.000)
[09:45:00.000, 10:00:00.000)
```

`09:14:59.999` falls into bucket `09:00`. `09:15:00.000` falls into bucket `09:15`. Consistency between `$gte/$lt` filters and `$dateTrunc` allows stitching reports together without double-counting.

## 9. Java Spring Data: Aggregation with `MongoTemplate`

Spring Data offers the `Aggregation` DSL, `Aggregation.match(...)`, and grouping/projection operations. For modern BSON expressions like `$dateTrunc`, you can implement an `AggregationOperation` via a lambda returning a `Document`: this reduces coupling to whether your specific Spring Data version exposes a typed DSL wrapper for every server operator.

### 9.1. Result DTO

File `TemperatureBucket.java`:

```java
package com.example.timeseries;

import java.time.Instant;

public record TemperatureBucket(
    Instant bucketStart,
    long samples,
    double sumValue,
    double avgValue,
    double minValue,
    double maxValue
) {}
```

A `TemperatureBucket` represents **a summary over one 15-minute bucket**, not a raw measurement document. It intentionally omits raw sample `_id`.

### 9.2. Aggregation Service

File `TemperatureReportService.java`:

```java
package com.example.timeseries;

import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

public final class TemperatureReportService {

    private final MongoTemplate template;

    public TemperatureReportService(MongoTemplate template) {
        this.template = template;
    }

    public List<TemperatureBucket> report15Minutes(
            String permittedTenantId,
            String deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        validate(
            permittedTenantId, deviceId,
            startInclusive, endExclusive);

        Criteria match = Criteria
            .where("meta.tenantId").is(permittedTenantId)
            .and("meta.deviceId").is(deviceId)
            .and("meta.sensorType").is("temperature")
            .and("meta.unit").is("C")
            .and("quality").is("OK")
            .and("measuredAt")
                .gte(Date.from(startInclusive))
                .lt(Date.from(endExclusive));

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(match),
            context -> groupBy15MinuteUtc(),
            context -> new Document("$sort",
                new Document("_id", 1)),
            context -> new Document("$project",
                new Document("_id", 0)
                    .append("bucketStart", "$_id")
                    .append("samples", 1)
                    .append("sumValue", 1)
                    .append("avgValue", 1)
                    .append("minValue", 1)
                    .append("maxValue", 1))
        );

        AggregationResults<Document> rows =
            template.aggregate(
                pipeline,
                "sensor_measurements",
                Document.class);

        return rows.getMappedResults().stream()
            .map(row -> new TemperatureBucket(
                row.getDate("bucketStart").toInstant(),
                asNumber(row, "samples").longValue(),
                asNumber(row, "sumValue").doubleValue(),
                asNumber(row, "avgValue").doubleValue(),
                asNumber(row, "minValue").doubleValue(),
                asNumber(row, "maxValue").doubleValue()))
            .toList();
    }

    private static Document groupBy15MinuteUtc() {
        Document truncate = new Document("$dateTrunc",
            new Document("date", "$measuredAt")
                .append("unit", "minute")
                .append("binSize", 15)
                .append("timezone", "UTC"));

        return new Document("$group",
            new Document("_id", truncate)
                .append("samples", new Document("$sum", 1))
                .append("sumValue",
                    new Document("$sum", "$value"))
                .append("avgValue",
                    new Document("$avg", "$value"))
                .append("minValue",
                    new Document("$min", "$value"))
                .append("maxValue",
                    new Document("$max", "$value")));
    }

    private static Number asNumber(
            Document document, String name) {
        Object raw = document.get(name);
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                "Aggregation field is not numeric: " + name);
        }
        return number;
    }

    private static void validate(
            String tenantId,
            String deviceId,
            Instant from,
            Instant to) {
        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant and device are required");
        }
        if (from == null || to == null
                || !from.isBefore(to)) {
            throw new IllegalArgumentException(
                "Invalid [from, to) range");
        }
        if (Duration.between(from, to)
                .compareTo(Duration.ofDays(31)) > 0) {
            throw new IllegalArgumentException(
                "Query range exceeds 31-day limit");
        }
    }
}
```

**Key points to note:**

- `Aggregation.match(match)` uses `Criteria`, placing metadata, quality, and range filters at the start of the pipeline.
- `groupBy15MinuteUtc()` returns a BSON `Document` representing a `$group` stage. Because it is a raw stage, **BSON field names must be exact**: `measuredAt`, `meta.tenantId`, `value`. If Java `@Field` annotations rename fields, update raw BSON names accordingly.
- `$dateTrunc` executes on the **MongoDB server**; Java is not computing per-sample buckets client-side.
- Mapping `Document` to `TemperatureBucket` validates `Number` types rather than assuming `samples` is always `Integer` or `avgValue` is always `Double`.
- The 31-day limit is an **API policy in this example**, not a fixed MongoDB constraint.
- `permittedTenantId` must come from security/authorization; the service never trusts an unverified tenant sent by the client.
- For large result sets, do not materialize everything via `getMappedResults()` unbounded; consider cursor/streaming APIs and bucket-count caps.

### 9.3. Why Use a Raw `Document` for `$dateTrunc`?

Different Spring Data versions expose different DSL operators. With a raw `Document`:

```java
context -> new Document("$group",
    new Document("_id",
        new Document("$dateTrunc",
            new Document("date", "$measuredAt")
                .append("unit", "minute")
                .append("binSize", 15))))
```

reviewers see the exact BSON sent to MongoDB, though **type-checked mapping protection from the DSL is lost**. When using raw stages, write integration tests to catch field typos or annotation mapping changes. If your Spring Data version includes a compatible `DateOperators.DateTrunc` DSL, you may use the DSL for property-mapping safety; avoiding `Document` everywhere is not mandatory.

### 9.4. Handling Gaps

The service returns **only buckets that contain at least one measurement**. If no sample arrived between 09:15 and 09:30, `$group` **does not emit a zero-count row** for that bucket. If the UI needs all four slots on a chart, choose an explicit **missing-data policy** before filling gaps.

## 10. Multi-Device Reports: Composite Group Keys

For a multi-device dashboard within a tenant, group by both device and bucket:

```javascript
db.sensor_measurements.aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      },
      quality: "OK"
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        bucketStart: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            binSize: 15,
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      avgValue: { $avg: "$value" }
    }
  },
  {
    $sort: {
      "_id.deviceId": 1,
      "_id.bucketStart": 1
    }
  },
  {
    $project: {
      _id: 0,
      deviceId: "$_id.deviceId",
      bucketStart: "$_id.bucketStart",
      samples: 1,
      sumValue: 1,
      avgValue: 1
    }
  }
])
```

This keeps S-01 and S-02 separate. Grouping solely by timestamp without the device dimension produces an "average temperature across all devices" report, which can be valid if named accurately, **but is no longer per-device**; align naming with the API contract.

### 10.1. Why Must Tenant Be in the Filter?

Suppose both `TENANT-A` and `TENANT-B` have `deviceId="S-01"`. Grouping by `deviceId` and bucket without matching tenant mixes 20°C and 888°C into a meaningless average while leaking cross-tenant data. **Tenant filtering must occur inside MongoDB**, not by filtering already-aggregated rows in Java.

### 10.2. Never Aggregate Incompatible Units Together

If S-01 reports Celsius and S-02 reports Fahrenheit, computing `$avg: "$value"` across both devices is physically invalid. Two safe approaches:

1. Normalize to a single unit prior to ingestion, recording unit in metadata.
2. Filter to a single unit or include `unit` in the group key, converting before cross-unit aggregation.

Likewise, never average temperature and humidity together simply because both fields are numeric.

## 11. Daily Reports and Local Timezones

"Report for Nov 20" is a **timezone-sensitive** requirement, not just swapping `unit: "minute"` for `unit: "day"`.

If a site dashboard operates in `Asia/Ho_Chi_Minh`, the start of November 20, 2026 there is `2026-11-19T17:00:00Z`. When filtering, use:

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    measuredAt: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  }
}
```

Then group by **local day**:

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$measuredAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    samples: { $sum: 1 },
    averageValue: { $avg: "$value" }
  }
}
```

`$dateTrunc` still returns a **BSON Date representing a UTC instant** corresponding to midnight in the selected timezone. Never print `_id` directly as `YYYY-MM-DD` in UTC and label it as the Vietnam calendar date; format it using the report's `ZoneId`.

### 11.1. Query Range and Timezone Must Follow the Same Contract

| Approach | Result |
| --- | --- |
| Vietnam local-day filter + `$dateTrunc` with Vietnam timezone | Correct contract |
| `00:00Z–00:00Z` filter + Vietnam-day grouping | Misses part of the local day and includes part of another |
| Vietnam local-day filter + UTC-day grouping | Splits one local day across two buckets |
| Using `Instant.now()` per server to guess local day | Risk of clock/timezone skew and non-reproducible results |

An API should accept a `LocalDate` and a trusted zone policy (such as the site's configured zone), convert to `Instant from/to` once at the boundary, and pass that same zone into the aggregation. Avoid letting each layer infer timezones independently.

### 11.2. Java Code for Computing Reporting Day Bounds

```java
package com.example.timeseries;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public record DailyRange(
    Instant startInclusive,
    Instant endExclusive,
    String timezone
) {
    public static DailyRange of(
            LocalDate day,
            ZoneId reportingZone) {

        if (day == null || reportingZone == null) {
            throw new IllegalArgumentException(
                "Missing day or timezone");
        }

        return new DailyRange(
            day.atStartOfDay(reportingZone).toInstant(),
            day.plusDays(1)
                .atStartOfDay(reportingZone).toInstant(),
            reportingZone.getId());
    }
}
```

`endExclusive` is always calculated as the start of the next day in the same timezone, naturally handling 23-hour and 25-hour DST days.

### 11.3. Weeks, Months, and Other Calendar Boundaries

`$dateTrunc` also supports `unit: "hour"`, `"week"`, `"month"`, and so on with corresponding options. For weeks, `startOfWeek` sets the first day of the week; do not rely on defaults if business reports start on Monday. For months, use the **first day of the next month** as `endExclusive`; never hardcode "30 days" or subtract one millisecond to find month-end.

Example of a Monday-start week:

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

If a product uses a 4-4-5 fiscal calendar or custom closing periods, standard `$dateTrunc` may not suffice. Use a business **calendar table/configuration** or dedicated period mapping rather than assuming standard weeks/months equal fiscal periods.

### 11.4. Repeated or Skipped Hours Due to DST

In DST-observing timezones, "01:00" can occur twice when clocks fall back, or a local hour can disappear entirely when clocks spring forward. To prevent charts from merging distinct hours, keep **UTC `bucketStart` instants** paired with `timezone`, and convert to local labels only for display. When two buckets share the same local clock label, distinguish them using their offset/timezone or full ISO timestamp.

Never use a bare `"01:00"` string as a bucket ID on DST transition days.

## 12. Computing Correct Averages When Rolling Up Multiple Buckets

This is a critical statistical pitfall in hierarchical reporting.

From our fixture:

| Bucket | Samples | Average |
| --- | ---: | ---: |
| `09:00` | 3 | 22 |
| `09:15` | 2 | 27 |
| `09:30` | 1 | 30 |
| `09:45` | 1 | 32 |

If a backend takes the **average of the four averages**:

\[
\frac{22+27+30+32}{4}=27.75
\]

The result **27.75** is not the true average of the seven measurements. The true average is:

\[
\frac{3\cdot22+2\cdot27+1\cdot30+1\cdot32}{3+2+1+1}
=\frac{182}{7}=26
\]

To roll up 15-minute buckets into hourly metrics, store **`sumValue` and `samples`**, then compute:

```text
hourSum     = sum(bucket.sumValue)
hourSamples = sum(bucket.samples)
hourAverage = hourSum / hourSamples
```

**Never compute `avg(bucket.avgValue)`** when buckets can have unequal sample counts.

### 12.1. Two-Tier Rollup Pipeline in MongoDB

If the output report only needs hourly stats from raw samples, the simplest option is grouping **directly** on raw data by hour. However, when a 15-minute rollup collection already exists, you can roll up those rows:

```javascript
db.temperature_rollups_15m.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      deviceId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$bucketStart",
          unit: "hour",
          timezone: "UTC"
        }
      },
      samples: { $sum: "$samples" },
      sumValue: { $sum: "$sumValue" },
      minValue: { $min: "$minValue" },
      maxValue: { $max: "$maxValue" }
    }
  },
  {
    $project: {
      _id: 0,
      hourStart: "$_id",
      samples: 1,
      sumValue: 1,
      avgValue: {
        $cond: [
          { $gt: ["$samples", 0] },
          { $divide: ["$sumValue", "$samples"] },
          null
        ]
      },
      minValue: 1,
      maxValue: 1
    }
  }
])
```

`$min` and `$max` over rollups preserve exact global extrema if computed over the **same sample population**, whereas statistics like percentiles, medians, or standard deviations cannot generally be combined from a single per-bucket summary scalar.

### 12.2. Sample Average Differs from Time-Weighted Average

`$avg: "$value"` assigns **equal weight to each sample**. If a sensor reports at 09:00, 09:01, and then 09:59, the sample average can differ significantly from the signal's **time-weighted average**.

To compute a time-weighted average, you must define semantics such as:

- Assume values stay constant until the next reading (step function), or interpolate linearly?
- After how long a gap is data considered unreliable?
- How should integration be clipped at `start/end` boundaries?
- How are late-arriving and out-of-order samples handled?

Never label `$avg` as "time-weighted temperature" without integrating duration. When telemetry arrives at a steady cadence with low lag, sample averages can be a useful approximation; when cadence is irregular, state the limitation explicitly.

### 12.3. Summing Rates Is Not Summing Volume

If `value` is a flow rate in `liters/second`, `$sum: "$value"` does not equal total liters. Multiply by each sample's **effective duration** or ingest volume per interval. Units must match the formula:

```text
Sum of °C samples       -> sum of numeric readings (not energy)
Average °C              -> sample-weighted average temperature
Sum of liters           -> total volume if each value is already a quantity
Integral of liters/sec  -> total volume when weighted by elapsed duration
```

## 13. When No Samples Exist: Empty Buckets and Missing-Data Policies

A standard `$group` aggregation **only emits buckets that have data**. For example, if S-01 sends nothing during `[09:30, 09:45)`:

```text
09:00 -> 3 samples
09:15 -> 2 samples
09:30 -> (no row returned)
09:45 -> 1 sample
```

Never fabricate `09:30 = 0°C` and include it in averages; that represents **unobserved data**, not a reading of zero degrees.

### 13.1. Common Policies

| Policy | Interpretation | When appropriate |
| --- | --- | --- |
| **Null / gap** | Unknown value | Good default for missing temperature or telemetry |
| **Zero fill** | Assumes absence of events equals zero | Only for event counts where domain semantics permit |
| **LOCF** | Last observation carried forward | Short-term stable signals with a freshness cap |
| **Linear interpolation** | Interpolate between neighboring samples | When domain physics allow and gaps are short |
| **Drop bucket** | Omit the empty timestamp | Sparse API responses where the frontend handles gaps |

Crucially, **record quality metadata**: whether a value is observed or inferred, sample count, gap length, and confidence. Never disguise interpolated values as real measurements in audits or high-stakes reports.

### 13.2. `$densify` and `$fill`

MongoDB provides the `$densify` and `$fill` aggregation stages on supporting versions to generate missing timestamps and populate values. Conceptual flow:

```text
$match(...range/tenant...)
    -> $group(by bucketStart, avgValue, samples)
    -> $project(bucketStart, avgValue, samples)
    -> $densify(field=bucketStart, step=15 minute, bounds=...)
    -> $fill(avgValue using chosen method)
    -> $sort(bucketStart)
```

Do not blindly apply a `$fill` stage to zero-fill all metrics. Exact field names, `$densify` placement, bounds, partitioning, and server version support must be verified with integration tests. When a device has only 96 buckets per day, the application can also generate a bounded timeline in memory and merge sparse query results, provided **timezones, tenant permissions, and missing-data semantics** remain accurate.

### 13.3. Distinguishing `samples=0` from `avgValue=null`

An application-generated bucket filling a timeline can look like:

```json
{
  "bucketStart": "2026-11-20T09:30:00Z",
  "samples": 0,
  "avgValue": null,
  "valueStatus": "NO_DATA"
}
```

Never set `samples: 0, avgValue: 0` when 0°C is a valid physical reading. Separate `observedSamples` and `estimatedValue` if a dashboard must show both real readings and an interpolated line.

## 14. Numeric Types, Nulls, and Statistical Consistency

MongoDB aggregations follow specific rules across `int`, `long`, `double`, `Decimal128`, and non-numeric fields. Before computing reports:

1. Enforce `value` as numeric with a consistent unit.
2. Validate at ingestion to reject strings like `"23.5"` or booleans like `true` in numeric measurement fields.
3. Distinguish null/missing from zero.
4. Define how `NaN`/`Infinity` are handled in application/driver layers if external sources can emit them.
5. Check arithmetic precision requirements for financial or energy billing domains.

### 14.1. Counting Documents vs. Counting Numeric Values

Suppose the source contains:

```javascript
[
  { measuredAt: ISODate("2026-11-20T09:00:00Z"),
    value: 12.5 },
  { measuredAt: ISODate("2026-11-20T09:01:00Z"),
    value: null },
  { measuredAt: ISODate("2026-11-20T09:02:00Z"),
    quality: "INVALID" }
]
```

If `$group` computes `count: { $sum: 1 }` and `avg: { $avg: "$value" }`, `count` is 3 while the average uses fewer numeric samples. If the report needs missing-value ratios, track separate counters:

```javascript
{
  $group: {
    _id: "$meta.deviceId",
    documents: { $sum: 1 },
    numericSamples: {
      $sum: {
        $cond: [{ $isNumber: "$value" }, 1, 0]
      }
    },
    avgNumericValue: { $avg: "$value" }
  }
}
```

`$isNumber` is a MongoDB aggregation operator; check support for your server version. Filter `quality: "OK"` and numeric checks before grouping when the contract specifies reporting only valid samples.

### 14.2. When High Decimal Precision Is Required

For revenue or billing amounts, use **integer/long minor units** or `Decimal128` per policy instead of `double` when exact arithmetic is mandatory. In Java, test `BigDecimal` and converter round-trips carefully. For temperature/telemetry, `double` is typically acceptable, provided test assertions use a **tolerance** instead of exact multi-digit floating-point equality.

### 14.3. `$avg` Can Return `null` When No Valid Samples Exist

When a group contains zero numeric samples, `$avg` can return `null`. Therefore, a Java mapper reading `row.get("avgValue", Number.class)` must handle `null` according to contract; never call `.doubleValue()` unchecked on pipelines that may encounter missing data.

`TemperatureReportService` in section 9 was written for a **pre-validated fixture with numeric `value` and `OK` quality**. Before applying it to unclean legacy data, add field validation, filters, and a nullable DTO.

## 15. Optimizing Time-Series Queries: `metaField`, `timeField`, and Indexes

Time-series collections organize internal storage into buckets to lower cost for suitable workloads, which does not automatically make every query fast. Well-designed queries typically feature:

- **A bounded `measuredAt` range**.
- **Predicates on stable metadata**, such as tenant, device, and sensorType.
- Server-side field filtering and numeric accumulators rather than pulling all raw samples into Java.
- Projections and reporting bucket resolutions matching display needs.

### 15.1. `$match` Helps Prune Buckets

Example:

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    "meta.deviceId": "S-01",
    measuredAt: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  }
}
```

MongoDB can leverage time and metadata bounds to limit which buckets are scanned. Do not assume all optimizer versions push down every expression identically: verify with `explain` on representative data.

### 15.2. Indexes for Metadata and Time Filters

Evaluate candidates on your target MongoDB version:

```javascript
db.sensor_measurements.createIndex(
  {
    "meta.tenantId": 1,
    "meta.deviceId": 1,
    measuredAt: 1
  },
  { name: "idx_tenant_device_measured_at" }
)
```

This index targets equality predicates on metadata and range predicates on `measuredAt`. Keep in mind:

1. Time-series collections have **specialized index rules that evolve across MongoDB versions**; certain index types and options are unsupported or restricted.
2. Never assume a newly created index is automatically chosen by the query planner.
3. If queries typically scan an entire tenant over time without `deviceId`, index key ordering may need adjustment.
4. Indexes increase write and storage overhead; create only what real workloads justify.
5. Some MongoDB versions create default meta/time indexes automatically; inspect `getIndexes()` to avoid redundant indexes.

**Do not claim regular-collection unique index support on time-series collections.** If duplicate `eventId` writes must be prevented, check version-specific constraints and use a separate deduplication/inbox mechanism.

### 15.3. Inspecting `explain` on Real Queries

```javascript
db.sensor_measurements.explain("executionStats").aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 }
    }
  }
])
```

Signals to compare:

| Signal | What to evaluate |
| --- | --- |
| `totalKeysExamined` | Number of index keys scanned |
| `totalDocsExamined` | Cost of reading documents/buckets as reported by the server |
| `executionTimeMillis` | Estimated execution time reported in explain |
| Selected index | Does it match the workload and filter? |
| Bucket unpack / optimizer stages | Are too many measurements being unpacked? |
| Sort/group memory | Does it exceed memory thresholds or spill to disk? |
| Time range / span | How do 1-hour, 1-day, and 90-day queries compare? |

Stage names and formats in `explain()` can change across MongoDB versions and query execution engines. Never write a test that merely greps a fixed stage name and treats that as a performance check across upgrades.

### 15.4. Avoid Fetching All Raw Data to Compute `AVG` in the Application

Counter-example:

```java
List<SensorMeasurement> all =
    template.find(new Query(), SensorMeasurement.class);

double average = all.stream()
    .mapToDouble(SensorMeasurement::value)
    .average().orElse(Double.NaN);
```

This is an anti-pattern on large time-series collections: no filters, pulling every document over the network and into the JVM heap. Push filtering and grouping into MongoDB; when raw samples are genuinely needed, enforce range/record caps, pagination/streaming, or async export jobs.

### 15.5. Even Reporting Buckets Can Grow Too Large

One day grouped by second equals 86,400 buckets **per device**. Across 10,000 devices, group count explodes. Never assume "aggregation always returns a small group set":

- Pick resolution appropriate for the UI: 1 minute, 15 minutes, 1 hour, 1 day.
- Cap both device count and time span.
- Use rollups/pre-aggregation when dashboards repeatedly query the same intervals.
- Limit page/group counts and separate real-time queries from batch exports.
- Monitor disk spill, memory, CPU, and latency across range sizes.

## 16. Weekly/Monthly Reports: When to Use Rollups (Pre-Aggregation)?

If users refresh a 15-minute dashboard every few seconds against a raw collection holding billions of readings, re-running the full pipeline every time consumes heavy CPU and I/O.

One solution is maintaining a **regular rollup collection** storing:

```javascript
{
  tenantId: "TENANT-A",
  deviceId: "S-01",
  bucketStart: ISODate("2026-11-20T09:00:00Z"),
  granularityMinutes: 15,
  samples: NumberLong(3),
  sumValue: 66.0,
  minValue: 20.0,
  maxValue: 24.0,
  computedAt: ISODate("2026-11-20T10:05:00Z")
}
```

Dashboards then read 15-minute rollups instead of scanning raw samples repeatedly.

### 16.1. Store `count`/`sum`, Not Only `avg`

Each rollup needs at least:

- `samples`: count of valid samples per policy.
- `sumValue`: sum needed to recompute weighted averages.
- `minValue`/`maxValue` if extrema are required.
- `bucketStart`, `tenantId`, `deviceId`, unit, and resolution.
- `computedAt`/`sourceRange`/freshness metadata as needed.

If you store only `avgValue` and drop `samples`, you cannot roll up accurately into hours or days when buckets have different sample counts.

### 16.2. Writing Rollups with `$merge` into a Regular Collection

Once a bucket set has a well-defined identity, a pipeline can end with `$merge` targeting **a regular reporting collection**:

```javascript
// Minimized example: stages computing a 15-minute rollup
db.sensor_measurements.aggregate([
  { $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      quality: "OK",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
  }},
  { $group: {
      _id: {
        bucketStart: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute", binSize: 15, timezone: "UTC"
          }
        },
        tenantId: "$meta.tenantId",
        deviceId: "$meta.deviceId"
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
  }},
  { $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      deviceId: "$_id.deviceId",
      bucketStart: "$_id.bucketStart",
      samples: 1,
      sumValue: 1,
      minValue: 1,
      maxValue: 1
  }},
  { $merge: {
      into: "temperature_rollups_15m",
      on: ["tenantId", "deviceId", "bucketStart"],
      whenMatched: "replace",
      whenNotMatched: "insert"
  }}
])
```

To use `$merge.on` with non-`_id` fields, the **target** collection must have a **matching unique index** satisfying MongoDB's requirements and support conditions. Create the index on the **regular rollup collection** using identical `Date`/key types before running the pipeline.

```javascript
db.temperature_rollups_15m.createIndex(
  { tenantId: 1, deviceId: 1, bucketStart: 1 },
  { unique: true, name: "uq_rollup_identity" }
)
```

**Warning:** `$merge` is a **write stage**, not a read-only reporting query. It requires write privileges and impact review; never let clients trigger arbitrary `$merge` aggregations. Never reuse a `$merge` pipeline in a read API expecting `List<TemperatureBucket>`.

### 16.3. A Rollup Can Become Stale

A sensor measures at 09:03, goes offline, and uploads the reading at 11:00. If the 09:00 rollup job ran at 10:05 and never re-runs, that bucket's `samples` and `sumValue` remain **incomplete**.

You need a strategy:

1. **Allowed lateness:** wait N minutes/hours before finalizing a bucket.
2. **Recompute overlap:** each scheduled run recomputes a recent trailing window, such as the last 24 hours.
3. **Correction events:** when late data updates an already-published bucket, push updates to read models/caches.
4. **Backfill:** for very late arrivals, run a tracked and verified batch backfill job.
5. **Freshness metadata:** surface whether a report is finalized or still provisional.

Allowed lateness is a domain/source-data policy, not a bucket-time parameter decided by MongoDB.

### 16.4. Idempotent Rollup Does Not Mean Idempotent Ingestion

`whenMatched: "replace"` lets a job recompute the same bucket without creating duplicate rollup rows for the same key, **provided** the unique identity is enforced properly. However, if the raw collection already holds **duplicate samples**, `$group` will still count those duplicates. Enforce deduplication by `eventId`/unique business key in the ingestion pipeline or appropriate source layer.

Never equate "re-running aggregation doesn't multiply rollup rows" with "every reported metric is accurate".

## 17. Late Arrivals, Out-of-Order Events, and Duplicates

Time-series collections receive readings over time, yet data does not always arrive in `measuredAt` order. One plant's offline gateway may upload an old batch while other devices stream real-time readings.

### 17.1. Timestamps Must Represent Trustworthy Event Time

An invalid timestamp from a drifting device clock can shift a sample into the wrong day. At ingestion:

- Validate timestamps against an acceptable window relative to server receipt time.
- Record `receivedAt` and `clockSkewEstimate` where useful.
- Reject, quarantine, or flag timestamps too far in the future or past.
- Allow valid late arrivals while keeping report-update policies clear.

Never replace every `measuredAt` with `Instant.now()` just to keep data "neat": that destroys real measurement timestamps.

### 17.2. Source-Side Duplicates

An HTTP retry from a device may submit the same sample twice. If each request writes a new MongoDB document, a report over:

```text
value 20 at 09:02 (original)
value 20 at 09:02 (retry duplicate)
```

will count two samples. If deduplication is required, every measurement must carry a **stable source `eventId`/sequence** paired with duplicate control compatible with time-series collection/version restrictions. Generating a fresh `_id` on each retry will not identify the same measurement.

### 17.3. Out-of-Order Is Different from Duplicate

```text
received 10:03 -> measuredAt 10:00, event A
received 10:04 -> measuredAt 09:55, event B
```

These two samples are distinct; they simply arrived out of event-time order. If both are valid, aggregation by `measuredAt` places B into bucket 09:45–10:00 and A into 10:00–10:15. However, any rollup computed before 10:04 must be refreshed to incorporate B.

### 17.4. TTL/Retention Changes Report Completeness

Time-series collections can configure data expiration via `expireAfterSeconds`, following time/bucket-based cleanup rules. TTL deletion is **not instantaneous** and not a millisecond-accurate timer. If a report requests 90 days of data while retention is only 30 days, results will be partial or empty.

Never interpret `count=0` for an old period as proof that a device was offline once raw data has expired. Define explicitly:

```text
rawRetention = 30 days
rollupRetention = 12 months
businessReportCoverage = measured and published separately
```

Even when rollups outlive raw expiration, jobs can no longer recompute expired windows accurately unless an archive or durable source exists.

## 18. Integration Testing Against a Real Time-Series Collection

Unit tests mocking `MongoTemplate.aggregate(...)` fail to prove that:

- The collection genuinely has the right `timeseries.timeField` and `metaField`.
- `Instant` converts to BSON `Date`.
- `$dateTrunc` groups into exact 15-minute intervals.
- `$gte/$lt` excludes samples on the end boundary.
- Tenant/device/quality filters prevent cross-data leakage.
- `$avg`/`$sum` return numeric types matching expectations.
- Indexes and the optimizer perform adequately on your target MongoDB version.

Therefore, write integration tests against a **MongoDB server supporting time-series collections and `$dateTrunc`**. This lesson does not require a replica set solely to test these **aggregation reads**; if your project also tests transactions or change streams, satisfy those features' topology requirements separately.

### 18.1. Minimum Test Matrix

| Test | Input | Expected |
| --- | --- | --- |
| Collection structure | Create with `timeField=measuredAt`, `metaField=meta` | Collection has time-series configuration |
| BSON timestamp | Insert `Date`/`Instant` | Raw document stores BSON Date |
| Half-open range | `[09:00,10:00)` | Sample at 10:00 excluded |
| Tenant isolation | `TENANT-A` + `TENANT-B` | Excludes 888 from B |
| Device isolation | S-01 + S-02 | Excludes 99 from S-02 |
| 15-minute grouping | 09:02,09:07,09:14,09:16,... | 4 reporting buckets |
| Numeric results | 7-sample fixture | `count=7`, `sum=182`, avg 26 |
| Bucket boundary | 09:14 and 09:16 | Placed in adjacent buckets |
| Empty interval | Different interval | Returns no bucket, does not invent `avg=0` |
| Validation | End ≤ start or exceeds policy | Rejected before querying MongoDB |
| Timezone | Vietnam local day | UTC boundaries at `17:00Z` |
| Performance | Explain on sizable dataset | Inspect index/scan; never generalize from tiny fixtures |

### 18.2. Dedicated Test Database Configuration

Example with Spring Boot 3.x, JUnit 5, and AssertJ:

```java
@DataMongoTest
@TestPropertySource(properties =
    "spring.data.mongodb.database=ts_lesson_test_worker9")
class TemperatureReportIntegrationTest {
    // ...
}
```

**Warning:** the property above is sample configuration for Spring Boot 3.x; other driver or Boot major versions may differ. Never trust the property name blindly: tests should verify the **actual database name from `MongoTemplate`** before creating or dropping collections. Never run MongoDB time-series tests against production or shared databases.

### 18.3. Complete Integration Test with Expected Assertions

File `TemperatureReportIntegrationTest.java`:

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

@DataMongoTest
@TestPropertySource(properties =
    "spring.data.mongodb.database=ts_lesson_test_worker9")
class TemperatureReportIntegrationTest {

    private static final String COLLECTION =
        "sensor_measurements";

    @Autowired
    MongoTemplate template;

    private boolean createdByTest;

    @BeforeEach
    void prepareFixture() {
        String actualDb = template.getDb().getName();
        if (!"ts_lesson_test_worker9".equals(actualDb)) {
            throw new IllegalStateException(
                "Refusing to modify unexpected MongoDB: "
                    + actualDb);
        }
        if (template.collectionExists(COLLECTION)) {
            throw new IllegalStateException(
                "Test database must start with no collection "
                    + COLLECTION);
        }

        Document create = new Document("create", COLLECTION)
            .append("timeseries",
                new Document("timeField", "measuredAt")
                    .append("metaField", "meta")
                    .append("granularity", "seconds"));

        template.getDb().runCommand(create);
        createdByTest = true;

        template.getCollection(COLLECTION).insertMany(List.of(
            sample("09:02", "TENANT-A", "S-01", 20),
            sample("09:07", "TENANT-A", "S-01", 22),
            sample("09:14", "TENANT-A", "S-01", 24),
            sample("09:16", "TENANT-A", "S-01", 26),
            sample("09:26", "TENANT-A", "S-01", 28),
            sample("09:32", "TENANT-A", "S-01", 30),
            sample("09:46", "TENANT-A", "S-01", 32),
            sample("10:00", "TENANT-A", "S-01", 100),
            sample("09:04", "TENANT-A", "S-02", 99),
            sample("09:08", "TENANT-B", "S-01", 888)
        ));
    }

    private static Document sample(
            String hhmm, String tenant,
            String device, double value) {

        Document metadata = new Document("tenantId", tenant)
            .append("deviceId", device)
            .append("sensorType", "temperature")
            .append("unit", "C");

        return new Document("measuredAt",
            Date.from(Instant.parse(
                "2026-11-20T" + hhmm + ":00Z")))
            .append("meta", metadata)
            .append("value", value)
            .append("quality", "OK");
    }

    @AfterEach
    void cleanup() {
        if (createdByTest
                && "ts_lesson_test_worker9"
                    .equals(template.getDb().getName())) {
            // Database/collection dedicated solely to this test.
            template.dropCollection(COLLECTION);
        }
    }

    private TemperatureReportService service() {
        return new TemperatureReportService(template);
    }

    @Test
    void groupsSevenSamplesIntoFourQuarterHourBuckets() {
        List<TemperatureBucket> rows =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T10:00:00Z"));

        assertThat(rows).hasSize(4);
        assertThat(rows).extracting(
            TemperatureBucket::bucketStart)
            .containsExactly(
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T09:15:00Z"),
                Instant.parse("2026-11-20T09:30:00Z"),
                Instant.parse("2026-11-20T09:45:00Z"));

        assertThat(rows.get(0).samples()).isEqualTo(3);
        assertThat(rows.get(0).sumValue()).isEqualTo(66);
        assertThat(rows.get(0).avgValue())
            .isCloseTo(22, within(0.000001));
        assertThat(rows.get(0).minValue()).isEqualTo(20);
        assertThat(rows.get(0).maxValue()).isEqualTo(24);

        assertThat(rows.get(1).samples()).isEqualTo(2);
        assertThat(rows.get(1).sumValue()).isEqualTo(54);
        assertThat(rows.get(1).avgValue())
            .isCloseTo(27, within(0.000001));

        long count = rows.stream()
            .mapToLong(TemperatureBucket::samples)
            .sum();
        double sum = rows.stream()
            .mapToDouble(TemperatureBucket::sumValue)
            .sum();

        assertThat(count).isEqualTo(7);
        assertThat(sum).isCloseTo(182, within(0.000001));
        assertThat(sum / count)
            .isCloseTo(26, within(0.000001));

        double incorrectAverageOfAverages =
            rows.stream()
                .mapToDouble(TemperatureBucket::avgValue)
                .average().orElseThrow();

        assertThat(incorrectAverageOfAverages)
            .isCloseTo(27.75, within(0.000001));
    }

    @Test
    void endBoundaryIsExclusiveAndTenantMustMatch() {
        List<TemperatureBucket> tenToEleven =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T10:00:00Z"),
                Instant.parse("2026-11-20T11:00:00Z"));

        assertThat(tenToEleven).hasSize(1);
        assertThat(tenToEleven.get(0).samples())
            .isEqualTo(1);
        assertThat(tenToEleven.get(0).sumValue())
            .isEqualTo(100);

        List<TemperatureBucket> otherTenant =
            service().report15Minutes(
                "TENANT-B", "S-01",
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T10:00:00Z"));

        assertThat(otherTenant).hasSize(1);
        assertThat(otherTenant.get(0).sumValue())
            .isEqualTo(888);
    }

    @Test
    void noDataIsEmptyNotZero() {
        List<TemperatureBucket> rows =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T11:00:00Z"),
                Instant.parse("2026-11-20T12:00:00Z"));

        assertThat(rows).isEmpty();
    }

    @Test
    void timeFieldIsStoredAsBsonDate() {
        Document first = template.getCollection(COLLECTION)
            .find(new Document(
                "meta.deviceId", "S-01"))
            .first();

        assertThat(first).isNotNull();
        assertThat(first.get("measuredAt"))
            .isInstanceOf(Date.class);
        assertThat(first.get("meta"))
            .isInstanceOf(Document.class);
    }

    @Test
    void invalidRangeDoesNotReachMongoDb() {
        Instant same =
            Instant.parse("2026-11-20T09:00:00Z");

        assertThatThrownBy(() ->
            service().report15Minutes(
                "TENANT-A", "S-01", same, same))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Important limitations of this test fixture:**

- It is only safe when **both the test runner and MongoDB database are isolated**; never run two test instances concurrently against the same database and collection name. In CI, provision an isolated database or container per job.
- If the collection already exists, the test **refuses to write**; `createdByTest` permits dropping only a collection created by the fixture itself.
- MongoDB server/driver must support time-series collections and `$dateTrunc`.
- The test does not use `deleteMany` on the time-series collection for per-document cleanup; delete/update rules on time-series collections vary by version. It drops only the fixture-created collection in its dedicated database.
- There is no guarantee this test code was executed during documentation authoring; this step provides **test code for your project to execute**.

### 18.4. Testing Local Days and DST with a Unit Test

Even without MongoDB, range calculations can be verified:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

@Test
void vietnameseLocalDayUsesCorrectUtcBoundaries() {
    DailyRange range = DailyRange.of(
        LocalDate.of(2026, 11, 20),
        ZoneId.of("Asia/Ho_Chi_Minh"));

    assertThat(range.startInclusive()).isEqualTo(
        Instant.parse("2026-11-19T17:00:00Z"));
    assertThat(range.endExclusive()).isEqualTo(
        Instant.parse("2026-11-20T17:00:00Z"));
}
```

This method belongs to a JUnit test class with the imports shown above. For DST-observing timezones, add tests around clock-change days verifying `end` comes from `day.plusDays(1).atStartOfDay(zone)` rather than adding a fixed 24 hours.

### 18.5. Testing That Query Count Differs from Average Count on Dirty Data

In a **separate** test database or fresh fixture, seed both `value: null` and `quality: "INVALID"`, then compare:

- Documents matched after `$match`.
- Valid numeric values actually used by `$avg`.
- Samples excluded due to `quality`.

Do not run a dirty-data test against `TemperatureReportService` until you extend its validation policy and nullable DTO; otherwise you will only trigger an expected failure due to documented assumptions.

## 19. Reactive Access: Do Not Aggregate Client-Side

Spring Data MongoDB provides `ReactiveMongoTemplate` and reactive aggregation APIs when applications run on WebFlux / Project Reactor.

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<Document> rows = reactiveTemplate.aggregate(
    pipeline,
    "sensor_measurements",
    Document.class);
```

`reactiveTemplate` and `pipeline` are configured in the service. `Flux` is a Publisher; the MongoDB query executes only upon subscription, and consumers must handle errors, cancellation, and backpressure. Never do this:

```java
// ANTI-PATTERN in event-loop code:
List<Document> all = rows.collectList().block();
```

on a WebFlux request thread. Even if you only need a bounded number of buckets to render a chart, **filter, group, and sort inside MongoDB**, returning a `Flux<DTO>` or bounded `Mono<List<DTO>>` per API contract.

### 19.1. Reactor Does Not Turn `$group` into Sample-by-Sample Streaming

`Flux<Document>` in this example emits **post-aggregation rows**. `$group` operations may still have to process many raw samples on the server before emitting a single row. Reactive access avoids blocking client threads; **it does not eliminate MongoDB aggregation cost**.

### 19.2. Backpressure and Output Caps

If a report queries 10,000 devices × 96 buckets/day, the emitted row count can still be huge. Constrain scope and resolution before opening the stream. `rows.take(10)` only caps items **received by the client**—it does not guarantee the server skips expensive grouping. Apply server-side filters, proper aggregation logic, well-placed `$limit` stages, and workload caps.

### 19.3. Never Mix Blocking `MongoTemplate` into a Reactive Chain

A reactive service must not invoke `MongoTemplate.aggregate(...)` directly on an event loop and wrap the result in `Mono.just(...)`. That is still blocking I/O. Use `ReactiveMongoTemplate`, or controlled thread offloading when a blocking driver is unavoidable; for long-running time-series reports, consider batch jobs instead of holding HTTP requests open.

### 19.4. Testing Reactive Aggregation with `StepVerifier`

Given the test fixture and `Aggregation pipeline` from section 9, rows can be verified without `block()`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import static org.assertj.core.api.Assertions.assertThat;

Flux<Document> rows = reactiveTemplate.aggregate(
    pipeline, "sensor_measurements", Document.class);

StepVerifier.create(rows)
    .assertNext(first -> {
        assertThat(first.getDate("bucketStart")
                .toInstant())
            .isEqualTo(Instant.parse(
                "2026-11-20T09:00:00Z"));
        assertThat(((Number) first.get("samples"))
                .longValue()).isEqualTo(3L);
        assertThat(((Number) first.get("avgValue"))
                .doubleValue()).isEqualTo(22.0);
    })
    .expectNextCount(3)
    .verifyComplete();
```

This is an **integration test snippet** where `reactiveTemplate`, `pipeline`, `Instant`, and the fixture are already set up. `verifyComplete()` confirms the stream finishes cleanly with four rows; `expectNextCount(3)` does not assert details of the remaining three buckets, so production correctness tests must still assert timestamps, counts/sums, and tenant isolation like the imperative suite in section 18. When testing unstable or failing inputs, assert `onError`, cancellation, and timeouts explicitly rather than swallowing errors via `onErrorResume` returning an empty list.

## 20. Designing Reporting APIs with Clear Guardrails

Never expose an API allowing users to pick `from=1900-01-01` to now, `resolution=1 second`, and `deviceIds=*` without limits. That can trigger massive aggregations regardless of indexing.

A request DTO:

```java
package com.example.timeseries;

import java.time.Instant;

public record TemperatureReportRequest(
    String deviceId,
    Instant startInclusive,
    Instant endExclusive,
    int bucketMinutes
) {}
```

`tenantId` does not belong in the request body when authentication is active; the service obtains `permittedTenantId` from the security context. For bucket resolution requests, enforce an allowlist:

```java
if (bucketMinutes != 1
        && bucketMinutes != 5
        && bucketMinutes != 15
        && bucketMinutes != 60) {
    throw new IllegalArgumentException(
        "Unsupported bucket resolution");
}
```

### 20.1. Capping Expected Reporting Buckets

```text
requestedTimeRange = 7 days
bucketResolution   = 1 minute
expectedBuckets    = 7 * 24 * 60 = 10080 per device
```

Across 500 devices, that reaches over 5 million bucket rows if all devices report continuously. Therefore, cap not only the raw range but also **device count × bucket count**, applying pagination, batch exports, or rollups according to UX.

### 20.2. Never Trust Client-Supplied Timezones Without Validation

`timezone` is a string influencing `$dateTrunc`. Accept only valid IANA Zone IDs such as `"Asia/Ho_Chi_Minh"` permitted by the tenant/site zone policy. If only display formatting varies, prefer the site's configured timezone; never allow clients to inject arbitrary BSON expressions into the pipeline.

`ZoneId.of(value)` throws on invalid IDs; controllers should return a clear validation error. Never splice client JSON strings into raw `Document` stages, preventing query/pipeline injection at the application layer.

### 20.3. Response Contracts Should State Data Completeness

Example response:

```json
{
  "deviceId": "S-01",
  "timezone": "UTC",
  "fromInclusive": "2026-11-20T09:00:00Z",
  "toExclusive": "2026-11-20T10:00:00Z",
  "bucketMinutes": 15,
  "unit": "C",
  "dataCompleteness": "PROVISIONAL",
  "buckets": [
    {
      "start": "2026-11-20T09:00:00Z",
      "samples": 3,
      "average": 22.0,
      "minimum": 20.0,
      "maximum": 24.0
    }
  ]
}
```

This format is **illustrative**; a real response returns all applicable buckets or paginated slices. `dataCompleteness` can be `PROVISIONAL` while late arrivals may still alter results, `FINAL` once finalized per business rules, or `PARTIAL_RETENTION` when raw data has expired. Never declare `"FINAL"` merely because the MongoDB query completed.

### 20.4. Caching Must Account for Late Arrivals

If a cache key only includes `deviceId+range` without `tenantId`, cross-tenant data leaks can occur. Even with tenant/zone/resolution in the key, a one-day cache TTL can hide late-arriving measurements from dashboards.

Strategy:

- Include tenant, device, time range, zone, resolution, quality policy, and algorithm version in cache keys.
- Use short TTLs for recent buckets and longer TTLs for finalized buckets per policy.
- Invalidate or recompute affected buckets when late data arrives.
- When serving from rollups, include `computedAt`/data freshness in responses.

## 21. Consistency Between Raw Measurements, Rollups, and Dashboards

Time-series queries read the logical collection as of execution time; a long-running report request can overlap incoming measurements, batch inserts, or concurrent rollup updates. **A completed aggregation query does not guarantee the report numbers will never change.**

### 21.1. Reading "the Same Day" Twice with Different Answers

```text
09:30  Dashboard reads 09:00–10:00
       raw measurements available: 09:02,09:07,09:14
       avg=22

09:35  Gateway uploads late measurement measuredAt=09:16
       avg for 09:00–10:00 now changes

09:40  Dashboard reads same range again
       avg based on 4 samples, not 3
```

This can be the **correct behavior** under event-time semantics. If a product requires immutable finalized figures, define a clear **cutoff/watermark** workflow rather than treating a "latest" raw query as a final accounting document.

### 21.2. Separating Provisional and Finalized Data

Suggested two-tier flow:

```text
Raw time series:
  measuredAt, receivedAt, eventId, metadata, value
        |
        v
Background aggregation with allowed lateness
        |
        v
Rollup:
  bucketStart, samples, sum, min, max,
  computedAt, revision, completenessStatus
        |
        v
Dashboard and exported reports
```

While late arrivals keep trickling in, a bucket may increment its revision from 3 to 4. If clients require change auditing, store revisions/changelogs in a regular collection with a clear schema. Never try to turn MongoDB time-series TTL into a business watermark.

### 21.3. Avoid Wrapping Huge Reports in Transactions by Default

A long aggregation scanning vast data carries its own cost and consistency rules. Never place every time-series reporting job inside a long-running multi-document transaction; execution time limits, resource caps, topology, and write stages impose constraints. Pick read concern/snapshot policies suited to actual consistency requirements, measure load, and use versioned rollups when publishing stable figures.

## 22. Diagnosing Wrong Results

| Symptom | Possible cause | Verification / fix |
| --- | --- | --- |
| Report counts 8 samples instead of 7 | Used `$lte` at upper bound, capturing 10:00 | Switch to `$lt`; test boundary |
| Average spikes unexpectedly instead of 26 | Forgot tenant or S-02 filter | Match `meta.tenantId` + `meta.deviceId` in DB |
| Group spans 2 hours/days instead of 1 day | Filtered in UTC, grouped in local timezone | Build UTC bounds consistently from `LocalDate + ZoneId` |
| Daily report shifted by 7 hours | Used `LocalDateTime` without timezone | Use `Instant` and `ZoneId` |
| DST day report misses or repeats an hour | Added fixed 24h for a local day | Compute next day's start in the target `ZoneId` |
| No row for 09:30 | No raw samples in that interval | Apply missing-data policy; do not assume 0 |
| Average 27.75 instead of 26 | Averaged bucket averages | Sum `sumValue` / sum `samples` |
| Count exceeds numeric samples | `$sum:1` counts null-value documents | Filter numeric values or count `$isNumber` separately |
| °C stats far too high | Mixed °C/°F or humidity values | Filter unit/sensorType or convert before grouping |
| Bucket jumps hours later | Late arrival updated event-time aggregate | Recompute overlap / rollup revision / freshness |
| Identical duplicate samples | Source retries wrote duplicates | Event ID / idempotent ingestion / deduplication |
| Queries return empty for older dates | TTL already dropped raw buckets | Check retention, rollups, or archives |
| Date-string range queries fail/misbehave | `measuredAt` stored as String, not BSON Date | Inspect raw BSON and migrate data |
| `$dateTrunc` unrecognized | MongoDB version too old | Check server version; upgrade or change operator |
| `@Document` hits wrong collection | Mismatched collection name | Check namespace and mapping |
| Raw Java aggregation misses numeric field | BSON field renamed via `@Field` | Inspect BSON and update raw `Document` stages |
| Buckets out of order | Missing `$sort` after `$group` | Add `$sort: { "_id": 1 }` |
| Daily query slow while hourly is fast | Wide range unpacking many buckets | Run `explain`, tune indexes, add rollups |
| Dashboard stale despite new raw samples | Cache or rollup not refreshed | Invalidation, freshness tracking, recompute |
| `$merge` fails | Missing unique index on rollup target, or missing privileges | Create proper target index; check merge version |
| Intended index not used | Time-series index restrictions/version/planner | Inspect `getIndexes()` and `explain()` |
| API query times out | Pulling millions of rows unbounded | Cap range, resolution, or use batch export jobs |
| Cross-tenant data leaks via cache | Cache key/query missing tenant | Enforce tenant in query + cache key + auth |
| Slight floating-point drift | `double` precision | Assert with tolerance; select numeric policy |

### 22.1. Inspect Raw BSON First

When reports show wrong timezones or metadata, inspect a real sample in the logical collection first:

```javascript
db.sensor_measurements.find(
  { "meta.tenantId": "TENANT-A" },
  { measuredAt: 1, meta: 1, value: 1, quality: 1 }
).limit(3)
```

Verify `Date` type, `meta` structure, and units. Looking only at Java DTOs through converters can hide distinctions between BSON String, Date, and Decimal128.

### 22.2. Run Stage by Stage to Pinpoint Discrepancies

Systematic debugging steps:

1. Run `$match` followed by `$count`; the fixture count must be 7.
2. Run `$match` + `$project` with `$dateTrunc` to see which bucket each sample enters.
3. Add `$group`, comparing each `samples` and `sumValue` against the manual table.
4. Add `$sort` and `$project`, verifying DTO mapping.
5. If rollup numbers drift, compare raw vs. rollup alongside revisions and late arrivals.

Never start debugging at frontend chart formatting when `$match` in MongoDB already selected the wrong dataset.

### 22.3. Never Fix Timezone Bugs by Adding/Subtracting 7 Hours Everywhere

Counter-example:

```java
Instant fixed = inputInstant.plusSeconds(7 * 3600);
```

This is not a general timezone conversion. `Instant` is already an absolute UTC timestamp; to derive a local day or hour, use `ZonedDateTime`/`ZoneId` for bounds. With DST, offsets are not fixed; adding 7 hours will also corrupt Vietnam reports whenever client input is already a proper instant.

## 23. Pre-Production Checklist for Time-Series Reports

1. **Correct collection:** verify actual `timeField`/`metaField` and namespace.
2. **Correct BSON types:** timestamps are BSON Dates; numeric values carry units and quality.
3. **Event time vs. ingest time:** confirmed which timestamp each question uses.
4. **Half-open ranges:** `$gte start` + `$lt end`, never `$lte` across adjacent intervals.
5. **Timezones:** `start`/`end` computed from `LocalDate` + `ZoneId`; grouping uses the same timezone.
6. **Tenant scoped:** tenant filter enforced in the database and authorized from user/session context.
7. **Stable metadata:** avoid putting per-sample changing fields into `metaField` unnecessarily.
8. **Quality policy:** invalid/missing samples filtered and surfaced transparently.
9. **Early `$match`:** filter metadata and time before large groupings.
10. **Bucket resolution:** bound total groups = device count × time buckets.
11. **Proper `$dateTrunc`:** `unit`/`binSize`/`timezone` verified against MongoDB server version.
12. **Complete group keys:** never mix devices, tenants, units, or sensor types semantically.
13. **Sorted output:** `$sort` by bucket timestamp after `$group`.
14. **Missing-data policy:** distinguish null/gap from zero.
15. **Weighted rollups:** retain sum/count, never average-of-averages.
16. **Late data:** define allowed lateness, recomputation, and rollup revisions.
17. **Duplicates:** establish event identity and deduplication policy.
18. **Retention:** ensure raw/rollup/archive lifetimes cover reporting horizons.
19. **Indexes:** evaluate meta+time indexes per version using `getIndexes()`/`explain()`.
20. **Error handling:** never turn database errors into empty reports.
21. **Reactivity:** never call `block()` in WebFlux; server aggregation still consumes resources.
22. **Rollup security:** restrict `$merge` to controlled jobs with proper target indexes and write roles.
23. **Integration tests:** cover boundaries, tenant/device isolation, numeric types, missing data, and timezones.
24. **Monitoring:** track latency, scan metrics, memory/spill, ingestion lag, rollup freshness, and errors.

## 24. Design Mistakes to Avoid

### 24.1. Formatting Time Strings in Java and Grouping in Memory

Instead of pulling millions of measurements into the JVM, formatting `measuredAt` into `yyyy-MM-dd HH:mm` strings, and grouping with `Collectors.groupingBy`, push `$dateTrunc` and `$group` to MongoDB. Reserve client-side aggregation for small, explicitly bounded datasets with clear justification.

### 24.2. Enabling TTL While Expecting Complete Historical Reports

TTL enforces retention policies, not historical archiving. If 1-year reports must stay available, keep corresponding rollups or archives; never wait for raw data to expire and then try to reconstruct it from the expired collection.

### 24.3. Mechanically Placing `$sort` on Raw Samples Before `$group`

`$sort` before `$group` is unnecessary for bucketed `sum/avg/min/max/count`, since those accumulators are order-independent. It can add substantial CPU and memory cost. Sort beforehand only for order-dependent accumulators like `$first`/`$last`, or when business logic genuinely requires chronological ordering.

### 24.4. Computing "Change Since Previous Reading" via Unsorted `$first`

To find the first or last sample inside each bucket, `$first`/`$last` depend on input order. You must explicitly sort by `measuredAt`, define tie-breakers for identical timestamps, and evaluate optimization/performance. Never rely on implicit time-series storage order to deduce a bucket's first or last measurement.

### 24.5. Mixing Incompatible Readings in One Bucket Because Field Names Match

A new metadata dimension (`firmwareVersion`, calibration version, unit) can change how readings are interpreted. When aggregations span calibration changes, define normalization or split grouping and audit changes. Never look only at `deviceId` while ignoring scientifically or operationally significant dimensions.

## 25. Practice Exercises

An energy monitoring system has real-time power meters. The `power_measurements` collection contains:

```javascript
{
  measuredAt: ISODate("2026-11-20T09:02:00Z"),
  meta: {
    tenantId: "TENANT-ENERGY",
    meterId: "M-001",
    unit: "kW"
  },
  value: 12.5,
  quality: "OK"
}
```

The initial goal is reporting **sample-average power** during working hours, then expanding to total energy consumed and daily reports.

### Exercise 1 — Modeling the Collection

Write `db.createCollection("power_measurements", {timeseries:{...}})`, choosing:

- `timeField = measuredAt`.
- `metaField = meta`.
- Granularity suited to measurements every few seconds to one minute.

Explain why `measuredAt` does not belong inside `meta`, and why `unit="kW"` is an important dimension when aggregating across multiple meters. Inspect actual options with `getCollectionInfos`.

### Exercise 2 — Half-Open Intervals

A user selects `09:00–10:00 UTC`. Write `Criteria`:

```java
Criteria criteria = Criteria
    .where("meta.tenantId").is("TENANT-ENERGY")
    .and("meta.meterId").is("M-001")
    .and("measuredAt")
        .gte(Date.from(start))
        .lt(Date.from(end));
```

Between `09:59:59.999` and `10:00:00.000`, which sample is included? If you next query `[10:00, 11:00)`, why is there no double-counting?

### Exercise 3 — 5-Minute `$dateTrunc`

Write the pipeline:

```javascript
[
  { $match: { /* time range, meterId, tenant, quality */ } },
  { $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 5,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      averageKw: { $avg: "$value" },
      minimumKw: { $min: "$value" },
      maximumKw: { $max: "$value" }
  }},
  { $sort: { _id: 1 } }
]
```

Explain why `09:04` falls into bucket `09:00`, while `09:05` falls into bucket `09:05`.

### Exercise 4 — Hand-Verified Fixture Data

Return to the temperature fixture:

```text
09:02 -> 20
09:07 -> 22
09:14 -> 24
09:16 -> 26
09:26 -> 28
09:32 -> 30
09:46 -> 32
```

Compute for each 15-minute window:

- Sample count.
- Sum of values.
- Average.
- Min and max.

Compare with the expected table in section 4.1. Run the real MongoDB pipeline and explain why `$group` needs `$sort` afterward.

### Exercise 5 — Weighted Average

Buckets have `count=[3,2,1,1]` and `avg=[22,27,30,32]`.

1. Compute the unweighted average of the four `avg` values.
2. Compute the true average across all seven samples.
3. Prove why `sum(sumValue)/sum(samples)` is the valid rollup formula.
4. If a bucket has `samples=0`, how must the formula guard against division by zero?

**Check answer:** 27.75 is the **wrong** average-of-averages for seven samples; 26 is the true average across all seven.

### Exercise 6 — Local Day

The API receives:

```text
day = 2026-11-20
timezone = Asia/Ho_Chi_Minh
```

Construct `DailyRange` using `LocalDate` and `ZoneId` and assert:

```text
startInclusive = 2026-11-19T17:00:00Z
endExclusive   = 2026-11-20T17:00:00Z
```

If you used UTC midnight for both querying and grouping, which day would late-evening Vietnam measurements be assigned to? Add a test with a DST timezone proving you cannot simply add 24 hours.

### Exercise 7 — Multi-Device Reporting

A tenant owns M-001 and M-002, both reporting at 09:05. Build the group key:

```javascript
_id: {
  meterId: "$meta.meterId",
  bucketStart: {
    $dateTrunc: {
      date: "$measuredAt",
      unit: "hour",
      timezone: "UTC"
    }
  }
}
```

If `meterId` is omitted from the group key, how does the meaning of the numbers change? If one meter reports in kW and another in W, can you average them directly?

### Exercise 8 — Empty Buckets

No samples arrived during `09:30–09:45`. Design two responses:

1. **Sparse:** return only populated buckets, omitting 09:30.
2. **Dense:** return every slot, using `samples=0`, `average=null`, `status="NO_DATA"` at 09:30.

Explain when to use `$densify`/`$fill`, when to generate a bounded timeline client-side, and why you should not auto-fill `0°C`/`0 kW` for every metric.

### Exercise 9 — Late Measurements

A job computes the 09:00 rollup at 10:10. At 11:00, a gateway uploads a delayed sample with `measuredAt=09:07`.

Design:

- Allowed lateness.
- Overlapping recompute window.
- Rollup revisioning.
- Cache invalidation strategy.
- Flags distinguishing provisional vs. finalized reports.

Explain why "computed accurately when the job ran" does not mean a report stays complete forever.

### Exercise 10 — Duplicates and Quality

A source retries and sends a duplicate `value=20` sample. How does `$sum: 1` change? Propose a stable producer `eventId`, a deduplication strategy compatible with time-series collection constraints, and how to verify it via integration tests.

Add one `quality="INVALID"` sample and one `value: null` sample. Compare:

- Document count.
- Numeric count.
- Average of valid numeric values.

Never treat `null` as zero temperature unless domain rules explicitly specify it.

### Exercise 11 — Rollups and `$merge`

Create a regular collection `power_rollups_15m` with a unique identity on tenant, meter, and `bucketStart`. Write the pipeline:

```text
raw measurements
  -> $match (tenant, meter, time, quality)
  -> $group (15-minute start, count, sum, min, max)
  -> $project (rollup fields)
  -> $merge into regular collection
```

Run it twice over the same interval and verify no duplicate rollup rows appear for the same key. Explain why double-counting can still happen if the raw source holds duplicate measurements and why `whenMatched: "replace"` cannot fix ingestion errors on its own.

### Exercise 12 — Performance

Compare `explain("executionStats")` for:

1. Single-device query over 1 hour.
2. Single-device query over 30 days.
3. Whole-tenant query over 30 days.
4. Rollup query over 30 days.

Record latency, docs/buckets examined, index selection, memory/spill, and row counts. Propose API caps on time range and resolution, a pre-aggregation plan, and cache invalidation. Never use a 10-document fixture to claim production indexes are "fast enough".

### Exercise 13 — Energy Consumption

`powerKw` is instantaneous power, not kWh energy delivered. If measurements arrive every 5 minutes and power is assumed constant until the next reading, design the estimated energy calculation:

```text
energyKWh ≈ sum(powerKw_i * elapsedHours_i)
```

Consider:

- If there is a 2-hour gap, should the last value be held across the entire gap?
- If a device sends late data, which buckets' energy must be recomputed?
- If measurements fall inside an interval without landing on exact start/end boundaries, how do you clip integration at the boundaries?
- Why is `$sum: "$powerKw"` wrong if labeled `energyKWh`?

This exercise is about **metric definitions**: syntactically valid MongoDB operators do not make physical formulas accurate on their own.

### Exercise 14 — Testing and Isolation

Write a `@DataMongoTest` on a dedicated database:

1. Create a **time-series collection** with verified options.
2. Insert the 7-sample fixture plus three control samples.
3. Assert `count=7`, `sum=182`, `avg=26`.
4. Assert the sample at exactly 10:00 falls only into the following interval.
5. Assert tenant B and S-02 are isolated out.
6. Assert BSON `measuredAt` is stored as `Date`.
7. Assert Vietnam local-day reporting uses the right bounds.
8. Assert empty ranges return empty lists rather than `avg=0`.
9. Clean up only the test-created collection inside the verified database, never dropping shared data.

## 26. Self-Check Questions

| Question | Suggested answer |
| --- | --- |
| Which BSON type does `timeField` store? | Date |
| What is `metaField` typically used for? | Stable metadata identifying the series / measurement source |
| Are time-series storage buckets the same as reporting buckets? | No |
| Why use `[start,end)`? | Adjacent intervals stitch without double-counting |
| Should the upper bound use `$lt` or `$lte`? | `$lt` |
| How does `Instant` differ from `LocalDateTime`? | `Instant` is an absolute UTC instant; `LocalDateTime` lacks a timezone |
| When does Vietnam day 2026-11-20 begin in UTC? | 2026-11-19 at 17:00Z |
| Which operator groups into 15-minute buckets? | `$dateTrunc` inside `$group` |
| Does `$group` guarantee output order? | No; add `$sort` |
| How many samples match the fixture report? | 7 |
| What are the fixture sum and average? | 182 and 26 |
| Why is the 27.75 average-of-averages wrong? | Bucket sample counts differ |
| Does an empty bucket equal 0? | No |
| Does TTL delete at the exact second of expiration? | No; cleanup is asynchronous with lag |
| How do late arrivals affect reports? | They can alter previously computed buckets |
| What does `$merge` do? | Writes aggregation results into a target collection |
| Does pre-aggregation automatically remove raw duplicates? | No |
| When is `explain` needed? | When tuning indexes/scans and diagnosing load |
| Can devices with different units be grouped into one `AVG`? | Not without prior unit normalization |
| What does `ReactiveMongoTemplate` help with? | Non-blocking client queries; the server still runs the aggregation |
| Is `$avg` a time-weighted average? | Not by default; it is the sample-weighted average of numeric values |
| Is a DST local day always 24 hours? | No |
| Why must tenant filtering happen on the server? | Correctness, security, and performance |

## 27. References

- MongoDB Manual — [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): time-series collection model and limitations.
- MongoDB Manual — [Create Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/): configuring `timeField`, `metaField`, and `granularity`.
- MongoDB Manual — [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/): indexing capabilities and version restrictions.
- MongoDB Manual — [Time Series Querying](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-querying/): querying by metadata and time.
- MongoDB Manual — [`$dateTrunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/): `unit`, `binSize`, `timezone`, and `startOfWeek`.
- MongoDB Manual — [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): accumulators `$sum`, `$avg`, `$min`, `$max`.
- MongoDB Manual — [`$match`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/): filtering before aggregation.
- MongoDB Manual — [`$densify`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/): generating missing points over ranges in supporting versions.
- MongoDB Manual — [`$fill`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/): controlling how missing values are populated.
- MongoDB Manual — [`$merge`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/): writing rollup outputs and target unique index requirements.
- MongoDB Manual — [Time Series TTL](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/): retention and automatic expiration.
- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `MongoTemplate`, `Query`, `Criteria`.
- Spring Data MongoDB — [Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `Aggregation`, input/output mapping, stages.
- Spring Data MongoDB — [Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `ReactiveMongoTemplate` and Publishers.
- Java SE — [Java Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `LocalDate`, `ZoneId`, and local time handling.

## Remember

**Accurate time-series reporting starts with defining time and data properly**, not with `$group`. Store `measuredAt` as BSON Date, filter tenant/device/unit/quality **inside MongoDB**, use half-open intervals `[startInclusive, endExclusive)` to prevent double-counting, and group into reporting buckets with `$dateTrunc` using the right `binSize` and `timezone`. `$group` computes `count/sum/avg/min/max` without emitting empty buckets; `$sort` guarantees chart ordering. When rolling up multiple buckets, divide **total sum by total count** rather than averaging bucket averages when sample counts differ. For local-day reports, convert `LocalDate + ZoneId` into UTC bounds and pass that same timezone when grouping, including across DST days. Late arrivals, duplicate measurements, TTL, and pre-aggregation can all alter or omit reported numbers; enforce explicit freshness, deduplication, retention, and rollup policies alongside integration tests verifying BSON types, boundaries, tenant isolation, and real values before going to production.
