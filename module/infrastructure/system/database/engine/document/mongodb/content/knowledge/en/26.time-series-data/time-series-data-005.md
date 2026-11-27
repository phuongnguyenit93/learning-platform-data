# Time-Range Queries, Metadata Filtering, and Index Design in MongoDB Time Series

## 1. Problem: Continuous Ingestion, Slice-Based Queries

A monitoring system tracks 50,000 devices. Each device reports power, temperature, and status every minute. In a single day, the system can ingest over 70 million measurements. Users, however, typically ask very specific questions:

- How much power did device **meter-A** of tenant **t001** consume over the last 30 minutes?
- Give me the **20 latest measurements** for a sensor.
- Plot **hourly** power curves for all devices at a site.
- Within the selected time range, how many samples had **quality = "suspect"**?
- Why is a query over a two-hour window still slow even though a timestamp index exists?

This is a classic **time-series data** workload: high write volume, measurements carrying timestamps and source identifiers, and queries combining **time range + device metadata**.

MongoDB supports **time series collections** to optimize storing and accessing time series data. However, creating a collection with `timeseries` options **does not automatically make every query fast**. Performance still depends on metadata structure, time filter bounds, sorting, indexes, and how effectively irrelevant buckets are pruned.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **`timeField`**, **`metaField`**, and **measurement fields**.
2. Write time filters with **BSON Date** using half-open intervals **`[start, end)`**.
3. Combine **metadata** equality predicates with time ranges and sorts.
4. Retrieve latest samples, aggregate by device, and group by hour/day.
5. Choose **compound indexes** based on access patterns instead of indexing individual fields mechanically.
6. Understand the role of **buckets**, `granularity`, and special stages in `explain`.
7. Distinguish indexes supporting **routing/bucket pruning** from indexes filtering measurement fields.
8. Design retention/TTL, sharding, and tenant isolation in a time series system.
9. Handle timezones, late-arriving data, duplicate measurements, and missing intervals.
10. Run a `mongosh` lab that seeds deterministic data, runs queries, reads `explain`, and tunes indexes.

> This lesson sits in **Database Engine Document MongoDB → Time Series Data**, using real **time series collections**. Some features around indexing, updates, TTL, resampling, and sharding depend on MongoDB version. In production, consult documentation for your **exact server version** and inspect real query plans.

## 2. Time-Series Collection Model

### 2.1. What Comprises a Measurement?

Sample document:

~~~javascript
{
  _id: "ts-001",
  observedAt: ISODate("2026-01-15T00:30:00.000Z"),
  metadata: {
    tenantId: "t001",
    siteId: "hn",
    deviceId: "meter-A",
    metricType: "power"
  },
  watts: 12,
  temperatureC: 22.4,
  quality: "ok",
  seq: 2
}
~~~

Roles:

| Field group | Examples | Meaning |
| --- | --- | --- |
| **`timeField`** | `observedAt` | Timestamp when the measurement occurred; value is a **BSON Date** |
| **`metaField`** | `metadata` | Source/classification metadata, typically stable over time |
| **Measurement fields** | `watts`, `temperatureC`, `quality` | Values that vary per measurement |
| **Keys and auxiliary** | `_id`, `seq` | Identity/provenance and tie-breaking when needed |

In a time series collection, `metaField` can be an object with multiple properties. It does not have to be named **`metadata`**, though that name makes it clear throughout this lesson.

### 2.2. Creating the Collection

~~~javascript
db.createCollection("deviceMetrics", {
  timeseries: {
    timeField: "observedAt",
    metaField: "metadata",
    granularity: "seconds"
  }
});
~~~

Declarations:

- **`timeField: "observedAt"`**: field that must hold a valid Date value on every measurement write.
- **`metaField: "metadata"`**: field used for metadata grouping.
- **`granularity: "seconds"`**: time-granularity hint guiding how MongoDB manages buckets; it does not round document timestamps.

You continue operating on the logical collection **`deviceMetrics`** with `insert`, `find`, and `aggregate`. There is no need to manually build arrays holding thousands of measurements inside one document.

### 2.3. What Is a Bucket?

MongoDB can store multiple related measurements inside internal **buckets** for compression and read/write optimization:

~~~text
Logical documents seen by the user:

  meter-A @ 00:00 -> 10 W
  meter-A @ 00:15 -> 11 W
  meter-A @ 00:30 -> 12 W
  meter-B @ 00:00 -> 20 W

Physical storage (conceptual model):

  Bucket A: metadata for meter-A, a time span,
            multiple organized/compressed measurements

  Bucket B: metadata for meter-B, a time span,
            multiple organized/compressed measurements
~~~

**A bucket is not a business document directly managed by the application.** MongoDB decides bucket boundaries, compression, and physical layout based on configuration and incoming data.

When querying:

~~~javascript
db.deviceMetrics.find({
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T01:00:00Z")
  }
});
~~~

MongoDB can **prune non-matching buckets before decompressing/reading measurements**, using metadata and bucket time bounds. This underpins time-series collection performance.

### 2.4. Do Not Operate Directly on `system.buckets`

In observability tools or `explain`, you may see an internal namespace like **`system.buckets.deviceMetrics`** or bucket-related stages.

Never:

- Insert directly into `system.buckets`.
- Edit or delete buckets directly to "optimize compression".
- Emulate a manual bucket schema expecting time-series APIs to behave identically.
- Rely on internal bucket layout as a stable contract across versions.

Applications must access data exclusively through the **logical time series collection** and supported MongoDB APIs.

## 3. Choose Metadata Properly From the Start

### 3.1. Suitable Fields

Metadata typically describes the data source and repeats across many measurements:

~~~javascript
metadata: {
  tenantId: "t001",
  siteId: "hn",
  deviceId: "meter-A",
  metricType: "power"
}
~~~

These fields answer "which series does this measurement belong to?" When `deviceId`/`tenantId` are stable, MongoDB can pack readings from the same source together and leverage metadata filtering.

### 3.2. Fields Not to Put in Metadata Just for Indexing

Poor example:

~~~javascript
metadata: {
  tenantId: "t001",
  deviceId: "meter-A",
  watts: 12,
  temperatureC: 22.4,
  requestUuid: "new-id-for-every-sample"
}
~~~

Because `watts`, `temperatureC`, and `requestUuid` change constantly, consecutive samples from the same device carry different metadata values. This prevents grouping measurements into useful buckets and can inflate storage overhead.

**Metadata should be relatively stable; measurement fields should hold values that vary per sample.**

### 3.3. Metadata Is Not Authorization

A filter:

~~~javascript
{ "metadata.tenantId": "t001" }
~~~

narrows results, but it does not verify that the caller is authorized for tenant `t001`. The API must extract the authenticated tenant from the security context and inject it into the query—never trust a client-supplied `tenantId` blindly.

This is critical because a single time-series collection can hold measurements across many tenants.

### 3.4. What If a Device Moves Sites or Changes Configuration?

Suppose `meter-A` moves from site `hn` to site `dn` on Jan 20. Two options exist:

- **Point-in-time metadata**: older readings keep `siteId = "hn"`; new readings carry `siteId = "dn"`. Fits historical questions like "which site was the device at when measured?".
- **Separate device registry**: metadata keeps only immutable `deviceId`/`tenantId`, while current site lives in a `devices` collection. Fits when you want to avoid splitting metadata series, accepting joins/lookups for site resolution.

No single option fits all businesses. Define **historical reporting semantics**, update rules, and access patterns before choosing.

## 4. `mongosh` Lab: 24 Deterministic Measurements

### 4.1. Dataset

We use three devices, each with eight samples spaced 15 minutes apart on January 15, 2026 (UTC).

| Tenant | Site | Device | Timestamps (UTC) | `watts` |
| --- | --- | --- | --- | --- |
| `t001` | `hn` | `meter-A` | 00:00 → 01:45, every 15 min | 10 → 17 |
| `t001` | `hn` | `meter-B` | 00:00 → 01:45, every 15 min | 20 → 27 |
| `t002` | `dn` | `meter-C` | 00:00 → 01:45, every 15 min | 30 → 37 |

Specifically, each device has:

~~~text
00:00, 00:15, 00:30, 00:45,
01:00, 01:15, 01:30, 01:45 UTC
~~~

Total: **3 × 8 = 24 measurements**.

### 4.2. Creating and Seeding the Collection

Run in `mongosh`. The script intentionally **does not drop the collection** or touch unrelated data; if the 24 lab readings already exist, it avoids inserting duplicates.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_ts_query_lab_285");
  const collName = "lab_metrics";
  const tag = "ts-index-lab-v1";

  const collectionInfo = lab.getCollectionInfos({
    name: collName
  });

  if (collectionInfo.length === 0) {
    lab.createCollection(collName, {
      timeseries: {
        timeField: "observedAt",
        metaField: "metadata",
        granularity: "seconds"
      }
    });
  } else {
    const options = collectionInfo[0].options || {};
    const ts = options.timeseries;
    if (
      !ts ||
      ts.timeField !== "observedAt" ||
      ts.metaField !== "metadata"
    ) {
      throw new Error(
        "lab_metrics already exists without valid time series configuration."
      );
    }
  }

  const metrics = lab.getCollection(collName);
  const sources = [
    {
      tenantId: "t001", siteId: "hn",
      deviceId: "meter-A", wattsStart: 10
    },
    {
      tenantId: "t001", siteId: "hn",
      deviceId: "meter-B", wattsStart: 20
    },
    {
      tenantId: "t002", siteId: "dn",
      deviceId: "meter-C", wattsStart: 30
    }
  ];

  const rows = [];
  for (const source of sources) {
    for (let i = 0; i < 8; i++) {
      rows.push({
        _id: "ts285-" + source.deviceId + "-" + i,
        metadata: {
          lab: tag,
          tenantId: source.tenantId,
          siteId: source.siteId,
          deviceId: source.deviceId,
          metricType: "power"
        },
        observedAt: new Date(
          Date.UTC(2026, 0, 15, 0, i * 15, 0)
        ),
        watts: source.wattsStart + i,
        temperatureC: 20 + i / 2,
        quality: (
          source.deviceId === "meter-B" && i === 3
        ) ? "suspect" : "ok",
        seq: i
      });
    }
  }

  const existing = metrics.countDocuments({
    "metadata.lab": tag
  });

  if (existing === 0) {
    metrics.insertMany(rows);
  } else if (existing !== rows.length) {
    throw new Error(
      "Lab dataset currently has " + existing +
      "/24 samples. Skipping seed to avoid duplicates."
    );
  }

  printjson({
    collection: collName,
    existingBeforeSeed: existing,
    currentCount: metrics.countDocuments({
      "metadata.lab": tag
    }),
    collectionType: lab.getCollectionInfos({
      name: collName
    })[0].type
  });
})();
~~~

**Expected first-run output:** `currentCount = 24`. If re-run while data is intact, `existingBeforeSeed = 24` and `currentCount = 24`.

The **`count === 24`** guard only prevents duplicate seeding in the lab—it is not a tamper-detection mechanism. If you manually alter or delete part of the dataset, use a fresh lab database or **intentionally** reset the dedicated collection rather than appending potentially duplicate readings.

### 4.3. Verifying the Data

~~~javascript
const metrics = db.getSiblingDB("mongo_ts_query_lab_285")
  .getCollection("lab_metrics");

printjson(
  metrics.find(
    { "metadata.lab": "ts-index-lab-v1" },
    {
      _id: 1,
      observedAt: 1,
      metadata: 1,
      watts: 1
    }
  )
  .sort({ "metadata.deviceId": 1, observedAt: 1 })
  .limit(5)
  .toArray()
);
~~~

Under that sort order, the first five documents belong to **`meter-A`**, spanning `00:00` to `01:00` UTC, with `watts` from 10 to 14.

### 4.4. Conventions for Subsequent Queries

In the following sections, unless redeclared:

~~~javascript
const lab = db.getSiblingDB("mongo_ts_query_lab_285");
const metrics = lab.getCollection("lab_metrics");
const tag = "ts-index-lab-v1";
~~~

Run those three lines in your `mongosh` session. If you open a new terminal, redeclare these variables before running examples.

## 5. Time Queries with Proper Data Types

### 5.1. Use BSON Date, Never Strings for Date Filters

Correct:

~~~javascript
metrics.find({
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00.000Z"),
    $lt: ISODate("2026-01-15T01:30:00.000Z")
  }
});
~~~

Semantically wrong when `observedAt` is stored as BSON Date:

~~~javascript
metrics.find({
  observedAt: {
    $gte: "2026-01-15T00:30:00.000Z",
    $lt: "2026-01-15T01:30:00.000Z"
  }
});
~~~

The values in the second query are BSON Strings, not Dates. MongoDB compares values under BSON type bracketing rules, so a String filter cannot serve as a proper time filter against BSON Dates.

### 5.2. Half-Open Interval `[start, end)`

Recommended pattern:

~~~javascript
const start = ISODate("2026-01-15T00:30:00.000Z");
const end = ISODate("2026-01-15T01:30:00.000Z");

metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: start,
    $lt: end
  }
})
.sort({ observedAt: 1 })
.toArray();
~~~

**Expected result:** four samples:

| `observedAt` (UTC) | `watts` |
| --- | ---: |
| 00:30 | 12 |
| 00:45 | 13 |
| 01:00 | 14 |
| 01:15 | 15 |

The **`01:30`** sample is excluded because the upper bound uses **`$lt: end`**.

### 5.3. Why `[start, end)` Is Better Than Inclusive Endpoints

Suppose two shifts are processed:

~~~text
Shift 1: [00:00, 01:00)
Shift 2: [01:00, 02:00)
~~~

The **`01:00`** sample belongs strictly to Shift 2. If both shifts used **`$lte`** at the end, the `01:00` sample would be counted twice.

Half-open intervals compose cleanly across joins, time pagination, and hourly/daily bucket rollups. They do not forbid `$lte` when a business contract explicitly requires an inclusive endpoint, provided the rule is explicit.

### 5.4. Late-Arriving Data

A measurement with **`observedAt = 00:15`** transmitted at **`02:30`** still belongs to the `00:00–01:00` window when querying by `observedAt`. If the system also needs to analyze receipt timing, store it separately:

~~~javascript
{
  observedAt: ISODate("2026-01-15T00:15:00Z"),
  ingestedAt: ISODate("2026-01-15T02:30:00Z")
}
~~~

These carry distinct meanings:

- **`observedAt`**: when the event/measurement occurred.
- **`ingestedAt`**: when the system received the data.

To alert on "data arriving more than 30 minutes late", compare both timestamps. To compute power for `00:00–01:00`, normally use **`observedAt`**. Never blindly substitute `ingestedAt` as `timeField`.

## 6. Combining Metadata and Time Filters

### 6.1. Querying a Single Device

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  { _id: 0, observedAt: 1, watts: 1, quality: 1 }
)
.sort({ observedAt: 1 })
.toArray();
~~~

**Expected result:** eight samples for `meter-A`, with `watts` from 10 to 17.

Metadata narrows the **series**, while time narrows the **slice within that series**.

### 6.2. Querying Multiple Devices at One Site

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.siteId": "hn",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  {
    _id: 0,
    "metadata.deviceId": 1,
    observedAt: 1,
    watts: 1
  }
)
.sort({ "metadata.deviceId": 1, observedAt: 1 })
.toArray();
~~~

**Expected result:** **16 samples** from `meter-A` and `meter-B`. `meter-C` is excluded because it belongs to a different tenant/site.

### 6.3. Using `$in` for a Group of Devices

~~~javascript
metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": { $in: ["meter-A", "meter-B"] },
  observedAt: {
    $gte: ISODate("2026-01-15T01:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
}).toArray();
~~~

Result is **8 samples**: four timestamps from 01:00 to 01:45 for each device. With an overly long device list, `$in` increases routing and index-scan overhead; measure before expanding lists unboundedly.

### 6.4. System-Wide Time-Only Queries

~~~javascript
metrics.find({
  "metadata.lab": tag,
  observedAt: {
    $gte: ISODate("2026-01-15T01:00:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
}).toArray();
~~~

**Expected result:** **6 samples** (three devices × two timestamps, 01:00 and 01:15).

In a tiny lab, this runs effortlessly. With 50,000 devices, filtering solely by time without narrowing metadata forces the server to inspect many series and buckets. A standalone **time index** can help certain global workloads, yet does not replace evaluating cardinality and actual bucket scan volume.

## 7. Retrieving the Latest N Samples

### 7.1. Latest Samples for One Device

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A"
  },
  {
    _id: 0,
    observedAt: 1,
    watts: 1
  }
)
.sort({ observedAt: -1 })
.limit(3)
.toArray();
~~~

**Expected result:**

| Rank | `observedAt` UTC | `watts` |
| ---: | --- | ---: |
| 1 | 01:45 | 17 |
| 2 | 01:30 | 16 |
| 3 | 01:15 | 15 |

If this query runs constantly in your API, a compound index with **metadata equality prefix + descending `observedAt`** is a prime candidate.

### 7.2. When Multiple Measurements Share a Timestamp

A device may emit two records with the same `observedAt`. Sorting solely by `observedAt` leaves the ordering between tied records **underspecified**.

If the business requires deterministic order, store a tie-breaker field such as **`seq`**, **`eventId`**, or another meaningful discriminator:

~~~javascript
metrics.find({
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A"
})
.sort({ observedAt: -1, seq: -1 })
.limit(20);
~~~

**Note:** sorting on two fields may require adjusting indexes or sorting post-read; do not assume an `observedAt`-only index satisfies a `seq` tie-breaker without extra work.

### 7.3. Latest Sample Per Device

This is a different question from "the three latest samples site-wide". One straightforward pipeline:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.siteId": "hn"
    }
  },
  {
    $sort: {
      "metadata.deviceId": 1,
      observedAt: -1,
      seq: -1
    }
  },
  {
    $group: {
      _id: "$metadata.deviceId",
      latestAt: { $first: "$observedAt" },
      latestWatts: { $first: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**Expected result:** `meter-A` `latestWatts = 17`, `meter-B` `latestWatts = 27`, both at 01:45 UTC.

Do not confuse:

~~~javascript
{ $sort: { observedAt: -1 } },
{ $limit: 2 }
~~~

with **"2 latest samples per device"**. That returns 2 samples **total** after sorting, not 2 samples per group.

### 7.4. Large Device Fleets

A sort→group pipeline becomes expensive when finding the latest point across millions of series. Options to evaluate:

- Tune indexes on metadata and time.
- Scope by site/tenant and time window where business rules allow.
- Use accumulators like **`$top`/`$topN`** on supported versions where appropriate.
- Maintain a dedicated **latest-reading collection** updated safely when ultra-low-latency API lookups are required.

When updating a latest-reading cache under late arrivals, enforce **conditional updates so only newer `observedAt` overwrites**; the most recently arrived point does not always hold the largest timestamp.

## 8. Aggregating Over Time Ranges

### 8.1. Counting and Averaging Over a Segment

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: null,
      samples: { $sum: 1 },
      minWatts: { $min: "$watts" },
      maxWatts: { $max: "$watts" },
      avgWatts: { $avg: "$watts" },
      sumOfWattsSamples: { $sum: "$watts" }
    }
  },
  { $project: { _id: 0 } }
]).toArray();
~~~

**Expected result:** `samples = 8`, `minWatts = 10`, `maxWatts = 17`, `avgWatts = 13.5`, `sumOfWattsSamples = 108`.

**Unit warning:** `sumOfWattsSamples = 108` is the **sum of power samples**, not automatically 108 Wh or kWh of energy. If each sample represents average power over a non-overlapping 15-minute interval, an energy estimate is:

\[
E_{\mathrm{Wh}} \approx \sum_{i=1}^{8} P_i\;(\mathrm{W}) \times 0.25\;(\mathrm{h})
\]

For `meter-A`, that yields **27 Wh** under the assumption that each sample covers a full 15-minute slot. If readings are instantaneous power samples, use an appropriate integration or interpolation method—never blindly multiply every sample by 15 minutes when sampling is irregular or points are missing.

### 8.2. Aggregating by Device

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$metadata.deviceId",
      sampleCount: { $sum: 1 },
      avgWatts: { $avg: "$watts" },
      maxWatts: { $max: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Result:

| Device | `sampleCount` | `avgWatts` | `maxWatts` |
| --- | ---: | ---: | ---: |
| `meter-A` | 8 | 13.5 | 17 |
| `meter-B` | 8 | 23.5 | 27 |

### 8.3. Grouping by Hour with `$dateTrunc`

From MongoDB 5.0 onward, **`$dateTrunc`** cleanly computes the start of each time window:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$observedAt",
          unit: "hour",
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" },
      maxWatts: { $max: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**Expected result:**

| Hour start UTC | `samples` | `avgWatts` | `maxWatts` |
| --- | ---: | ---: | ---: |
| 00:00 | 4 | 11.5 | 13 |
| 01:00 | 4 | 15.5 | 17 |

This grouping runs over filtered measurements; **it does not mean MongoDB automatically stores each hour as a business document**.

### 8.4. Grouping by Device and Hour

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.siteId": "hn",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$metadata.deviceId",
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" }
    }
  },
  {
    $sort: {
      "_id.deviceId": 1,
      "_id.hour": 1
    }
  }
]).toArray();
~~~

Returns **4 groups**:

| Device | Hour UTC | `samples` | `avgWatts` |
| --- | --- | ---: | ---: |
| `meter-A` | 00:00 | 4 | 11.5 |
| `meter-A` | 01:00 | 4 | 15.5 |
| `meter-B` | 00:00 | 4 | 21.5 |
| `meter-B` | 01:00 | 4 | 25.5 |

### 8.5. Filtering Only Quality-Verified Measurements

If `quality = "suspect"` must be excluded from reports:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-B",
      quality: "ok",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: null,
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" }
    }
  }
]).toArray();
~~~

In the lab, `meter-B` has one `quality = "suspect"` sample at **00:45** with `watts = 23`. Consequently, the output covers **7 samples**, total `watts = 188 - 23 = 165`, and average roughly **23.5714**.

**A `quality` filter is a measurement predicate**, not a metadata predicate. It may be evaluated per measurement after bucket pruning unless the server/index supports pushing additional filters down. Never assume all predicates offer equal selectivity.

## 9. Timezones, Local Calendar Days, and DST

### 9.1. Store Timestamps Consistently

BSON Date is an absolute instant in time with millisecond resolution. Clients can convert to user timezones for display.

Recommendations:

- Record timestamps from sources with properly managed clocks.
- Use UTC when expressing or reconciling across systems.
- Convert local dates/times to UTC **before building query filters**.
- Specify reporting timezones using IANA zone names when DST applies, such as **`Asia/Ho_Chi_Minh`** or **`America/New_York`**.

Never store local wall-clock time without a timezone as a String and treat it as a complete timestamp.

### 9.2. A Day in Vietnam Does Not Start at 00:00 UTC

For example, **January 15, 2026** in Vietnam (UTC+07:00):

~~~text
Local start:
  2026-01-15 00:00:00 +07:00
=> UTC:
  2026-01-14 17:00:00Z

Local half-open end:
  2026-01-16 00:00:00 +07:00
=> UTC:
  2026-01-15 17:00:00Z
~~~

Filter:

~~~javascript
metrics.find({
  "metadata.tenantId": "t001",
  observedAt: {
    $gte: ISODate("2026-01-14T17:00:00Z"),
    $lt: ISODate("2026-01-15T17:00:00Z")
  }
});
~~~

All lab samples sit between 00:00 and 01:45 UTC on Jan 15, so all happen to fall inside Jan 15 in Vietnam time. In production, swapping dates in a UTC string while forgetting the `+07:00` offset causes off-by-hours errors at day boundaries.

### 9.3. `$dateTrunc` with Timezone

~~~javascript
{
  $dateTrunc: {
    date: "$observedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

This groups by **local calendar day**, rather than naively subtracting seven hours from every timestamp. Timezones observing DST do not always have 24-hour days.

### 9.4. Never Measure Latency by Subtracting Arbitrary `clusterTime`

When ingesting from devices, use explicit **`observedAt`** and **`ingestedAt`** fields to measure data lag. Oplog logical timestamps or replication fields do not represent when a device actually took a reading.

## 10. Designing Indexes Starting from Query Patterns

### 10.1. Illustrative Workload

Suppose a system serves these primary queries:

| ID | Question | Primary predicates | Sort / Output |
| --- | --- | --- | --- |
| Q1 | Single-sensor history | `tenantId` + `deviceId` + time range | Ascending `observedAt` |
| Q2 | Latest 20 samples | `tenantId` + `deviceId` | Descending `observedAt`, limit 20 |
| Q3 | Site chart | `tenantId` + `siteId` + time range | Group by device and hour |
| Q4 | Whole-tenant daily stats | `tenantId` + time range | Group and average |
| Q5 | Global hourly totals | time range | Group by hour |
| Q6 | Quality-flagged samples | `tenantId` + `quality` + time range | Count per device |
| Q7 | Latest per sensor at a site | `tenantId` + `siteId` | Sort/group by device |
| Q8 | Lookup by business sample ID | `tenantId` + `deviceId` + `observedAt` + `seq` | Return one record |

Do not create an index simply because a field appears in documents. Document **frequency, returned rows, time span, metadata cardinality, and SLA** for each Q.

### 10.2. Equality Filters First, Time Range Next

For Q1/Q2, candidate index:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

Rationale:

1. **`tenantId` equality** narrows the dataset.
2. **`deviceId` equality** pinpoints the series.
3. **`observedAt`** provides chronological ordering, especially for latest-N or time-range scans.

This applies the **equality-first, range/sort-next** intuition, yet time series collections use buckets and a dedicated optimizer—**never predict query plans solely from regular-collection B-tree theory**.

### 10.3. For Q3 by Site

Another candidate:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.siteId": 1,
  observedAt: -1
}
~~~

This supports filtering by tenant + site + time range. However, the query still needs to **group by `deviceId`**, so sorting/grouping and unpacking measurements still carry cost.

If Q7 ("latest per device") runs very frequently, consider placing **`deviceId`** before `observedAt` within the site group:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.siteId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

Do not create every variant upfront. Determine which queries merit optimization and whether gains outweigh index maintenance costs.

### 10.4. For Q5 Time-Only Queries

An index on:

~~~javascript
{ observedAt: -1 }
~~~

can assist cluster/collection-wide time queries depending on version and plan. If your product almost always scopes by tenant/device, a time-only index is far less useful than a `metadata + time` compound index.

### 10.5. For Q6 Measurement Filters

~~~javascript
{
  "metadata.tenantId": 1,
  quality: 1,
  observedAt: -1
}
~~~

is a candidate for which you must **verify measurement-field secondary index support** on your MongoDB time series version. Different releases impose different restrictions on secondary indexes, partial indexes, and index types.

If Q6 runs rarely or over narrow windows, filter by **`metadata + time range`** first to prune buckets, then filter `quality` across unpacked readings. You do not always need a dedicated index for every `quality`/`status` field.

## 11. Default Indexes and Custom Indexes on Time Series

### 11.1. What Default Index Does a Time Series Collection Have?

Modern MongoDB versions—notably **since MongoDB 6.3**—automatically create a **default compound index on `metaField` and `timeField`** for newly created time series collections (or an appropriate time index when `metaField` is omitted).

However:

- Historical collections created on older versions do not necessarily gain the same index automatically after upgrade.
- A default index is not necessarily optimal for every **`metadata` subfield** query.
- An index on the whole **`metadata`** object differs from a compound index on **`metadata.tenantId`** and **`metadata.deviceId`**.
- Indexes appear on the logical time series collection while the planner operates over internal **bucket-level** structures.

**Verify in practice with `getIndexes()`** instead of guessing from collection names.

~~~javascript
printjson(metrics.getIndexes());
~~~

### 11.2. Creating an Index for Q1/Q2

In the lab, if your server version supports this index shape:

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.deviceId": 1,
    observedAt: -1
  },
  { name: "ix_ts_tenant_device_time_desc" }
);
~~~

If `createIndex` reports an unsupported index on your version, **never edit `system.buckets` directly**. Check the **time series secondary indexes** docs for your exact version, then adjust your design or plan an upgrade properly.

### 11.3. Creating an Index for Q3

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.siteId": 1,
    observedAt: -1
  },
  { name: "ix_ts_tenant_site_time_desc" }
);
~~~

This illustrates a compact index set serving two main access patterns: individual devices and site-wide device groups.

### 11.4. Listing Existing Indexes

~~~javascript
printjson(
  metrics.getIndexes().map(i => ({
    name: i.name,
    key: i.key
  }))
);
~~~

If an index with the same key pattern already exists, do not recreate a duplicate under a different name. If an index goes unused by the planner, inspect query shapes before declaring "the index is broken".

### 11.5. Ascending vs. Descending Index

For queries filtering:

~~~javascript
{
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A"
}
~~~

and sorting **`observedAt: -1`**, a descending time suffix is a natural candidate. For some query shapes, MongoDB can scan an index in reverse to satisfy the opposite sort direction. For compound indexes with complex metadata/range predicates, inspect the actual execution plan rather than just counting `+1`/`-1` signs.

**Do not create both ascending and descending indexes solely because the UI has "oldest first / newest first" buttons** when one index can be walked in reverse efficiently. Verify `explain` and overall sort behavior.

## 12. Understanding Compound Indexes and Prefixes

### 12.1. Prefixes Matter

Index:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

orders keys as:

~~~text
tenantId -> deviceId -> observedAt
~~~

It is a strong candidate when queries apply equality on `tenantId` and `deviceId`, then filter/sort by `observedAt`.

If a query provides only `tenantId` and an `observedAt` range **without `deviceId`**, keys for many devices interleave. The planner cannot scan the time suffix as one contiguous range. If Q4 is high-priority, a separate **`tenantId + observedAt`** index may be worthwhile.

### 12.2. Comparing Three Indexes Across Queries

| Index | Q1 single device | Q3 single site | Q4 entire tenant |
| --- | --- | --- | --- |
| `tenantId, deviceId, time` | Strong candidate | Missing `siteId` in prefix | `time` suffix after `deviceId` is less favorable |
| `tenantId, siteId, time` | Suboptimal for `deviceId` if `site` is omitted | Strong candidate | `time` after `siteId` is less favorable |
| `tenantId, time` | Usable, but scans many tenant devices | Usable, requires post-filtering site | Better suited to Q4 |

This is a **design analysis**, not a guarantee of execution plans. The time series planner weighs bucket metadata, statistics, and costs independently.

### 12.3. Do Not Assume Simple Regular-Collection Overlap Rules

In regular collections, a compound index covers prefixes of shorter indexes; in time series collections:

- Indexes map onto and execute against bucket structures.
- Subfields of `metaField` vs. the entire `metaField` object can have different semantics.
- Certain index types have version-specific constraints.
- Query shapes affect optimizer predicate pushdown.

Therefore, dropping an existing index requires **`getIndexes`, `$indexStats` (if supported), `explain`, real workload traces, and a rollback plan**—never drop by intuition because "the names look similar".

### 12.4. Cost of Multiple Indexes

Each additional index:

- Consumes disk and memory.
- Adds I/O and maintenance overhead when writing measurements/buckets.
- Takes build time and cluster resources.
- Complicates query planning across many candidates.
- Adds operational cost during upgrades, retention, and rapid growth.

For continuous time series ingestion, **over-indexing** directly degrades write throughput. Start with the primary SLA/traffic queries and measure before adding more.

## 13. Reading `explain` on Time Series Collections

### 13.1. `explain` for a Single-Device Query

~~~javascript
const plan = metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
})
.sort({ observedAt: -1 })
.explain("executionStats");

printjson(plan);
~~~

Inspect these metrics:

| Metric | Question to answer |
| --- | --- |
| **`winningPlan` / `stages`** | Which stages execute the query? |
| **`IXSCAN` / `COLLSCAN`** | Are buckets accessed via index or full scan? |
| **`$_internalUnpackBucket` or similar** | Is there a stage unpacking buckets into measurements? |
| **`totalKeysExamined`** | How many index keys were examined? |
| **`totalDocsExamined`** | How many documents/buckets were examined at that plan stage? |
| **`nReturned`** | How many final measurements were returned? |
| **`SORT`** | Was an in-memory/blocking sort needed outside the index? |
| **`executionTimeMillis`** | Execution latency observed during `explain` |

**Stage names are not guaranteed identical** across MongoDB versions, query engines, or filter types. Mental models of bucket pruning are helpful, but verify against real `explain` output.

### 13.2. Why Reading 10 Buckets Differs from Reading 10 Measurements

One bucket can hold many measurements. When `explain` reports:

~~~text
totalDocsExamined = 10
~~~

in the internal bucket scan stage, **never conclude** only 10 measurements were read or evaluated. Bucket-level metrics count bucket documents, whereas **`nReturned`** after unpacking and filtering reflects returned logical measurements.

To assess efficiency holistically, inspect:

- How many buckets were scanned and unpacked?
- How many measurements actually matched?
- How many bytes were read and decompressed?
- Was there a large sort/group after unpacking?
- Was an index aligned with metadata and time range used?

### 13.3. Bucket Pruning

With a filter:

~~~javascript
{
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
}
~~~

MongoDB uses bucket metadata and min/max timestamps to skip buckets guaranteed to contain no matching data.

Even so, a bucket whose `minTime`/`maxTime` overlaps the query range can still contain **many measurements outside the range**. Filtering individual measurements after unpacking remains necessary. Thus, bucket pruning is not equivalent to filtering every measurement strictly via metadata alone.

### 13.4. Comparing Two Query Shapes

~~~javascript
const filterByDevice = {
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
};

const filterGlobal = {
  "metadata.lab": tag,
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
};

printjson(
  metrics.find(filterByDevice).explain("executionStats")
);

printjson(
  metrics.find(filterGlobal).explain("executionStats")
);
~~~

With only 24 measurements in the lab, runtimes are tiny and optimizer statistics are not meaningful benchmarks. In production across millions of devices, narrow-metadata queries prune far more buckets. Benchmark with representative data.

### 13.5. Conditional Use of `hint`

When your MongoDB version and index support `hint` on time series queries, you can test a specific index:

~~~javascript
const result = metrics.find(filterByDevice)
  .hint("ix_ts_tenant_device_time_desc")
  .explain("executionStats");

printjson(result);
~~~

This requires **`ix_ts_tenant_device_time_desc`** to have been created in Section 11. If the index does not exist or your version restricts `hint`, the command errors out—an environment detail, not proof that the workload fails to use indexes.

**`hint` is a diagnostic tool**; never hardcode it into production queries based solely on one `explain` over 24 samples.

## 14. Granularity, Bucket Span, and Performance

### 14.1. `granularity` Does Not Alter Timestamps

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "metadata",
  granularity: "seconds"
}
~~~

**`granularity`** helps MongoDB select bucket grouping policies matching workload cadence. It **does not** turn:

~~~text
00:15:30 -> 00:00:00
~~~

in logical results. Measurement timestamps remain exactly as written.

### 14.2. Choosing Granularity by Data Cadence

General guide:

| Series type | Measurement cadence | Candidate granularity |
| --- | --- | --- |
| Telemetry every few seconds | High | `"seconds"` |
| Per-minute/hourly data | Moderate | `"minutes"` or tailored config |
| A few readings per day | Sparse | `"hours"` or tailored design |

These are **design guidelines**, not rigid formulas. Custom bucket span and rounding options have version-specific capabilities and limits. Benchmark on production-like data covering compression, bucket pruning, and ingestion.

### 14.3. Buckets Too Small or Too Wide

Overly fragmented buckets cause:

- Many bucket documents and metadata overhead.
- Extra index entries and read work.
- Poor compression when each bucket holds very few measurements.

Overly wide buckets cause:

- Reading/unpacking many measurements outside the query window.
- Poor bucket pruning on short time-range queries.
- Overhead for late-arriving data or TTL retention in certain scenarios.

Measure trade-offs against **common query windows**. If your API typically renders 5 minutes of data, bucketing tuned exclusively for 1-year reports may underperform.

### 14.4. Metadata Cardinality Affects Buckets

If every measurement introduces brand-new metadata, MongoDB cannot sustain long-lived buckets for stable series. With 1 million readings each carrying a unique `requestUuid` in metadata, metadata groups proliferate.

Choose low-churn metadata sufficient to **distinguish queried sources**. Never merge all devices into one identical metadata object just to save buckets, as that destroys series-level pruning.

### 14.5. Never Edit Physical Buckets to Tune Performance

To change `granularity` or bucket spans, use **supported MongoDB APIs and version rules**. Some changes are one-way (increase-only) or require creating a new collection and migrating. Never modify the `system.buckets` namespace directly.

## 15. How TTL and Retention Affect Queries

### 15.1. Retention Is a Business Requirement

Telemetry often follows a lifecycle:

~~~text
Raw measurements:   retain 30 days
Hourly aggregates:  retain 1 year
Daily aggregates:   retain 5 years
~~~

If users need data from six months ago while raw measurements expire after 30 days, queries return empty results regardless of indexing. **Indexes cannot recover data purged by retention.**

### 15.2. TTL on Time Series Collections

MongoDB supports TTL/retention on time series collections, configured at creation time:

~~~javascript
// DESIGN EXAMPLE FOR A NEW COLLECTION; DO NOT RUN ON THE 24-SAMPLE LAB.
db.createCollection("metricsRetained30Days", {
  timeseries: {
    timeField: "observedAt",
    metaField: "metadata",
    granularity: "minutes"
  },
  expireAfterSeconds: 30 * 24 * 60 * 60
});
~~~

**`expireAfterSeconds`** expresses the target maximum age of data under time-series TTL semantics. Cleanup is **asynchronous** and bucket-aware, so expiration cannot be treated as a synchronous deletion down to the exact millisecond.

### 15.3. One Bucket Holds Multiple Timestamps

Because a bucket contains samples spanning multiple timestamps, MongoDB evaluates expiration under bucket semantics. Consequently, data can persist for some time after an individual measurement passes the desired TTL age.

If a product requires data to disappear **at an exact millisecond**, time series TTL is not a hard real-time deletion protocol; design explicit query/purge policies and verify server semantics.

### 15.4. Partial TTL by Metadata

On supported versions, time series collections allow **partial TTL indexes** scoped by metadata predicates, useful when device tiers have distinct retention windows. However, syntax and support constraints depend on version and field types.

Do not arbitrarily create a TTL index on a measurement field expecting regular-collection TTL behavior. When different tenants need distinct retentions, weigh **separate collections, explicit retention policies, or version-supported partial TTL**.

### 15.5. Raw vs. Downsampled Data

A common architecture:

~~~text
lab_metrics_raw
   1 sample every 15 minutes
       |
       | aggregation job
       v
lab_metrics_hourly
   1 summary document/bucket per hour
       |
       | aggregation job
       v
lab_metrics_daily
~~~

For one-year charts, querying daily/hourly aggregates is far cheaper than scanning all raw measurements. Define:

- Do you need min/max or only average?
- How are missing and late data handled?
- What timezone defines daily windows?
- Should aggregates recompute when late samples arrive?
- Do energy calculations account for the true sampling interval?

Never store only `average` and later try to reconstruct exact totals without **`sampleCount`** or interval-duration metadata.

## 16. Missing Intervals and Resampling

### 16.1. `$group` Does Not Synthesize Empty Time Buckets

If `meter-A` reports at 00:00, 00:15, and 00:45 but **misses 00:30**, a 15-minute `$group` pipeline produces no row for 00:30.

No row is **different from `watts = 0`**.

In monitoring:

- **`watts = 0`:** device recorded a verified 0 W measurement.
- **missing:** no measurement exists; device may be offline or ingestion failed.
- **`null`:** missing/invalid value per schema.

Never impute missing points as zero unless business rules explicitly permit it.

### 16.2. `$densify` and `$fill`

Modern MongoDB versions provide **`$densify`** and **`$fill`** to generate and populate missing gaps inside aggregation pipelines; verify server version and time-series support before deploying.

Example illustrating resampling intent after filtering to a single device:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  { $sort: { observedAt: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-01-15T00:00:00Z"),
          ISODate("2026-01-15T02:00:00Z")
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      observedAt: 1,
      watts: 1
    }
  }
]).toArray();
~~~

The lab dataset already contains all eight points for `meter-A`, so this example demonstrates syntax rather than filling gaps. On irregular or gapped datasets, `$densify` generates extra documents **without `watts`**.

**`$densify` `bounds` has its own boundary semantics**; never assume it behaves identically to `[start, end)` across all versions. If your application expects eight slots without `02:00`, check the output and add a trailing half-open `$match` if needed.

### 16.3. Interpolation Can Misrepresent Reality

Charts can use:

- **Forward-fill**: carry the last known value forward.
- **Linear interpolation**: interpolate between neighboring points.
- **Null gap**: leave a visible break in the line.
- **Zero-fill**: only when business semantics explicitly allow it.

Temperature and power fields often require different gap policies. Never let `$fill` synthesize values that users mistake for real measurements.

## 17. Sharding Time Series and Metadata Queries

### 17.1. Time Series Shard Keys Have Dedicated Constraints

Time series collections support sharding on compatible MongoDB versions, yet **permitted shard key fields and key types vary across releases**.

Check current official documentation for **`metaField`**, `metaField` subfields, `timeField`, and hashed keys. Never copy a regular collection's shard key blindly onto a time series collection without verifying version support.

### 17.2. Which Shard Does a Query Target?

If the shard key uses **`metadata.tenantId`/`deviceId`** and queries filter on those fields, `mongos` can route narrowly to matching shards.

If an API sends only:

~~~javascript
{ observedAt: { $gte: start, $lt: end } }
~~~

against a metadata-based shard key, the query must **scatter-gather** across shards.

### 17.3. Hot Shard Problem

Picking a shard key **based solely on monotonically increasing time** funnels all fresh writes onto one hot range; moreover, using `timeField` in shard keys carries version-specific constraints/deprecations. A low-cardinality metadata field can likewise skew load.

Evaluate:

- Concurrently active series counts.
- Which devices/tenants generate the heaviest ingestion.
- Which metadata fields queries know upfront.
- Data distribution over time.
- Cost of tenant-wide or cluster-wide queries.

### 17.4. Replica Sets and Per-Shard Indexes

In a sharded cluster, each shard is typically a replica set. **Each shard stores its assigned slice of time series data and corresponding indexes**, while `mongos` routes and merges results.

Do not imagine a "cluster-wide time index" as one monolithic B-tree covering every document across all shards.

### 17.5. Broad Queries Still Cost Resources

A dashboard comparing every device across every tenant over an entire year scans and groups data across shards. When run frequently, use a **summary collection** or dedicated analytics store instead of hitting the raw time-series collection with massive global scans every few seconds.

## 18. Measurement Updates, Deletes, and Corrections

### 18.1. Time Series Data Is Typically Append-Heavy

Time series collections fit **appending timestamped measurements**. Update and delete capabilities have version-dependent limits; several MongoDB versions restrict updates/deletes to metadata predicates or impose rules on which fields can be modified.

**Never assume** time series collections support full regular-collection `updateOne`/`replaceOne`/`upsert` semantics across all MongoDB versions.

### 18.2. What If a Sensor Resends a Corrected Sample?

Common strategies:

- Append a correction event with **`originalSampleId`, `correctedValue`, `correctedAt`**.
- Use update operations supported by your time series version where contracts allow.
- Keep raw measurements immutable and apply corrections during aggregation.
- Store mutable data in a staging/normalized regular collection if edits are frequent.

Sample logical correction document:

~~~javascript
{
  originalSampleId: "ts285-meter-A-3",
  observedAt: ISODate("2026-01-15T00:45:00Z"),
  correctedAt: ISODate("2026-01-15T03:00:00Z"),
  oldWatts: 13,
  newWatts: 12.8,
  reason: "sensor-calibration"
}
~~~

This is a business schema example, not a MongoDB-mandated format.

### 18.3. Duplicate Measurements

If a sensor retries an insert on a network blip, duplicates keyed by **`(deviceId, observedAt, seq)`** can arrive. On time series collections, unique index limitations mean you **cannot enforce arbitrary unique constraints** like on regular collections.

Implement idempotency at the ingestion layer:

- Stable business `sampleId` generated by the device or ingest tier.
- A regular intake collection with a unique index when strict enforcement is needed.
- Deduplication inside the ingestion stream pipeline.
- Reconciliation jobs for stored duplicates.

Never assume **`_id` in a time series collection** behaves identically to a regular collection's unique `_id` index across all versions.

### 18.4. Late Arrivals and Buckets

Late-arriving measurements carry timestamps older than ingestion time, affecting bucket selection and compression/storage efficiency. When data arrives far out of order:

- Monitor late-arrival rates.
- Clarify whether retention tracks `observedAt` or `ingestedAt` per business rules.
- Recompute hourly/daily aggregates if needed.
- Never rely on receipt time to decide "this is the latest measurement".

## 19. Choosing Indexes from a Workload Matrix

### 19.1. Initial Recommendation Matrix

| Workload | Filter | Candidate index | Notes |
| --- | --- | --- | --- |
| Q1: device history | `tenant` + `device` + `time` | `tenant, device, observedAt` | Top priority |
| Q2: latest 20 | `tenant` + `device` | `tenant, device, observedAt desc` | Can share with Q1 |
| Q3: site chart | `tenant` + `site` + `time` | `tenant, site, observedAt` | Consider if Q3 is frequent |
| Q4: tenant hourly rollup | `tenant` + `time` | `tenant, observedAt` | If Q4 is large/frequent enough |
| Q5: global time report | `time` | `observedAt` | Still wide; consider rollups |
| Q6: quality errors | `tenant` + `quality` + `time` | version-dependent: `tenant + quality + time` | Only if selectivity/cost justifies |
| Q7: latest per device | `tenant` + `site`, sort by device/time | `tenant, site, device, observedAt` | Benchmark vs. materialized latest view |
| Q8: event ID lookup | `device` + `timestamp` + `seq` | key-value index / separate collection | Time series should not replace a KV store |

### 19.2. Minimal Index Set for the Lab

In the lab, create two indexes covering the primary workloads:

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.deviceId": 1,
    observedAt: -1
  },
  {
    name: "ix_ts_tenant_device_time_desc"
  }
);

metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.siteId": 1,
    observedAt: -1
  },
  {
    name: "ix_ts_tenant_site_time_desc"
  }
);
~~~

These examples apply **when supported by your server version**. If an index already exists under the same name, skip creation; if an existing index has different keys, inspect `getIndexes()` instead of dropping blindly.

### 19.3. When to Add a Third Index?

Never decide by gut feeling. Document:

~~~text
Q4 tenant+time represents:
  35% of total queries
  p95 latency 800 ms
  target SLA p95 150 ms

Current indexes:
  tenant+device+time
  tenant+site+time

Test candidate:
  tenant+time

Compare:
  executionStats, buckets/keys examined,
  latency, ingest throughput, and disk footprint.
~~~

If the new index accelerates Q4 but slows ingestion unacceptably, **pre-aggregate hourly** instead of keeping the extra index. Good performance engineering optimizes **total system cost**, not a single query.

## 20. Query Validation and Production Operations

### 20.1. Always Bound Query Time Ranges

An API handling thousands of requests/sec must never let clients query from `MinKey` to `MaxKey` or scan ten years of raw data.

Application-side example:

~~~javascript
function buildRange(start, end, maxDays = 31) {
  const startMs = start.getTime();
  const endMs = end.getTime();
  const maxMs = maxDays * 24 * 60 * 60 * 1000;

  if (
    !Number.isFinite(startMs) ||
    !Number.isFinite(endMs) ||
    endMs <= startMs ||
    endMs - startMs > maxMs
  ) {
    throw new Error("Invalid or overly wide time range");
  }

  return {
    $gte: start,
    $lt: end
  };
}
~~~

This is a generic JavaScript helper; given valid Date objects, it returns a MongoDB range predicate. It is not a standalone security control—tenant and device filters must still be authorized.

### 20.2. Projection and Result Limits

~~~javascript
metrics.find(
  {
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  {
    _id: 0,
    observedAt: 1,
    watts: 1
  }
)
.sort({ observedAt: -1 })
.limit(100)
.toArray();
~~~

Projection shrinks network payloads, yet does not automatically make queries **covered** when buckets must be unpacked or other internal fields read. Check `explain` before claiming zero-fetch execution.

### 20.3. Time-Based Pagination

Over long histories, **large `skip` offsets** are costly because skipped items must still be traversed. With timestamps and a deterministic tie-breaker, use **keyset pagination**:

~~~text
Page 1:
  filter tenant/device
  sort observedAt DESC, seq DESC
  limit 50

Page 2:
  add predicate:
    observedAt < lastObservedAt
    OR (observedAt == lastObservedAt AND seq < lastSeq)
~~~

This requires:

- A stable sort key matching the schema.
- An index/plan benchmarked for the `OR`/range predicate.
- Signed/validated pagination cursors so callers cannot tamper with tenant/scope.
- A policy for newly arriving or late-arriving data.

Do not promise that keyset pagination over a live time series guarantees an **immutable snapshot** across pages unless the application provides explicit snapshot semantics.

### 20.4. Reading Many Sensors

An API receiving 10,000 `deviceId`s might construct a huge `$in`, yet:

- BSON command sizes are bounded.
- Index range scans multiply.
- Merge/sort time grows.
- Single shards or sites can saturate.

Depending on SLA, cap devices per query, group by site, or serve dashboards from precomputed summary collections.

### 20.5. Relationship Between Indexes and Compression

Time series compression reduces data size, while each extra index still carries independent overhead. Never assume "compression saved disk space so adding 20 indexes is free".

Dashboards should monitor:

- Ingest measurements/second.
- Average document/bucket size and compression ratio (when exposed by tools).
- Bucket count and creation rate.
- Storage/index sizes and cache pressure.
- Query p50/p95/p99 by query shape.
- Buckets unpacked, keys/docs examined.
- Late-arrival rate and data quality metrics.
- TTL cleanup and retention progress.
- CPU/IOPS and replication lag.

### 20.6. Benchmark on Representative Data

With the 24-sample lab:

- Every query completes almost instantaneously.
- The optimizer may choose different plans than in production.
- Bucket counts, compression, and cardinality do not reflect 50,000 devices.

Use the lab to **learn semantics and syntax**; use a staging dataset matching production distributions to **evaluate performance**.

## 21. Common Errors and Fixes

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Date query returns nothing | Filtering with String instead of BSON Date | Use `ISODate`/`new Date`; check types |
| Wrong daily report totals | Using UTC day instead of business timezone | Convert boundaries to UTC for the timezone |
| `01:00` sample counted twice | Both windows used `$lte` end | Use half-open `[start, end)` |
| Query reads all tenants | Missing `metadata.tenantId` predicate | Bind tenant from auth context |
| Time index exists yet sensor query is slow | Missing metadata filter or wrong index shape | Test `metadata + time` compound index |
| `tenant/device/time` index slow for tenant-wide query | Missing `device` equality; `time` trails `device` | Test `tenant/time` or rollups |
| Wrong "latest" order on tied timestamps | Sort lacks tie-breaker | Add `seq`/`eventId` and align index |
| Two samples total instead of two per device | `$limit` placed before per-device `$group` | Group/`$topN` per device |
| Skewed average with bad samples | Did not filter `quality` or missing points | Define valid samples and filter |
| `sum(watts)` mistaken for `Wh` | Confused instantaneous power sum with energy | Integrate over the sampling interval |
| `$dateTrunc` assigns wrong day | Wrong timezone | Pass proper IANA timezone |
| Poor bucket pruning | Missing metadata filter or overly wide range | Narrow scope and time bounds |
| Every sample creates new metadata | Dynamic values/UUIDs placed in `metaField` | Keep metadata stable |
| Reading `explain` thinking 10 buckets = 10 samples | Bucket-level metrics | Check unpacking and `nReturned` |
| Creating temperature index errors out | Version restricts secondary index on measurements | Check time series index support |
| Duplicate indexes slow ingestion | Over-indexing | Audit `getIndexes()`, workload, drop safely |
| TTL deletes "late" relative to deadline | Bucket-level asynchronous cleanup | Set realistic retention SLAs |
| Last year's report is empty | Raw measurements expired by TTL | Query hourly/daily rollups |
| Missing samples treated as 0 | Incorrect densify/fill semantics | Distinguish `null`/missing from zero |
| Late data breaks latest view | Used `ingestedAt` as `observedAt` or bad update guard | Compare business timestamps |
| Duplicate samples after retry | Ingestion lacks idempotency/dedup | Use business `sampleId` and pipeline dedup |
| Cluster-wide sharded time-series query slow | Missing shard-key targeting / scatter-gather | Review shard key and read models |
| Desired index/TTL fails to create | Version/syntax/collection limitation mismatch | Check docs for exact server version |
| 24-sample lab is fast so assuming prod is fast | Dataset far too small | Benchmark on realistic data |

## 22. Practice Exercises

### Exercise 1 — Identify `timeField` / `metaField`

From a measurement containing `observedAt`, `metadata.tenantId`, `metadata.deviceId`, `watts`, and `temperatureC`, classify each field by role. Explain why `watts` should not go into `metaField` when power fluctuates continuously.

### Exercise 2 — Create Collection

Write a `db.createCollection` command for **`sensorMetrics`** with `timeField: "measuredAt"`, `metaField: "source"`, and `granularity: "seconds"`. Explain what happens if the application sends `measuredAt` as a String instead of BSON Date.

### Exercise 3 — Half-Open Range

For `meter-A`, filter from `00:30` to before `01:30` UTC. Predict the four `watts` values and explain why the `01:30` sample is excluded.

### Exercise 4 — Metadata and Multi-Tenancy

Write a query fetching all measurements for `meter-A` in `t001`, from `00:00` to `02:00`. Why does filtering solely by `deviceId` without `tenantId` create data/security bugs?

### Exercise 5 — Site Chart

Filter `t001`/site `hn` over two hours. How many measurements match in total? Why is `meter-C` absent? Explain the role of a `tenantId/siteId/time` index.

### Exercise 6 — Latest N

Fetch the three latest samples for `meter-A`. Predict `observedAt`/`watts`. If two samples share the same `observedAt`, what must be added to guarantee deterministic order?

### Exercise 7 — Latest Per Device

Write an aggregation returning one latest sample for each device in `t001`/site `hn`. Explain why a pipeline-wide `$limit: 2` does not equal one sample per device.

### Exercise 8 — Average and Energy

For `meter-A` (`watts` 10..17), compute `avg`, `min`, `max`, and `sum`. Assuming each reading represents average power over a 15-minute slot, estimate energy in Wh. State when this estimation becomes invalid.

### Exercise 9 — Grouping by Hour

Use `$dateTrunc` with UTC timezone to aggregate `avgWatts` for `meter-B` by hour. Predict the averages for `00:00` and `01:00`.

### Exercise 10 — Quality Filter

In the lab, `meter-B` has a `suspect` sample at `00:45` with `watts = 23`. Recompute the average excluding `suspect`. Analyze index choices when `quality` is a measurement field.

### Exercise 11 — Vietnam Local Day

A report requires January 15, 2026 in `Asia/Ho_Chi_Minh`. Compute the UTC `start`/`end` for that half-open interval. Why is using `00:00Z–00:00Z` of the UTC calendar day wrong?

### Exercise 12 — Index Design

Among Q1/Q2/Q3/Q4, pick at most two initial indexes when 70% of traffic reads single devices and 20% renders site charts. Explain which remaining queries may be suboptimal.

### Exercise 13 — Prefix and Sort

An index has keys **`tenantId, deviceId, observedAt: -1`**. Can a query with only `tenantId` + time range use the entire time suffix as efficiently as one specifying `deviceId`? Describe how to verify with `explain`.

### Exercise 14 — Reading `executionStats`

Run `explain("executionStats")` for a single-device query and a time-only query. Record stages, keys/docs examined, and `nReturned`. Explain why bucket-level `totalDocsExamined` is not measurement count.

### Exercise 15 — Granularity

System A reports every second; System B reports twice a day. How should you choose `granularity`? Why is sharing one setting across both suboptimal?

### Exercise 16 — Late-Arriving Data

A measurement has `observedAt = 00:15` and `ingestedAt = 03:00`. Which hourly bucket does it belong to in `observedAt` reports? If the latest-state view already holds a `01:45` sample, why must the late arrival not overwrite latest state?

### Exercise 17 — Missing vs. Zero

A device lacks a `00:30` sample while reporting `00:15 = 5 W` and `00:45 = 7 W`. Compare zero-fill, forward-fill, and linear interpolation. When does treating filled values as real measurements cause wrong conclusions?

### Exercise 18 — Retention

A design keeps raw data for 30 days and hourly aggregates for 365 days. Which collection should a 90-day history query target? Why does TTL cleanup not always run at the exact millisecond of expiration?

### Exercise 19 — Sharding

An application filters by `tenantId`/`deviceId` on most requests. What principles guide shard key selection? Why can a global time-only query scatter-gather?

### Exercise 20 — Over-Indexing

A team created 12 indexes on a time-series collection receiving 10 million inserts/day, while only two appear in regular query plans. Propose a process to measure write overhead, disk usage, and query p95, and safely drop unused indexes.

### Exercise 21 — Duplicates

A sensor retries the same measurement three times. Without a regular-style unique index on the business key, what errors can arise in time series? Design an ingest pipeline with `sampleId` and deduplication.

### Exercise 22 — Tenant Security

An API accepts `deviceId` and a time range from the frontend. Describe how to bind `tenantId` from auth credentials, validate `start`/`end`, and enforce a maximum window. Why do indexes not replace authorization?

### Exercise 23 — Architecture Comparison

Compare two designs:

1. Every dashboard request scans one year of raw measurements.
2. Detail APIs read raw data over narrow ranges; dashboards query hourly/daily summaries.

Analyze latency, freshness, storage cost, late-arrival handling, and rebuild/reconciliation workflows.

### Exercise 24 — Realistic Benchmarking

Design a production-like benchmark with 50,000 devices and queries Q1–Q7. Select metrics for throughput, bucket count, p95/p99, keys/docs examined, compression, and ingestion latency. Explain why performance cannot be extrapolated from a 24-sample lab.

## 23. MongoDB References

- MongoDB Manual — [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/).
- MongoDB Manual — [Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/).
- MongoDB Manual — [Time Series Secondary Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-secondary-index/).
- MongoDB Manual — [Time Series Best Practices](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/).
- MongoDB Manual — [Time Series Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/).
- MongoDB Manual — [Time Series TTL](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/).
- MongoDB Manual — [Time Series Sharding](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/).
- MongoDB Manual — [$dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/).
- MongoDB Manual — [$densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/).
- MongoDB Manual — [$fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/).

**Conclusion:** Efficient time series queries usually start with **accurate source metadata + tightly bounded half-open time intervals**. Time-series collections store data in **buckets** to optimize compression and pruning, yet do not eliminate the need for thoughtful indexing. Design indexes around **query patterns**: equality on tenant/device/site followed by ranges or sorts on **`timeField`**; verify with **`getIndexes`** and **`explain`** to understand bucket reads without confusing bucket scans with measurement counts. For wide historical spans, favor **hourly/daily rollups** where appropriate; for real-time ingestion, handle **timezones, late arrivals, missing samples, retention, and idempotency** explicitly. Stable metadata and a compact index set measured on a representative workload beat a large collection of guesswork indexes.
