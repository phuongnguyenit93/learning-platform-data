# Reading Aggregation Results with Cursors and Verifying Each Stage in MongoDB

## 1. Lesson Objectives

In MongoDB, an **aggregation pipeline** processes documents through a sequence of stages such as `$match`, `$project`, `$unwind`, `$group`, `$sort`, and `$limit`. Each stage receives data from the preceding stage and produces input data for the next stage. The final results are usually returned to the application via a **cursor**, not necessarily an array loaded all at once into RAM.

This lesson addresses two skills that go hand in hand:

1. **Reading results properly:** using aggregation cursors in `mongosh` and drivers; choosing among `toArray()`, `forEach()`, and `hasNext()/next()`; understanding batches, `getMore`, closing cursors, and resource limits.
2. **Verifying each stage:** splitting a pipeline into prefixes, comparing documents before and after each transformation, cross-checking counts, values, and BSON types; using `explain()` to understand execution plans without confusing them with business results.

After this lesson, you will know how to spot an inflated revenue total caused by `$unwind`, a wrong count caused by `$group`, a missing field caused by `$project`, or a slow query caused by blocking stages like `$sort`.

> **Scope:** Examples focus on read pipelines. Write stages such as `$merge` and `$out` have side effects and must not be placed into arbitrary intermediate inspection utilities.

## 2. Operational Model: Pipeline and Cursor

The processing flow can be pictured as:

~~~text
Collection orders
       |
       v
   $match          -> select PAID orders
       |
       v
   $project        -> retain needed fields
       |
       v
   $unwind         -> each item becomes one logical document
       |
       v
   $set            -> compute line total per item
       |
       v
   $group          -> aggregate by SKU
       |
       v
   $sort           -> rank by revenue
       |
       v
   $limit          -> take top groups
       |
       v
Aggregation cursor
       |
       +-- next()/hasNext(): sequential reading
       +-- forEach():       process each document
       +-- toArray():       collect all results into an array
       +-- close():         release cursor resources
~~~

Some stages can process in a streaming fashion, while stages like `$group` and `$sort` may need to read and buffer substantial input data before emitting output. Therefore, a cursor is a mechanism for **reading output results**, **not a guarantee that every stage processes one document and immediately emits one document**.

Important distinctions:

| Object/concept | Purpose |
| --- | --- |
| **Aggregation pipeline** | Ordered sequence of stages defining data transformations |
| **Aggregation result document** | A document produced at the pipeline's output |
| **Aggregation cursor** | Interface for a client to read result documents sequentially |
| **Batch** | A group of result documents transmitted from server to client |
| **`getMore`** | Command fetching the next batch from an active cursor |
| **`explain`** | Diagnostic info about the plan and execution, not business result rows |

A pipeline can return **0, 1, 10, or millions of documents**. Cursors keep applications from having to load millions of results into memory all at once.

## 3. Preparing Practice Data Easy to Cross-Check by Hand

Connect to MongoDB with **mongosh** and create an isolated database:

~~~javascript
var lab = db.getSiblingDB("aggregation_cursor_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O01",
    status: "PAID",
    customerId: "C01",
    region: "north",
    createdAt: ISODate("2026-01-03T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 2, unitPrice: 100 },
      { sku: "MS", quantity: 1, unitPrice: 50 }
    ]
  },
  {
    _id: "O02",
    status: "PAID",
    customerId: "C02",
    region: "south",
    createdAt: ISODate("2026-01-04T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 1, unitPrice: 100 },
      { sku: "PAD", quantity: 2, unitPrice: 30 }
    ]
  },
  {
    _id: "O03",
    status: "PENDING",
    customerId: "C01",
    region: "north",
    createdAt: ISODate("2026-01-05T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 5, unitPrice: 100 }
    ]
  },
  {
    _id: "O04",
    status: "PAID",
    customerId: "C03",
    region: "north",
    createdAt: ISODate("2026-01-06T08:00:00Z"),
    items: [
      { sku: "MS", quantity: 3, unitPrice: 50 }
    ]
  },
  {
    _id: "O05",
    status: "PAID",
    customerId: "C01",
    region: "south",
    createdAt: ISODate("2026-01-07T08:00:00Z"),
    items: [
      { sku: "MS", quantity: 2, unitPrice: 50 },
      { sku: "PAD", quantity: 1, unitPrice: 30 }
    ]
  },
  {
    _id: "O06",
    status: "CANCELLED",
    customerId: "C04",
    region: "south",
    createdAt: ISODate("2026-01-08T08:00:00Z"),
    items: [
      { sku: "PAD", quantity: 4, unitPrice: 30 }
    ]
  },
  {
    _id: "O07",
    status: "PAID",
    customerId: "C02",
    region: "north",
    createdAt: ISODate("2026-01-09T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 1, unitPrice: 100 },
      { sku: "MS", quantity: 1, unitPrice: 50 },
      { sku: "PAD", quantity: 1, unitPrice: 30 }
    ]
  },
  {
    _id: "O08",
    status: "PAID",
    customerId: "C03",
    region: "south",
    createdAt: ISODate("2026-01-10T08:00:00Z"),
    items: []
  },
  {
    _id: "O09",
    status: "PAID",
    customerId: "C05",
    region: "north",
    createdAt: ISODate("2026-01-11T08:00:00Z")
    // Intentionally missing the items field.
  }
]);

lab.orders.find(
  {},
  { _id: 1, status: 1, items: 1 }
).sort({ _id: 1 });
~~~

There are **9 orders** in total:

- **7 PAID orders:** O01, O02, O04, O05, O07, O08, and O09.
- **1 PENDING order:** O03.
- **1 CANCELLED order:** O06.
- **O08** has `items: []`; **O09** lacks the `items` field.

The last two cases help spot stages that **reduce output document counts**. In the sample data, `unitPrice` and `quantity` are small integers so totals can be checked by hand; for real currency, choose an appropriate numeric type and rounding policy such as Decimal128.

**Never run `drop()` on a production collection.** The dataset in `aggregation_cursor_lab` is strictly for practice.

## 4. Writing a Revenue Report Pipeline by SKU

Goal: count only items from paid orders, then return the **top two SKUs by revenue**.

~~~javascript
var pipeline = [
  // Stage 1: only paid orders.
  {
    $match: {
      status: "PAID"
    }
  },

  // Stage 2: keep fields needed for calculation.
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerId: 1,
      region: 1,
      items: 1
    }
  },

  // Stage 3: each item becomes one logical row.
  {
    $unwind: "$items"
  },

  // Stage 4: compute revenue for the item line.
  {
    $set: {
      lineTotal: {
        $multiply: ["$items.quantity", "$items.unitPrice"]
      }
    }
  },

  // Stage 5: group rows sharing the same SKU.
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalRevenue: { $sum: "$lineTotal" },
      lineCount: { $sum: 1 }
    }
  },

  // Stage 6: use API-friendly field names.
  {
    $project: {
      _id: 0,
      sku: "$_id",
      totalQuantity: 1,
      totalRevenue: 1,
      lineCount: 1
    }
  },

  // Stage 7: highest revenue first; sku as tie-breaker.
  {
    $sort: {
      totalRevenue: -1,
      sku: 1
    }
  },

  // Stage 8: keep only the top 2 groups.
  {
    $limit: 2
  }
];
~~~

Run:

~~~javascript
var cursor = lab.orders.aggregate(pipeline);

cursor.toArray();
~~~

Output values:

~~~javascript
[
  {
    sku: "KB",
    totalQuantity: 4,
    totalRevenue: 400,
    lineCount: 3
  },
  {
    sku: "MS",
    totalQuantity: 7,
    totalRevenue: 350,
    lineCount: 4
  }
]
~~~

`PAD` does not appear in the final output because of `$limit: 2`, **not because its total revenue is 0**. When checking `$group` before `$limit`, you will see the PAD group has revenue 120.

### Manual Arithmetic Verification

| SKU | Lines in PAID orders | Units sold | Revenue |
| --- | --- | ---: | ---: |
| KB | O01: 2 × 100; O02: 1 × 100; O07: 1 × 100 | 4 | **400** |
| MS | O01: 1 × 50; O04: 3 × 50; O05: 2 × 50; O07: 1 × 50 | 7 | **350** |
| PAD | O02: 2 × 30; O05: 1 × 30; O07: 1 × 30 | 4 | **120** |
| **Total** | 10 item lines across 5 orders with items | **15** | **870** |

Even though there are **7 PAID orders**, only **5 PAID orders have at least one item**. When grouping by SKU after default `$unwind`, O08 and O09 contribute zero rows.

## 5. How Does Aggregation Return a Cursor?

### 5.1. `aggregate()` Returns a Cursor, Not a JavaScript Array

In `mongosh`, for a standard read pipeline:

~~~javascript
var resultCursor = lab.orders.aggregate(pipeline);
~~~

`resultCursor` is a cursor object. It provides methods such as:

~~~javascript
resultCursor.hasNext();
resultCursor.next();
resultCursor.toArray();
resultCursor.forEach(doc => printjson(doc));
resultCursor.close();
~~~

**Pick only one consumption strategy per cursor.** Once `toArray()` has been called, all elements are consumed; you cannot expect `next()` to return the first element again.

To read results from the start again, create a **new cursor with a new aggregate call**:

~~~javascript
var again = lab.orders.aggregate(pipeline);
again.toArray();
~~~

A cursor is **not a static copy of data stored in a variable**. It represents the result stream of one execution; source data can change between separate command invocations.

### 5.2. Using `toArray()` When Output Is Small

~~~javascript
var smallCursor = lab.orders.aggregate(pipeline);
var rows = smallCursor.toArray();

printjson(rows);
print("Number of groups returned: " + rows.length);
~~~

Advantages:

- Easy to experiment in `mongosh`.
- Easy to inspect the entire small output.
- Can use JavaScript `map()`, `filter()`, and `reduce()` for cross-checking.

Limitations:

- `toArray()` **loads all remaining results into client memory**.
- On large result sets, it can spike RAM and slow down or crash the application.
- On a partially read cursor, `toArray()` only fetches **the remaining elements** without re-reading already consumed ones.

Example:

~~~javascript
var c = lab.orders.aggregate(pipeline);
var firstDoc = c.next();

printjson(firstDoc);
printjson(c.toArray()); // Only the second group remains.
~~~

For a top-2 report, `toArray()` is fine. For exporting millions of rows, process sequentially or in batches.

### 5.3. Reading Sequentially with `hasNext()` and `next()`

~~~javascript
var c = lab.orders.aggregate(pipeline);

while (c.hasNext()) {
  var row = c.next();

  print(row.sku + ": " + row.totalRevenue);
}

c.close();
~~~

`hasNext()` checks whether more elements remain, potentially fetching another batch from the server. `next()` returns the next document; do not call `next()` after the cursor is exhausted unless handling the error case.

This pattern fits when:

- You want to process one record at a time instead of buffering all output.
- You need to stop early based on application-specific logic.
- You want to stream records row-by-row to a file or output stream.

### 5.4. Using `forEach()`

~~~javascript
var c = lab.orders.aggregate(pipeline);

c.forEach(doc => {
  print(doc.sku + " | qty=" + doc.totalQuantity +
        " | revenue=" + doc.totalRevenue);
});
~~~

`forEach()` invokes the callback for each returned document and exhausts the cursor. When the callback can throw errors, handle exceptions and close the cursor appropriately. Do not reuse the same cursor after iteration finishes expecting fresh data.

### 5.5. Stopping Early and Closing the Cursor

For pipelines returning many results, you can read a few documents and stop:

~~~javascript
var c = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { _id: 1 } }
]);

var readCount = 0;

try {
  while (c.hasNext() && readCount < 3) {
    printjson(c.next());
    readCount++;
  }
} finally {
  c.close();
}
~~~

Closing a cursor early releases client- and server-side resources when the cursor is still open. For pipelines with blocking stages, the server may have already processed significant data before your first `next()` call, so stopping on the client after three rows **does not mean the server only processed three documents**.

## 6. Batch Size, getMore, and How Cursors Fetch Data

### 6.1. Cursors Read Results in Batches

MongoDB does not necessarily send one document per network request. Instead, the server returns a **first batch** followed by subsequent batches via `getMore` as needed.

~~~text
Client sends aggregate(pipeline)
          |
          v
MongoDB executes and returns firstBatch + cursor id (if more data remains)
          |
          v
Client reads documents in the current batch
          |
          +--- more in batch: read directly
          |
          +--- batch exhausted, cursor open: getMore
                                    |
                                    v
                                next batch
~~~

`batchSize` is the **configured target maximum number of documents per batch**, not the total document count of the aggregation. The server also caps batch sizes by message/BSON limits and may return fewer than requested.

### 6.2. Specifying Batch Size in mongosh

Depending on your `mongosh` API, you can configure cursor batch size when calling `aggregate()`:

~~~javascript
var c = lab.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { _id: 1 } }
  ],
  {
    cursor: { batchSize: 2 }
  }
);

c.forEach(doc => print(doc._id));
~~~

Or use the cursor configuration method if supported by your cursor API version:

~~~javascript
var c2 = lab.orders.aggregate([
  { $match: { status: "PAID" } }
]);

c2.batchSize(2);
c2.toArray();
~~~

The point is that **batch size tunes network delivery**, without changing filters, sort order, or logical result counts.

For the sample pipeline with `$limit: 2`, changing batch size cannot make the server return three SKUs. To get three SKUs, change `$limit` or remove that stage.

### 6.3. Batch Size Is Not $limit

| Setting | What is bounded? |
| --- | --- |
| `$limit: 2` in pipeline | **Total number of result documents** at that pipeline stage |
| `cursor: { batchSize: 2 }` | Size of each chunk of data returned to the client |
| `find().limit(2)` | Number of documents returned by find, not array elements inside each document |
| `$slice` on an array | Number of elements taken from the array, not cursor batch size |

Example:

~~~javascript
// Returns 7 PAID documents, in small batches.
var c = lab.orders.aggregate(
  [{ $match: { status: "PAID" } }],
  { cursor: { batchSize: 2 } }
);

print(c.toArray().length); // 7
~~~

### 6.4. Cursor Timeout and Lifecycle

A server-side cursor can close because:

- All results have been read.
- The client closed the cursor.
- The connection or session ended.
- The cursor sat idle past the configured timeout and was reclaimed by the server.
- A query error, timeout, or administrative condition occurred.

Do not keep cursors alive across long user pauses in a REST API. For multi-request HTTP pagination, run a fresh query per page using **keyset cursor tokens or pagination filters** rather than holding a server cursor open for long periods.

Depending on version/driver, `noCursorTimeout` or session settings exist, but never make them the default because long-lived cursors tie up server resources and sessions still have their own lifecycle.

## 7. Verifying Pipelines Stage by Stage with Prefix Runs

Aggregation bugs happen easily when many stages are chained. The surest way to verify **data semantics** is running each **prefix** of the pipeline:

~~~text
P1 = [stage1]
P2 = [stage1, stage2]
P3 = [stage1, stage2, stage3]
...
P8 = [stage1, ..., stage8]
~~~

Each `Pk` shows what documents look like **immediately after stage k logically**.

### 7.1. Helper Function to Inspect a Prefix Output

In `mongosh`:

~~~javascript
function inspectStage(pipeline, stageCount, sampleSize = 5) {
  if (!Number.isInteger(stageCount) ||
      stageCount < 1 || stageCount > pipeline.length) {
    throw new Error("Invalid stageCount");
  }

  if (!Number.isInteger(sampleSize) || sampleSize < 1) {
    throw new Error("sampleSize must be >= 1");
  }

  // Create a new pipeline without mutating the original pipeline array.
  var prefix = pipeline.slice(0, stageCount);

  // Adding limit at the end of the prefix avoids printing excessive output.
  var preview = prefix.concat([{ $limit: sampleSize }]);

  print("After stage " + stageCount +
        " | " + Object.keys(pipeline[stageCount - 1])[0]);

  lab.orders.aggregate(preview).forEach(printjson);
}
~~~

Call:

~~~javascript
inspectStage(pipeline, 1); // after $match
inspectStage(pipeline, 2); // after $project
inspectStage(pipeline, 3); // after $unwind
inspectStage(pipeline, 4); // after $set
inspectStage(pipeline, 5); // after $group
inspectStage(pipeline, 6); // after second $project
inspectStage(pipeline, 7); // after $sort
inspectStage(pipeline, 8); // after $limit
~~~

**Two crucial caveats:**

- `$limit` is **appended at the end of the prefix**, never inserted into the middle of the original pipeline and then used to claim the full pipeline keeps the same semantics. In particular, placing `$limit` before `$group` or `$sort` alters aggregations or ordering.
- With blocking stages like `$group`/`$sort`, a `$limit` at the end of the prefix can still force the server to process most or all input. This only **caps printed rows**, not a guarantee of a cheap query.

For pipelines with `$out` or `$merge`, **never run an automated prefix-inspection helper** like this if the prefix includes a write stage; "previewing" would write data. All examples in this lesson are read pipelines.

### 7.2. Using Intentional $limit and $sort for Inspection

To inspect a **deterministic** sample before building a complex pipeline, run a **dedicated debug query**:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { _id: 1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, items: 1 } }
]);
~~~

This is a **data-exploration pipeline**, not a prefix identical to the main reporting pipeline. It helps inspect a few comparable documents, but never use three sample documents to assert collection-wide revenue totals.

To inspect **all groups** produced by `$group`, run the prefix up to `$group` **without adding a limit that hides groups**.

## 8. Verifying Stage 1: $match

The first stage filters paid orders:

~~~javascript
lab.orders.aggregate([
  {
    $match: { status: "PAID" }
  }
]).toArray();
~~~

The result must contain **7** documents:

~~~text
O01, O02, O04, O05, O07, O08, O09
~~~

Count directly:

~~~javascript
var matched = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "orderCount" }
]).toArray();

printjson(matched);
// [{ orderCount: 7 }]
~~~

Or compare:

~~~javascript
lab.orders.countDocuments({ status: "PAID" }); // 7
~~~

**What to verify:**

- Did it match the exact `"PAID"` enum value, or does data contain `"paid"`/`"Paid"`?
- Are there records missing `status`?
- Does the query include required tenant, authorization, or date constraints?
- Does the count match business rules?

Logically, `$match` only keeps or drops documents; it **never turns one document into multiple documents**. If the count increases after `$match`, check your measurement or whether source data changed between runs.

## 9. Verifying Stage 2: $project

Use the two-stage prefix:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 2))
  .forEach(printjson);
~~~

Sample document:

~~~javascript
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: [
    { sku: "KB", quantity: 2, unitPrice: 100 },
    { sku: "MS", quantity: 1, unitPrice: 50 }
  ]
}
~~~

The `$project` stage in the pipeline:

~~~javascript
{
  $project: {
    _id: 0,
    orderId: "$_id",
    customerId: 1,
    region: 1,
    items: 1
  }
}
~~~

Cross-check:

- `_id` is removed from output.
- The original `_id` value is mapped to `orderId`.
- `customerId`, `region`, and `items` are retained.
- `status` and `createdAt` no longer appear in the prefix output because they were not included.
- Document count remains **7**; only document shape changed.

**Common bug:** if a subsequent stage tries to use `"$status"` or `"$createdAt"` after `$project` dropped them, expressions receive missing/null and produce wrong results. When inspecting prefixes, verify every field needed by downstream stages.

`$project` does not have to sit earliest in every pipeline. The MongoDB optimizer can automatically prune unused fields. Use `$project` intentionally to standardize output, rather than assuming it always speeds up queries.

## 10. Verifying Stage 3: $unwind

Run:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 3))
  .forEach(printjson);
~~~

`$unwind: "$items"` produces **one result document per element of the items array**. Order O01 has two items, becoming two logical documents:

~~~javascript
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: { sku: "KB", quantity: 2, unitPrice: 100 }
}
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: { sku: "MS", quantity: 1, unitPrice: 50 }
}
~~~

Row count per order:

| PAID order | Items elements | Rows after default $unwind |
| --- | ---: | ---: |
| O01 | 2 | 2 |
| O02 | 2 | 2 |
| O04 | 1 | 1 |
| O05 | 2 | 2 |
| O07 | 3 | 3 |
| O08 | 0 | 0 |
| O09 | Missing field | 0 |
| **Total** | **10 real elements** | **10 rows** |

Therefore:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 3),
  { $count: "rowsAfterUnwind" }
]).toArray();
// [{ rowsAfterUnwind: 10 }]
~~~

**Why verify at this step?**

If you accidentally count `$sum: 1` after `$unwind`, you are counting **item rows**, not **orders**. An order with three items gets counted three times. The `10` at this step must never be called "10 PAID orders."

### 10.1. preserveNullAndEmptyArrays Changes Cardinality

If business rules require keeping O08 and O09:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $unwind: {
      path: "$items",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      items: 1
    }
  }
]).toArray();
~~~

With `preserveNullAndEmptyArrays: true`, documents with empty arrays, null, or missing fields are retained; on this dataset, total documents after unwind becomes **12** (10 item rows plus O08/O09).

If subsequent stages compute `$multiply` or `$group` by `items.sku`, handle the two documents lacking valid items. **Never turn preserve on just to keep counts and assume all downstream aggregations handle empty rows automatically.**

### 10.2. includeArrayIndex to Identify Element Order

When checking which array element generated a row:

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O01" } },
  {
    $unwind: {
      path: "$items",
      includeArrayIndex: "itemIndex"
    }
  },
  {
    $project: {
      _id: 1,
      itemIndex: 1,
      items: 1
    }
  }
]);
~~~

O01 yields two rows with `itemIndex` 0 and 1. This is very helpful when suspecting malformed array elements or debugging `$unwind` output.

## 11. Verifying Stage 4: $set and Computed Expressions

The `$set` stage adds the `lineTotal` field:

~~~javascript
{
  $set: {
    lineTotal: {
      $multiply: ["$items.quantity", "$items.unitPrice"]
    }
  }
}
~~~

Read the prefix through stage 4:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 4))
  .forEach(doc => {
    print(doc.orderId + " | " +
          doc.items.sku + " | " +
          doc.items.quantity + " x " +
          doc.items.unitPrice + " = " +
          doc.lineTotal);
  });
~~~

Printed rows:

~~~text
O01 | KB  | 2 x 100 = 200
O01 | MS  | 1 x 50  = 50
O02 | KB  | 1 x 100 = 100
O02 | PAD | 2 x 30  = 60
O04 | MS  | 3 x 50  = 150
O05 | MS  | 2 x 50  = 100
O05 | PAD | 1 x 30  = 30
O07 | KB  | 1 x 100 = 100
O07 | MS  | 1 x 50  = 50
O07 | PAD | 1 x 30  = 30
~~~

This stage preserves cardinality: **10 documents in, 10 documents out**.

Verify totals with a cross-check pipeline:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 4),
  {
    $group: {
      _id: null,
      lines: { $sum: 1 },
      quantity: { $sum: "$items.quantity" },
      revenue: { $sum: "$lineTotal" }
    }
  }
]).toArray();
// [{ _id: null, lines: 10, quantity: 15, revenue: 870 }]
~~~

In real applications, check:

- Are `quantity` and `unitPrice` BSON numeric types or strings?
- Can null/missing values enter `$multiply`?
- Should the output type be int32, int64, double, or Decimal128?
- Are rounding rules and currency units standardized?

With `$sum`, non-numeric values in many contexts are silently skipped; that can **silently undercount revenue** if input data is unnormalized. Never treat a sum of 0 as proof that every item had value 0.

## 12. Verifying Stage 5: $group

The `$group` stage receives 10 item rows and groups by SKU:

~~~javascript
{
  $group: {
    _id: "$items.sku",
    totalQuantity: { $sum: "$items.quantity" },
    totalRevenue: { $sum: "$lineTotal" },
    lineCount: { $sum: 1 }
  }
}
~~~

Run prefix:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 5))
  .toArray();
~~~

Expected values, **without guaranteed order**:

~~~javascript
[
  { _id: "KB", totalQuantity: 4, totalRevenue: 400, lineCount: 3 },
  { _id: "MS", totalQuantity: 7, totalRevenue: 350, lineCount: 4 },
  { _id: "PAD", totalQuantity: 4, totalRevenue: 120, lineCount: 3 }
]
~~~

**Never trust the display order of `$group`.** This stage does not guarantee output order. The array above illustrates the **set of values**, not the exact order the server must emit.

### 12.1. Verifying Group Count

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  { $count: "skuCount" }
]).toArray();
// [{ skuCount: 3 }]
~~~

From **10 item rows**, `$group` produces **3 SKU groups**. Dropping from 10 down to 3 is **intentional**, not a bug losing documents.

### 12.2. Verifying Grand Totals After Grouping

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  {
    $group: {
      _id: null,
      grandRevenue: { $sum: "$totalRevenue" },
      grandQuantity: { $sum: "$totalQuantity" },
      grandLines: { $sum: "$lineCount" }
    }
  }
]).toArray();
// [{ _id: null, grandRevenue: 870, grandQuantity: 15, grandLines: 10 }]
~~~

These three totals must equal the pre-`$group` totals from section 11 when business logic is simple addition. This is a very useful **invariant** to catch bugs from changed grouping keys, filters, or item duplication.

### 12.3. Do Not Confuse Orders with Line Items

In the sample data:

- There are **7 PAID orders**.
- There are **5 PAID orders with items**.
- There are **10 item lines**.
- There are **3 SKUs**.

If a dashboard needs "order count," never take `lineCount` and label it `orderCount`. To count distinct orders per SKU, use `$addToSet: "$orderId"` and take its size afterward, as that measures a different quantity:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 4),
  {
    $group: {
      _id: "$items.sku",
      orderIds: { $addToSet: "$orderId" }
    }
  },
  {
    $project: {
      sku: "$_id",
      _id: 0,
      orderCount: { $size: "$orderIds" }
    }
  },
  { $sort: { sku: 1 } }
]);
~~~

In the sample data, each SKU appears at most once per order; if an order had two items with the same SKU, `lineCount` would differ from distinct orders, while `$addToSet` deduplicates order IDs.

## 13. Verifying Stages 6–8: Projection, Sort, and Limit

### 13.1. Stage 6: Naming Output Fields

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 6))
  .toArray();
~~~

The `$project` stage:

~~~javascript
{
  $project: {
    _id: 0,
    sku: "$_id",
    totalQuantity: 1,
    totalRevenue: 1,
    lineCount: 1
  }
}
~~~

After this stage, results must have:

- `sku` holding the SKU code, replacing grouping key `_id`.
- `totalQuantity`, `totalRevenue`, and `lineCount` preserved.
- No `_id` in the response.

There are still **3 documents**, but the shape changed. When clients report missing `sku` or an unexpected `_id` field, check this stage first.

### 13.2. Stage 7: Sort Needs a Tie-Breaker Rule If Required

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 7))
  .toArray();
~~~

Results in descending revenue order:

~~~text
KB  400
MS  350
PAD 120
~~~

The stage:

~~~javascript
{
  $sort: {
    totalRevenue: -1,
    sku: 1
  }
}
~~~

The `sku` field serves as a secondary sort key for deterministic ordering when revenues tie. Without a tie-breaker, tied SKUs have no guaranteed order—especially critical before `$limit` or pagination.

### 13.3. Stage 8: Limit Retains Only the Top Two Groups

~~~javascript
lab.orders.aggregate(pipeline).toArray();
~~~

Only **KB** and **MS** remain. When checking the dataset's total `870`, **do not sum after `$limit: 2`** and conclude total revenue is 750. The `$limit` stage intentionally excluded PAD from the top-2 list.

Summary table:

| Stage | Stage name | Output docs in lab | Primary meaning |
| ---: | --- | ---: | --- |
| Source | `orders` | 9 | All orders |
| 1 | `$match` | 7 | Keep PAID orders |
| 2 | `$project` | 7 | Reshape fields |
| 3 | `$unwind` | 10 | Expand item array into rows |
| 4 | `$set` | 10 | Add lineTotal |
| 5 | `$group` | 3 | Group by SKU |
| 6 | `$project` | 3 | Rename fields |
| 7 | `$sort` | 3 | Sort order |
| 8 | `$limit` | 2 | Take top 2 |

**How to read the table:** stages changing cardinality in this pipeline are `$match`, `$unwind`, `$group`, and `$limit`. `$project`/`$set`/`$sort` neither create nor drop documents here, though they alter displayed fields and result ordering.

## 14. Helper Function to Measure Document Counts at Each Prefix

When checking **exact counts**, do not use a `$limit` preview and count printed lines. Run the actual prefix and append `$count`:

~~~javascript
function countAfterStage(pipeline, stageCount) {
  if (!Number.isInteger(stageCount) ||
      stageCount < 1 || stageCount > pipeline.length) {
    throw new Error("Invalid stageCount");
  }

  var prefix = pipeline.slice(0, stageCount);

  var result = lab.orders.aggregate([
    ...prefix,
    { $count: "n" }
  ]).toArray();

  // $count on empty input returns zero documents.
  return result.length === 0 ? 0 : result[0].n;
}

for (var i = 1; i <= pipeline.length; i++) {
  print("After stage " + i + ": " +
        countAfterStage(pipeline, i));
}
~~~

Results on unmodified data:

~~~text
After stage 1: 7
After stage 2: 7
After stage 3: 10
After stage 4: 10
After stage 5: 3
After stage 6: 3
After stage 7: 3
After stage 8: 2
~~~

**Operational warning:** each call to `countAfterStage()` **re-runs the pipeline from the source**, without reusing previous results. On large collections or pipelines heavy with `$lookup`, `$group`, and `$sort`, counting every prefix can be very resource-intensive. Use it only in lab, staging, on a pre-filtered sample, or with proper load monitoring.

Do not append `$count` after `$out` or `$merge` to "measure rows" with the same pattern; those are write pipelines with distinct syntax rules.

### 14.1. Each Stage Can Increase, Decrease, or Preserve Totals

Quick identification of common stages:

| Stage | Typical cardinality |
| --- | --- |
| `$match` | Preserves or decreases |
| `$project` / `$set` / `$unset` | Preserves |
| `$unwind` | Can increase, decrease, or preserve |
| `$group` | Usually decreases to group count; never exceeds input count on normal data |
| `$sort` | Preserves |
| `$skip` / `$limit` | Decreases or preserves |
| `$lookup` | Usually preserves outer document count while attaching a join result array |
| `$facet` | Emits one output document containing multiple arrays |
| `$count` | 1 document if input is non-empty; 0 output documents if empty |

This table is a guide to **typical semantics**, not a substitute for inspecting actual data and stage options. For example, `$lookup` paired with `$unwind` can multiply documents after joining; `$unwind` with `preserveNullAndEmptyArrays` alters empty-array behavior.

## 15. Checking BSON Types and Missing Data Mid-Pipeline

The hardest bugs to spot are sometimes not row counts, but **unexpected data types**.

### 15.1. Using $type to Inspect Intermediate Structures

Example after `$unwind`:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 3),
  {
    $project: {
      _id: 0,
      orderId: 1,
      sku: "$items.sku",
      quantityType: { $type: "$items.quantity" },
      priceType: { $type: "$items.unitPrice" }
    }
  }
]);
~~~

The output shows whether MongoDB sees values as `int`, `long`, `double`, `decimal`, `string`, or another type. Do not infer from `mongosh` printing `100` that the stored BSON type is definitely int32: depending on how data was inserted or which driver wrote it, numeric storage types can differ.

### 15.2. Finding Items Missing Fields with a Dedicated Check Pipeline

One strategy is filtering item rows that lack any field needed for multiplication:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $match: {
      $or: [
        { "items.quantity": { $exists: false } },
        { "items.unitPrice": { $exists: false } },
        { "items.sku": { $exists: false } }
      ]
    }
  },
  {
    $project: {
      _id: 1,
      items: 1
    }
  }
]);
~~~

On the lab dataset, this query returns zero documents; on real data, it isolates rows that corrupt revenue totals.

Similarly, check for non-numeric values using `$type` or `$isNumber` in version-appropriate aggregation expressions. Before normalizing/converting, decide which records are errors to reject versus records safe to convert.

### 15.3. Empty and Missing Differ from Null or 0

O08 has an empty array; O09 lacks `items`. Default `$unwind` drops both from the output. However, if reporting needs to show "orders without items" or data-error stats, build a **separate check branch** before `$unwind`:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      itemsType: { $type: "$items" },
      itemsCount: {
        $cond: [
          { $isArray: "$items" },
          { $size: "$items" },
          null
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Document O08 has `itemsType` equal to `array` and `itemsCount` equal to 0; O09 has `itemsType` equal to `missing` and `itemsCount` equal to null. Business logic may need to handle these two states differently rather than silently equating them if the schema requires every order to have an items array.

## 16. Explaining Aggregation: Checking Execution Plans, Not Business Results

Running prefixes verifies **output semantics**; `explain()` analyzes **how MongoDB executes the pipeline**.

### 16.1. Running explain in mongosh

~~~javascript
lab.orders.explain("queryPlanner").aggregate(pipeline);

lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Two commonly used verbosity modes:

- `queryPlanner`: the query plan chosen by the optimizer.
- `executionStats`: execution details and metrics per the explain mechanism.

`explain` output is a **diagnostic document**, not an array of SKU revenues for application reports.

### 16.2. Inspecting Index Scans and Document Scans

Create an index supporting the `status` condition:

~~~javascript
lab.orders.createIndex(
  { status: 1 },
  { name: "ix_status" }
);

lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Common indicators to inspect:

| Indicator | Meaning |
| --- | --- |
| `IXSCAN` | Index scan |
| `COLLSCAN` | Collection scan |
| `FETCH` | Source document retrieval |
| `indexBounds` | Index key ranges scanned |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of output documents at the reported level/stage |
| `usedDisk`, `spills`, or similar counters | Indicators of temporary disk spilling, depending on version |

With only 9 orders in the dataset, the server **may choose `COLLSCAN` even after creating the index** because scanning a tiny collection is cheaper than index lookup plus fetch. Never treat that as proof that the index would be useless on production data.

### 16.3. Explain May Not Match Stage-for-Stage

MongoDB has an **aggregation optimizer**. Depending on version and pipeline shape, the server may:

- Push `$match` ahead of transformations that do not alter results.
- Merge or split stages.
- Lower certain operations into the query execution engine.
- Coalesce `$sort + $limit`.
- Prune unnecessary intermediate fields.
- Represent plans differently under the **slot-based query execution engine**.

Consequently, **you cannot always map stage 3 in source code to line 3 in explain**. To prove what a stage does logically, **run prefixes** and compare outputs. To learn which stage consumes CPU/I/O or uses an index, inspect **explain/metrics**.

### 16.4. Explain Is Not How You Fetch Sample Data

This snippet has the wrong intent:

~~~javascript
// WRONG intent: explain returns a plan, not report documents.
var rows = lab.orders.explain("executionStats")
  .aggregate(pipeline);
~~~

To fetch results:

~~~javascript
var rows = lab.orders.aggregate(pipeline).toArray();
~~~

To inspect the first stage of the pipeline:

~~~javascript
var stage1Rows = lab.orders.aggregate(
  pipeline.slice(0, 1)
).toArray();
~~~

**Be careful with write stages:** `$out`/`$merge` must not be treated as harmless reads when executed for real. Explain has its own execution rules and restrictions; never use explain to verify written data, and never blindly run prefixes of write pipelines against production data.

## 17. When Pipelines Grow Large: Memory, allowDiskUse, and Runtime

### 17.1. Streaming vs. Blocking Stages

Stages like `$match` or `$project` can typically process documents one by one. By contrast:

- `$sort` may need to hold many documents to determine order.
- `$group` must maintain state across groups.
- Stages such as `$setWindowFields` or complex joins can require substantial memory.

This means: **reading a cursor element by element does not mean the server only keeps one element in RAM**. A pipeline with blocking stages may consume heavy memory before the cursor returns its first document.

### 17.2. allowDiskUse

In supported environments/versions:

~~~javascript
var c = lab.orders.aggregate(
  pipeline,
  {
    allowDiskUse: true,
    maxTimeMS: 30000
  }
);

c.forEach(printjson);
~~~

`allowDiskUse` permits eligible stages to spill temporary data to disk when exceeding per-stage memory limits. Starting in MongoDB 6.0, default disk usage behavior is also governed by `allowDiskUseByDefault`. Spill eligibility depends on **stage type and server version**; `allowDiskUse: true` does not exempt every transformation from memory limits.

`maxTimeMS` sets an execution time budget via MongoDB's timeout mechanism; operations over huge datasets can be aborted when exceeding the limit. Do not pick an arbitrarily tiny timeout in production, as it can cause spurious application failures.

### 17.3. Output Limits and Document Size

- Aggregation output can span many documents read via cursor batches.
- **Each individual output document** must still obey MongoDB's BSON document size limit.
- If `$group` builds a single document with a massive `$push` array, it can breach the document size limit even when total result document count is small.
- `$limit` after `$group` does not shrink a document already built by `$group`.
- `toArray()` on the client can exhaust RAM even when the server completes the pipeline cleanly.

For large reports, consider projecting fewer fields, partitioning by date/tenant, bounding group counts, streaming exports, or materializing results where appropriate.

### 17.4. Production Verification Needs Guardrails

The stage-by-stage inspection helpers in this lesson can **re-run the entire pipeline multiple times**. In production, keep these precautions in mind:

1. Filter a meaningful subset using `tenantId`/date ranges.
2. Set an appropriate `maxTimeMS`.
3. Never print an entire large result set.
4. Never call `toArray()` unbounded.
5. Check `explain("queryPlanner")` or telemetry before running `executionStats` repeatedly.
6. Never run pipelines containing `$out`/`$merge` directly just to debug.
7. Maintain expected figures or test fixtures in a dedicated environment.

## 18. Reading an Aggregation Cursor in the Java Driver

With the **MongoDB Java Sync Driver**, `collection.aggregate(pipeline)` returns an `AggregateIterable<T>`, which can be iterated via `MongoCursor<T>`. Example:

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Accumulators.*;
import static com.mongodb.client.model.Filters.*;

public class AggregateCursorExample {

    public static void readPaidOrders(MongoCollection<Document> orders) {
        List<org.bson.conversions.Bson> stages = Arrays.asList(
            match(eq("status", "PAID")),
            group("$customerId", sum("orderCount", 1))
        );

        AggregateIterable<Document> iterable = orders
            .aggregate(stages)
            .batchSize(50)
            .allowDiskUse(true);

        try (MongoCursor<Document> cursor = iterable.iterator()) {
            while (cursor.hasNext()) {
                Document row = cursor.next();
                System.out.println(row.toJson());
            }
        }
    }
}
~~~

Meaning:

- `AggregateIterable` configures and iterates over aggregation results; it is **not a List**.
- `batchSize(50)` tunes batch fetching when reading results.
- `try-with-resources` ensures `MongoCursor` closes even on errors.
- `cursor.hasNext()`/`cursor.next()` reads sequentially without buffering the entire output.

This Java example groups PAID order counts by customer, **differing** from the lab's SKU revenue pipeline. On the current dataset, customers with PAID orders are C01, C02, C03, and C05: **four groups**, with C01=2, C02=2, C03=2, C05=1. Results from `group()` have no default order; add `sort` if deterministic presentation is needed.

### 18.1. When Should You Avoid into(new ArrayList)?

The Java Driver supports collecting aggregation results into a client collection via its iterable API. Example:

~~~java
List<Document> allRows = orders
    .aggregate(stages)
    .into(new java.util.ArrayList<>());
~~~

This is convenient for **small reports**. For large results, it shares the same drawback as `toArray()` in `mongosh`: holding too many documents in RAM. When exporting CSV/NDJSON or feeding streams, consume sequentially via the cursor.

## 19. Reading Cursors in the MongoDB Node.js Driver

With the **Node.js MongoDB Driver**, `collection.aggregate(pipeline)` returns an `AggregationCursor`; the driver API relies heavily on **asynchronous** operations:

~~~javascript
// Node.js application example, do not run in mongosh.
// Assumes orders is a MongoDB collection from the Node.js Driver.
async function printAggregation(orders, pipeline) {
  const cursor = orders.aggregate(pipeline, {
    batchSize: 50,
    allowDiskUse: true
  });

  try {
    for await (const doc of cursor) {
      console.log(doc);
    }
  } finally {
    await cursor.close();
  }
}
~~~

Here:

- `for await...of` reads each document asynchronously.
- The cursor does not need to be materialized into an array all at once.
- `finally` ensures resource cleanup if the loop exits early or throws.
- Reading the same cursor concurrently from independent async flows can cause unpredictable state; use a single consumer or open separate cursors.

**Environment difference:** `mongosh` provides convenient synchronous methods for interactive learning, whereas the Node.js Driver uses Promises/async iterators. Do not copy `while (cursor.hasNext())` from mongosh into the Node.js Driver omitting `await`.

### 19.1. When a Small Array Is Needed

~~~javascript
const cursor = orders.aggregate(pipeline);
const rows = await cursor.toArray();
console.log(rows);
~~~

Only do this once you know the output size is bounded and small. When building paginated API endpoints, design explicit ordered pagination or suitable batching rather than turning a huge export into one massive JSON response.

## 20. Designing Verification in Real Projects

A strong aggregation test suite does not only assert final totals; it verifies **per-stage invariants**.

### 20.1. Small Fixtures Covering Edge Cases

The lab dataset intentionally includes:

- Documents dropped by `$match`.
- Documents with multi-element arrays.
- Documents with empty arrays.
- Documents missing the array field altogether.
- Multiple SKUs appearing across multiple orders.
- A lower-revenue SKU that still must appear before `$limit`.

Real-world test data should also cover:

- Negative, zero, and null numeric values.
- Wrong BSON field types.
- Nested arrays.
- Duplicate item codes within one order.
- Very large numbers or exact decimal fractions.
- New statuses not yet in the enum.
- Dates in other timezones.

### 20.2. Recommended Invariants

| Position | Invariant to verify |
| --- | --- |
| After `$match` | Every document has `status = "PAID"` |
| After `$project` | Required `orderId`, `region`, and `items` exist for downstream stages |
| After `$unwind` | Each output represents one item; row count equals sum of array lengths of eligible orders |
| After `$set` | `lineTotal = quantity × unitPrice` with valid numeric type |
| After `$group` | Sum across SKU groups equals pre-group `lineTotal` sum |
| After final `$project` | Field names and types match the API contract |
| After `$sort` | Revenue is non-increasing top-to-bottom; tie-breakers are consistent |
| After `$limit` | Result count does not exceed limit; top N aligns with sort |

### 20.3. Comparing Two Independent Calculations

A useful technique is summing at two different levels:

~~~javascript
// Approach A: compute from individual items before grouping by SKU.
var totalA = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: null,
      sum: {
        $sum: {
          $multiply: [
            "$items.quantity",
            "$items.unitPrice"
          ]
        }
      }
    }
  }
]).toArray();

// Approach B: sum across already-grouped SKU totals.
var totalB = lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  {
    $group: {
      _id: null,
      sum: { $sum: "$totalRevenue" }
    }
  }
]).toArray();

printjson({ totalA, totalB });
// Both sums must equal 870 on the initial dataset.
~~~

If the two diverge, focus on `$unwind`, `$multiply`, and `$group`, or check whether source data mutated between runs.

**Note:** both pipelines can share the same business bug if both use a flawed `quantity × unitPrice` definition; always include hand-calculated expected fixtures as well.

## 21. Difference Between Logic Verification and Performance Measurement

Do not conflate two questions:

1. **Are the results correct?**
2. **Is the query running efficiently?**

| Need | Right tool | What to avoid |
| --- | --- | --- |
| View a stage's output | Prefix run + small `toArray()` or `forEach()` | Printing entire production datasets |
| Count input/output | Prefix + `$count` | Counting after `$limit` and calling it source total |
| Verify calculations | Debug `$project`/`$set`, invariants, fixtures | Looking only at final output and guessing |
| Check missing fields/types | `$type`, `$exists`, `$isArray` | Assuming every document shares the exact same schema |
| Check index usage | `explain()` | Thinking `IXSCAN` means business logic is correct |
| Check memory/spill | Execution stats, profiler, server metrics | Looking only at result document count |
| Check batches/client RAM | `batchSize`, streaming, monitoring | `toArray()` on massive datasets |
| Verify stability | Sort with tie-breakers, run on fixtures | Trusting `$group` output order |

`explain()` reveals *how the server executes work*, while running pipeline prefixes reveals *how data transforms*. Combine both, but never substitute one for the other.

## 22. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Second `cursor.toArray()` returns empty array | Cursor was already exhausted | Call `aggregate()` to open a fresh cursor |
| `next()` has no elements | Cursor exhausted or empty result | Check `hasNext()` and close cursors properly |
| Client runs out of RAM | Buffering entire output via `toArray()` | Stream/iterate sequentially, bound output |
| Batch size 2 still yields 7 results | Batch size is not a total limit | Use `$limit` to cap result documents |
| `$group` returns an inflated order count | `$unwind` turned one order into many rows | Separate item count, line count, and distinct orders |
| O08/O09 missing after unwind | Empty/missing arrays dropped by default | Check `preserveNullAndEmptyArrays` and business rules |
| Field needed later disappears after `$project` | Projection dropped the field | Keep the field or reorder stages |
| Revenue is wrong even though group count is right | Wrong `$multiply`, bad types, or empty fields | Inspect `lineTotal` stage before grouping |
| Group total differs from item-row total | Extra filtering, duplication, wrong grouping key, data mutation | Compare prefixes and invariant totals |
| `$group` returns groups in surprising order | `$group` does not sort output | Add an explicit `$sort` |
| Top 2 has unstable ordering | Sort lacks tie-breaker when groups tie | Add a tie-breaker key |
| Few documents in preview led to thinking dataset is small | `$limit` was added to prefix | Use `$count` on the full prefix |
| `explain` does not show stages matching source | Optimizer merged/pushed/transformed stages | Distinguish logical pipeline from physical plan |
| `explain` does not return SKUs | Explain returns diagnostic plan info only | Use `aggregate()` to fetch business data |
| Cursor expires during long user pause | Server/session idle timeout or cursor closed | Never hold server cursors open across HTTP requests |
| Pipeline with `$merge` altered data while debugging | Actually ran a write stage | Separate read pipelines; never run prefixes with side effects |
| Two runs return different results | Source data updated between runs | Use stable fixtures or appropriate consistent-read mechanisms |
| Sort/group stages use high RAM | Blocking stages, large datasets | Optimize `$match`, indexes, partitioning, allowDiskUse as needed |

## 23. Practice Exercises

### Exercise 1 — Reading a Cursor Three Ways

Run `pipeline` from section 4 and read results using:

1. `toArray()`.
2. `forEach()`.
3. `while (hasNext())` + `next()` loop.

Each method must use **a fresh cursor**. Explain differences in client memory usage and ability to stop early.

### Exercise 2 — Observing an Exhausted Cursor

~~~javascript
var c = lab.orders.aggregate(pipeline);

printjson(c.next());
printjson(c.toArray());
printjson(c.toArray());
~~~

Why does the first `toArray()` return only one document while the second returns an empty array? Rewrite to obtain both SKUs cleanly without reusing an exhausted cursor.

### Exercise 3 — Counting Cardinality at Each Stage

Use `countAfterStage(pipeline, i)` for `i` from 1 to 8. Fill in the table:

| Stage | Document count to fill in |
| --- | ---: |
| `$match` | ? |
| `$project` | ? |
| `$unwind` | ? |
| `$set` | ? |
| `$group` | ? |
| `$project` | ? |
| `$sort` | ? |
| `$limit` | ? |

Answers: **7, 7, 10, 10, 3, 3, 3, 2**. Explain which stages increase and which decrease cardinality.

### Exercise 4 — Changing $unwind Options

Replace `$unwind: "$items"` with:

~~~javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Predict the document count after unwind and verify. On the lab dataset, the result is **12**. Analyze what must be fixed if `lineTotal` continues to be computed on documents lacking items.

### Exercise 5 — Verifying Each SKU's Revenue

Use the prefix through `$group` and compare:

~~~text
KB  -> qty 4, revenue 400, lineCount 3
MS  -> qty 7, revenue 350, lineCount 4
PAD -> qty 4, revenue 120, lineCount 3
~~~

Sum group revenues and compare with the pre-`$group` `lineTotal` sum; both must equal **870**.

### Exercise 6 — Intentionally Breaking Projection

Replace the first `$project` stage with a version **omitting `items`**:

~~~javascript
{
  $project: {
    _id: 0,
    orderId: "$_id",
    region: 1
  }
}
~~~

Predict what happens at `$unwind` and later stages. Why does `$group` no longer produce three SKU groups? Then restore the correct `$project` stage.

### Exercise 7 — Checking BSON Types

Use `$type` to inspect `items.quantity`, `items.unitPrice`, and `lineTotal` after `$set`. If a document had `unitPrice: "100"` as a string instead of a number, how would you design a validation/filtering rule before computing revenue?

### Exercise 8 — Reading Explain and Indexes

Create an index `{ status: 1 }` on `orders`. Run:

~~~javascript
lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Compare `IXSCAN`/`COLLSCAN` if shown, along with `totalDocsExamined`. Explain why with 9 documents the optimizer might still pick `COLLSCAN`.

### Exercise 9 — Increasing the Output Group Limit

Change `$limit: 2` to `$limit: 3` and re-run. The output must include SKU PAD with revenue 120. Compare the top-2 revenue sum (**750**) against all 3 SKUs (**870**) to explain why you cannot take a top-N output and treat it as the grand total.

### Exercise 10 — Designing a Pipeline to Catch Bad Data

Insert a PAID document with an item missing `unitPrice` or having `quantity` as a string in the **lab database**. Design a **read** pipeline listing invalid items along with `orderId`, `sku`, value, and `$type` of each field.

Never coerce bad values to 0 automatically without a business decision; doing so produces wrong revenue reports that still succeed silently.

### Exercise 11 — Distinguishing Application Cursors from Cursor Tokens

A REST API needs to paginate order history across multiple HTTP requests. Should you hold an aggregation cursor open from the first request until the user clicks page 20 several minutes later? Analyze session/cursor lifecycles, deterministic keyset pagination, and executing a fresh aggregation query per page.

### Exercise 12 — Writing Integration Tests

Write a test on a fixed dataset verifying:

- After `$match`, 7 orders.
- After `$unwind`, 10 rows.
- After `$group`, 3 SKUs, total revenue 870.
- After `$sort`, KB, MS, PAD.
- After `$limit`, top two SKUs KB and MS.

When a test fails, run the nearest prefix to pinpoint the first stage causing divergence rather than guessing edits across the whole pipeline.

## 24. Summary of Key Principles

An aggregation pipeline defines a **sequence of logical transformations**, while an aggregation cursor is the **mechanism for reading final results** from the server. Having a cursor does not mean every stage streams immediately; `$sort` and `$group` can still require memory or disk to process.

Core rules:

1. **`aggregate()` returns a cursor** in `mongosh`; `toArray()` is only for small outputs, while `forEach()` and `hasNext()/next()` suit sequential consumption.
2. **A cursor is a stateful result source**: reading once consumes elements; reading again requires running a new aggregate.
3. **Batch size controls how many result documents arrive per transfer**, not total result documents; `$limit` bounds pipeline cardinality.
4. **Verify each stage using prefixes** to inspect intermediate values; appending `$limit` at the end of a prefix is only for sampling, not full validation.
5. **Count with prefix + `$count`** when you need exact document counts after each stage, mindful of the cost of re-running pipelines repeatedly.
6. **Track cardinality and arithmetic invariants**: after `$unwind` count item rows, after `$group` count groups, and after `$limit` only top-N remains.
7. **Inspect fields and BSON types** before calculations; missing, null, string, or empty-array values can skew results.
8. **`explain()` is for understanding the optimizer and performance**, not for returning business data and not guaranteed to match source stage order one-for-one.
9. **Never run write pipelines automatically while debugging**; `$out` and `$merge` must be treated as side-effecting operations.
10. **At scale, combine streaming cursors, early filtering, proper indexes, memory/spill monitoring, and time budgets** to keep operations safe.

### Official MongoDB Documentation

- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — stage-by-stage processing model.
- [db.collection.aggregate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/) — syntax, options, cursors, and write stages.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — optimizer and execution plan rewrites.
- [$match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/), [$project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/), [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/), [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — stages used in the examples.
- [$sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/) and [$limit](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/) — ordering and limiting results.
- [$count](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/) — counting documents reaching the stage.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — memory limits and temporary file spilling.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — executionStats and query planner.
- [MongoDB Cursors](https://www.mongodb.com/docs/manual/core/cursors/) — cursor lifecycle and batches.
- [MongoDB Java Driver: Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — `AggregateIterable` and Java cursors.
- [MongoDB Node.js Driver: Aggregation](https://www.mongodb.com/docs/drivers/node/current/aggregation/) — `AggregationCursor` and async iteration.