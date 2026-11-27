# Field Order, Index Prefixes, and Index Reusability in MongoDB

## 1. Why Does Field Order in an Index Matter?

In MongoDB, indexes help the database locate matching documents without scanning the entire collection sequentially. For a **compound index** (an index composed of multiple fields), **field order** is part of the index's structural design, not merely syntactic ordering.

Suppose a B2B tenant order-management application routinely receives these queries:

1. Find all orders belonging to a tenant.
2. Find orders belonging to a tenant with status `PAID`.
3. Within a tenant and status, retrieve the newest orders first.
4. Find orders with a given status across **all tenants**.
5. Filter orders within a time range without specifying a tenant.

An index such as:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

usually serves queries 1–3 well, yet is not automatically optimal for 4–5. The reason is that index keys are ordered **from left to right**: `tenantId` first, `status` next, and then `createdAt` within each fixed group of preceding values.

That is the focus of this lesson: **field order, index prefixes, and index reusability**. After completing it, you will:

- Understand how a compound index orders keys and why field order affects queries.
- Identify the **prefixes** of a compound index.
- Know when one compound index can serve multiple distinct query patterns.
- Understand the conditions for an index to support `sort()`, in both forward and reverse directions.
- Apply the **Equality – Sort – Range (ESR)** guideline as a starting point for design.
- Know how to read `explain("executionStats")` to inspect selected indexes and execution costs.
- Avoid creating redundant indexes or relying on an index mismatched to critical query patterns.

## 2. Single-Field and Compound Indexes

### 2.1. Single-Field Index

A single-field index contains only one key field:

```javascript
db.orders.createIndex({ tenantId: 1 });
```

`1` denotes ascending order; `-1` denotes descending order. For a single-field index on a scalar field, MongoDB can generally scan the index forward or backward to serve ascending or descending sorts, so choosing `1` versus `-1` matters far less than in compound indexes with mixed sort directions.

Special cases such as multikey, collation, text, hashed, wildcard, or geospatial indexes follow their own rules. In this lesson, we first examine **standard B-tree indexes on scalar fields**.

### 2.2. Compound Index

A compound index stores multiple fields in their declared order:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Conceptual key order:

```text
(tenantId ASC, status ASC, createdAt DESC)

tenant A
 ├── status CANCELLED
 │     ├── newest createdAt
 │     └── older createdAt
 ├── status NEW
 │     ├── newest createdAt
 │     └── older createdAt
 └── status PAID
       ├── newest createdAt
       └── older createdAt

tenant B
 ├── status NEW
 │     └── ...
 └── status PAID
       └── ...
```

This diagram illustrates logical key ordering, not the exact physical layout of each B-tree page. Key takeaways to remember:

1. Keys sharing the same `tenantId` sit in the same logical region.
2. Within a tenant's region, keys sharing the same `status` are grouped together.
3. Within each tenant + status group, `createdAt` is ordered in the chosen direction.

Therefore, once `tenantId` and `status` are known, the database can jump to a narrow key range and read orders in date order without re-sorting the entire dataset.

### 2.3. An Index Is Not "Three Single-Field Indexes Combined"

The compound index `{ tenantId: 1, status: 1, createdAt: -1 }` is not equivalent to three separate single-field indexes:

```javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
```

Three single-field indexes can assist individual conditions, and MongoDB may consider index intersection in certain cases. However, never assume index intersection delivers the same filtering efficiency and sort order as a compound index tailored to the query pattern.

A compound index's advantage is that **all fields reside together in a single ordered key**. That is why field order cannot be ignored when optimizing combined predicates.

## 3. Index Prefixes

### 3.1. Definition

Given the index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

the **contiguous prefixes starting from the first field** are:

```javascript
{ tenantId: 1 }

{ tenantId: 1, status: 1 }

{ tenantId: 1, status: 1, createdAt: -1 }
```

The following sets are **not prefixes** of the index above:

```javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 } // Skips status in the middle
```

The last one is easy to get wrong: `{tenantId, createdAt}` still includes the leading `tenantId` field, yet it is **not a contiguous prefix** because it skips `status`. It can use part of the index to filter by tenant and sometimes check the trailing field at the key level, but it lacks the full benefit of narrowing contiguously along `tenantId → status → createdAt`.

### 3.2. Reusing a Compound Index for Prefix Queries

With the index above, the following queries can typically leverage it:

```javascript
// Single-field prefix.
db.orders.find({ tenantId: "TENANT-A" });

// Two-field prefix.
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
});

// Full prefix, with a range on the last field.
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

This is the core idea of **index reusability**: a well-designed compound index can serve multiple queries filtering on its different prefixes.

However, "can be used" and "will be chosen by the query planner" are not the same. For small collections, low selectivity, or cases where index scans plus document fetches cost more than a collection scan, the optimizer may still pick `COLLSCAN`. Always verify with `explain()` on representative data.

### 3.3. Queries Omitting the First Field

Queries like:

```javascript
db.orders.find({ status: "PAID" });

db.orders.find({
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
});
```

have no predicate on `tenantId`, skipping the index's leading field. The compound index above is typically **inefficient** at narrowing the search range for them. Some plans may still scan the index and filter, yet that is not equivalent to a narrow lookup by `status` or `createdAt` keys.

If querying across all tenants by `status` or date is a high-frequency use case, consider a separate index with the appropriate leading field, such as:

```javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
```

Do not add an index merely because a query exists; evaluate call frequency, returned document count, selectivity, and index overhead.

### 3.4. Filter Fields Do Not Need to Match Index Order

In JavaScript, the two filters below express the exact same condition:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
});

db.orders.find({
  status: "PAID",
  tenantId: "TENANT-A"
});
```

**The order in which fields are written in a filter does not dictate index key order.** The MongoDB query planner evaluates predicates against available indexes. The order **declared when creating the compound index** is what determines how keys are organized.

## 4. Setting Up Test Data in `mongosh`

To observe these principles, create an isolated database and a few sample orders. Run this only on a MongoDB instance where you are permitted to write test data, never on a production collection.

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Adjust the URI to match your local MongoDB configuration. Inside the shell:

```javascript
const lab = db.getSiblingDB("mongo_index_row150_lab");
const orders = lab.getCollection("orders_demo");

// Each run gets its own tenant so it doesn't overwrite other test runs.
const tenantId = "row150-" + new ObjectId().toHexString();
const runId = tenantId;

const samples = [
  { status: "NEW",       day: "2026-11-01T03:00:00Z", amountCents: 100000 },
  { status: "NEW",       day: "2026-11-03T03:00:00Z", amountCents: 150000 },
  { status: "NEW",       day: "2026-11-09T03:00:00Z", amountCents: 180000 },
  { status: "PAID",      day: "2026-11-02T04:00:00Z", amountCents: 200000 },
  { status: "PAID",      day: "2026-11-05T04:00:00Z", amountCents: 250000 },
  { status: "PAID",      day: "2026-11-10T04:00:00Z", amountCents: 300000 },
  { status: "PAID",      day: "2026-11-12T04:00:00Z", amountCents: 220000 },
  { status: "SHIPPED",   day: "2026-11-04T05:00:00Z", amountCents: 350000 },
  { status: "SHIPPED",   day: "2026-11-08T05:00:00Z", amountCents: 190000 },
  { status: "CANCELLED", day: "2026-11-06T06:00:00Z", amountCents: 50000 }
];

orders.insertMany(samples.map((item, index) => ({
  _id: new ObjectId(),
  runId,
  tenantId,
  externalOrderId: "DEMO-" + String(index + 1).padStart(3, "0"),
  status: item.status,
  createdAt: ISODate(item.day),
  amountCents: item.amountCents
})));

orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "tenant_status_createdAt" }
);

printjson(orders.getIndexes());
```

Every single-tenant query in this lesson uses the generated `tenantId`, avoiding the need to simulate multiple tenants. In real deployments, environments typically host many tenants with uneven order volumes; **data distribution** is a critical factor when tuning indexes.

> `explain()` examples with only 10 documents teach how to read output, not how to prove performance. On tiny datasets, the optimizer may pick a collection scan; effective indexes in real systems must be measured on production-scale document counts and distributions.

## 5. Three Queries Leveraging Different Prefixes

### 5.1. Find All Orders for a Tenant

```javascript
orders.find(
  { tenantId },
  { _id: 0, externalOrderId: 1, status: 1, createdAt: 1 }
);
```

The `tenantId` predicate matches the single-field prefix. The index can locate the key range belonging to that tenant rather than scanning all tenants across the collection.

Note: when fetching all orders for a tenant, keys in the compound index are grouped by `status` before `createdAt`. If the application needs **all orders of a tenant sorted newest-first across all statuses**, the current index does not necessarily supply that sort order.

### 5.2. Find Orders by Tenant and Status

```javascript
orders.find(
  { tenantId, status: "PAID" },
  { _id: 0, externalOrderId: 1, createdAt: 1 }
);
```

This predicate matches the first two fields of the compound index. The database can narrow the key range by both tenant and status.

### 5.3. Find Paid Orders Within a Date Range

```javascript
orders.find(
  {
    tenantId,
    status: "PAID",
    createdAt: {
      $gte: ISODate("2026-11-05T00:00:00Z"),
      $lt: ISODate("2026-11-13T00:00:00Z")
    }
  },
  { _id: 0, externalOrderId: 1, createdAt: 1, amountCents: 1 }
).sort({ createdAt: -1 });
```

Here:

- `tenantId` is filtered by equality.
- `status` is also filtered by equality.
- `createdAt` is a range on the third field, and also the sort key.

Documents with the same tenant and status lie in one contiguous key range. Inside that range, `createdAt` is ordered descending, so the index typically assists both range filtering and returning results in the requested date order.

## 6. Field Order Determines Efficiency for Combined Filters

Consider three indexes containing the same three fields in different orders:

```javascript
// Index A
{ tenantId: 1, status: 1, createdAt: -1 }

// Index B
{ status: 1, tenantId: 1, createdAt: -1 }

// Index C
{ tenantId: 1, createdAt: -1, status: 1 }
```

With the filter:

```javascript
{
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}
```

both A and B place **both equality predicates** ahead of the `createdAt` range predicate. Whenever both `tenantId` and `status` are always supplied, either can be a reasonable candidate. However, their reusability differs:

- Index A has prefix `tenantId`, serving per-tenant queries that omit `status`.
- Index B has prefix `status`, serving cross-tenant queries by status.
- Index C has prefix `tenantId` then `createdAt`, which suits a full chronological order history per tenant, yet places `status` after the `createdAt` range—making narrowing by `status` less effective than Index A when filtering by both status and date.

You cannot rank A, B, and C in isolation without knowing **which query set matters most** and how values are distributed in the data.

### 6.1. Selection Table by Query Pattern

| Query pattern | Index worth considering | Explanation |
| --- | --- | --- |
| `{tenantId}` | `{tenantId:1, status:1, createdAt:-1}` | Has tenant prefix |
| `{tenantId, status}` | `{tenantId:1, status:1, createdAt:-1}` | Uses first two fields |
| `{tenantId, status}` + sort `createdAt:-1` | `{tenantId:1, status:1, createdAt:-1}` | Equality precedes sort key |
| `{tenantId}` + sort `createdAt:-1` | `{tenantId:1, createdAt:-1}` | No `status` sitting in between |
| `{status}` across all tenants | `{status:1, createdAt:-1}` | Status leads |
| Only `createdAt` range | `{createdAt:-1}` | Date leads |
| `{tenantId, createdAt range}`, no status filter | `{tenantId:1, createdAt:-1}` | Prefix matches filter and sort |

This table illustrates selection principles, **not a mandate to create every index listed**. Every index consumes space and increases work on inserts, updates, and deletes. Choose a compact set serving frequent, selective queries.

### 6.2. Is "Always Put the Highest-Cardinality Field First" Always True?

No. Selectivity/cardinality is one factor, but it does not replace understanding **prefix reuse and sorting**. When queries always apply equality on both `tenantId` and `status`, either field order can locate a sufficiently narrow key slice. Yet if most APIs filter by tenant and many omit `status`, putting `tenantId` first creates valuable reusability.

For multi-tenant data, also weigh access controls, shard key design, volume skew, and the frequency of cross-tenant admin queries. Never apply a single "cardinality rule" while ignoring query patterns.

## 7. Does the Index Support `sort()`?

### 7.1. Sorting Within an Equality-Pinned Group

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

within the slice where `tenantId` and `status` are fixed, `createdAt` keys are ordered descending.

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });
```

This is the ideal pattern: fields **preceding the sort field** are pinned by equality, so the index can supply results in date order without a separate **blocking sort** stage.

### 7.2. Missing Equality on a Field Preceding the Sort Key

```javascript
orders.find({
  tenantId
}).sort({ createdAt: -1 });
```

In Index A, a tenant's documents are grouped by `status` before `createdAt`. Consequently, the overall order is not "newest first" across all statuses.

The index can still help filter by tenant, yet the query may require an extra `SORT` step or a separate index:

```javascript
orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_createdAt" }
);
```

`tenant_createdAt` fits an "all orders for a tenant, newest first" page better. However, it does not fully replace `tenant_status_createdAt` for status-filtered pages; weigh the frequency of both views.

### 7.3. Sorting by an Index Prefix

With `{tenantId:1, status:1, createdAt:-1}`, key order can support `sort({tenantId:1, status:1})` or `sort({tenantId:1, status:1, createdAt:-1})` under appropriate conditions.

A **non-prefix subset** of the sort key can also be supported if every preceding index field is pinned by equality. For example:

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });
```

Here the sort specifies only `createdAt`, which is not a prefix of the index. Yet because both preceding keys are fixed by equality, scanning the corresponding index slice yields exact `createdAt` order.

If the filter applies a range predicate on a field preceding the sort field, avoiding `SORT` behaves differently and is usually limited. Inspect actual plans instead of relying solely on field names.

### 7.4. Forward, Reverse, and Mixed-Direction Sorts

Index:

```javascript
{ a: 1, b: -1 }
```

typically supports sort patterns matching the same directional ratio:

```javascript
{ a: 1,  b: -1 }  // Forward scan.
{ a: -1, b: 1 }   // Full reverse scan of the index.
```

However, when both fields change direction identically:

```javascript
{ a: 1, b: 1 }
```

`{a:1,b:-1}` does not naturally yield that order when both `a` and `b` vary across the result set. Supporting that sort via an index may require creating an index with matching directions.

**Exception due to equality:** if `a` is pinned by equality, only `b`'s order varies. Scanning forward or backward within that key slice can yield `b` ascending or descending without needing two separate indexes. Therefore, always analyze **equality filters** alongside **sort objects** rather than comparing sort directions in isolation.

### 7.5. Deterministic Sorting and Pagination

Sorting solely by `createdAt` can encounter ties when multiple documents share the same timestamp. For pagination, add a deterministic tie-breaker such as `_id`:

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

If this is a critical query, consider the index:

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "tenant_status_createdAt_id" }
);
```

This index appends `_id` as the final sort key. Do not assume an index on `createdAt` automatically orders ties by `_id`. Storage internals may use an internal RecordId to disambiguate keys, which does not substitute for an explicit application sort contract.

## 8. The Equality – Sort – Range (ESR) Guideline

When designing a compound index, the **ESR** rule is a helpful starting point:

1. **Equality:** place fields compared with `=`/`$eq` first.
2. **Sort:** place fields used for result ordering next.
3. **Range:** place fields with range comparisons like `$gt`/`$gte`/`$lt`/`$lte` last.

Example query:

```javascript
db.products.find({
  category: "book",
  price: { $gte: 100000, $lt: 500000 }
}).sort({ rating: -1 });
```

ESR candidate:

```javascript
{ category: 1, rating: -1, price: 1 }
```

Where:

- `category` is equality.
- `rating` is sort.
- `price` is range.

Placing sort before range allows the query to retrieve documents in `rating` order from the index without re-sorting a large set of documents. However, narrowing by `price` may be less tight than an index with range first.

### 8.1. When to Consider Equality – Range – Sort (ERS)?

For the same query, an alternative index:

```javascript
{ category: 1, price: 1, rating: -1 }
```

can bound `price` more tightly if the price window is highly selective. In trade-off, the index cannot return results globally sorted by `rating` across the price range without an extra sort step.

Which option runs faster depends on:

- Value distribution of `price` in the collection.
- How many documents the range matches.
- Whether `limit` is used and how small it is.
- Ratio of documents examined to documents returned.
- Cost of `SORT` versus scanning extra index keys.

**ESR is a guideline, not an absolute law.** When a range is very selective, ERS can win. When avoiding a blocking sort and returning a limited slice is the priority, ESR often fits better. Use `explain("executionStats")` and test with representative data to decide.

### 8.2. Multiple Equality Fields: Which Comes First?

Suppose a query always includes:

```javascript
{
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}
```

Both indexes:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ status: 1, tenantId: 1, createdAt: -1 }
```

place equality predicates before the range predicate. For queries supplying both equalities, either can be a valid candidate. The key question is **which prefixes other queries use**:

- Tenant APIs always filter `tenantId`, but sometimes omit `status` → favor `tenantId` first.
- Admin dashboards frequently inspect all tenants by `status` → may need an index starting with `status`.

Optimize for the **entire workload**, not one query in isolation.

### 8.3. `$in`, `$ne`, and Other Operators

Not every operator behaves cleanly as pure equality or pure range in all scenarios:

- `$eq` with a single value is clear equality.
- `$in` with multiple values can be optimized similarly to multiple equalities or via other strategies; its effect on sorting and index usage depends on list size, version, and execution plan.
- `$ne` and `$nin` are generally low-selectivity and can require scanning many keys.
- `$regex` only optimizes certain patterns—such as case-sensitive prefix regexes—efficiently via a B-tree index under qualifying conditions.
- Collation can alter string comparisons and index usability.

Therefore, never slap ESR labels onto fields solely from operator names without checking expression shape, value counts, and actual query plans.

## 9. Commonly Misunderstood "Index Reuse" Cases

### 9.1. A Longer Index Can Subsume a Shorter Prefix Index

If a collection already has:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

many `{tenantId}` queries can use it, so adding:

```javascript
{ tenantId: 1 }
```

may not be necessary. If both indexes are standard indexes without differences in unique, sparse, partial, collation, or other critical options, the shorter prefix index may become **redundant** for serving queries. Keeping a shorter index can occasionally still pay off because it is smaller and cheaper for certain workloads, yet do not create it by default before measuring.

MongoDB does not verify whether every created index is necessary or automatically prune overlapping indexes during schema design. Before adding a new index, review existing indexes and their prefixes.

### 9.2. A Compound Unique Index Does Not Make Its Prefix Unique

```javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
```

This index permits:

```text
(tenant A, user@example.test)
(tenant B, user@example.test)
```

because the two key pairs differ. It **does not** enforce email uniqueness across the entire collection, nor does it restrict each tenant to one document.

Adding a unique index on `{tenantId:1}` creates a **completely different business constraint** (at most one document per tenant) and cannot be treated as a redundant prefix index.

Uniqueness always applies to the **entire key** within the index's scope, along with any applicable collation, partial filter, or null/missing rules.

### 9.3. A Partial Index Does Not Replace a Full Index for All Queries

For example, indexing only active orders:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    partialFilterExpression: { active: true },
    name: "active_tenant_createdAt"
  }
);
```

This index contains only documents where `active: true`. A query filtering on `tenantId` without constraining `active` cannot arbitrarily use this index to fetch all orders. For the planner to use a partial index without omitting results, the query predicate must entail the partial filter condition.

Two indexes sharing identical key fields but different partial filters are **not equivalent** in indexed document scope.

### 9.4. Sparse Indexes Differ in Scope from Standard Indexes

A sparse index only indexes documents containing the indexed field according to sparse index rules. For compound sparse indexes, behavior depends on the fields and index type. Hence, you cannot assume a sparse index replaces a standard index merely because their key orders match. Queries needing documents that lack the field must return complete results; misusing a sparse index would omit documents, so the planner accounts for completeness.

### 9.5. Collation Must Match String Comparison Requirements

Suppose you create:

```javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  {
    collation: { locale: "vi", strength: 2 },
    name: "tenant_name_vi"
  }
);
```

An equality query on `name` using the default simple collation may not leverage `tenant_name_vi` for string matching as expected. Supply the matching operation collation:

```javascript
db.customers.find({
  tenantId: "TENANT-A",
  name: "Nguyễn An"
}).collation({
  locale: "vi",
  strength: 2
});
```

When an index has a non-string prefix such as `tenantId`, some plans can still use that portion of the index even if collations differ for `name`; do not assume the entire index is completely unusable. Nonetheless, **reusability for string equality and sorting depends on compatible collations**.

In particular, `$regex` is not collation-aware in the same way equality is. A case-insensitive collated index does not automatically optimize `/abc/i` via collation rules.

### 9.6. Specialized Index Types Do Not Follow All Standard B-Tree Examples

Text, wildcard, hashed, 2dsphere, multikey, TTL, and other index types follow specific rules and limits. For example, a hashed index supports hash equality lookups rather than ranges or original-field sorting like standard ascending/descending indexes.

Do not extrapolate the scalar B-tree prefix table in this lesson to assume every key combination of specialized indexes behaves identically.

## 10. Multikey Indexes and Array Fields

### 10.1. When a Field in a Compound Index Is an Array

Suppose a product document contains multiple tags:

```javascript
{
  tenantId: "TENANT-A",
  tags: ["mongo", "database"],
  price: 250000
}
```

The index:

```javascript
db.products.createIndex({
  tenantId: 1,
  tags: 1,
  price: 1
});
```

becomes a **multikey index** when indexing an array field. One document can contribute multiple index keys depending on array elements. The query:

```javascript
db.products.find({
  tenantId: "TENANT-A",
  tags: "mongo"
});
```

can leverage this index. However, when evaluating covered queries and sorting involving array fields, understand multikey restrictions. Never assume prefix queries across arrays carry the same cost as scalar fields.

### 10.2. Not Every Pair of Array Fields Can Be Compound-Indexed

Compound multikey indexes impose limits on documents containing array fields in more than one component of the same index. When MongoDB classifies them as invalid parallel arrays, creating the index or inserting such documents can be rejected.

Conceptual example:

```javascript
{
  labels: ["A", "B"],
  categories: ["X", "Y"]
}
```

Do not casually create `{labels:1, categories:1}` on documents where both fields are independent arrays expecting MongoDB to index the Cartesian product. Check document structure and multikey restrictions, or remodel the data for the intended query.

## 11. Covered Queries: Using Indexes Without Reading Documents

### 11.1. Concept

A **covered query** can be answered purely from index entries without fetching documents, provided filter fields, projections, index types, collations, and other coverage rules are satisfied.

Suppose the index is:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

A query requesting only fields already stored in the index:

```javascript
orders.find(
  {
    tenantId,
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
);
```

With scalar data and qualifying conditions, this is a candidate for an index-covered query: all filter and projection fields live in the index. Specifying `_id: 0` is crucial because MongoDB returns `_id` by default; if the index excludes `_id` while the projection requests it, the engine may have to fetch documents.

Projecting few fields does not automatically cover a query. If the projection includes `amountCents` and the index lacks it, the query must read from the documents unless another qualifying index covers it.

### 11.2. Evaluating Covered Queries with explain

```javascript
const plan = orders.find(
  { tenantId, status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).explain("executionStats");

printjson(plan);
```

When truly covered, execution stats typically show `totalDocsExamined` equal to 0 and the index scan serving results directly. However, stage layouts can vary across versions/engines (for example, plans do not always show an identical `IXSCAN → PROJECTION_COVERED` chain). Rely on **metrics and specific case details**, not merely matching one stage sequence.

### 11.3. Should Every Displayed Field Be Added to an Index?

No. Every extra field inflates the index, consumes more RAM/cache/disk, and increases update cost. For a critical hot query, adding a couple of fields to achieve coverage can pay off; for endpoints returning full documents, widening an index to cover every field rarely helps.

Analyze query hot paths, document read counts, cache hit ratios, and write overhead before widening an index.

## 12. Reading `explain("executionStats")` to Verify Reusability

### 12.1. Inspecting the Query Planner

In `mongosh`:

```javascript
const explanation = orders.find({
  tenantId,
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).explain("executionStats");

printjson(explanation);
```

Depending on MongoDB version, the plan may appear as a classic stage tree or another engine's representation. Key indicators to inspect:

| Indicator | Interpretation |
| --- | --- |
| `COLLSCAN` | Collection scan |
| `IXSCAN` | Index scan |
| `FETCH` | Reads documents from the collection after identifying keys |
| `SORT` | Performs a separate sort stage, potentially adding cost |
| `indexName` | Name of the index used |
| `indexBounds` | Index key ranges traversed, if shown in the plan |
| `nReturned` | Number of documents returned |
| `totalKeysExamined` | Number of index keys scanned |
| `totalDocsExamined` | Number of documents examined |
| `executionTimeMillis` | Reported execution time; varies with cache warmth and run conditions |

### 12.2. Distinguishing Eligible Indexes from Selected Indexes

Just because an index **can** satisfy a predicate does not force the optimizer to **choose** it. The MongoDB planner compares viable plans using selectivity and estimated cost. An index may handle filtering without supporting the sort, leaving the query with `FETCH` or `SORT`.

To test candidate indexes, `hint()` can force the planner to try a specific index:

```javascript
printjson(
  orders.find(
    { tenantId, status: "PAID" }
  ).hint("tenant_status_createdAt").explain("executionStats")
);
```

`hint()` is helpful during experiments, but should not be embedded in every production query just to force index selection. Pinning an unsuitable index can degrade queries as data and workloads evolve.

### 12.3. Two Queries with the Same Filter but Different Sorts

Compare:

```javascript
// Q1: equality on tenantId + status.
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });

// Q2: equality on tenantId only, sorting by createdAt.
orders.find({
  tenantId
}).sort({ createdAt: -1 });
```

With `tenant_status_createdAt`, Q1 fits cleanly because all fields preceding `createdAt` are pinned. Q2 may need to sort documents across multiple status groups. When practicing on larger datasets, use `explain` to observe how the execution plans differ.

## 13. Avoiding Redundant Indexes and Excessive Write Overhead

### 13.1. Every Index Has a Cost

A collection with many indexes must update index structures on inserts, deletes, and updates that modify indexed fields. Indexes also consume disk space, RAM/cache, and maintenance time. Therefore:

```javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

do not necessarily all need to coexist. They share prefix relationships; longer indexes can cover many queries of shorter ones. Still, account for differences in **size and speed**, unique/partial/collation options, and each index's role in the workload.

### 13.2. Questions to Ask Before Adding a New Index

1. Which query is slow or high-frequency?
2. Which fields does the filter pin with equality?
3. Are there sorts or ranges? What are their order and directions?
4. Do other queries share the same prefix?
5. Do any existing indexes share the same prefix, collation, or partial/sparse scope?
6. Are there unique constraints that must remain untouched?
7. What are the expected key count and additional write costs?
8. Does `explain("executionStats")` confirm a real improvement?

Aim to serve **a group of key query patterns with the smallest sensible index set**, rather than creating a distinct index for every query variant.

### 13.3. Which Indexes Fit an Example Workload?

An application has two heavily used APIs:

- **API A:** `GET /orders?tenantId=T&status=PAID`, sorted by newest `createdAt`.
- **API B:** `GET /orders?tenantId=T`, sorted by newest `createdAt` across all statuses.

You may consider keeping:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 }
```

The first serves API A; the second serves API B. Although both start with `tenantId`, neither is a full prefix of the other because the second field differs; each solves a specific sort requirement.

If API A is rare and returns very few documents, it might not need its own index; the query planner could use the other index and filter further at acceptable cost. Base the final call on measured data.

## 14. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Any compound index containing a field finds it as fast as a single-field index" | Field position and prefixes govern how tightly the key range can be narrowed |
| "Filters must list fields in the exact same order as the index" | Field order in the filter object rarely matters; key order in the index definition is what counts |
| "`{a:1,b:1,c:1}` serves `{b,c}` just as well as `{a,b}`" | `{b,c}` skips the leading field and usually loses prefix efficiency |
| "If an index exists, the query will definitely use it" | The query planner may choose COLLSCAN or another index |
| "One compound index equals three single-field indexes" | It is one left-to-right ordered key structure |
| "`{a:1,b:-1}` supports any sort combination on a and b" | It supports forward or full reverse pattern scans, not flipping one field alone when both vary |
| "Ordering fields strictly by Equality, Sort, Range is always optimal" | ESR is only a starting point; selectivity and workload may favor another order |
| "Keep only the longest prefix index; shorter ones are always useless" | Shorter indexes can be smaller/cheaper; differing unique, partial, or collation options change meaning |
| "A unique compound index makes each prefix field unique" | Uniqueness applies to the full key tuple |
| "Any collated index works for all string equalities" | Operation and index collations must be compatible for string comparisons |
| "Indexing array fields behaves identically to scalar fields" | Multikey indexes have restrictions on keys, sorting, and covered queries |
| "`explain` on 10 documents proves production performance" | Representative data is needed; check total keys/docs examined and real costs |

## 15. Hands-On Practice: Designing Indexes from Requirements

### Exercise A. Identifying Prefixes

Given the index:

```javascript
{ companyId: 1, departmentId: 1, hiredAt: -1, _id: -1 }
```

Identify which of the following are contiguous prefixes:

1. `{companyId}`
2. `{companyId, departmentId}`
3. `{departmentId, hiredAt}`
4. `{companyId, hiredAt}`
5. `{companyId, departmentId, hiredAt}`
6. `{companyId, departmentId, hiredAt, _id}`

Hint: a prefix must always start from the **first field** and cannot skip any field in between.

### Exercise B. Choosing Field Order by Workload

A `tickets` collection receives these queries:

```javascript
// Q1: open tickets for a project, newest first.
db.tickets.find({
  projectId: "P1",
  status: "OPEN"
}).sort({ createdAt: -1 });

// Q2: all tickets for a project, newest first.
db.tickets.find({
  projectId: "P1"
}).sort({ createdAt: -1 });

// Q3: all OPEN tickets across all projects.
db.tickets.find({
  status: "OPEN"
});
```

Compare these candidates:

```javascript
{ projectId: 1, status: 1, createdAt: -1 }
{ projectId: 1, createdAt: -1 }
{ status: 1, projectId: 1 }
```

Questions: Which index best fits Q1, Q2, and Q3? If Q3 runs only once a month while Q1/Q2 run continuously, which indexes should be prioritized? There is no single optimal index set without knowing query frequencies and data volumes.

### Exercise C. Comparing ESR and ERS

Consider the query:

```javascript
db.products.find({
  brand: "A",
  price: { $gte: 100000, $lt: 200000 }
}).sort({ popularity: -1 }).limit(20);
```

Evaluate two indexes:

```javascript
{ brand: 1, popularity: -1, price: 1 }
{ brand: 1, price: 1, popularity: -1 }
```

If the `price` range is very wide, which index helps avoid sorting? If the price range matches only 0.1% of the brand's products, which index is worth testing? Use `explain` instead of guessing intuitively.

### Exercise D. Practicing Plan Inspection

Using the `orders_demo` collection from Section 4, compare:

```javascript
// Equality on tenant + status.
printjson(
  orders.find(
    { tenantId, status: "PAID" }
  ).sort({ createdAt: -1 }).explain("executionStats")
);

// Equality on tenant only.
printjson(
  orders.find(
    { tenantId }
  ).sort({ createdAt: -1 }).explain("executionStats")
);
```

Observe `indexName`, `IXSCAN`/`COLLSCAN`, `SORT` if present, `totalDocsExamined`, and `totalKeysExamined`. Results may differ across versions/engines and because the demo dataset is tiny.

## 16. Safely Cleaning Up Practice Data

Before cleaning up, confirm the database, collection, `runId`, and list of IDs belonging to your practice run:

```javascript
print("database=" + lab.getName());
print("collection=" + orders.getName());
print("runId=" + runId);

const ownedDocs = orders.find(
  { runId, tenantId },
  { _id: 1, externalOrderId: 1, runId: 1 }
).toArray();

printjson(ownedDocs);
print("ownedCount=" + ownedDocs.length);
```

Only once the IDs in the list match the exact documents you created, delete each document using a filter scoped to both `_id` and your run identifiers:

```javascript
for (const doc of ownedDocs) {
  const result = orders.deleteOne({
    _id: doc._id,
    runId,
    tenantId
  });
  print(doc.externalOrderId + ": deleted=" + result.deletedCount);
}

print("remaining=" + orders.countDocuments({ runId, tenantId }));
```

These commands leave documents with other `runId` values untouched. **Created indexes remain** in the collection; clean up test indexes or collections only according to ownership and environment procedures. Never use `deleteMany({})` or `dropDatabase()` on a shared database for lesson cleanup.

## 17. Review Questions

1. How does a compound index differ from three single-field indexes?
2. Given `{a:1,b:1,c:-1}`, what are the contiguous prefixes? Is `{a,c}` a prefix?
3. Why does a query filtering only on `b` usually fail to leverage an index starting with `a` efficiently?
4. Why can `{tenantId:1,status:1,createdAt:-1}` filter well by tenant yet not always support sorting all of a tenant's orders by `createdAt`?
5. How does an index `{a:1,b:-1}` support a full reverse sort?
6. When multiple equality predicates exist, what should you consider when deciding which field comes first?
7. What does ESR mean? When might placing range before sort be worthwhile?
8. When can a longer compound index replace a shorter prefix index? What differences make them non-equivalent?
9. Does a compound unique index enforce uniqueness on each prefix field individually?
10. Why do collation and partial filters affect index reusability?
11. What is a covered query, and why can the default `_id` projection prevent a query from being covered?
12. How do you use `explain("executionStats")` to inspect the chosen index, keys scanned, and documents read?

## 18. Conclusion

**A compound index is an ordered sequence of keys**, so field order dictates which data ranges can be accessed efficiently, how the index supports `sort()`, and which query patterns can share it. Index prefixes start at the first field and extend contiguously to the right. A longer index can serve queries matching its prefixes, while omitting the leading field or skipping an intermediate field diminishes or alters its benefit.

When selecting indexes, start from the **actual workload**—equalities, sorts, ranges, and pagination requirements; use ESR as an initial guide, then verify with `explain()` and metrics on representative data. The goal is not having as many indexes as possible, but a **just-enough index set** reusable across critical queries with balanced read and write costs.
