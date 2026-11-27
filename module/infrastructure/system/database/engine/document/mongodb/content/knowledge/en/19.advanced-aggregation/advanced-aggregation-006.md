# Grouping into Ranges with $bucket and $bucketAuto

In MongoDB, aggregation is not limited to filtering documents or grouping identical values. Many reports need to **partition data into ranges (buckets)**: product prices from 0 to under 100 thousand VND, exam scores from 50 to under 65, orders by month, customer age brackets, or transaction counts across value tiers.

Two aggregation stages are purpose-built for this task:

- **`$bucket`**: the developer **predefines the range boundaries**. Best suited when the business has fixed tiers and needs consistent comparisons across reporting periods.
- **`$bucketAuto`**: MongoDB **computes the boundaries automatically** from data distribution, aiming to create close to the requested number of buckets with roughly balanced document counts.

For example, if the business team wants product counts in price tiers under 100,000, 100,000–under 300,000, and 300,000–under 600,000 VND: use `$bucket`. If the analytics team does not yet know where to place thresholds and wants to split products into four groups of roughly equal size: use `$bucketAuto`.

This lesson explains syntax, lower/upper bound inclusivity, out-of-range document handling, accumulators, time-based bucketing, actual bucket counts, cross-period stability, performance, Java examples, and practice exercises.

## 1. Preparing Practice Data

We use the `bucketLabProducts` collection in a test environment. `price` is stored as BSON Decimal128 in **thousands of VND**; `100` represents 100,000 VND. Never run `drop()` on a collection containing real data you need to keep.

```javascript
db.bucketLabProducts.drop();

db.bucketLabProducts.insertMany([
  {
    _id: "P01", name: "Ballpoint pen",
    category: "stationery",
    price: NumberDecimal("50"), stock: 80,
    createdAt: ISODate("2026-01-05T08:00:00Z")
  },
  {
    _id: "P02", name: "Notebook",
    category: "stationery",
    price: NumberDecimal("90"), stock: 60,
    createdAt: ISODate("2026-01-17T08:00:00Z")
  },
  {
    _id: "P03", name: "Water bottle",
    category: "accessory",
    price: NumberDecimal("100"), stock: 35,
    createdAt: ISODate("2026-02-01T08:00:00Z")
  },
  {
    _id: "P04", name: "Headphones",
    category: "electronics",
    price: NumberDecimal("180"), stock: 25,
    createdAt: ISODate("2026-02-10T08:00:00Z")
  },
  {
    _id: "P05", name: "Office mouse",
    category: "electronics",
    price: NumberDecimal("299"), stock: 20,
    createdAt: ISODate("2026-02-26T08:00:00Z")
  },
  {
    _id: "P06", name: "Keyboard",
    category: "electronics",
    price: NumberDecimal("300"), stock: 15,
    createdAt: ISODate("2026-03-01T08:00:00Z")
  },
  {
    _id: "P07", name: "Portable drive",
    category: "electronics",
    price: NumberDecimal("450"), stock: 12,
    createdAt: ISODate("2026-03-12T08:00:00Z")
  },
  {
    _id: "P08", name: "Bluetooth speaker",
    category: "electronics",
    price: NumberDecimal("599"), stock: 10,
    createdAt: ISODate("2026-03-28T08:00:00Z")
  },
  {
    _id: "P09", name: "Small monitor",
    category: "electronics",
    price: NumberDecimal("600"), stock: 8,
    createdAt: ISODate("2026-04-03T08:00:00Z")
  },
  {
    _id: "P10", name: "Large monitor",
    category: "electronics",
    price: NumberDecimal("850"), stock: 5,
    createdAt: ISODate("2026-04-19T08:00:00Z")
  },
  {
    _id: "P11", name: "Printer",
    category: "electronics",
    price: NumberDecimal("1000"), stock: 4,
    createdAt: ISODate("2026-05-01T08:00:00Z")
  },
  {
    _id: "P12", name: "Pro equipment kit",
    category: "electronics",
    price: NumberDecimal("1200"), stock: 2,
    createdAt: ISODate("2026-05-15T08:00:00Z")
  },
  {
    _id: "P13", name: "Sample with null price",
    category: "electronics",
    price: null, stock: 1,
    createdAt: ISODate("2026-06-02T08:00:00Z")
  },
  {
    _id: "P14", name: "Sample missing price",
    category: "electronics",
    stock: 3,
    createdAt: ISODate("2026-06-12T08:00:00Z")
  },
  {
    _id: "P15", name: "Sample negative price",
    category: "electronics",
    price: NumberDecimal("-20"), stock: 1,
    createdAt: ISODate("2026-06-20T08:00:00Z")
  }
]);
```

The dataset intentionally includes boundary cases: prices landing directly on boundaries `100`, `300`, `600`, `1000`; out-of-range prices; `null` price; and a missing `price` field. These edge cases help prevent misinterpreting histogram results.

## 2. What Is a Data Range?

Suppose a report requires four price tiers:

```text
0          100           300            600           1000
|-----------|-------------|--------------|--------------|
 [0,100)     [100,300)     [300,600)      [600,1000)
```

The notation `[a,b)` means:

- Inclusive of values **equal to a**.
- Exclusive of values **equal to b**.
- Each value falls into at most one interval defined by the ascending sequence of boundaries.

Therefore:

| Value | Containing Bucket |
|---:|---|
| 0 | `[0,100)` |
| 99 | `[0,100)` |
| **100** | **`[100,300)`** |
| 299 | `[100,300)` |
| **300** | **`[300,600)`** |
| **600** | **`[600,1000)`** |
| 999 | `[600,1000)` |
| **1000** | **Not in any of the ranges above** |
| -20 | Not in any of the ranges above |

**Characteristic of `$bucket`: even the final upper bound is exclusive.** If a pipeline author wants `1000` included, they must provide a higher upper boundary or define an out-of-range classification policy. This is an important difference from `$bucketAuto`'s output semantics covered later.

Values of a different BSON type from the boundaries, such as String and null, must also be handled explicitly; do not assume they behave as valid numbers.

## 3. `$bucket` Syntax

General structure:

```javascript
{
  $bucket: {
    groupBy: <expression>,
    boundaries: [<first>, <second>, ..., <last>],
    default: <defaultBucketId>,
    output: {
      <name1>: { <accumulator1>: <expression1> },
      <name2>: { <accumulator2>: <expression2> }
    }
  }
}
```

Properties:

| Property | Meaning | Required |
|---|---|---|
| `groupBy` | Expression computing the value to bucket for each document | Yes |
| `boundaries` | Bounds in **strictly ascending order**, at least two values | Yes |
| `default` | `_id` value of the bucket receiving out-of-range inputs | No |
| `output` | Accumulators computing metrics per bucket | No |

A `boundaries` array with `N+1` elements defines at most `N` predetermined intervals. For instance, `[0,100,300]` creates **two buckets**, `[0,100)` and `[100,300)`, not three.

Boundaries must follow MongoDB's BSON type and comparison rules: generally the same type, with exceptions allowing mixed numeric types. For monetary values, use a consistent type such as Decimal128 for boundaries to avoid precision or unit confusion.

### 3.1. Output Shape

Each `$bucket` output document represents an interval that contains at least one document. Its `_id` field is the **lower bound** of the interval; for out-of-range documents, `_id` is the `default` value.

Example:

```javascript
{
  _id: NumberDecimal("100"),
  count: 3
}
```

means the bucket has lower bound 100. The upper bound is not included in `_id` by default; the application derives it from the corresponding `boundaries` configuration.

When `output` is omitted, MongoDB uses a default equivalent to:

```javascript
output: {
  count: { $sum: 1 }
}
```

When you need metrics beyond a simple count, declare `output` explicitly.

## 4. Practicing `$bucket`: Grouping Products by Price

The following example splits products into four tiers plus an out-of-range group:

```javascript
db.bucketLabProducts.aggregate([
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      default: "OTHER",
      output: {
        productCount: { $sum: 1 },
        productIds: { $push: "$_id" }
      }
    }
  }
]);
```

Grouping breakdown over the dataset:

| Bucket `_id` | Range / Meaning | Products | Count |
|---|---|---|---:|
| `0` | `[0,100)` | P01, P02 | 2 |
| `100` | `[100,300)` | P03, P04, P05 | 3 |
| `300` | `[300,600)` | P06, P07, P08 | 3 |
| `600` | `[600,1000)` | P09, P10 | 2 |
| `"OTHER"` | Out of bounds or outside numeric intervals | P11, P12, P13, P14, P15 | 5 |

The order of IDs inside the `$push` array should not be treated as guaranteed unless the pipeline explicitly defines sorting.

### 4.1. Why Does P11 (Price 1000) Land in OTHER?

The last bucket is `[600,1000)`, so `1000` **equals the exclusive upper bound and is excluded**, while `1200` exceeds it. P15 has a negative price below the lowest boundary. P13 is null and P14 is missing `price`; they do not fall into any of the numeric intervals.

`default: "OTHER"` collapses all of these into one output bucket. That **does not** imply they share a single root cause. In strict reporting, distinguish valid high prices, invalid negative prices, and missing/null prices.

### 4.2. If `default` Is Omitted

```javascript
db.bucketLabProducts.aggregate([
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

Because the dataset contains inputs outside the boundaries, `$bucket` **throws an error** when no default bucket is provided to catch them. This differs from silently skipping non-matching documents.

There are two design choices:

- Declare `default` to capture out-of-domain documents.
- Use `$match` **to filter valid in-domain inputs before** `$bucket` when the business only wants statistics for that subset.

Example filtering non-negative numeric prices below 1000:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

In this study schema, `price` is a scalar. `$type: "number"` matches all BSON numeric types. On schemas with complex arrays, validate actual field types to prevent array predicates from matching elements unexpectedly.

### 4.3. Each Record Belongs to Only One Bucket

When `price = 300`, it falls into `[300,600)`, **not** simultaneously into `[100,300)`. Inclusive lower bounds paired with exclusive upper bounds ensure adjacent intervals never overlap.

Consequently, for a filtered valid input set covered by the intervals, the sum of `count` across all buckets equals the number of input documents.

## 5. Computing Multiple Metrics per Bucket

`$bucket` supports standard aggregation accumulators such as `$sum`, `$avg`, `$min`, `$max`, and `$push`.

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: {
        productCount: { $sum: 1 },
        stockUnits: { $sum: "$stock" },
        averagePrice: { $avg: "$price" },
        lowestActualPrice: { $min: "$price" },
        highestActualPrice: { $max: "$price" }
      }
    }
  }
]);
```

Meaning:

- `productCount`: number of documents in the bucket.
- `stockUnits`: total inventory units.
- `averagePrice`: mean price of documents in the bucket.
- `lowestActualPrice`: lowest actual price observed in the bucket.
- `highestActualPrice`: highest actual price observed in the bucket.

**The lowest actual price does not necessarily equal the lower bound**, nor does the highest actual price necessarily equal the upper bound. For example, `[100,300)` might contain only prices 180 and 299 while still having bucket `_id` 100.

### 5.1. Inventory Value per Range

If you need monetary inventory value:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      },
      stock: { $type: "number" }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: {
        productCount: { $sum: 1 },
        inventoryValue: {
          $sum: {
            $multiply: ["$price", "$stock"]
          }
        }
      }
    }
  }
]);
```

`$multiply` computes each document's inventory value, then `$sum` totals it per bucket. For financial logic, enforce consistent numeric types and currency units; since `price` is in thousands of VND, the resulting sum is also in thousands of VND.

### 5.2. Avoid `$push` of Full Documents in Large Buckets

```javascript
output: {
  allProducts: { $push: "$$ROOT" }
}
```

This can produce an output document containing huge arrays, consuming RAM and risking the BSON document size limit. Histograms normally need **summary statistics**, not turning an entire collection into a few massive arrays.

If you need a few representative sample documents, design bounded sampling according to your MongoDB version and features.

## 6. Boundary Rules and Common Mistakes

### 6.1. Boundaries Must Be Strictly Increasing

Valid:

```javascript
boundaries: [0, 100, 300, 1000]
```

Invalid:

```javascript
// Duplicate boundary values.
boundaries: [0, 100, 100, 300]

// Not in ascending order.
boundaries: [0, 300, 100, 1000]

// Only one value; cannot form an interval.
boundaries: [0]
```

You cannot create a `[100,100)` bucket to capture values equal to 100. To group by discrete exact values, `$group` is the right stage.

### 6.2. The Final Upper Bound Is Also Exclusive

With:

```javascript
boundaries: [0, 100, 300]
```

you only get `[0,100)` and `[100,300)`. The value `300` **does not belong to the second bucket**. If business rules must include 300, define a higher upper boundary or a dedicated rule.

Do not blindly add 1 to the final boundary when prices can be decimals: `300.50` and `300.99` could exist, so "+1" only makes sense when unit resolution and valid domain bounds are strictly known.

### 6.3. Choose Consistent Data Types

If `price` is Decimal128, use Decimal128 for boundaries:

```javascript
boundaries: [
  NumberDecimal("0"),
  NumberDecimal("100"),
  NumberDecimal("300"),
  NumberDecimal("1000")
]
```

MongoDB defines rules for mixing BSON numeric types in boundaries, yet you should never mix Dates and Numbers or put numeric Strings into boundaries expecting numeric range comparisons.

### 6.4. Empty Buckets Do Not Automatically Emit `count: 0`

Suppose data contains only prices 50 and 850 with boundaries `[0,100,300,600,1000]`. MongoDB returns only:

```javascript
{ _id: 0, count: 1 }
{ _id: 600, count: 1 }
```

The intervals `[100,300)` and `[300,600)` have zero documents and **are not emitted with count 0 by default**.

If a dashboard must render all four columns, the application layer can merge results against the known `boundaries` configuration and backfill 0 for missing intervals.

### 6.5. `default` Is Not a Contiguous Numeric Interval

`default: "OTHER"` can mix negative prices, prices above the upper bound, nulls, and missing fields. It does not represent an interval with a single lower and upper bound. On charts, render OTHER separately as "Out of range or invalid data" rather than drawing it as a column of equal numeric width alongside price ranges.

## 7. Classifying Dirty Data Before Building Histograms

Suppose legacy documents contain:

```javascript
[
  { price: NumberDecimal("125.50") },
  { price: "125.50" },
  { price: "not available" },
  { price: null },
  {}
]
```

If you bucket without normalizing, strings do not automatically become numbers. Use `$convert` with `onError` and `onNull`:

```javascript
db.legacyProducts.aggregate([
  {
    $set: {
      normalizedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      normalizedPrice: {
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$normalizedPrice",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

This pipeline counts **only convertible records within range**, excluding invalid and missing records. That is valid for a scoped report, yet if a report claims "distribution of all products," you must disclose how many records were excluded.

### 7.1. Counting Invalid Records Separately

```javascript
db.legacyProducts.aggregate([
  {
    $project: {
      price: 1,
      sourceType: { $type: "$price" },
      normalizedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      quality: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$sourceType", "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$sourceType", "null"] },
              then: "NULL"
            },
            {
              case: { $eq: ["$normalizedPrice", null] },
              then: "INVALID"
            },
            {
              case: {
                $lt: ["$normalizedPrice", NumberDecimal("0")]
              },
              then: "NEGATIVE"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $group: {
      _id: "$quality",
      count: { $sum: 1 }
    }
  }
]);
```

This lets the report present two parts: a histogram of valid prices and an input data-quality breakdown. This is far safer than silently coercing bad prices to 0, since 0 may itself be a legitimate business price.

## 8. Bucketing Time Intervals with `$bucket`

`groupBy` does not have to be numeric. When data is BSON Date, you can bucket by Date boundaries.

Example counting products created in Q1 2026:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$createdAt",
      boundaries: [
        ISODate("2026-01-01T00:00:00Z"),
        ISODate("2026-02-01T00:00:00Z"),
        ISODate("2026-03-01T00:00:00Z"),
        ISODate("2026-04-01T00:00:00Z")
      ],
      output: {
        productsCreated: { $sum: 1 }
      }
    }
  }
]);
```

Three intervals:

```text
[2026-01-01, 2026-02-01)
[2026-02-01, 2026-03-01)
[2026-03-01, 2026-04-01)
```

A product created at exactly `2026-03-01T00:00:00Z` lands in the March bucket, not February.

### 8.1. Calendar Months Do Not Have a Fixed Day Count

When grouping by month, never split timestamps into fixed `30 × 24 hours` chunks and call them "months." Calendar months have 28, 29, 30, or 31 days. Use proper Date boundaries or `$dateTrunc` with a timezone to find month starts.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$orderedAt",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

`$dateTrunc` + `$group` fits rolling multi-year monthly reporting; `$bucket` fits when a report must match a fixed pre-agreed list of Date boundaries.

### 8.2. Timezones Can Shift Buckets

`ISODate("2026-03-01T00:00:00Z")` is midnight UTC, not midnight Vietnam time. An event at 00:30 Vietnam time on March 1 is still February 28 in UTC. If the business defines "month" in Vietnam time, compute the corresponding UTC instants or use time operators supporting `timezone`.

**Time boundaries are business rules**, not merely display formatting.

## 9. Bucketing Computed Expressions

`groupBy` accepts any aggregation expression. You can bucket documents by a **derived calculation** over multiple fields.

Suppose `orderLines` has `unitPrice` and `quantity`:

```javascript
db.orderLines.aggregate([
  {
    $match: {
      unitPrice: { $type: "number" },
      quantity: { $type: "number" }
    }
  },
  {
    $bucket: {
      groupBy: {
        $multiply: ["$unitPrice", "$quantity"]
      },
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: {
        lineCount: { $sum: 1 }
      }
    }
  }
]);
```

This buckets **line-item total value**, not single-unit price. Before using this, validate `quantity`, `unitPrice`, currency unit, and numeric types; malformed string inputs can break arithmetic.

You can extract the expression into `$set` for readability:

```javascript
db.orderLines.aggregate([
  {
    $set: {
      lineValue: {
        $multiply: ["$unitPrice", "$quantity"]
      }
    }
  },
  {
    $bucket: {
      groupBy: "$lineValue",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: { count: { $sum: 1 } }
    }
  }
]);
```

`$set` in an aggregation pipeline adds the computed field only to **pipeline documents**, without modifying the stored collection documents.

## 10. When to Use `$group` Instead of `$bucket`

`$group` groups by **exact matching key values**:

```javascript
db.bucketLabProducts.aggregate([
  {
    $group: {
      _id: "$category",
      productCount: { $sum: 1 }
    }
  }
]);
```

Example grouping by exact price:

```javascript
db.bucketLabProducts.aggregate([
  {
    $group: {
      _id: "$price",
      count: { $sum: 1 }
    }
  }
]);
```

This creates separate groups for prices 50, 90, 100, etc.; it **does not combine** all prices from 0 to under 100 into one bucket.

Comparison:

| Goal | Tool |
|---|---|
| Count by exact status/category | `$group` |
| Numeric values falling into fixed intervals | `$bucket` |
| Automatic intervals from data distribution | `$bucketAuto` |
| Non-contiguous or multi-condition business labels | `$switch`/`$cond` followed by `$group` |
| Calendar day/month reports by timezone | `$dateTrunc` + `$group` |
| Multiple independent stats from the same input | `$facet` |

Do not force every grouping need into `$bucket` merely because a field is numeric. When grouping non-contiguous tiers or multi-field conditions, computing a label with `$switch` and then running `$group` is more flexible.

## 11. `$bucketAuto`: MongoDB Determines Boundaries Automatically

General syntax:

```javascript
{
  $bucketAuto: {
    groupBy: <expression>,
    buckets: <positiveInteger>,
    output: {
      <fieldName>: { <accumulator>: <expression> }
    },
    granularity: <preferredNumberSeries>
  }
}
```

Properties:

- `groupBy`: expression producing the value to bucket.
- `buckets`: **desired number of buckets**, a positive integer.
- `output`: per-bucket accumulators, just like `$bucket`; defaults to count.
- `granularity`: optional preferred number series for rounding numeric boundaries, such as `"R5"`.

Core principle:

> `$bucketAuto` tries to create buckets with **roughly balanced document counts**, not intervals of **equal value width**.

Example:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      output: {
        productCount: { $sum: 1 },
        averagePrice: { $avg: "$price" },
        actualMin: { $min: "$price" },
        actualMax: { $max: "$price" }
      }
    }
  }
]);
```

With 12 products having non-negative numeric prices in the test data, requesting four buckets targets around three products per group, though exact bounds and counts **depend on value distribution**. Never hardcode automatic bounds as if they were a fixed contract.

### 11.1. `_id` Shape in `$bucketAuto`

`$bucket` sets `_id` to the single lower-bound value. `$bucketAuto` differs:

```javascript
{
  _id: {
    min: NumberDecimal("..."),
    max: NumberDecimal("...")
  },
  productCount: 3
}
```

Here `min` and `max` are **bucket boundaries**, not necessarily the actual min/max observed values when `granularity` is used. If you need actual observed extremes, add `$min` and `$max` accumulators explicitly.

### 11.2. Boundary Rules in `$bucketAuto`

Auto buckets describe intervals via `min` and `max`. Intermediate buckets have inclusive lower bounds and exclusive upper bounds; **the final bucket has an inclusive upper bound** so it can contain the maximum value.

Do not mechanically apply `$bucket`'s rule that *every* upper bound is exclusive to `$bucketAuto` output. When turning auto bounds back into queries, account for the final bucket's inclusive upper bound.

## 12. `$bucketAuto` Does Not Guarantee Exact Bucket Count or Equal Counts per Bucket

Suppose there are 100 documents and you ask for:

```javascript
{
  $bucketAuto: {
    groupBy: "$price",
    buckets: 5
  }
}
```

The goal is roughly 20 documents/bucket, not a strict guarantee. Reasons include:

1. Multiple documents share the **same `groupBy` value**.
2. Fewer distinct values exist than requested buckets.
3. Identical values cannot be split across two different value intervals just to equalize counts.
4. `granularity` may shift boundaries onto preferred round numbers.

Example:

```text
Values:
10, 10, 10, 10, 10, 10, 20, 20, 20, 30, 30, 30

Distinct value count = 3
Requested buckets    = 5
```

You cannot form five **distinct value intervals** while keeping equal values together in one interval. `$bucketAuto` may return **fewer buckets** or buckets with noticeably unequal document counts.

### 12.1. Balanced Counts Do Not Mean Equal Interval Widths

Example:

```text
10, 11, 12, 13, 14, 15, 16, 17, 18, 1000, 5000, 15000
```

To split this into four buckets with similar document counts, buckets around 10–18 will be **narrow**, whereas the bucket covering 1000–15000 will be **enormous**.

If a chart plots price on a proportional horizontal axis, bars will have unequal widths. If the chart renders "Bucket 1–4" with uniform column widths, label clearly that columns represent **unequal price widths**.

### 12.2. Be Careful with "25%, 50%, 75%" Labels

`buckets: 4` suggests quartiles dividing documents into quarters. Yet with duplicate values, each bucket does not necessarily hold exactly 25% of records. Always compute and display **actual observed percentages** rather than printing "Quartile 1–4" blindly without checking counts.

## 13. Granularity: Producing Readable Numeric Boundaries

Automatic boundaries can have awkward decimals, making chart labels hard to read. `$bucketAuto` supports the `granularity` option with preferred number series.

Example:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gt: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      granularity: "R5",
      output: {
        count: { $sum: 1 },
        avgPrice: { $avg: "$price" }
      }
    }
  }
]);
```

`"R5"` is a preferred number series yielding cleaner tick marks. When using granularity:

- Inputs must match the **numeric type** and constraints of the series; most preferred series require positive values, with specific rules for zero by series and MongoDB version.
- Granularity **does not alter stored price values**; it only shapes boundary selection.
- "Nicer" rounded boundaries can make document counts less evenly balanced across buckets.
- Do not use numeric granularity as a substitute for grouping Dates by week or month.

If the business requires **exact** breakpoints at 100, 300, and 1000, use `$bucket` instead of hoping `$bucketAuto` with granularity happens to generate them.

## 14. `$bucket` vs. `$bucketAuto`

| Criterion | `$bucket` | `$bucketAuto` |
|---|---|---|
| Who picks boundaries? | Pipeline author | MongoDB based on distribution |
| Signature required parameter | `boundaries` | `buckets` |
| Goal | Fixed intervals | Roughly balanced document counts per bucket |
| Interval width | Defined by `boundaries`; equal or custom | Not guaranteed |
| Documents per bucket | Can be heavily skewed | Attempts balance, not guaranteed |
| Returned bucket count | Only non-empty intervals, plus `default` if triggered | May be fewer than requested |
| Output `_id` | Lower bound or `default` value | `{ min, max }` object |
| Final upper bound | Exclusive | Inclusive on the last bucket |
| Out-of-range inputs | `default` bucket or error | Domain inferred from inputs |
| Supports granularity | No | Yes |
| Do bounds shift as data grows? | No, unless config changes | Yes, can shift |
| Best for business tiers | Ideal | Only if labels are not fixed scales |
| Exploring unknown thresholds | Must pick thresholds first | Ideal |

**Product-level distinction:** If bucket #2 covered `[100,200)` last month and shifts to `[120,260)` this month, comparing bucket #2 counts across months compares **different price domains**.

## 15. Designing Charts That Stay Stable Across Periods

For a multi-month dashboard:

```text
Month 1: [0,100), [100,300), [300,600), [600,1000)
Month 2: [0,100), [100,300), [300,600), [600,1000)
Month 3: [0,100), [100,300), [300,600), [600,1000)
```

The same bucket `_id` always carries the same meaning, enabling valid trend comparisons.

With `$bucketAuto`, as distribution shifts:

```text
Month 1:
  Bucket A [10,40)
  Bucket B [40,80)
  ...

Month 2:
  Bucket A [10,50)
  Bucket B [50,95)
  ...
```

These numbers illustrate shifting bounds. A product whose price never changed can move to a different relative bucket simply because the rest of the catalog changed.

**A practical workflow:**

1. Run `$bucketAuto` on representative data to explore the distribution.
2. Collaborate with business stakeholders to choose meaningful thresholds.
3. Store `boundaries` alongside a **tier schema version**.
4. Use `$bucket` for recurring reports with those fixed thresholds.
5. When updating boundaries, bump the version and avoid mixing incompatible historical series.

If the goal genuinely is tracking **quantile positions** rather than fixed price brackets, `$bucketAuto` remains appropriate—just display each bucket's min/max explicitly for every period.

## 16. Computing Percentages per Bucket

Once you have document counts per bucket, you can compute percentages over the **filtered input set**.

Example:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  },
  {
    $group: {
      _id: null,
      buckets: {
        $push: {
          lowerBound: "$_id",
          count: "$count"
        }
      },
      totalCount: { $sum: "$count" }
    }
  },
  { $unwind: "$buckets" },
  {
    $project: {
      _id: 0,
      lowerBound: "$buckets.lowerBound",
      count: "$buckets.count",
      totalCount: 1,
      percent: {
        $cond: [
          { $gt: ["$totalCount", 0] },
          {
            $multiply: [
              {
                $divide: [
                  "$buckets.count",
                  "$totalCount"
                ]
              },
              100
            ]
          },
          null
        ]
      }
    }
  },
  { $sort: { lowerBound: 1 } }
]);
```

Here the **denominator `totalCount`** is the count of products with numeric prices in `[0,1000)`, not all products in the collection. If percentages must reflect the entire catalog, include out-of-range/null/missing documents in the denominator per business rules.

If the input query matches zero documents, the pipeline emits no buckets; the API should handle an empty result rather than assuming four rows and a positive total always exist.

## 17. Combining with `$facet` for Multiple Views

An analytics screen may simultaneously want:

- A histogram on official price tiers;
- Four automatic price quantiles;
- Minimum, maximum, and average price.

`$facet` runs multiple sub-pipelines over the same post-filter input:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $facet: {
      fixedRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [
              NumberDecimal("0"),
              NumberDecimal("100"),
              NumberDecimal("300"),
              NumberDecimal("600"),
              NumberDecimal("1000")
            ],
            default: "ABOVE_RANGE",
            output: {
              count: { $sum: 1 }
            }
          }
        }
      ],
      autoRanges: [
        {
          $bucketAuto: {
            groupBy: "$price",
            buckets: 4,
            output: {
              count: { $sum: 1 },
              averagePrice: { $avg: "$price" }
            }
          }
        }
      ],
      overall: [
        {
          $group: {
            _id: null,
            totalProducts: { $sum: 1 },
            minPrice: { $min: "$price" },
            maxPrice: { $max: "$price" },
            averagePrice: { $avg: "$price" }
          }
        }
      ]
    }
  }
]);
```

Output is one document containing `fixedRanges`, `autoRanges`, and `overall` arrays.

**Note:** `$match` before `$facet` already excluded nulls, missing values, and negatives, so `overall.totalProducts` counts only **valid prices matching the filter**. If you also want data-error counts, feed the unfiltered input into `$facet` and filter differently inside each branch. Never filter out bad records **before** the branch responsible for reporting them.

### 17.1. Memory and Output Size Limits

`$facet` is not a free pass to run unlimited charts. Branches containing `$bucketAuto`, `$group`, `$push`, or huge outputs can pressure memory or disk. The single combined `$facet` output document remains subject to BSON size limits and stage memory caps. For high-traffic dashboards, measure real load and consider pre-aggregation.

## 18. Age or Score Distribution Analysis

Another example: grouping students by exam score.

```javascript
db.examResults.aggregate([
  {
    $match: {
      score: {
        $type: "number",
        $gte: 0,
        $lte: 100
      }
    }
  },
  {
    $bucket: {
      groupBy: "$score",
      boundaries: [0, 50, 65, 80, 90, 101],
      output: {
        studentCount: { $sum: 1 },
        averageScore: { $avg: "$score" }
      }
    }
  }
]);
```

Upper bound 101 lets the top bucket include score 100 when scores are capped at 100. Semantically, however, that bucket is `[90,101)` and **does not validate** 100.5 on its own. The `$match` filter `score <= 100` enforces the domain; document that clearly in reports.

To split into four relative quantile groups instead of official grade brackets:

```javascript
db.examResults.aggregate([
  {
    $match: {
      score: { $type: "number" }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$score",
      buckets: 4,
      output: {
        studentCount: { $sum: 1 },
        minActualScore: { $min: "$score" },
        maxActualScore: { $max: "$score" }
      }
    }
  }
]);
```

If many students share the same score, counts across buckets will vary. Never substitute automatic buckets for official pass/fail thresholds or fixed grading rubrics.

### 18.1. Age Grouping with Expressions

```javascript
db.members.aggregate([
  {
    $match: {
      birthDate: { $type: "date" }
    }
  },
  {
    $set: {
      ageYears: {
        $dateDiff: {
          startDate: "$birthDate",
          endDate: "$$NOW",
          unit: "year",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $bucket: {
      groupBy: "$ageYears",
      boundaries: [0, 18, 25, 35, 50, 120],
      default: "OTHER",
      output: {
        memberCount: { $sum: 1 }
      }
    }
  }
]);
```

`$dateDiff` calculates years according to MongoDB's calendar rules. If a report needs age **as of a cutoff date** rather than query execution time, pass a fixed BSON Date instead of `$$NOW` for reproducible runs. For legal age rules around birthdays and leap years, verify exact domain conventions.

## 19. Multi-Dimensional Grouping: When One Bucket Stage Isn't Enough

`$bucket` partitions along a single `groupBy` expression in one stage. When you need **price × category** counts, derive the price band label with `$switch` and then `$group` by the `(band, category)` pair.

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $set: {
      priceBand: {
        $switch: {
          branches: [
            {
              case: {
                $lt: ["$price", NumberDecimal("100")]
              },
              then: "UNDER_100"
            },
            {
              case: {
                $lt: ["$price", NumberDecimal("300")]
              },
              then: "100_TO_299"
            },
            {
              case: {
                $lt: ["$price", NumberDecimal("600")]
              },
              then: "300_TO_599"
            }
          ],
          default: "600_TO_999"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        band: "$priceBand",
        category: "$category"
      },
      count: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.band": 1,
      "_id.category": 1
    }
  }
]);
```

This handles **two-dimensional** bucketing cleanly. Still, if one report uses `$bucket` and another uses `$switch` for the same price scale, manage boundaries centrally and version them so one place never drifts to 300 while another uses 299.

## 20. Performance and Indexing

Both `$bucket` and `$bucketAuto` must process every input document entering the stage. A histogram returning four rows **does not mean the server read only four documents**.

### 20.1. Early `$match` to Shrink Input

Example order report for one tenant and date window:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      orderedAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2026-07-01T00:00:00Z")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$total",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: {
        orderCount: { $sum: 1 }
      }
    }
  }
]);
```

Candidate index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  orderedAt: 1
});
```

The index accelerates `$match` on tenant/status/range, reducing how many documents reach `$bucket`. However, it **does not make the aggregation itself free**.

### 20.2. `$bucketAuto` Must Inspect the Full Input Distribution

`$bucketAuto` derives boundaries from the values passing through the stage. If tens of millions of records enter the stage, computing the distribution and bucketing can consume substantial CPU, RAM, and disk.

When a popular dashboard repeatedly requests the same histogram:

- Consider maintaining a periodic summary collection;
- Add caching with TTL and clear invalidation rules;
- Scope inputs tightly by tenant, date range, and status;
- Prefer fixed `$bucket` intervals where business allows;
- Consider sampling when approximate distributions are acceptable and disclosed.

Never run `$bucketAuto` across an entire system every time a user toggles a UI option without assessing scale, throughput, and SLAs.

### 20.3. Memory Limits and `allowDiskUse`

Grouping, sorting, and bucketing stages have resource limits. In supported versions/configurations, `allowDiskUse: true` lets spill-capable stages write temporary files to disk when needed:

```javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-A",
        status: "PAID"
      }
    },
    {
      $bucketAuto: {
        groupBy: "$total",
        buckets: 10,
        output: {
          count: { $sum: 1 },
          averageTotal: { $avg: "$total" }
        }
      }
    }
  ],
  { allowDiskUse: true }
);
```

`allowDiskUse` **does not remove all limits**: disk I/O still adds latency, stage-specific restrictions remain, and single BSON output limits still apply. Monitor slow queries, disk spills, CPU, RAM, and disk usage.

### 20.4. Analyzing with `explain`

```javascript
db.bucketLabProducts.explain("executionStats").aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      output: {
        count: { $sum: 1 }
      }
    }
  }
]);
```

Key items to inspect:

| Metric or Stage | Meaning |
|---|---|
| `winningPlan` | Which access strategy the planner chose |
| `IXSCAN` | Whether an index was used |
| `COLLSCAN` | Whether a collection scan occurred |
| `FETCH` | Whether documents were fetched outside the index |
| `totalDocsExamined` | Number of documents examined |
| `totalKeysExamined` | Number of index keys scanned |
| Sort/group/spill metrics | Resource cost of bucketing |
| `nReturned` | Result count at the corresponding summary level |

Explain output varies by MongoDB version and query engine. A pipeline reading millions of documents to return five buckets cannot be called "cheap" just because the output has five rows.

## 21. Histograms Requiring Zero-Count Bars

With fixed boundaries:

```javascript
const expectedBuckets = [
  { min: 0, max: 100, label: "Under 100" },
  { min: 100, max: 300, label: "100–under 300" },
  { min: 300, max: 600, label: "300–under 600" },
  { min: 600, max: 1000, label: "600–under 1000" }
];
```

The application receives `$bucket` results, matches `_id` as the lower bound against `expectedBuckets`, and fills `count: 0` for absent intervals.

Example response:

```javascript
[
  { min: 0, max: 100, count: 15 },
  { min: 100, max: 300, count: 0 },
  { min: 300, max: 600, count: 7 },
  { min: 600, max: 1000, count: 12 }
]
```

This enforces a **fixed report shape** without altering underlying metrics. With Date or Decimal128 keys, compare using exact types and units when joining results.

`default` values such as `"OTHER"` should be displayed separately because they have no fixed numeric width.

## 22. Do You Need a Snapshot When Data Mutates?

If you run `$bucketAuto` this morning and again this afternoon while thousands of products are added, boundaries may shift. That is **expected behavior reflecting the current distribution**.

If you need a report "as of 00:00 on month-end":

- Define the exact cutoff timestamp;
- Use appropriate read concerns/snapshots or an immutable dataset matching your consistency requirements;
- Never assume running one histogram guarantees subsequent reads see the exact same snapshot;
- Never treat `readConcern: "majority"` across separate requests as a cross-request snapshot guarantee.

With `$bucket`, boundaries stay constant, yet **counts still change** whenever inputs mutate. A fixed-bucket dashboard guarantees **stable interval definitions**, not immutable counts.

## 23. Using from the MongoDB Java Driver

The MongoDB Java Sync Driver can construct bucket stages using API builders or BSON `Document` objects. The examples below use `Document` to show the exact structure clearly.

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> products =
    database.getCollection("bucketLabProducts");

List<Decimal128> boundaries = Arrays.asList(
    new Decimal128(new BigDecimal("0")),
    new Decimal128(new BigDecimal("100")),
    new Decimal128(new BigDecimal("300")),
    new Decimal128(new BigDecimal("600")),
    new Decimal128(new BigDecimal("1000"))
);

Document bucket = new Document(
    "$bucket",
    new Document("groupBy", "$price")
        .append("boundaries", boundaries)
        .append("default", "OTHER")
        .append(
            "output",
            new Document("count", new Document("$sum", 1))
                .append("stockUnits", new Document("$sum", "$stock"))
        )
);

for (Document result : products.aggregate(Arrays.asList(bucket))) {
    System.out.println(result.toJson());
}
```

`$bucketAuto` example:

```java
Document bucketAuto = new Document(
    "$bucketAuto",
    new Document("groupBy", "$price")
        .append("buckets", 4)
        .append(
            "output",
            new Document("count", new Document("$sum", 1))
        )
);

for (Document result : products.aggregate(
        Arrays.asList(bucketAuto))) {
    System.out.println(result.toJson());
}
```

The auto example should include `$match`/validation when the collection contains nulls, missing values, or out-of-domain data. When mapping Decimal128 in Java, use an appropriate DTO type such as `BigDecimal` via configured codecs rather than converting monetary values to `double` where precision matters.

### 23.1. The Two Stages Have Different DTO Shapes

With `$bucket`:

```javascript
{ _id: NumberDecimal("100"), count: 25 }
```

With `$bucketAuto`:

```javascript
{
  _id: {
    min: NumberDecimal("100"),
    max: NumberDecimal("250")
  },
  count: 25
}
```

The two `_id` shapes are **not equivalent**. The API should decide whether to normalize both into `{min, max, count}` or expose separate response schemas. `$bucket` does not emit `max`; derive the upper bound from the configured `boundaries` list.

## 24. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking N boundaries create N buckets | N boundaries actually define N-1 intervals | Count consecutive boundary pairs |
| Thinking exact 100 lands in `[0,100)` | Wrong classification | Lower bound is inclusive; upper bound is exclusive |
| Thinking `$bucket`'s last upper bound is inclusive | Extreme values get excluded or routed to default | Add a higher bound or define `default` |
| Omitting `default` when outliers exist | Pipeline errors | Filter inputs or define `default` |
| Dumping null/missing/negative into `"HIGH_PRICE"` | Misleading report | Classify input quality first |
| Duplicate or descending boundaries | Configuration error | Use strictly increasing thresholds |
| Mixing Date and Number in boundaries | Type mismatch | Standardize BSON types |
| Expecting empty buckets to emit `count: 0` | Missing chart bars in UI | Backfill empty ranges when shaping response |
| Using `$push: "$$ROOT"` across millions of records | Oversized output / OOM | Prefer summary accumulators |
| Thinking `$bucketAuto` makes equal-width intervals | Misinterpreted histogram | Explain that it balances document counts |
| Thinking `buckets: 5` always returns five buckets | Duplicates / low cardinality skew counts | Handle actual returned bucket count |
| Comparing bucket #2 across two auto periods | Boundaries may have shifted | Use `$bucket` for fixed-threshold comparisons |
| Using numeric granularity to parse Dates | Wrong tool | Use Date boundaries or `$dateTrunc` |
| Analyzing string prices as numeric | Wrong results or errors | `$convert`, validation, migration |
| Reporting percentages with an unclear denominator | Misleading interpretation | State input/filter and excluded count explicitly |
| Judging cost from output count instead of input | Wrong performance assessment | Run `explain` and measure realistic load |

## 25. Practice Exercises

### Exercise 1 — Verifying Exact Boundaries

Use `bucketLabProducts` and boundaries `[0,100,300,600,1000]`.

1. Record the bucket for P03 (price 100).
2. Record the bucket for P06 (price 300).
3. Record the bucket for P09 (price 600).
4. Explain why P11 (price exactly 1000) goes into `OTHER`.
5. Remove `default`, re-run, and describe the error when out-of-range inputs exist.

### Exercise 2 — Multiple Accumulators

Write a `$bucket` pipeline computing per price tier:

- Product count;
- Total stock units;
- Average price;
- Lowest and highest actual prices;
- Total inventory value from `price × stock`.

Explain the difference between bucket bounds and actual min/max prices.

### Exercise 3 — Empty Buckets

Create a collection with only two prices, 50 and 850, split into four fixed ranges. How many bucket documents does MongoDB return? Build a response containing all four ranges with `count: 0` filled in for the two empty intervals.

### Exercise 4 — Skewed Data Distribution

Generate 1,000 documents: 800 products priced under 100, 150 priced from 100 to under 1000, and 50 priced 1000 or higher.

1. Run `$bucket` with fixed-width intervals.
2. Run `$bucketAuto` with five buckets.
3. Compare interval widths and document counts.
4. Explain which approach fits distribution exploration vs. official business segmentation.

### Exercise 5 — Duplicate Values

Create 100 documents using only three values: 10, 20, and 30. Ask `$bucketAuto` for five buckets. Why can't it produce five balanced buckets? How should the result be presented to report readers?

### Exercise 6 — Granularity

On a positive price set, run `$bucketAuto` without granularity and then with `"R5"`. Compare boundaries, counts, and bucket counts; comment on when readable thresholds matter more than strict balance. State how zero/negative prices are handled under the chosen series rules.

### Exercise 7 — Dates and Timezones

Use `$bucket` to group orders by January, February, and March 2026. Insert an order at `2026-03-01T00:00:00Z` and determine its bucket. If the business wants months in `Asia/Ho_Chi_Minh`, how must boundaries change or which operator should be used?

### Exercise 8 — `$facet` for Dashboards

Write a single pipeline with four branches:

1. Fixed-tier price buckets;
2. Four automatic price buckets;
3. Min/max/average of valid prices;
4. Count of null/missing/invalid documents.

Explain why placing a `$match` that drops nulls before `$facet` prevents the fourth branch from counting excluded records.

### Exercise 9 — Percentages and Denominators

Compute the percentage of products in each range. Clarify whether the denominator is products with valid prices in 0–1000 or all products; if an `OTHER` group exists, how should percentage reporting adjust?

### Exercise 10 — Performance Evaluation

On a dataset of one million orders:

1. Place `$match` by tenant and date range before `$bucketAuto`.
2. Create a candidate index for the filter.
3. Inspect `explain("executionStats")`.
4. Compare runtime/resource usage of 5 buckets vs. 100 buckets.
5. Propose pre-aggregation or caching for high-traffic dashboards.
6. Distinguish output bucket count from documents examined to build them.

## 26. MongoDB References

- [MongoDB $bucket](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/)
- [MongoDB $bucketAuto](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/)
- [MongoDB $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Accumulators](https://www.mongodb.com/docs/manual/reference/mql/accumulators/)
- [MongoDB $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Conclusion

**`$bucket`** is the right choice when grouping by **fixed boundaries**, such as price tiers, grade brackets, or business-defined date milestones. Every interval includes its lower bound and excludes its upper bound; out-of-range inputs must be filtered out or routed to a `default` bucket. Empty buckets do not automatically appear with count 0, and output `_id` is typically the lower bound.

**`$bucketAuto`** fits **exploring distributions**: MongoDB chooses boundaries to balance document counts across buckets, optionally using `granularity` for cleaner numeric ticks. Actual bucket counts and per-bucket document counts are not strictly guaranteed when duplicates or skewed data exist, and boundaries can shift between runs.

In both cases, standardize BSON types, clarify measurement units, handle null/missing/outliers intentionally, and benchmark performance on large inputs. A trustworthy histogram needs more than a valid aggregation query—it requires **explicitly defining what each range represents, which documents enter the denominator, and whether historical periods truly compare the same value domains**.
