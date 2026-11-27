# Exact Counts, Estimated Counts, and Distinct Values in MongoDB

When working with a MongoDB collection, applications often need to know **how many documents exist**, **how many documents match a condition**, or **which distinct values appear in a field**. These three needs sound similar yet map to different operations:

- **`countDocuments(filter)`** accurately counts the number of documents matching a query condition.
- **`estimatedDocumentCount()`** estimates the total document count of a collection using metadata/statistics, which is typically fast on large collections.
- **`distinct(field, filter)`** returns the set of **unique values** of a field across documents matching a filter, rather than a document count.

MongoDB also provides aggregation tools such as **`$count`**, **`$group`**, **`$sortByCount`**, and **`$unwind`** for more complex statistics. Understanding the scope, accuracy, and return type of each operation prevents bugs in pagination, dashboards, and business reporting.

## 1. One Collection, Three Different Questions

Suppose an e-commerce application stores orders in the **`shop.orders`** collection.

| Business question | Appropriate operation | Expected output |
| --- | --- | --- |
| How many orders have status PAID? | `countDocuments({ status: "PAID" })` | An exact integer scoped to the query |
| Roughly how many documents are in `orders`? | `estimatedDocumentCount()` | A metadata-based count, not guaranteed strictly exact |
| Which order statuses currently exist? | `distinct("status")` | List of distinct status values |
| How many distinct statuses exist? | `distinct("status").length` or aggregation | Count of distinct values, not total documents |
| How many orders exist per status? | `$group` or `$sortByCount` | Multiple status–count pairs |

Diagram example:

~~~text
Collection orders (10 documents)
│
├── countDocuments({ status: "PAID" })
│     └── 5 documents
│
├── estimatedDocumentCount()
│     └── ~10 documents from metadata
│
└── distinct("status")
      └── ["PAID", "PENDING", "CANCELLED"]
           (order not guaranteed)
~~~

**Counting documents** differs from **counting distinct values**. A single status might appear in millions of documents yet contribute only one element to the `distinct` result.

## 2. Preparing Test Data in mongosh

Use a dedicated test database **`mongo_query_count_lab`**. The examples assume the collection starts empty; `drop()` deletes the entire collection, so run it only in a test environment.

~~~javascript
use mongo_query_count_lab

db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C-01",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "HCM" },
    tags: ["new", "priority"],
    amount: 250000
  },
  {
    _id: "O-1002",
    customerId: "C-02",
    status: "PAID",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new"],
    amount: 120000
  },
  {
    _id: "O-1003",
    customerId: "C-03",
    status: "PENDING",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift", "priority"],
    amount: 500000
  },
  {
    _id: "O-1004",
    customerId: "C-04",
    status: "CANCELLED",
    channel: "APP",
    shipping: { city: "DN" },
    tags: [],
    amount: 200000
  },
  {
    _id: "O-1005",
    customerId: "C-01",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift"],
    amount: 800000
  },
  {
    _id: "O-1006",
    customerId: "C-05",
    status: "PENDING",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new", "gift"],
    amount: 650000
  },
  {
    _id: "O-1007",
    customerId: "C-06",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "DN" },
    tags: ["priority"],
    amount: 300000
  },
  {
    _id: "O-1008",
    customerId: "C-07",
    status: "CANCELLED",
    channel: "WEB",
    shipping: { city: "HCM" },
    tags: [],
    amount: 100000
  },
  {
    _id: "O-1009",
    customerId: "C-02",
    status: "PAID",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new"],
    amount: 380000
  },
  {
    _id: "O-1010",
    customerId: "C-08",
    status: "PENDING",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift"],
    amount: 220000
  }
]);
~~~

The data distribution is:

| Status | Orders |
| --- | ---: |
| PAID | 5 |
| PENDING | 3 |
| CANCELLED | 2 |
| **Total** | **10** |

There are 6 orders from channel **WEB** and 4 from **APP**; three city values are **HCM**, **HN**, and **DN**. The distinct tag values are **new**, **priority**, and **gift**.

All numeric result examples below assume **no concurrent writes** and an unchanged dataset between commands.

## 3. `countDocuments()`: Accurately Counting Matching Documents

mongosh syntax:

~~~javascript
db.collection.countDocuments(query, options)
~~~

Where:

- **query** is a filter document, identical in syntax to `find()`.
- **options** can specify options such as `limit`, `skip`, `hint`, and `maxTimeMS`.
- The return value is **a number** representing the documents counted under the filter and options.

### 3.1. Counting the Entire Collection

~~~javascript
db.orders.countDocuments({});
// 10
~~~

An empty filter **`{}`** means no filtering by domain fields. With 10 documents present, the result is **10**.

This is an exact count evaluated over the queried documents rather than relying solely on collection-level count statistics.

### 3.2. Counting with a Single Condition

~~~javascript
db.orders.countDocuments({ status: "PAID" });
// 5

db.orders.countDocuments({ status: "PENDING" });
// 3

db.orders.countDocuments({ channel: "WEB" });
// 6
~~~

Conditions are evaluated using standard MongoDB query syntax.

### 3.3. Combining Multiple Conditions

~~~javascript
// PAID orders from the WEB channel.
db.orders.countDocuments({
  status: "PAID",
  channel: "WEB"
});
// 3
~~~

Two fields appearing together at the top level of a filter combine with **AND** logic.

Operators can be used as well:

~~~javascript
// Number of orders with amount 300000 or more.
db.orders.countDocuments({
  amount: { $gte: 300000 }
});
// 5

// Orders in either PAID or PENDING status.
db.orders.countDocuments({
  status: { $in: ["PAID", "PENDING"] }
});
// 8

// Orders shipped to HCM.
db.orders.countDocuments({
  "shipping.city": "HCM"
});
// 5
~~~

**`shipping.city`** uses **dot notation** to access a field inside an embedded document. It is not a collection or namespace name.

### 3.4. Counting on an Array Field

~~~javascript
// Documents with at least one tags element equal to "priority".
db.orders.countDocuments({
  tags: "priority"
});
// 3
~~~

The three matching documents are **O-1001**, **O-1003**, and **O-1007**. Each document is counted **only once**, even if an array field contains multiple matching elements. `countDocuments()` counts **documents**, not how many times a value appears inside arrays.

### 3.5. Counting Over a Time Range

Suppose the application has a BSON Date field **createdAt**:

~~~javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end = ISODate("2026-12-01T00:00:00Z");

db.orders.countDocuments({
  createdAt: {
    $gte: start,
    $lt: end
  }
});
~~~

The interval **`[start, end)`** includes the start instant and excludes the end instant. This is useful for daily/monthly statistics without double-counting boundary instants. This example illustrates syntax; the sample dataset above **does not have a `createdAt` field yet**, so running it on the sample data returns 0.

When computing statistics in a local time zone, convert local day boundaries to UTC properly before filtering.

## 4. How Does `countDocuments()` Work?

MongoDB does not simply read a cached metadata counter to answer `countDocuments()`. Logically, the operation is equivalent to an aggregation that filters documents and sums them:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: null,
      n: { $sum: 1 }
    }
  }
]);
// [ { _id: null, n: 5 } ]
~~~

Where:

1. **`$match`** selects documents matching the filter.
2. **`$group`** collects all selected documents into one group.
3. **`$sum: 1`** increments the count by 1 for each document.

`countDocuments()` itself returns the **number 5**, rather than a document containing field `n`.

### 4.1. What "Exact" Means

Exact here means the count is computed over the actual documents matching the filter under the active read concern, read timestamp, and deployment conditions. It is not a promise that this number **never changes**.

Example:

~~~javascript
const total = db.orders.countDocuments({ status: "PAID" });

// Another client could insert/delete/update a PAID order right after the line above.

const page = db.orders.find({ status: "PAID" })
                      .sort({ _id: 1 })
                      .limit(20)
                      .toArray();
~~~

If a write occurs between those two calls, `total` and `page` can reflect **two different points in time**. Obtaining a consistent snapshot across multiple reads is a separate problem involving appropriate read concerns, snapshots, and transactions.

Furthermore, when reading from a secondary with replication lag, the count may not yet reflect recent writes on the primary. Always interpret results according to how the system reads data.

### 4.2. Accuracy in a Sharded Cluster

In a sharded cluster, **orphaned documents** left behind by chunk migrations can exist. `countDocuments()` is designed to return an accurate count even in the presence of orphaned documents, making it far more suitable for business-critical counts than metadata-only counts.

Accuracy does not eliminate the cost of querying participating shards. If the filter lacks the shard key or cannot target specific shards, the operation may need to scatter across multiple shards.

### 4.3. `skip` and `limit` Options

~~~javascript
db.orders.countDocuments(
  { status: "PAID" },
  { skip: 2, limit: 2 }
);
// 2
~~~

There are 5 PAID orders. Skipping 2 documents and limiting the count to 2 returns **2**. That result **is no longer the total number of PAID documents**.

In a paginated API, to get the total record count for a filter, typically call:

~~~javascript
const filter = { status: "PAID" };

const total = db.orders.countDocuments(filter);

const page = db.orders.find(filter)
                      .sort({ _id: 1 })
                      .skip(0)
                      .limit(2)
                      .toArray();
~~~

Here **total = 5**, while **page.length = 2**. Never pass the page's `skip` and `limit` into the total-count call if your goal is the total matching record count.

## 5. `estimatedDocumentCount()`: Estimating Total Document Count

Syntax:

~~~javascript
db.collection.estimatedDocumentCount(options)
~~~

Example:

~~~javascript
db.orders.estimatedDocumentCount();
// Typically ~10 on the sample dataset; value is metadata-based.
~~~

Key difference: **`estimatedDocumentCount()` does not accept a query filter**. It returns an estimated count for the **entire collection**.

Do not write:

~~~javascript
// WRONG PURPOSE: estimatedDocumentCount does not take a filter parameter.
db.orders.estimatedDocumentCount({ status: "PAID" });
~~~

That argument is not a filter condition. To count only PAID orders, use `countDocuments({ status: "PAID" })`.

### 5.1. Why Is It Usually Fast?

`estimatedDocumentCount()` relies on **collection metadata**, so for normal collections it does not have to scan documents just to compute the total.

This is useful for:

- Overview dashboards that do not require strict precision at every instant.
- Displaying dataset scale, such as "roughly several million records".
- Operational or admin metrics needing a fast estimate.
- Preliminary checks on large collections when slight drift is acceptable.

Do not misinterpret the word "estimated" as a random percentage sampling algorithm, nor assume the number is always off. On small collections with healthy metadata, it can return the exact count; the difference lies in **the counting mechanism and its guarantees**.

### 5.2. When Can the Result Be Inaccurate?

Situations to watch out for:

- **Sharded clusters:** metadata counts can include **orphaned documents** and fail to filter them out.
- **Unclean shutdown:** after an unclean `mongod` shutdown, collection count statistics may lag behind actual stored data.
- **Views:** views do not maintain collection-style metadata counts. For a view, MongoDB must evaluate the view's underlying pipeline, yielding no "fast metadata count" advantage.

For example, when an order count directly impacts financial reconciliation, billing, or a hard business quota, **do not use an estimated count as the authoritative figure**.

### 5.3. Options

You can bound server execution time:

~~~javascript
db.orders.estimatedDocumentCount({
  maxTimeMS: 2000
});
~~~

`maxTimeMS` limits server-side execution time, **not the maximum number of documents**. This option does not turn an estimated count into an exact count.

## 6. Direct Comparison of the Two Counting Methods

| Criterion | `countDocuments()` | `estimatedDocumentCount()` |
| --- | --- | --- |
| Purpose | Exact count of matching documents | Estimated total documents in collection |
| Filter by fields | **Yes** | **No** |
| Uses collection metadata as count | No | Yes, for standard collections |
| Cost on large datasets | Depends on filter, indexes, and scanned volume | Usually low due to metadata |
| Suitable for exact business reporting | Yes | Not recommended when exactness is mandatory |
| Sharded orphaned documents | Accounts for them accurately | Can overcount |
| After unclean shutdown | Does not rely on potentially stale counters | Can be inaccurate |
| Counting documents in a view | Yes | Supported, without metadata fast-path |
| Return type | A number | A number |

Decision rule:

~~~text
Need to count with a filter?
    ├── YES ──> countDocuments(filter)
    └── NO
         ├── Need an exact number? ──> countDocuments({})
         └── Fast estimate acceptable? ──> estimatedDocumentCount()
~~~

If the system displays a number with high user impact—such as refundable orders—define the required accuracy clearly before choosing a method.

## 7. `distinct()`: Retrieving Unique Values

mongosh syntax:

~~~javascript
db.collection.distinct(field, query, options)
~~~

Where:

- **field**: field name or dot path to collect distinct values from, passed as a string.
- **query**: optional filter document.
- **options**: optional query settings such as `collation`.
- Return value: an **array of distinct BSON values**, not a document cursor like `find()`.

### 7.1. Retrieving Existing Statuses

~~~javascript
db.orders.distinct("status");
// Example: ["PAID", "PENDING", "CANCELLED"]
~~~

The collection has 10 documents but only **3 distinct statuses**. Element order in the returned array **is not guaranteed**; if alphabetical or domain ordering is needed for display, sort explicitly in the application.

### 7.2. Distinct with a Filter

~~~javascript
db.orders.distinct(
  "status",
  { channel: "WEB" }
);
// Statuses among orders from WEB: PAID, PENDING, CANCELLED.
~~~

`query` is applied to select **input documents** before extracting distinct values.

Another example:

~~~javascript
db.orders.distinct(
  "channel",
  { status: "PAID" }
);
// ["WEB", "APP"], in arbitrary order.
~~~

Five PAID orders span both channels, yet `distinct` returns **one WEB value and one APP value**.

### 7.3. Distinct on a Nested Field

~~~javascript
db.orders.distinct("shipping.city");
// Three values: "HCM", "HN", "DN".
~~~

The path **`shipping.city`** accesses `city` inside the embedded document `shipping`.

You can combine it with a filter:

~~~javascript
db.orders.distinct(
  "shipping.city",
  { status: "PAID" }
);
// Values: "HCM", "HN", "DN".
~~~

### 7.4. Distinct on an Array

~~~javascript
db.orders.distinct("tags");
// Values: "new", "priority", "gift".
~~~

When the specified field holds an **array**, `distinct()` treats **each element** of the array as a candidate value. It does not treat the entire array `["new", "priority"]` as a single label in this example.

Therefore:

~~~javascript
db.orders.countDocuments({ tags: "priority" });
// 3 documents

db.orders.distinct("tags").length;
// 3 distinct tag values across the collection
~~~

Both results happen to equal **3**, yet they answer two different questions. On another dataset, the two numbers do not have to match.

### 7.5. Do Not Use Distinct to Fetch Full Documents

`distinct("status")` returns only values of the `status` field, not the matching order documents. To retrieve full documents, use `find()`; to group documents and compute statistics per field value, use `aggregate()`.

## 8. Missing Values, Null, Data Types, and Collation

### 8.1. Missing Fields Differ from Null Values

Consider another test collection:

~~~javascript
use mongo_query_count_lab

db.profiles.drop();

db.profiles.insertMany([
  { _id: 1, displayName: "An", region: "NORTH" },
  { _id: 2, displayName: "Bình", region: null },
  { _id: 3, displayName: "Chi" },
  { _id: 4, displayName: "Dung", region: "SOUTH" }
]);
~~~

You can count:

~~~javascript
// Includes both documents with region: null and documents missing region.
db.profiles.countDocuments({ region: null });
// 2

// Field region exists, even when its value is null.
db.profiles.countDocuments({
  region: { $exists: true }
});
// 3

// Field region does not exist.
db.profiles.countDocuments({
  region: { $exists: false }
});
// 1

// Only region fields with BSON type Null.
db.profiles.countDocuments({
  region: { $type: "null" }
});
// 1
~~~

With `distinct("region")`, MongoDB collects **values from existing fields**; an explicitly stored `null` counts as a value, whereas a document missing the field does not add a region value.

~~~javascript
db.profiles.distinct("region");
// Values: "NORTH", null, "SOUTH".
~~~

If the goal is to list "regions actually declared" and exclude `null`, filter them out:

~~~javascript
db.profiles.distinct(
  "region",
  { region: { $ne: null } }
);
// "NORTH", "SOUTH"
~~~

### 8.2. Strings Differing Only by Case

Under default binary comparison, strings such as **`"paid"`**, **`"PAID"`**, and **`"Paid"`** are treated as distinct values. When you want `distinct` to follow linguistic rules or ignore case, pass an appropriate **collation**.

Example:

~~~javascript
db.profiles.distinct(
  "displayName",
  {},
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

`strength: 2` generally compares case-insensitively while still distinguishing accents/diacritics per collation rules. `locale`, `strength`, and index collation affect both returned results and index eligibility.

Do not simply call `toLowerCase()` on everything on the client assuming it matches database collation. Language rules, diacritics, and Unicode normalization must be defined as explicit business rules.

### 8.3. Semantically Identical Values with Different BSON Types

Suppose `customerCode` is stored sometimes as a number and sometimes as a string:

~~~javascript
{ customerCode: 101 }
{ customerCode: "101" }
~~~

MongoDB treats these as **two distinct values of different types**, even though they look similar in the UI.

Likewise, a string UUID and a BSON Binary UUID do not merge into one distinct value automatically. For reliable statistics, standardize schemas and BSON types at write time.

## 9. When `distinct` Is Not Enough: Use Aggregation

`distinct()` works well when you only need a moderately sized list of unique values. When you also need **document counts per value**, **sorting**, **pagination over grouped values**, or **combined metrics**, aggregation is far more flexible.

### 9.1. Counting Documents with `$count`

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "totalPaid" }
]);
// [ { totalPaid: 5 } ]
~~~

`$count` is an **aggregation stage** that outputs a document with your chosen field name. Unlike `countDocuments()`, the result comes from an aggregation cursor.

Important detail: if the pipeline receives zero input documents, **`$count` emits no result document**.

~~~javascript
db.orders.aggregate([
  { $match: { status: "UNKNOWN" } },
  { $count: "total" }
]);
// []
~~~

Meanwhile:

~~~javascript
db.orders.countDocuments({ status: "UNKNOWN" });
// 0
~~~

Applications must handle an empty aggregation cursor when using `$count`.

### 9.2. `$group`: Counting per Status

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Results sorted by status name:

~~~javascript
[
  { _id: "CANCELLED", total: 2 },
  { _id: "PAID", total: 5 },
  { _id: "PENDING", total: 3 }
]
~~~

Each distinct status creates one group; `total` is the document count in that group.

If you only need to count how many **distinct statuses** exist:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $count: "distinctStatusCount" }
]);
// [ { distinctStatusCount: 3 } ]
~~~

This approach is useful when the number of groups is large and you do not want to send all values to the client just to call `.length`.

### 9.3. `$sortByCount`: Concise Frequency Table

~~~javascript
db.orders.aggregate([
  { $sortByCount: "$status" }
]);
~~~

The `$sortByCount` stage groups by the expression value, counts documents in each group, and sorts by count descending. Output on the sample dataset:

~~~javascript
[
  { _id: "PAID", count: 5 },
  { _id: "PENDING", count: 3 },
  { _id: "CANCELLED", count: 2 }
]
~~~

When frequencies tie, ordering among tied groups is not guaranteed without an additional sort.

### 9.4. `$unwind` for Array Fields

To count how often each tag appears across documents, flatten the array into separate input documents:

~~~javascript
db.orders.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tags",
      totalOccurrences: { $sum: 1 }
    }
  },
  { $sort: { totalOccurrences: -1, _id: 1 } }
]);
~~~

In the sample dataset:

- `new` appears in 4 documents.
- `gift` appears in 4 documents.
- `priority` appears in 3 documents.

By default, `$unwind` drops documents with empty arrays. If a single document contains two **identical** elements in `tags`, the pipeline above counts it twice because it counts **unwound elements**, not **distinct documents** containing that tag.

If business logic requires "each tag counted at most once per order", deduplicate the array or add a deduplication stage by **order ID + tag** before counting frequencies.

### 9.5. Difference When Using `$group` on an Array Without `$unwind`

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$tags" } }
]);
~~~

This pipeline groups by **the entire array value** (such as `["new", "priority"]`), rather than behaving like `distinct("tags")` over individual elements. To emulate `distinct` over array elements in aggregation, use:

~~~javascript
db.orders.aggregate([
  { $unwind: "$tags" },
  { $group: { _id: "$tags" } },
  { $sort: { _id: 1 } }
]);
~~~

These transformations demonstrate how the same array field can be treated as **a single whole value** or **a collection of elements**, depending on the operation.

## 10. Performance: Indexes, Scans, and Large Datasets

### 10.1. `countDocuments({})` on Large Collections

An unfiltered `countDocuments({})` can trigger a **full collection scan**, scaling in cost with collection size.

MongoDB recommends that you can hint the `_id_` index to avoid scanning full documents when counting an entire collection:

~~~javascript
db.orders.countDocuments(
  {},
  { hint: "_id_" }
);
~~~

`_id_` is the default index on `_id` in standard collections. `hint` forces the query planner to use the specified index; it works only when the index exists and serves the count.

Do not apply `hint: "_id_"` blindly to filtered counts. When counting by other fields, an index covering the filter fields is usually much better.

### 10.2. Indexes for Filtered Counts

Suppose an API frequently counts orders by **status** and **channel**:

~~~javascript
db.orders.createIndex({
  status: 1,
  channel: 1
});
~~~

You can count:

~~~javascript
db.orders.countDocuments({
  status: "PAID",
  channel: "WEB"
});
~~~

MongoDB can use the index to narrow down matching documents. Actual speedup depends on selectivity, index field order, filter shape, data volume, and the query plan.

An index does not guarantee instant performance in every scenario. Indexes also consume storage and add overhead on inserts, updates, and deletes.

### 10.3. Indexes for `distinct`

If you frequently query distinct values of `status`:

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.distinct("status");
~~~

In some cases, MongoDB can use a **DISTINCT_SCAN** or index scan to collect distinct values much more efficiently. Inspect the execution plan with the appropriate explain tool.

Not every `distinct()` uses an index. Filters, mismatched collations, array fields, or special collection types can cause the query planner to choose a different plan.

### 10.4. Shard Keys and Scattered Requests

In a sharded cluster, a count with a filter targeting the shard key can be routed to one or a few shards; an unfiltered count or non-shard-key filter may need to aggregate results from multiple shards.

For example, suppose `orders` is sharded by `customerId`:

~~~javascript
// Eligible for targeted routing by shard key.
db.orders.countDocuments({ customerId: "C-01" });

// Missing customerId: may need to query multiple shards.
db.orders.countDocuments({ status: "PAID" });
~~~

This is a consequence of data partitioning design, not a bug in `countDocuments()`.

### 10.5. Using `explain` to Understand Cost

You can inspect the execution plan of an equivalent aggregation count:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
~~~

Inspect stages such as **IXSCAN**, **COLLSCAN**, keys/documents examined, and execution time on a sufficiently large dataset. A 10-document collection does not represent production performance.

## 11. Limits and Cautions for `distinct()`

### 11.1. Very Large Result Sets

`distinct()` collects all distinct values into a single command response. If a field has an extremely high number of unique values, the response can hit the **16 MiB BSON document size limit** and fail.

For example, calling `distinct` on `eventId` when every document has a unique `eventId` means the distinct count approaches the total document count. In that case, `distinct()` is unsuitable for streaming millions of IDs.

You can use aggregation to return **one document per group** and iterate via a cursor:

~~~javascript
db.events.aggregate([
  { $match: { status: "ACTIVE" } },
  { $group: { _id: "$eventId" } },
  { $sort: { _id: 1 } }
]);
~~~

This avoids packing all distinct values into **a single result array**. However, `$group` still has RAM, disk, and resource limits; it is not free on massive datasets.

In particular, using `$addToSet` to accumulate **all IDs into one array inside a single document** can still hit the size limit. To export large value lists, stream groups over a cursor instead of building one giant array.

### 11.2. `distinct` in Sharded Clusters

The `distinct` command in certain sharded-cluster scenarios can collect values from **orphaned documents**, returning values that no longer belong to validly owned chunks.

When exact business distinct values are required in a sharded cluster, account for this behavior, inspect query plans, and use aggregation `$group` where appropriate.

### 11.3. `distinct` in Transactions

Under MongoDB transaction rules:

- On **unsharded collections**, `distinct()` can be used inside transactions.
- On **sharded collections**, do not call `distinct()` or the `distinct` command inside transactions; MongoDB recommends using an aggregation pipeline with `$group` instead.

Example for a scalar field:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$channel" } }
]);
~~~

If the field is an array, consider `$unwind` before `$group` to match element-level distinct semantics.

### 11.4. Result Ordering and Display

`distinct()` output **has no ordering contract**. APIs returning lists of values must apply sorting explicitly:

~~~javascript
const channels = db.orders.distinct("channel");
channels.sort();
~~~

Calling `.sort()` on a JavaScript array in the example uses default string comparison. For numbers, dates, accented characters, or custom business ordering, provide an appropriate comparator or collation.

Never rely on the element order returned by `distinct` as a basis for "page 1" and "page 2" without a deterministic sort/pagination strategy.

## 12. Common Mistakes with Count and Distinct

| Misconception | Why it is wrong or incomplete |
| --- | --- |
| `estimatedDocumentCount({ status: "PAID" })` counts PAID orders | `estimatedDocumentCount` does not accept a filter |
| `countDocuments({})` and `estimatedDocumentCount()` are always equal | Different mechanisms and guarantees; metadata can drift |
| `distinct("status")` returns document counts per status | It returns **distinct values**; use `$group` for frequencies |
| `distinct("tags")` returns whole `tags` arrays | On array fields, `distinct` extracts elements |
| `countDocuments({ tags: "gift" })` counts occurrences of the `"gift"` tag | It counts matching documents, once per document |
| Computing total pages with `countDocuments(filter, { skip, limit })` | `skip`/`limit` alter the returned count |
| `$count` always returns a document with `0` | Empty input causes the pipeline to return an empty cursor |
| Exact count means the result cannot change between two commands | Concurrent writes or replica lag can change counts |
| Adding an index guarantees every count is instantaneous | Still depends on filter, selectivity, execution plan, and sharding |
| MongoDB automatically merges `"PAID"` and `"paid"` | Depends on collation and stored values |
| `distinct` never hits size limits | Large distinct sets can exceed the BSON response limit |
| `$group: { _id: "$tags" }` equals `distinct("tags")` | For arrays, `$group` groups whole arrays unless `$unwind` is used |
| Estimated count is fine for financial reconciliation | Operations requiring exact numbers need exact counting and controls |

Another subtle bug is using `find(filter).limit(20).toArray().length` as the total search result count. That number only tells you **how many documents were fetched on the current page** (at most 20); it does not equal total matching documents across pages.

## 13. Real-World Applications: Pagination and Dashboards

### 13.1. Paginating Search Results

Example API returning a page of PAID orders, 3 orders per page:

~~~javascript
const filter = { status: "PAID" };
const pageNumber = 1;
const pageSize = 3;

const totalItems = db.orders.countDocuments(filter);

const items = db.orders
  .find(filter)
  .sort({ _id: 1 })
  .skip((pageNumber - 1) * pageSize)
  .limit(pageSize)
  .toArray();

const totalPages = Math.ceil(totalItems / pageSize);

printjson({
  totalItems,
  pageNumber,
  pageSize,
  totalPages,
  items
});
~~~

With the static sample dataset:

~~~text
totalItems = 5
pageSize   = 3
totalPages = 2
items      = 3 documents on the first page
~~~

On large datasets, **deep `skip`** becomes expensive; keyset/cursor pagination is usually better for traversing many pages. Also, fetching total count and items are two separate reads; if strict consistency between them is needed, design the read mechanism accordingly.

### 13.2. Overview Dashboard

A dashboard might need:

- Total documents in the collection to show approximate scale.
- Exact PAID order count for business tracking.
- List of available statuses for filter dropdowns.
- Order counts broken down by status.

Example:

~~~javascript
const approximateAllOrders =
  db.orders.estimatedDocumentCount();

const exactPaidOrders =
  db.orders.countDocuments({ status: "PAID" });

const availableStatuses =
  db.orders.distinct("status");

const ordersByStatus =
  db.orders.aggregate([
    { $sortByCount: "$status" }
  ]).toArray();

printjson({
  approximateAllOrders,
  exactPaidOrders,
  availableStatuses,
  ordersByStatus
});
~~~

On small datasets, these calls produce matching figures. In production, they run at **different instants** and can reflect slightly different states under concurrent writes.

If a high-traffic screen needs the same complex count repeatedly, consider caching or maintaining domain counter tables/collections rather than scanning a large collection on every view. Define **data freshness expectations** and update mechanisms clearly.

### 13.3. Dynamic Filter Dropdowns

For example, an orders page provides a **Status** dropdown:

~~~javascript
const statusOptions =
  db.orders.distinct("status").sort();

printjson(statusOptions);
~~~

This works well when the cardinality of statuses is small. For high-cardinality free-form fields with millions of values such as `customerId`, loading all `distinct` values into a dropdown is impractical. Use a prefix-search autocomplete API with pagination and an appropriate index instead.

## 14. MongoDB Java Sync Driver: Corresponding Operations

In Java, **`MongoCollection<Document>`** exposes methods corresponding to the mongosh helpers:

| Mongosh | Java Sync Driver |
| --- | --- |
| `db.orders.countDocuments({})` | `collection.countDocuments()` |
| `db.orders.countDocuments({ status: "PAID" })` | `collection.countDocuments(Filters.eq("status", "PAID"))` |
| `db.orders.estimatedDocumentCount()` | `collection.estimatedDocumentCount()` |
| `db.orders.distinct("status")` | `collection.distinct("status", String.class)` |

Example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CountOptions;
import com.mongodb.client.model.Filters;

import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class CountAndDistinctExample {

    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_query_count_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            // Exact count of all documents.
            long totalExact = orders.countDocuments();

            // Exact count with a filter.
            long paidOrders = orders.countDocuments(
                    Filters.eq("status", "PAID")
            );

            // Estimated count of the entire collection.
            long totalEstimated = orders.estimatedDocumentCount();

            // Retrieve distinct status values.
            List<String> statuses = orders
                    .distinct("status", String.class)
                    .into(new ArrayList<>());

            // Full-collection count hinting the _id_ index.
            long totalWithHint = orders.countDocuments(
                    new Document(),
                    new CountOptions().hintString("_id_")
            );

            System.out.println("Exact total: " + totalExact);
            System.out.println("Paid orders: " + paidOrders);
            System.out.println("Estimated total: " + totalEstimated);
            System.out.println("Statuses: " + statuses);
            System.out.println("Exact with hint: " + totalWithHint);
        }
    }
}
~~~

**Note:** This example requires the MongoDB Java Sync Driver on the classpath, a running MongoDB instance at the given URI, and the sample data loaded. `long` is the appropriate type for counts in the Java Driver. If a field contains mixed BSON types, passing `String.class` to `distinct` may fail; standardize the schema or decode using an appropriate type.

In Spring Data MongoDB applications, equivalent repository or template APIs exist, but you must still distinguish **exact count**, **estimated count**, and **distinct** according to MongoDB's underlying semantics.

## 15. Practice Exercises

The following exercises use **`mongo_query_count_lab.orders`** from the start of this lesson. Run each statement in mongosh and verify against the expected results.

### Exercise 1: Counting Documents

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ status: "PAID" });
db.orders.countDocuments({ channel: "APP" });
db.orders.countDocuments({ amount: { $lt: 300000 } });
~~~

Results on the sample dataset:

- Total: **10**.
- PAID status: **5**.
- APP channel: **4**.
- Amount less than 300000: **5**.

Try replacing `$lt` with `$lte` and observe how the document with `amount = 300000` is now included.

### Exercise 2: Distinguishing Exact and Estimated

~~~javascript
const exact = db.orders.countDocuments({});
const estimated = db.orders.estimatedDocumentCount();

printjson({ exact, estimated });
~~~

Explain why both numbers can match on a small dataset yet must not be treated as providing **the same accuracy guarantees**. In a sharded cluster, think about why orphaned documents can skew metadata statistics.

### Exercise 3: Distinct on Scalar and Nested Fields

~~~javascript
db.orders.distinct("status");
db.orders.distinct("channel");
db.orders.distinct("shipping.city");
db.orders.distinct("shipping.city", { status: "PENDING" });
~~~

Identify the returned values and explain why `distinct` does not tell you **how many orders exist per city**.

### Exercise 4: Distinct on Arrays

~~~javascript
db.orders.distinct("tags");

db.orders.countDocuments({ tags: "new" });

db.orders.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" }
]);
~~~

Compare three questions:

1. Which distinct tags exist?
2. How many documents contain the **new** tag?
3. How many times does each tag appear across array elements?

If a document has **`tags: ["new", "new"]`**, how does the third query's output change while the second query still counts that document only once?

### Exercise 5: Group, Sort, and Count

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $sort: { n: -1 } }
]);

db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $count: "numberOfStatuses" }
]);
~~~

Answer:

- Why does the first query return **3 group documents** whose `n` values sum to **10**?
- Why does the second query return **3** instead of **10**?
- If a filter matches zero documents and the pipeline ends with `$count`, why can the result be an empty array instead of `[{ numberOfStatuses: 0 }]`?

### Exercise 6: Choosing the Right Approach for New Requirements

A system has an `events` collection with tens of millions of documents. Choose the right solution for each requirement:

| Requirement | Recommended approach |
| --- | --- |
| Number of events for customer C-01 | `countDocuments({ customerId: "C-01" })` with a suitable index |
| Approximate collection size for an admin page | `estimatedDocumentCount()` |
| Existing `eventType` values (low cardinality) | `distinct("eventType")` |
| Event count per `eventType` | `$group` or `$sortByCount` |
| Exporting millions of distinct `eventId` values | Aggregation returning groups via cursor or dedicated export pipeline |
| Event count used for exact financial reconciliation | `countDocuments(filter)` with defined scope, timestamp, and read concern |

You have mastered this topic when you can clearly distinguish **filtered document counting**, **metadata-based estimated total counting**, and **listing unique values**, and recognize when aggregation is needed instead of a single helper method.

## References

- [MongoDB Manual — db.collection.countDocuments()](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/)
- [MongoDB Manual — db.collection.estimatedDocumentCount()](https://www.mongodb.com/docs/manual/reference/method/db.collection.estimatedDocumentCount/)
- [MongoDB Manual — db.collection.distinct()](https://www.mongodb.com/docs/manual/reference/method/db.collection.distinct/)
- [MongoDB Manual — $count](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $sortByCount](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/)
- [MongoDB Java Sync Driver — Count Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/count/)
