# Grouping with `$group` and Choosing Grouping Keys in MongoDB

When using MongoDB to store orders, events, or accounts, each document typically describes a single object or business event. However, reporting screens need answers at the **group** level: how many orders each customer has, what revenue is per status, how daily order counts change, or which product is ordered the most.

In an **aggregation pipeline**, the **`$group`** stage groups documents sharing the same **grouping key** and computes aggregate values using **accumulators** such as `$sum`, `$avg`, `$min`, `$max`, `$push`, and `$addToSet`.

The key point is not just memorizing `$group` syntax, but **choosing the right grouping key**. Pick `status` for a status report, `customerId` for a customer report, a multi-field object for a multi-dimensional report, or an expression computed from dates when summarizing by day. Each choice changes the meaning of every result row.

This lesson in the **Aggregation Basics** chapter explains how to design grouping keys, practice with order data, handle missing/`null` keys, distinguish counting documents from counting array elements, read results, optimize pipelines, and apply it in Java applications.

## 1. What Does `$group` Do?

A pipeline typically consists of stages, each receiving data from the previous stage and passing results to the next:

```text
Collection orders
       |
       v
  $match (filter)
       |
       v
  $group (group + compute)
       |
       v
  $sort (sort groups)
       |
       v
  $project (format)
       |
       v
  Summary report
```

Example counting orders by status:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 }
    }
  }
])
```

Meaning:

- `aggregate([...])`: runs aggregation stages in order.
- `$group`: produces one output document for each distinct grouping key value.
- `_id: "$status"`: uses the **value of the `status` field** in each document to determine which group the document belongs to.
- `orderCount: { $sum: 1 }`: each document contributes `1` to its group, so the result is the count of documents in the group.

The `_id` field in `$group` output is the **grouping key**, not necessarily the original `_id` of a document. For example, `_id: "paid"` means this is the group of paid orders; it does not mean there is an order with `_id` equal to `"paid"`.

**General syntax:**

```javascript
{
  $group: {
    _id: <group_key_expression>,
    metricName1: { <accumulator>: <expression> },
    metricName2: { <accumulator>: <expression> }
  }
}
```

Output fields other than `_id` in the `$group` stage are normally built using **accumulator expressions**. You cannot arbitrarily emit a source document field without specifying how to aggregate it, because a group can contain many documents with different values.

## 2. Practice Dataset

Open `mongosh` and select a dedicated practice database:

```javascript
use mongo_aggregation_lab
```

Create a new or empty `orders` collection, then insert ten sample orders:

```javascript
db.orders.insertMany([
  {
    _id: 101,
    customerId: "C01",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(120),
    createdAt: ISODate("2026-11-10T08:00:00Z"),
    items: [
      { sku: "A", qty: NumberInt(2) },
      { sku: "B", qty: NumberInt(1) }
    ]
  },
  {
    _id: 102,
    customerId: "C01",
    status: "paid",
    channel: "mobile",
    region: "north",
    total: NumberInt(180),
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    items: [{ sku: "A", qty: NumberInt(1) }]
  },
  {
    _id: 103,
    customerId: "C02",
    status: "pending",
    channel: "web",
    region: "south",
    total: NumberInt(90),
    createdAt: ISODate("2026-11-10T10:00:00Z"),
    items: [{ sku: "C", qty: NumberInt(3) }]
  },
  {
    _id: 104,
    customerId: "C03",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(240),
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    items: [{ sku: "B", qty: NumberInt(2) }]
  },
  {
    _id: 105,
    customerId: "C02",
    status: "cancelled",
    channel: "mobile",
    region: "south",
    total: NumberInt(60),
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    items: []
  },
  {
    _id: 106,
    customerId: "C03",
    status: "paid",
    channel: "mobile",
    region: "north",
    total: NumberInt(150),
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    items: [
      { sku: "A", qty: NumberInt(2) },
      { sku: "C", qty: NumberInt(1) }
    ]
  },
  {
    _id: 107,
    customerId: "C04",
    status: "pending",
    channel: "web",
    region: "south",
    total: NumberInt(110),
    createdAt: ISODate("2026-11-12T08:00:00Z"),
    items: [{ sku: "B", qty: NumberInt(1) }]
  },
  {
    _id: 108,
    customerId: "C01",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(210),
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    items: [{ sku: "C", qty: NumberInt(2) }]
  },
  {
    _id: 109,
    customerId: "C05",
    status: "pending",
    channel: "web",
    total: NumberInt(85),
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    items: []
    // Missing region field
  },
  {
    _id: 110,
    customerId: "C06",
    channel: "mobile",
    region: null,
    total: NumberInt(45),
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    items: []
    // Missing status field
  }
])
```

Order `109` intentionally **omits `region`**, while order `110` has `region: null` and **omits `status`**. These two cases help test how grouping keys handle incomplete data.

With this dataset:

| Status | Order count | Sum of `total` |
| --- | ---: | ---: |
| `paid` | 5 | 900 |
| `pending` | 3 | 285 |
| `cancelled` | 1 | 60 |
| Missing `status` | 1 | 45 |
| **Total** | **10** | **1,290** |

Subsequent queries assume the data remains unchanged. Do not run `insertMany()` repeatedly with the same `_id` values; duplicate inserts will trigger duplicate key errors. Do not drop collections holding important data just to redo practice exercises.

## 3. Choosing a Single Field as the Grouping Key

### 3.1. Grouping Orders by `status`

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Result on the sample data, formatted cleanly by group:

```javascript
{ _id: null,        orderCount: 1, totalAmount: 45 }
{ _id: "cancelled", orderCount: 1, totalAmount: 60 }
{ _id: "paid",      orderCount: 5, totalAmount: 900 }
{ _id: "pending",   orderCount: 3, totalAmount: 285 }
```

Where:

- `$sum: 1` counts **each input document** exactly once.
- `$sum: "$total"` adds the **numeric value** of the `total` field in each document belonging to the group.
- `_id: "$status"` determines how many groups exist; two documents with the same `status` belong to the same group.
- `$sort` after `$group` determines the display order of the groups.

MongoDB **does not guarantee the output order of `$group`**. If a report needs deterministic ordering, add `$sort` after grouping.

### 3.2. Grouping by Customer

Change the grouping key from `"$status"` to `"$customerId"`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { totalAmount: -1, _id: 1 } }
])
```

On the sample data:

| Customer | Order count | Total amount |
| --- | ---: | ---: |
| C01 | 3 | 510 |
| C03 | 2 | 390 |
| C02 | 2 | 150 |
| C04 | 1 | 110 |
| C05 | 1 | 85 |
| C06 | 1 | 45 |

Same ten input documents, yet the report now has **six groups** instead of four. Therefore, choosing a grouping key means choosing the **unit of analysis**: does one result row represent a status or a customer?

### 3.3. Accessing Nested Fields with Dot Notation

If a document has:

```javascript
{
  customer: {
    id: "C01",
    address: { city: "Hà Nội" }
  }
}
```

you can group by the nested field:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customer.address.city",
      orderCount: { $sum: 1 }
    }
  }
])
```

The path `"$customer.address.city"` is an **aggregation field path**. This illustrates a different document structure from the practice `orders` collection in section 2, where `customerId` sits at the root level. If run directly on the sample dataset, that field does not exist and all results will collapse into the missing-key group instead of city statistics.

**Distinguish the two strings:** `"$status"` reads the value of the `status` field; `"status"` (without `$`) is a constant string, placing every document into the same group.

## 4. `_id: null` — Grouping All Documents into a Single Group

When you only need overall summary metrics for the **entire dataset**, without splitting by any field, use the constant `null` as the grouping key:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: null,
      totalOrders: { $sum: 1 },
      totalAmount: { $sum: "$total" },
      averageAmount: { $avg: "$total" },
      minAmount: { $min: "$total" },
      maxAmount: { $max: "$total" }
    }
  }
])
```

Result on the ten sample documents:

```javascript
{
  _id: null,
  totalOrders: 10,
  totalAmount: 1290,
  averageAmount: 129,
  minAmount: 45,
  maxAmount: 240
}
```

This is completely different from `_id: "$status"`, which forms distinct groups and **may emit a `null`-keyed group** for documents missing `status`. Put differently:

- `_id: null` → one **constant key** for all input documents.
- `_id: "$status"` → key is a field value; some documents **might** fall into the `null` group.

If there are zero input documents, `$group` does not synthesize a dummy summary row for the constant group; handle empty result sets explicitly when designing statistics APIs.

### Combining `$match` to Group Only Relevant Data

To compute the total amount only for `paid` orders:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      paidAmount: { $sum: "$total" }
    }
  }
])
```

The result is `paidOrders: 5`, `paidAmount: 900`. The `$match` stage ahead of `$group` feeds only the needed documents into the calculation and can leverage a suitable index for filtering.

## 5. Composite Grouping Keys from Multiple Fields

Reports often span multiple dimensions. For example: **order count and total amount by `status` and `channel`**. Grouping only by `status` fails to distinguish `web` from `mobile` orders. Grouping only by `channel` fails to distinguish `paid` from `pending`.

Declare `_id` as an object containing multiple components:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  {
    $sort: {
      "_id.status": 1,
      "_id.channel": 1
    }
  }
])
```

Each group is identified by the **pair of values** `(status, channel)`. Illustrative output:

| `_id.status` | `_id.channel` | Order count | Total amount |
| --- | --- | ---: | ---: |
| `null` / missing | mobile | 1 | 45 |
| cancelled | mobile | 1 | 60 |
| paid | mobile | 2 | 330 |
| paid | web | 3 | 570 |
| pending | web | 3 | 285 |

Suppose two documents share `status: "paid"`, one with `channel: "web"` and the other with `channel: "mobile"`. These two documents **do not belong to the same group**, because their composite keys differ.

### 5.1. Why Use an Object Instead of String Concatenation?

A seemingly simple approach is joining the two values into a string:

```javascript
// Not a good choice when wanting an explicit key structure
{
  $group: {
    _id: {
      $concat: ["$status", "|", "$channel"]
    },
    orderCount: { $sum: 1 }
  }
}
```

String concatenation carries risks:

- Source values might contain the delimiter, causing unintended key collisions.
- A missing or `null` field can make concatenation behave unexpectedly.
- Component data types and structure are lost.
- Filtering or sorting by individual components requires splitting the string back out.

An object with clear field names is easy to extend—such as adding `region` or date to the key—without having to invent delimiter-escaping rules.

### 5.2. Promoting Key Components to Top-Level Fields

`$group` output has a nested `_id` object. To reshape it into a friendlier API format:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id.status",
      channel: "$_id.channel",
      orderCount: 1,
      totalAmount: 1
    }
  },
  { $sort: { status: 1, channel: 1 } }
])
```

`$project` only transforms the **output shape**. It does not modify orders in the collection.

If you need output field names like `paymentStatus` or `sourceChannel`, you can rename them in `$project` without altering grouping logic.

## 6. Grouping Keys as Expressions, Not Necessarily Existing Fields

`$group`'s `_id` accepts an **aggregation expression**. That lets you group data by a computed value, such as a calendar day, price bracket, age band, or normalized status.

### 6.1. Grouping by Day from a `Date` Field

The `createdAt` field is a timestamp; grouping directly by `_id: "$createdAt"` puts orders at different times (even on the same day) into separate groups. When you need a **daily** report, compute a key representing the **calendar date**.

Example using `$dateToString` with the Vietnam timezone:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

On the sample data, every timestamp falls on the same UTC date and local date, so the result is:

| Date key `_id` | Order count | Total amount |
| --- | ---: | ---: |
| `2026-11-10` | 3 | 390 |
| `2026-11-11` | 3 | 450 |
| `2026-11-12` | 4 | 450 |

`$dateToString` here produces a **string** like `"2026-11-10"`. When you only need daily bucketing and still want a BSON Date representing the start of each group's day, you can use `$dateTrunc` on supported MongoDB versions:

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    orderCount: { $sum: 1 }
  }
}
```

`$dateTrunc` returns a **Date** representing the period boundary, stored/displayed in UTC even though day boundaries are calculated in the specified timezone. Distinguish this Date type from the date string produced by `$dateToString`.

### Why Timezones Matter

The instant `2026-11-10T20:00:00Z` falls on **Nov 10 in UTC**, but on **Nov 11 in Asia/Ho_Chi_Minh**. If a report uses Vietnam business days, grouping by UTC by default can place transactions on the wrong day relative to user expectations.

When designing day/week/month keys, agree on the **timezone, time unit, and reporting-period rules** before writing the pipeline.

### 6.2. Grouping Key from a Classification Expression

Suppose you need to classify orders into `low` if `total < 150`, otherwise `high`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $cond: {
          if: { $lt: ["$total", 150] },
          then: "low",
          else: "high"
        }
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

On the sample dataset, the `low` group includes totals `120, 90, 60, 110, 85, 45` (6 orders), while `high` includes `180, 240, 150, 210` (4 orders). This is an example of a **computed grouping key**, requiring no pre-stored `priceBand` field.

When classifying values, define boundaries clearly: in the example above, `150` falls into `high` because the condition uses `$lt`, not `$lte`.

### 6.3. Combining Date with Another Dimension

To report **order counts by status per day**:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        status: { $ifNull: ["$status", "unknown"] }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.day": 1, "_id.status": 1 } }
])
```

The grouping key is an object combining a **computed date** and a **normalized status**. This is a classic example of a multi-dimensional report.

## 7. Handling Missing Keys, `null`, and Different Data Types

In the sample dataset:

```javascript
{ _id: 109, /* missing region */ }
{ _id: 110, region: null }
```

The query:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

produces the corresponding groups:

```javascript
{ _id: null,    orderCount: 2, totalAmount: 130 }
{ _id: "north", orderCount: 5, totalAmount: 900 }
{ _id: "south", orderCount: 3, totalAmount: 260 }
```

With a simple field-path key, both documents with `region: null` and documents **lacking `region`** fall into the `null` key group. If business rules must distinguish "undeclared" from "declared as null," do not assume the output above represents three complete states.

### 7.1. Merging Unknown Values with `$ifNull`

In a UI report, you can use a label like `"unknown"`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $ifNull: ["$region", "unknown"] },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

`$ifNull` treats null/missing/undefined values as absent and substitutes `"unknown"`. On the sample data, orders `109` and `110` land together in `"unknown"` with a count of two.

**Label collision warning:** If real data already uses `region: "unknown"` as a valid value, this normalization merges it with missing/null records. When exact business distinction is required, use a structured key or classification code designed not to collide with real values.

### 7.2. Keeping Null and Missing Separate

The aggregation expression `$type` returns `"missing"` when a field does not exist and `"null"` when the field value is BSON Null. You can build a grouping key that includes the state type:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        regionType: { $type: "$region" },
        regionValue: { $ifNull: ["$region", null] }
      },
      orderCount: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.regionType": 1,
      "_id.regionValue": 1
    }
  }
])
```

Now one group has `regionType: "missing"` and another has `regionType: "null"`; report consumers clearly see two distinct data sources. If the system schema enforces that the field is always a string, this distinction is needed less often; it is helpful during migrations or when handling inconsistent data.

### 7.3. BSON Type of the Grouping Key Affects Results

Suppose one document stores `groupCode: 1` as a number and another stores `groupCode: "1"` as a string. The two values will not automatically be merged into one group. The BSON type of data affects how equality/grouping operates.

To unify groups, normalize schema on write or apply **intentional** type-conversion aggregation expressions after deciding how to handle conversion errors. For strings, collation rules also matter: locale, case sensitivity, and diacritic rules affect which values are considered equal in filters and groups.

**Rule:** grouping keys should have a consistent type and meaning. If source data mixes `Date` and date strings, `"01"` and `1`, or inconsistent casing, decide on normalization rules before interpreting group counts.

## 8. Common Accumulators Used with `$group`

Accumulators take multiple inputs within a group and produce a summary metric or representative value.

| Accumulator | Purpose | Example |
| --- | --- | --- |
| `$sum` | Sums numeric values or counts documents | `{ $sum: "$total" }`, `{ $sum: 1 }` |
| `$avg` | Averages numeric values | `{ $avg: "$total" }` |
| `$min` | Smallest value per BSON comparison rules | `{ $min: "$total" }` |
| `$max` | Largest value | `{ $max: "$total" }` |
| `$first` | Value from the first document entering the group | `{ $first: "$createdAt" }` |
| `$last` | Value from the last document entering the group | `{ $last: "$createdAt" }` |
| `$push` | Collects values into an array, preserving duplicates | `{ $push: "$_id" }` |
| `$addToSet` | Collects distinct values into an array | `{ $addToSet: "$channel" }` |

Example creating a per-customer report with multiple metrics:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" },
      averageAmount: { $avg: "$total" },
      smallestOrder: { $min: "$total" },
      largestOrder: { $max: "$total" },
      allOrderIds: { $push: "$_id" },
      channelsUsed: { $addToSet: "$channel" }
    }
  },
  { $sort: { _id: 1 } }
])
```

For group `C01`, we get `orderCount = 3`, `totalAmount = 510`, `averageAmount = 170`, `smallestOrder = 120`, and `largestOrder = 210`. The IDs are `101, 102, 108`, and the channels set contains `web` and `mobile`.

**Element order in `$addToSet` arrays is not guaranteed.** For `$push`, order reflects the order in which documents enter the stage; if ordering matters, design the pipeline to sort before collecting.

### 8.1. Difference Between Counting Rows and Summing Values

```javascript
{
  $group: {
    _id: "$customerId",
    numberOfOrders: { $sum: 1 },
    totalAmount: { $sum: "$total" }
  }
}
```

`$sum: 1` adds a constant for every document, whereas `$sum: "$total"` reads **the field's value**. These two expressions have completely different meanings despite both using `$sum`.

If `total` contains non-numeric values, numeric accumulators have specific rules: `$sum` and `$avg` ignore non-numeric values; if no valid numeric values exist, their outputs differ too. Therefore, `orderCount` does not necessarily equal the denominator used in averages when data has missing/invalid types. Schema validation or data hygiene should enforce numeric types before financial reporting.

For monetary values needing exact decimal precision, consider **BSON Decimal128** (`NumberDecimal` in `mongosh`) rather than storing amounts as strings or inappropriate binary floating-point numbers.

### 8.2. Taking First or Last Values Only When Order Is Explicit

To find the first and last order dates for each customer, you can use `$min` and `$max` directly because the field is a Date:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      earliestCreatedAt: { $min: "$createdAt" },
      latestCreatedAt: { $max: "$createdAt" }
    }
  }
])
```

To retrieve the **entire newest order** or a field tied to that exact newest order, `$sort` before `$group`, then pick `$first` or `$last`:

```javascript
db.orders.aggregate([
  { $sort: { customerId: 1, createdAt: -1, _id: -1 } },
  {
    $group: {
      _id: "$customerId",
      newestOrderId: { $first: "$_id" },
      newestOrderTotal: { $first: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

For `C01`, `newestOrderId` is `108` and `newestOrderTotal` is `210`.

Do not omit `$sort` and assume `$first` returns the document with the smallest `_id`: **`$first` takes the first document arriving in pipeline order**, not the min/max value automatically. When timestamps can tie, add a unique key like `_id` to stabilize selection.

## 9. Grouping by Arrays: Whole Array or Individual Elements?

If a document contains:

```javascript
{
  _id: 101,
  items: [
    { sku: "A", qty: 2 },
    { sku: "B", qty: 1 }
  ]
}
```

then the key:

```javascript
{
  $group: {
    _id: "$items",
    orderCount: { $sum: 1 }
  }
}
```

does not mean "group by each item." It groups documents by the **value of the entire `items` array**; arrays with different contents form different keys.

To aggregate **by each SKU inside the array**, split the elements first with **`$unwind`**:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      orderLines: { $sum: 1 },
      unitsOrdered: { $sum: "$items.qty" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Result on the sample dataset:

| SKU | Item lines `orderLines` | Total quantity `unitsOrdered` |
| --- | ---: | ---: |
| A | 3 | 5 |
| B | 3 | 4 |
| C | 3 | 6 |

Explanation:

- Product A appears in order `101` with qty 2, order `102` with qty 1, and order `106` with qty 2 → total 5.
- Product B appears in order `101` (1), `104` (2), and `107` (1) → total 4.
- Product C appears in order `103` (3), `106` (1), and `108` (2) → total 6.

`$unwind` turns **one order with multiple items into multiple input rows** for `$group`. Consequently, after unwind, `$sum: 1` counts **item lines**, **not unique orders**.

### 9.1. Counting Unique Orders per SKU

If the same SKU can appear multiple times within one order, `orderLines` does not equal the number of orders containing that SKU. Collect distinct order `_id` values:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      orderIds: { $addToSet: "$_id" },
      unitsOrdered: { $sum: "$items.qty" }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      uniqueOrderCount: { $size: "$orderIds" },
      unitsOrdered: 1
    }
  },
  { $sort: { sku: 1 } }
])
```

This example highlights **defining the counting unit**: order documents, line items, and unit quantities are three distinct metrics.

### 9.2. Empty Arrays and Missing Array Fields

`$unwind: "$items"` by default emits zero rows for documents with `items: []`, `items: null`, or missing `items`. Hence orders `105`, `109`, and `110` do not contribute to the SKU group table above.

When you need to retain those documents for another report, you can use:

```javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
```

However, decide the grouping key / accumulation strategy for orders without items to avoid creating an unintended `null` SKU group. Depending on the goal, filter out rows without a valid SKU before `$group`.

## 10. `$match` Before or After `$group`?

The placement of `$match` changes **what is filtered** and can impact performance.

### 10.1. Filtering Documents Before Grouping

Question: **"What is the total amount of paid orders per customer?"**

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      paidOrders: { $sum: 1 },
      paidAmount: { $sum: "$total" }
    }
  },
  { $sort: { paidAmount: -1 } }
])
```

Here only `paid` orders enter the group. On the sample dataset, the groups include `C01` with 3 orders totaling 510 and `C03` with 2 orders totaling 390.

### 10.2. Filtering Groups After Grouping

Question: **"Which customers have at least two orders, regardless of status?"**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $match: { orderCount: { $gte: 2 } } },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

The result includes `C01` (3 orders), `C02` (2 orders), and `C03` (2 orders). The `orderCount` field **only exists after `$group`**, so this condition must come afterward.

### Distinguishing the Two Condition Types

| Condition type | Example | Logical position |
| --- | --- | --- |
| Condition on source document | `status: "paid"`, `createdAt: {$gte: ...}` | `$match` before `$group` |
| Condition on aggregated metric | `orderCount: {$gte: 2}`, `totalAmount: {$gt: 500}` | `$match` after `$group` |

Placing `$match` early to restrict input documents usually reduces the records to aggregate and enables index usage. However, you cannot move a condition on `orderCount` ahead of when `orderCount` is computed while preserving the same meaning.

## 11. Choosing Grouping Keys from Business Requirements

Choosing a grouping key should start with **one clear business question**: "What does each row of the report represent?"

| Report requirement | Grouping key `_id` | Each result row represents |
| --- | --- | --- |
| System-wide total revenue | `null` | All filtered documents combined |
| Order count by status | `"$status"` | One status |
| Total amount by customer | `"$customerId"` | One customer |
| Order count by status and channel | `{status:"$status",channel:"$channel"}` | One status–channel pair |
| Order count by Vietnam calendar day | `{$dateToString:{date:"$createdAt",format:"%Y-%m-%d",timezone:"Asia/Ho_Chi_Minh"}}` | One calendar day in the chosen timezone |
| Order count by day and region | `{day:<computed_date>,region:"$region"}` | One day–region pair |
| Item quantity by SKU | `"$items.sku"` **after** `$unwind` | One SKU from item rows |
| Order count by price range | `{$cond: ...}` or price-bucketing expression | One defined price bracket |

### 11.1. Keys Too Broad or Too Granular

If you pick `_id: "$_id"` for orders, since source `_id` is unique, almost **every document becomes its own group**. That is rarely useful when summarizing multiple orders per customer. Conversely, `_id: null` yields only **one total row** and no longer distinguishes customers.

Example:

```javascript
// Practically every order becomes its own group
{ $group: { _id: "$_id", orderCount: { $sum: 1 } } }

// All orders into one group
{ $group: { _id: null, orderCount: { $sum: 1 } } }

// One group per customer
{ $group: { _id: "$customerId", orderCount: { $sum: 1 } } }
```

More components in a grouping key are not automatically better. An overly granular key can create nearly as many groups as documents, making reports hard to read and wasting processing memory. Add dimensions only when they provide genuine analytical value.

### 11.2. Considering Cardinality

**Grouping key cardinality** is the number of distinct values/groups in the input document set.

- A `status` key usually has few groups.
- A `customerId` key can have millions of groups.
- A composite key `customerId + day + SKU` can produce a huge number of groups.
- Keying by millisecond-precision timestamp can be nearly unique even when business only wants daily grouping.

High group counts expand the accumulator state that must be maintained. Whenever possible, group at the **required granularity**: by day rather than timestamp, by customer rather than order, or filter data before grouping.

### 11.3. Choosing Reusable, Unambiguous Key Types

In a report you can use:

```javascript
_id: {
  customerId: "$customerId",
  yearMonth: {
    $dateToString: {
      format: "%Y-%m",
      date: "$createdAt",
      timezone: "Asia/Ho_Chi_Minh"
    }
  }
}
```

This composite key lets you access each component cleanly and expresses "monthly revenue per customer." It is far better than concatenating values into a string without stable delimiter/escaping conventions.

## 12. Performance and Practical Limits of `$group`

`$group` is a **blocking stage** in many cases: it must process enough input data to build groups and accumulators before emitting aggregated output. This differs from streaming operations that can pass documents along immediately.

Grouping cost typically depends on:

- **Input document count** after `$match`.
- **Number of distinct groups** produced by `_id`.
- **State size per group**, especially when using `$push` or `$addToSet` to accumulate large arrays.
- **Cost of grouping-key expressions**, such as date or string processing.
- **Data distribution**, distinct value counts, and group skew.
- **Index utilization** in preceding stages, alongside optimization strategies in your MongoDB version.

### 12.1. Where Do Indexes Help?

Suppose most reports begin with:

```javascript
{ $match: { status: "paid" } }
```

An index on `status` can assist early filtering when selective. If the pipeline must sort before picking `$first`/`$last`, a compound index matching both filter and sort can also help.

However, having an index on `customerId` **does not automatically mean** `$group: {_id:"$customerId", total:{$sum:"$total"}}` only reads a few index entries. To sum all orders for every customer, MongoDB still must process the contributing values. Special optimizations can leverage indexes for certain group patterns, but do not assume every `$group` is directly accelerated by an index on the grouping key.

### 12.2. Managing Memory When Group Counts Are High

In given MongoDB versions/configurations, stages like `$group` enforce RAM usage limits and can spill temporary data to disk when allowed. You can configure the option:

```javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: "$customerId",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$total" }
      }
    }
  ],
  { allowDiskUse: true }
)
```

`allowDiskUse: true` permits eligible operations to use temporary disk storage per server capabilities; it is **not** a switch that makes grouping faster. Using disk can increase I/O and runtime. Limits and default behaviors for `allowDiskUse` vary by version and server settings, so check your target environment.

When a pipeline uses `$push: "$$ROOT"` to retain **entire documents for every group**, accumulated state can grow massive. Retain only needed fields, limit input sets, or redesign the report. Moreover, each result document remains subject to MongoDB's BSON document size limit; allowing disk spill does not lift the output document size limit.

### 12.3. `$sort` Before vs. After Group Has Different Effects

```javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: -1 } },
  {
    $group: {
      _id: "$customerId",
      newestOrderId: { $first: "$_id" }
    }
  }
])
```

`$sort` **before** group sets the input row order, thereby determining `$first`.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

`$sort` **after** group sorts the **resulting groups** by order count. A `$sort` after group cannot retroactively alter which document `$first` picked in the earlier group.

### 12.4. Inspecting Pipelines with `explain`

When investigating execution paths:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { totalAmount: -1 } }
])
```

The response may present the query planner, stages, and execution stats in different structures depending on MongoDB version and query engine. No single fixed metric fits every dataset; inspect scan stages, input counts, and group/sort costs in real context.

## 13. Using `$group` in the MongoDB Java Sync Driver

In Java applications, the MongoDB Sync Driver builds pipelines from `Bson` stages. Example grouping orders by `status`, counting orders, and summing totals:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class GroupOrdersDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI environment variable");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_aggregation_lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            List<Bson> pipeline = Arrays.asList(
                Aggregates.group(
                    "$status",
                    Accumulators.sum("orderCount", 1),
                    Accumulators.sum("totalAmount", "$total")
                ),
                Aggregates.sort(Sorts.ascending("_id"))
            );

            orders.aggregate(pipeline)
                .forEach(result ->
                    System.out.println(result.toJson())
                );
        }
    }
}
```

The example requires a compatible `mongodb-driver-sync` dependency, the populated practice database, and the `MONGODB_URI` environment variable. In Java:

- `Aggregates.group("$status", ...)` corresponds to `{$group:{_id:"$status",...}}`.
- `Accumulators.sum("orderCount", 1)` corresponds to `orderCount:{$sum:1}`.
- `Accumulators.sum("totalAmount", "$total")` corresponds to `totalAmount:{$sum:"$total"}`.
- `Aggregates.sort(...)` sorts the groups after computation.

### 13.1. Composite Grouping Keys in Java

To group by `status` and `channel`:

```java
Document compoundId = new Document("status", "$status")
    .append("channel", "$channel");

List<Bson> pipeline = Arrays.asList(
    Aggregates.group(
        compoundId,
        Accumulators.sum("orderCount", 1),
        Accumulators.sum("totalAmount", "$total")
    ),
    Aggregates.sort(Sorts.ascending("_id.status", "_id.channel"))
);
```

Here `Document` constructs the **grouping key expression**, not a data document inserted into a collection. The values `"$status"` and `"$channel"` are MongoDB field paths, not literal strings `"status"` and `"channel"`.

When using Spring Data MongoDB or other frameworks, the aggregation builder API differs, but the core principle that `_id` defines groups and accumulators compute over group inputs remains the same.

## 14. Common Mistakes When Using `$group`

| Situation | Common cause | Resolution |
| --- | --- | --- |
| Every document lands in a single `"status"` group | Wrote `_id: "status"` instead of `_id: "$status"` | Use a `$`-prefixed field path |
| Every document unexpectedly lands in a `null` group | Wrong field path or documents lack the grouping field | Check schema and paths, test `$project` on the field first |
| Missing and null groups merge together | Simple field-path key does not separate both states | Normalize intentionally or include `$type` in a composite key |
| Grouping by `createdAt` creates too many groups | Key is exact timestamp instead of day | Use `$dateTrunc` or `$dateToString` |
| Daily report shifts near midnight | Inconsistent timezone handling | Specify the business timezone explicitly |
| Total amount differs from order count times expected price | `$sum: "$total"` differs from `$sum: 1`; data may have wrong types | Verify BSON types and metric definitions |
| Order count per SKU is wrong | `$unwind` splits multi-item orders into multiple rows | Distinguish order lines, units, and unique order IDs |
| `$group` by `items` does not split by SKU | Grouping by the **entire array** | Use `$unwind` before grouping by item fields |
| `$first` returns an order that is not the newest | Missing or nondeterministic input sort | `$sort` by timestamp and unique key before grouping |
| Group output order varies across runs | `$group` does not guarantee output order | Add `$sort` after group |
| `$match` on `orderCount` placed before group | Aggregated field does not exist yet | Place the metric filter after group |
| High group count exhausts RAM | Grouping key cardinality too high or large array accumulators | Filter early, pick right granularity, evaluate memory/spill |
| Expecting `$addToSet` array to have fixed order | Distinct set has no ordering guarantee | Sort results as needed |
| Putting a raw source field directly beside `_id` | Group output fields require a proper accumulator | Use `$first`, `$last`, or appropriate aggregation after defining intent |

## 15. Practice Exercises

The following exercises use the unmodified ten-order dataset from section 2. Read each requirement as a decision on **what each group represents** before writing syntax.

### Exercise 1. Counting Orders by Status

Task: produce a report with status, order count, and total amount. Sort by order count descending.

**Reference answer:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

The `paid` group has 5 orders, `pending` 3, `cancelled` 1, and the missing-status group 1.

### Exercise 2. Revenue Statistics by Customer

Task: take only paid orders, group by customer, and return customers whose paid total exceeds 400.

**Reference answer:**

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      paidAmount: { $sum: "$total" }
    }
  },
  { $match: { paidAmount: { $gt: 400 } } },
  { $sort: { paidAmount: -1 } }
])
```

Only `C01` is returned with `paidAmount: 510`. `C03` totals 390, which does not exceed 400.

### Exercise 3. Composite Grouping Key

Task: count orders and sum total amount for each `status`–`channel` pair.

**Reference answer:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  }
])
```

The two groups `{status:"paid",channel:"web"}` and `{status:"paid",channel:"mobile"}` are **two distinct groups**, despite sharing the same status.

### Exercise 4. Grouping by Day in Vietnam

Task: compute daily order counts using Vietnam calendar days, returning date strings formatted as `YYYY-MM-DD`.

**Reference answer:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

Daily counts are 3, 3, and 4 orders for 2026-11-10, 2026-11-11, and 2026-11-12.

### Exercise 5. Total Quantity Sold by SKU

Task: each result row represents **one SKU**, with total quantity summed from `items.qty`.

**Reference answer:**

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.qty" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Result: SKU `A` = 5, `B` = 4, `C` = 6. If you used `_id: "$items"` without unwinding, you would group by **each order's entire items array**, not by SKU.

### Exercise 6. Distinguishing Null and Missing in Grouping Keys

Task: group by `region`, keeping documents **without region** separate from documents with `region: null`.

**Reference answer:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        regionType: { $type: "$region" },
        regionValue: { $ifNull: ["$region", null] }
      },
      orderCount: { $sum: 1 }
    }
  }
])
```

In the sample dataset, `109` falls into the `regionType: "missing"` group, while `110` falls into the `regionType: "null"` group.

### Exercise 7. Why `$first` Does Not Guarantee the Earliest Order

A pipeline states:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      earliestOrderId: { $first: "$_id" }
    }
  }
])
```

Question: Is `earliestOrderId` guaranteed to be the customer's earliest created order?

**Answer:** No. `$first` takes the first document **in the order documents enter the stage**, without automatically finding the minimum timestamp. Add `$sort: {customerId:1, createdAt:1, _id:1}` before `$group` to use `$first`, or use a `$min` calculation if you only need the earliest date.

### Exercise 8. Recognizing Overly Granular Groups

A report asks for "order count per customer," yet someone writes `_id: {customerId:"$customerId",orderId:"$_id"}`. Does this still produce a per-customer report?

**Answer:** Not at the desired granularity. Because every `orderId` is unique, practically every order forms its own group, making `orderCount` almost always 1. Use only `_id: "$customerId"` for a per-customer report.

## 16. Summary of Choosing Grouping Keys

Before writing `$group`, express the requirement as **"each result row corresponds to one ..."**. The rest of the sentence guides how to design `_id`:

1. **One overall total:** `_id: null`.
2. **One field value:** `_id: "$fieldName"`.
3. **A multi-dimensional combination:** `_id: {a:"$fieldA",b:"$fieldB"}`.
4. **A day, bucket, or value category:** `_id` is an aggregation expression such as `$dateToString`, `$dateTrunc`, or `$cond`.
5. **An element inside an array:** consider `$unwind` followed by grouping on the element's field.

Only after choosing the key should you choose **accumulators**: `$sum:1` to count input rows, `$sum:"$total"` to sum values, `$avg` for averages, `$min`/`$max` for extremes, and `$push`/`$addToSet` when you genuinely need collections of values.

Finally, remember that `$group` **does not guarantee output order**; `$first`/`$last` are only well-defined when the input is sorted properly; missing or null keys need an explicit policy; and both group count and accumulator state size can significantly affect memory cost. Designing grouping keys around **business granularity**, not merely existing fields, is the foundation for accurate, maintainable MongoDB reports.