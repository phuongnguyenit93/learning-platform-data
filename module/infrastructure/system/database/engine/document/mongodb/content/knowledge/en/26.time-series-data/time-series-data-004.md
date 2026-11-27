# Late-Arriving Data, Out-of-Order Writes, and Duplicate Measurements in MongoDB

## 1. Problem Statement and Objectives

Time series data appears across IoT sensors, telemetry, application metrics, market trades, device logs, and industrial systems. Each record captures a measurement at a point in time. However, **the order in which data is measured does not necessarily match the order in which it is received**:

- A device loses connectivity and later resends measurements from 10 minutes earlier.
- Two gateways push messages through queue partitions with different delays.
- A client times out and retries a message that was already processed.
- A source emits a correction for an older measurement.
- A device reboots and reuses sequence numbers.
- A backfill job imports historical data while the system simultaneously ingests real-time data.
- A device clock drifts, producing timestamps in the past or future.

MongoDB **time series collections** optimize storing and reading measurements via `timeField`, `metaField`, and internal buckets. However, they **do not automatically provide** a late-data policy, watermarks, measurement identity resolution, or duplicate prevention like a standard unique key.

After this lesson, you will be able to:

1. Distinguish **event time**, **ingestion time**, and **processing time**.
2. Understand how MongoDB handles out-of-order timestamps and their impact on buckets.
3. Distinguish an **event retry duplicate**, a **logical measurement**, and a **revision/correction**.
4. Detect duplicates, compute canonical values, and recompute time windows.
5. Understand time series collection limitations regarding `unique index`, `_id`, `upsert`, `$merge`, and transactions.
6. Design a dedicated ingestion registry with a unique index, alongside a recovery plan when dual-writes are non-atomic.
7. Define **allowed lateness**, watermarks, `provisional`/`final`/`revised` states, and a backfill strategy.
8. Monitor lag, bucketing efficiency, TTL, and duplicate data.

**Core principle:** Just because MongoDB successfully stores a record does not mean that record is a new measurement, in order, or meant to be counted again in reports.

## 2. Three Timestamps of a Measurement

An event often needs separate timestamps:

| Field | Meaning | Assigned by | Purpose |
| --- | --- | --- | --- |
| `observedAt` | **Event time** — when measured | Device or business source | Window grouping, chronological order, analytics |
| `receivedAt` | **Ingestion time** — when received | Gateway or backend | Measuring late arrival, auditing |
| `processedAt` | **Processing time** — when processed | Worker/processor | Measuring pipeline latency, retries |
| `sentAt` (optional) | When source transmitted the message | Device | Separating network delay from device buffering |

Example:

```javascript
{
  eventId: "sensor-A:boot-7:seq-104",
  sampleId: "sensor-A:boot-7:sample-104",
  revision: 1,
  meta: {
    tenantId: "factory-1",
    deviceId: "sensor-A",
    metric: "temperature"
  },
  observedAt: ISODate("2026-11-14T09:00:00Z"),
  receivedAt: ISODate("2026-11-14T09:04:30Z"),
  value: 21.5,
  unit: "C"
}
```

The measurement occurred at **09:00 UTC** but reached the backend at **09:04:30 UTC**; ingestion delay is 270 seconds assuming both clocks are trustworthy.

Never replace `observedAt` with `receivedAt` merely to make timestamps increase monotonically: doing so shifts the 09:00 report into 09:04.

### 2.1. Two Different Orderings

```text
Measurement OCCURRENCE order:
08:59     09:00     09:01     09:02
 M0        M1        M2        M3

System RECEIPT order:
09:00:05  09:02:02  09:03:00  09:03:10
 M1        M3        M0        M2
```

- **Out-of-order:** measurement M2 arrives after M3 even though `observedAt(M2)` is earlier.
- **Late:** a measurement arrives past a business-defined processing *cutoff*, such as after a window has finalized or more than 2 minutes past event time.

A measurement carrying an older timestamp than the previously received one **is not necessarily invalid**. It may fall within allowed lateness.

### 2.2. Device Clocks Are a Source of Errors

When computing `receivedAt - observedAt`, verify:

- NTP or the device's clock-synchronization mechanism.
- Whether timestamps carry an explicit timezone.
- Whether clocks reset after a reboot.
- Whether an event "from the future" is caused by a fast device clock.
- Whether `receivedAt` is stamped at initial ingress or after queue delay.
- Whether retries preserve the original source timestamp or stamp a new one.

BSON Date stores instants in UTC. Normalize timezones at ingress and reject or quarantine invalid timestamps according to source rules.

## 3. How Does MongoDB Bucket Data?

A time series collection groups measurements by **identical `metaField` values** and sufficiently close `timeField` timestamps. Buckets have limits on time span, measurement count, byte size, and cache residency.

```text
meta = {deviceId: "A", metric: "temperature"}

Bucket matching earlier range: 08:59
Bucket matching newer range:   09:00, 09:01, 09:02
```

This diagram is conceptual and does not guarantee one bucket per hour. Situations that open a new bucket include:

- No active bucket matches `metaField`.
- The timestamp falls outside the span of active buckets.
- The bucket reaches its measurement count or size limit.
- A bucket closes due to resource pressure, restart, or conflicting writes.

MongoDB rounds timestamps when creating buckets according to bucketing settings, accommodating timestamps **arriving out of order within close ranges**. Still, never promise that every old event appends to its old bucket at the same cost as a fresh insert. Late backfills can trigger extra buckets, I/O, and cache pressure.

### 3.1. Choosing a Stable `metaField`

Good:

```javascript
meta: {
  tenantId: "factory-1",
  deviceId: "sensor-A",
  metric: "temperature"
}
```

Do not put `receivedAt`, `requestId`, or `retryCount` (which change on each submission) inside `metaField`. Frequently changing `meta` produces many sparse buckets and hurts compression and filtering efficiency.

### 3.2. `granularity` Is Not a "Max Lateness" Policy

`granularity` accepts `seconds`, `minutes`, and `hours`. Depending on version, `bucketMaxSpanSeconds` and `bucketRoundingSeconds` are also available. These configure **bucketing** around measurement cadence and time spans—they are **not** the ingestion pipeline's allowed-lateness threshold.

Do not set `granularity: "hours"` simply to tolerate two-hour-late events; benchmark measurement frequency, bucket sizes, and queries instead.

## 4. Key Limitations: Time Series Collections Are Not Regular Collections

The following constraints directly shape how you handle duplicates and corrections:

| Feature | Time series collection | Consequence |
| --- | --- | --- |
| **Unique index** | **Unsupported** | Cannot create a unique index directly on device/time/`eventId` |
| Default `_id` index | **No default unique `_id` index** | A deterministic `_id` will not block duplicates automatically |
| Updates | Restricted to `metaField`, cannot arbitrarily edit measurement fields, no upsert | Cannot handle corrections via standard value updates |
| Transaction writes | **Unsupported** | Cannot atomically wrap registry insert and time series insert in one transaction |
| `$merge` into time series | **Unsupported** | Cannot use aggregation `$merge` to upsert into time series |
| Schema validation rules | Not supported like regular collections | Validate in application or staging layer |
| Read aggregations | Supported with appropriate limits | Use `$sort`, `$group` to detect and canonicalize |

Rules evolve across MongoDB versions. When deploying, verify your exact **server version, Feature Compatibility Version, and driver**.

**Invalid** example:

```javascript
db.measurements.createIndex(
  { "meta.deviceId": 1, observedAt: 1 },
  { unique: true }
);
```

Example **not to design** for time series:

```javascript
db.measurements.updateOne(
  { "meta.deviceId": "sensor-A", observedAt: someTime },
  { $set: { value: 25 } },
  { upsert: true }
);
```

Note: MongoDB time series collections have no default unique `_id` index. **A deterministic `_id` does not automatically provide idempotency** without a supported uniqueness mechanism.

## 5. Initializing the Time Series Lab

Run the examples in `mongosh` on a MongoDB version supporting time series collections. Use a dedicated lab database only; **never run `drop()` in production**.

```javascript
const lab = db.getSiblingDB("ts_late_duplicate_lab");

lab.measurements.drop();
lab.ingestKeys.drop();
lab.canonicalReadings.drop();

lab.createCollection("measurements", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  }
});
```

Logical measurement design in the lab:

```javascript
{
  eventId: "A-0901-r1",
  sampleId: "09:01",
  revision: 1,
  meta: {
    tenantId: "factory-1",
    deviceId: "sensor-A",
    metric: "temperature"
  },
  observedAt: ISODate("2026-11-14T09:01:00Z"),
  receivedAt: ISODate("2026-11-14T09:03:10Z"),
  value: 21,
  unit: "C"
}
```

- `eventId`: identity of **a source event**, which may be retried.
- `sampleId`: identity of **a logical measurement**, which may have multiple revisions.
- `revision`: correction version number.
- `meta`: stable series identity.
- `observedAt`: business timestamp serving as the time series axis.

`sampleId: "09:01"` is only for this single-day fixture. Production must use a `sampleId` durable across days, such as source sequence + boot ID or a full timestamp plus channel.

## 6. Fixture of 12 Raw Measurements: Out-of-Order + Retry + Correction

Use three temperature sensors A, B, and C. The array below is ordered **by simulated receipt time**, while some `observedAt` values do not increase monotonically. `receivedAt` holds fixed timestamps for easy verification; a single `insertMany` does not simulate real wait intervals between events.

```javascript
const a = {
  tenantId: "factory-1",
  deviceId: "sensor-A",
  metric: "temperature"
};

const b = {
  tenantId: "factory-1",
  deviceId: "sensor-B",
  metric: "temperature"
};

const c = {
  tenantId: "factory-1",
  deviceId: "sensor-C",
  metric: "temperature"
};

lab.measurements.insertMany([
  {
    eventId: "A-0900-r1", sampleId: "09:00", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:05Z"),
    value: 20, unit: "C"
  },
  {
    eventId: "B-0900-r1", sampleId: "09:00", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:10Z"),
    value: 30, unit: "C"
  },
  {
    eventId: "C-0900-r1", sampleId: "09:00", revision: 1,
    meta: c,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:15Z"),
    value: 18, unit: "C"
  },
  {
    eventId: "B-0901-r1", sampleId: "09:01", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:01:10Z"),
    value: 31, unit: "C"
  },
  {
    eventId: "C-0901-r1", sampleId: "09:01", revision: 1,
    meta: c,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:01:20Z"),
    value: 20, unit: "C"
  },
  {
    eventId: "A-0902-r1", sampleId: "09:02", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:02:00Z"),
    receivedAt: ISODate("2026-11-14T09:02:02Z"),
    value: 22, unit: "C"
  },
  {
    eventId: "A-0859-r1", sampleId: "08:59", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T08:59:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:00Z"),
    value: 19, unit: "C"
  },
  {
    eventId: "B-0903-r1", sampleId: "09:03", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:03:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:05Z"),
    value: 33, unit: "C"
  },
  {
    eventId: "A-0901-r1", sampleId: "09:01", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:10Z"),
    value: 21, unit: "C"
  },
  // Retry with the same eventId, revision, and source payload.
  {
    eventId: "A-0901-r1", sampleId: "09:01", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:15Z"),
    value: 21, unit: "C"
  },
  // Correction: same logical sample, new revision.
  {
    eventId: "A-0901-r2", sampleId: "09:01", revision: 2,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:04:00Z"),
    value: 21.5, unit: "C"
  },
  // Late retry from B.
  {
    eventId: "B-0901-r1", sampleId: "09:01", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:05:00Z"),
    value: 31, unit: "C"
  }
]);

lab.measurements.countDocuments({});
// 12
```

The dataset contains:

- **12 raw documents**.
- **10 distinct `eventId` values**.
- **2 extra deliveries** due to retries (`A-0901-r1` and `B-0901-r1`).
- **1 revision correction** (`A-0901-r2`).
- **9 logical measurements** after deduplicating and selecting revisions.

This follows the fixture's conventions—MongoDB is not automatically detecting duplicates.

## 7. Reading by Event Time, Never Trusting Insert Order

```javascript
lab.measurements.find(
  { "meta.deviceId": "sensor-A" },
  {
    _id: 0,
    eventId: 1,
    observedAt: 1,
    receivedAt: 1,
    revision: 1,
    value: 1
  }
).sort({
  observedAt: 1,
  revision: 1,
  receivedAt: 1
}).toArray();
```

`sensor-A` records, ordered by event time:

| `observedAt` (UTC) | `eventId` | `receivedAt` | `value` |
| --- | --- | --- | ---: |
| 08:59 | A-0859-r1 | 09:03:00 | 19 |
| 09:00 | A-0900-r1 | 09:00:05 | 20 |
| 09:01 | A-0901-r1 | 09:03:10 | 21 |
| 09:01 | A-0901-r1 | 09:03:15 | 21 |
| 09:01 | A-0901-r2 | 09:04:00 | 21.5 |
| 09:02 | A-0902-r1 | 09:02:02 | 22 |

Without `.sort()`, a query makes no guarantee to return results in `observedAt`, `receivedAt`, `_id`, or bucket order. When timestamps tie, define explicit **tie-breakers** such as `revision` and `eventId`.

## 8. Computing Per-Event Delay with `$dateDiff`

```javascript
lab.measurements.aggregate([
  {
    $set: {
      delaySeconds: {
        $dateDiff: {
          startDate: "$observedAt",
          endDate: "$receivedAt",
          unit: "second"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      eventId: 1,
      "meta.deviceId": 1,
      observedAt: 1,
      receivedAt: 1,
      delaySeconds: 1
    }
  },
  { $sort: { delaySeconds: -1, eventId: 1 } }
]).toArray();
```

Delays for selected records:

| `eventId` | `observedAt` | `receivedAt` | Delay |
| --- | --- | --- | ---: |
| A-0859-r1 | 08:59 | 09:03:00 | 240 s |
| B-0901-r1 (retry) | 09:01 | 09:05:00 | 240 s |
| A-0901-r2 | 09:01 | 09:04:00 | 180 s |
| A-0901-r1 (retry) | 09:01 | 09:03:15 | 135 s |
| A-0901-r1 (first) | 09:01 | 09:03:10 | 130 s |

Find raw documents delayed over 120 seconds:

```javascript
lab.measurements.aggregate([
  {
    $set: {
      delaySeconds: {
        $dateDiff: {
          startDate: "$observedAt",
          endDate: "$receivedAt",
          unit: "second"
        }
      }
    }
  },
  { $match: { delaySeconds: { $gt: 120 } } },
  {
    $project: {
      _id: 0,
      eventId: 1,
      delaySeconds: 1
    }
  }
]).toArray();
```

There are **5 raw documents** exceeding 120 seconds. However, **high delay does not mean the event must be dropped**: it may be a valid backfill.

Note that `$dateDiff` with `"second"` counts unit boundary crossings; for sub-second precision or clock-skew checks, computing in milliseconds may be more accurate.

## 9. Defining What "Duplicate" Means at Each Level

Scenarios:

| Received data | Is it a duplicate? | Appropriate policy |
| --- | --- | --- |
| Same `eventId`, identical source payload | Usually a **retry** | Do not count as an extra measurement |
| Same `sampleId`, new `revision` | **Correction**, not a retry | Select the newer revision per policy |
| Two devices both measure at 09:01 | No | Each device is a distinct series |
| Same device and timestamp, different channel | Not necessarily | Include metric/channel in identity |
| Same measured value, two genuine `eventId`s | Insufficient basis to merge | Keep if they are two valid readings |
| Same `eventId`, differing payload | **Conflict** | Quarantine and reconcile |
| Sequence reset after reboot | Possible collision | Add `bootId` or epoch to the key |
| Backfill job resending old data | Could be retry or correction | Compare identity and revision |

Recommended identities:

```text
Delivery identity:
  (tenantId, eventId)

Logical sample:
  (tenantId, deviceId, metric, sampleId)

Version:
  (tenantId, deviceId, metric, sampleId, revision)
```

Relying solely on `(deviceId, observedAt)` risks wrongly merging two distinct measurements sharing the same millisecond. `sampleId` should be generated by the source under contract, rather than guessed from timestamps when sampling rates make collisions possible.

### 9.1. Payload Fingerprint for Conflicts

Compute a hash of the **canonical source payload** (such as SHA-256) prior to storage. When the same `eventId` arrives again:

- Matching hash: likely a retry.
- Different hash: never silently ignore; quarantine it.
- `receivedAt` should not be included in the source payload hash because each retry carries a different ingestion timestamp.
- When a source corrects a reading, it should issue a **new `revision`/`eventId`**, never reuse an old `eventId` with a different value.

Hashing is a conditional payload-comparison tool; it does not decide correction semantics on its own.

## 10. Detecting Duplicate `eventId` Retries

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        eventId: "$eventId"
      },
      copies: { $sum: 1 },
      firstSeen: { $min: "$receivedAt" },
      lastSeen: { $max: "$receivedAt" }
    }
  },
  { $match: { copies: { $gt: 1 } } },
  { $sort: { "_id.eventId": 1 } }
]).toArray();
```

Result:

| `eventId` | `copies` | Extra deliveries |
| --- | ---: | ---: |
| A-0901-r1 | 2 | 1 |
| B-0901-r1 | 2 | 1 |

Count distinct event IDs and extra copies:

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        eventId: "$eventId"
      },
      n: { $sum: 1 }
    }
  },
  {
    $group: {
      _id: null,
      distinctEvents: { $sum: 1 },
      extraDeliveries: {
        $sum: { $subtract: ["$n", 1] }
      }
    }
  }
]).toArray();

// distinctEvents: 10
// extraDeliveries: 2
```

Grouping by `eventId` does **not** collapse correction `A-0901-r2`, because the correction has a new `eventId`. To obtain one value per logical measurement, group by `sampleId` and pick the canonical revision.

## 11. Selecting the Canonical Revision for Each Logical Sample

Fixture rules:

1. Each logical measurement is identified by `tenantId`, `deviceId`, `metric`, and `sampleId`.
2. The highest `revision` is selected.
3. If the same `revision` arrives multiple times, use `receivedAt` and `eventId` as deterministic tie-breakers.
4. **If the same `revision` carries differing payloads** in a real system, never blindly pick the latest arrival; run conflict resolution.

```javascript
const canonicalPrefix = [
  {
    $sort: {
      "meta.tenantId": 1,
      "meta.deviceId": 1,
      "meta.metric": 1,
      sampleId: 1,
      revision: -1,
      receivedAt: -1,
      eventId: -1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        deviceId: "$meta.deviceId",
        metric: "$meta.metric",
        sampleId: "$sampleId"
      },
      latest: { $first: "$$ROOT" },
      rawCopiesAndVersions: { $sum: 1 }
    }
  }
];

lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $project: {
      _id: 0,
      deviceId: "$_id.deviceId",
      sampleId: "$_id.sampleId",
      observedAt: "$latest.observedAt",
      revision: "$latest.revision",
      value: "$latest.value",
      eventId: "$latest.eventId",
      rawCopiesAndVersions: 1
    }
  },
  { $sort: { deviceId: 1, observedAt: 1 } }
]).toArray();
```

Canonical result:

| Device | `sampleId` | `revision` | `value` |
| --- | --- | ---: | ---: |
| A | 08:59 | 1 | 19 |
| A | 09:00 | 1 | 20 |
| A | 09:01 | **2** | **21.5** |
| A | 09:02 | 1 | 22 |
| B | 09:00 | 1 | 30 |
| B | 09:01 | 1 | 31 |
| B | 09:03 | 1 | 33 |
| C | 09:00 | 1 | 18 |
| C | 09:01 | 1 | 20 |

Total: **9 logical measurements**.

### 11.1. Why `$sort` Must Precede `$first`

`$first` inside `$group` is meaningful only when input order is explicitly defined. Without an explicit `$sort`, it does not automatically know what "highest revision" means.

If two events share the same revision but arrive at different workers, `receivedAt` is merely a **tie-breaker**, not proof of which value is accurate. Correctness requires monotonic revisions or source priority defined by the business.

## 12. Duplicates Skew Aggregations

Computing averages directly over raw documents:

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: "$meta.deviceId",
      count: { $sum: 1 },
      rawAverage: { $avg: "$value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Device | Raw count | Raw average |
| --- | ---: | ---: |
| A | 6 | **20.75** |
| B | 4 | **31.25** |
| C | 2 | **19** |

After canonicalization:

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $group: {
      _id: "$_id.deviceId",
      logicalCount: { $sum: 1 },
      canonicalAverage: { $avg: "$latest.value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Device | Logical count | Canonical average |
| --- | ---: | ---: |
| A | 4 | **20.625** |
| B | 3 | **31.333333…** |
| C | 2 | **19** |

Device A has 6 raw records but only 4 logical samples: revision 1 of 09:01 was sent twice, and revision 2 was a correction. B has one retry. C has no retries or corrections.

**Deduplicating by `eventId` alone is still not enough:** two revisions with distinct `eventId`s still refer to one logical sample. If the domain expects one current value, you must resolve revisions.

Not every metric selects the latest revision: balances/counters, financial transactions, or log events may require *compensating events* rather than overwrites. The rule comes from the domain.

## 13. Window Aggregations Must Use Event Time

A dashboard computing per-minute averages should use `observedAt` when the question is **"the value at that time"**, not when the gateway received it.

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $set: {
      minuteStart: {
        $dateTrunc: {
          date: "$latest.observedAt",
          unit: "minute",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: "$minuteStart",
      samples: { $sum: 1 },
      average: { $avg: "$latest.value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Result:

| Minute UTC | Logical samples | Total value | Average |
| --- | ---: | ---: | ---: |
| 08:59 | 1 | 19 | 19 |
| 09:00 | 3 | 68 | 22.666667 |
| 09:01 | 3 | 72.5 | 24.166667 |
| 09:02 | 1 | 22 | 22 |
| 09:03 | 1 | 33 | 33 |

### 13.1. Late Arrivals Alter Previously Displayed Windows

Suppose at 09:02 the dashboard computes window `[09:01, 09:02)` before A's 09:01 reading has arrived.

Initial result includes only B and C:

```text
(31 + 20) / 2 = 25.5
```

After A sends revision 1:

```text
(31 + 20 + 21) / 3 = 24
```

After A sends correction revision 2:

```text
(31 + 20 + 21.5) / 3 ≈ 24.166667
```

If the dashboard publishes `25.5` as **final** immediately at 09:02 and disallows updates, it fails to reflect valid late-arriving data.

For minute windows, use half-open intervals **`[start, end)`**: inclusive of start, exclusive of end. An event at `09:02:00` belongs to the next window, not `[09:01, 09:02)`.

## 14. Allowed Lateness and Watermarks

**Allowed lateness** is an application or stream-processor policy permitting a window's output to update after the window nominally closes.

Example:

```text
Window:           [09:01, 09:02)
Allowed lateness: 3 minutes
```

Define **which clock governs this**:

- Measured from window end in wall-clock/processing time?
- Driven by event-time watermark progression?
- Watermark tracked per device, per partition, or globally across the stream?
- If a device stops sending, does the watermark keep advancing?
- Are very late events dropped, quarantined, or routed to backfill?

**MongoDB time series collections do not close event-time windows or emit watermarks.** MongoDB stores measurements; finalization logic belongs in the processing tier.

### 14.1. Illustrative Watermark

A simple model:

```text
watermark = maxObservedEventTimeSeen - maxExpectedOutOfOrderDelay
```

Suppose:

```text
Max event time seen:          09:05:00
Expected out-of-order delay:  2 minutes
Watermark:                    09:03:00
```

Under processor policy, windows ending at or before the watermark can be marked complete **at the chosen confidence level**.

Even so, a `09:01` event may still arrive later. A watermark is a **heuristic estimate of event-time progress**, never a guarantee that no older event can arrive.

With parallel sources, watermarks must handle **idle partitions**. Never assume the watermark always equals `receivedAt - 2 minutes`.

### 14.2. Provisional, Final, and Revised States

| State | Meaning | When a late event arrives |
| --- | --- | --- |
| `provisional` | Window not yet closed per policy | Update the result |
| `final` | Past expected lateness cutoff | Keep as-is or apply correction policy |
| `revised` | Late/corrected data altered a finalized result | Write a new revision and notify downstream |

When materializing aggregates, store:

```javascript
{
  windowStart: ISODate("2026-11-14T09:01:00Z"),
  windowEnd: ISODate("2026-11-14T09:02:00Z"),
  revision: 2,
  status: "revised",
  average: 24.1666666667,
  sampleCount: 3,
  computedAt: new Date()
}
```

The `revision` of a **window aggregate** is separate from the `revision` of an **individual measurement**. Downstream consumers need to know when a published summary changes.

## 15. Three Deduplication Architectures

| Strategy | How it works | Pros | Limitations |
| --- | --- | --- | --- |
| **A. Raw append + read-time dedup** | Write all events to time series; resolve canonical at query time | Simple, preserves audit trail | Higher storage and aggregation cost |
| **B. Unique inbox + time series sink** | Block duplicate `eventId` in a regular collection, then append | Protects ingress across writers | Non-atomic dual-write |
| **C. Regular canonical store + time series projection** | Uniqueness/updates in regular collection; time series for analytics | Strong source of truth and version control | Projection lag and extra operational complexity |

No single solution fits every case. Choose based on accuracy requirements, retention, latency, throughput, and tolerance for eventual consistency.

## 16. Strategy A: Raw Append, Query-Time Deduplication

Strengths:

- Direct `insertOne`/`insertMany` into the time series collection.
- No need to mutate stored measurements.
- Corrections handled cleanly via new revisions.
- Raw events preserve an audit trail and enable reprocessing.

Weaknesses:

- Retries create extra raw documents.
- Canonical aggregation using `$sort` + `$group` consumes resources.
- Materialized reports must be recomputed when late events arrive.
- Once TTL purges raw data, history cannot be rebuilt from it.

On large collections, always **filter by series and time range before grouping**:

```javascript
lab.measurements.aggregate([
  {
    $match: {
      "meta.deviceId": "sensor-A",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T10:00:00Z")
      }
    }
  },
  {
    $sort: {
      sampleId: 1,
      revision: -1,
      receivedAt: -1,
      eventId: -1
    }
  },
  {
    $group: {
      _id: "$sampleId",
      newest: { $first: "$$ROOT" }
    }
  },
  { $replaceRoot: { newRoot: "$newest" } },
  { $sort: { observedAt: 1 } }
]).toArray();
```

This groups by `sampleId` only because the `$match` stage locked onto one device and a short window in our fixture. Production must group by the **full logical identity** whenever `sampleId` is not globally unique.

## 17. Strategy B: Unique Inbox in a Regular Collection

Time series collections **do not support unique indexes**, whereas **regular collections** do.

```javascript
lab.ingestKeys.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event"
  }
);
```

Claim an event:

```javascript
lab.ingestKeys.insertOne({
  tenantId: "factory-1",
  eventId: "A-0901-r1",
  payloadFingerprint: "sha256-of-canonical-source-payload",
  state: "pending",
  createdAt: new Date()
});
```

If two workers attempt to insert entries with the same `(tenantId, eventId)`, the unique index prevents both from creating duplicate registry documents, raising an `E11000` error.

### 17.1. Upserts Apply to the Registry, Not the Time Series Collection

```javascript
const result = lab.ingestKeys.updateOne(
  {
    tenantId: "factory-1",
    eventId: "A-0902-r1"
  },
  {
    $setOnInsert: {
      payloadFingerprint: "source-payload-hash",
      state: "pending",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(result);
```

An equality filter matching the unique key prevents two registry entries for the same identity. Under concurrency, an upsert can still turn into an update or return a duplicate-key error; the application needs proper error handling.

When an `eventId` already exists, read the registry entry and compare fingerprints; **never treat every `E11000` as an identical payload**.

### 17.2. Crashes Between Two Collections: No Atomic Dual-Write

A simple pipeline:

```text
1. Insert registry claim (unique)
2. Insert measurement into time series
3. Update registry state = delivered
```

Failure windows:

| Crash point | Registry | Time series | Risk |
| --- | --- | --- | --- |
| After step 1, before step 2 | `pending` | Missing | Ignoring `pending` loses the measurement |
| After step 2, before step 3 | `pending` | Present | Retrying the append may create a duplicate |
| After step 3 | `delivered` | Expected present | Still check write concern and network ambiguity |

You cannot wrap a time-series insert and a registry insert inside **a single MongoDB write transaction** because time series collections do not support transaction writes.

Therefore, **a unique registry deduplicates at registration time; it does not by itself guarantee exactly-once raw appends**.

### 17.3. At-Most-Once, At-Least-Once, and Exactly-Once Logical Results

- **At-most-once append:** do not retry writes with unknown outcomes; lowers duplicates at the risk of losing events.
- **At-least-once append:** retry to avoid data loss, potentially creating multiple raw documents.
- **Exactly-once logical result:** requires canonical identity and deduplication/revision resolution, or using a regular collection with unique constraints as the source of truth.

If downstream consumers require zero logical duplicates, never treat raw document counts as measurement counts.

## 18. Strategy C: Regular Canonical Collection

For sources demanding strong uniqueness and controlled corrections, a regular collection can hold the **canonical record**.

```javascript
lab.canonicalReadings.createIndex(
  {
    tenantId: 1,
    deviceId: 1,
    metric: 1,
    sampleId: 1
  },
  {
    unique: true,
    name: "uq_canonical_sample"
  }
);
```

Regular collections support unique indexes and atomic conditional updates/upserts under regular semantics. You can store the current revision there while keeping revision history in another collection for auditing.

A time series collection remains valuable for compressed raw telemetry and analytics, though syncing into it becomes **eventual materialization**.

### 18.1. Materializing from Time Series into a Regular Collection

MongoDB permits `$merge` **from** a time series collection **into** a **regular collection**. Never target a time series collection with `$merge`.

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $project: {
      _id: 1,
      tenantId: "$_id.tenantId",
      deviceId: "$_id.deviceId",
      metric: "$_id.metric",
      sampleId: "$_id.sampleId",
      observedAt: "$latest.observedAt",
      revision: "$latest.revision",
      value: "$latest.value",
      eventId: "$latest.eventId"
    }
  },
  {
    $merge: {
      into: "canonicalReadings",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);

lab.canonicalReadings.countDocuments({});
// 9
```

`_id` in the output is an object identifying the logical sample. The regular collection has a unique `_id` index; `$merge` updates each canonical document by this key.

This is a **full batch reconciliation for the lab**. In production, if two materialization jobs process overlapping data across different boundaries or times, a slower job can overwrite newer revisions with stale ones. Use checkpoints, job serialization, or version-aware compare-and-set.

**Invalid** example targeting a time series collection:

```javascript
db.rawInput.aggregate([
  {
    $merge: {
      into: "measurements",
      whenMatched: "replace"
    }
  }
]);
```

## 19. Corrections: Append Revisions or Update Canonical State?

A correction can be modeled as:

```text
A:09:01 revision 1 = 21.0
A:09:01 revision 2 = 21.5
```

Three approaches:

1. **Append revisions:** keep both in time series; queries pick revision 2.
2. **Canonical mutable store:** a regular collection stores the current value and revision; corrections are guarded by conditional updates.
3. **Compensating events:** rather than overwriting, emit a new event adjusting the prior event's effect; common in accounting domains.

Never mutate `value` directly on a time-series document using an upsert as if it were a regular collection.

If two sources both submit revision 2 with different payloads, policy must trigger conflict/quarantine handling rather than blindly assuming "higher `receivedAt` wins".

## 20. TTL Can Purge Very Late Measurements

Create another time-series collection with 24-hour retention:

```javascript
lab.shortRetention.drop();

lab.createCollection("shortRetention", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 86400
});
```

Time series TTL relies on **`timeField`**, here `observedAt`, not `receivedAt`. MongoDB cleans up expired measurements/buckets via a background task, not at the exact millisecond of expiration.

If a device sends an event today whose `observedAt` is from **three days ago**, it may be accepted upon insert yet already exceed the retention window and be cleaned up in an upcoming TTL pass.

Never promise "every event is retained for 24 hours from ingestion" when TTL is evaluated against event time.

### 20.1. Questions When Aligning TTL and Allowed Lateness

- Is retention longer than the late-arrival window you must handle?
- Will historical backfills span days or weeks?
- Are raw events still needed to rebuild aggregations?
- Is there a durable canonical source elsewhere?
- Is data purged by TTL reconciled against dashboards?

Some systems keep short hot raw retention while archiving long-term history elsewhere for backfills and compliance.

## 21. How Out-of-Order Data Impacts Performance

Factors to measure:

- Older events lacking an eligible active bucket → may open another bucket.
- Many unique `meta` values → bucket catalog holds many sparsely populated buckets.
- Wide backfills → elevated I/O and cache churn competing with real-time ingestion.
- Retries → higher storage and deduplication overhead.
- Corrections → more revisions/documents per sample.
- Collection-wide `$sort`/`$group` → high aggregation memory and CPU consumption.
- Concurrent TTL + backfill → simultaneous ingestion and old-bucket cleanup.
- Secondary reads may lag further under heavy replication load.

**Do not** blindly alter `granularity` solely because late arrivals exist. `granularity` should reflect measurement cadence and target bucket density. Changing bucket parameters post-creation carries version-specific restrictions.

For large queries, pre-filter by `meta` and time range prior to deduplication, verify indexes, and monitor keys/docs examined alongside resource usage.

## 22. Buffering and Sorting Before Writing: Benefits and Limits

An ingestion pipeline can buffer events briefly before appending:

```text
Devices
   |
Gateway
   |
Per-device buffer (short, bounded)
   |
Sort by observedAt
   |
Batch insert into time series
```

Pros:

- Smooths minor network-induced out-of-order jitter.
- Enables batch inserts for better efficiency.
- Can collapse some retries inside the buffer window.

Cons:

- Increases end-to-end latency.
- Requires memory/queues and durability.
- Events arriving hours late still bypass the buffer.
- Multiple workers can reorder events unless partitioned/coordinated.
- Buffering does not replace a unique registry, correction handling, or idempotency.

**Buffering is an ingestion optimization**, not a global consistency guarantee.

## 23. Safe Backfill Procedure

When re-importing historical data:

1. Identify the authoritative data source.
2. Preserve original `observedAt` values; never stamp import time as event time.
3. Preserve or generate deterministic `eventId`s across re-runs.
4. Record logical `sampleId` and `revision`.
5. Check the target time series collection's TTL.
6. Run throttled batches so backfills do not starve real-time ingestion of I/O.
7. Maintain checkpoints to resume cleanly after crashes.
8. Count raw events, unique event IDs, corrections, and conflicts.
9. Recompute affected event-time windows.
10. Increment revisions of materialized aggregates and notify downstream consumers.
11. Reconcile data integrity against the source.
12. Support rollback/rebuilding canonical outputs if a mapping bug occurs.

Example of an event measured at 09:01 and backfilled at 15:00:

```javascript
{
  observedAt: ISODate("2026-11-14T09:01:00Z"),
  receivedAt: ISODate("2026-11-14T15:00:00Z")
}
```

**Event-time** reports must assign it to minute `09:01`. **Ingestion latency** metrics use `15:00` to measure lag.

## 24. Reference Production Architecture

```text
Devices / Broker
       |
       v
  Ingestion API
       |
  Validate schema,
  normalize UTC / ID
       |
       v
  Regular inbox with
  UNIQUE(tenantId, eventId)
       |
  Durable queue / outbox
       |
       v
  Time series raw sink
       |
  Dedup / revision resolver
       |
  Canonical measurements
  / window aggregates
       |
  Dashboards / APIs
```

This is a **logical diagram**; not every step commits atomically together.

### 24.1. Ingress Validation

- `observedAt` is a valid Date within sensible bounds.
- Tenant/device/metric match expected formats and permissions.
- Event identities are not reused.
- `revision` follows source rules.
- Value and unit have valid types and physical ranges.
- `receivedAt` is stamped consistently.
- Check clock skew and future timestamps.
- Enforce a quarantine policy for conflicting data.

Time series collections do not support regular-collection schema validation rules; enforce validation at ingress or in a regular staging collection.

### 24.2. Durable Processing and Reconciliation

The registry can track states `pending`, `processing`, `delivered`, `failed` along with retry count, last error, and checkpoints. Handle:

- Worker crashing after claiming, before appending.
- Worker crashing after appending, before marking `delivered`.
- Ambiguous write outcomes on network timeouts.
- Duplicate `eventId` retries carrying different payloads.
- Corrections arriving before the original reading.
- Backfills arriving after windows finalized.
- TTL purging raw records before downstream reconciliation.

If you cannot prove exactly-once raw appends, implement canonical/read-time deduplication so **logical outputs** never double-count.

### 24.3. Monitoring

Track:

- Ingest throughput and p95/p99 write latency.
- P50/p95/p99 of `receivedAt - observedAt`.
- Out-of-order rate per device and source.
- Rate of late events exceeding business thresholds.
- Duplicate `eventId` rate and payload-conflict rate.
- Correction revisions per sample.
- Raw count to canonical count ratio.
- Count of revised window aggregates.
- Registry entries stuck in `pending` too long.
- Reconciliation lag and recovery backlog.
- Bucket/storage efficiency, cache, and I/O.
- TTL cleanup, backfill queue depth, and dead-letter rate.

Monitoring insert success rate alone is never enough to know if reports are accurate.

## 25. Common Pitfalls

| Pitfall | Consequence | Correct approach |
| --- | --- | --- |
| Using `receivedAt` as `timeField` for event-time data | Reports shift to wrong times | Keep `observedAt` and store `receivedAt` separately |
| Treating insert order as chronological order | Misordered displays | `.sort({observedAt: 1, ...})` |
| Treating out-of-order data as invalid | Loses valid late readings | Define allowed lateness |
| Creating a unique index directly on time series | Unsupported | Use regular registry/canonical collection |
| Assuming time series `_id` is auto-unique | Duplicates can be stored | Never use `_id` as a unique constraint |
| Upserting `value`/`timeField` to fix measurements | Restricted | Append revisions or use regular canonical store |
| Using `$merge` to upsert into time series | Target unsupported | `$merge` into a regular collection |
| Writing to time series inside transactions | Unsupported | Design recoverable dual-writes |
| Equating unique registry with exactly-once TS append | Crashes can leave gaps or duplicates | Reconciliation + canonical deduplication |
| Deduplicating by equal values | Distinct readings can share values | Use event/source IDs |
| Deduplicating solely by timestamp | Concurrent devices/channels collide | Use full logical identity |
| Dropping all `revision > 1` as retries | Loses corrections | Separate `eventId` and `sampleId` |
| Picking latest `receivedAt` regardless of revision | Reordering picks wrong version | Use source revision/priority |
| Mistaking `granularity` for allowed lateness | Windows close improperly | Track watermarks in the processor |
| Assuming watermarks block all older events | Events can arrive later than expected | Late policy + backfill |
| Assuming TTL starts from receipt time | Old events get purged early | Retention is evaluated on `timeField` |
| Not monitoring clock skew | Misclassifies late/future data | NTP + normalization |
| Averaging over raw retries | Skewed statistics | Deduplicate before aggregating |
| Running unthrottled backfills on live clusters | Spikes I/O and bucket churn | Throttle and checkpoint |
| Lacking window revisions when aggregates change | Downstream misses corrections | Use `provisional`/`final`/`revised` states |

## 26. Practice Exercises

### Exercise 1 — Three Timestamps

A device measures at 09:00, the gateway receives it at 09:03, and a worker processes it at 09:04:30. Identify event time, ingestion time, and processing time. Which timestamp should a 09:00 temperature report group by?

**Answer:** `observedAt=09:00`, `receivedAt=09:03`, `processedAt=09:04:30`; event-time reports use `observedAt`.

### Exercise 2 — Out-of-Order

`A-0902-r1` arrives before `A-0901-r1`. Should `A-0901-r1` be rejected because `observedAt` is smaller? List the criteria for deciding.

**Hint:** Not by default. Evaluate allowed lateness, source identity, clock skew, TTL, and backfill policy.

### Exercise 3 — Chronological Query

Write a `find` query for `sensor-A` sorted by ascending `observedAt`, ascending `revision`, and ascending `receivedAt`. Why should you avoid natural order?

### Exercise 4 — Raw vs. Unique Event IDs

After loading the fixture, how many raw documents and distinct event IDs exist?

**Answer:** 12 raw documents, 10 distinct event IDs.

### Exercise 5 — Detecting Retries

Group by `(tenantId, eventId)` and filter `copies > 1`. Which event IDs have duplicates and how many extra deliveries exist?

**Answer:** `A-0901-r1`, `B-0901-r1`; two extra deliveries.

### Exercise 6 — Newer Revision

`A-0901-r1` has `value=21`; `A-0901-r2` has `value=21.5`. What is the canonical value?

**Answer:** `21.5`, assuming the policy picks the highest revision.

### Exercise 7 — Counting Logical Samples

Using `canonicalPrefix`, count samples per device. What are the totals?

**Answer:** A=4, B=3, C=2; total=9.

### Exercise 8 — Skewed Averages

Compute the raw average and canonical average for sensor A.

**Answer:** 20.75 and 20.625.

### Exercise 9 — Window 09:01

Compute the `[09:01, 09:02)` average before A arrives, after `A-r1`, and after `A-r2`.

**Answer:** 25.5 → 24 → 24.166667.

### Exercise 10 — Lateness

Use `$dateDiff` and filter `delay > 120` s. How many raw documents match in the fixture?

**Answer:** 5; to count unique late events, deduplicate first.

### Exercise 11 — Fast Clock

If `observedAt` is 6 minutes ahead of `receivedAt`, what can you infer and what should you check?

### Exercise 12 — Unique Index on Time Series

Why can you not create a unique index on `("meta.deviceId", observedAt)`? If you must block retries, where should the unique index live?

**Answer:** Time series collections do not support unique indexes; use a regular inbox/registry collection.

### Exercise 13 — Crash Between Dual Writes

The registry claim succeeds but the time series append has not run; or the append succeeds but the registry state was not updated. How does recovery differ between the two failures?

### Exercise 14 — TTL

A time series collection has 24-hour retention on `observedAt`. An event arrives today with `observedAt` from three days ago. Why must you not promise 24-hour retention from receipt time?

### Exercise 15 — Last Week's Backfill

Design a backfill job with checkpoints, event identity, throttling, TTL checks, correction handling, and recomputation of finalized windows.

### Exercise 16 — Materializing Canonical State

Use `$merge` from `measurements` into regular collection `canonicalReadings`, counting 9 logical samples. Why can you not set `into` to a time-series collection?

### Exercise 17 — Sequence Reset

A device emits an incrementing `sequenceNo` that resets to 0 on reboot. Design an ID preventing collisions across reboots.

**Answer:** Combine `deviceId`, `bootId`/epoch, `sequenceNo`, and `tenant`/`metric` if needed.

### Exercise 18 — Window Finalization

A dashboard requires results in under 10 seconds, while 5% of events arrive after 5 minutes. Propose a `provisional`/`final`/`revised` policy and downstream notification strategy.

### Exercise 19 — Monitoring

List at least eight metrics covering ingestion, late events, duplicates, conflicts, corrections, bucket efficiency, TTL, and window revisions.

### Exercise 20 — Architecture Selection

Compare append-only + read-time dedup, unique inbox + time series, and regular canonical store + TS projection for an IoT system with retries and corrections. Specify atomicity boundaries and recovery procedures.

## 27. Summary

Three concepts must remain distinct:

- **Late arrival:** a measurement arriving after a chosen cutoff.
- **Out of order:** receipt order differs from event-time order.
- **Duplicate:** the same event resent; must be distinguished from a correction to the same logical sample.

To build a reliable time-series pipeline in MongoDB:

1. Keep `observedAt` as event time and store `receivedAt` separately.
2. Choose a stable `metaField` to support bucketing.
3. Sort by event time rather than trusting insertion order.
4. Use `eventId` to identify retries, `sampleId` for logical measurements, and `revision` for corrections.
5. Deduplicate before aggregating whenever business logic requires one value per logical sample.
6. Define watermarks and allowed lateness in the business processing pipeline.
7. Never treat unique indexes, measurement upserts, or transaction writes on time series like regular collections.
8. When strong uniqueness is required, use a regular collection and account for dual-write limits.
9. Check TTL against `timeField`; very old late arrivals may be purged.
10. Maintain audit trails, checkpoints, reconciliation, and revisions for aggregated results.
11. Monitor p95/p99 ingestion lag, duplicates, conflicts, and revised windows.
12. Choose an architecture balancing correctness requirements against operational cost.

**A successful raw insert does not guarantee accurate reports.** Correctness comes from source identity, event-time ordering, correction rules, and recoverable reconciliation.

### Official MongoDB References

- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — concepts and storage optimizations.
- [About Time Series Data / Bucketing](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/) — bucketing by meta/time and out-of-order timestamps.
- [Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/) — `timeField`, `metaField`, granularity.
- [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — unique indexes, updates, transactions, schema validation, `$merge` restrictions.
- [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — supported indexes.
- [Time Series Best Practices](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — choosing metadata and granularity.
- [Set Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/) — bucket parameters.
- [Automatic Removal for Time Series (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — expiration on `timeField`.
- [Aggregation $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — windowed grouping.
- [Aggregation $dateDiff](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateDiff/) — measuring delay.
- [Aggregation $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — canonicalization.
- [Aggregation $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materializing into regular collections.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — constraints on regular collections.
- [Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — distinguishing atomic writes.
