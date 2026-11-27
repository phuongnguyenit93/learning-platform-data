# Time-Window Aggregations and Generating Statistical Summaries in MongoDB

## 1. Problem: From Continuous Measurements to Actionable Data

A temperature monitoring system records readings from multiple sensors. Each record carries a timestamp, sensor ID, temperature, humidity, and electrical power:

~~~javascript
{
  ts: ISODate("2026-05-10T00:05:00Z"),
  meta: {
    sensorId: "S-01",
    site: "HCM"
  },
  temperatureC: 28,
  humidityPct: 70,
  powerW: 110
}
~~~

At launch, a dashboard may only display **the latest reading**. Over time, requirements grow more demanding:

- How many readings arrive every **15 minutes**?
- What are the **hourly average**, min, and max temperatures?
- During which hours did a sensor send **no data**?
- How did the average temperature over the **last 3 hours** change?
- How much does the current value differ from the **previous measurement**?
- How is daily total power or electricity consumption computed?
- Can we build a **`sensor_hourly_stats`** collection so dashboards read quickly instead of grouping millions of measurements every time?
- If late events arrive or historical numbers are revised, how should the summary table be updated?

MongoDB provides the **aggregation pipeline** with date and window operators to answer these questions directly inside the database.

An essential goal is distinguishing three operations often grouped together under *windowed aggregation* that behave quite differently:

1. **Tumbling / fixed time buckets:** group measurements into non-overlapping intervals such as hours or 15-minute slots, computing one result per bucket.
2. **Sliding / rolling windows:** at each chronologically ordered row, compute statistics over a neighboring count of rows or time span.
3. **Materialization / downsampling:** persist aggregated summaries into a summary collection for reuse and lower query cost.

### Lesson Objectives

After this lesson, you will be able to:

- Model time series data with **`timeField`** and **`metaField`**.
- Use **`$dateTrunc` + `$group`** to compute statistics by minute, hour, day, or week.
- Distinguish between **`documents` windows** and **`range`/time windows** in **`$setWindowFields`**.
- Compute rolling averages, rolling sums, cumulative totals, min/max, and deltas between consecutive readings.
- Handle hours with missing data using **`$densify`** and **`$fill`** without arbitrarily turning missing values into 0.
- Properly handle timezones, DST days, bad readings, late arrivals, and irregular sampling.
- Persist summary tables with **`$merge`** and design safe backfill/recompute schedules.
- Implement examples in `mongosh`, the MongoDB Java Sync Driver, and Spring Data MongoDB.
- Recognize server version constraints, indexing, memory/spill limits, processing cost, and statistical accuracy pitfalls.

## 2. Core Concepts

### 2.1. Event Time vs. Processing Time

IoT, log, and telemetry systems involve at least two timestamps:

| Field | Meaning | Example |
|---|---|---|
| **`ts` / `eventTime`** | When the event actually occurred or was measured. | Sensor measured at 08:05. |
| **`ingestedAt` / `processingTime`** | When the backend received and stored the record. | Due to network outage, the 08:05 reading arrived at 09:20. |

If the question is **"average temperature from 08:00 to 09:00?"**, group by **event time**, not when the record reached the server.

If the question is **"how long does a measurement take to reach the system?"**, use the difference between `ingestedAt` and `ts`.

Never substitute an HTTP request timestamp for measurement time without clarifying business semantics.

### 2.2. Fixed Buckets vs. Rolling Windows

A sequence of readings might look like:

~~~text
00:05 --28°C
00:35 --30°C
01:10 --29°C
02:00 --(no sample)
03:20 --31°C
03:50 --32°C
~~~

**Fixed hourly buckets**:

~~~text
[00:00,01:00) -> 28,30 -> average 29
[01:00,02:00) -> 29    -> average 29
[02:00,03:00) -> empty
[03:00,04:00) -> 31,32 -> average 31.5
~~~

A **rolling three-hour window** at 03:50 spans readings within `00:50–03:50`; that is not the same calculation as "the last three observed buckets".

### 2.3. Half-Open Intervals

To partition time without overlap, use:

~~~text
[start, end)
~~~

Meaning:

- **`start`** is inclusive.
- **`end`** is exclusive.

In MongoDB:

~~~javascript
{
  ts: {
    $gte: ISODate("2026-05-10T00:00:00Z"),
    $lt: ISODate("2026-05-10T01:00:00Z")
  }
}
~~~

This ensures a measurement at exactly **01:00** belongs solely to the bucket starting at 01:00 rather than being double-counted across consecutive hours.

### 2.4. Composable vs. Non-Composable Metrics

Common statistical metrics:

| Metric | Meaning | Can be rolled up from sub-summaries? |
|---|---|---|
| **`count`** | Valid sample or document count. | Sum the counts. |
| **`sum`** | Sum of values. | Sum the sums. |
| **`min` / `max`** | Minimum / maximum. | Min of mins, max of maxes. |
| **`average`** | Arithmetic mean. | Must retain **`sum` and `count`** to compute a weighted mean. |
| **`percentile` / `median`** | Quantile / median. | **Cannot** be computed by averaging sub-percentiles or sub-medians. |
| **`stddev`** | Standard deviation. | Requires intermediate moments/statistics or recomputing properly. |
| **`rate`** | Change over time. | Requires interval length, counter resets, and boundary samples. |

A classic bug is averaging hourly averages when sample counts vary per hour. In this lesson we retain **`sum` + `count`** to compute accurate daily statistics.

## 3. Creating Practice Data

Use a dedicated database on MongoDB **5.0+** to run the core window operators. Newer stages explicitly note their version requirements.

~~~javascript
use mongo_timeseries_stats_lab
~~~

Create the **time series collection**:

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

**`timeField`** must hold a BSON Date to organize measurements chronologically. **`metaField`** holds relatively stable source attributes—here `sensorId` and `site`.

MongoDB stores time series measurements in internal **buckets** for compression and query optimization. Those internal storage buckets are **not** the 15-minute or 1-hour aggregation buckets produced by pipelines.

### 3.1. Seed Data

~~~javascript
db.sensor_readings.insertMany([
  {
    ts: ISODate("2026-05-10T00:05:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 28,
    humidityPct: 70,
    powerW: 110
  },
  {
    ts: ISODate("2026-05-10T00:35:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 30,
    humidityPct: 68,
    powerW: 125
  },
  {
    ts: ISODate("2026-05-10T01:10:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 29,
    humidityPct: 69,
    powerW: 118
  },
  {
    ts: ISODate("2026-05-10T03:20:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 31,
    humidityPct: 67,
    powerW: 130
  },
  {
    ts: ISODate("2026-05-10T03:50:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 32,
    humidityPct: 66,
    powerW: 132
  },
  {
    ts: ISODate("2026-05-10T00:20:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 26,
    humidityPct: 74,
    powerW: 95
  },
  {
    ts: ISODate("2026-05-10T01:30:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 27,
    humidityPct: 73,
    powerW: 98
  },
  {
    ts: ISODate("2026-05-10T02:40:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 28,
    humidityPct: 72,
    powerW: 101
  }
]);
~~~

**Run the seed once on a fresh collection.** Subsequent commands can be tested independently; if you add or delete rows, expected outputs change. Never run collection-recreation examples in production.

### 3.2. Inspecting Raw Readings by Sensor and Time

~~~javascript
db.sensor_readings.find(
  {
    "meta.sensorId": "S-01",
    ts: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  },
  {
    _id: 0,
    ts: 1,
    "meta.sensorId": 1,
    temperatureC: 1
  }
).sort({ ts: 1 });
~~~

`S-01` has five readings in the sample dataset. There is no reading from **02:00 to before 03:00**; that is completely different from "sensor measured 0°C during hour 02".

### 3.3. Designing `metaField`

Choose `metaField` attributes that stay relatively stable—sensor ID, device type, fixed location. Avoid placing **timestamps, random `requestId`s, or per-measurement changing values** inside `metaField`, as that spawns tiny buckets and degrades compression.

When `metaField` is an object, query scalar subfields like **`meta.sensorId`** rather than comparing whole objects that depend on key ordering.

## 4. `$dateTrunc`: Creating Time Bucket Keys

**`$dateTrunc`** (MongoDB 5.0+) truncates a timestamp to the **start of a chosen interval**.

Example:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "hour",
    binSize: 1,
    timezone: "UTC"
  }
}
~~~

For `ts = 00:05` or `00:35` UTC, both return **`2026-05-10T00:00:00Z`**, which serves directly as a `$group` key.

### 4.1. Hourly Temperature Aggregation with `$group`

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      sumTempC: { $sum: "$temperatureC" },
      avgTempC: { $avg: "$temperatureC" },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      samples: 1,
      sumTempC: 1,
      avgTempC: 1,
      minTempC: 1,
      maxTempC: 1
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Results for `S-01` on the sample dataset:

| `hourStart` (UTC) | `samples` | `sumTempC` | `avgTempC` | `minTempC` | `maxTempC` |
|---|---:|---:|---:|---:|---:|
| 00:00 | 2 | 58 | 29 | 28 | 30 |
| 01:00 | 1 | 29 | 29 | 29 | 29 |
| 03:00 | 2 | 63 | 31.5 | 31 | 32 |

There is no **02:00** row because **`$group` does not synthesize buckets with zero source documents**.

### 4.2. Pipeline Breakdown

1. **`$match`** restricts sensor and time range to shrink input entering the pipeline.
2. **`$group`** uses `sensorId + hourStart` as a composite key.
3. Accumulators compute count/sum/avg/min/max per bucket.
4. **`$project`** reshapes the group key into a dashboard-friendly schema.
5. **`$sort`** enforces deterministic output order; `$group` output is unordered.

### 4.3. 15-Minute Aggregation

Adjust the bucket expression:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

Intervals align to `00:00–00:15`, `00:15–00:30`, `00:30–00:45`, `00:45–01:00` per `$dateTrunc` rules.

**`binSize`** must be an appropriate positive integer. Never manually round timestamp strings in application code to create 15-minute bins when MongoDB can compute them natively.

### 4.4. Daily, Weekly, and Monthly Aggregations

Daily bucket in business timezone:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Weekly bucket starting Monday:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Monthly bucket:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "month",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

The output is a **BSON Date representing the bucket start**, stored in UTC; `timezone` dictates how local calendar boundaries are found. Never confuse "returns 00:00 UTC" with "the local day started at 00:00 UTC".

## 5. Conditional Statistics, `null` Values, and Sample Counts

### 5.1. `$avg` Ignores Non-Numeric Values

When some measurements omit temperature or store `null`, **`$avg`** ignores non-numeric values. Hence in:

~~~javascript
{
  $group: {
    _id: "$meta.sensorId",
    totalDocuments: { $sum: 1 },
    avgTempC: { $avg: "$temperatureC" }
  }
}
~~~

**`totalDocuments`** may differ from the count of valid numeric readings averaged into `avgTempC`.

### 5.2. Counting Valid Measurements Separately

~~~javascript
db.sensor_readings.aggregate([
  {
    $group: {
      _id: "$meta.sensorId",
      totalDocuments: { $sum: 1 },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      avgTempC: { $avg: "$temperatureC" }
    }
  }
]);
~~~

When no numeric temperature exists, **`validTempSamples = 0`** and **`avgTempC`** is `null`. Never divide by zero.

### 5.3. Zero, `null`, and Missing Document Are Different

| State | Meaning |
|---|---|
| `temperatureC = 0` | An actual temperature measurement equal to 0°C. |
| `temperatureC = null` | Document exists, value is unknown or invalid per schema. |
| Missing `temperatureC` | Field was not transmitted in the document. |
| No document in hour | No measurement arrived for that bucket. |

Only replace `null` or missing with `0` when **the domain proves `0` is semantically valid**—for instance, `eventCount` of an empty bucket. For temperature, filling missing values with `0` corrupts charts and statistics.

### 5.4. Rounding for Display

~~~javascript
{
  $project: {
    avgTempC: {
      $round: ["$avgTempC", 2]
    }
  }
}
~~~

Keep unrounded values inside summary records used for further computation; round only at display time or per explicit business rules to avoid rounding drift.

## 6. Differences Between Tumbling, Hopping, and Sliding Windows

### 6.1. Tumbling Window

Each measurement belongs to **exactly one bucket** for a given partition scheme:

~~~text
00:00      01:00      02:00      03:00
  |----------|----------|----------|
   bucket 0   bucket 1   bucket 2
~~~

In MongoDB, this typically uses **`$dateTrunc` + `$group`**.

### 6.2. Hopping Window

Fixed window duration, with each new window advancing by a **hop smaller than the window size**:

~~~text
60-minute window, 15-minute hop:

00:00 ------ 01:00
  00:15 ------ 01:15
    00:30 ------ 01:30
      00:45 ------ 01:45
~~~

One measurement can belong to **multiple windows**.

MongoDB does not have a built-in `hopSize` option in `$group`; you can generate window timestamps and join/unwind appropriately, or use range window analytics depending on the goal. Materializing overlapping windows multiplies output row counts substantially.

### 6.3. Sliding Window

At each sorted measurement or bucket, compute across neighboring rows:

~~~text
S-01 observed hourly averages:
00:00 29
01:00 29
03:00 31.5

Rolling 2 observed rows:
00:00 -> [29]         -> 29
01:00 -> [29,29]      -> 29
03:00 -> [29,31.5]    -> 30.25
~~~

This covers **the last two observed rows**, not necessarily **two consecutive calendar hours** when `02:00` is missing. Know when to use a **`documents` window** vs. a **`range` window**.

## 7. `$setWindowFields`: Per-Window Statistics

**`$setWindowFields`** (MongoDB 5.0+) computes statistical fields across documents belonging to a **partition** and **window**.

Syntax skeleton:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      metricName: {
        $avg: "$avgTempC",
        window: {
          documents: [-2, 0]
        }
      }
    }
  }
}
~~~

- **`partitionBy`:** computes independently per sensor.
- **`sortBy`:** defines chronological order inside each partition.
- **`output`:** new computed fields attached to each row.
- **`documents`:** relative row-position range around the current row.
- **`range`:** range over `sortBy` values, supporting time units.

### 7.1. Rolling 3 Hourly Rows

Starting from `S-01`'s hourly summary table:

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgTempC: { $avg: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      sampleCount: 1,
      avgTempC: 1
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: {
        hourStart: 1
      },
      output: {
        avgLast3ObservedHours: {
          $avg: "$avgTempC",
          window: {
            documents: [-2, 0]
          }
        },
        samplesCumulative: {
          $sum: "$sampleCount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

For `S-01` at `03:00`, **`avgLast3ObservedHours`** averages the three rows **`00:00`, `01:00`, and `03:00`**: `(29 + 29 + 31.5) / 3 ≈ 29.8333`.

This is **not a rolling 3 consecutive calendar hours window**. Because `02:00` has no bucket, a `documents` window does not see that gap.

### 7.2. Cumulative Sum

~~~javascript
samplesCumulative: {
  $sum: "$sampleCount",
  window: {
    documents: ["unbounded", "current"]
  }
}
~~~

Accumulates from the start of the partition to the current row. For `S-01`:

~~~text
00:00 -> 2
01:00 -> 3
03:00 -> 5
~~~

Without **`partitionBy`**, a cumulative total sums across all sensors together, violating per-sensor reporting.

### 7.3. `documents` Window vs. Time-`range` Window

**`documents` window**:

~~~javascript
window: {
  documents: [-2, 0]
}
~~~

Evaluates at most three rows: the two preceding rows plus the current row.

**Time-`range` window**:

~~~javascript
window: {
  range: [-2, 0],
  unit: "hour"
}
~~~

Evaluates rows whose timestamps fall within **two hours prior up to the current row's timestamp**, inclusive at both ends per window semantics. When `range` uses **`unit`**, `sortBy` must be an appropriate date/time field.

Never assume `documents: [-2, 0]` equals `range: [-2, 0], unit: "hour"`. They match only on evenly spaced, gap-free datasets.

### 7.4. Rolling 60 Minutes on Raw Readings

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: {
        ts: 1
      },
      output: {
        avgPrevious60Minutes: {
          $avg: "$temperatureC",
          window: {
            range: [-60, 0],
            unit: "minute"
          }
        },
        maxPrevious60Minutes: {
          $max: "$temperatureC",
          window: {
            range: [-60, 0],
            unit: "minute"
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      ts: 1,
      sensorId: "$meta.sensorId",
      temperatureC: 1,
      avgPrevious60Minutes: 1,
      maxPrevious60Minutes: 1
    }
  },
  {
    $sort: {
      ts: 1
    }
  }
]);
~~~

At `01:10` for `S-01`, the window `[00:10, 01:10]` includes `00:35` (30°C) and `01:10` (29°C), excluding `00:05`. The average is **29.5°C**.

### 7.5. Why Append `$sort` at the End?

**`$setWindowFields` does not guarantee output document order**, even though `sortBy` governs window evaluation. If dashboards or APIs expect sorted output, append **`$sort`** at the end.

### 7.6. Window Boundaries and Initial Records

With `documents: [-2, 0]`, the first row has no two prior rows. MongoDB computes over **existing rows in the window** rather than synthesizing two zero rows.

If a product requires **emitting a 3-hour average only when 3 samples exist**, compute the window sample count alongside it and filter or flag the result:

~~~javascript
output: {
  rollingAvg: {
    $avg: "$temperatureC",
    window: { documents: [-2, 0] }
  },
  rollingSampleCount: {
    $count: {},
    window: { documents: [-2, 0] }
  }
}
~~~

After this stage, you can filter `rollingSampleCount >= 3` or expose `isCompleteWindow` to the UI. Never present the first row's single-point value as a "full three-sample average".

## 8. Comparing Consecutive Readings and Detecting Sudden Changes

Beyond averages and sums, systems often track **deltas between consecutive readings**.

### 8.1. `$shift` to Fetch the Previous Value

Inside **`$setWindowFields`**, **`$shift`** returns a field from a row at a relative offset. **`by: -1`** selects the preceding row:

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: { ts: 1 },
      output: {
        previousTemperatureC: {
          $shift: {
            output: "$temperatureC",
            by: -1,
            default: null
          }
        },
        previousTs: {
          $shift: {
            output: "$ts",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      deltaTempC: {
        $subtract: ["$temperatureC", "$previousTemperatureC"]
      },
      elapsedMs: {
        $subtract: ["$ts", "$previousTs"]
      }
    }
  },
  {
    $project: {
      _id: 0,
      ts: 1,
      temperatureC: 1,
      previousTs: 1,
      previousTemperatureC: 1,
      deltaTempC: 1,
      elapsedMs: 1
    }
  },
  { $sort: { ts: 1 } }
]);
~~~

For `S-01`:

~~~text
00:05 -> 28°C, previous=null
00:35 -> 30°C, delta=+2°C
01:10 -> 29°C, delta=-1°C
03:20 -> 31°C, delta=+2°C
03:50 -> 32°C, delta=+1°C
~~~

If multiple readings share **identical timestamps**, sorting by `ts` alone leaves their relative order ambiguous. Add a stable sequence/tie-breaker field when analyses depend on exact ordering.

### 8.2. Detecting Threshold Crossings

After computing `deltaTempC`, you can filter:

~~~javascript
{
  $match: {
    $expr: {
      $gte: [
        { $abs: "$deltaTempC" },
        2
      ]
    }
  }
}
~~~

However, readings 130 minutes apart vs. 5 minutes apart carry very different physical meanings. A 2°C delta alone does not measure rate of temperature rise.

### 8.3. Rate of Change

~~~text
rateCPerHour =
  (currentTemperatureC - previousTemperatureC)
  / ((currentTs - previousTs) / 3_600_000)
~~~

Inside the pipeline, guard `elapsedMs` to prevent division by zero:

~~~javascript
{
  $set: {
    changeRateCPerHour: {
      $cond: [
        { $gt: ["$elapsedMs", 0] },
        {
          $multiply: [
            "$deltaTempC",
            { $divide: [3600000, "$elapsedMs"] }
          ]
        },
        null
      ]
    }
  }
}
~~~

MongoDB also provides **`$derivative`** and **`$integral`** window operators where suitable, though you must understand window definitions, units, and boundary values. Never assume operator names automatically handle sensor resets or bad readings.

## 9. Moving Average and Exponential Moving Average

### 9.1. Simple Moving Average

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$meta.sensorId",
    sortBy: { ts: 1 },
    output: {
      sma3: {
        $avg: "$temperatureC",
        window: { documents: [-2, 0] }
      }
    }
  }
}
~~~

**SMA** (simple moving average) weights every row in the window equally. When timestamps are irregularly spaced, a row-count SMA is **not** a time-weighted average.

### 9.2. Exponential Moving Average

**`$expMovingAvg`** is a window operator that smooths series while weighting recent readings higher:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$meta.sensorId",
    sortBy: { ts: 1 },
    output: {
      ema3: {
        $expMovingAvg: {
          input: "$temperatureC",
          N: 3
        }
      }
    }
  }
}
~~~

This EMA steps by **reading sequence**, without accounting for whether gaps between readings are 1 minute or 2 hours. To compute over uniform time steps, first map data onto a regular time grid with an explicit missing-data policy.

### 9.3. Choosing the Right Statistic

| Use case | Recommended approach |
|---|---|
| Average of last three samples | Document-based SMA. |
| Smoothing emphasizing recent samples | EMA. |
| Average over a true 60-minute span | Time **`range` window**. |
| Average of three consecutive hourly buckets | Hourly buckets, fill gaps, then window. |
| Energy from irregular `powerW` readings | Time integration / proper measurement rules—never sum `powerW` directly. |

## 10. `$densify`: Inserting Missing Time Buckets

**`$group`** emits rows only for buckets containing measurements. For `S-01`:

~~~text
00:00 -> average 29
01:00 -> average 29
02:00 -> (no row)
03:00 -> average 31.5
~~~

If a dashboard requires a uniform hourly X-axis, the **`02:00`** slot must be represented.

**`$densify`** (MongoDB 5.1+) synthesizes documents for missing numeric/date values within a range.

### 10.1. Densifying After Hourly Grouping

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-10T05:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgTempC: { $avg: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      sampleCount: 1,
      avgTempC: 1
    }
  },
  {
    $densify: {
      field: "hourStart",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Inside `S-01`'s partition, MongoDB generates the **`02:00`** document, leaving **`sampleCount`** and **`avgTempC`** absent because no matching measurements existed.

### 10.2. `bounds: "partition"` vs. `"full"`

| `bounds` | Range |
|---|---|
| **`"partition"`** | From min to max within each individual partition. |
| **`"full"`** | Across the global min-to-max range of the field in the dataset. |
| **`[lower, upper]`** | Explicit interval, lower inclusive and upper exclusive. |

With `bounds: "partition"`, `S-01` will not synthesize **`04:00`** when its last reading is at `03:50`. To emit all slots `00–04`, use explicit bounds or a dedicated timeline.

### 10.3. Explicit Bounds

~~~javascript
{
  $densify: {
    field: "hourStart",
    partitionByFields: ["sensorId"],
    range: {
      step: 1,
      unit: "hour",
      bounds: [
        ISODate("2026-05-10T00:00:00Z"),
        ISODate("2026-05-10T05:00:00Z")
      ]
    }
  }
}
~~~

For each partition present in the input, missing slots from `00` to `04` UTC are synthesized. **`$densify` does not create partitions for sensors with zero input documents**; to show completely offline sensors, start from a sensors registry and join/lookup summaries onto a time grid.

### 10.4. Document Generation Cost

For example, 50,000 sensors × 24 hours = 1.2 million rows/day before running downstream statistics. **`$densify` enforces limits on generated document counts** and can significantly spike CPU and memory.

Never densify years of history just to render a 24-hour chart. Narrow **`$match`, time range, and partitions** first.

### 10.5. Ordering After `$densify`

**`$densify` does not guarantee output sort order**. Add **`$sort`** when display order, ordered fills, or window stages follow.

## 11. `$fill`: Handling Missing Data Responsibly

**`$fill`** (MongoDB 5.3+) populates `null`/missing fields using specified methods.

| Method | Mechanism | When appropriate |
|---|---|---|
| **`value`** | Fills a fixed value or expression. | `sampleCount = 0` for buckets with genuinely zero events. |
| **`locf`** | Carries forward the nearest prior non-null value. | Retaining last-known state when domain semantics allow. |
| **`linear`** | Linearly interpolates between neighboring values. | Continuous signals across short gaps where interpolation is valid. |

### 11.1. Filling `sampleCount = 0` While Leaving Temperature Unknown

After **`$densify`**:

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      sampleCount: {
        value: 0
      }
    }
  }
}
~~~

`S-01` becomes:

| `hourStart` | `sampleCount` | `avgTempC` | Meaning |
|---|---:|---:|---|
| 00:00 | 2 | 29 | Two samples recorded. |
| 01:00 | 1 | 29 | One sample recorded. |
| 02:00 | 0 | *missing/null* | No measurements recorded. |
| 03:00 | 2 | 31.5 | Two samples recorded. |

This accurately conveys **no data**, rather than claiming `02:00 = 0°C`.

### 11.2. Flagging Gaps Before Filling

~~~javascript
{
  $set: {
    dataStatus: {
      $cond: [
        { $eq: ["$sampleCount", null] },
        "NO_SAMPLES",
        "OBSERVED"
      ]
    }
  }
}
~~~

Place this stage **after `$densify` and before `$fill`**, while `sampleCount` on newly synthesized rows is still missing.

### 11.3. Last Observation Carried Forward (`locf`)

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      avgTempC: {
        method: "locf"
      }
    }
  }
}
~~~

For the empty `02:00` slot, **`locf`** carries `01:00`'s average forward. This is an **estimated/held value**, not an actual measurement. Add an **`isImputed`** flag or preserve the raw average in a separate field for traceability.

### 11.4. Linear Interpolation

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      avgTempC: {
        method: "linear"
      }
    }
  }
}
~~~

If `01:00 = 29°C` and `03:00 = 31.5°C`, linear interpolation fills `02:00` with **`30.25°C`**. This relies on assuming roughly linear change; never treat it as an observed reading.

Do not blindly apply interpolation to event counts, transaction counts, boolean states, or metrics incompatible with interpolation.

### 11.5. `$densify` and `$fill` Perform Two Separate Jobs

~~~text
$densify
  -> Generates documents at missing timestamp/numeric steps.

$fill
  -> Populates null/missing fields in existing documents,
     including newly generated documents from $densify.
~~~

Running **`$fill`** alone without a `02:00` row will not create `02:00`. Running **`$densify`** alone creates the timestamp row, leaving metric fields missing.

## 12. Rolling Averages After Constructing a Time Grid

After **`$group → $densify → $fill`**, you can compute sliding windows over an hourly grid.

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      rolling3CalendarHours: {
        $avg: "$avgTempC",
        window: {
          documents: [-2, 0]
        }
      },
      hoursWithSamples: {
        $sum: {
          $cond: [
            { $gt: ["$sampleCount", 0] },
            1,
            0
          ]
        },
        window: {
          documents: [-2, 0]
        }
      }
    }
  }
}
~~~

For `S-01` at hour `03`:

~~~text
hourStart 01:00, avg=29, sampleCount=1
hourStart 02:00, avg=null, sampleCount=0
hourStart 03:00, avg=31.5, sampleCount=2

rolling3CalendarHours = (29 + 31.5) / 2 = 30.25
hoursWithSamples = 2
~~~

This is the **average of populated hourly averages across three calendar buckets**—not the raw-measurement average across those hours, since sample counts differ.

### 12.1. Computing Raw-Measurement Averages Across Multiple Buckets

Suppose each hour retains **`sumTempC`** and **`validTempSamples`**. Instead of averaging averages:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      rollingTempSum: {
        $sum: "$sumTempC",
        window: { documents: [-2, 0] }
      },
      rollingSampleCount: {
        $sum: "$validTempSamples",
        window: { documents: [-2, 0] }
      }
    }
  }
}
~~~

Followed by:

~~~javascript
{
  $set: {
    rollingRawAverageC: {
      $cond: [
        { $gt: ["$rollingSampleCount", 0] },
        {
          $divide: [
            "$rollingTempSum",
            "$rollingSampleCount"
          ]
        },
        null
      ]
    }
  }
}
~~~

At `03:00` for `S-01`, hours `01, 02, 03` contain readings `29, 31, 32`; the result is **`(29+31+32)/3 = 30.6667`**, differing from `30.25` (the mean of hourly means).

### 12.2. Insufficient-Data Windows

To emit a "3-hour rolling" value only when at least **2 hours contain samples**, check **`hoursWithSamples >= 2`** and return `isCompleteWindow`/`dataQuality`. Just because MongoDB returns a number does not mean data coverage is trustworthy.

### 12.3. Truncating Input Context Too Early

To display a 3-hour rolling metric from `12:00` to `18:00`, include prior context before `12:00` when computing windows, then **filter the output to the display range** afterward.

A common bug is placing `$match` tightly on `12:00–18:00` and expecting `12:00` to reflect two prior hours of history.

## 13. Timezones and Local Time

### 13.1. Store UTC Timestamps, Group by Business Timezone

Standard practice stores timestamps as **BSON Date** (absolute instants) and supplies `timezone` when computing calendar boundaries.

Example:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

May 10 in Vietnam starts at **17:00 UTC on May 9**. Consequently, the BSON Date representing the start of a local day falls on the preceding UTC calendar date.

### 13.2. Daylight Saving Time (DST)

In some timezones, a day can be **23 or 25 hours** long across DST transitions.

Therefore:

- A local calendar day **does not always equal 86,400 seconds**.
- Local clock hours can be skipped or occur twice.
- Grouping keys formatted as **`YYYY-MM-DD HH`** strings without an offset can collide across repeated hours.
- `$dateTrunc` with Olson timezones (e.g., **`America/New_York`**) respects DST boundaries, though UIs must still label repeated hours clearly.

Never manually add fixed offsets to timestamps across all sites and slice date strings when data spans DST timezones.

### 13.3. Weeks Starting on Monday

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Without `startOfWeek`, week boundaries may mismatch your business calendar. Document the convention in report schemas so revenue dashboards stay consistent.

### 13.4. Computing Ingestion Delay

Given:

~~~javascript
{
  ts: ISODate("2026-05-10T00:05:00Z"),
  ingestedAt: ISODate("2026-05-10T00:06:15Z")
}
~~~

subtracting two BSON Dates yields milliseconds:

~~~javascript
{
  $subtract: ["$ingestedAt", "$ts"]
}
~~~

This yields **75,000 ms**. **`$dateDiff`** suits calendar-unit boundary counts; do not default to it as a blanket replacement for exact elapsed milliseconds.

### 13.5. Summary Schemas Should Record Timezone and Granularity

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("2026-05-09T17:00:00Z"),
  timezone: "Asia/Ho_Chi_Minh",
  granularity: "day",
  validSamples: 123
}
~~~

When storing summaries for multiple timezones, **`timezone`, `granularity`, and `site`/`sensor`** may belong in the business key. Never merge two local days from different timezones merely because their UTC timestamps coincide.

## 14. Percentiles, Standard Deviation, and Quality Metrics

### 14.1. Useful Accumulators in `$group`

~~~javascript
{
  $group: {
    _id: {
      sensorId: "$meta.sensorId",
      hourStart: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour"
        }
      }
    },
    sampleCount: { $sum: 1 },
    avgTempC: { $avg: "$temperatureC" },
    stdDevPopTempC: { $stdDevPop: "$temperatureC" },
    minTempC: { $min: "$temperatureC" },
    maxTempC: { $max: "$temperatureC" }
  }
}
~~~

**`$stdDevPop`** computes population standard deviation, whereas **`$stdDevSamp`** computes sample standard deviation. Pick the right definition and document it; with a single sample, sample standard deviation is undefined.

### 14.2. Percentiles (MongoDB 7.0+)

Example for p50 and p95:

~~~javascript
{
  $group: {
    _id: "$meta.sensorId",
    percentiles: {
      $percentile: {
        input: "$temperatureC",
        p: [0.5, 0.95],
        method: "approximate"
      }
    }
  }
}
~~~

The **`percentiles`** output is an array matching the requested probabilities. Under the `approximate` method's semantics, do not promise that p95 is always an exact raw sample value.

Never average hourly p95 values to derive a daily p95; percentiles do not combine that way.

### 14.3. Checking Valid Sample Counts

A bucket might contain 100 measurements while only 15 contain a valid `temperatureC`. Separate these fields in reports:

~~~text
totalReadings
validTempReadings
missingTempReadings
avgTempC
coverage
~~~

If each sensor is **expected** to emit one sample every 5 minutes, an hour expects 12 samples:

~~~text
coverage = actualValidSamples / expectedSamples
~~~

However, `expectedSamples` depends on schedules, downtime, DST, and sensor types. Never hardcode denominator `12` across devices with differing cadences.

## 15. Multi-Level Rollups: From Hourly to Daily Statistics

Dashboards often support multiple zoom levels:

~~~text
Raw measurements (seconds/minutes)
             |
             v
Hourly statistics
             |
             v
Daily statistics
             |
             v
Weekly / Monthly statistics
~~~

Rather than scanning raw readings for every weekly request, compute daily stats from hourly summaries when those summaries preserve sufficient statistics.

### 15.1. Averaging Averages Can Be Wrong

Suppose:

| Hour | Samples | Average temp |
|---|---:|---:|
| 00:00 | 2 | 29 |
| 01:00 | 1 | 29 |
| 03:00 | 2 | 31.5 |

Simple mean of the three hourly averages:

~~~text
(29 + 29 + 31.5) / 3
= 29.8333
~~~

Whereas the mean across **all 5 raw readings** is:

~~~text
(28 + 30 + 29 + 31 + 32) / 5
= 30
~~~

Why do they differ? Hour `01` has one sample yet received **equal weight** to hours with two samples.

### 15.2. Persist `sum` and Valid `count`

Each hourly summary should store:

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("2026-05-10T00:00:00Z"),
  sampleCount: 2,
  sumTempC: 58,
  validTempSamples: 2,
  avgTempC: 29,
  minTempC: 28,
  maxTempC: 30
}
~~~

When rolling up to daily:

~~~javascript
db.sensor_hourly_stats.aggregate([
  {
    $match: {
      sensorId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensorId",
        dayStart: {
          $dateTrunc: {
            date: "$bucketStart",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: "$sampleCount" },
      sumTempC: { $sum: "$sumTempC" },
      validTempSamples: { $sum: "$validTempSamples" },
      minTempC: { $min: "$minTempC" },
      maxTempC: { $max: "$maxTempC" }
    }
  },
  {
    $set: {
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  }
]);
~~~

**Rollups are accurate only when hourly fields share consistent semantics and units.** For local calendar days, use the appropriate timezone and time range—never build a UTC day and display it as a local day.

### 15.3. Min/Max and Standard Deviation

From hourly summaries:

- **Daily min** = `min(hourly min)`.
- **Daily max** = `max(hourly max)`.
- **Daily sum** = `sum(hourly sum)`.
- **Daily count** = `sum(hourly count)`.

However, **daily `stddev` does not equal `average(hourly stddev)`**. Rolling up `stddev` requires storing sufficient moments (count, sum, and sum of squares) or recomputing from raw data.

### 15.4. Percentiles Do Not Roll Up Like Means

You cannot compute exact daily p95 solely from hourly p95s and counts. If downstream consumers need exact population percentiles, either:

- Recompute from raw measurements.
- Or use a mergeable statistical structure (such as a validated sketch/histogram).

### 15.5. Metrics with Different Physical Units

**`temperatureC`** and **`powerW`** obey different semantics:

- Average temperature across samples is an intensive measurement statistic.
- Average power (W) is not energy consumed (Wh).
- Energy requires integrating power over time; on irregular intervals, define explicit interpolation/integration rules and units.

Never add one hour at `powerW = 100` and the next hour at `powerW = 150` and label the sum **250 kWh**. Both the calculation and the unit would be wrong.

## 16. Materializing Statistics Collections with `$merge`

When raw collections hold millions of readings, re-scanning and grouping on every HTTP request is expensive. A **materialized view** persists precomputed aggregates for fast reads:

~~~text
sensor_readings (raw time series)
        |
        v
Hourly aggregation
        |
        v
$merge into sensor_hourly_stats
        |
        v
Dashboard queries summary collection
~~~

### 16.1. Create a Regular Summary Collection

Do not make the summary table a **time series collection**; a regular collection simplifies upserts, replacements, and unique indexes:

~~~javascript
db.createCollection("sensor_hourly_stats");

db.sensor_hourly_stats.createIndex(
  {
    sensorId: 1,
    bucketStart: 1
  },
  {
    unique: true,
    name: "uq_sensor_hour"
  }
);
~~~

**Fields specified in `$merge.on` must be backed by a matching unique index** per server rules, preventing duplicate summaries for the same sensor and hour.

### 16.2. Recomputing a Day and Merging

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        bucketStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      bucketStart: "$_id.bucketStart",
      granularity: { $literal: "hour" },
      timezone: { $literal: "UTC" },
      sampleCount: 1,
      validTempSamples: 1,
      sumTempC: 1,
      minTempC: 1,
      maxTempC: 1,
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $merge: {
      into: "sensor_hourly_stats",
      on: ["sensorId", "bucketStart"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

### 16.3. Why Project `_id: 0`?

`$group` outputs a composite object `_id`. However, **`$merge`** identifies summary documents via **`sensorId + bucketStart`**. Passing a different `_id` from `$group` can trigger an immutable `_id` error during replacement.

Always **strip the `$group` `_id` before `$merge`** when matching on custom `on` fields so MongoDB manages target `_id`s per `$merge` rules.

### 16.4. `whenMatched` Options

| Choice | Behavior |
|---|---|
| **`replace`** | Replaces existing summary document with recomputed output; ideal for recomputes. |
| **`merge`** | Updates/merges fields emitted by the pipeline. |
| **`keepExisting`** | Preserves old summary if present; unsuitable when late data must update stats. |
| **`fail`** | Errors on key collision. |
| **custom pipeline** | Executes custom update pipeline supported by MongoDB; design carefully. |

For late-arriving data, **`replace`** is usually cleaner than incrementing counts, because recomputing from source avoids double-counting when jobs re-run.

### 16.5. `$merge` Has Write Side Effects

An aggregation ending in **`$merge`** **writes to the target collection**. When executed, it does not return summary rows like a read-only pipeline.

`$merge` updates across multiple documents are **not a single batch-wide atomic transaction**. If a job fails midway, some buckets are updated while others are not. Design jobs to be **idempotent and recomputable**, with checkpoints, run state, or partition-level publishing when strict consistency is required.

### 16.6. Never Run Uncoordinated Concurrent Overwriting Jobs

If a slow backfill job and a near-real-time job `$merge` the same keys, the slower job can overwrite newer numbers with stale snapshots.

Mitigations:

1. Enforce a single writer per partition/time range.
2. Guard publishes with watermarks, versions, or compare-and-set.
3. Write to versioned staging collections and swap views/pointers cleanly.
4. Recompute and reconcile after overlapping runs.

Never assume `$merge` with `whenMatched: "replace"` solves concurrency races on its own.

## 17. Reading Materialized Summaries from Dashboards

After materialization:

~~~javascript
db.sensor_hourly_stats.find(
  {
    sensorId: "S-01",
    bucketStart: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  },
  {
    _id: 0,
    sensorId: 1,
    bucketStart: 1,
    sampleCount: 1,
    avgTempC: 1,
    minTempC: 1,
    maxTempC: 1
  }
).sort({
  bucketStart: 1
});
~~~

The dashboard reads one summary document per hour instead of scanning all raw readings. Keep in mind summaries are **eventually consistent** with raw data; define SLAs for materialization lag and staleness handling.

### 17.1. One Collection vs. Multiple Collections per Resolution

You can either separate collections:

~~~text
sensor_5m_stats
sensor_hourly_stats
sensor_daily_stats
~~~

or store together with explicit discriminator fields:

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("..."),
  granularity: "hour",
  timezone: "UTC",
  ...
}
~~~

Choose based on schema, indexes, TTL, retention, and query patterns. If sharing one collection across granularities or timezones, include **`granularity` and `timezone`** in the unique key whenever they alter bucket meaning.

### 17.2. Summary Timestamps

Commonly store:

- **`bucketStart`**: start of the summarized window.
- **`bucketEnd`** or `granularity`: defines `[start, end)`.
- **`computedAt`**: when the job last created/updated the summary.
- **`sourceWatermark`**: event-time watermark processed by the job.
- **`dataQuality`** or `coverage`: completeness indicator.

**`computedAt` differs from `bucketStart`**: data measured at `00:00` may be recomputed at `08:30` after delayed sensor uploads arrive.

### 17.3. Combining Summaries with Real-Time Data

A dashboard can combine:

~~~text
Closed / finalized hours -> sensor_hourly_stats
Current open hour        -> raw readings / real-time aggregation
~~~

Once the current hour closes and its late-arrival allowance passes, reads transition to the stable summary. Define the boundary cleanly to avoid double-rendering or missing the transition hour.

## 18. Late Arrivals, Backfills, and Watermarks

### 18.1. Events Occurring Earlier but Stored Later

Example:

~~~javascript
{
  ts: ISODate("2026-05-10T01:20:00Z"),
  ingestedAt: ISODate("2026-05-10T04:05:00Z"),
  meta: { sensorId: "S-01", site: "HCM" },
  temperatureC: 35
}
~~~

This reading belongs to the **01:00 bucket in event time**, not 04:00.

If the hourly summary ran at 02:10, it missed this late reading. A job computing only the **current hour** will never repair 01:00.

### 18.2. Recomputing Recent Rolling Windows

A simple strategy:

~~~text
Every 5 minutes:
  Recompute buckets over the last 24 hours.
  Write with $merge whenMatched: "replace".

Nightly:
  Reconcile days within the retention/backfill SLA.
~~~

24 hours is merely illustrative. Choose based on **actual source delays and business SLAs**. If readings routinely arrive 48 hours late, 24 hours is insufficient.

### 18.3. Watermarks and Bucket Completeness

In stream processing, a **watermark** represents the event-time threshold up to which data is assumed complete under chosen tolerances. Example:

~~~text
Current processing time: 12:00
Allowed lateness: 2 hours
Watermark: 10:00
~~~

Buckets ending before 10:00 may be treated as relatively complete **under the 2-hour SLA**, though never as proof that even older readings cannot arrive.

MongoDB aggregations **do not automatically create or maintain business watermarks**. Your application/scheduler must track source arrival times, bucket state, and late corrections.

### 18.4. Historical Backfills

When repairing a month of history, execute aggregations in manageable **partitions/time ranges**:

~~~text
Backfill 2026-05:
  Day 01 -> recompute hourly -> merge
  Day 02 -> recompute hourly -> merge
  ...
  Day 31 -> recompute hourly -> merge
~~~

Each partition needs logging, retries, and count/sum reconciliation checks. Never launch one massive unrecoverable pipeline across months of history.

### 18.5. Deletes and Corrections

When raw measurements are deleted or edited, incremental delta updates can drift summaries.

For instance, removing a 35°C sample:

~~~text
Old bucket: sampleCount=3, sumTempC=95
New bucket: sampleCount=2, sumTempC=60
~~~

**Recomputing from current raw data** and replacing summaries handles edits cleanly for recomputed buckets. In append-only architectures, model corrections via explicit correction/compensating events.

### 18.6. Classic Bug: Non-Idempotent Incremental `$inc`

If a consumer receives an insert event and runs:

~~~javascript
db.sensor_hourly_stats.updateOne(
  { sensorId: "S-01", bucketStart: hourStart },
  {
    $inc: {
      sampleCount: 1,
      sumTempC: temperatureC
    }
  }
);
~~~

then **replaying the same event** double-counts it. Exact incremental aggregation requires event deduplication, ordering, and transactional checkpoints.

At moderate data volumes, **overlapping recompute + `$merge` replace** is far simpler to operate and recover.

## 19. Optimizing Aggregations on Time Series Collections

### 19.1. Place `$match` as Early as Possible

Common first stage:

~~~javascript
{
  $match: {
    "meta.sensorId": "S-01",
    ts: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  }
}
~~~

Filtering early on **`metaField` subfields** and **`timeField` ranges** enables index usage and bucket pruning, minimizing documents reaching heavy stages like `$group`, `$densify`, `$setWindowFields`, and `$merge`.

Never run `$setWindowFields` across the entire raw collection before filtering by sensor, unless cross-boundary context is truly needed and budgeted.

### 19.2. Index by Query Pattern

For queries filtering by sensor and time:

~~~javascript
db.sensor_readings.createIndex(
  {
    "meta.sensorId": 1,
    ts: 1
  }
);
~~~

Time series indexes follow version-specific rules. **Since MongoDB 6.3, time series collections may auto-create an index on `timeField`/`metaField`**, so inspect existing indexes first to avoid duplicates.

Whether an index helps depends on cardinality, selectivity, bucket layout, and query patterns—not syntax alone.

### 19.3. Stable `metaField` and Suitable `granularity`

Time series collections pack measurements into storage buckets by `metaField` and time.

Best practices:

- Put `sensorId`, fixed site, or device type in `metaField` when frequently filtered.
- Keep per-reading volatile fields like random `requestId`s out of `metaField`.
- Pick `granularity` (**`seconds`/`minutes`/`hours`**) matching measurement spacing.
- On supported MongoDB versions, evaluate **`bucketMaxSpanSeconds` / `bucketRoundingSeconds`** if custom bucketing is needed.
- Never confuse **storage bucket `granularity`** with 15-minute reporting bins created by `$dateTrunc`.

### 19.4. Bound Output Cardinality

Given:

~~~text
100,000 sensors
12 buckets per hour for 5-minute stats
24 hours/day
~~~

potential output rows reach:

~~~text
100000 × 12 × 24 = 28,800,000 rows/day
~~~

That volume is already massive before `$densify` adds gaps. Bound scope and time ranges, downsample appropriately for display resolution, and avoid constructing dense grids over multi-year histories.

### 19.5. Managing Memory and Disk Spill

**`$group`**, **`$sort`**, and **`$setWindowFields`** can consume substantial memory depending on partition count and data volume. Where supported by server version and stage limits, consider **`allowDiskUse`**:

~~~javascript
db.sensor_readings.aggregate(
  [
    {
      $match: {
        "meta.sensorId": "S-01",
        ts: {
          $gte: ISODate("2026-05-10T00:00:00Z"),
          $lt: ISODate("2026-05-11T00:00:00Z")
        }
      }
    },
    {
      $group: {
        _id: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour"
          }
        },
        avgTempC: { $avg: "$temperatureC" }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
~~~

Enabling disk spill **is not a fix for an unbounded pipeline**. It increases disk I/O and latency. Reduce input via `$match`, partitioning, indexes, and materialization first.

### 19.6. `explain` and Metrics

Inspect query plans with:

~~~javascript
db.sensor_readings.explain("executionStats").aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour"
        }
      },
      n: { $sum: 1 }
    }
  }
]);
~~~

Inspect documents/buckets examined, execution duration, index usage, sort/group costs, and disk spill exposed by your server. Never assume `explain` output has identical structure across MongoDB versions.

### 19.7. Raw TTL vs. Summary Retention

Time series collections accept **`expireAfterSeconds`** to automatically purge expired raw measurements:

~~~javascript
db.createCollection("sensor_readings_ttl_demo", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
});
~~~

This sets roughly **30-day** retention on raw data in a separate collection. Expired cleanup runs with delay and operates by storage buckets; never claim documents vanish at the exact millisecond of expiration.

If the business permits corrections 60 days later while raw TTL is 30 days, a job cannot recompute a 45-day-old bucket from raw data. **Raw retention must exceed late-arrival/backfill SLAs**, or a longer-term archive is required.

### 19.8. Using Materialized Summaries to Downsample

A tiered retention strategy:

~~~text
Raw measurements:          30 days
5-minute summary:          90 days
Hourly summary:             2 years
Daily summary:              5 years
~~~

These thresholds are illustrative. What matters:

- Know what detail is lost when downsampling.
- Retain sufficient statistics for required rollups.
- Align retention with privacy and data governance.
- Backfill or reconcile before raw data expires.

## 20. Java Sync Driver: Hourly Aggregation

The MongoDB Java Sync Driver accepts pipeline stages as **`Bson`** objects.

### 20.1. Complete Java Example

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SensorHourlyStats {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI is required");
        }

        Date from = Date.from(
                Instant.parse("2026-05-10T00:00:00Z")
        );
        Date to = Date.from(
                Instant.parse("2026-05-11T00:00:00Z")
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_timeseries_stats_lab"
            );
            MongoCollection<Document> readings =
                    database.getCollection("sensor_readings");

            Bson match = Aggregates.match(
                    Filters.and(
                            Filters.eq("meta.sensorId", "S-01"),
                            Filters.gte("ts", from),
                            Filters.lt("ts", to)
                    )
            );

            Document dateTrunc = new Document(
                    "$dateTrunc",
                    new Document("date", "$ts")
                            .append("unit", "hour")
                            .append("timezone", "UTC")
            );

            Bson group = new Document(
                    "$group",
                    new Document("_id", dateTrunc)
                            .append(
                                    "sampleCount",
                                    new Document("$sum", 1)
                            )
                            .append(
                                    "avgTempC",
                                    new Document("$avg", "$temperatureC")
                            )
                            .append(
                                    "minTempC",
                                    new Document("$min", "$temperatureC")
                            )
                            .append(
                                    "maxTempC",
                                    new Document("$max", "$temperatureC")
                            )
            );

            List<Bson> pipeline = List.of(
                    match,
                    group,
                    new Document("$sort", new Document("_id", 1))
            );

            readings.aggregate(pipeline)
                    .allowDiskUse(true)
                    .forEach(System.out::println);
        }
    }
}
~~~

Explanation:

- **`Filters.gte`/`lt`** constructs the `[from, to)` range.
- **`$dateTrunc`** maps timestamps into hourly buckets.
- **`$group`** produces one result document per hour.
- **`$sort`** guarantees chronological output.
- **`allowDiskUse(true)`** should be used deliberately—never as a substitute for indexes and early filters.

This is a **read-only aggregation**: it streams summaries to Java without writing to a materialized collection.

### 20.2. Running `$merge` from Java

Once a unique index exists and you want to persist summaries, append:

~~~java
Document mergeStage = new Document(
        "$merge",
        new Document("into", "sensor_hourly_stats")
                .append("on", List.of("sensorId", "bucketStart"))
                .append("whenMatched", "replace")
                .append("whenNotMatched", "insert")
);
~~~

Before appending this stage, include a **`$project` or `$set`** emitting **`sensorId`** and **`bucketStart`** and stripping `_id` as shown earlier. Never pair `$group` with a Date `_id` directly into `$merge` matching on non-existent fields.

When a pipeline ends with `$merge`, it **performs writes** and does not return a list of summary documents like a read-only aggregation. Never run it synchronously in an HTTP request expecting a large JSON result array.

### 20.3. Java Dates and Timezones

Java **`Instant`** represents an absolute instant; `Date.from(Instant)` persists as a BSON Date. When grouping by business days, pass the Olson timezone string directly to **`$dateTrunc`** rather than shifting Java `Date` offsets manually.

### 20.4. Numeric Precision

For financial amounts, avoid `Double` where exact decimal arithmetic is needed; for sensor readings, `double` is usually acceptable within device precision. If using **`Decimal128`**, keep BSON types uniform and verify accumulator behavior.

The Java code above is illustrative; production code requires timeouts, exception handling, pagination/batching, authentication, and resource budgets.

## 21. Spring Data MongoDB: Building Aggregation Pipelines

Spring Data MongoDB provides **`MongoTemplate.aggregate()`** and fluent builders for standard stages. For newer or specialized operators like `$dateTrunc`, `$densify`, or `$fill`, **`AggregationOperation`** lets you emit exact BSON stages compatible with your Spring Data version.

### 21.1. Example Using `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.query.Criteria;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SpringHourlyStatsService {

    private final MongoTemplate template;

    public SpringHourlyStatsService(MongoTemplate template) {
        this.template = template;
    }

    public List<Document> hourly(String sensorId) {
        Date from = Date.from(
                Instant.parse("2026-05-10T00:00:00Z")
        );
        Date to = Date.from(
                Instant.parse("2026-05-11T00:00:00Z")
        );

        AggregationOperation match = Aggregation.match(
                Criteria.where("meta.sensorId").is(sensorId)
                        .and("ts").gte(from).lt(to)
        );

        AggregationOperation group = context -> new Document(
                "$group",
                new Document(
                        "_id",
                        new Document(
                                "$dateTrunc",
                                new Document("date", "$ts")
                                        .append("unit", "hour")
                                        .append("timezone", "UTC")
                        )
                )
                        .append(
                                "sampleCount",
                                new Document("$sum", 1)
                        )
                        .append(
                                "avgTempC",
                                new Document("$avg", "$temperatureC")
                        )
        );

        AggregationOperation sort = context ->
                new Document("$sort", new Document("_id", 1));

        Aggregation aggregation = Aggregation.newAggregation(
                match,
                group,
                sort
        );

        return template.aggregate(
                aggregation,
                "sensor_readings",
                Document.class
        ).getMappedResults();
    }
}
~~~

In this example:

- **`Aggregation.match(Criteria)`** scopes sensor and time early.
- **`AggregationOperation` lambdas** supply raw BSON Document stages.
- **`MongoTemplate.aggregate`** maps and returns the grouped results.

Do not reuse the raw measurement Java DTO if the grouped output `_id` and summary fields differ from raw documents. Define a dedicated hourly summary DTO and map explicitly.

### 21.2. Spring Data Mapping Note

When writing raw **`AggregationOperation`** stages, field names inside `Document` must match **the actual stored MongoDB field names**. If an entity uses **`@Field`** to rename properties, inspect the mapping context and use typed builders or the exact persisted field names.

### 21.3. `ReactiveMongoTemplate`

In reactive stacks, **`ReactiveMongoTemplate.aggregate()`** returns a **`Flux`** of aggregated results. However:

- `Flux` does not make server-side `$group` free.
- Consumers still need backpressure and must never block the event loop.
- Long-running pipelines remain bound by server resource limits and timeouts.
- A `$merge` pipeline has **write side effects** and is not a streamable query source.

Never spawn heavy aggregations per WebSocket subscriber without caching and concurrency limits.

### 21.4. Version Compatibility

`$dateTrunc`, `$setWindowFields`, `$densify`, `$fill`, and `$percentile` each have minimum server version requirements. Your Spring Data MongoDB version also determines which typed builders exist.

When a typed builder is missing, `AggregationOperation` can emit the raw BSON stage, yet the server must still support that operator. **A raw `Document` will not make MongoDB 4.4 understand `$dateTrunc`.**

## 22. Complete Pipeline: Hourly Summary, Gap Detection, and Rolling Average

This section combines the concepts into a **read-only** pipeline useful for rendering an hourly chart with data-coverage indicators.

Objectives:

1. Compute hourly sum, count, and average for `S-01`.
2. Fill missing hours between the first and last buckets.
3. Distinguish **`NO_SAMPLES`** from **`OBSERVED`**.
4. Fill missing hours' counts and sums with `0`.
5. Compute a rolling mean over **raw samples across the last three calendar buckets**.
6. Return rows sorted chronologically.

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-10T05:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      documentCount: {
        $sum: 1
      },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      documentCount: 1,
      validTempSamples: 1,
      sumTempC: 1,
      minTempC: 1,
      maxTempC: 1
    }
  },
  {
    $densify: {
      field: "hourStart",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $set: {
      dataStatus: {
        $cond: [
          { $eq: ["$documentCount", null] },
          "NO_SAMPLES",
          "OBSERVED"
        ]
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: {
        hourStart: 1
      },
      output: {
        documentCount: { value: 0 },
        validTempSamples: { value: 0 },
        sumTempC: { value: 0 }
      }
    }
  },
  {
    $set: {
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: {
        hourStart: 1
      },
      output: {
        rolling3hTempSum: {
          $sum: "$sumTempC",
          window: {
            documents: [-2, 0]
          }
        },
        rolling3hValidSamples: {
          $sum: "$validTempSamples",
          window: {
            documents: [-2, 0]
          }
        },
        cumulativeSampleCount: {
          $sum: "$documentCount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $set: {
      rolling3hRawAvgTempC: {
        $cond: [
          { $gt: ["$rolling3hValidSamples", 0] },
          {
            $divide: [
              "$rolling3hTempSum",
              "$rolling3hValidSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Key output columns on `S-01` sample data:

| Hour UTC | `documentCount` | `avgTempC` | `dataStatus` | `rolling3hRawAvgTempC` |
|---|---:|---:|---|---:|
| 00:00 | 2 | 29 | OBSERVED | 29 |
| 01:00 | 1 | 29 | OBSERVED | 29 |
| 02:00 | 0 | null | NO_SAMPLES | 29 |
| 03:00 | 2 | 31.5 | OBSERVED | 30.6667 |

Explanation:

- `02:00` has no samples, so `avgTempC = null`, yet the **3-hour rolling** value still computes from hours `00` and `01` (since `[00, 02]` contains samples).
- `03:00` covers buckets `01, 02, 03`; `sumTempC = 29 + 0 + 63 = 92`, `validTempSamples = 1 + 0 + 2 = 3`; result **`92 / 3 ≈ 30.6667`**.
- Final **`cumulativeSampleCount`** = `5`.

### 22.1. Returning Hour `04:00` Even Without Samples

Switch **`bounds`** from `"partition"` to an explicit date range ending exclusively at `05:00`, as in the `$densify` section. `S-01` then emits `04:00` even though its last reading arrived at `03:50`.

### 22.2. Including Completely Offline Sensors

A pipeline starting from `sensor_readings` sees only sensors with at least one matching source document. A completely offline sensor produces no partition and will not appear automatically.

Solve this with a **`sensors` inventory** collection: generate or fetch the required time grid per registered sensor and `$lookup`/left-join summaries onto it. This is essential for SLA reporting so a "completely offline sensor" never disappears silently from dashboards.

### 22.3. Never Replace Raw Averages with Imputed Values in Primary Metrics

The pipeline keeps **`avgTempC = null`** at `02:00`. If the UI needs a continuous line, compute a separate **`displayTempC`** field via interpolation or `locf` while keeping `dataStatus` clear on what is observed vs. estimated.

## 23. Reliability, Consistency, and Materialization Limits

### 23.1. `$merge` Does Not Delete Summaries When All Source Readings Disappear

This edge case is critical:

1. Initially, bucket `01:00` had three readings, so its summary was written.
2. Later, all three readings are deleted or corrected away in the raw source.
3. The **`$group → $merge`** pipeline re-runs.
4. Because `01:00` has zero source readings, **`$group` emits no row for `01:00`**.
5. **`$merge` does not delete** existing target summaries lacking a matching input row.

Consequently, the `01:00` summary becomes **stale** even though neighboring buckets refreshed.

Remedies:

- Emit a fixed time grid covering all buckets to publish, including 0-count buckets.
- Rebuild a partition/range into a staging collection and swap summaries cleanly.
- Run reconciliation to detect summary keys absent from raw-derived keys and delete or mark them stale.
- If physical deletes are prohibited, use immutable correction events with explicit business semantics.

Never treat `$merge` `replace` as full two-way synchronization between source and target collections.

### 23.2. Out-of-Order and Late Arrivals

Late readings can change the average, min, or max of a bucket dashboards assumed was finalized. Track lifecycle states:

~~~text
OPEN
  -> PROVISIONAL
  -> FINALIZED
  -> CORRECTED (if backfilled)
~~~

These states are application-managed—MongoDB aggregations do not emit them automatically.

### 23.3. Freshness of Summary Tables

Dashboards need to know:

- **When** was the summary computed?
- **Up to what event-time watermark** is source data complete?
- Is there an ingestion backlog?
- Is raw retention still sufficient to recompute?
- Are any jobs failing or actively backfilling?

Returning **`avgTempC`** without freshness metadata misleads users into assuming data is real-time.

### 23.4. Competing Writes

If a batch job and a real-time job write the same summary keys concurrently, **last-writer-wins** can overwrite fresh stats with stale data. Coordinate writers via locking, version guards, or versioned storage; `$merge` alone does not enforce cross-job ordering.

### 23.5. Multi-Tenant Data

If sensors belong to different tenants, summary keys must include **`tenantId`** (or use globally unique sensor IDs). Grouping solely by a per-tenant `sensorId` merges data across tenants.

Proper multi-tenant key:

~~~javascript
_id: {
  tenantId: "$meta.tenantId",
  sensorId: "$meta.sensorId",
  hourStart: {
    $dateTrunc: {
      date: "$ts",
      unit: "hour",
      timezone: "UTC"
    }
  }
}
~~~

The summary's unique index must mirror the same business key, and API queries must still enforce tenant filters from authenticated context.

### 23.6. Anomalous Numeric Data

Distinguish:

- **Sensor outage:** missing readings.
- **Bad value:** reading present, but `temperatureC` outside physical bounds.
- **Duplicate event:** same measurement recorded multiple times.
- **Calibration correction:** prior value superseded per business rules.

Never assume every numeric BSON value is valid. Proper validation/calibration enforces domain bounds (e.g., physical sensor limits) and deduplicates by event ID where needed.

## 24. Production Deployment Checklist

### 24.1. Data Design

1. Distinguish **event time** and **ingestion time** accurately.
2. Store BSON Date in UTC and choose reporting timezones explicitly.
3. Create time series collections with stable **`timeField`** and **`metaField`**.
4. Choose storage `granularity`, indexes, and raw retention.
5. Define metric schemas: units, numeric types, `null`, missing, and outliers.
6. Include deduplication keys if ingestion can replay.

### 24.2. Aggregation Design

1. Push **`$match`** on tenant/sensor/time as early as possible.
2. Configure **`$dateTrunc`** with accurate `binSize`, `timezone`, and `startOfWeek`.
3. Clarify whether metrics represent raw sample averages or averages of bucket averages.
4. Configure **`$setWindowFields`** with proper `partitionBy`, `sortBy`, and window bounds.
5. Use **`$densify`/`$fill`** deliberately without turning missing readings into misleading zeros.
6. Provide tie-breakers for tied timestamps when order matters.
7. Append **`$sort`** at the end whenever callers expect ordered output.
8. Separate provisional from finalized outputs under late data.

### 24.3. Materialization and Lifecycle

1. Use a regular output collection with a unique business key for `$merge`.
2. Persist **`sum`, `count`, `min`/`max`**—not `avg` alone.
3. Include `timezone` and `granularity` in summary keys where needed.
4. Schedule overlapping recomputes for late arrivals.
5. Implement full backfill/reconciliation for raw corrections or deletes.
6. Handle summary buckets whose source readings were deleted.
7. Prevent concurrent jobs from overwriting newer results with stale snapshots.
8. Monitor `computedAt`, watermarks, `dataQuality`, and last successful run.

### 24.4. Performance and Operations

1. Monitor index usage, input row counts, and output cardinality.
2. Bound partition counts and output rows in `$densify`.
3. Never run multi-year raw `$group` queries synchronously on dashboard requests.
4. Track memory consumption and disk spill across `$group`/`$sort`/`$setWindowFields`.
5. Configure timeouts, retry policies, and error-specific backoff.
6. Never rely on `allowDiskUse` to mask poor pipeline design.
7. Ensure raw TTL exceeds late-arrival and backfill SLAs.
8. Test against irregular cadences, `null`s, DST transitions, and late data.

## 25. Common Pitfalls and Fixes

| Pitfall | Consequence | Fix |
|---|---|---|
| Averaging hourly averages | Wrong when sample counts differ | Retain `sum + validCount`; compute weighted mean |
| Using `documents: [-2, 0]` and calling it 3 hours | Skips gaps; may span more than 3 hours | Use time `range` or densify the bucket grid |
| Using `$fill` alone without missing rows | Missing hours are never created | Run `$densify` first or join a time grid |
| Filling missing temperature with `0` | Fake `0°C` dips on charts | Keep `null + dataStatus` or transparent interpolation |
| Using local time strings as group keys | DST hour collisions and timezone bugs | Use BSON Date + `$dateTrunc` with explicit timezone |
| Running `$merge` without a unique index on `on` | `$merge` fails or creates duplicates/conflicts | Align unique index and business key |
| Storing only `avg` without `sum`/`count` | Cannot compute exact daily means from hourly stats | Store sufficient statistics |
| Recomputing only the newest bucket | Late data never updates older buckets | Run overlapping recomputes / backfills |
| Deleting all source readings of a bucket | `$merge` leaves stale summary behind | Reconcile, emit 0-count grid, or rebuild range |
| Densifying full multi-year history | Row explosion and heavy load | Bound sensors/time and downsample |
| Raw TTL shorter than backfill SLA | Cannot recompute expired intervals | Align retention or keep cold archive |
| Omitting tenant from `$group` | Cross-tenant data mixing | Group by `tenant + sensor + bucket` |
| Treating `sum(powerW)` as `kWh` | Wrong calculation and wrong unit | Define energy integration over interval |
| Treating cached summaries as real-time | Stale figures presented as live | Track watermark/`computedAt` + SLA |

## 26. Practice Exercises

### Exercise 1 — Event Time vs. Ingestion Time

A sensor records a reading at 10:05, loses connectivity, and the server receives it at 11:50. Answer:

1. Which hourly bucket does the reading belong to when charting temperature by measurement time?
2. Which hourly bucket does it belong to when charting server ingestion volume?
3. Why should both reports not blindly share the same timestamp field?

### Exercise 2 — Hourly Aggregation

From `sensor_readings`, write a pipeline grouping by **`meta.sensorId`** and UTC hour start, returning:

~~~text
sensorId, hourStart, sampleCount, avgTempC, minTempC, maxTempC
~~~

Verify `S-01` at `00:00` has two samples (`28°C` and `30°C`), average `= 29°C`.

### Exercise 3 — 15-Minute Buckets

Rewrite the **`$dateTrunc`** expression for 15-minute buckets. Which buckets contain the `00:05` and `00:35` readings?

### Exercise 4 — Grouping by Vietnam Calendar Day

Write a pipeline grouping by **`dayStart`** in **`Asia/Ho_Chi_Minh`**. Explain why `dayStart` for a local calendar day can display as the previous UTC calendar day.

### Exercise 5 — Weeks Starting Monday

Write a **`$dateTrunc`** expression with `unit: "week"`, `startOfWeek: "monday"`, and your target timezone.

### Exercise 6 — Valid Count vs. Document Count

Suppose an hour has 12 documents, 3 of which lack `temperatureC`. Write expressions producing:

~~~text
totalDocuments = 12
validTempSamples = 9
avgTempC computed from the 9 valid samples
~~~

Use **`$isNumber`**, **`$cond`**, **`$sum`**, and **`$avg`**.

### Exercise 7 — `documents` Window vs. Time-`range` Window

Given measurements:

~~~text
00:05 -> 28
00:35 -> 30
01:10 -> 29
03:20 -> 31
~~~

At the `03:20` reading, list which readings fall inside:

- `documents: [-2, 0]`
- `range: [-60, 0], unit: "minute"`

Why do the two windows produce different sets?

### Exercise 8 — Cumulative Sample Count

Starting from `S-01`'s hourly counts `2, 1, 2`, use **`$setWindowFields`** to compute cumulative counts `2, 3, 5` in chronological order.

### Exercise 9 — `$shift` and Delta

Write a pipeline retrieving `previousTemperatureC` and `previousTs` per sensor ordered by `ts`, then compute `deltaTempC`. Explain how to handle the first row where `previous = null`.

### Exercise 10 — Rate of Change

At `00:05` temperature is `28°C`; at `00:35` it is `30°C`. Compute the rate in `°C/hour` assuming linear change over that interval. Why must you check `elapsedMs > 0`?

### Exercise 11 — EMA

Write `$setWindowFields` with **`$expMovingAvg`** using `N = 3` per sensor. Why does EMA over irregularly spaced readings not equal a three-calendar-hour average?

### Exercise 12 — Adding Missing Hours with `$densify`

`S-01` has no readings during hour `02:00`. From hourly summaries, write `$densify` with `partitionByFields: ["sensorId"]`, `step = 1`, `unit = "hour"`, `bounds = "partition"`.

### Exercise 13 — Filling Count Without Filling Temperature

After densifying, use `$fill` to set `sampleCount` at hour `02` to `0`, leaving `avgTempC` as `null`/missing. Why should you not assign `0°C`?

### Exercise 14 — Linear Interpolation

Hour `01` has `avgTempC = 29`, hour `03` has `avgTempC = 31.5`, and hour `02` is missing. Apply `$fill` with `method: "linear"`, then explain the `30.25` result and its underlying assumption.

### Exercise 15 — Comparing Two Moving Averages

At `03:00`, `S-01` has:

~~~text
01:00 -> 1 sample: 29
02:00 -> 0 samples
03:00 -> 2 samples: 31, 32
~~~

Compute:

1. The average of the two populated hourly averages.
2. The average across the three raw samples.
3. Explain why the two numbers differ.

### Exercise 16 — Daily Mean from Hourly Summaries

Given:

| Hour | `count` | `sumTempC` | `avgTempC` |
|---|---:|---:|---:|
| 00 | 2 | 58 | 29 |
| 01 | 1 | 29 | 29 |
| 03 | 2 | 63 | 31.5 |

Write a pipeline computing the exact daily average **`150 / 5 = 30`**, without averaging the three hourly averages.

### Exercise 17 — Percentiles

Use **`$percentile`** (MongoDB 7.0+) to compute `p50` and `p95` of `temperatureC` per sensor. Why does daily `p95` not equal the average of hourly `p95`s?

### Exercise 18 — Materialized Summary

Create `sensor_hourly_stats` with a unique index on `sensorId + bucketStart`. Write an hourly grouping pipeline followed by **`$merge`** with `whenMatched: "replace"`, `whenNotMatched: "insert"`.

### Exercise 19 — Why Strip `$group` `_id` Before `$merge`?

Analyze the case where an existing summary has a MongoDB-generated `ObjectId` `_id`, while `$merge` input still retains a composite object `_id` from `$group`. What is the immutable `_id` risk?

### Exercise 20 — Late Arrivals

A `01:20` reading reaches the database at `04:05`, after the `01:00` summary was already built. Design an overlapping recompute schedule and explain why processing only the current hour produces wrong totals.

### Exercise 21 — All Raw Readings Deleted in a Bucket

The `02:00` summary already exists. Later, all raw readings for hour `02` are deleted. Does re-running `$group → $merge` with `replace` delete the old summary automatically? Propose a reconciliation mechanism.

### Exercise 22 — Timezone with DST

A dashboard in `America/New_York` groups by day and hour. Explain why a day can span 23 or 25 hours and why `HH` strings without offsets fail as unique keys.

### Exercise 23 — TTL and Backfills

Raw data is kept for 30 days, while business rules permit corrections after 45 days. What goes wrong? Propose a sound retention or archiving policy.

### Exercise 24 — Java Sync Driver

Write a Java aggregation using **`Filters.gte`/`lt`** on `ts`, **`$dateTrunc`** by hour, and **`$group`** computing averages. Return results as a list of `Document`s without materializing.

### Exercise 25 — Spring Data MongoDB

Use **`MongoTemplate.aggregate()`** combining `Aggregation.match` and a raw `Document` `AggregationOperation` for `$dateTrunc`. If entities use **`@Field`** to rename persisted fields, what must you watch out for?

### Exercise 26 — Multi-Tenant Aggregation

Two tenants both have a sensor named `"S-01"`. Design the group key and summary unique index so their readings never mix.

### Exercise 27 — Assessing Data Coverage

A sensor is expected every 5 minutes, yet an hour receives only 7 valid readings. Compute coverage and propose how the UI should indicate complete, partial, or unreliable data.

### Exercise 28 — Sizing `$densify`

A system has 100,000 sensors requiring 5-minute points over 24 hours. Calculate the theoretical row count and explain why you must never densify all sensors inside every HTTP request.

## 27. Review Questions

1. Which components does a time series collection use to organize measurements?
2. How does `metaField` differ from `timeField`?
3. Are storage buckets synonymous with hourly aggregation buckets?
4. Why store event time and ingestion time separately?
5. Why are half-open intervals `[start, end)` preferred for time filters?
6. What problem does `$dateTrunc` solve?
7. How are `binSize` and `unit` used to create 15-minute buckets?
8. When does `startOfWeek` matter?
9. Why does `$group` omit hourly buckets that have no raw readings?
10. Does `$avg` treat missing/null numeric fields as zero?
11. What do `$isNumber` and `validSampleCount` help ensure?
12. How does a `documents` window differ from a `range` window?
13. What bug does `$setWindowFields` `partitionBy` prevent?
14. Why append `$sort` at the end of a pipeline when ordered output is required?
15. What calculations use `$shift`?
16. Is an EMA over readings equivalent to an EMA over uniform time steps?
17. How do `$densify` and `$fill` differ in responsibility?
18. When is filling a missing bucket with `0` valid?
19. What misconception can linear interpolation cause?
20. Is the average of hourly averages always equal to the daily average?
21. Why retain `sum + count` when materializing summaries?
22. Can you compute daily percentiles by averaging hourly percentiles?
23. What unique index does `$merge` require when using custom `on` fields?
24. Why remove `$group`'s `_id` before `$merge` with `whenMatched: "replace"`?
25. Does `$merge` update all buckets atomically as a single transaction?
26. If a bucket loses all source readings, does `$merge` automatically remove its old summary?
27. How do late-arriving readings invalidate previously published numbers?
28. Is a watermark a field automatically maintained by MongoDB aggregations?
29. How do DST timezones affect day and hour boundaries?
30. When should you run raw aggregations vs. querying materialized summaries?
31. How do time series indexes, `metaField`, and `granularity` affect query performance?
32. What happens when raw TTL is shorter than the backfill SLA?
33. How does the Java Sync Driver pass BSON stages to `aggregate()`?
34. How can Spring Data use `AggregationOperation` for stages lacking typed builders?
35. Why check server version before using `$densify` or `$fill`?

## 28. Summary

Time series aggregation in MongoDB goes far beyond computing a simple mean. A sound statistical pipeline defines **time semantics, resolution, partitioning, data bounds, missing-value handling, and proper rollups**.

Three core patterns:

~~~text
FIXED / TUMBLING BUCKETS
  $match -> $dateTrunc -> $group
  Example: hourly averages.

SLIDING / ROLLING WINDOWS
  $setWindowFields
  Example: moving average, cumulative sum, previous reading.

MATERIALIZED SUMMARIES
  $match -> $group -> $project -> $merge
  Example: sensor_hourly_stats serving dashboards.
~~~

When spacing is irregular:

~~~text
Observed buckets
    |
    v
 $densify
    |
    v
Rows at missing timestamps
    |
    v
Controlled $fill
    |
    v
Window calculations on the time grid
~~~

Key takeaways:

1. **`$dateTrunc`** builds bucket keys using `unit`, `binSize`, `timezone`, and `startOfWeek`.
2. **`$group`** emits rows only for groups containing source documents; it does not synthesize empty intervals.
3. **`$setWindowFields`** enables rolling/cumulative calculations; **`documents` windows** differ from **time-`range` windows**.
4. **`$densify`** generates missing timestamps and **`$fill`** populates missing fields; never assume missing measurements equal `0`.
5. **Weighted averages** from raw measurements must divide total `sum` by total valid `count`, never averaging bucket averages.
6. **`$merge`** persists idempotent summaries with unique keys, yet neither auto-deletes stale buckets nor guarantees whole-batch atomicity.
7. **Late data, corrections, and TTL** demand planned recomputes, backfills, and reconciliation.
8. **Timezones and DST** are integral to business semantics for local daily/weekly reporting.
9. **`metaField`/`timeField` indexes, early filtering, output cardinality, and `allowDiskUse`** govern execution cost.
10. **Java Driver and Spring Data** build equivalent aggregation pipelines, subject to server-version compatibility.

### Official MongoDB References

- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — `timeField`, `metaField`, and storage buckets.
- [Best Practices for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — metadata, granularity, indexes, and ingest/query performance.
- [$dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — fixed time buckets, timezone, `startOfWeek`.
- [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — count/sum/min/max/average and accumulators.
- [$setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/) — documents/range windows, cumulative and moving statistics.
- [$shift](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shift/) — previous/next row access.
- [$expMovingAvg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/expMovingAvg/) — exponential moving average.
- [$densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/) — generating missing timestamp/numeric steps.
- [$fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/) — constant, `locf`, and linear interpolation.
- [$percentile](https://www.mongodb.com/docs/manual/reference/operator/aggregation/percentile/) — percentiles and computation methods.
- [$merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materialized outputs, `on` fields, and unique indexes.
- [MongoDB Java Sync Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — building and running pipelines in Java.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — `MongoTemplate`, `Aggregation`, and `AggregationOperation`.

When building a time series statistics system, start with the question: **"Which time interval, which measurements, and what level of data completeness does each number represent?"** From that answer, choose the right bucket/window, preserve coverage metadata, and design recomputable materializations. This keeps reports fast while remaining explainable and verifiable whenever late arrivals or corrections occur.
