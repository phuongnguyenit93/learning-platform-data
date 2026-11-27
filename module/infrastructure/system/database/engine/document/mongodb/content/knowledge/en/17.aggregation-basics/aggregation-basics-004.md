# Sorting, Limiting, and Skipping with `$sort`, `$limit`, and `$skip` in MongoDB

An order-listing API typically must answer three questions: **Which order comes first? How many orders to take? How many initial orders to skip?** In the MongoDB Aggregation Pipeline, the three fundamental stages for solving this are `$sort`, `$limit`, and `$skip`.

- **`$sort`** sorts the documents flowing through the pipeline by one or more keys.
- **`$limit`** allows at most a specified number of documents to proceed in the pipeline.
- **`$skip`** skips a specified number of initial documents in the **current order**.

These three stages often pair with `$match` to build pagination, latest feeds, leaderboards, top-N reports, and APIs requiring stable display order. Although the syntax is short, stage placement and key order determine both **correctness** and **performance**. In particular, `$skip` does not sort on its own, `$limit` does not automatically pick "top" items without a prior order, and `$sort` on fields with duplicate values can make pages unstable.

This lesson belongs to the **Aggregation Basics** chapter of *Database Engine Document MongoDB*. Examples run in **mongosh**, in the practice database `aggregation_paging_lab`, using BSON Date and Decimal128 to represent timestamps and currency. Depending on the MongoDB version, `explain()` output and index/disk-spill behavior may differ; the operational sections distinguish those cases.

## 1. Reviewing How the Aggregation Pipeline Works

The Aggregation Pipeline processes a set of documents through **stages in order**. Each stage takes input from the previous stage, processes it, and passes results to the next stage.

~~~mermaid
flowchart LR
    C["Collection orders"] --> M["$match: select documents"]
    M --> S["$sort: determine order"]
    S --> K["$skip: skip previous pages"]
    K --> L["$limit: cap page size"]
    L --> P["$project: choose fields to return"]
    P --> O["API Result"]
~~~

Example:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 10 },
  { $limit: 5 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Logically:

1. Keep only paid orders.
2. Sort newest orders first; when timestamps tie, smaller ID comes first.
3. Skip the first 10 documents in the sorted list.
4. Take at most the next 5 documents.
5. Return only the fields the application needs.

**Stage order is not decorative**. Placing `$limit` before `$sort` can select "5 documents that arrived first in the pipeline and then sort them" instead of "the 5 newest documents in the entire set."

### Distinguishing Aggregation Syntax from Cursor Methods

MongoDB also supports similar operations on a `find()` cursor:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .skip(10)
  .limit(5)
~~~

In aggregation, each operation is a **stage object**:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 10 },
  { $limit: 5 }
])
~~~

Both approaches can solve simple pagination needs, but aggregation also enables `$group`, `$unwind`, `$lookup`, `$addFields`, `$facet`, and many other transformation steps. You must clarify whether you want to paginate **source documents**, **items after unwind**, or **aggregated groups**.

## 2. Preparing Lab Data

Select an isolated test database:

~~~javascript
use aggregation_paging_lab
~~~

Create the orders collection; the `createdAt` field intentionally includes duplicate timestamps to illustrate tie-breakers:

~~~javascript
db.orders.insertMany([
  {
    _id: "o-001", tenantId: "t-01", status: "PAID",
    region: "HCM", customerId: "c-101", score: 80,
    amount: NumberDecimal("250000"),
    createdAt: ISODate("2026-07-03T09:00:00Z")
  },
  {
    _id: "o-002", tenantId: "t-01", status: "PAID",
    region: "HN", customerId: "c-102", score: 92,
    amount: NumberDecimal("120000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-003", tenantId: "t-01", status: "CREATED",
    region: "HCM", customerId: "c-101", score: 76,
    amount: NumberDecimal("330000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-004", tenantId: "t-01", status: "PAID",
    region: "DN", customerId: "c-103", score: 92,
    amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-005", tenantId: "t-01", status: "CANCELLED",
    region: "HCM", customerId: "c-104", score: 61,
    amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-07-02T15:00:00Z")
  },
  {
    _id: "o-006", tenantId: "t-01", status: "PAID",
    region: "HN", customerId: "c-102", score: 85,
    amount: NumberDecimal("700000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-007", tenantId: "t-01", status: "PAID",
    region: "HCM", customerId: "c-103", score: 88,
    amount: NumberDecimal("520000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-008", tenantId: "t-02", status: "PAID",
    region: "HCM", customerId: "c-201", score: 75,
    amount: NumberDecimal("180000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-009", tenantId: "t-02", status: "CREATED",
    region: "HN", customerId: "c-202", score: 82,
    amount: NumberDecimal("310000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-010", tenantId: "t-02", status: "PAID",
    region: "DN", customerId: "c-201", score: 95,
    amount: NumberDecimal("800000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-011", tenantId: "t-02", status: "PAID",
    region: "HCM", customerId: "c-202", score: 90,
    amount: NumberDecimal("640000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-012", tenantId: "t-02", status: "CANCELLED",
    region: "HN", customerId: "c-203", score: 65,
    amount: NumberDecimal("100000"),
    createdAt: ISODate("2026-07-03T09:00:00Z")
  },
  {
    _id: "o-013", tenantId: "t-03", status: "PAID",
    region: "HCM", customerId: "c-301", score: 99,
    amount: NumberDecimal("930000"),
    createdAt: ISODate("2026-07-07T13:00:00Z")
  },
  {
    _id: "o-014", tenantId: "t-03", status: "CREATED",
    region: "DN", customerId: "c-302", score: 70,
    amount: NumberDecimal("200000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-015", tenantId: "t-03", status: "PAID",
    region: "HN", customerId: "c-301", score: 88,
    amount: NumberDecimal("430000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-016", tenantId: "t-03", status: "PAID",
    region: "HCM", customerId: "c-303", score: 90,
    amount: NumberDecimal("500000"),
    createdAt: ISODate("2026-07-07T13:00:00Z")
  }
])
~~~

Run `insertMany()` only once on an empty lab collection: re-running with the same `_id` values will trigger duplicate key errors. To start fresh, use a new lab database; do not delete data outside the practice scope.

Verify:

~~~javascript
db.orders.countDocuments({}) // 16

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, amount: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

The dataset contains:

| Status | Order count |
|---|---:|
| PAID | 11 |
| CREATED | 3 |
| CANCELLED | 2 |
| **Total** | **16** |

The examples below project `{_id: 1}` or `{_id: 1, createdAt: 1}` to make results easy to inspect, not to alter sorting logic.

## 3. `$sort`: Sorting Documents

### 3.1. Syntax

~~~javascript
{
  $sort: {
    fieldA: 1,
    fieldB: -1
  }
}
~~~

Where:

- `1`: sort ascending by the field.
- `-1`: sort descending by the field.
- When `fieldA` values tie, evaluate `fieldB`.
- Nested paths such as `"customer.address.city"` can be used when the field exists under an appropriate schema.

Example getting orders with larger amounts first:

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } },
  { $project: { _id: 1, amount: 1 } }
])
~~~

In the lab dataset, the orders with the largest amounts at the top are:

~~~text
o-013  930000
o-010  800000
o-006  700000
o-011  640000
o-007  520000
~~~

### 3.2. Multiple Keys in `$sort`

~~~javascript
db.orders.aggregate([
  {
    $sort: {
      status: 1,
      createdAt: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      createdAt: 1
    }
  }
])
~~~

MongoDB sorts first by status; within the same status, it evaluates createdAt descending; if dates tie, it evaluates `_id` ascending.

**This does not mean** MongoDB sequentially runs three independent sorts and "preserves" old order. It is **one multi-field comparison key**.

### 3.3. Sorting by Nested Fields

Suppose a document looks like:

~~~javascript
{
  _id: "p-01",
  customer: {
    profile: {
      loyaltyScore: 82
    }
  }
}
~~~

You can sort by the path:

~~~javascript
db.profiles.aggregate([
  {
    $sort: {
      "customer.profile.loyaltyScore": -1
    }
  }
])
~~~

If not every document contains this path, define the semantics for missing/null values and consider normalizing the schema.

### 3.4. Sorting by a Computed Value

`$sort` takes fields or supported sort specifications, not arbitrary calculation expressions in place of `1`/`-1`. To sort by a computed value, create the field first:

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      amountWithFee: {
        $multiply: ["$amount", NumberDecimal("1.05")]
      }
    }
  },
  {
    $sort: {
      amountWithFee: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountWithFee: 1
    }
  }
])
~~~

Because `amountWithFee` is computed inside the pipeline, a standard index on `amount` does not automatically provide the order of the computed expression in all cases; optimization potential depends on the transformation and query shape.

## 4. `$sort` Is Unstable When Keys Have Duplicate Values

MongoDB **does not guarantee the relative order of documents sharing the exact same full sort key**. If you only sort by `createdAt`, two orders created in the same second may appear in different orders across runs or different execution plans.

For example, two orders:

~~~text
o-006 createdAt = 2026-07-05T10:00:00Z
o-007 createdAt = 2026-07-05T10:00:00Z
~~~

The query:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1 } }
])
~~~

does not specify whether `o-006` or `o-007` comes first. When paginating with `$skip`, this nondeterminism can cause a document to appear on two pages or be skipped if the tie order shifts.

### Adding a Unique Tie-Breaker

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  }
])
~~~

Since `_id` is unique, the key `createdAt + _id` establishes a deterministic order over an **unchanged** dataset. On the lab dataset, `t-01`'s PAID orders are ordered as:

~~~text
o-006  2026-07-05 10:00
o-007  2026-07-05 10:00
o-002  2026-07-04 08:00
o-004  2026-07-04 08:00
o-001  2026-07-03 09:00
~~~

**Two guarantees must be distinguished:**

- A *tie-breaker* creates deterministic ordering when the dataset at read time is identical.
- *Snapshot consistency across multiple requests* is a separate problem: if new orders are inserted or old orders are modified between page fetches, data can still shift even with `_id` as a tie-breaker.

### When Sorting by Score

If multiple documents share `score: 92`, use:

~~~javascript
{ $sort: { score: -1, _id: 1 } }
~~~

so leaderboard results stay deterministic against the same snapshot. Never rely on the collection's "natural" order as a tie-breaker.

## 5. `$limit`: Allowing at Most N Documents to Proceed

### 5.1. Syntax

~~~javascript
{ $limit: 5 }
~~~

`$limit` accepts a positive integer representing the **maximum number of documents** allowed to pass through. MongoDB supports 64-bit integer limits in modern versions; the value must adhere to the representation and rules of the running version.

Example fetching the 3 orders with the highest amount:

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 3 },
  { $project: { _id: 1, amount: 1 } }
])
~~~

Result:

~~~text
o-013  930000
o-010  800000
o-006  700000
~~~

`$limit` **does not pick the business "top N"** unless preceded by an appropriate sort stage.

### 5.2. `$limit` Is Not a Filter Condition

~~~javascript
db.orders.aggregate([
  { $limit: 3 }
])
~~~

simply keeps at most the first three documents arriving at the pipeline in whatever order exists. Do not call those "the three newest orders" without sorting by date first.

### 5.3. Limiting After `$match`

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

Meaning: fetch the **5 newest PAID orders**. Placing `$limit` before `$match` could yield fewer than five PAID orders and would not give the five newest PAID orders across the collection.

### 5.4. `$limit` Does Not Guarantee N Documents

If only three documents remain after `$match`, `{ $limit: 10 }` still returns three. `$limit` is an **upper bound**, not a request to pad or guarantee a full page.

### 5.5. Limit Values from APIs Must Be Validated

In real APIs, never pass an unbounded client-supplied `pageSize` into `$limit`. For example, in the application layer:

~~~javascript
// Illustrates a variable validated at the API layer.
const requestedPageSize = 25
const pageSize = Math.min(Math.max(requestedPageSize, 1), 100)

db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: pageSize }
])
~~~

Capping page size protects database load, document serialization count, and response size. MongoDB does not know what page size suits your application's SLA.

## 6. `$skip`: Skipping the First N Documents in Current Order

### 6.1. Syntax

~~~javascript
{ $skip: 5 }
~~~

`$skip` takes a **non-negative** integer. `{ $skip: 0 }` skips no documents. Negative values, non-integers, or out-of-range values are invalid.

### 6.2. Skipping After Sorting

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 5 },
  { $project: { _id: 1, createdAt: 1 } }
])
~~~

The pipeline drops the **first five documents in the established order** and returns the remaining ones. Without `$sort`, `$skip` merely slices documents in the current execution order, which is not a safe foundation for pagination.

### 6.3. `$skip` Does Not Jump Directly to Position N

For offset pagination, the database usually still has to traverse or process results preceding the target position, even when an index serves the sort. For instance, `$skip: 100000` does not mean an index can jump instantaneously to "record 100001" without scanning/counting the preceding region.

This is why **deep offset pagination becomes progressively more expensive** as the page number increases. The keyset pagination section later presents an alternative.

### 6.4. Skipping More Than the Available Documents

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $skip: 1000 }
])
~~~

With 16 documents in the lab, the result is empty. Skipping past the end does not raise an error as long as the skip value itself is valid.

## 7. Combining `$sort`, `$skip`, and `$limit` for Offset Pagination

This is the classic pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  {
    $project: {
      _id: 1,
      amount: 1,
      createdAt: 1
    }
  }
])
~~~

Meaning: among `t-01`'s PAID orders, skip the first two and take the next two.

### 7.1. Offset Formula

For **1-based** page numbers:

\[
\mathrm{offset} = (\mathrm{page} - 1) \times \mathrm{pageSize}
\]

~~~text
page = 1, pageSize = 2 => skip = 0, limit = 2
page = 2, pageSize = 2 => skip = 2, limit = 2
page = 3, pageSize = 2 => skip = 4, limit = 2
~~~

### 7.2. Data Illustrating Three Pages

For `t-01`'s PAID subset:

| Position after sort | `_id` | `createdAt` |
|---:|---|---|
| 1 | `o-006` | 2026-07-05 10:00 UTC |
| 2 | `o-007` | 2026-07-05 10:00 UTC |
| 3 | `o-002` | 2026-07-04 08:00 UTC |
| 4 | `o-004` | 2026-07-04 08:00 UTC |
| 5 | `o-001` | 2026-07-03 09:00 UTC |

<escape>Therefore:</escape>

| Page | `$skip` | `$limit` | Result IDs |
|---|---:|---:|---|
| 1 | 0 | 2 | `o-006`, `o-007` |
| 2 | 2 | 2 | `o-002`, `o-004` |
| 3 | 4 | 2 | `o-001` |
| 4 | 6 | 2 | Empty |

### 7.3. Parameterized Pipeline Pattern

~~~javascript
const page = 2
const pageSize = 2
const offset = (page - 1) * pageSize

if (!Number.isSafeInteger(page) || page < 1) {
  throw new Error("INVALID_PAGE")
}
if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100) {
  throw new Error("INVALID_PAGE_SIZE")
}
if (!Number.isSafeInteger(offset)) {
  throw new Error("OFFSET_OUT_OF_RANGE")
}

db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: offset },
  { $limit: pageSize },
  { $project: { _id: 1, amount: 1, createdAt: 1 } }
])
~~~

In applications, `tenantId` must come from an authenticated context; never trust a client-declared tenant ID as an authorization mechanism. Also enforce API-appropriate upper bounds on offset/page, because even valid integers can lead to very expensive pagination queries.

## 8. How Does Stage Order Change the Result?

### 8.1. Correct: Sort First, Limit After

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Returns the three orders with the highest amount across the entire collection.

### 8.2. Wrong Intent: Limit First, Sort After

~~~javascript
db.orders.aggregate([
  { $limit: 3 },
  { $sort: { amount: -1, _id: 1 } }
])
~~~

This pipeline first accepts only the first three documents arriving in the current pipeline order, **then** sorts just those documents. It is not a "top 3 amount across the collection" query.

Putting `$sort` after `$limit` only makes sense if you intentionally want to pick an arbitrary subset first and sort that subset alone; that is a different business requirement.

### 8.3. Wrong Intent: Limit Before Skip

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $limit: 2 },
  { $skip: 2 }
])
~~~

Logically, `$limit` lets only two documents through and `$skip` drops both, resulting in an empty output. This is not equivalent to:

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $skip: 2 },
  { $limit: 2 }
])
~~~

In some stage sequences, the query optimizer can **transform execution while preserving semantics**, yet developers must still write pipelines matching their intended logic. Do not swap two stages and hope the optimizer fixes the bug.

### 8.4. Wrong Intent: Skip Before Sort

~~~javascript
db.orders.aggregate([
  { $skip: 10 },
  { $sort: { createdAt: -1 } },
  { $limit: 5 }
])
~~~

Here the first 10 documents of an **unspecified input order** are discarded before sorting. The newest orders may have already been dropped. To paginate a list sorted by date, you must sort **before skipping**.

### 8.5. Where Does Match Go?

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

means the three newest PAID orders.

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 },
  { $match: { status: "PAID" } }
])
~~~

means take the three newest orders **regardless of status**, then keep only the PAID ones among those three. The result can have fewer than three documents or miss the next newest PAID order. The two pipelines are not equivalent.

## 9. Sort Is a Blocking Stage: Memory and Cost

`$sort` is generally a **blocking stage**: to determine the order of the entire input, the engine may need to collect, organize, or manage many documents before emitting output. It can put pressure on memory, CPU, and I/O, especially when index order cannot be exploited.

### 9.1. Sorting Everything Without a Limit

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } }
])
~~~

If the input has millions of documents and no index serves this order, sorting can consume heavy resources.

### 9.2. Top-K: Sort Followed by Limit

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

MongoDB can apply **`$sort` + `$limit` coalescence** (*top-k sort optimization*): when conditions allow, instead of buffering the entire input to sort, the engine maintains a bounded pool of the best N candidates. This often reduces memory usage substantially.

This is a query planner optimization; do not interpret it as "only reads 20 documents" if no helpful index exists. To find the top 20 of a large set, the engine may still have to inspect many documents even while keeping only the top K in memory.

### 9.3. Sort, Skip, Limit, and the Internal K Bound

For:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 1000 },
  { $limit: 20 }
])
~~~

When the planner applies the corresponding optimization, the sort may need to retain candidates for the first **1000 + 20 = 1020** positions to determine the 20 documents after skipping 1000. The **offset + limit** sum illustrates why deep pagination stays expensive: page 10000 is not as cheap as page 1 just because the final `$limit` is still 20.

Do not hardcode one formula to predict every plan: optimization also depends on intervening stages, index eligibility, and MongoDB version.

### 9.4. Memory Limits and Disk Spill

Many aggregation stages require memory to execute. For a `$sort` that cannot use an index, when resource consumption exceeds limits, the server may need to write temporary data to disk (*spill*). In modern MongoDB versions, the threshold is typically tied to **100 MB** for memory-intensive stages; since MongoDB 6.0, the `allowDiskUseByDefault` parameter controls whether exceeding the limit spills by default or errors, with per-command override capability.

Illustrative command:

~~~javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { amount: -1, _id: 1 } },
    { $limit: 100 }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse: true` **permits** supported stages to write temporary files to disk when needed; it does not automatically make queries fast, does not replace indexes, and can increase disk I/O. `allowDiskUse: false` or specific server defaults may cause an error if the sort exceeds the threshold without spill permission. Verify against your actual MongoDB version and configuration.

### 9.5. Reducing Input Before Sorting

Place `$match` early when logic allows:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

Fewer documents to sort reduces resource consumption. However, do not push `$match` earlier if the condition depends on a computed field that does not exist yet or changes meaning across `$unwind`/`$group`. The query optimizer may push certain filters when safe, but you should write pipelines transparently reflecting business intent.

## 10. When Can an Index Serve `$sort`?

A pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

can benefit from a compound index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

The first two fields are filtered by equality, and the last two provide descending date, ascending ID order. This is an example of applying the **Equality – Sort – Range** (ESR) rule when designing indexes for common queries.

### 10.1. Example Where Sort Can Use an Index

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

With suitable data and plan, MongoDB can traverse the index in order and return results without needing a separate in-memory SORT stage.

### 10.2. Example Where Sort Is Not Fully Served by the Index

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

The index `{tenantId:1,status:1,createdAt:-1,_id:1}` has the **status field sitting between** tenantId and createdAt. Without an equality predicate on status, keys are grouped by status before creation date; that index does not naturally provide newest-date order across the **entire tenant**. You may need an index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: 1 },
  { name: "idx_tenant_date_id" }
)
~~~

### 10.3. Sorting After Transformation Stages

Example:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$region", revenue: { $sum: "$amount" } } },
  { $sort: { revenue: -1, _id: 1 } }
])
~~~

`revenue` is computed after `$group`, so an index on the source document's `amount` field cannot automatically provide ordering by **total revenue**. This sort applies to the newly generated group documents.

Similarly, after `$unwind` or `$addFields`, whether index sort order from the source collection can be preserved depends on the plan and cannot be inferred merely from the fact that a field had an index.

### 10.4. Sorting on a Single-Field Index

If sorting only by:

~~~javascript
{ $sort: { createdAt: -1 } }
~~~

a single-field index `{createdAt:1}` can in many cases be scanned **in reverse** to satisfy a descending sort. However, for multi-field sorts with **mixed directions**, a compound index must match the pattern or its exact full inverse.

You do not need to create both ascending and descending indexes on a single field just because an API supports both sort directions.

## 11. Using `explain()` to Observe Performance

You can use:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Elements to inspect:

| Field/stage | How to interpret |
|---|---|
| `winningPlan` | Selected execution plan |
| `IXSCAN` | Stage reading index keys |
| `COLLSCAN` | Stage scanning the collection |
| `FETCH` | Stage reading documents to evaluate/return fields |
| `SORT` | Dedicated sort operation present |
| `LIMIT`/`SKIP` or equivalent representation | Count/position control as lowered by the optimizer |
| `nReturned` | Number of documents returned at the relevant statistics stage |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `executionTimeMillis` | Recorded execution time for the run |

`explain` JSON structure can differ between the classic engine and Slot-Based Execution, and the optimizer can merge stages. Therefore, **do not assume every pipeline stage must appear as one exact corresponding node** in the execution plan.

### 11.1. Distinguishing COLLSCAN from In-Memory Sort

`COLLSCAN` means reading the collection; the query may still need no sort if no ordering was requested. `IXSCAN` does not automatically guarantee there is no SORT; an index might assist the filter without providing sort order. Inspect **both the access path and the sort mechanism**.

### 11.2. Verification Questions

- Which index was used for `$match`?
- Did `$sort` leverage index order?
- Is there a separate SORT stage?
- Were many keys/documents examined before `$skip` discarded them?
- Did `$limit` reduce sort resources or the number of documents needing FETCH?
- Did the query spill to disk, according to server/profiler telemetry?
- How does latency differ between page 1 and page 10000?

**Do not benchmark on 16 documents and draw speed conclusions.** On tiny datasets, MongoDB can reasonably pick COLLSCAN; a few milliseconds of latency is not representative of real data.

## 12. Deep Pagination: Limitations of Offset Pagination

An API call:

~~~http
GET /orders?page=10000&pageSize=20
~~~

leads to:

~~~text
offset = (10000 - 1) × 20 = 199980
limit = 20
~~~

Pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 199980 },
  { $limit: 20 }
])
~~~

Even with an index serving the sort order, the database typically still must **walk past many preceding results** before returning the requested page. If data is continuously inserted/deleted, offset positions can also shift between calls.

### 12.1. When Offset Pagination Is Still Appropriate

- First page or first few pages, small offsets.
- Admin UIs with moderate data volume.
- Users genuinely need to jump to numbered pages.
- Workload is light and cost has been measured.
- Low data churn, or minor drift between pages is acceptable.

### 12.2. When to Consider Keyset Pagination

- Infinite feeds or "Load more" UIs.
- Millions of documents and deep pages.
- Need pagination in stable order backed by indexed keys.
- No need to jump directly to page 10,000 by page number.
- Want to eliminate large offset traversal overhead.

## 13. Keyset Pagination: Paginating by the Previous Page's Last Key

Instead of passing `skip: 100000`, the client passes **the last sort key of the previous page**. With:

~~~javascript
{ $sort: { createdAt: -1, _id: 1 } }
~~~

we need a cursor consisting of two values:

~~~javascript
{
  lastCreatedAt: ISODate("2026-07-05T10:00:00Z"),
  lastId: "o-007"
}
~~~

Because createdAt is descending, documents **after** the cursor have either:

1. `createdAt` smaller than the cursor timestamp, **or**
2. `createdAt` equal to the cursor timestamp and `_id` greater than the cursor ID (because `_id` is ascending within the same-date group).

### 13.1. First Page

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Result: `o-006`, `o-007`. The client retains `createdAt` and `_id` of `o-007` to fetch the next page.

### 13.2. Next Page

~~~javascript
const cursorDate = ISODate("2026-07-05T10:00:00Z")
const cursorId = "o-007"

db.orders.aggregate([
  {
    $match: {
      tenantId: "t-01",
      status: "PAID",
      $or: [
        { createdAt: { $lt: cursorDate } },
        {
          createdAt: cursorDate,
          _id: { $gt: cursorId }
        }
      ]
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Result: `o-002`, `o-004`. No `$skip` is needed because the cursor predicate excludes all documents in prior positions.

### 13.3. Matching Index

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

This is a candidate index for the equality filter + keyset condition + sort. With `$or`, the planner may evaluate multiple branches/bounds; use `explain` to verify.

### 13.4. When Sorting in Another Direction, Condition Signs Must Change

If using:

~~~javascript
{ $sort: { amount: -1, _id: -1 } }
~~~

then the next page requires:

~~~javascript
{
  $or: [
    { amount: { $lt: lastAmount } },
    {
      amount: lastAmount,
      _id: { $lt: lastId }
    }
  ]
}
~~~

Do not copy the `_id: {$gt: ...}` condition from a mixed-direction sort into a sort where both fields are descending. The cursor condition must match the exact comparison semantics of the sort key tuple.

### 13.5. Keyset Also Has Limitations

- Requires a sort key tuple with a strict total order (typically adding a unique ID).
- Sort keys might change after pagination begins, shifting documents.
- Insertions/deletions between requests still affect the dataset; keyset **does not automatically provide a full-session snapshot**.
- Does not support jumping directly to an arbitrary page number without a cursor.
- Cursors should be encoded and validated, bound to filter/sort/tenant to prevent misuse.

If you need a consistent snapshot across multiple points in time, you must design reads against a version/cutoff or an appropriate consistency mechanism, not rely solely on `$sort`.

## 14. Paginating with Total Result Count Using `$facet`

APIs often want to return:

~~~javascript
{
  items: [/* documents of the current page */],
  total: 5
}
~~~

A pipeline can use `$facet` to create two branches on the same **matched** input set:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $facet: {
      items: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 2 },
        { $limit: 2 },
        {
          $project: {
            _id: 1,
            createdAt: 1,
            amount: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
])
~~~

On the lab data:

~~~javascript
{
  items: [
    { _id: "o-002", /* createdAt and amount */ },
    { _id: "o-004", /* createdAt and amount */ }
  ],
  metadata: [
    { total: 5 }
  ]
}
~~~

**Meaning:** the `items` branch returns one page, while the `metadata` branch counts all documents that passed `$match` before `$facet`, not just the items on the page.

### 14.1. Watching the Cost of `$facet`

`$facet` is not free: each branch must process input data, and the final output is **one document** holding the arrays. This stage has its own memory/output size limits and cannot always leverage index optimizations like a linear `$match → $sort → $limit` pipeline.

If `$facet` sits right at the start of a pipeline, it can force scanning the whole collection undesirably. Usually, place an index-friendly `$match` before `$facet`, and benchmark on a realistic workload.

### 14.2. Why Can Metadata Be Empty?

If zero documents match, the branch:

~~~javascript
metadata: [{ $count: "total" }]
~~~

can return `[]`, not `[{total:0}]`. The API layer should normalize this to `0` if required by the contract, or add an appropriate transformation stage for a consistent response shape.

### 14.3. Two Separate Queries Can Also Be Reasonable

You are not forced to use `$facet` for every API. You can run:

~~~javascript
db.orders.countDocuments({ tenantId: "t-01", status: "PAID" })
~~~

alongside a pipeline fetching the page. This can leverage indexes with two separate plans, though two separate requests might observe different data states under concurrent writes. Choose based on consistency, performance, and API interface requirements.

## 15. `$sort` After `$group`: Leaderboards from Aggregated Data

When building a revenue leaderboard by region, each input document is an order, whereas each output result is **a group**.

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$region",
      totalRevenue: { $sum: "$amount" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalRevenue: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Flow:

~~~mermaid
flowchart LR
    O["N orders"] --> M["PAID only"]
    M --> G["$group by region"]
    G --> R["3 group documents: HCM/HN/DN"]
    R --> S["$sort by totalRevenue"]
    S --> L["$limit: top 3 regions"]
~~~

### 15.1. Placing Limit Before Group Is a Different Problem

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

This pipeline counts **by region within the 5 newest orders**, not across all orders in the collection to find the top 5 regions.

### 15.2. Placing Sort Before Group Affects `$first` and `$last`

Example finding the newest order per customer:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      latestOrder: { $first: "$$ROOT" }
    }
  },
  {
    $project: {
      _id: 1,
      latestOrderId: "$latestOrder._id",
      latestCreatedAt: "$latestOrder.createdAt"
    }
  }
])
~~~

`$first` picks the first value according to the order documents arrive at `$group`. If you need the "newest," establish the order before grouping or use dedicated accumulators supported in your MongoDB version. **Sort by a deterministic key**, including a tie-breaker, to avoid arbitrary selection when timestamps tie.

## 16. `$sort` with `$unwind`: Document Order and Array Elements

Suppose:

~~~javascript
db.baskets.insertMany([
  {
    _id: "basket-1",
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 5 }
    ]
  },
  {
    _id: "basket-2",
    items: [
      { sku: "C", qty: 3 },
      { sku: "D", qty: 2 }
    ]
  }
])
~~~

To fetch the **top 3 line items** by qty:

~~~javascript
db.baskets.aggregate([
  { $unwind: "$items" },
  { $sort: { "items.qty": -1, _id: 1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

After `$unwind`, each intermediate document represents **one item**, so `$limit: 3` caps the output at **three items**, not three baskets.

Conversely:

~~~javascript
db.baskets.aggregate([
  { $limit: 1 },
  { $unwind: "$items" }
])
~~~

selects just one input basket and then expands all items of that basket. The output can contain more than one document despite `$limit: 1` at the start of the pipeline.

### Mental Check When Using `$skip` After `$unwind`

Ask: "What is one document at this stage?" If after unwind a document is an item, then `$skip: 10` skips **10 unwound items**, not 10 original baskets. To paginate baskets, normally place `$sort/$skip/$limit` at the stage where each basket is still a single document, before unwinding, if business requirements allow.

## 17. Ordering of Missing Fields, `null`, and BSON Types

Sorting follows MongoDB's BSON comparison rules. Documents whose sort field is missing or `null` may sort differently relative to documents containing strings, numbers, or Dates.

### 17.1. Missing Fields

~~~javascript
db.sort_values.insertMany([
  { _id: "v-1", rank: 3 },
  { _id: "v-2", rank: null },
  { _id: "v-3" },
  { _id: "v-4", rank: 1 }
])

db.sort_values.aggregate([
  { $sort: { rank: 1, _id: 1 } }
])
~~~

In sort comparisons, missing and null have closely related semantics; adding `_id` creates deterministic ordering among documents with equivalent sort keys.

If a real product requires "putting documents missing rank at the end" regardless of ascending/descending order, **create a dedicated sort key** with explicit logic:

~~~javascript
db.sort_values.aggregate([
  {
    $addFields: {
      missingRank: {
        $cond: [
          { $in: [{ $type: "$rank" }, ["missing", "null"]] },
          1,
          0
        ]
      }
    }
  },
  { $sort: { missingRank: 1, rank: 1, _id: 1 } }
])
~~~

This example flags both missing and explicit null values to sort last. Using a computed expression can alter whether an index can serve the sort.

### 17.2. Mixed Data Types

If `amount` is Decimal128 in one document and string `"500000"` in another, sorting groups values by BSON type precedence rather than interpreting strings as currency. Principles:

- Use consistent BSON numeric types for numeric fields.
- Use BSON Date for timestamps.
- Standardize timezones and formatting conventions at the API layer.
- Use schema validation if the system requires fixed types.

### 17.3. Sorting by Arrays

When the sort field is an array, MongoDB follows specific rules to pick a representative value from the array: in typical cases, **ascending sort uses the smallest element**, whereas **descending sort uses the largest element** of the array for comparison. A `$match` condition on the array does not necessarily change which element is chosen for sorting as you might expect.

Example:

~~~javascript
db.array_sort_lab.insertMany([
  { _id: "a-1", scores: [30, 90] },
  { _id: "a-2", scores: [45, 60] },
  { _id: "a-3", scores: [10, 100] }
])

db.array_sort_lab.aggregate([
  { $sort: { scores: 1, _id: 1 } }
])

db.array_sort_lab.aggregate([
  { $sort: { scores: -1, _id: 1 } }
])
~~~

In ascending sort, the representative comparison values are 30, 45, and 10; the order differs in descending sort, which uses 90, 60, and 100. If business logic needs sorting by **average**, **sum**, or a **specific filtered element**, compute the corresponding scalar field before `$sort` (e.g., `$avg` or `$max`) rather than relying on default array sorting.

## 18. Collation: Language-Aware String Sorting

If there is a `displayName` field, string sorting is affected by collation. Choices regarding case sensitivity, diacritics, and locale can produce different orderings.

~~~javascript
db.customers.aggregate(
  [
    { $sort: { displayName: 1, _id: 1 } },
    { $limit: 20 }
  ],
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
)
~~~

The exact behavior of `locale` and `strength` depends on MongoDB/ICU collation rules. Never assume every collation produces the same order as byte/binary string comparison.

### Collation and Indexes

If an index is created with a different collation from the query, MongoDB may not be able to use that index for string equality or sorting. When building a name directory:

1. Identify the collation required by the API.
2. Create an index with the matching collation if the workload is important.
3. Ensure queries specify the same collation per the contract.
4. Check `explain()` to confirm there is no unexpected SORT stage.

Collation does not replace identifier normalization or access-control checks.

## 19. Sorting After `$project` and Other Transformations

If a stage drops a field needed for sorting, the next stage may no longer have data to compare:

~~~javascript
// Unsuitable if intending to sort by createdAt because the field was dropped.
db.orders.aggregate([
  { $project: { _id: 1, status: 1 } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

Logically, `createdAt` is gone from the document after projection. The query optimizer may swap stages when proven safe in some cases, yet developers should never design pipelines assuming "the optimizer will always fix it."

Clear version:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, status: 1 } }
])
~~~

Here the required field is kept until sorting finishes, then dropped.

### 19.1. When You Need to Sort on a Newly Created Field

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerId: 1,
      normalizedScore: { $multiply: ["$score", 10] }
    }
  },
  { $sort: { normalizedScore: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

This is an example where you **must compute before sorting**. You cannot sort by `normalizedScore` before it exists if there is no equivalent field in the source collection.

### 19.2. Tracking Cardinality-Changing Boundaries

| Stage | Can change downstream document count? | Impact on pagination |
|---|---|---|
| `$match` | Yes, filters down | Page is based on the filtered set |
| `$sort` | Does not add/remove on its own | Determines order |
| `$skip` | Yes, drops prefix | Shifts starting point |
| `$limit` | Yes, keeps at most N | Bounds page size |
| `$project` | Usually preserves count | Changes fields returned or available to sort |
| `$unwind` | Can increase/decrease | Page after unwind is an item page |
| `$group` | Can decrease/alter cardinality | Page after group is a group page |
| `$lookup` | Usually preserves document count until unwound | Can widen documents, affecting sort/memory |

Good practice: **sketch what one document represents at each stage** before placing pagination.

## 20. Sorting by Score and Building Leaderboards

Gaming or review applications might rank entries:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { score: -1, createdAt: 1, _id: 1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      score: 1,
      createdAt: 1
    }
  }
])
~~~

When scores tie, favor older creation times; if still tied, smaller ID wins. This is a concrete **business rule**. Document the secondary ordering clearly so users do not see leaderboard rankings shift unexpectedly.

### 20.1. Top N per Group Differs from Global Top N

The pipeline:

~~~javascript
db.orders.aggregate([
  { $sort: { score: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

takes the top 3 of the **entire collection**.

If you need the **top 3 per tenant**, global `$sort + $limit` is not enough. You need a pipeline using `$group`, window operators, or a top-N accumulator supported by your version so each group gets its own limit. That is a more advanced pattern than global pagination.

### 20.2. Rank Does Not Equal Post-Limit Position

If two documents have the same score, the concept of **rank** may assign them a tie, whereas `$sort` with a tie-breaker still places one document ahead of the other. If tied rankings are needed, consider window functions like `$rank`/`$denseRank` in an appropriate pipeline rather than inferring rank from list index.

## 21. Pagination and Consistency When Data Changes

Suppose page 1 returns:

~~~text
o-006
o-007
~~~

between the client fetching page 1 and page 2, a new order `o-new` is inserted with a `createdAt` newer than all existing orders. The sorted list shifts:

~~~text
Before insert:
1 o-006
2 o-007
3 o-002
4 o-004

After insert:
1 o-new
2 o-006
3 o-007
4 o-002
5 o-004
~~~

When fetching page 2 with `$skip: 2`, the client may see `o-007` again—a record that already appeared on page 1.

### 21.1. A Tie-Breaker Alone Is Not Enough

`_id` guarantees deterministic order when data stays unchanged, but **inserts/deletes/updates between requests** can still shift offsets.

### 21.2. Keyset Reduces Offset Drift

Using a cursor after `o-007`, a newly inserted order newer than the cursor will not shift subsequent pages by offset. Keyset is therefore friendlier to continuously updated feeds. However:

- Updating an old document's sort key can still cause changes.
- Documents deleted between pages will disappear.
- Subsequent queries may observe newly inserted documents falling behind the cursor.

Never advertise keyset as an absolute snapshot.

### 21.3. When a Fixed Dataset Is Needed

For audit exports or consistent full-dataset traversal, you may need to:

- Freeze the data range using a cutoff/version.
- Bind queries to a snapshot/transaction within supported limits.
- Build a temporary ID list or stable materialized result.
- Use a batch export designed for consistency.

Do not hold a transaction open for hours just to paginate a normal API; transaction limits and resource overhead must be factored into the architecture.

## 22. Which Queries Should Use `$sort`, `$limit`, and `$skip`?

| Requirement | Pipeline pattern | Notes |
|---|---|---|
| 10 newest orders | `$sort → $limit` | Include a tie-breaker |
| Page 3, 20 per page | `$sort → $skip:40 → $limit:20` | Large offsets can be expensive |
| 5 newest PAID orders | `$match → $sort → $limit` | Match before limiting |
| Top 5 highest-revenue regions | `$match → $group → $sort → $limit` | Sort on group results |
| Top 10 items after splitting arrays | `$unwind → $sort → $limit` | Paginating by item |
| Page with total record count | `$match → $facet(items,metadata)` | Measure memory footprint/latency |
| Next feed page via cursor | `$match(cursor) → $sort → $limit` | Avoids deep offsets |
| Locale-sorted name list | `$sort` + `collation` | Index needs matching collation |
| Sort by computed field | `$addFields/$project → $sort → $limit` | May not use an index for sorting |

## 23. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `$skip` without `$sort` | Pages lack stable ordering | Sort by deterministic keys before skipping |
| Sorting only by non-unique timestamp | Documents swap positions across pages | Add `_id` or a unique key as tie-breaker |
| `$limit` before `$sort` for top N | Sorts only an arbitrary subset | Sort the full candidate set then limit |
| `$limit` before `$skip` when paginating | Skips within an already capped set, possibly empty | Sort → skip → limit |
| `$match` after `$limit` to find top PAID | Misses valid PAID orders outside initial limit | Match → sort → limit |
| `$sort` after `$project` dropped sort key | All documents appear to lack the sort field | Sort before dropping or retain the field |
| Treating large `$skip` as instant jump | Deep page queries become slow | Keyset/cursor pagination |
| Ignoring document count after `$unwind` | Paginating items instead of orders | Place stages according to the target entity |
| Assuming filter index automatically covers all sorts | Extra SORT stage remains | Align filter+sort index, verify with explain |
| Assuming `allowDiskUse:true` is always fast | Disk spill can incur heavy I/O | Match early, top-k, appropriate indexes |
| Forgetting page validation | Negative skip, invalid limit, or huge offset | Validate page/pageSize/offset |
| Treating tie-breaker as multi-request snapshot | Inserts/deletes still shift the dataset | Use keyset, cutoff/version/snapshot as needed |
| Counting post-`$limit` results as total | Wrong total | Count on matched set before pagination |
| Sorting array expecting average order | MongoDB uses its own array sort rules | Compute desired sort key beforehand |
| Comparing numeric currency with strings | BSON type order does not reflect numeric value | Standardize data types |

## 24. Comprehensive Practice on `orders`

Use the 16-document dataset from section 2. Before running each query, predict the IDs and explain **which set each stage is processing**.

### Exercise 1 — Sort by Amount

Write an aggregation returning the 5 orders with the largest `amount`, projecting `_id` and `amount`, using `_id` as a tie-breaker. Predict the order of the five IDs.

### Exercise 2 — Sort by Two Fields

Fetch all orders for `t-01`, sorted by `createdAt` descending and `_id` ascending. Why is sorting by createdAt alone insufficient?

### Exercise 3 — Three Consecutive Pages

Fetch `t-01`'s PAID orders with `pageSize = 2`. Run:

- Page 1: skip 0, limit 2.
- Page 2: skip 2, limit 2.
- Page 3: skip 4, limit 2.

Record the results and explain why page 3 only has one document.

### Exercise 4 — Stage Order

Compare two pipelines:

~~~javascript
// A
[
  { $sort: { amount: -1 } },
  { $limit: 3 }
]

// B
[
  { $limit: 3 },
  { $sort: { amount: -1 } }
]
~~~

Do they mean the same thing? In what scenario would B make sense?

### Exercise 5 — Filter Before or After Limit?

Write two pipelines: one returning the **3 newest PAID orders**, and one taking the **3 newest orders in the collection and keeping only PAID**. Explain why the result counts differ.

### Exercise 6 — Group Then Sort

Compute total `amount` for PAID orders by `region`, sort highest to lowest, and take the top 2 regions. Why can you not put `$limit:2` before `$group` if you want the total across all PAID orders?

### Exercise 7 — Adding `$project`

Get the 5 newest orders, returning only `_id`, `tenantId`, and `status`. Where should `$project` be placed so sorting by `createdAt` still works properly?

### Exercise 8 — Index

Create:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
})
~~~

Run `db.orders.explain("executionStats").aggregate(...)` for a tenant's PAID listing query. Inspect the plan and discuss why 16 documents are insufficient to draw performance conclusions.

### Exercise 9 — Keyset

Page 1 of `t-01` PAID orders contains `o-006`, `o-007`. Write the page 2 filter using `o-007`'s cursor in `createdAt:-1,_id:1` order without using `$skip`.

### Exercise 10 — Total Count

Build a `$facet` returning page 2 and `total` for `t-01`'s PAID orders. Count total from the set before `$skip`.

### Exercise 11 — Sorting by Array

Insert the three documents with score arrays from section 17.3, compare ascending and descending sort results, and explain which array element is used for default comparison.

### Exercise 12 — Deep Pagination

For page 10,000 and size 20, compute the offset and explain why an index serving the sort still does not turn `$skip` into an O(1) operation. Propose an alternative pagination strategy and its limitations.

## 25. Guided Answers

### Exercise 1

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, amount: 1 } }
])
~~~

Result: `o-013`, `o-010`, `o-006`, `o-011`, `o-007`.

### Exercise 2

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

`o-006` and `o-007` share the same timestamp. Adding `_id` ensures the relative order of these two documents is deterministic when the dataset is unchanged.

### Exercise 3

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1 } }
])
~~~

Page 1: `o-006`, `o-007`; page 2: `o-002`, `o-004`; page 3: `o-001`. There are five matching documents, so the third page does not have two documents.

### Exercise 4

A returns the global top 3. B first caps the pipeline to three incoming documents, then sorts them; it does not solve the same problem. B only makes sense when **picking a subset first** is the actual business intent.

### Exercise 5

~~~javascript
// 3 newest PAID orders.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 }
])

// Take 3 newest orders, then filter for PAID.
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 },
  { $match: { status: "PAID" } }
])
~~~

The two pipelines operate on different candidate sets. If the global top 3 contains a CREATED order, the second pipeline may return fewer than 3 PAID orders.

### Exercise 6

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$region",
      totalRevenue: { $sum: "$amount" }
    }
  },
  { $sort: { totalRevenue: -1, _id: 1 } },
  { $limit: 2 }
])
~~~

Limiting before group only sums over a truncated subset, not the total of all PAID orders.

### Exercise 7

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, tenantId: 1, status: 1 } }
])
~~~

Sort before stripping `createdAt` from the returned output.

### Exercise 9

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "t-01",
      status: "PAID",
      $or: [
        {
          createdAt: { $lt: ISODate("2026-07-05T10:00:00Z") }
        },
        {
          createdAt: ISODate("2026-07-05T10:00:00Z"),
          _id: { $gt: "o-007" }
        }
      ]
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 }
])
~~~

Result: `o-002`, `o-004`. The `_id: {$gt: ...}` condition is correct because IDs are sorted ascending within groups sharing the same createdAt.

### Exercise 10

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $facet: {
      items: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 2 },
        { $limit: 2 }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
])
~~~

`total = 5` even though page 2 only returns two documents.

### Exercise 12

`offset = 199980`. `$skip` still has to discard results preceding the target window; keyset uses conditions based on the previous page's final key, fitting sequential feeds, though it cannot jump to arbitrary page numbers and does not inherently guarantee snapshots across multiple requests.

## 26. Review Questions

**1. How does `$sort` differ from `$limit`?**

`$sort` determines document order; `$limit` allows at most N documents to proceed. To get the top N by a criterion, you typically must sort before limiting.

**2. Does `$skip` sort documents on its own?**

No. It merely drops the first N documents in the current input order. Stable pagination requires an explicit sort.

**3. Why is sorting by createdAt alone insufficient for pagination?**

Multiple documents can share the same timestamp. MongoDB does not guarantee order among equal sort values; add a unique `_id` as a tie-breaker.

**4. Is placing `$limit` before `$sort` always wrong?**

Not syntactically wrong, but it solves a different problem: capping input first and then sorting that subset. It does not produce the global top N.

**5. Formula for 1-based page p with size n?**

`skip = (p - 1) × n`, followed by `limit = n`, given an established sort order.

**6. Is a page returning fewer than n documents an error?**

No. `$limit` is only an upper bound; fewer documents may remain after filtering/skipping.

**7. Can `$sort` use an index in aggregation?**

Yes, when the query shape/stages and index align, such as an equality prefix `$match` followed by sorting on trailing keys. Not every `$sort` can be served by an index.

**8. Why does sorting after `$group` usually operate on grouped results?**

Aggregated fields like `totalRevenue` do not exist in the source collection; they are computed by `$group`. An index on the source amount field does not provide ordering by total revenue.

**9. Does `allowDiskUse:true` make every sort faster?**

No. It allows eligible stages to spill temporarily to disk when needed; disk spilling can incur I/O overhead. Indexes and reducing input remain crucial.

**10. What performance advantage does `$sort + $limit` have?**

The planner can apply top-k/coalescence to maintain only the best N candidates, lowering memory usage in eligible cases. It does not mean only N documents are examined.

**11. Why is skipping 100,000 usually slower than skipping 20?**

The database still must traverse or process many results preceding a large offset. An index does not turn skip into an O(1) positional jump.

**12. How does keyset pagination differ from offset pagination?**

Offset skips the first N documents. Keyset filters against the last sort key of the previous page and takes the next `limit`, usually avoiding deep offset scans and reducing drift from inserts ahead of the cursor.

**13. Does keyset guarantee a snapshot across all pages?**

No. Data mutations between requests can still affect results. Use a cutoff/version/snapshot when high consistency is required.

**14. To return the total count of the filtered set, should you count before or after skip/limit?**

Count on the matched set **before pagination**. `$facet` can run one count branch and one items branch.

**15. What objects does `$sort` after `$unwind` sort?**

It sorts the intermediate documents produced after each array element is expanded. A subsequent `$limit` bounds the number of unwound elements, not necessarily source documents.

**16. Do you need `$project` to limit the number of documents?**

No. `$project` selects/transforms fields; `$limit` and `$skip` control document counts. However, `$project` can remove sort keys if placed in the wrong spot.

**17. Do string monetary values and numeric monetary values sort the same way?**

Never assume so. BSON enforces type-based ordering rules; store consistent numeric types and apply schema validation.

**18. Why does collation matter when sorting names?**

Because case sensitivity, diacritics, and locale rules affect ordering. Queries and indexes need matching collations to leverage indexes for string sorting.

## 27. Quick Reference Table

| Purpose | Stage / pipeline |
|---|---|
| Sort ascending | `{$sort:{amount:1}}` |
| Sort descending | `{$sort:{createdAt:-1}}` |
| Sort with tie-breaker | `{$sort:{createdAt:-1,_id:1}}` |
| Keep at most N documents | `{$limit:N}` with positive N |
| Skip first N documents | `{$skip:N}` with non-negative N |
| Top N documents | `$sort → $limit` |
| Page p, size n | `$sort → $skip:(p-1)*n → $limit:n` |
| Top N after filter | `$match → $sort → $limit` |
| Rank groups by sum | `$group → $sort → $limit` |
| Top items after unwinding array | `$unwind → $sort → $limit` |
| Page with total count | `$match → $facet(items, metadata)` |
| Next page without offset | `$match(cursor) → $sort → $limit` |
| Sort computed field | `$addFields/$project → $sort` |
| Allow spill when supported | `aggregate(pipeline,{allowDiskUse:true})` |
| Inspect execution plan | `db.orders.explain("executionStats").aggregate(pipeline)` |

## 28. Pre-Deployment Checklist for Pagination APIs

- [ ] Does the pre-pagination filter enforce tenant, access-control, and status boundaries?
- [ ] Does the sort order reflect business requirements?
- [ ] Is a unique tie-breaker like `_id` included to handle duplicate sort values?
- [ ] Does `$sort` appear before `$skip` and `$limit` when ordered top/pages are required?
- [ ] Are page/pageSize/offset validated as integers within API-defined bounds?
- [ ] Are deep pages capped or handled via keyset/cursor pagination for large datasets?
- [ ] Do sort keys have consistent types, with null/missing/arrays handled per contract?
- [ ] Is there an index aligned with `$match` and `$sort` order?
- [ ] Have you checked `explain` to distinguish IXSCAN, FETCH, SORT, and keys/docs examined?
- [ ] Are memory/disk spill limits controlled for large sort pipelines?
- [ ] Is total count calculated on the filtered set before pagination?
- [ ] Are `$unwind`/`$group` stages placed appropriately for the entity being paginated?
- [ ] Is there a plan for handling documents inserted/deleted/updated between pages?
- [ ] If using keyset, does the API bind and validate cursors against filter/sort/tenant?
- [ ] Were both initial and deep pages benchmarked on sufficiently large data rather than just the lab set?

## 29. Conclusion

`$sort`, `$limit`, and `$skip` are three fundamental stages that directly govern **list correctness and pagination scalability**. `$sort` establishes order, `$skip` discards leading elements in that order, and `$limit` caps the output count. Returning "page N" requires deterministic ordering, typically a composite key pairing business fields with a unique ID.

Under heavy workloads, keep in mind that `$sort` can consume substantial memory or require disk spilling, while `$skip` with deep offsets still has to walk through many documents. Combining early `$match`, suitable indexes, top-k optimization, `explain()`, and **keyset pagination** for deep feeds are essential practices. Finally, always ask **"what entity does one document represent at this stage?"** before placing sort/skip/limit—especially when the pipeline uses `$group`, `$unwind`, or computed fields.