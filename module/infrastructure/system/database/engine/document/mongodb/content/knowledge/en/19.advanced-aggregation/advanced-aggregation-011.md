# Pipeline Limits, Document Size, and Disk Spill in MongoDB

## 1. Why can an aggregation run out of memory even when returning only a few rows?

The aggregation pipeline is MongoDB's powerful data processing engine. A pipeline can filter, compute, group, join, sort, generate reports, paginate, and write aggregated data. However, on large datasets, the question is not only **whether the pipeline produces the right result**, but also:

- How many stages are in the pipeline?
- Does each output document exceed the BSON limit?
- Which stages need to hold large amounts of data in RAM rather than streaming documents one by one?
- If a stage needs more than its memory budget, will MongoDB fail or **spill** temporary data to disk?
- Which limits does `allowDiskUse: true` solve, and which limits does it **not** solve?
- How do `$facet`, `$group`, `$push`, `$sort`, and `$lookup` differ in their risks?
- How can you avoid a pipeline that is slow, consumes excessive disk space, or puts pressure on the entire cluster?

This lesson belongs to the **Advanced Aggregation** chapter of the **MongoDB Document Database Engine** module. It focuses on **pipeline limits, document size, and disk spill**.

After completing this lesson, you will be able to:

1. Distinguish the **16 MiB per-BSON-document** limit, the **1,000-stage** limit, and the **100 MB** budget commonly applied to memory-intensive aggregation stages.
2. Explain why a cursor returning millions of documents does not mean a single document is allowed to exceed 16 MiB.
3. Use `allowDiskUse` for stages that support spilling temporary data to disk, while understanding `allowDiskUseByDefault` introduced in MongoDB 6.0.
4. Identify the special limits of `$facet` and `$push`: cases that can fail **even when disk spill is enabled**.
5. Design `$match`, `$sort`, `$limit`, `$group`, and `$project` to minimize the data held in RAM.
6. Read `explain("executionStats")`, the `usedDisk` indicator in profiler/diagnostic logs, and spill metrics when provided by the server version.
7. Write `mongosh` and Java Driver pipelines with safe timeout, memory, and output configurations.

**General rule:** `allowDiskUse` is an out-of-memory handling mechanism for **certain supported stages**, not a switch that removes all MongoDB limits. In particular, it does not make an output BSON document larger than 16 MiB valid, and it does not make `$facet` spill to disk automatically.

## 2. Map of limits to distinguish

Limits exist at different layers:

| Scope | Common limit/rule | Meaning |
|---|---|---|
| **A single returned or stored BSON document** | **16 MiB** | An individual document cannot exceed the maximum BSON size |
| **An aggregation pipeline** | **1,000 stages** | Exceeding the stage count before or after parsing/canonicalization may be rejected |
| **Memory-intensive stage** | **100 MB** threshold for stages covered by the memory-limit/spill mechanism | Supported stages can spill to disk if allowed; otherwise they may fail |
| **`$facet`** | Document constructed by the stage capped at **100 MB**, **no spill** | Enabling `allowDiskUse` does not overcome this limit |
| **Final `$facet` output** | Still subject to the **16 MiB/document** limit | A facet may stay within its stage memory threshold yet fail when returning an oversized result |
| **`$push` accumulator** | Has its own accumulator memory limit, defaulting to ~**100 MB**, **no spill** | Accumulating an entire list into one array can fail even with `allowDiskUse:true` |
| **Entire query operation** | Starting in **MongoDB 9.0**, an overall operation memory limit also applies | Check the specific server version and configuration parameters |
| **Temporary disk space, time, I/O** | Depends on deployment/operational limits | Can run out of disk or time out even when a stage supports spill |

**Version note:** MongoDB may change operational parameters across releases. The sections below describe the common mechanisms and highlight key version milestones. When deploying on a real cluster, always verify against your MongoDB Server version, driver, Atlas tier, and configured parameters.

### 2.1. How does MiB differ from MB?

- `1 MiB = 1,048,576 bytes`.
- `16 MiB = 16,777,216 bytes`.
- MongoDB documentation often refers to the stage memory threshold as **100 megabytes**, whereas BSON size is explicitly specified as **16 mebibytes (MiB)**.

Do not assume 16,000,000 bytes is 16 MiB, or collapse all limits into a single unit without checking the source definition.

### 2.2. Data flow

~~~text
Documents stored on disk
        |
        |  Each valid BSON document <= 16 MiB
        v
Aggregation pipeline
        |
        +--> $match / $project / $set: typically transform/filter document by document
        |
        +--> $sort / $group: may need to retain large amounts of data in RAM
        |            |
        |            +--> Stage supports spill + disk use allowed?
        |                      |
        |                  Yes: temporary data goes to disk
        |                  No: may hit memory limit error
        |
        +--> $facet: dedicated limit, no spill
        |
        v
Cursor or write stage
        |
        |  Each result document still <= 16 MiB
        v
Client or target collection
~~~

A pipeline can process **vast numbers of documents**. The 16 MiB BSON threshold applies to **each individual document** in the result, not the total bytes of all documents streamed through a cursor.

## 3. Preparing the practice dataset

The examples use `mongosh` on a dedicated database. Do not run sample-data generation commands in a production collection.

~~~javascript
use aggregation_limits_lab
~~~

Create 24 simulated order documents:

~~~javascript
const sampleOrders = [];

for (let i = 1; i <= 24; i++) {
  const id = "ord-" + String(i).padStart(3, "0");

  const status =
    i % 3 === 0 ? "PAID" :
    i % 3 === 1 ? "NEW" :
    "SHIPPED";

  sampleOrders.push({
    _id: id,
    tenantId: i <= 18 ? "tenant-A" : "tenant-B",
    status: status,
    category: ["book", "pen", "bag"][i % 3],
    amount: NumberDecimal(String(i * 10) + ".00"),
    createdAt: new Date(Date.UTC(2026, 9, i + 1, 8, 0, 0)),
    items: [
      {
        sku: "SKU-" + String(i).padStart(3, "0"),
        qty: NumberInt(2),
        price: NumberDecimal("5.00")
      },
      {
        sku: "PEN-001",
        qty: NumberInt(1),
        price: NumberDecimal("2.00")
      }
    ],
    note: "Sample data for aggregation limits"
  });
}

sampleOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

On a new empty collection, the result is **24**. Because `replaceOne(..., {upsert:true})` is used, re-running resets the 24 sample documents with IDs from `ord-001` through `ord-024`; any other documents previously inserted will **not** be automatically deleted.

In this dataset:

- Tenant-A has **18** orders, and tenant-B has **6** orders.
- Tenant-A has **6** orders each in statuses `NEW`, `SHIPPED`, and `PAID`.
- Tenant-B has **2** orders per status.
- Each order has two `items` entries, stored as an array of objects.
- `amount` is stored as `Decimal128`.
- `createdAt` increases with the ID, making it convenient for sort and limit examples.

Create an index used in multiple comparisons:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_status_date_id"
  }
);
~~~

Inspect documents and counts:

~~~javascript
db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1 }
).sort({ _id: 1 });

db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
}); // 6 when only sample data is present
~~~

**Why the sample dataset is small:** The pipelines in this lesson are designed to illustrate structure and mechanics. They **do not intentionally generate hundreds of megabytes of data or fill up the disk** just to force server errors. On a 24-document dataset, `allowDiskUse:true` normally will not create spill files, and that is expected.

## 4. The 16 MiB limit applies to each BSON document

### 4.1. Each result document must fit within the limit

MongoDB caps a standard BSON document at a maximum of **16 MiB**. In aggregation, a command can return a cursor with thousands of documents; every document in that result must satisfy this limit.

Example returning multiple small documents:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1
    }
  }
]);
~~~

There are 18 documents if only sample data is present. Total cursor data can exceed 16 MiB in real workloads as long as **no individual document** exceeds the limit and other resources remain sufficient.

### 4.2. Do not confuse 16 MiB with total pipeline result size

Incorrect:

> "An aggregation can only return at most 16 MiB of data in total."

More accurate:

> "Each returned or written document must comply with the 16 MiB BSON limit. A cursor can return many documents across batches."

Cursor batches have their own data-transfer limits, and the server/driver manage batched delivery. That is no reason to pack every record into one giant array inside **a single document**.

### 4.3. An intermediate document may exceed 16 MiB

According to MongoDB's aggregation limits, the BSON limit for documents **in the result set** does not mean every intermediate document at every stage must stay under 16 MiB. Some pipelines may construct larger intermediate documents before shrinking them.

However:

- The final result must still satisfy 16 MiB/document.
- Individual stages such as `$facet` and accumulators may enforce independent limits.
- Allowing intermediate documents to occasionally grow larger does **not** guarantee that every other transformation accepts unbounded size.
- You should never design a pipeline that relies on accumulating massive intermediate data and "hoping the final stage shrinks it in time."

### 4.4. Measuring BSON size with $bsonSize

MongoDB provides the `$bsonSize` aggregation expression to compute the byte size of a BSON document/object.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 5 }
]);
~~~

`$$ROOT` is the current document in the stage; `$bsonSize` returns the BSON byte size of that object.

You can add converted units:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: {
        $bsonSize: "$$ROOT"
      },
      bsonMiB: {
        $divide: [
          { $bsonSize: "$$ROOT" },
          1048576
        ]
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 3 }
]);
~~~

In practice, `$bsonSize` is helpful for spotting records with abnormally large arrays or deeply nested objects before rolling out an aggregation pipeline.

### 4.5. Count the target document size, not just payload fields

BSON includes field names, type metadata, values, terminators, and related encoding overhead. A 15 MiB payload string does not mean the entire BSON document is exactly 15 MiB; the full BSON structure must be counted.

If a document tends to grow unboundedly because it embeds too many historical items, revisit the data model instead of trying to raise `allowDiskUse` to bypass the BSON limit.

## 5. Risks of $group and $push producing a huge document

### 5.1. $group produces one summary record per group

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

With 24 documents, each status has 8 orders. The result is three small documents, each holding the group key, count, and total amount.

`$group` must maintain accumulator state for groups. When the number of groups is very large or accumulators hold substantial data, memory usage can rise significantly.

### 5.2. $push: "$$ROOT" can create a massive output

Dangerous pattern on large collections:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      allOrders: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Each group contains an array holding entire order documents. If a tenant has millions of orders, a single document can become enormous.

This introduces at least **two risk categories**:

1. The `$push` accumulator memory has its own limit and cannot rely on disk spill to resolve it completely.
2. The resulting document can exceed **16 MiB**, even after grouping logic completes.

`allowDiskUse:true` does not make a BSON document exceeding 16 MiB valid.

### 5.3. Replace full-document $push with numeric aggregates

If the goal is reporting order counts and revenue:

~~~javascript
db.orders.aggregate([
  {
    $match: { tenantId: "tenant-A" }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

If a list of representative IDs is needed, consider `$first`/`$top` or a dedicated paginated fetch per contract rather than pushing full documents into an array.

### 5.4. Dedicated limit of $push

MongoDB documentation states that the `$push` accumulator has its own memory limit; it **does not write accumulator data to temporary files** merely because `allowDiskUse` is enabled. By default, the internal parameter `internalQueryMaxPushBytes` is typically 104,857,600 bytes (approximately 100 MiB).

Do not arbitrarily alter server parameters to "fix" a design that packs unbounded documents into a single array. Instead, partition groups, cap results, store items in separate documents, and read via pagination.

## 6. Stage count limit in a pipeline

MongoDB enforces a limit of **1,000 aggregation stages in a single pipeline**. If the stage count exceeds this threshold before or after parsing/canonicalization, the server may return an error.

A reasonable pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $set: {
      isPaid: { $eq: ["$status", "PAID"] }
    }
  },
  {
    $group: {
      _id: "$isPaid",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

There are four clear stages here. A pipeline built by a generator with thousands of small repeated stages can hit the limit even when the input has only a few documents.

### 6.1. Case where a generator produces repeated stages

The following example **is designed to trigger the stage-count error**; run it only on the practice database if you want to observe it:

~~~javascript
const tooManyStages = Array.from(
  { length: 1001 },
  () => ({ $set: { touched: true } })
);

try {
  db.orders.aggregate(tooManyStages).toArray();
} catch (e) {
  print("Pipeline exceeded stage limit: " + e.message);
}
~~~

MongoDB may report the stage-limit error during parsing, before processing documents. Exact wording varies by version.

**Do not try to optimize by raising this limit:** simplify the formula, combine semantically related calculations into appropriate stages, and eliminate unnecessary intermediate steps.

### 6.2. $set multiple fields instead of hundreds of trivial stages

Instead of:

~~~javascript
db.orders.aggregate([
  { $set: { statusText: "$status" } },
  { $set: { tenantText: "$tenantId" } },
  { $set: { amountText: { $toString: "$amount" } } }
]);
~~~

you can write:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      statusText: "$status",
      tenantText: "$tenantId",
      amountText: {
        $toString: "$amount"
      }
    }
  }
]);
~~~

This reduces the stage count and improves readability **when expressions do not depend on fields newly created in the same stage**. When a later field must read the output of an earlier computed field, keep stages separated according to dependencies.

### 6.3. Do not count only lines in application code

A stage like `$facet` contains multiple sub-pipelines. Stages transformed by a generator, driver, or optimizer can also make the total stage count differ from what a developer sees by merely glancing at a simple top-level list.

Avoid designing close to the 1,000-stage threshold; inspect the actual pipeline emitted by your application, especially pipelines dynamically built from many filters.

## 7. Why do some stages require large amounts of RAM?

Some stages can process documents in a streaming fashion: take one document, then emit the corresponding result or discard it.

Examples:

~~~javascript
{ $match: { status: "PAID" } }
{ $project: { _id: 1, amount: 1 } }
{ $set: { doubleAmount: { $multiply: ["$amount", 2] } } }
~~~

Many operations of this kind do not need to hold all input documents in RAM simultaneously.

Conversely, **blocking stages** may need to collect many documents before producing complete output:

~~~text
Input documents
    |
    v
  $sort              May need to hold many records/keys to determine order
    |
    v
  $group             May need to maintain state for a huge number of groups
    |
    v
  $setWindowFields   May need buffers/partitions for window calculations
    |
    v
  Output
~~~

Without an index or suitable optimization, `$sort` over large datasets can create memory pressure. The same applies to `$group` with high group cardinality or complex accumulators.

Examples of stages that can spill when allowed include:

- `$sort` when not satisfied by an index.
- `$group`.
- `$bucket` and `$bucketAuto`.
- `$sortByCount`.
- `$setWindowFields`.

Exact support and limits depend on the MongoDB version. Do not assume that **every stage** automatically spills when `allowDiskUse` is enabled.

## 8. The 100 MB threshold and allowDiskUse

### 8.1. What is spill to disk?

When a spill-capable stage needs more memory than the applicable budget, MongoDB can write part of its intermediate state to temporary files on disk and read it back when needed.

~~~text
                 Blocking stage
                       |
                Enough RAM or not?
                     /   \
                   Yes    No
                   |       |
                   v       v
             Process RAM   Spill allowed?
                              /   \
                            Yes    No
                            |       |
                            v       v
                     Temp files   Memory limit error
                       on disk
                            |
                            v
                         Continue
~~~

**Spilling does not make the operation free.** It shifts part of the pressure from RAM to disk I/O and storage capacity. A query that no longer throws a memory error can become much slower and create disk pressure.

### 8.2. allowDiskUse is a per-operation option

Example:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$status",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    },
    { $sort: { totalAmount: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

`allowDiskUse:true` permits supported stages to spill data to temporary files under necessary conditions. It does not instruct the server to always create temporary files on every run.

With 18 tenant-A documents, there is no reason to expect a spill event merely from enabling this option.

### 8.3. allowDiskUse: false

~~~javascript
db.orders.aggregate(
  [
    { $sort: { amount: -1 } }
  ],
  {
    allowDiskUse: false
  }
);
~~~

This option forbids disk spill for the operation, even when the server default allows it. On small datasets, the command still succeeds; on large workloads exceeding a stage's memory budget, it can fail.

How to interpret it:

| Option | Expected behavior |
|---|---|
| `allowDiskUse: true` | Allows supported stages to use temporary files when needed |
| `allowDiskUse: false` | Forbids stage spilling; may error when memory runs out |
| Unspecified | Depends on server version and `allowDiskUseByDefault`/environment configuration |

### 8.4. Does not change the 16 MiB BSON limit

Even when running:

~~~javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: null,
        allOrders: { $push: "$$ROOT" }
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

it can still fail on a sufficiently large dataset because the accumulator grows too large or **a single output document** exceeds 16 MiB BSON. Allowing spill does not alter the maximum size of a returned document.

### 8.5. Not every error calls for enabling allowDiskUse

Different failures require different remedies:

- BSON result too large → change the output shape, don't just enable spill.
- `$facet` memory limit → reduce data in facet branches, don't just enable spill.
- `$push` accumulator limit → avoid holding entire records in an array.
- Over 1,000 stages → simplify the pipeline.
- Schema/type/regex error → fix the data or expression.
- Out of disk space → reduce workload/spill and address storage.
- Timeout → optimize the query, bound the work, and evaluate SLA.

## 9. allowDiskUseByDefault since MongoDB 6.0

Starting in MongoDB **6.0**, the `allowDiskUseByDefault` server parameter determines the default behavior of stages covered by standard memory/spill limits.

### 9.1. When allowDiskUseByDefault = true

- Supported stages can use temporary files if they exceed the memory threshold requiring spill.
- A specific command can specify `{allowDiskUse:false}` to prohibit temporary disk usage for that command.

### 9.2. When allowDiskUseByDefault = false

- Stages that exceed the threshold without spill permission may return an error.
- A specific command can specify `{allowDiskUse:true}` to permit disk spill.

Therefore, do not hardcode in application documentation that "MongoDB 6.0 and later always spill by default" without checking the actual configuration.

### 9.3. Inspecting the parameter with administrative privileges

In a self-managed environment where you have appropriate privileges, you can query the server parameter:

~~~javascript
db.adminCommand({
  getParameter: 1,
  allowDiskUseByDefault: 1
});
~~~

On managed services, certain parameters may not be directly readable or modifiable. If denied, coordinate with a DBA or check provider-supported configurations.

**You do not need to change server parameters to follow this lesson.** For each pipeline with clear requirements, setting `allowDiskUse` at the command level usually makes intent more explicit.

### 9.4. Versions prior to MongoDB 6.0

In older versions, permitting disk spill generally required specifying `allowDiskUse:true` when executing the command. When writing documentation or code across multiple versions, verify the capabilities of the deployed server rather than assuming newer defaults apply everywhere.

## 10. MongoDB 9.0: operation-wide memory limit

In addition to per-stage memory limits, MongoDB documentation for **9.0 and later** describes an **overall memory limit for a query operation**. This limit aggregates consumption across tracked components within the same operation.

Under the documented default configuration, the total budget is **the greater of 1 GiB and 20% of available memory for the server process**, as determined by that version's mechanism. Adjustments can be made through server parameters and settings permitted in the corresponding environment.

What this means:

- An operation with multiple memory-intensive stages can hit the total limit even if no single stage stands out individually.
- The overall limit **does not replace** per-stage memory-limit and spill mechanisms.
- Certain memory-heavy expressions also have their own dedicated limits.
- Behavior upon exceeding the limit depends on the workload type and the spill capability of its components.

**Compatibility note:** If a cluster runs MongoDB 7.x or 8.x, do not assume the 9.0 operation-wide parameter/limit exists there. In multi-version environments, always consult documentation for the exact major version.

For the 24-document practice exercise, no server memory parameters need to be modified.

## 11. $sort as a classic blocking stage

### 11.1. Sorting all documents without a matching index

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } }
]);
~~~

If MongoDB lacks an index serving the `amount` ordering, the server must sort the data itself. On large collections, the sort step may hold large amounts of data in RAM or spill to disk if permitted.

The bottleneck is not how many final documents are returned, but having to establish the ordering across the input set.

### 11.2. Adding $limit to take only top N

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 }
]);
~~~

When `$sort` precedes `$limit` with no intervening stage changing the document count, the MongoDB optimizer can coalesce `$limit` into `$sort` and retain only the needed **top N** results.

This reduces memory compared to sorting to return the entire set. If those N documents themselves are huge, memory/spill can still be an issue.

### 11.3. Match before sort

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 }
]);
~~~

`$match` narrows the set from 24 down to 18 documents in the sample dataset. In large workloads, filtering early on indexed conditions can shrink the sort scope substantially.

The `{tenantId:1,status:1,createdAt:-1,_id:-1}` index created during setup can optimize queries filtering on both `tenantId` and `status`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

With the sample data, the result is `ord-018` and `ord-015`.

### 11.4. Index sort vs. in-memory sort

MongoDB can leverage an index for `$sort` when the stage appears in an appropriate position, especially as the first stage or preceded by `$match` without transforming sort keys.

Example:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

When an index serves both the filter and sort, the server can avoid a large blocking sort stage.

Conversely, if you compute a new key and then sort:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      doubledAmount: {
        $multiply: ["$amount", 2]
      }
    }
  },
  { $sort: { doubledAmount: -1 } }
]);
~~~

the key `doubledAmount` is not an indexed field on the collection. This sort must sort intermediate computed data.

### 11.5. $sort is not guaranteed stable on duplicate keys

If multiple documents share the same `amount` value, their relative order is not necessarily stable. When paginating:

~~~javascript
{ $sort: { amount: -1, _id: 1 } }
~~~

the secondary key `_id` ensures deterministic ordering. Pagination stability is a separate concern from memory; a supporting index should also reflect the actual sort order.

## 12. $group: maintaining state for many groups

### 12.1. Grouping by status

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

With the tenant-A sample data, each status has `count:6`. The total amount depends on the IDs belonging to each group.

### 12.2. Group count can be huge

If grouping by a very high-cardinality field, such as `userId` across millions of users:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: "$userId",
      eventCount: { $sum: 1 }
    }
  }
], { allowDiskUse: true });
~~~

`$group` may need to maintain vast numbers of groups. `allowDiskUse:true` can help if the stage qualifies for supported spilling, but it does not reduce memory usage to zero.

The `db.events` example only illustrates an external workload outside the practice collection; you do not need to run it without an `events` collection.

### 12.3. Avoid putting entire documents into a group

When you write:

~~~javascript
{
  $group: {
    _id: "$tenantId",
    documents: { $push: "$$ROOT" }
  }
}
~~~

you build a large array containing complete documents. If the application only needs statistics, use `$sum`, `$avg`, `$min`, `$max`, or top/bottom expressions appropriate for your server version.

If you need every document for a tenant, use a cursor with filters, sorting, and pagination rather than packing everything into a single BSON result.

### 12.4. $sortByCount also consumes resources

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sortByCount: "$status" }
], { allowDiskUse: true });
~~~

`$sortByCount` aggregates occurrence counts and then sorts the results. It can experience memory/spill pressure on datasets with high group cardinality, even though the final output only contains each group and its count.

### 12.5. $bucket and $bucketAuto

Range-based grouping operations:

~~~javascript
db.orders.aggregate([
  {
    $bucket: {
      groupBy: "$amount",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("200"),
        NumberDecimal("1000")
      ],
      default: "other",
      output: {
        count: { $sum: 1 }
      }
    }
  }
], { allowDiskUse: true });
~~~

`$bucket`/`$bucketAuto` may also require significant intermediate state. Design bucket counts and accumulators carefully, and avoid retaining whole documents if only counts are needed.

## 13. $setWindowFields and partition memory

Window functions can compute running totals, moving averages, row numbers, and partition-level statistics.

Example running amount total per tenant:

~~~javascript
db.orders.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: {
        createdAt: 1,
        _id: 1
      },
      output: {
        runningAmount: {
          $sum: "$amount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      amount: 1,
      runningAmount: 1
    }
  }
], { allowDiskUse: true });
~~~

This stage may need to sort/buffer data by partition and window. Across many large partitions or wide windows, memory usage and temporary spill files can grow substantially.

Key considerations:

- Filter the dataset early by tenant or time range if business logic allows.
- An index matching `partitionBy` and `sortBy` can help, though the actual execution plan should always be checked.
- An `unbounded` window should not be used blindly when the application only needs a window of a few records.
- `allowDiskUse` can help supported stages spill, but it does not change the BSON limit on output documents.

## 14. $facet: a special limit not solved by allowDiskUse

`$facet` runs multiple sub-pipelines over the same input document stream and combines their outputs into a single document containing multiple arrays.

Example:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $facet: {
      statusCounts: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        },
        { $sort: { _id: 1 } }
      ],
      latestOrders: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            status: 1,
            createdAt: 1
          }
        }
      ]
    }
  }
]);
~~~

The result has this structure:

~~~javascript
[
  {
    statusCounts: [
      { _id: "NEW", count: 6 },
      { _id: "PAID", count: 6 },
      { _id: "SHIPPED", count: 6 }
    ],
    latestOrders: [
      { _id: "ord-018", /* ... */ },
      { _id: "ord-017", /* ... */ },
      { _id: "ord-016", /* ... */ }
    ]
  }
]
~~~

### 14.1. Memory limit of $facet

According to MongoDB documentation, the document constructed by `$facet` is capped at **100 MB** during stage processing; **`$facet` cannot spill to disk**. `allowDiskUse:true` does not increase that 100 MB limit.

If arrays generated by facet branches grow too large, MongoDB can return an `ExceededMemoryLimit` error.

### 14.2. The 16 MiB output limit still applies

Even if the internal document inside `$facet` stays under 100 MB, once it becomes the **final result document**, it must still fit within the **16 MiB BSON** limit.

These are two separate limit layers:

~~~text
$facet builds a document with multiple arrays
             |
             v
        100 MB stage limit
        (no spill)
             |
             v
       16 MiB BSON result limit
             |
             v
        Client receives output
~~~

A facet pipeline can fail because the result document exceeds 16 MiB **before ever reaching 100 MB**, and enabling `allowDiskUse` does not solve it.

### 14.3. Why pagination facets fail easily

Pattern to avoid on large collections:

~~~javascript
db.orders.aggregate([
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

The `data` branch puts **every document** into one array. The array grows with the number of records and can exceed the facet budget or BSON output limit.

A safer approach bounds the `data` branch:

~~~javascript
const filter = { tenantId: "tenant-A" };
const page = 2;
const pageSize = 3;
const offset = (page - 1) * pageSize;

db.orders.aggregate([
  { $match: filter },
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $skip: offset },
        { $limit: pageSize },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  },
  {
    $project: {
      data: 1,
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.total", 0] },
          0
        ]
      }
    }
  }
]);
~~~

In the sample dataset, `total=18` and the `data` branch returns 3 documents for page 2.

### 14.4. A single facet command does not make counting free

Even though `data` only returns 3 documents, `metadata` must still count the entire matching input set. Reducing network round trips does not eliminate the underlying work.

For complex reports, measure facet cost and consider two separate queries, cached counts, or pagination returning only `hasNext` when an exact total is unnecessary.

### 14.5. Not every stage can run inside a facet

Certain stages are forbidden inside `$facet` sub-pipelines, notably write stages such as `$out` and `$merge`. When you need to persist results, structure the aggregation pipeline and write step in compliance with MongoDB rules; you cannot use `$facet` to bypass those stage restrictions.

## 15. $lookup and fan-out: not just a RAM problem

`$lookup` joins documents from another collection into an array. If one order links to a huge number of line items, the resulting array can grow enormous.

Schema example:

~~~javascript
// orders:
{
  _id: "ord-001",
  tenantId: "tenant-A"
}

// orderLines:
{
  _id: "ord-001#01",
  orderId: "ord-001",
  sku: "SKU-001",
  qty: 2
}
~~~

Create small line-item data for practice:

~~~javascript
for (let i = 1; i <= 24; i++) {
  const orderId = "ord-" + String(i).padStart(3, "0");

  for (let j = 1; j <= 3; j++) {
    const lineId = orderId + "#" + String(j).padStart(2, "0");

    db.orderLines.replaceOne(
      { _id: lineId },
      {
        _id: lineId,
        orderId: orderId,
        sku: "LINE-" + String(j),
        qty: NumberInt(j),
        price: NumberDecimal(String(j * 2) + ".00")
      },
      { upsert: true }
    );
  }
}

db.orderLines.createIndex(
  { orderId: 1 },
  { name: "idx_orderLines_orderId" }
);
~~~

On a fresh `orderLines` collection, there are **72** sample line documents (3 lines per order). Re-running updates the sample IDs without removing other records.

### 15.1. Simple join

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      as: "lines"
    }
  },
  {
    $project: {
      _id: 1,
      lines: 1
    }
  }
]);
~~~

In the sample dataset, the output contains only three lines. In a real system, however, if an order has millions of lines, `lines` can push the joined document past the BSON limit or consume massive resources.

### 15.2. Limit joined data to what is needed

If only a 3-line preview is needed:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $sort: { _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            sku: 1,
            qty: 1
          }
        }
      ],
      as: "previewLines"
    }
  },
  {
    $project: {
      _id: 1,
      previewLines: 1
    }
  }
]);
~~~

The `$lookup` `pipeline` retrieves only the lines required for the preview. This is **not** the full line set of the order, and the response field should be named and documented accordingly.

### 15.3. When all lines are needed, consider row-shaped results

Instead of stuffing all `lines` into one document, you can fetch line items with a separate query:

~~~javascript
db.orderLines.find({
  orderId: "ord-001"
})
.sort({ _id: 1 })
.limit(20);
~~~

Or design a pipeline using `$unwind` to emit multiple small output documents:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      as: "lines"
    }
  },
  { $unwind: "$lines" },
  {
    $project: {
      _id: 1,
      sku: "$lines.sku",
      qty: "$lines.qty"
    }
  }
]);
~~~

**Caution:** The pipeline above still constructs the `lines` array in `$lookup` before `$unwind` runs. With huge fan-out, it can hit limits **at the lookup step** before unwind ever splits the output. For massive real datasets, query `orderLines` directly by `orderId` or use a streaming/pagination pattern rather than relying on unwind after lookup to avoid every limit.

## 16. $unwind can multiply document counts

Each sample document has 2 elements in the `items` array:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unwind: "$items" },
  { $count: "lineCount" }
]);
~~~

With 18 orders for tenant-A and 2 items per order, the result is:

~~~javascript
[{ lineCount: 36 }]
~~~

`$unwind` generally emits more output documents than it receives, and is not necessarily a blocking stage holding everything in RAM. However, it forces **downstream stages** such as `$sort`, `$group`, or `$facet` to process far more records.

If a document contains an array of 100,000 elements, a single unwind dramatically inflates cardinality. If preceded by a high-fan-out lookup, row counts after unwinding can multiply across relationships.

### 16.1. Filter before unwinding

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" }
    }
  }
]);
~~~

Moving the tenant/status filter earlier reduces how many documents must be unwound and grouped, whenever doing so preserves business semantics.

### 16.2. Do not re-group all data unless necessary

After `$unwind`, a common mistake is grouping everything back into `{$push:"$$ROOT"}`. If you only need quantities or totals, aggregate into numbers rather than rebuilding a huge array.

## 17. Reducing output size with $project and $unset

### 17.1. Return only required fields

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      createdAt: 1
    }
  }
]);
~~~

`$project` defines an **allowlist** of output fields, reducing payload returned to the client and preventing accidental exposure of unneeded fields.

### 17.2. Removing large fields

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unset: ["items", "note"] }
]);
~~~

This transforms only the **pipeline output**. Original data in the collection is not deleted.

### 17.3. Is placing $project early always faster?

Not necessarily. The MongoDB optimizer can often detect which fields downstream stages need and automatically retain only those fields.

If you drop `amount` before a stage that needs to sum `amount`:

~~~javascript
db.orders.aggregate([
  { $project: { status: 1 } },
  {
    $group: {
      _id: "$status",
      total: { $sum: "$amount" }
    }
  }
]);
~~~

then the later stage no longer has the original `amount` data to compute the correct total. Pipeline optimization must therefore respect **inter-stage dependencies**.

Putting `$match` on source fields early, using proper indexes for sort/filter, and projecting only needed fields is generally more useful than a rigid rule to "always put project first."

## 18. allowDiskUse does not guarantee success

Suppose a `$sort` stage is permitted to write temporary files. Risks still remain:

- Insufficient temporary disk space.
- Saturated I/O because multiple queries spill concurrently.
- Execution time exceeding SLA or `maxTimeMS`.
- A **non-spillable** stage hitting its own limit.
- Result document exceeding 16 MiB.
- An accumulator like `$push` building an oversized array.
- Pagination or grouping generating too many intermediate records.
- Sharded clusters needing to merge results across many shards, stressing the merge node.
- On newer server versions, hitting the overall operation memory limit.

In MongoDB Atlas or managed environments, temporary spill files can also pressure storage and trigger cost or auto-scaling changes depending on service configuration.

**Do not turn on `allowDiskUse:true` indiscriminately without monitoring.** Each pipeline should justify why spilling is needed, whether an index can eliminate a large sort, and whether storage/latency overhead is acceptable.

## 19. Observing spill with explain

One way to view an execution plan in `mongosh`:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { totalAmount: -1 } }
], { allowDiskUse: true });
~~~

Explain output depends on MongoDB version, query engine, and optimizer.

Fields and stages to watch:

| Indicator | Meaning |
|---|---|
| `IXSCAN` | Query uses an index scan |
| `COLLSCAN` | Collection scan |
| `SORT` | Execution plan includes a sort step |
| `GROUP` or equivalent representation | Includes a grouping step |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned by a plan/stage |
| `executionTimeMillis` | Execution duration reported by explain |
| `usedDisk` | Disk spill indicator if reported |
| `spills`, `spilledDataStorageSize`, or similar fields | Spill count/volume information when supported by version/stage |

Not every server version or stage prints the exact same fields. If `usedDisk` is absent from explain output, you cannot conclude solely from its absence that no spill occurred; check the appropriate profiler/diagnostic logs and your running version.

### 19.1. Reading differences between indexed and unindexed queries

Example index-supported sort:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]);
~~~

Example sort likely requiring in-memory processing:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sort: { amount: -1 } },
  { $limit: 3 }
]);
~~~

Compare the plans, stages, and documents/keys read. On 24 documents, both are tiny; real performance must be measured on representative data volumes.

### 19.2. Explain is not an absolute benchmark

`executionTimeMillis` in explain can be influenced by caching, data scale, infrastructure, and execution plans. Running `explain` may also carry different overhead from normal query execution.

When evaluating production, monitor:

- API p50/p95/p99 latency.
- Database CPU/RAM and I/O.
- Number of operations spilling to disk.
- Temporary file usage / available storage.
- Document count passing through each stage.
- Query frequency and concurrency level.
- Fan-out growth caused by `$unwind`/`$lookup`.

## 20. usedDisk in the profiler and diagnostic logs

MongoDB can record a **`usedDisk`** flag in the profiler and diagnostic logs when an aggregation stage has to write temporary data to disk due to memory constraints.

This is a key signal to distinguish:

~~~text
Query completed using RAM
           vs.
Query completed after spilling to disk
~~~

Two queries can both return correct results yet differ drastically in latency and system cost.

### 20.1. Do not enable the profiler unilaterally in shared environments

The profiler is an operational tool that adds overhead and records query details. Enabling or raising logging verbosity requires proper privileges and governance procedures.

In exercises, prefer `explain("executionStats")` and only inspect metrics/profiler data authorized by a DBA. Do not alter `profilingLevel` or logging parameters on a shared cluster just to force data collection.

### 20.2. Meaning of usedDisk

`usedDisk:true` indicates that a stage used temporary disk files due to memory constraints as tracked by MongoDB. It does **not** by itself tell you total I/O bytes, exact slowdown duration, or root design cause.

Combine it with explain plans, query shapes, data sizes, indexes, and storage metrics.

## 21. Latency and resource cost of spilling

Relative execution paths:

~~~text
No spill:
Process in RAM → emit results

With spill:
Process in RAM → write temp files → read temp files → merge/sort/group → emit results
~~~

If a stage both scans many documents and writes large temporary files, total latency can become dominated by disk I/O.

Speed and impact depend on:

- Number and size of intermediate records.
- Number of groups in `$group`.
- Sort keys and number of documents to sort.
- Partition/window size.
- Storage throughput and latency.
- Concurrent spilling queries competing for CPU/I/O.
- Server/shard topology and where merging occurs.
- Timeouts and environment quotas/auto-scaling behavior.

You cannot assert that a spilling stage will always be slower by a fixed percentage. Measure with real workloads.

## 22. Adding maxTimeMS to bound execution time

Even a well-indexed query can take too long if the dataset is massive. You can set `maxTimeMS` on the command:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    allowDiskUse: true,
    maxTimeMS: 3000
  }
);
~~~

`maxTimeMS` is an execution time limit enforced by MongoDB under its timing mechanism, **not an optimization that makes queries faster**. If an operation exceeds the limit, it may return a timeout error.

Applications must distinguish between:

- No matching documents.
- Matching documents exist, but aggregation timed out.
- Stage exceeded memory limit.
- Exceeded BSON size limit.
- Permission, network, or storage errors.

Do not turn every timeout error into `count:0` or an empty list, because that converts "no confirmed result" into a false conclusion.

## 23. Does $merge or $out bypass the 16 MiB limit?

An aggregation can write results to a collection via `$merge` or `$out`, but **every written document must still be a valid BSON document**. There is no mechanism to "enable `$merge` to store a 50 MiB document" in a standard collection.

Example producing summary metrics by tenant and status:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      amountTotal: { $sum: "$amount" }
    }
  },
  {
    $merge: {
      into: "orderSummaries",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
], { allowDiskUse: true });
~~~

Each summary document is small and does not embed complete orders. This is a much better design than `$push:"$$ROOT"` creating an enormous record.

**Important:** `$merge` actually **writes data** into the `orderSummaries` collection. Run this example only in your practice database with appropriate permissions. When an application needs a read-only aggregation, never attach a write stage.

### 23.1. Writing many small documents beats one giant document

Instead of:

~~~javascript
{
  _id: "tenant-A",
  allOrders: [
    /* millions of documents */
  ]
}
~~~

design:

~~~javascript
{
  _id: {
    tenantId: "tenant-A",
    status: "PAID"
  },
  orderCount: 6,
  amountTotal: NumberDecimal("...")
}
~~~

A summary holding numeric metrics has a well-bounded size. If individual orders are needed, read from the source collection via cursor and pagination.

## 24. Strategies to redesign a pipeline hitting limits

### 24.1. Step 1: Identify the exact failure

| Symptom | Likely cause |
|---|---|
| BSON object/document too large message | A single document exceeds 16 MiB |
| ExceededMemoryLimit in facet | Document built by `$facet` exceeds stage budget |
| Memory limit with no disk use | Stage needs memory/spill, but disk use is disallowed |
| `$push` accumulator threshold exceeded | Accumulated array too large, cannot spill |
| Too many aggregation pipeline stages | Pipeline exceeds 1,000 stages |
| Query timeout | Work exceeded `maxTimeMS` or another layer's timeout |
| Disk full / insufficient storage | Spill or other workloads exhausted storage |
| `usedDisk:true` with high latency | Query spilled; analyze indexes/cardinality |

**Do not fix by blindly toggling every option.** Identify which limit was hit first, then choose the appropriate remedy.

### 24.2. Step 2: Reduce input volume

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
~~~

An early filter reduces the dataset entering `$group`. However, if business logic requires totals across **all tenants**, never inject a filter just to make the query faster at the expense of wrong results.

### 24.3. Step 3: Shrink individual record size

Pass only necessary fields through the pipeline and bound output:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      createdAt: 1
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 10 }
]);
~~~

In real optimization, examine optimizer/index behavior and avoid dropping fields needed by downstream stages. An overly early projection can discard required data or prevent a plan from using an index sort as intended.

### 24.4. Step 4: Control fan-out

- Be cautious with `$unwind` on very long arrays.
- Join only required fields/records inside `$lookup`.
- Paginate child collections when 1-to-many relationships are large.
- Avoid re-grouping fanned-out results into one massive array.
- Clearly define the counting unit: order, order line, customer, or event.

### 24.5. Step 5: Optimize sorting

- Build indexes matching the filter prefix and sort order.
- Pair `$sort` with `$limit` when only top N is required.
- Avoid sorting on expressions computed from full documents when a stored/indexed key can be used.
- Include a unique tie-breaker for pagination.
- Compare query plans on representative data.

### 24.6. Step 6: Decide whether to permit spilling

Once stages are supported and reasonably optimized, `allowDiskUse:true` can help process memory-heavy workloads.

But accompany it with:

- Monitoring of temporary files, I/O, and latency.
- Time and resource limits.
- Concurrency evaluation during peak hours.
- Checks on disk quotas and autoscaling.
- Assessment of impact on other queries sharing the cluster.

### 24.7. Step 7: Reshape output if BSON limits are exceeded

If `$facet` or `$group` creates documents with huge arrays, better alternatives usually include:

- Returning multiple smaller documents via cursor.
- Separating detail views from summary data.
- Paginating related lists.
- Returning only top N.
- Writing compact aggregates to a summary collection.
- Storing long histories as separate child documents rather than an unbounded array.

## 25. Quick decision table: which limit, which tool?

| Issue | Does `allowDiskUse:true` help directly? | Primary fix |
|---|---|---|
| Large unindexed `$sort` | **Can help** | Proper index, early `$match`, `$limit` top N, spill when needed |
| `$group` with high cardinality | **Can help** | Lower cardinality, compact aggregates, spill if stage supports it |
| `$setWindowFields` over large partitions | **Can help** | Narrow input/window, index, verify spill support |
| `$facet` document exceeds 100 MB | **No** | Cap sub-pipeline/output, split facets |
| `$facet` result exceeds 16 MiB | **No** | Shrink data arrays, paginate, return multiple documents |
| Any single result document exceeds 16 MiB | **No** | Redesign output into multiple smaller documents |
| `$push` accumulator too large | **No**, due to accumulator's dedicated limit | Do not accumulate whole documents into an array |
| Pipeline exceeds 1,000 stages | **No** | Consolidate/simplify stages, fix generator |
| `$lookup` creates a huge array | **Does not solve BSON limit** | Limit joins, split queries, change data model |
| Out of disk due to spill | **No**; can worsen it | Reduce spill, adjust storage/quota |
| Slow query from non-selective scan | Not the root fix | Filter/index, optimize data, inspect explain |
| Query timeout | No guarantee | Reduce work, optimize plan, or use appropriate async/cached design |

## 26. MongoDB Compass: inspecting pipelines and controlling allowDiskUse

MongoDB Compass typically provides an **Aggregations** tab to run pipelines, inspect results, and, depending on version, configure options such as `allowDiskUse`.

Practice workflow:

1. Connect Compass to the MongoDB instance hosting `aggregation_limits_lab`.
2. Open the `orders` collection and select the **Aggregations** tab.
3. Add a `$match` stage:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

4. Add `$group`:

   ~~~json
   {
     "_id":"$status",
     "orderCount":{"$sum":1},
     "totalAmount":{"$sum":"$amount"}
   }
   ~~~

5. Add `$sort` descending by `totalAmount`:

   ~~~json
   {"totalAmount":-1}
   ~~~

6. If your Compass version has an **Options** section, inspect disk usage/`allowDiskUse` settings and toggle them on the small dataset.
7. If **Explain Plan** is available, inspect indexes, scan/sort stages, and metrics shown by the UI.
8. Try the `$facet` pipeline from Section 14, keeping `latestOrders` capped with `$limit:3`.
9. Compare Compass results with `mongosh` to distinguish pipeline effects from execution options.
10. Do not attempt to inflate data to exhaust memory or run administrative commands outside practice scope.

**Do not assume Compass exposes the exact same button across all versions.** If the UI does not let you set full options, use `mongosh`:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    { $sort: { amount: -1 } },
    { $limit: 5 }
  ],
  {
    allowDiskUse: true,
    maxTimeMS: 5000
  }
);
~~~

## 27. Java Driver: configuring allowDiskUse and maxTime

With the MongoDB Java Sync Driver, the aggregate API supports `allowDiskUse` and time limits on `AggregateIterable`.

Example, assuming a connected `MongoDatabase` variable named `database`:

~~~java
import static com.mongodb.client.model.Accumulators.sum;
import static com.mongodb.client.model.Aggregates.group;
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> orders =
    database.getCollection("orders");

List<Bson> pipeline = List.of(
    match(eq("tenantId", "tenant-A")),
    group("$status", sum("orderCount", 1)),
    sort(descending("orderCount"))
);

List<Document> result = orders.aggregate(pipeline)
    .allowDiskUse(true)
    .maxTime(10, TimeUnit.SECONDS)
    .into(new ArrayList<>());

for (Document doc : result) {
    System.out.println(doc.toJson());
}
~~~

`allowDiskUse(true)` enables supported stages to spill. `maxTime` sets a time limit; it does not automatically optimize the query.

### 27.1. Use a streaming cursor instead of loading everything into application RAM

On huge result sets, avoid:

~~~java
// May consume too much application RAM.
List<Document> everything = orders.aggregate(pipeline)
    .allowDiskUse(true)
    .into(new ArrayList<>());
~~~

Instead, iterate the cursor in batches:

~~~java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor = orders.aggregate(pipeline)
        .allowDiskUse(true)
        .batchSize(100)
        .iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        // Process one row in a memory-bounded workflow.
        System.out.println(row.toJson());
    }
}
~~~

Enabling disk spill on MongoDB **does not protect application RAM** if the application still collects every document into an `ArrayList`.

### 27.2. batchSize does not alter the 16 MiB limit

`batchSize(100)` controls the desired number of documents per driver/server batch, not permission to return a BSON document over 16 MiB.

If a single document is too large, lowering `batchSize` will not fix it; you must reshape the document.

### 27.3. Handle errors by category

Applications should handle these cases distinctly:

- Operation exceeded memory limit without spill permission.
- Result document exceeded BSON size limit.
- Timeout.
- Network error or node unavailability.
- Invalid pipeline syntax.
- Insufficient privileges.
- Storage failure.

Do not infinitely retry a pipeline with a deterministic structural error, such as `$facet` producing an oversized array, because retrying the same input will generally hit the same limit again.

## 28. Practice exercises

These exercises use the small dataset from Section 3. If an exercise involves `orderLines`, load the extra data from Section 15 first. You do not need hundreds of megabytes to understand the mechanics.

### Exercise 1. BSON size per document

Run:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 5 }
]);
~~~

**Question:** Why does a 100-byte string field not mean the whole BSON document is exactly 100 bytes?

### Exercise 2. Count orders by status

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** Each status has **8** orders when only the 24 sample documents are present.

### Exercise 3. Count for tenant-A

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** `NEW`, `PAID`, and `SHIPPED` each have `count:6`.

### Exercise 4. Top 5 by amount

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 }
], { allowDiskUse: false });
~~~

**Question:** Why does the command succeed on the sample dataset even with spill disabled? When does a top-N sort help reduce memory?

### Exercise 5. Indexed sort query

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

**Expected data:** `ord-018`, `ord-015`. Observe whether the plan uses an index scan or a collection scan/sort.

### Exercise 6. allowDiskUse true/false

Run the same pipeline:

~~~javascript
const p = [
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
];

db.orders.aggregate(p, { allowDiskUse: false });
db.orders.aggregate(p, { allowDiskUse: true });
~~~

**Question:** Why is the output identical on the sample data? Does enabling spill mean "temporary files were definitely written"?

### Exercise 7. $push and array size

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      ids: { $push: "$_id" }
    }
  }
]);
~~~

With 24 sample documents, the arrays are tiny and the command succeeds.

**Question:** What changes if you replace `ids:{$push:"$_id"}` with `allOrders:{$push:"$$ROOT"}` on a collection with millions of documents?

### Exercise 8. $facet with page data limit

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 3 },
        { $project: { _id: 1, status: 1 } }
      ],
      meta: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

**Expected:** `meta[0].total = 18` and `data` has 3 documents. If `$limit` is removed, what risks increase on a large collection? Why does `allowDiskUse:true` not resolve all limits?

### Exercise 9. $unwind increases document count

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unwind: "$items" },
  { $count: "lineCount" }
]);
~~~

**Expected:** `lineCount:36`, not 18. Explain the impact on a `$group` or `$sort` placed after `$unwind`.

### Exercise 10. $lookup and BSON limits

After loading `orderLines`, run the join for `ord-001`. Observe that `lines` contains three elements.

**Question:** If an order had millions of lines, why would outputting a single document with all lines become invalid? When should you switch to paginated queries on the child collection?

### Exercise 11. Identify the error from description

Choose the primary solution:

| Scenario | Primary fix |
|---|---|
| A returned document exceeds 16 MiB | Return multiple small documents, paginate, or trim fields |
| Large unindexed sort hits memory limit | Index/filter/top N, plus spill if supported by stage |
| Facet data array is too large | `$limit` inside branch, split queries, or reshape output |
| `$push` accumulates millions of documents | Do not `$push:"$$ROOT"`; use counts/summaries or separate queries |
| Pipeline has over 1,000 stages | Simplify generator/pipeline |
| Disk spill nearly fills storage | Reduce spill, optimize query, and manage storage |
| Query exhausted `maxTimeMS` | Reduce workload; do not turn timeouts into empty results |

### Exercise 12. Redesigning a large report

Initial requirement: produce one document containing every order of every tenant:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      allOrders: { $push: "$$ROOT" }
    }
  }
]);
~~~

**Task:** Propose two endpoints:

1. **summary** endpoint: order counts and total amounts by tenant/status.
2. **detail** endpoint: paginated list of orders per tenant with filtering and sorting.

Explain why the redesigned approach avoids cramming all orders into one BSON document and makes latency easier to control.

### Exercise 13. Stage limit

Suppose a pipeline generator repeatedly appends 1,100 `$set` stages to construct the same field. What risk does that pose? Should you enable `allowDiskUse` or adjust memory thresholds to fix it?

*Hint:* This is a **stage-count** limit, not a RAM limit. Fix the generator and combine expressions where possible.

### Exercise 14. Reading usedDisk signals

A query exhibits:

~~~text
usedDisk: true
executionTimeMillis spiked sharply
totalDocsExamined is very large
~~~

In what order should you investigate?

*Hint:* Check filters/indexes, sort/group steps, document counts flowing through stages, memory/stats, I/O, and concurrency; do not just enable more disk usage.

### Exercise 15. Version-dependent limits

On a project spanning multiple MongoDB Server versions:

- Check which version introduced `allowDiskUseByDefault`.
- Identify which version documents the overall query operation memory limit.
- Explain why the exact same pipeline can behave differently depending on configuration even on nearly identical data.
- Explain why you must not assume every stage, especially `$facet`, can spill.

## 29. Common errors and misconceptions

| Misconception / symptom | Accurate explanation |
|---|---|
| "Aggregation only returns up to 16 MiB total" | The 16 MiB limit applies **per result document**; a cursor can return many documents |
| "Enabling allowDiskUse makes a 40 MiB document valid" | No, BSON results are still capped at 16 MiB |
| "Every stage can spill to disk" | Only supported stages/mechanisms can spill; `$facet` does not spill |
| "Facet gets 100 MB so the result can be 100 MB" | The final result must still satisfy the 16 MiB BSON limit |
| "$push always spills like $group" | `$push` has its own non-spilling accumulator memory limit |
| "100 MB is the absolute total RAM cap for any aggregation" | Limits apply per stage; newer versions also enforce a separate operation-wide limit |
| "MongoDB 6.0 always spills by default" | Behavior depends on `allowDiskUseByDefault` and command-level overrides |
| "Spilling means the query failed" | Spilling can help a query succeed, though it increases I/O and latency |
| "No usedDisk in explain means definitely no spill" | Output fields vary by version/stage; inspect the right observability sources |
| "A 1,100-stage pipeline will run if RAM is large" | Exceeds the 1,000-stage limit, which cannot be solved with RAM |
| "$sort + $limit still buffers every record" | The optimizer can retain only top N when optimization conditions are met |
| "$project at the start is always faster" | The optimizer and stage dependencies apply; always measure and preserve correctness |
| "$lookup followed by $unwind always avoids oversized docs" | `$lookup` can still build an oversized array before `$unwind` runs |
| "Any index works for sorting" | The index must match the filter/sort pattern, order, and collation |
| "Return count=0 on timeout" | A timeout means no confirmed result, not zero |
| "allowDiskUse protects Java application RAM" | No; if the client loads every result into a `List`, client RAM still grows |
| "A pipeline with small output uses little RAM" | Blocking stages may process huge intermediate volumes before emitting small output |

## 30. Production deployment checklist

Before shipping a heavy aggregation pipeline to production, align on:

1. **Input scale:** How big can the dataset get, how many documents, and how long can arrays grow?
2. **Output goal:** Do you need a compact summary, one page of results, or full detailed rows?
3. **BSON limit:** Is there any risk a result document contains an oversized array?
4. **Stage count:** Could a generated pipeline exceed 1,000 stages?
5. **Blocking stages:** Are there large `$sort`, `$group`, `$bucket`, `$setWindowFields`, or `$facet` stages?
6. **Indexes:** Do filters and sorts match index prefixes, ordering, and collation?
7. **Cardinality:** Do `$unwind`/`$lookup` multiply intermediate record counts dramatically?
8. **Allow disk:** Should spilling be explicitly enabled? Do server parameters differ across environments?
9. **Exceptions:** Are `$facet`, `$push`, and 16 MiB output constraints explicitly designed around?
10. **Time budget:** Does the query have `maxTimeMS`/SLA and clear timeout handling?
11. **Monitoring:** Are `usedDisk`, spills, scan metrics, CPU/RAM/I/O, and p95/p99 latency tracked?
12. **Resources:** Does the cluster have adequate temp storage, autoscaling headroom, and concurrency protection?
13. **Application layer:** Does the driver stream the cursor in batches instead of loading all documents into RAM?
14. **Access control:** Does the pipeline filter properly by tenant/scope and avoid leaking sensitive fields?
15. **Compatibility:** Have the MongoDB major version and corresponding memory parameters been verified?

## 31. Conclusion

There are three easily confused limit groups in MongoDB Aggregation:

- **Per-document size:** every returned or stored result document must stay within the **16 MiB** BSON limit.
- **Pipeline structure:** a pipeline can have at most **1,000 stages** under server limits.
- **Runtime resources:** blocking stages can demand heavy RAM, and certain stages support spilling when permitted by `allowDiskUse`; meanwhile `$facet`, `$push`, and other constraints do not disappear on their own.

The most important practical takeaway is to **design your data and pipelines so you never accumulate unbounded documents into a single array**. Leverage early `$match` filters, sort-supporting indexes, `$limit` for top-N queries, compact group accumulators, paginated detail queries, and explain/monitoring checks. Permitting disk spill is a useful operational escape valve when genuinely needed, but it never replaces controlling cardinality, BSON size, stage count, and overall system latency.

## Official Documentation

- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
