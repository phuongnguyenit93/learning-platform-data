# Filling Gaps with `$densify`, `$fill`, and Support Requirements in MongoDB

## 1. Two Different Kinds of Gaps

In time-series or sequential data, "missing data" has two distinct meanings:

- **Missing an entire document at a point**: a sensor has records at 00:00 and 02:00, but no document at 01:00.
- **Document exists, but the value field is `null` or missing**: the 02:00 document exists with `temperature: null`.

MongoDB provides two aggregation stages tailored to these exact two problems:

| Stage | Purpose | What It Cannot Do Alone |
| --- | --- | --- |
| **`$densify`** | Generates additional documents for missing numeric or date points at the chosen step. | Does not estimate values for measurement fields like temperature or revenue. |
| **`$fill`** | Populates null/missing fields via constant value, LOCF, or linear interpolation. | Does not create documents at timestamps that do not yet exist. |

Example:

```text
Input data:
00:00 -> temperature = 10
01:00 -> no document
02:00 -> temperature = null
03:00 -> no document
04:00 -> temperature = 18

After hourly $densify:
00:00 -> 10
01:00 -> temperature field missing
02:00 -> null
03:00 -> temperature field missing
04:00 -> 18

After linear $fill:
00:00 -> 10
01:00 -> 12
02:00 -> 14
03:00 -> 16
04:00 -> 18
```

The values 12, 14, and 16 are **estimates**, not real measurements. Generated or interpolated data must be distinguished from raw observed data when used for monitoring, billing, reporting, or auditing.

> **Core rule:** If **timestamps/documents** are missing, use `$densify`. If **field values inside documents** are missing, use `$fill`. If both are missing, typically run `$densify` then `$fill`, with an explicit policy on how values are inferred.

## 2. Version Support Requirements in MongoDB

| Feature | First Version or Change | Significance |
| --- | --- | --- |
| `$densify` | MongoDB **5.1** | Generates missing numeric/Date slots. |
| `$fill` | MongoDB **5.3** | Fills null/missing values in a sequence. |
| `$locf` window expression | MongoDB **5.2** | Carries forward the most recent non-null value inside `$setWindowFields`. |
| `$linearFill` window expression | MongoDB **5.3** | Linear interpolation inside `$setWindowFields`. |
| `$densify` with equal bounds | **8.0** | `[x, x]` is an empty range; before 8.0 it could emit slot `x`. |
| `$fill` linear: same sort key across **different partitions** | **8.0.20** | Different partitions may share sort keys; duplicates within the same partition remain forbidden. |
| `$densify.field` sharing prefix with `partitionByFields` | **8.1** | Stricter validation throws an error on conflicting paths. |

Because `$fill` arrived in 5.3, **a 5.1 or 5.2 server cannot run a pipeline using both `$densify` and `$fill`**. The Java driver version does not compensate for server capabilities.

Check:

```javascript
db.version();
```

With appropriate privileges, you can inspect feature compatibility version (FCV):

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

In managed services, read server version/FCV from admin tooling rather than granting admin privileges to application accounts. Verify exact version details before deploying, especially when relying on 8.0, 8.0.20, or 8.1 behaviors.

## 3. Practice Dataset

Assume test collection `sensorReadings207` does not yet contain the IDs below:

```javascript
db.sensorReadings207.insertMany([
  {
    _id: "A-00",
    sensorId: "A",
    ts: ISODate("2026-11-14T00:00:00Z"),
    temperature: 10
  },
  {
    _id: "A-02",
    sensorId: "A",
    ts: ISODate("2026-11-14T02:00:00Z"),
    temperature: null
  },
  {
    _id: "A-04",
    sensorId: "A",
    ts: ISODate("2026-11-14T04:00:00Z"),
    temperature: 18
  },
  {
    _id: "A-06",
    sensorId: "A",
    ts: ISODate("2026-11-14T06:00:00Z"),
    temperature: 24
  },
  {
    _id: "B-01",
    sensorId: "B",
    ts: ISODate("2026-11-14T01:00:00Z"),
    temperature: 100
  },
  {
    _id: "B-03",
    sensorId: "B",
    ts: ISODate("2026-11-14T03:00:00Z"),
    temperature: 120
  },
  {
    _id: "B-06",
    sensorId: "B",
    ts: ISODate("2026-11-14T06:00:00Z"),
    temperature: 150
  }
]);
```

Initial data:

| Sensor | `ts` (UTC) | `temperature` |
| --- | --- | ---: |
| A | 00:00 | 10 |
| A | 02:00 | null |
| A | 04:00 | 18 |
| A | 06:00 | 24 |
| B | 01:00 | 100 |
| B | 03:00 | 120 |
| B | 06:00 | 150 |

**Missing-document** points: A lacks 01, 03, 05; B lacks 02, 04, 05; additionally, B has no observation at 00:00.

Inspect in deterministic order:

```javascript
db.sensorReadings207.find(
  {},
  { sensorId: 1, ts: 1, temperature: 1 }
).sort({ sensorId: 1, ts: 1 });
```

Re-running `insertMany` triggers duplicate `_id` errors; use an empty test collection and never drop production data just to run examples.

---

## 4. `$densify` Syntax

General form:

```javascript
{
  $densify: {
    field: "ts",
    partitionByFields: ["sensorId"],
    range: {
      step: 1,
      unit: "hour",
      bounds: "partition"
    }
  }
}
```

| Property | Required? | Meaning |
| --- | --- | --- |
| `field` | Yes | Field containing BSON Date or numeric values to densify. |
| `partitionByFields` | No | List of fields forming independent partitions. Omitting uses one global partition. |
| `range` | Yes | Slot-generation rules. |
| `range.step` | Yes | Arithmetic step between slots; must be a valid positive increment. |
| `range.unit` | Yes for Date; disallowed for numeric | Time unit. |
| `range.bounds` | Yes | `"full"`, `"partition"`, or `[lower, upper]`. |

### 4.1. Supported Date/Time Units

When the field is a Date, `unit` must be one of:

```text
millisecond, second, minute, hour, day,
week, month, quarter, year
```

When `unit` is set, `step` must be an **integer**. For numeric fields, omit `unit`; `step` can be any valid numeric increment.

```javascript
// Date: generate missing slots every 15 minutes.
{
  $densify: {
    field: "ts",
    range: {
      step: 15,
      unit: "minute",
      bounds: "partition"
    }
  }
}

// Numeric: generate missing sequence integers stepping by 1.
{
  $densify: {
    field: "sequence",
    range: {
      step: 1,
      bounds: "partition"
    }
  }
}
```

Do not pass `step: 0` or a negative step hoping to generate a descending series. To return descending results, generate slots with a positive step and append `$sort: { ts: -1 }` at the end.

---

## 5. `bounds: "partition"`: Densifying Within Each Group

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
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
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1
    }
  }
]);
```

`partitionByFields: ["sensorId"]` keeps A and B as two independent series.

With `"partition"`:

- Sensor A has observed span **00:00–06:00**.
- Sensor B has observed span **01:00–06:00**.

MongoDB generates the missing slots within each span:

```javascript
// Generated slots for A:
{ sensorId: "A", ts: ISODate("2026-11-14T01:00:00Z") }
{ sensorId: "A", ts: ISODate("2026-11-14T03:00:00Z") }
{ sensorId: "A", ts: ISODate("2026-11-14T05:00:00Z") }

// Generated slots for B:
{ sensorId: "B", ts: ISODate("2026-11-14T02:00:00Z") }
{ sensorId: "B", ts: ISODate("2026-11-14T04:00:00Z") }
{ sensorId: "B", ts: ISODate("2026-11-14T05:00:00Z") }
```

The synthesized documents above **do not have `temperature`**. Existing document A-02 with `temperature: null` stays as is; `$densify` never fills measurement fields.

Documents generated by `$densify` contain only the densified field and required partition keys; they do not automatically inherit `_id`, device metadata, measured values, or other fields from neighboring documents.

### 5.1. Does Not Collapse Multiple Readings in One Bucket

If a sensor reports twice at `01:10` and `01:40`, `$densify` does not merge them into a single `01:00` point. To report one slot per hour, bucket with `$dateTrunc` and aggregate per bucket before densifying.

### 5.2. `partition` Does Not Generate Slots Outside Observed Bounds

Because B has no data before 01:00, `bounds: "partition"` does not create B at 00:00. If a report requires the full 00–06 grid for every sensor, use `bounds: "full"` or explicit `[lower, upper]` bounds.

---

## 6. `bounds: "full"`: Shared Global Span

With multiple partitions, `"full"` uses the full min-to-max span of the densify field across the entire input set, generating slots in every partition across that shared span.

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "full"
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

On the sample data, the global span starts at **A 00:00** and ends at **06:00**. Thus B gets a generated 00:00 slot, unlike `bounds: "partition"`.

| Group | `partition` | `full` |
| --- | --- | --- |
| A | 00:00 to 06:00 | Shared span 00:00 to 06:00 |
| B | 01:00 to 06:00 | Shared span 00:00 to 06:00 |

**Do not confuse `"full"` with "up to now" or "up to end of reporting period."** It depends solely on the data entering the stage. If an earlier `$match` trims the input, the `"full"` span changes accordingly.

### 6.1. Risk of Generating Too Many Documents

With thousands of devices, if one device has years of history while another just came online, `bounds: "full"` expands the brand-new device across the entire multi-year span. That explodes generated document counts and can mislead readers: timestamps before a device existed are not "missing measurements."

Choose `"full"` only when comparing groups across an identical shared time axis is genuinely required, not merely out of convenience.

---

## 7. Explicit Bounds: `[lower, upper]`

You can specify explicit bounds:

```javascript
const start = ISODate("2026-11-14T00:00:00Z");
const end   = ISODate("2026-11-14T07:00:00Z");

db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: [start, end]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Key rules:

- Lower bound is **inclusive**: a slot at `start` can be generated.
- Upper bound is **exclusive**: a slot at `end` is not generated.
- Generation steps forward from the lower bound, independent of the earliest existing data point.
- Bound types must match the field type: Date for Date, numeric for numeric.
- **Source documents outside `bounds` are not automatically filtered out by `$densify`.**

With `[00:00, 07:00)` and a 1-hour step, generated slots cover 00, 01, 02, 03, 04, 05, 06. 07:00 is not generated because the upper bound is exclusive.

### 7.1. Add `$match` to Constrain Returned Scope

```javascript
db.sensorReadings207.aggregate([
  {
    $match: {
      ts: {
        $gte: start,
        $lt: end
      }
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: [start, end]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

If you need an observation immediately **before `start`** as an anchor for LOCF, do not `$match` so aggressively that you drop that anchor. Either extend the read window or fetch the prior anchor intentionally.

### 7.2. When Both Bounds Are Equal

```javascript
{
  $densify: {
    field: "sequence",
    range: {
      step: 1,
      bounds: [10, 10]
    }
  }
}
```

- **Starting in MongoDB 8.0**: this is an empty range; no documents are generated.
- **Before 8.0**: equal bounds could generate a document at 10 if none existed.

To generate a single slot reliably across versions, use a one-step interval like `[10, 11]` instead of depending on version-specific equal-bound behavior.

---

## 8. `$densify` with Numeric Fields

Sequential collection:

```javascript
db.sequence207.insertMany([
  { _id: "X1", channel: "X", seq: 1, value: 100 },
  { _id: "X3", channel: "X", seq: 3, value: 140 },
  { _id: "X5", channel: "X", seq: 5, value: 180 },
  { _id: "Y2", channel: "Y", seq: 2, value: 50 },
  { _id: "Y4", channel: "Y", seq: 4, value: 70 }
]);
```

Pipeline:

```javascript
db.sequence207.aggregate([
  {
    $densify: {
      field: "seq",
      partitionByFields: ["channel"],
      range: {
        step: 1,
        bounds: "partition"
      }
    }
  },
  {
    $sort: {
      channel: 1,
      seq: 1
    }
  }
]);
```

Added documents:

```javascript
{ channel: "X", seq: 2 }
{ channel: "X", seq: 4 }
{ channel: "Y", seq: 3 }
```

Omit `unit` because `seq` is numeric, not a Date.

### 8.1. Fractional Steps

With `step: 0.1`, Double values can suffer binary floating-point rounding drift. When exact decimal steps or exact slot keys are critical, use integer-scaled units or Decimal128 as appropriate and test on your target version. Never combine wide bounds with tiny steps: generated document volume will explode.

---

## 9. Limitations of `$densify`

### 9.1. Data Types

The densified field must contain valid numeric or Date values. If it is Date without `unit`, the stage errors. If it is numeric with `unit`, the stage also errors. Never assume ISO date strings are auto-converted into BSON Dates.

Documents missing the densify field pass through unchanged; the stage cannot invent a timestamp for a document that lacks one.

### 9.2. Partition Fields

Field names in `partitionByFields` must be valid field names not starting with `$`. `field` also must not start with `$`.

**Starting in MongoDB 8.1**, if `field` matches or shares a prefix with any field in `partitionByFields`, the stage errors—for example:

```javascript
// Conflicting path starting in MongoDB 8.1:
{
  $densify: {
    field: "timestamp",
    partitionByFields: ["timestamp.hours"],
    range: {
      step: 1,
      unit: "hour",
      bounds: "partition"
    }
  }
}
```

Solution: keep the densified field (`timestamp`) separate from partition identifier fields (`sensorId`, `siteId`).

### 9.3. Generated Document Cap

MongoDB caps documents generated by `$densify` via the server parameter `internalQueryMaxAllowedDensifyDocs`. Per official documentation, the default cap is **500,000 generated documents**; exceeding it throws an error.

Do not treat raising this internal parameter as your first fix. Changing it depends on admin/managed-service permissions and **does not eliminate the CPU, RAM, I/O, and network cost** of generating huge document counts. Prefer shrinking the time range, coarsening `step`, batching, and reducing partition count.

### 9.4. Output Order

`$densify` **does not guarantee sorted output**. If downstream consumers expect order, add an explicit `$sort` or an appropriate `sortBy` in `$fill`. If an API expects ascending timestamps, place `$sort` at the end of the pipeline.

---

## 10. `$fill` Syntax

`$fill` populates `null` or missing fields in documents flowing through the pipeline:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "linear" },
      status: { method: "locf" },
      requestCount: { value: 0 }
    }
  }
}
```

| Property | Requirement | Effect |
| --- | --- | --- |
| `output` | Required | Fields to populate. |
| `output.<field>.value` | One option | Fills using a constant or aggregation expression. |
| `output.<field>.method` | One option | Accepts only `"linear"` or `"locf"`. |
| `sortBy` | Required when using `method` | Order used to locate preceding/following values. |
| `partitionBy` | Optional | Expression defining the partition key. |
| `partitionByFields` | Optional | List of fields defining the partition key. |

`partitionBy` and `partitionByFields` **cannot be used together**. Omitting both treats all documents as **one partition**, risking mixing data across different devices.

### 10.1. `$fill` Does Not Create New Documents

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  }
]);
```

This pipeline fills existing A-02 (which had `temperature: null`), but **does not create A-01, A-03, or A-05**. You need `$densify` if those slots must exist.

### 10.2. `$fill` Only Replaces Null/Missing Values

A field that already holds a non-null value like `temperature: 18` is preserved and never overwritten by interpolation. To recompute all values via a formula, use `$set`/`$project` with explicit logic rather than `$fill`.

---

## 11. Constant Fill: `output.<field>.value`

When the domain defines missing fields as **zero activity**, filling with 0 makes sense.

```javascript
db.dailySales207.insertMany([
  {
    _id: 1,
    day: ISODate("2026-11-01T00:00:00Z"),
    bootsSold: 12,
    sandalsSold: 5
  },
  {
    _id: 2,
    day: ISODate("2026-11-02T00:00:00Z"),
    sandalsSold: 9
  },
  {
    _id: 3,
    day: ISODate("2026-11-03T00:00:00Z"),
    bootsSold: null
  }
]);
```

Pipeline:

```javascript
db.dailySales207.aggregate([
  {
    $fill: {
      output: {
        bootsSold: { value: 0 },
        sandalsSold: { value: 0 }
      }
    }
  },
  {
    $sort: { day: 1 }
  }
]);
```

Result:

```text
01/11: bootsSold=12, sandalsSold=5
02/11: bootsSold=0,  sandalsSold=9
03/11: bootsSold=0,  sandalsSold=0
```

With `value: 0`, `sortBy` is not required because constant replacement does not depend on document order.

### 11.1. `value` Can Be an Expression

```javascript
{
  $fill: {
    output: {
      discount: { value: "$defaultDiscount" }
    }
  }
}
```

When `discount` is missing or null, the expression supplies the fallback value. Ensure `defaultDiscount` is validated and permitted by business rules.

### 11.2. Zero Is Not the Same as Missing

- `value: 0`: may be a valid measured zero.
- `value: null`: no useful measurement available.
- Missing `value` field: record may be incomplete.

Filling 0 for offline sensor readings can trigger false alarms, skew averages, or hide ingestion outages. Fill 0 only when **the business confirms no record means quantity zero**.

---

## 12. LOCF — `method: "locf"`

**Last Observation Carried Forward** propagates the most recent prior non-null value within each partition ordered by `sortBy`.

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "locf" }
      }
    }
  },
  {
    $sort: { sensorId: 1, ts: 1 }
  }
]);
```

On A's existing documents:

```text
00:00 -> 10
02:00 -> null  => 10 (carried from 00:00)
04:00 -> 18
06:00 -> 24
```

01:00 still does not exist because `$fill` creates no documents. Placing `$densify` before this stage allows LOCF to fill synthesized slots as well.

### 12.1. No Prior Observation

If the start of a partition is null/missing, there is no prior value to carry forward, so leading slots remain null. If an entire partition has no valid values, LOCF cannot invent one.

### 12.2. LOCF Can Make Stale Data Look Fresh

Suppose a sensor reports 25°C at 00:00 and then goes offline for two weeks. Densifying up to the present and running LOCF displays 25°C continuously for two weeks—an **unreliable assumption** for temperature.

To cap how long an old value stays valid, enforce a policy like `maxStalenessMinutes` by tracking the age of the latest real observation. `$fill` does not reject stale values automatically.

### 12.3. Avoid Mixing Partitions

With multiple sensors or tenants, always partition by full source identity, e.g., `tenantId`, `siteId`, `sensorId`. Missing a partition key causes sensor A's LOCF value to bleed into sensor B, corrupting results.

---

## 13. Linear — `method: "linear"`

**Linear interpolation** uses non-null values on both sides to estimate missing points in between.

Evenly spaced sequence:

```text
0 -> 10
1 -> null
2 -> null
3 -> null
4 -> 18
```

Total change from 10 to 18 is 8 across four steps:

```text
1 -> 10 + 8 × 1/4 = 12
2 -> 10 + 8 × 2/4 = 14
3 -> 10 + 8 × 3/4 = 16
```

Pipeline:

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  }
]);
```

On raw data, A-02 is filled with **14**, halfway between A-00=10 and A-04=18. Since A-01 and A-03 have no documents yet, no values are produced there.

### 13.1. Interpolates Only When Bracketed by Anchors

If a null sits at the beginning or end of a partition without both a preceding and following value, linear does not extrapolate.

```text
Input:
0 -> null
1 -> 10
2 -> null
3 -> 18
4 -> null

After linear:
0 -> null
1 -> 10
2 -> 14
3 -> 18
4 -> null
```

Forecasting before the first point or after the last point is **extrapolation**, which requires a separate model/method, not linear `$fill`.

### 13.2. Critical `sortBy` Rules

When using `linear`:

1. **`sortBy` is required.**
2. `sortBy` must contain **exactly one field**.
3. **No two documents in the same partition may share the same `sortBy` value**.

Invalid:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: {
      ts: 1,
      _id: 1
    },
    output: {
      temperature: { method: "linear" }
    }
  }
}
```

Even though appending `_id` is normally great for deterministic sorting, linear forbids two sort fields. Normalize the data to **one document per timestamp per partition** via aggregation or explicit deduplication before running linear.

### 13.3. Identical Sort Keys Across Different Partitions

A and B may share timestamps. Per MongoDB documentation, **starting in 8.0.20**, linear permits different partitions to share the same sort key. Older versions may error in that scenario. Within the **same partition**, duplicate sort keys remain disallowed.

### 13.4. Irregular Timestamps and Interpolated Values

Linear fill computes over the ordered sequence of documents and their `sortBy` coordinates surrounded by valid anchors. When timestamps are irregular, verify that MongoDB's linear interpolation matches the exact **elapsed-time weighting** required by your domain.

For example, suppose 00:00 = 10, 09:00 = null, 10:00 = 20. If the target is an **hourly evenly spaced** series, densify to an hourly grid before filling.

### 13.5. Do Not Interpolate Categorical Data

`status: "ON"/"OFF"`, `paymentState`, `deviceMode`, or string fields have no arithmetic midpoint. LOCF may make sense for persistent state flags, whereas linear interpolation makes no business sense.

---

## 14. Complete Pipeline: `$densify` Followed by `$fill`

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1
    }
  }
]);
```

Expected calculated results:

| Sensor | UTC Slot | Temperature | Data Type |
| --- | --- | ---: | --- |
| A | 00:00 | 10 | Original observation |
| A | 01:00 | 12 | Generated slot, interpolated value |
| A | 02:00 | 14 | Original doc had null, now interpolated |
| A | 03:00 | 16 | Generated slot, interpolated value |
| A | 04:00 | 18 | Original observation |
| A | 05:00 | 21 | Generated slot, interpolated value |
| A | 06:00 | 24 | Original observation |
| B | 01:00 | 100 | Original observation |
| B | 02:00 | 110 | Generated slot, interpolated value |
| B | 03:00 | 120 | Original observation |
| B | 04:00 | 130 | Generated slot, interpolated value |
| B | 05:00 | 140 | Generated slot, interpolated value |
| B | 06:00 | 150 | Original observation |

Between A04=18 and A06=24 there is one missing slot, so A05 = (18+24)/2 = 21. Between B03=120 and B06=150 there are two missing slots, so B04=130 and B05=140.

**Never pass these estimated values off as real observations in reports requiring raw measurements.** Attach provenance flags when exporting results.

### 14.1. Switching to LOCF

Replace the fill stage with:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

Then:

```text
A01=10, A02=10, A03=10, A05=18
B02=100, B04=120, B05=120
```

Choose linear, LOCF, or 0 based on **data semantics**, never merely because you want "a chart with no gaps."

---

## 15. Tracking Provenance of Synthetic Data

Without provenance flags, an interpolated 12 at A01 looks identical to a real measurement. Tag input documents before `$densify`:

```javascript
db.sensorReadings207.aggregate([
  {
    $set: {
      wasObserved: true,
      hadValue: {
        $ne: [
          { $ifNull: ["$temperature", null] },
          null
        ]
      }
    }
  },
  {
    $densify: {
      field: "ts",
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
      wasObserved: {
        $ifNull: ["$wasObserved", false]
      },
      hadValue: {
        $ifNull: ["$hadValue", false]
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $set: {
      valueWasFilled: {
        $and: [
          { $not: ["$hadValue"] },
          { $ne: ["$temperature", null] }
        ]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1,
      wasObserved: 1,
      valueWasFilled: 1
    }
  }
]);
```

How to read the flags:

- `wasObserved: true`: document existed in the input.
- `wasObserved: false`: document was generated by densify.
- `valueWasFilled: true`: value was initially null/missing and became populated after fill.
- A-02 has `wasObserved: true`, `valueWasFilled: true`.
- A-01 has `wasObserved: false`, `valueWasFilled: true`.

If linear lacks enough anchors, the value stays null and `valueWasFilled` stays false—avoiding falsely marking an unfilled slot as "interpolated."

In real systems, inputs with NaN, Infinity, bad strings, or out-of-schema types need dedicated validation; `!= null` alone does not prove a valid measurement.

---

## 16. `partitionBy` vs. `partitionByFields` in `$fill`

There are two ways to specify partitions.

### 16.1. Field List

```javascript
{
  $fill: {
    partitionByFields: ["tenantId", "sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

Each `(tenantId, sensorId)` combination forms an independent series. Use this when partitioning fields already exist directly on documents.

### 16.2. Expression

```javascript
{
  $fill: {
    partitionBy: {
      tenant: "$tenantId",
      sensor: "$sensorId"
    },
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

`partitionBy` accepts any expression constructing a partition key, not just a list of field names. Never specify **both `partitionBy` and `partitionByFields`** in the same `$fill`.

**Difference from `$densify`:** `$densify` uses `partitionByFields` and does not offer the same `partitionBy` expression option. To partition `$densify` on a computed key, materialize that key with `$set` before densifying.

---

## 17. Preserving the Original Field with `$setWindowFields`

`$fill` overwrites the field named in `output` directly. To keep the original measurement untouched and add **two estimated columns** for comparison, use:

```javascript
db.sensorReadings207.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: { ts: 1 },
      output: {
        linearTemperature: {
          $linearFill: "$temperature"
        },
        carriedTemperature: {
          $locf: "$temperature"
        }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

- `$linearFill` and `$locf` are **window expressions**, not the `$fill` stage.
- They are valid only inside `$setWindowFields` under each operator's rules.
- The output field name can differ from the source field—e.g., `linearTemperature` alongside `temperature`.
- Remember `$linearFill`'s sorting and uniqueness requirements.

If missing slots must also be generated beforehand, place `$densify` before `$setWindowFields` instead of `$fill`.

| Goal | Tool |
| --- | --- |
| Generate missing 01:00 document | `$densify` |
| Fill nulls directly inside `temperature` | `$fill` |
| Add `temperatureLinear` while keeping original `temperature` | `$setWindowFields` + `$linearFill` |
| Add a separate `temperatureLocf` field | `$setWindowFields` + `$locf` |
| Uniform grid plus multiple estimation columns | `$densify` + window expressions or `$fill` as needed |

---

## 18. Normalizing Timestamps and Deduplicating Before Linear Fill

Raw sensors may emit two readings within the same hour:

```javascript
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:10:00Z"),
  temperature: 10
}
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:40:00Z"),
  temperature: 12
}
```

If a report expects one point at **01:00**, `$densify` will not collapse 01:10 and 01:40 into a single 01:00 bucket.

Typical pipeline:

```javascript
db.rawSensorReadings.aggregate([
  {
    $set: {
      hourStart: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensorId",
        hour: "$hourStart"
      },
      temperature: {
        $avg: "$temperature"
      },
      sampleCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      ts: "$_id.hour",
      temperature: 1,
      sampleCount: 1
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Flow:

```text
Raw events
   |
   v
$dateTrunc: snap timestamps to hour boundaries
   |
   v
$group: collapse readings per sensor + hour
   |
   v
$densify: generate missing hours
   |
   v
$fill: interpolate missing values
   |
   v
$sort: set output order
```

`$avg` is merely an **illustrative aggregation rule**. For cumulative counters or device states, averaging may be wrong; you may need the latest reading by timestamp, a sum, min/max, or another rule.

Never apply `$first` on unsorted data and assume it picks "the latest reading." If duplicate timestamps come from retries, define deduplication using event IDs or versions.

---

## 19. Daily Revenue Series with `$densify` and `$fill: 0`

Sales event data:

```javascript
db.salesEvents207.insertMany([
  {
    _id: "S1",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-01T05:00:00Z"),
    amountMinor: 120000
  },
  {
    _id: "S2",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-01T12:00:00Z"),
    amountMinor: 80000
  },
  {
    _id: "S3",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-03T09:00:00Z"),
    amountMinor: 300000
  }
]);
```

Revenue report from 01/11 through 04/11 UTC:

```javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end   = ISODate("2026-11-05T00:00:00Z");

db.salesEvents207.aggregate([
  {
    $match: {
      occurredAt: {
        $gte: start,
        $lt: end
      }
    }
  },
  {
    $set: {
      day: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        shopId: "$shopId",
        day: "$day"
      },
      revenueMinor: {
        $sum: "$amountMinor"
      },
      transactionCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      shopId: "$_id.shopId",
      day: "$_id.day",
      revenueMinor: 1,
      transactionCount: 1
    }
  },
  {
    $densify: {
      field: "day",
      partitionByFields: ["shopId"],
      range: {
        step: 1,
        unit: "day",
        bounds: [start, end]
      }
    }
  },
  {
    $fill: {
      output: {
        revenueMinor: { value: 0 },
        transactionCount: { value: 0 }
      }
    }
  },
  {
    $sort: {
      shopId: 1,
      day: 1
    }
  }
]);
```

Expected output:

| Date | Revenue (minor units) | Transactions |
| --- | ---: | ---: |
| 01/11 | 200000 | 2 |
| 02/11 | 0 | 0 |
| 03/11 | 300000 | 1 |
| 04/11 | 0 | 0 |

Filling 0 is valid only when source completeness and cutoff timing guarantee that no events means zero transactions. If ingestion lagged or events arrived late, a missing day **does not guarantee zero revenue**. Financial reports need period-close and reconciliation workflows.

### 19.1. Partitions That Never Appeared

If SHOP-2 has zero documents in the input, `$densify` has no way to know SHOP-2 exists. To cover **every store including stores with zero events**, supply the store/partition roster from a reference collection or build a separate calendar grid.

---

## 20. Calendars, Timezones, and Non-Standard Timestamps

BSON Date stores an **instant in time**; "each day" is a **calendar and timezone** concept.

For instance, a store's business day in Vietnam rarely aligns with UTC days:

```javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

This aligns events to day buckets in the business timezone. Bounds passed to `$densify` must match those actual Date boundaries—never hardcode UTC midnight when business days use local time.

In regions observing daylight saving time (DST), a calendar day can be 23 or 25 hours long. Calendar-aware `unit: "day"` behaves differently from blindly adding `86,400,000` milliseconds. Test DST transitions if your app operates in DST timezones.

### 20.1. Does Not Snap 10:17 to 10:00

If data arrives at 10:17 and 12:17, `$densify` does not snap them to 10:00 and 12:00. To build an on-the-hour grid, run `$dateTrunc` and `$group` first.

### 20.2. `linear` After Densify Is Still an Assumption

On a 1-minute grid, two readings 10 minutes apart with 9 missing slots get linearly interpolated evenly; that can look fine for visualization. Still, define a **maximum gap threshold** before allowing interpolation, especially for physical devices whose readings can jump abruptly.

---

## 21. Performance and Document Generation Limits

Suppose:

```text
500 sensors
30 days
24 hours/day
60 minutes/hour
```

Potential slots:

```text
500 × 30 × 24 × 60 = 21,600,000 slots
```

This is the theoretical slot count **before subtracting existing documents**. If most slots are absent, `$densify` tries to generate millions of documents, exceeding the default 500,000 cap and failing.

### 21.1. Ways to Bound Cost

1. `$match` early by `sensorId` and the required time window.
2. Pick an appropriate granularity: 5 minutes, 15 minutes, 1 hour, or 1 day.
3. Process reports in smaller time or partition batches.
4. Densify only the entities the user requested.
5. Avoid `"full"` when one partition has a much longer history than others.
6. Keep an appropriate index for the leading `$match`.
7. For recurring dashboards, consider controlled materialized reporting series.
8. Check returned document counts, BSON sizes, latency, and driver memory.

`allowDiskUse` helps memory-heavy operations spill when supported, yet **it does not lift the `$densify` generated-document limit**.

### 21.2. Every Stage Has a Cost

- `$group` may read and aggregate large volumes of raw events.
- `$densify` can multiply intermediate document counts thousandfold.
- `$fill` must process partitions in order, especially for interpolation.
- Trailing `$sort` may sort the expanded stream.
- The Java driver must fetch, decode, and map results, potentially slowing APIs.

Consequently, a collection with only a few thousand source documents can still produce a huge response after densify.

### 21.3. Indexing the Source Read Path

When queries routinely filter by sensor and time:

```javascript
db.sensorReadings207.createIndex({
  sensorId: 1,
  ts: 1
});
```

This index helps the `$match` before densify. It **does not remove the cost of generating documents or interpolating**.

Inspect the pipeline with:

```javascript
db.sensorReadings207.explain("executionStats").aggregate([
  {
    $match: {
      sensorId: "A",
      ts: {
        $gte: ISODate("2026-11-14T00:00:00Z"),
        $lt: ISODate("2026-11-14T07:00:00Z")
      }
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  }
]);
```

Beyond `IXSCAN`/`COLLSCAN`, examine post-stage document counts, execution time, and output size. Explain output varies across MongoDB versions.

---

## 22. Read-Only Results or Persisting Output?

Aggregations with `$densify`/`$fill` **do not mutate source data** by default. They generate transient results flowing through the pipeline.

```javascript
db.sensorReadings207.aggregate([
  // Stages producing the reporting series...
]);
```

does not insert slot A-01 into the collection.

If you need to **materialize** results for dashboards, design a target collection with an explicit schema, unique key, and late-arrival update policy. For example, key `(sensorId, ts)`:

```javascript
db.denseReadings207.createIndex(
  {
    sensorId: 1,
    ts: 1
  },
  {
    unique: true
  }
);
```

Writing with `$merge` requires choosing `on`, `whenMatched`, `whenNotMatched`, and `_id` handling carefully—not just slapping a write stage onto an experimental pipeline.

With late-arriving source data, values interpolated today may need recalculation tomorrow. **Never overwrite real observed data with interpolated values** without preserving provenance and recomputability.

Example reporting record:

```javascript
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:00:00Z"),
  temperature: 12,
  origin: "synthetic",
  fillMethod: "linear"
}
```

A document like this must clearly be understood as an **analytical value**, not as the sensor having actually reported 12.

---

## 23. Using the MongoDB Java Sync Driver

Stages can be built with `org.bson.Document` to mirror `mongosh` syntax closely:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public final class DenseSensorService {

    public static void showSeries(
            MongoCollection<Document> readings,
            String sensorId
    ) {
        Bson match = new Document(
            "$match",
            new Document("sensorId", sensorId)
        );

        Document range = new Document("step", 1)
            .append("unit", "hour")
            .append("bounds", "partition");

        Bson densify = new Document(
            "$densify",
            new Document("field", "ts")
                .append("partitionByFields", List.of("sensorId"))
                .append("range", range)
        );

        Bson fill = new Document(
            "$fill",
            new Document("partitionByFields", List.of("sensorId"))
                .append("sortBy", new Document("ts", 1))
                .append(
                    "output",
                    new Document(
                        "temperature",
                        new Document("method", "linear")
                    )
                )
        );

        Bson sort = new Document(
            "$sort",
            new Document("sensorId", 1)
                .append("ts", 1)
        );

        List<Bson> pipeline = Arrays.asList(
            match,
            densify,
            fill,
            sort
        );

        readings.aggregate(pipeline).forEach(
            document -> System.out.println(document.toJson())
        );
    }
}
```

This runs on servers supporting `$densify` and `$fill` (MongoDB 5.3+ for both). Never call these stages against an older server expecting the driver to emulate them.

### 23.1. Passing Explicit Bounds as BSON Date

```java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;

Date start = Date.from(
    Instant.parse("2026-11-14T00:00:00Z")
);

Date end = Date.from(
    Instant.parse("2026-11-14T07:00:00Z")
);

Document dateRange = new Document("step", 1)
    .append("unit", "hour")
    .append("bounds", List.of(start, end));
```

Do not pass ISO strings instead of `Date` expecting `$densify` to cast them. Validate `start < end`, cap reporting spans, sensor counts, and granularity before dispatching the pipeline.

### 23.2. Choosing DTOs Compatible with Synthesized Documents

Documents generated by `$densify` lack `_id`, device metadata, and `temperature` before fill. A Java model assuming every field is non-null may fail deserialization.

Read as `Document` or map into a reporting DTO with nullable fields and provenance flags. Because linear fill can still leave leading/trailing nulls, avoid primitive `double` for fields that may be null or missing.

### 23.3. Avoid Materializing Millions of Documents in RAM

```java
// Unsuitable for pipelines with huge results:
readings.aggregate(pipeline)
    .into(new java.util.ArrayList<>());
```

If an endpoint only needs one report page, bound input spans and stream/batch appropriately. Avoid `println` per document during benchmarks since console I/O skews latency measurements significantly.

---

## 24. Two Applied Scenarios

### 24.1. Device Downtime Reporting

Heartbeat data:

```text
12:00 heartbeat present
12:01 missing document
12:02 missing document
12:03 heartbeat present
```

`$densify` generates 12:01 and 12:02. Flag source records with `wasObserved: true` before densify, then default new records to false:

```javascript
{
  $set: { wasObserved: true }
},
{
  $densify: {
    field: "ts",
    partitionByFields: ["deviceId"],
    range: {
      step: 1,
      unit: "minute",
      bounds: "partition"
    }
  }
},
{
  $set: {
    heartbeatPresent: {
      $ifNull: ["$wasObserved", false]
    }
  }
}
```

Result:

```text
12:00 heartbeatPresent=true
12:01 heartbeatPresent=false
12:02 heartbeatPresent=false
12:03 heartbeatPresent=true
```

Here `false` means **no record existed in the dataset**, not necessarily that the device lost power—it could be a network drop or ingestion delay. Never use LOCF to turn missing slots into `heartbeat=true`, as that hides outages.

### 24.2. Inventory Snapshot State

Each inventory change is an event:

```javascript
{
  sku: "P100",
  warehouseId: "W1",
  changedAt: ISODate("2026-11-14T08:00:00Z"),
  onHandAfterChange: 42
}
```

To build hourly snapshots, LOCF is appropriate if the system records **every inventory change event** and no new event means stock stayed constant. By contrast, linear fill would invent fractional/intermediate stock levels that never existed.

Normalize by `(warehouseId, sku)`, pick the latest event within each hour deterministically, densify missing hours, and apply LOCF. If event history is incomplete, even LOCF can be inaccurate.

---

## 25. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `$densify` does not create on-the-hour slots | Raw timestamp 10:17 was not bucketed | Run `$dateTrunc`/`$group` before densify. |
| Date `$densify` throws error | Missing `unit` or wrong field type | Use BSON Date and specify `unit`. |
| Numeric `$densify` throws error | Specified `unit` or mixed field types | Omit `unit`, validate numeric values. |
| Documents outside bounds still appear | `bounds` controls generation only | Add `$match` for the reporting window. |
| `$densify` returns unsorted documents | Stage does not guarantee output order | Add trailing `$sort`. |
| `$fill` does not create missing dates | `$fill` never creates documents | Run `$densify` first. |
| `$fill` mixes tenant A into tenant B | Partition lacks distinguishing keys | Partition by full entity identity. |
| Linear `$fill` rejects multi-field `sortBy` | Linear allows only one sort field | Normalize to a single unique time key. |
| Linear `$fill` fails on duplicate timestamps | Duplicates inside the same partition | Deduplicate or aggregate inputs first. |
| Leading/trailing nulls unchanged by linear | Missing anchors on both sides | Accept null or apply another policy. |
| Leading LOCF slots stay null | No prior value exists | Supply a valid prior anchor if appropriate. |
| Pipeline errors generating too many docs | Long span, tiny step, many partitions | Narrow range, batch, coarsen granularity. |
| Report shows all 0s even when sensor failed | Misleading zero fill | Distinguish missing from measured zero. |
| Path error starting in MongoDB 8.1 | `field` shares prefix with partition path | Use independent field paths. |
| Behavior differs across patch versions | `[x,x]` change in 8.0 or linear in 8.0.20 | Check server version and release docs. |

### 25.1. Do Not Put Two Sort Fields on Linear Fill

```javascript
// Invalid with method "linear":
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1, _id: 1 },
    output: {
      temperature: { method: "linear" }
    }
  }
}
```

There is no "just add `_id` to be safe" here. Determine why one sensor has duplicate `ts` documents and apply an explicit aggregation/deduplication rule first.

### 25.2. Cannot Invent Partitions Missing from Source Input

If a tenant has zero records entering the stage, there is no key to synthesize a time series for that tenant. To report all tenants including inactive ones, merge against a reference tenant list and calendar grid.

---

## 26. Practice Exercises and Answers

### Exercise 1 — Missing Slots vs. Missing Values

Input:

```javascript
[
  { seq: 0, value: 10 },
  { seq: 2, value: null },
  { seq: 4, value: 18 }
]
```

**Question:** What does `$densify` with step 1 create? What values does linear fill give for slots 1, 2, 3?

**Answer:** Creates documents at 1 and 3; slot 2 already existed. Linear fills 12, 14, and 16 respectively.

### Exercise 2 — Leading Null with LOCF

```text
0 -> null
1 -> 10
2 -> null
3 -> null
4 -> 18
5 -> null
```

**Answer:** `null, 10, 10, 10, 18, 18`. Slot 0 has no prior observation so it remains null.

### Exercise 3 — Linear Does Not Extrapolate

```text
0 -> null
1 -> 10
2 -> null
3 -> 20
4 -> null
```

**Answer:** `null, 10, 15, 20, null`.

### Exercise 4 — Exclusive Upper Bound

```javascript
range: {
  step: 1,
  bounds: [2, 5]
}
```

**Answer:** Slots generated in range are 2, 3, 4; 5 is exclusive. Densify does not drop source documents outside the bounds.

### Exercise 5 — `partition` vs. `full`

```text
A: seq 1, 3
B: seq 2, 4
```

Step 1. **Question:** Which extra slots can `"full"` generate compared to `"partition"`?

**Suggested answer:** `"full"` spans the global range 1–4, so it can generate slot 1 for B and slot 4 for A; `"partition"` uses each group's own min–max span.

### Exercise 6 — Duplicate Timestamps

A sensor has two documents with the same `ts`, and linear fails. **How do you fix it?**

**Hint:** Determine whether they are retry duplicates, two valid readings, or distinct versions. Deduplicate or `$group` by `(sensorId, ts)` using an approved business rule before interpolating.

### Exercise 7 — Revenue Reporting

A shop has 500k VND revenue on 01/11 and 700k on 03/11; 02/11 had no transactions and data is finalized.

**Hint:** Filling 0 for 02/11 is right, whereas linear 600k or LOCF 500k would fabricate revenue that never happened.

### Exercise 8 — Choosing Partitions

You have `tenantId`, `warehouseId`, and `sku`. Inventory snapshots must stay isolated per SKU in each warehouse of each tenant.

**Answer:** Partition by all three fields. Partitioning only by `sku` mixes inventory across tenants and warehouses.

### Exercise 9 — Sizing the Expansion

1,000 devices, 24 hours, one slot per minute:

```text
1,000 × 24 × 60 = 1,440,000 slots
```

If most slots are missing, densify can exceed the 500,000-document default cap. Narrow the span, batch, or coarsen granularity.

### Exercise 10 — Versions

Does MongoDB 5.2 support both `$densify` and `$fill`?

**Answer:** It has `$densify` (5.1+), but **does not yet have the `$fill` stage** (5.3+). Upgrade the server or implement filling with operators supported on your version.

### Exercise 11 — Provenance of Interpolation

A02 is an original document with `temperature: null`, filled linearly to 14. A01 is a newly generated document filled to 12.

**Question:** Do both have the same data provenance?

**Answer:** No. A02 had a source document with null; A01 had no source document. Track at least `wasObserved` and `valueWasFilled` to distinguish them accurately.

### Exercise 12 — `$fill` Alone

Sensor A has 00:00=10 and 04:00=18, **with no documents for 01–03**. Will running linear `$fill` directly create 01/02/03?

**Answer:** No. Intermediate documents must exist first; run `$densify` beforehand or generate the grid another way.

---

## 27. Pre-Deployment Checklist

1. Is the data missing **documents** or missing **field values**?
2. Is the densified field numeric or BSON Date, and are wrong-typed strings/nulls excluded?
3. Does server version/FCV support `$densify`, `$fill`, and the relied-upon edge behaviors?
4. Do partitions fully isolate tenant, sensor, site, or entity IDs?
5. Are there duplicate sort keys inside any partition?
6. Do `step` and `unit` match the intended measurement interval?
7. Should bounds be `partition`, `full`, or explicit `[lower, upper)`, keeping upper exclusive in mind?
8. Should timestamps be bucketed with `$dateTrunc` and aggregated with `$group` before densifying?
9. Do leading/trailing anchors exist if LOCF or linear is expected to fill edges?
10. Per **domain rules**, should missing values stay null, become 0, use LOCF, or use linear?
11. Is there a maximum missing-gap limit beyond which interpolation is disallowed?
12. Are flags kept to distinguish observed, synthetic, and filled values?
13. Have you budgeted slot counts per partition to stay safely below the 500,000 generated-document cap?
14. Are early `$match` filters and indexes in place for the read path?
15. Are results returned transiently or persisted, and how are late-arriving records handled?
16. Do Java DTOs tolerate `null` values and documents missing `_id`?
17. Is a trailing `$sort` included whenever the API expects ordered output?
18. When benchmarking, did you account for generated document count and response size?

Deployment flow:

```text
Raw events
   |
   v
Validate types and partition keys
   |
   v
$dateTrunc + $group if bucketing/dedup needed
   |
   v
$match by entity and target time window
   |
   v
Tag source documents
   |
   v
$densify to create missing slots
   |
   v
$fill per business policy
   |
   v
Flag estimated values
   |
   v
$sort / $project
   |
   v
API response or materialized reporting series
```

---

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`$densify` guesses temperature values." | It creates documents at missing slots; `$fill` or other logic populates values. |
| "`$fill` creates dates that lack documents." | It only fills fields in existing documents. |
| "`$densify` is the same as `$dateTrunc`." | `dateTrunc` snaps to buckets; `densify` generates missing slots. |
| "`$densify` is the same as `$group`." | It does not aggregate multiple raw events sharing a bucket. |
| "`bounds: full` always extends to now." | It depends on the min/max present in stage input. |
| "`bounds: partition` aligns all sensors to the same span." | Each partition uses its own observed min–max span. |
| "The upper bound is inclusive." | The upper bound is exclusive. |
| "Densify filters out documents outside explicit bounds." | No; add an explicit `$match`. |
| "Densify guarantees sorted output." | No; add an explicit `$sort`. |
| "Date densify doesn't need `unit`." | Date fields require `range.unit`. |
| "Numeric densify should also have `unit`." | Numeric fields forbid `unit`. |
| "`$fill` removes all nulls." | Linear/LOCF leave nulls when required anchors are missing. |
| "Linear allows multiple `sortBy` fields." | No, only a single sort field. |
| "Linear allows duplicate timestamps in the same partition." | No; duplicates cause an error. |
| "Duplicate timestamps across different partitions always error." | Behavior changed starting in MongoDB 8.0.20. |
| "LOCF is valid for all data types." | It can carry stale values forward and mask outages. |
| "No temperature reading means temperature is 0." | Missing is distinct from a measured zero. |
| "Interpolated values equal real measurements." | Preserve provenance and distinct usage policies. |
| "`allowDiskUse` removes densify's generation limit." | It does not lift the generated-document cap. |
| "If partition X has no data, densify creates X." | It cannot invent partitions with zero input records. |
| "MongoDB 5.1 has both stages." | `$fill` was introduced in 5.3. |
| "Aggregation fill updates the collection." | No, unless an explicit write stage like `$merge` is used. |

---

## 29. Official MongoDB Documentation

- [`$densify` — Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/): syntax, bounds, partitions, document limits, and 8.0/8.1 changes.
- [`$fill` — Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/): constant, linear, LOCF, sortBy, partitions, and 8.0.20 changes.
- [`$linearFill` — Window Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/linearFill/): interpolation inside `$setWindowFields`.
- [`$locf` — Window Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/locf/): last-observation-carried-forward.
- [`$setWindowFields`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/): partitioning and window calculations.
- [`$dateTrunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/): snapping timestamps to calendar buckets.
- [`$dateDiff`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateDiff/): computing elapsed time for max-gap checks.
- [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): bucket aggregation.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): optimization and index usage.
- [MongoDB 8.2 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.2-compatibility/): behavioral changes related to densify/fill.
- [Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/): running pipelines from Java applications.

In production, always cross-check documentation against your **exact MongoDB server and Java driver versions**, especially regarding patch-release changes and `linear` constraints.

## 30. Conclusion

`$densify` and `$fill` complement rather than replace each other: one creates missing **slots/documents**, while the other populates **null/missing field values**. Used together, they produce continuous time-series or numeric sequences suitable for charts and downstream analytics.

Yet a series that looks complete is not automatically **complete observed data**. Choose partitions, bounds, and steps carefully, normalize timestamps, resolve duplicates, respect generated-document limits, pick domain-appropriate fill methods, and preserve provenance flags for synthesized values.

**Generating the right slots is only step one; filling them meaningfully while keeping real observations distinguishable from inferred values is what makes results trustworthy.**
