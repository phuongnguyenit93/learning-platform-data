# Designing an Index Set from Real Queries and Removing Redundant Indexes in MongoDB

## 1. Goal: Design an Index Set, Not One Index per Field

A single MongoDB collection can serve many access paths: fetching details by order ID, viewing customer order history, listing pending orders, filtering orders by amount, and exporting reports. An index can help one or multiple queries, yet every index also increases disk storage and the cost of inserts, updates, and deletes.

Therefore, the right design question is not "Which fields does this collection have that we can index?", but:

**How are the most critical queries executed, and what is the smallest set of indexes that supports them well enough at an acceptable write cost?**

Suppose an e-commerce application runs these commands:

~~~javascript
// View a customer's order history, newest orders first.
db.orders.find({ tenantId: "t001", customerId: "c001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// View the pending order queue.
db.orders.find({ tenantId: "t001", status: "pending" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// View one order by _id, scoped by tenant.
db.orders.findOne({ _id: "o001", tenantId: "t001" });
~~~

If you create three single-field indexes on **tenantId**, **customerId**, and **status**, plus an index on **createdAt** and one on **_id**, MongoDB may still have to read many documents and sort. Several indexes become redundant once you design **compound indexes** matching your filters and query sort orders.

This lesson walks through a complete workflow:

1. Document **access patterns** and read/write load.
2. Translate each critical query group into **candidate indexes**.
3. Leverage compound index prefixes, field order, and **equality–sort–range** relationships.
4. Identify exact duplicate indexes, potentially redundant prefix indexes, and indexes that must be kept.
5. Inspect **getIndexes**, **explain**, **$indexStats**, and workload metrics.
6. Use **hidden indexes** to evaluate impact before dropping an unneeded index.
7. Drop confirmed redundant indexes with a rollback plan and post-change verification.

Frequency figures in this lesson are **hypothetical design assumptions**. Do not treat them as performance guarantees or measurements from another system.

## 2. Start with Access Patterns

### 2.1. Describe Queries as Contracts

To decide on indexes, record the following for each API or job:

- **Filter:** equality, range, `$in`, `$exists`, arrays, `$elemMatch`, text search, etc.
- **Sort:** which fields, ascending/descending directions, and whether a tie-breaker key prevents unstable ordering.
- **Projection:** which fields are returned? Is there a **covered query** opportunity?
- **Result bounds:** limit, pagination strategy, and returned document count.
- **Frequency:** requests per second, read-heavy vs. write-heavy ratio, peak windows.
- **Selectivity:** what percentage of documents does the filter eliminate?
- **Integrity requirements:** uniqueness, collation, TTL, or partial filter needs.
- **Data scope:** system-wide vs. per-tenant, and retention period.

Example hypothetical workload table for the **orders** collection:

| ID | Need | Primary filter | Sort / output | Illustrative load |
| --- | --- | --- | --- | --- |
| Q1 | Order detail | `_id`, `tenantId` | Single document | 120 reads/sec |
| Q2 | Customer order history | `tenantId =`, `customerId =` | `createdAt DESC`, `_id DESC`, 20 records | 60 reads/sec |
| Q3 | Pending queue | `tenantId =`, `status = pending` | `createdAt DESC`, `_id DESC`, 20 records | 45 reads/sec |
| Q4 | All orders for a tenant | `tenantId =` | `createdAt DESC`, `_id DESC`, 20 records | 15 reads/sec |
| Q5 | Amount range report | `tenantId =`, `total` from A to B | No strict sort, aggregation | 2 reads/sec |
| Q6 | Unique `orderNo` check | `tenantId`, `orderNo` | Single-doc/insert constraint check | Tied to order writes |
| Q7 | Write / status transition | `_id`, old `status` | Single-doc update | 40 writes/sec |

The **=** symbol denotes equality predicates. In practice, measure **p95/p99 latency**, documents scanned, index keys scanned, error rates, write overhead, and index size. A rare query with a strict SLA may still justify a dedicated index; priority is not decided purely by raw call frequency.

### 2.2. Why Not Create One Index per Field?

Suppose Q2 filters by `tenantId`/`customerId` and sorts by `createdAt`:

~~~javascript
{ tenantId: "t001", customerId: "c001" }
// sort: { createdAt: -1, _id: -1 }
~~~

Three single-field indexes:

~~~javascript
{ tenantId: 1 }
{ customerId: 1 }
{ createdAt: -1 }
~~~

are not equivalent to one compound index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

With a compound index, MongoDB can narrow down by equality values and read directly in indexed sort order, reducing the need for a separate sort. MongoDB can use **index intersection** in some cases, yet intersection should not be assumed equal to a compound index tailored to the workload.

## 3. Compound Index Design Principles

### 3.1. Index Prefixes

Suppose you have the index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Its key prefixes are:

~~~text
{ tenantId: 1 }
{ tenantId: 1, customerId: 1 }
{ tenantId: 1, customerId: 1, createdAt: -1 }
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Consequently, one compound index can serve queries using its **leftmost prefixes** without needing separate indexes for those exact prefixes, provided index semantics remain compatible.

For example:

~~~javascript
db.orders.find({ tenantId: "t001" });
db.orders.find({ tenantId: "t001", customerId: "c001" });
~~~

can leverage prefixes of that index. However:

~~~javascript
db.orders.find({ customerId: "c001" });
~~~

cannot use the `tenantId` prefix because the leading field is absent; MongoDB might still scan the index in certain plans, yet it is typically far less efficient than an index starting with `customerId` when that is a primary query.

More importantly, the index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1 }
~~~

**does not guarantee `createdAt` ordering across the entire tenant** if the query filters only by `tenantId` **without** constraining `customerId`. Keys in the index are grouped by `customerId` first, so `createdAt` lacks global order across multiple customers.

### 3.2. The ESR Rule: Equality, Sort, Range

For many queries, a useful starting field order for a compound index is:

1. **E – Equality:** fields filtered by exact values.
2. **S – Sort:** fields determining output order.
3. **R – Range:** range conditions like greater-than or less-than.

Example:

~~~javascript
db.orders.find({
  tenantId: "t001",
  status: "pending",
  createdAt: { $gte: ISODate("2026-02-01T00:00:00.000Z") }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Candidate index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Here `tenantId` and `status` are equality predicates, while `createdAt` serves as both the range predicate and the primary sort key. The index narrows by equality and scans a `createdAt` range in the needed direction.

**ESR is a starting point, not an immutable law.** For queries with ultra-selective ranges, placing range ahead of sort fields (ERS) can sometimes win by slashing candidate documents, even if it incurs a `SORT` stage. Measure latency, `totalKeysExamined`, `totalDocsExamined`, and sorts on real data.

### 3.3. Choosing Appropriate Sort Directions

The index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

after equality filtering on `tenantId`, can support:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

and can scan backward to support:

~~~javascript
.sort({ createdAt: 1, _id: 1 })
~~~

However, sorting by:

~~~javascript
.sort({ createdAt: -1, _id: 1 })
~~~

uses a different relative direction, so it is not natively satisfied by the same index order. When choosing indexes for multi-field sorts, component directions and full reverse scan eligibility both matter.

### 3.4. Do Not Create an Index Just to Avoid a Rare Sort

A monthly report filtering orders by `total`, aggregating by customer, and exporting data has very different needs from a UI screen fetching the 20 latest orders. Creating a separate index for every infrequent sort can cost more than it saves.

When prioritizing indexes, consider:

- How often does this query run, and what is its SLA?
- How many documents does each run read and return?
- Can an existing index serve it at acceptable cost?
- Can heavy reporting move to background jobs, pre-aggregated views, or fixed time windows?
- How does the new index affect every write operation?

## 4. Setting Up a mongosh Lab: One Workload, Multiple Candidate Indexes

We will build an orders collection with fixed data and several **intentionally overlapping** indexes. Then we will inspect `explain` and separate essential indexes from potentially redundant ones.

### 4.1. Dataset

Database: **mongo_index_design_lab**.

Collection: **lab_orders**.

All documents in this lesson have **dataset: "index-design-v1"**.

Run in `mongosh`:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_index_design_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "index-design-v1";

  // Clean up only this lesson's data; never drop the database or collection.
  orders.deleteMany({ dataset: tag });

  const raw = [
    ["o001", "t001", "c001", "pending",   "2026-02-01T08:00:00Z", "250.00"],
    ["o002", "t001", "c001", "paid",      "2026-02-02T09:00:00Z", "100.00"],
    ["o003", "t001", "c002", "pending",   "2026-02-03T10:00:00Z", "300.00"],
    ["o004", "t001", "c001", "shipped",   "2026-02-04T11:00:00Z", "420.00"],
    ["o005", "t001", "c003", "paid",      "2026-02-05T12:00:00Z", "150.00"],
    ["o006", "t001", "c001", "pending",   "2026-02-06T13:00:00Z", "190.00"],
    ["o007", "t001", "c002", "cancelled", "2026-02-07T14:00:00Z", "270.00"],
    ["o008", "t001", "c003", "pending",   "2026-02-08T15:00:00Z", "360.00"],
    ["o009", "t002", "c004", "pending",   "2026-02-09T16:00:00Z", "500.00"],
    ["o010", "t002", "c004", "paid",      "2026-02-10T17:00:00Z", "200.00"],
    ["o011", "t001", "c001", "paid",      "2026-02-11T18:00:00Z", "110.00"],
    ["o012", "t001", "c002", "pending",   "2026-02-12T19:00:00Z", "280.00"]
  ];

  const documents = raw.map(([id, tenantId, customerId, status, date, total]) => ({
    _id: id,
    dataset: tag,
    tenantId: tenantId,
    customerId: customerId,
    status: status,
    orderNo: "SO-" + id.substring(1),
    createdAt: ISODate(date),
    total: NumberDecimal(total),
    items: [
      { sku: "SKU-" + id.substring(1), quantity: NumberInt(1) }
    ]
  }));

  orders.insertMany(documents);

  // Q2: customer order history.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, customerId: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_customer_recent" }
  );

  // Prefix index intentionally overlapping ix_customer_recent.
  orders.createIndex(
    { dataset: 1, tenantId: 1, customerId: 1 },
    { name: "ix_customer_short" }
  );

  // Q3: processing queue by status.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, status: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_queue_recent" }
  );

  // Prefix index intentionally overlapping ix_queue_recent.
  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_queue_short" }
  );

  // Q4: all orders in a tenant chronologically, without filtering customerId/status.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: -1 },
    { name: "ix_tenant_recent" }
  );

  // Q5: filtering by order amount. Serves a different query than history sorting.
  orders.createIndex(
    { dataset: 1, tenantId: 1, total: 1 },
    { name: "ix_tenant_total" }
  );

  // Q6: enforce unique orderNo within each tenant.
  orders.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ux_tenant_order_number", unique: true }
  );

  printjson({
    total: orders.countDocuments({ dataset: tag }),
    tenant001: orders.countDocuments({
      dataset: tag, tenantId: "t001"
    }),
    indexes: orders.getIndexes().map(index => index.name)
  });
})();
~~~

**Expected result:** 12 documents, of which tenant **t001** has 10. The default **_id_** index is already present. **ix_customer_short** and **ix_queue_short** are created **intentionally** to practice spotting prefix overlaps; they are not recommendations to keep in production.

Because the script uses fixed IDs, re-running it resets this lesson's data after lab edits or deletes. It does not drop the database or other indexes; never use it to wipe a production collection.

### 4.2. Inspect Existing Indexes

~~~javascript
const orders = db.getSiblingDB("mongo_index_design_lab")
  .getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

Each returned element typically contains:

- **name:** the index name.
- **key:** field order and key direction.
- **unique**, **partialFilterExpression**, **sparse**, **expireAfterSeconds**, **collation**, or other options when present.
- **hidden:** hidden state on supported versions.

Never inspect only the leading fields of two indexes to declare them duplicates: options like `unique`, `partialFilterExpression`, `sparse`, and `collation` alter **semantics**, not just performance.

## 5. Mapping Real Queries to the Index Set

### 5.1. Q1: Lookup by `_id`

~~~javascript
orders.findOne({
  _id: "o001",
  dataset: "index-design-v1",
  tenantId: "t001"
});
~~~

MongoDB automatically creates the **unique `_id_` index** on standard collections. Looking up by `_id` uses that default index; keeping `tenantId` in the predicate remains necessary for tenant isolation, though it does not require building a custom compound index for every `_id`/`tenantId` query.

Do not create another **{ _id: 1 }** index under a different name just to optimize lookups already served by `_id_`. Keep `_id` types aligned with your application's identity contract: if the lab uses strings, filter with strings; if production uses `ObjectId`, filter with `ObjectId`.

### 5.2. Q2: Customer Order History

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  },
  { _id: 1, orderNo: 1, status: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Expected output:** **o011, o006, o004** in descending chronological order. **ix_customer_recent** matches equality on `dataset`/`tenantId`/`customerId` followed by the sort fields, making it the natural candidate.

The short index **ix_customer_short** shares the first three fields but **lacks `createdAt`/`_id` to preserve ordering**. If the planner picks the short index, an extra sort is needed. Thus, the short index is a **removal candidate** whenever the longer index also serves prefix-only queries well enough.

### 5.3. Q3: Pending Queue

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    status: "pending"
  },
  { _id: 1, customerId: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Expected output:** **o012, o008, o006**.

**ix_queue_recent** serves filtering by `status` followed by sorting. **ix_queue_short** is its prefix and can be removed unless it offers a distinct, measurable benefit.

Do not try to substitute `ix_customer_recent` for `ix_queue_recent` simply because both begin with `dataset`/`tenantId`: after `tenantId`, one orders by `customerId` and the other by `status`. The middle field governs both filtering and sort order.

### 5.4. Q4: List All Orders for a Tenant

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001"
  },
  { _id: 1, createdAt: 1, status: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Expected output:** **o012, o011, o008**.

Why is **ix_tenant_recent** needed even though `ix_customer_recent` and `ix_queue_recent` already exist? Because this query **does not** constrain `customerId` or `status`. In those other two indexes, `createdAt` sits **after** `customerId` or `status`, providing no tenant-wide `createdAt` order. A dedicated **{dataset, tenantId, createdAt, _id}** index serves a distinct purpose rather than being an empty prefix overlap.

### 5.5. Q5: Total Amount Range

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    total: {
      $gte: NumberDecimal("150.00"),
      $lte: NumberDecimal("300.00")
    }
  },
  { _id: 1, total: 1, status: 1 }
).sort({ total: 1 }).toArray();
~~~

**Expected output:** **o005, o006, o001, o007, o012, o003** in ascending `total` order. **ix_tenant_total** puts equality fields first followed by the range/sort key.

If Q5 is rare and the index set is already costly, evaluate whether to skip this dedicated index; the decision depends on data volume and SLAs. There is no automatic rule that every field appearing in a filter must be indexed.

### 5.6. Q6: Uniqueness Is a Constraint, Not Merely an Optimization

~~~javascript
orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { name: "ux_tenant_order_number", unique: true }
);
~~~

This index ensures the `tenantId`/`orderNo` pair cannot repeat **across documents**, subject to MongoDB uniqueness semantics and valid data. The fact that it can also accelerate lookups by `orderNo` does not erase its role as a **business invariant**.

**Never drop a unique index** just because a non-unique index shares its prefix or partial fields. Doing so would allow duplicate `orderNo` values into the collection. In multi-tenant designs, unique indexes must also account for missing/null fields, sharding, and effective uniqueness scope.

## 6. Reading explain to Verify Whether an Index Serves a Query

### 6.1. `executionStats` and Metrics to Inspect

~~~javascript
orders.find({
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
})
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.explain("executionStats");
~~~

Key elements:

| Field / stage | How to interpret |
| --- | --- |
| **winningPlan** | The plan MongoDB chose for the query |
| **IXSCAN** | Scanning entries from an index |
| **indexName** | Specific index being scanned |
| **indexBounds** | Key range scanned for each field |
| **FETCH** | Reading full documents to return fields or verify remaining filters |
| **SORT** | Blocking sort stage rather than relying purely on index order |
| **COLLSCAN** | Collection scan |
| **nReturned** | Number of documents returned |
| **totalKeysExamined** | Number of index keys inspected |
| **totalDocsExamined** | Number of documents inspected |
| **executionTimeMillis** | Execution time reported in explain; does not replace real latency distributions |

**Never conclude an index is good just because you see `IXSCAN`.** If a query returns 20 documents while scanning 200,000 keys and 50,000 documents, investigate why. Conversely, on a 12-document lab, `COLLSCAN` may be cheaper than an index scan; that is not proof of a broken index design.

### 6.2. Comparing Two Candidates with hint in the Lab

~~~javascript
const query = {
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
};
const sorting = { createdAt: -1, _id: -1 };

print("Long index:");
printjson(
  orders.find(query)
    .sort(sorting)
    .limit(3)
    .hint("ix_customer_recent")
    .explain("executionStats")
);

print("Short index:");
printjson(
  orders.find(query)
    .sort(sorting)
    .limit(3)
    .hint("ix_customer_short")
    .explain("executionStats")
);
~~~

Observe the `SORT` stage and differences in `indexBounds`. The long index supplies `createdAt`/`_id` order per customer; the short index filters only the three equality fields and may require a `SORT`. On a tiny lab dataset, absolute timing differences are minuscule.

**`hint` is an experimental tool, not advice to pin indexes in production.** Forcing an index can block the planner from choosing a better plan when data distributions change.

### 6.3. Covered Queries Can Help Reduce FETCH

A query can be resolved from the index when all filtered and projected fields are satisfied without reading source documents, within the index's semantic limits. Example using `ix_customer_recent`:

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  },
  { _id: 0, tenantId: 1, customerId: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.hint("ix_customer_recent")
.explain("executionStats");
~~~

The projection excludes `_id`, while the index ends with `_id` to support the sort. When all necessary conditions hold, MongoDB can avoid `FETCH`. If the projection includes **status**, **total**, or **orderNo**, this index lacks those fields and must read documents.

Do not blindly stuff every display field into an index to chase covered queries: wider indexes consume more storage, RAM, and write overhead. Base the choice on high-impact queries and measured gains.

## 7. Classifying Overlapping and Redundant Indexes

### 7.1. Exact Key Duplicates

Two definitions:

~~~javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1 }
~~~

share the exact same key pattern. MongoDB generally prevents creating two identical indexes merely under different names, subject to options and server version. Hence, in practice the far more common problem is **overlapping / prefix-redundant indexes**, rather than exact key duplicates.

Never judge duplication solely by index names. Identical names across different collections are normal; conversely, different names do not prove two indexes behave differently.

### 7.2. Prefix Overlap: Removal Candidates

In our lab:

~~~javascript
// A: short index.
{ dataset: 1, tenantId: 1, customerId: 1 }

// B: longer index starting with A as its prefix.
{
  dataset: 1, tenantId: 1, customerId: 1,
  createdAt: -1, _id: -1
}
~~~

Index B can serve queries filtering only on the first three fields while also supporting `createdAt`/`_id` sorting. Therefore A is a **redundancy candidate**.

However, **"Index A is a prefix of B" does not automatically mean "it is always safe to drop A."** Check:

- Does Index A have **unique**, **sparse**, **partialFilterExpression**, **collation**, or other special options?
- Is there an ultra-high-frequency query that relies solely on A and benefits materially from a smaller/shorter index?
- Does a write-heavy workload see measurable write-latency improvement from keeping B and dropping A?
- Is there any query relying on A that was missed in your access-pattern inventory?
- How did the planner pick between A and B under representative load?

Often, the shorter index is not worth keeping if the longer index handles its queries adequately. Still, base that verdict on **workload evidence**, not key comparison alone.

### 7.3. Two Indexes Sharing a Prefix Are Not Necessarily Redundant

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 }
~~~

These three indexes serve three distinct patterns:

- Order history **by customer**.
- Order queue **by status**.
- All orders **for a tenant** chronologically.

They share only `tenantId` at the start. You cannot drop the third index arguing "we already have `tenantId` and `createdAt` in the other two indexes," because `customerId`/`status` sit in between and break global `createdAt` order across the tenant.

### 7.4. Reverse Directions Do Not Always Require Another Index

If the index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

already supports descending `createdAt`/`_id` sorts after `tenantId` equality, scanning it in reverse can support ascending sorts on both fields. Do not automatically create a second index:

~~~javascript
{ tenantId: 1, createdAt: 1, _id: 1 }
~~~

just to flip both sort directions; verify reverse scan eligibility with `explain`. However, mixed-direction flips like `createdAt` descending with `_id` ascending are not natively satisfied by the same index.

### 7.5. Indexes That Look Similar but Have Different Semantics

| Difference | Why you must not drop lightly |
| --- | --- |
| **unique** vs. non-unique | Unique enforces key uniqueness constraints |
| **partial index** vs. full index | Partial covers only documents matching its filter; serves a different query scope |
| **sparse** vs. non-sparse | Sparse omits documents missing keys; differs in behavior and query eligibility |
| **different collations** | Comparison, sorting, and case/accent sensitivity differ |
| **TTL** with `expireAfterSeconds` | TTL enforces automatic document expiration, not just fast filtering |
| **text, geospatial, hashed, wildcard** | Possess specialized query semantics and capabilities |
| **hidden** vs. visible | Hidden is skipped by the planner yet still maintained on writes |
| **multikey** on Array fields | Requires checking array bounds, covered query rules, and sort limits |

Never drop an index saying "no query uses it" if that index enforces a **data constraint** or **retention policy**. Those carry value beyond any single query plan.

### 7.6. Index Intersection Is Not a Reason to Keep Everything as Single-Field Indexes

MongoDB can combine multiple indexes to satisfy a query via **index intersection** in certain situations. Even so:

- The planner does not guarantee choosing intersection.
- Intersection does not inherently supply desired sort ordering.
- Merging candidate IDs can cost more than a dedicated compound index.
- Every single-field index still incurs write-maintenance overhead.

If a tenant/status/createdAt query is a hot path, a purpose-built compound index is usually a stronger candidate than three single-field indexes hoping the planner intersects them. Verify with `explain`.

## 8. Measuring Index Usage with `$indexStats`

### 8.1. Querying Index Access Statistics

MongoDB provides the **$indexStats** aggregation stage:

~~~javascript
db.getSiblingDB("mongo_index_design_lab")
  .getCollection("lab_orders")
  .aggregate([
    { $indexStats: {} }
  ]).toArray();
~~~

Output includes fields such as index name, host/shard, and **accesses.ops** since the timestamp reported in **accesses.since**. These are observations from a specific environment and window, not guarantees that an index will never be needed in the future.

### 8.2. Interpreting Metrics in Context

| Observation | Interpretation |
| --- | --- |
| High `accesses.ops` | A workload is actively using this index; identify which queries and how well |
| `accesses.ops = 0` | No uses recorded in the observation window; **insufficient to prove useless** |
| Rarely used during the day | May serve weekly/monthly reports or incident recovery |
| Counter grows on only one node | Other nodes/shards may serve different read/report workloads |
| Numbers change before/after restart | Counters are not permanent history; always check `accesses.since` |
| Counter does not increment during `explain` | Do not treat `explain` runs as representative production usage |

When analyzing production, collect statistics **across full workload cycles**: peak hours, end-of-day jobs, month-end closing, periodic reports, and rare critical flows. In replica sets or sharded clusters, inspect collection scope across all nodes and roles rather than relying on a single snapshot.

### 8.3. Do Not Use `$indexStats` in Place of `explain`

**$indexStats** answers: "How many times was this index accessed during the observation window?"

**explain("executionStats")** answers: "For this specific query, filter, sort, and projection, which plan was chosen and how many keys/documents were examined?"

Both questions matter. An index with high `accesses.ops` that produces terrible plans may still need redesign; an index unused this week that enforces a unique constraint cannot be dropped for low usage.

## 9. Controlled Process for Removing Redundant Indexes

Dropping a redundant index reclaims disk space and reduces write overhead, yet **`dropIndex` is a collection-wide operational change**. Never run it directly in production simply because a lab example showed two indexes sharing a prefix.

### 9.1. Step 1 — Capture Existing Definitions

In the lab:

~~~javascript
const lab = db.getSiblingDB("mongo_index_design_lab");
const orders = lab.getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

In real systems, store index definitions in version control / migrations and audit permissions, unique, partial, collation, TTL options, and dependencies from other services. Ensure you have everything needed to **recreate the exact index** if problems arise after removal.

### 9.2. Step 2 — Identify Prefix Candidates

In this lesson, there are two pairs:

~~~text
ix_customer_short
   -> prefix of ix_customer_recent

ix_queue_short
   -> prefix of ix_queue_recent
~~~

These are **candidates**, not indexes already proven safe to drop. Inventory all queries using `customer`/`status`, compare plans, and review queries with strict latency targets.

### 9.3. Step 3 — Observe with `explain` and Statistics

Example query set using `customer`:

~~~javascript
const historyFilter = {
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
};

printjson(
  orders.find(historyFilter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .explain("executionStats")
);

printjson(
  orders.find(historyFilter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_customer_recent")
    .explain("executionStats")
);
~~~

If the planner currently selects `ix_customer_short` for a customer-only query, test how that query behaves when only `ix_customer_recent` remains. Add all related queries to your test/monitoring suite; never optimize one sample query while ignoring the rest of the application.

### 9.4. Step 4 — Hide an Index to Test Removing It from Selection

MongoDB supports **hidden indexes** in compatible releases (from MongoDB 4.4 onward). A hidden index **is ignored by the query planner**, yet MongoDB still **maintains it on inserts, updates, and deletes**.

In the lab:

~~~javascript
orders.hideIndex("ix_customer_short");

printjson(
  orders.find({
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

Once the short index is hidden, the planner must pick another plan—such as the longer `ix_customer_recent`. This lets you verify correctness and latency without the short candidate. **You do not need to drop immediately** just to test how queries run without that index.

Key points to emphasize:

- Hiding an index is a **collection-level change** affecting all queries, not just your current `mongosh` session.
- Hidden indexes **still consume disk space and write maintenance overhead**, so hiding does not directly measure the write-performance gains of dropping.
- The planner skips hidden indexes, and you cannot `hint` a hidden index as an active candidate.
- You cannot hide the **_id_** index.
- If a regression appears, you can **unhide** immediately to restore planner eligibility without rebuilding.

### 9.5. Step 5 — Unhide or Drop

To restore the index under test:

~~~javascript
orders.unhideIndex("ix_customer_short");
~~~

Once sufficient evidence confirms the short index is unnecessary, drop **only the exact named index** in the lab environment:

~~~javascript
// Run only after confirming the lab collection and index name.
const lab = db.getSiblingDB("mongo_index_design_lab");
const orders = lab.getCollection("lab_orders");

const candidate = "ix_customer_short";
const found = orders.getIndexes().find(x => x.name === candidate);

if (!found) {
  print("Index does not exist: " + candidate);
} else {
  print("Dropping named lab index: " + candidate);
  printjson(orders.dropIndex(candidate));
}
~~~

This drops only **ix_customer_short** in **lab_orders** inside **mongo_index_design_lab**. Never drop unique indexes or `_id`. Never pass an index name taken directly from untrusted user input.

If testing reveals you need to restore it, recreate the short index using its original definition:

~~~javascript
orders.createIndex(
  { dataset: 1, tenantId: 1, customerId: 1 },
  { name: "ix_customer_short" }
);
~~~

Rebuilding an index can consume significant time and resources, especially on large collections. That is why **hide first, observe, and only then drop** is so valuable.

### 9.6. Step 6 — Verify After the Change

After dropping, monitor:

- p95/p99 latency of queries filtering by `customerId`.
- Any unexpected `COLLSCAN` or `SORT` stages appearing.
- `totalDocsExamined`/`nReturned` and `totalKeysExamined`.
- CPU, cache pressure, disk I/O, and connection pool saturation.
- Insert/update/delete throughput and write latency.
- Index sizes and replication/backup impacts.
- Periodic batch jobs running on longer schedules.

Do not declare success simply because a `mongosh` test query still returns the right rows. Dropping an index can leave queries returning **correct data slowly** as data grows or when month-end tasks execute.

## 10. Redundant Indexes: Decision Matrix

| Index pair | Initial assessment | Sensible action |
| --- | --- | --- |
| **{tenantId}** and **{tenantId,customerId,createdAt}** | Shorter index is a prefix | Evaluate dropping the shorter index if it has no special options or distinct benefit |
| **{tenantId,customerId}** and **{tenantId,status}** | Share first field, differ in second | Likely need both for different queries |
| **{tenantId,customerId,createdAt}** and **{tenantId,createdAt}** | Not the same prefix order | Tenant-wide chronological queries may need the second index |
| Same keys, but one is **unique** | Different data constraint | Never drop unique without an equivalent safeguard |
| Full index and partial index with identical keys | Indexed document subsets differ | Check filters and query coverage before deciding |
| Regular index and TTL index on same field | TTL also performs auto-expiration | Never treat TTL as a useless duplicate |
| Indexes with different collations | String comparison/sort rules differ | Keep both if both collations serve real requirements |
| Index containing an array vs. scalar index | Multikey, covered, and sort rules differ | Inspect query plans and data types first |
| Indexes A and B with fully inverted sort directions | Same index can be scanned in reverse | Check equality prefixes and sort directions before keeping both |
| Index with `accesses.ops = 0` for one day | Unused in a short window | Insufficient reason to drop; check business cycles and constraints |

## 11. Index Costs: The Read vs. Write Trade-Off

### 11.1. Every Index Must Be Maintained

When inserting an Order, MongoDB writes the document and updates all relevant indexes. When updating an indexed field, index keys may need changing. When deleting a document, its index entries must be removed.

With many overlapping indexes, a single write touches multiple nearly identical structures. Consequences can include:

- Higher insert/update/delete latency.
- Greater write amplification and more data to replicate/back up.
- Larger total index storage footprint and cache pressure.
- Longer index build/migration times and higher operational complexity.

Therefore, pruning verified redundant indexes delivers substantial optimization, particularly in write-heavy systems.

### 11.2. Longer Indexes Are Not Always Better

A compound index packing many fields:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  total: 1,
  orderNo: 1
}
~~~

does not automatically replace all shorter indexes well:

- A query filtering only `tenantId` and sorting by `createdAt` cannot use `createdAt` order because `customerId` and `status` sit ahead of it.
- Wider keys consume more storage.
- Different projections still trigger different `FETCH` behaviors.
- Forcing one giant index onto every access pattern can push queries into suboptimal scans and sorts.

The goal is a **right-sized index set**, not **one giant index**.

### 11.3. Arrays Increase Fan-Out

If an indexed field is an Array, MongoDB creates a **multikey index** with multiple entries per document. For instance, an index on `items.sku` scales in cost with the number of distinct SKUs inside each Order. Two independent arrays in one compound multikey index also hit parallel-array restrictions.

Add a multikey index only when queries genuinely filter on array elements. Never index every array field "just in case we search it later."

## 12. Special Conditions to Check Before Dropping an Index

### 12.1. Partial Indexes

Example workload querying only pending orders:

~~~javascript
orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "ix_pending_by_tenant",
    partialFilterExpression: { status: "pending" }
  }
);
~~~

This index includes only documents with **status: "pending"**; it can stay compact and efficient when only a small fraction of orders remain pending. MongoDB uses a partial index only when query conditions guarantee no documents outside the indexed subset are needed. It **does not** replace a full-collection index for order-history queries spanning all statuses.

**Lab note:** this example index uses `tenantId` and `createdAt`, whereas production multi-tenant systems may require routing/sharding fields too; tailor to your workload. Create indexes only when backed by real use cases and measurements.

### 12.2. Sparse Indexes

A sparse index skips documents missing the indexed field. This helps when many documents lack `email` or `externalId`, yet differs from a full index on null/missing queries and planner eligibility.

Never drop a sparse index just because it shares the key pattern of a full index without checking semantics, uniqueness, and missing-field documents.

### 12.3. Unique Indexes

A unique index enforces data integrity, not just read speed. A non-unique index with the same prefix is no substitute. Dropping a unique index introduces duplicate risk and must be evaluated as a **business constraint change**.

### 12.4. TTL Indexes

A TTL index purges expired documents in the background. If a `sessions` collection has a TTL index, never drop it just because `$indexStats` shows few read queries using it. Its purpose is **data retention**, not frequent application lookups.

### 12.5. Collation

Indexes built with different collations support different string comparison and sorting rules, such as case-sensitive vs. case-insensitive. Queries normally need a matching collation to leverage the index for string comparisons/sorts as intended. Check `collation` options in both `getIndexes` and queries before assuming one index replaces another.

### 12.6. Text, Geospatial, Hashed, and Wildcard Indexes

Specialized index types have distinct purposes and limits:

- **Text:** supports full-text search via text-index mechanics.
- **Geospatial:** supports coordinate and geographic queries.
- **Hashed:** indexes hashed values, commonly for equality lookups and shard distribution.
- **Wildcard:** helpful for unpredictable dynamic field paths, though not a replacement for targeted hot-query indexes.

Never drop these simply because they reference the same field name as a standard B-tree index.

## 13. From Requirements to an Index Set in Real Projects

Follow this step-by-step workflow:

**Step 1 — Collect query shapes:** Gather critical APIs and queries with exact filters, sorts, projections, limits, page sizes, call rates, latency targets, and tenant context. Do not start from a list of schema fields.

**Step 2 — Group queries:** Queries sharing the same equality prefix and sort can share an index; queries with differing sorts or leading filters may need separate indexes.

**Step 3 — Propose candidate indexes:** Start from ESR, prefixes, sort directions, and unique/partial/TTL constraints. Prefer indexes capable of serving multiple real queries.

**Step 4 — Inspect real data:** Measure cardinality, `status`/`tenant`/`customer` skew, null/missing rates, array lengths, and growth rates. An index fine for small tenants may struggle on mega-tenants.

**Step 5 — Measure `executionStats`:** Compare planner-chosen plans against candidate indexes on representative datasets. Inspect `IXSCAN`, `FETCH`, `SORT`, `indexBounds`, and key/doc scan counts.

**Step 6 — Identify overlaps:** Compare key patterns **and all options**. Mark prefix indexes only as **candidates**, never auto-drop.

**Step 7 — Collect usage:** Use `$indexStats`, profiler/slow-query logs, API telemetry, and workload cycles. Account for infrequent batch jobs and data constraints.

**Step 8 — Run controlled hidden-index tests:** In staging or via safe rollout processes, hide the candidate, monitor query plans and latency, and keep immediate unhide ready for regressions.

**Step 9 — Drop approved indexes carefully:** Save full definitions/rollbacks, pick an appropriate maintenance window, monitor load, and avoid dropping multiple indexes at once without isolating individual impacts.

**Step 10 — Monitor post-change:** Track p95/p99 latency, keys/docs examined, write latency, index size, errors, and scheduled jobs. Update index ownership docs so future changes do not reintroduce redundant indexes.

Healthy index governance assigns clear ownership for **each index's purpose**. When nobody knows which query an index serves, the cost isn't only disk space—it is ongoing maintenance risk.

## 14. Common Mistakes

| Mistake | Why it is wrong | Remedy |
| --- | --- | --- |
| Indexing every field | Inflates write/storage costs without guaranteeing sort support | Design from query shapes |
| Treating multiple single-field indexes as equal to one compound index | Intersection is not guaranteed optimal and lacks compound sort | Evaluate compound indexes via ESR |
| Dropping every prefix of a longer index | Shorter indexes may carry different options or run faster for narrow lookups | Review semantics and workload before dropping |
| Dropping a unique index because usage is 0 | Unique enforces data integrity constraints | Keep until an equivalent constraint exists |
| Dropping a TTL index because no query reads it | TTL drives background document expiration | Retain per retention policy |
| Assuming `{tenant,customer,createdAt}` sorts all tenant orders | `customer` sits between `tenant` and `createdAt` | Consider `{tenant,createdAt}` for tenant-wide queries |
| Assuming `IXSCAN` means the query is optimal | Can still scan excessive keys/docs or execute `SORT` | Check `executionStats` and latency |
| Hardcoding `hint` in production | Prevents the planner from adapting as data shifts | Use `hint` only deliberately with measured evidence |
| Declaring an index useless from a few hours of `$indexStats` | Misses daily, weekly, and month-end jobs | Observe across full cycles and all nodes |
| Thinking hiding an index cuts write overhead | Hidden indexes are still updated on writes | Hide only tests removing planner selection |
| Dropping multiple indexes at once | Hard to trace regressions and roll back cleanly | Drop candidates one at a time with monitoring |
| Building one giant index for every query | Middle fields block filters/sorts; index grows bloated | Separate by access patterns |
| Benchmarking only in a tiny lab | `COLLSCAN` wins on tiny datasets | Test with representative scale |
| Ignoring collation, partial, or sparse options | Changes semantics even when field names match | Compare full `getIndexes` specs |
| Dropping indexes based on name overlap | Names do not prove identical keys or semantics | Compare keys, options, and ownership |

## 15. Practice Exercises

### Exercise 1 — Writing Access Patterns

For an e-commerce system, write query contracts for these views: customer order history, pending queue, all orders by tenant, and an amount-range report. For each query, specify equality, sort, range, projection, and assumed frequency.

### Exercise 2 — Prefixes and Sorting

Given the index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Classify these queries:

1. Find all orders by `tenantId`/`customerId`.
2. Find orders by `tenantId`/`customerId` and sort by `createdAt` descending.
3. Find orders by `tenantId` and sort by `createdAt` descending.
4. Find orders by `customerId` without `tenantId`.

Explain which queries leverage prefixes cleanly and which require a different index.

### Exercise 3 — ESR vs. ERS

Design an index for a query filtering `tenantId`/`status` and `total` between A and B, sorted by `createdAt` descending. Propose two field orders—one ESR-oriented and one favoring selective ranges. List what metrics to measure to decide which yields lower total cost.

### Exercise 4 — Measuring Short vs. Long Indexes

After running the seed script, compare `explain` using **ix_customer_short** versus **ix_customer_recent** when querying history for `c001`. Inspect `indexBounds`, `FETCH`, `SORT`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. Why are results on 12 documents insufficient to assert production latency differences?

### Exercise 5 — Removing a Prefix-Redundant Index

Inspect `getIndexes`, run `hideIndex` on **ix_customer_short**, re-check customer queries, and then run `unhideIndex`. List the prerequisites required before running `dropIndex` in production and explain why hidden indexes do not measure write-cost savings.

### Exercise 6 — Avoiding Accidental Drops of Critical Indexes

Suppose a collection has these indexes:

~~~text
{tenantId:1,orderNo:1} unique
{tenantId:1,orderNo:1,createdAt:-1} non-unique
{expiresAt:1} TTL
{tenantId:1,status:1} partial(status="pending")
{tenantId:1,status:1,createdAt:-1} full
~~~

Classify overlapping indexes versus indexes with distinct semantics. Explain why you must never drop unique or TTL indexes merely because another index exists or `$indexStats` shows zero reads.

### Exercise 7 — Estimating Write Overhead

Suppose orders have 6 indexes, receive 2,000 writes/sec, and grow rapidly. List the metrics to monitor when adding or removing an index. Why can't exact index size be calculated simply as document count times indexed field count?

### Exercise 8 — Queries Hit by a Blocking SORT

Run `explain` on Q4 hinting **ix_customer_recent** and then **ix_tenant_recent**. Determine whether the query requires a `SORT` when using the index with `customerId` in the middle. Explain why multiple customers' records lack global `createdAt` order in the first index.

### Exercise 9 — Rollout Workflow

Design a decommissioning workflow for a suspected redundant index on a multi-million-document collection: multi-cycle usage collection, metadata backup, controlled hiding, regression monitoring, exact-name drop, and rebuild planning. Specify rollback triggers.

### Exercise 10 — Minimal Index Set

From the lab's index list, select a sensible minimal index set for Q1–Q6 under the stated workload assumptions. Specify which indexes are kept for **performance**, which for **uniqueness**, which are **removal candidates**, and what additional measurements are needed before finalizing.

## 16. MongoDB References

- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Index Stats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/).
- MongoDB Manual — [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/).
- MongoDB Manual — [db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/).
- MongoDB Manual — [db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/).

**Conclusion:** Index design starts from **filters, sorts, projections, limits, and real query frequencies**, not from a list of schema fields. Compound indexes can replace several prefix indexes, yet **prefix overlap is only a clue to investigate**. Before dropping an index, understand every option, uniqueness/retention constraint, query plan, usage pattern, and operational impact. **A good index set is the smallest one that satisfies critical read paths, protects required invariants, and keeps write costs within acceptable limits.**
