# Covered Queries and When MongoDB Must Fetch Documents

An index does more than help MongoDB **locate documents faster**. In certain cases, it also holds enough information for MongoDB to **return the results directly** **without opening the original documents in the collection**. This is a **covered query**. Understanding this concept accurately helps you design appropriate compound indexes, cut document reads, reduce I/O, and evaluate execution plans with `explain()`.

However, **using an index** does not equate to **being covered by an index**. A query can use `IXSCAN` to locate matching keys and still execute `FETCH` to read documents in order to retrieve unindexed fields or evaluate predicates not satisfied by the index.

This lesson explains:

- What a covered query is and how it differs from a query that **merely uses an index for filtering/sorting**.
- The conditions required for filters, projections, and sorts to be handled solely by an index.
- When MongoDB must read documents, even when `explain` shows an index was used.
- How to identify `IXSCAN`, `FETCH`, `COLLSCAN`, `totalKeysExamined`, and `totalDocsExamined`.
- Special cases: `_id`, `null` predicates, multikey indexes, nested fields, collation, partial indexes, and sharding.
- How to decide whether widening a compound index to cover a frequent query is worthwhile.

## 1. From Index Lookup to Covered Query

### 1.1. What Does an Index Contain?

For a standard B-tree index, MongoDB stores **index keys** built from the declared fields, linked to information that locates the source document. Consider a compound index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  customerId: 1,
  createdAt: -1
});
~~~

This index stores key components:

~~~text
(tenantId, status, customerId, createdAt)
                |
                v
         Source document location
~~~

Depending on the query, MongoDB can use index keys to locate matching records. If it needs to read `totalAmount` or `internalNote`—fields **not in the index**—MongoDB normally has to fetch the document.

### 1.2. Index Scan Followed by Document Fetch

A common plan:

~~~text
IXSCAN on index
   |
   v
FETCH documents from collection
   |
   v
Project returned fields
   |
   v
Client
~~~

Here:

1. `IXSCAN` scans the matching index keys.
2. `FETCH` retrieves the original documents, for instance to read `totalAmount`.
3. MongoDB applies any remaining predicates/projections and returns results.

Even though the query uses the index efficiently, it is **not a covered query** because source documents are still accessed.

### 1.3. Covered Query: Index-Only Execution

When **all data required for filtering and returning results** already resides in the index, MongoDB can execute:

~~~text
IXSCAN on index
   |
   v
Project directly from index keys
   |
   v
Client

No FETCH of source documents needed
~~~

One index can simultaneously identify matching documents, supply sort order, and provide returned values. Per the MongoDB Manual, the main requirements for a covered query include:

1. **All fields used in the filter** (including system fields required in certain topologies such as sharding) are satisfied by the same index.
2. **All fields returned** also reside in **that same index**.
3. **No filter predicate compares a field against `null`**.
4. The index and query shape satisfy additional index-type constraints, such as multikey restrictions.

If the query requires a sort key, sorting must also execute without reading extra fields from the document to remain index-only.

**Practical definition:** A covered query is one that can complete entirely using the index, **examining zero source documents**. It does not mean the index performs zero work: MongoDB may still scan many index keys, decode values, and assemble result documents.

## 2. Distinguishing Three Levels of Index Usage

| Case | Index involved? | Source documents read? | Typical indicators |
| --- | --- | --- | --- |
| **Collection scan** | No B-tree index used for primary scan | Yes | `COLLSCAN` |
| **Index scan + fetch** | Yes | Yes | `IXSCAN` alongside `FETCH` |
| **Covered query** | Yes | No | `IXSCAN` with no `FETCH`; `totalDocsExamined = 0` |

Examples:

~~~text
Index: (status, customerId, createdAt)

Query A:
  filter  = status, customerId
  return  = customerId, createdAt
  _id     = excluded
  => Potentially index-only

Query B:
  filter  = status, customerId
  return  = customerId, createdAt, totalAmount
  => Must read documents if totalAmount is not in the index

Query C:
  filter  = status, customerId, totalAmount > 100
  return  = customerId, createdAt
  => Must read documents to evaluate totalAmount
~~~

These examples are conceptual models. **The query planner picks the actual plan**; inspect `explain("executionStats")` instead of guessing from query shape alone. An index missing required fields generally cannot produce a covered plan, though the optimizer might pick a different index, index intersection, or a collection scan depending on data and available indexes.

## 3. Creating a Practice Dataset

Open `mongosh`, connect to a running MongoDB instance, and switch to a dedicated database:

~~~javascript
const lab = db.getSiblingDB("mongo_covered_query_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: ObjectId("000000000000000000000001"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-01T08:00:00Z"),
    totalAmount: 120,
    internalNote: "Urgent order",
    tags: ["web", "priority"]
  },
  {
    _id: ObjectId("000000000000000000000002"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-03T08:00:00Z"),
    totalAmount: 150,
    internalNote: "Summer promo",
    tags: ["web"]
  },
  {
    _id: ObjectId("000000000000000000000003"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C02",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    totalAmount: 240,
    internalNote: "New customer",
    tags: ["store"]
  },
  {
    _id: ObjectId("000000000000000000000004"),
    tenantId: "T1",
    status: "PENDING",
    customerId: "C01",
    createdAt: ISODate("2026-06-04T10:00:00Z"),
    totalAmount: 90,
    internalNote: "Unpaid",
    tags: ["web"]
  },
  {
    _id: ObjectId("000000000000000000000005"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-05T08:00:00Z"),
    totalAmount: 175,
    internalNote: "Confirmed",
    tags: ["web", "sale"]
  },
  {
    _id: ObjectId("000000000000000000000006"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C03",
    createdAt: ISODate("2026-06-06T08:00:00Z"),
    totalAmount: 300,
    internalNote: "Standard delivery",
    tags: ["store", "sale"]
  },
  {
    _id: ObjectId("000000000000000000000007"),
    tenantId: "T2",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-07T08:00:00Z"),
    totalAmount: 210,
    internalNote: "Different tenant",
    tags: ["web"]
  }
]);

lab.orders.find().sort({ createdAt: 1 });
~~~

Two details to note:

- `tenantId` isolates data across tenants, so **never drop the tenant filter** just to make a query covered.
- `totalAmount` and `internalNote` are fields **absent from the index used in the next section**, helping demonstrate when `FETCH` becomes necessary.

In this sample dataset, the `PAID` orders for tenant `T1` and customer `C01` are the three documents whose `_id` ends in `01`, `02`, and `05`.

## 4. Creating a Compound Index for a Covered Query

Create the index:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1
  },
  { name: "ix_tenant_status_customer_created" }
);

lab.orders.getIndexes();
~~~

This index contains these fields:

| Index component | Role in the example |
| --- | --- |
| `tenantId` | Equality predicate for tenant isolation |
| `status` | Equality predicate to select paid orders |
| `customerId` | Equality predicate to select the customer |
| `createdAt` | Returned timestamp and descending sort key |

With equality filters on the first three fields, MongoDB can exploit the `createdAt: -1` order within the matching index slice. Choose indexes based on **actual filters and sorts**, not solely to chase covered queries.

### 4.1. A Query That Can Be Covered

~~~javascript
const coveredFilter = {
  tenantId: "T1",
  status: "PAID",
  customerId: "C01"
};

const coveredProjection = {
  _id: 0,
  status: 1,
  customerId: 1,
  createdAt: 1
};

lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .toArray();
~~~

Expected output on the sample data, newest first:

~~~javascript
[
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-05T08:00:00.000Z")
  },
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-03T08:00:00.000Z")
  },
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-01T08:00:00.000Z")
  }
]
~~~

Why can this query be covered?

1. Filter fields `tenantId`, `status`, and `customerId` are all keys in the compound index.
2. The projection returns only `status`, `customerId`, and `createdAt`, all present in the index.
3. The projection explicitly sets `_id: 0`; `_id` **is not in the compound index** being used.
4. Sorting by `createdAt: -1` matches the trailing index key after the equality fields.
5. There is no `null` comparison, and no array fields are projected.

`hint()` in this lesson explicitly selects the index we want to study; normally, **production code should not routinely force indexes**. The planner may pick a better plan as data and indexes evolve.

### 4.2. Inspecting `explain` for a Covered Query

~~~javascript
const coveredExplain = lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");

printjson({
  nReturned: coveredExplain.executionStats.nReturned,
  totalKeysExamined: coveredExplain.executionStats.totalKeysExamined,
  totalDocsExamined: coveredExplain.executionStats.totalDocsExamined
});

printjson(coveredExplain.queryPlanner.winningPlan);
~~~

Here, `nReturned` is expected to be **3**. When MongoDB executes a covered plan, expect:

~~~text
IXSCAN: yes
FETCH: no
totalDocsExamined: 0
~~~

`totalKeysExamined` is typically greater than or equal to the number of returned records, though the exact count varies with the optimizer, bounds, and data. A covered query can scan index keys and return zero documents; `totalDocsExamined: 0` still holds.

In some MongoDB versions, the plan includes a `PROJECTION_COVERED` stage above `IXSCAN`. In versions using the **slot-based query execution engine**, the explain structure can look different. **Never build operational checks that hardcode a specific stage name at a fixed JSON nesting level.** Always combine `totalDocsExamined` with the actual plan tree.

## 5. Why `_id` Frequently Prevents Queries from Being Covered

### 5.1. `_id` Is Returned by Default

In MongoDB, `find(filter, projection)` returns `_id` by default unless you specify `_id: 0`. Remove the `_id` exclusion from the previous example:

~~~javascript
const withIdProjection = {
  status: 1,
  customerId: 1,
  createdAt: 1
  // Omit _id: 0.
};

lab.orders.find(
  coveredFilter,
  withIdProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

The results must include `_id`. **The secondary compound index being used does not expose `_id` as a queried/projected key**, so MongoDB must read the source documents to retrieve the identifier; the query is no longer covered by that index.

**Do not misunderstand:** MongoDB has a default index on `_id`, yet that **does not mean** a query can combine keys from the `_id` index and another compound index to automatically execute index-only. Covered query rules require all needed fields to be satisfied by the same eligible index.

### 5.2. Two Ways to Handle This

**Option A — The API does not need `_id`:** exclude `_id` from the projection:

~~~javascript
{
  _id: 0,
  customerId: 1,
  createdAt: 1
}
~~~

**Option B — The API needs `_id`:** append `_id` to the compound index when the query is critical and the storage trade-off makes sense:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "ix_tenant_status_customer_created_id" }
);
~~~

Query:

~~~javascript
lab.orders.find(
  coveredFilter,
  {
    _id: 1,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created_id")
 .explain("executionStats");
~~~

With the new index, both filtered and returned fields reside in the index. Now `_id` can be served from index keys and the query can be covered.

**Do not automatically append `_id` to every compound index.** Every added key enlarges the index and raises write and memory costs. If only rare queries need `_id`, the `FETCH` cost may be perfectly acceptable.

## 6. When the Projection Requests a Field Missing from the Index

A query's filter and sort are supported by the index, but the API also wants to display the order total:

~~~javascript
lab.orders.find(
  coveredFilter,
  {
    _id: 0,
    customerId: 1,
    createdAt: 1,
    totalAmount: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

`totalAmount` is not in the hinted index, so MongoDB cannot construct the complete result from index keys alone. The plan must read documents:

~~~text
IXSCAN (filter + order)
   |
   v
FETCH  (read totalAmount)
   |
   v
PROJECTION
~~~

On our sample dataset, `totalDocsExamined` may be **3**, because three documents are returned and need an unindexed field. In other scenarios, MongoDB may examine more documents than it returns if post-`FETCH` filtering is required.

One fact to remember: **a small projection does not automatically make a query covered**. Projections shrink response payloads, but avoiding document reads only happens when every projected field matches keys in an eligible index.

### 6.1. Should You Add `totalAmount` to the Index?

You could create an expanded index:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "ix_tenant_status_customer_created_amount" }
);
~~~

The previous query can now be covered by the new index, assuming no other obstacle. However:

- The new index is larger than the original one.
- Writes or updates modifying `totalAmount` must maintain extra index keys.
- Wide indexes consume more disk space and cache memory.
- Adding many fields just to "avoid FETCH" can make indexes bloated.
- If most queries return very few small documents, FETCH cost may be smaller than the overhead of a wide index.

**Design conclusion:** covered query benefits must be weighed against write and storage costs, not pursued as an absolute target.

## 7. When the Filter Uses a Field Missing from the Index

Suppose you only want orders with `totalAmount > 140` while still using the original index:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    totalAmount: { $gt: 140 }
  },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Even though **the projection omits `totalAmount`**, MongoDB still needs to **read `totalAmount`** to check whether each document matches the filter. The active index does not store that field, so it cannot evaluate the predicate fully.

Expected results are the two orders whose `_id` ends in `05` and `02`, though `_id` is omitted by the projection. Pseudocode:

~~~text
IXSCAN:
  locate T1 + PAID + C01 orders
   |
   v
FETCH:
  read totalAmount from each candidate document
   |
   v
FILTER:
  keep only totalAmount > 140
   |
   v
Return customerId, createdAt
~~~

If there are three candidates but only two matches, you may see `totalDocsExamined = 3` and `nReturned = 2`. Exact counts can vary by version and plan, yet the relationship is clear: documents **examined** differs from documents **returned**.

### 7.1. Distinguishing Indexed Predicates from Post-Filter Predicates

When a predicate targets an indexed field, the optimizer can tighten `indexBounds` directly inside `IXSCAN`. When a predicate is not covered by the index, MongoDB must evaluate it against values retrieved from documents after `FETCH`.

Sometimes an index handles part of the filtering while documents must still be fetched to confirm remaining predicates. Thus, seeing `IXSCAN` followed by `FETCH` does not mean the index is wasted: the index can still dramatically cut down how many documents must be inspected.

## 8. A Query Using an Index for Filtering and Sorting May Still Not Be Covered

A query can sort via an index and still fetch documents to return data:

~~~javascript
lab.orders.find(
  coveredFilter,
  { _id: 0, customerId: 1, totalAmount: 1 }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

The index handles all three equality filters and the `createdAt` sort order; however, returning `totalAmount` forces a `FETCH`.

Conversely, if you sort by a field **absent from the index** such as `totalAmount`—even if the projection returns only indexed fields—MongoDB still needs the sort field's values to order results:

~~~javascript
lab.orders.find(
  coveredFilter,
  { _id: 0, status: 1, customerId: 1 }
).sort({ totalAmount: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

`totalAmount` is absent from the index, so sorting by it cannot be completed from these index keys alone. The plan may require both `FETCH` and `SORT`.

Distinguish three independent questions:

1. **Does the index help locate documents matching the filter?**
2. **Does the index supply the requested sort order?**
3. **Does the index hold enough values to return the result without opening documents?**

Only when the third question is satisfied—and every supporting step is also index-only—do you have a covered query.

## 9. Null Equality Predicates: A Special Case

The MongoDB Manual specifies that a covered query **cannot compare a field against `null`**. For example:

~~~javascript
// Does not qualify as a covered query per MongoDB documentation:
lab.orders.find(
  { status: null },
  { _id: 0, status: 1 }
);

// Same behavior:
lab.orders.find(
  { status: { $eq: null } },
  { _id: 0, status: 1 }
);
~~~

In MongoDB, `{ field: null }` matches both documents **with a null value** and documents **missing that field**. This ambiguity between missing and null is one reason index keys alone cannot always verify the condition under coverage rules.

Be sure to distinguish:

| Document | `{ status: null }` | Interpretation |
| --- | --- | --- |
| `{ status: null }` | Matches | Has BSON null value |
| `{ }` | Matches | Missing `status` field |
| `{ status: "PAID" }` | Does not match | Non-null value |

**Not all negation or existence predicates behave identically.** `$exists`, `$type`, `$ne`, and `$nin` have distinct semantics and index eligibility. Never assume mechanically that "if a field is in the index, every condition on that field is covered."

If an application regularly uses `status` or `createdAt` in covered queries, schema validation helps guarantee fields are **always present with the right BSON type**. Still, validation does not turn `{ field: null }` into a covered query.

## 10. Multikey Indexes and Arrays: Conditionally Covered

When an indexed field holds an **array**, MongoDB creates a **multikey index**. Each array element can produce a corresponding index key. However, **the index does not store the full array structure** needed to reconstruct the original array value in a projection.

### 10.1. Creating a Multikey Index

The `lab.orders` dataset contains a `tags` field:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    tags: 1,
    status: 1
  },
  { name: "ix_tenant_tags_status" }
);
~~~

Because `tags` is an array in the documents, this index is a **compound multikey index**.

### 10.2. Covering a Query Without Returning the Array

You can filter for documents containing `"web"` while **projecting only the scalar `status` field**:

~~~javascript
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

MongoDB can use a compound multikey index to cover certain queries when these conditions hold:

- **The array field `tags` itself is not returned** in the projection.
- **No `$elemMatch` is used** in the query.
- All remaining covered-query requirements are satisfied.

In this example, `tenantId` and `tags` are filter fields and `status` is the returned scalar field—all present in the same index. The filter `tags: "web"` matches documents containing element `"web"`; reconstructing the entire `tags` array is unnecessary.

### 10.3. Returning the Array Forces a Document Read

~~~javascript
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1, tags: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

Now the client requests the **original `tags` array**; a multikey index cannot reconstruct that array from its keys. The query must fetch the document.

For instance, a document has:

~~~javascript
tags: ["web", "priority"]
~~~

The index holds keys per element, yet **does not replace the document storing the original array**. Element order, duplicate elements, and array shape are not preserved by multikey keys in a way suitable for projection.

### 10.4. `$elemMatch` Prevents Covered Queries

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    tags: { $elemMatch: { $eq: "web" } }
  },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

An `$elemMatch` predicate evaluates **single-element semantics**, and MongoDB documentation notes this case **cannot be covered by a multikey index**. The index can still locate candidate entries, yet documents must be fetched to verify matches.

**Do not confuse these:** a multikey index **can speed up array queries** even when it does not qualify for a covered query. Optimizing filtering and covering the full result are two separate concerns.

## 11. Nested Fields and Dotted Paths

Covered queries are not restricted to top-level fields. MongoDB can use an index on a **nested field** if filters and projections use the exact dotted path and other requirements are met.

Suppose a `profiles` collection contains:

~~~javascript
{
  _id: 1,
  userId: "U01",
  contact: {
    city: "Hanoi",
    country: "VN",
    phone: "0900000000"
  }
}
~~~

Create the index:

~~~javascript
lab.profiles.drop();

lab.profiles.insertMany([
  {
    _id: 1,
    userId: "U01",
    contact: { city: "Hanoi", country: "VN", phone: "0900000000" }
  },
  {
    _id: 2,
    userId: "U02",
    contact: { city: "Danang", country: "VN", phone: "0911111111" }
  }
]);

lab.profiles.createIndex(
  { "contact.city": 1, userId: 1 },
  { name: "ix_city_user" }
);
~~~

Query returning only the exact indexed dotted field:

~~~javascript
lab.profiles.find(
  { "contact.city": "Hanoi" },
  {
    _id: 0,
    "contact.city": 1,
    userId: 1
  }
).hint("ix_city_user")
 .explain("executionStats");
~~~

This is a covered query candidate because both the filter and projection paths belong to the index. Conversely, requesting **the entire `contact` object** or `contact.phone` requires fetching the source document, since the index stores only `contact.city` and `userId`.

When working with nested arrays or fields holding embedded objects of varying shapes, also watch out for multikey limits and dotted-path semantics. Never treat an index on a child field as a complete copy of its parent object.

## 12. Collation, Partial Indexes, and Sparse Indexes

### 12.1. Collation on Strings

**Collation** defines string comparison rules (case, accents, locale). A collated index can store **collation-encoded sort keys** that differ from the raw original string representation.

Example:

~~~javascript
lab.profiles.createIndex(
  { userId: 1 },
  {
    name: "ix_user_collated",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

A query intending to use this index for **string comparison** must specify a compatible collation:

~~~javascript
lab.profiles.find(
  { userId: "u01" },
  { _id: 0, userId: 1 }
).collation({ locale: "en", strength: 2 })
 .hint("ix_user_collated")
 .explain("executionStats");
~~~

With non-`simple` collations, string keys stored in the index may not preserve the exact raw representation required for all projections. Therefore, **a query using a collated index is not automatically a covered query**, especially when returning the original strings. Check `explain` and choose indexes/collations based on application needs rather than assumptions.

### 12.2. Partial Indexes Do Not Contain All Documents

A partial index stores keys only for documents satisfying its `partialFilterExpression`.

Example:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1 },
  {
    name: "ix_paid_orders_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
~~~

This index contains only `PAID` orders. A query filtering `status: "PAID"` can use it because the query predicate lets MongoDB verify all matching results fall inside the indexed subset:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01"
  },
  {
    _id: 0,
    tenantId: 1,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_paid_orders_partial")
 .explain("executionStats");
~~~

Notice: `status` appears in the **partial index filter**, not in the **key pattern**. If the projection requests `status` or the query is more complex, verify whether the planner can satisfy it from index metadata or requires a `FETCH`; do not assume a field referenced in `partialFilterExpression` is stored as an index key.

A query **not restricted to `PAID` orders** must not rely solely on this partial index to return complete results, because `PENDING` and `ARCHIVED` documents are absent from the index.

### 12.3. Sparse Indexes and Existence Conditions

A sparse index omits documents that lack the indexed field according to sparse rules. Queries that can match unindexed documents are **not automatically covered** simply because the field appears in the sparse index.

For instance, a query searching for documents **missing** a sparse-indexed field cannot retrieve valid results from an index that skipped them. With partial and sparse indexes, always verify **result-set completeness**, not just the fields listed in the key pattern.

## 13. Covered Queries on Sharded Collections

In a **sharded cluster**, MongoDB may need extra internal fields for routing or document checks. The MongoDB Manual notes that when executing through `mongos`, an index can only cover a query on a sharded collection if the index **includes the shard key**.

This means:

- An index covering all filter and projection fields on an unsharded collection **does not necessarily** qualify once sharded.
- Queries routed via `mongos` must account for the cluster's shard key configuration.
- Aligning an index with the shard key, filter, sort, and projection improves coverage chances, without guaranteeing every query is covered.
- Before altering indexes on a live cluster, evaluate query routing, scatter-gather behavior, and shard-key unique index constraints.

Always run `explain` against your application's **actual routing path**, not solely on a standalone `mongod` used for local development.

## 14. Reading explain: Distinguishing IXSCAN, FETCH, and Metrics

### 14.1. Basic Explain Command

~~~javascript
lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

`executionStats` reports execution metrics for the selected plan. Key fields:

| Name / concept | Meaning |
| --- | --- |
| `winningPlan` | Plan selected by the optimizer |
| `IXSCAN` | Scans entries from an index |
| `COLLSCAN` | Scans collection documents |
| `FETCH` | Retrieves documents from the collection using record locators |
| `PROJECTION_COVERED` | Projection stage satisfied directly from the index (seen in some plans) |
| `SORT` | Sorting stage; can consume memory/I/O if the index does not supply order |
| `nReturned` | Number of results emitted at the measured level |
| `totalKeysExamined` | Number of index entries examined |
| `totalDocsExamined` | Number of source document examinations |
| `indexBounds` | Index key value bounds scanned |

**`totalDocsExamined` is not a count of distinct documents**, nor does it always equal `nReturned`. If a document is examined multiple times within a plan, each examination is counted.

### 14.2. How to Confirm a Covered Query

Practical verification steps:

1. Check that `winningPlan` selects the expected index.
2. Inspect the entire plan tree, verify `IXSCAN`, and confirm no `FETCH` lies along the execution path.
3. Check that `executionStats.totalDocsExamined` equals **0**.
4. Confirm the filter and projection genuinely read values from the index rather than returning zero results or triggering a different optimization.
5. Compare against a query requiring an unindexed field to observe the difference.

Helper snippet to inspect metrics:

~~~javascript
function summarizeExplain(cursor) {
  const e = cursor.explain("executionStats");

  printjson({
    nReturned: e.executionStats.nReturned,
    totalKeysExamined: e.executionStats.totalKeysExamined,
    totalDocsExamined: e.executionStats.totalDocsExamined
  });

  printjson(e.queryPlanner.winningPlan);
}

summarizeExplain(
  lab.orders.find(
    coveredFilter,
    coveredProjection
  ).sort({ createdAt: -1 })
   .hint("ix_tenant_status_customer_created")
);
~~~

Across versions, `explain` may expose multiple plan layers or different shapes than shown above. **Never conclude a query is covered solely because `totalDocsExamined = 0`**; a query matching zero records or resolved by a special optimization can also examine 0 documents. For queries returning data, confirm the index-only path in the plan.

### 14.3. Interpreting Three Scenarios

**Scenario A — Covered:**

~~~text
nReturned = 3
totalKeysExamined >= 3
totalDocsExamined = 0
IXSCAN, no FETCH
~~~

**Scenario B — Index + FETCH:**

~~~text
nReturned = 3
totalKeysExamined >= 3
totalDocsExamined = 3 (illustrative example)
IXSCAN and FETCH
~~~

**Scenario C — Post-FETCH Filter:**

~~~text
nReturned = 2
totalKeysExamined >= 3
totalDocsExamined = 3 (illustrative example)
IXSCAN, FETCH, plus filtering on unindexed predicate
~~~

Numbers in B/C reflect the lab dataset and hinted index; actual counts depend on the plan and how the engine tallies document examinations.

### 14.4. When Is `hint` Useful?

`hint()` is helpful when **comparing two specific indexes** in a lab or when you have confirmed the planner is picking a problematic index in production. Yet hinting never turns a query missing an index field into a covered query. If `totalAmount` is missing from an index, hinting that index still cannot supply `totalAmount`.

In production, indexes evolve over time; a hardcoded hint can become suboptimal or fail with an error if the index is dropped. Treat hints as investigative tools or controlled operational overrides.

## 15. Should You Always Try to Achieve Covered Queries?

No. Covered queries reduce document reads, yet **wider indexes** impose their own costs.

### 15.1. Benefits

- Fewer reads of full source documents from the collection.
- Lower I/O when documents are large or cold (evicted from cache).
- Processing many results via compact index entries.
- Less projection work when returned fields already come from the index.

### 15.2. Costs

- **Larger index size** as more keys are appended.
- **Slower writes** because affected inserts, updates, and deletes must maintain larger index keys.
- **Higher RAM/cache pressure** as bigger indexes compete for memory.
- **Higher operational complexity**: overlapping indexes, field order, collations, partial filters, and schema versions.
- **Minimal gains** when queries return only a few small documents that already sit warm in cache.

Recommendation matrix:

| Workload | Recommendation |
| --- | --- |
| High-throughput list page needing only a few small fields | Consider an index covering filter, sort, and projection |
| Rare query returning 1–2 small documents | `FETCH` is usually acceptable |
| Very large documents where only a few scalar fields are needed | Covered queries can deliver clear savings |
| APIs returning large arrays or complex objects | Coverage is impractical; optimize filters, projections, and document schema |
| Write-heavy collection with already large indexes | Avoid widening indexes just for a rare screen |
| Queries on `null`, arrays with `$elemMatch`, or custom collations | Check `explain` and accept index-only limits |
| Added index yet queries remain slow | Inspect `explain`, profiler, data distribution, and cache before concluding |

The balance point is **optimizing the overall workload**, not forcing `totalDocsExamined: 0` on every query.

## 16. Comparing with Related Concepts

### 16.1. A Covered Query Is Not Just an Index-Only Sort

A query can use an index for sorting and still `FETCH` documents for unindexed projected fields. In a plan, "no `SORT` stage" does not prove a covered query.

### 16.2. A Covered Query Is Not Just a Small Projection

A small projection trims the network payload, yet still triggers `FETCH` if any projected field is absent from the index.

### 16.3. A Covered Query Does Not Mean One Index Containing Every Collection Field

The goal is never to duplicate entire documents inside an index. Only fields **genuinely required by critical queries** deserve inclusion.

### 16.4. A Covered Query Is Not Always the Fastest Plan

Sometimes the planner picks a plan with `FETCH` that scans fewer index keys, or a smaller index enjoys better cache locality. Covered execution is a potential advantage, not the sole speed metric.

### 16.5. A Covered Query Is Not a Materialized View

A covered query reads **index keys of source documents** directly. A materialized view persists **precomputed aggregates** in a separate collection requiring synchronization. Both solve different problems.

## 17. Common Pitfalls and How to Fix Them

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| `IXSCAN` present but still `FETCH` | Filter, projection, or sort requires an unindexed field | Compare every field against the index key pattern |
| Projected only a few fields yet documents are still read | At least one projected field is not indexed | Drop the field if unneeded or consider widening the index |
| All fields are in the index yet not covered | `_id` is returned by default | Add `_id: 0` or include `_id` in the index |
| Two separate indexes contain the fields yet query isn't covered | Two indexes cannot merge to form one covered scan | Design one compound index covering all needed fields |
| `totalDocsExamined` differs from `nReturned` | Candidate documents were filtered out or examined multiple times | Inspect predicates and the `FETCH` stage |
| `totalDocsExamined = 0` but zero results returned | Query matched no documents | Check the plan and re-test on matching data |
| `{field: null}` query is not covered | Null equality is excluded from covered query eligibility | Review null/missing semantics and accept `FETCH` |
| Multikey index works for filter but returning the array triggers `FETCH` | Multikey keys cannot reconstruct full arrays | Omit the array from projection or accept `FETCH` |
| Array query with `$elemMatch` loses coverage | Multikey covered queries do not support `$elemMatch` | Optimize query/index without forcing coverage |
| Fast sort yet documents are still read | Index supplies order, projection needs extra fields | Distinguish sort coverage from full query coverage |
| Index has all fields but query uses a different collation | String comparison requires compatible collation | Align query and index collations |
| Partial index omits records when forced | Filter does not entail the partial filter expression | Redesign index/filter; avoid unsafe hints |
| Covered in dev but behaves differently in sharded production | Sharded routing requires the shard key | Run `explain` through `mongos` with real topology |
| Widening compound index slowed down writes | Index grew too wide and expensive to maintain | Prioritize critical read paths and measure total cost |

## 18. Practice Exercises

Use the same `lab.orders` dataset and indexes created in Sections 3–4. No document modifications are needed to complete these exercises.

### Exercise 1 — Basic Covered Query

Given the index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  customerId: 1,
  createdAt: -1
}
~~~

Write a query retrieving `PAID` orders for customer `C01` in tenant `T1`, returning only `customerId` and `createdAt`, without `_id`.

Hint:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01"
  },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Inspect `totalDocsExamined` and verify whether the plan includes `FETCH`.

### Exercise 2 — Default `_id` Field

Remove `_id: 0` from Exercise 1's projection while keeping the same index. Explain why the planner must inspect source documents to return `_id`.

Next, create an index ending with `_id` and use `hint()` to compare. Analyze the cost/benefit trade-off of adding the identifier key to the index.

### Exercise 3 — Projection Requiring an Unindexed Field

Add `totalAmount: 1` to Exercise 1's projection and inspect `explain`.

Questions: Does the data come from the index or source documents? Compare `nReturned` and `totalDocsExamined`. If this screen is queried thousands of times per second, would you consider adding `totalAmount` to the compound index? Why or why not?

### Exercise 4 — Unindexed Filter Predicate

Add the condition:

~~~javascript
totalAmount: { $gt: 140 }
~~~

to the filter while **not returning `totalAmount`**. Explain why the query still needs to read documents to evaluate the filter.

### Exercise 5 — Multikey Index

Create the index:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, tags: 1, status: 1 },
  { name: "ix_tenant_tags_status" }
);
~~~

Run three queries:

~~~javascript
// A: project only scalar field status.
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status");

// B: also project the tags array.
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1, tags: 1 }
).hint("ix_tenant_tags_status");

// C: use $elemMatch on tags.
lab.orders.find(
  { tenantId: "T1", tags: { $elemMatch: { $eq: "web" } } },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status");
~~~

Append `.explain("executionStats")` to each query and identify which case can be covered by the index.

### Exercise 6 — Nested Fields

On `lab.profiles`, create index `{"contact.city": 1, userId: 1}`. Test:

- Returning only `"contact.city"` and `userId`.
- Returning the entire `contact` object.
- Returning `"contact.phone"`.

Explain why the latter two projections must fetch the documents.

### Exercise 7 — Comparing Two Indexes

Create a wider index:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "ix_tenant_status_customer_created_amount" }
);
~~~

For the same query returning `totalAmount`, run `hint()` with the old index and then the new index. Compare plans, keys/docs examined, and note that this is only a **tiny lab**, insufficient to draw production performance conclusions.

### Exercise 8 — Evaluating Your Own Design

A collection holds 10 million orders, each with a long `items` array and a large `internalNote` field. A list view needs only `createdAt`, `status`, `customerId`, and `totalAmount`. The API filters by `tenantId` and `status`, sorting by `createdAt` descending.

Propose a compound index supporting filter, sort, and projection (plus `_id` if returned by the API), then analyze:

1. Should `items` or `internalNote` be included in the index?
2. How does a covered query reduce document read work?
3. When does an index become too wide?
4. If a detail page needs all `items`, should you try to cover the detail page with the same index?
5. Which `explain` outputs and metrics confirm improvement?

## 19. Conclusion

A **covered query** in MongoDB executes purely from an index without reading source documents. To achieve it, **all filters, projections, and execution-required values** must be satisfied by an eligible index, with no `null` equality predicates, while respecting index-type and deployment constraints.

When you see `IXSCAN` in explain output, ask next: **Does MongoDB still execute `FETCH`?** If so, the index still helps filtering or sorting, yet the query is **not covered**. Metrics like `totalDocsExamined`, `totalKeysExamined`, and `nReturned` confirm the actual workload cost.

In system design, build compound indexes around **frequent workloads**: prioritize efficient filtering and sorting first, then consider adding a few projected fields to eliminate `FETCH` only when read savings outweigh the cost of wider indexes and write maintenance.

### Official References

- [Query Optimization — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/) — definitions, coverage conditions, `_id`, null, embedded documents, and sharding.
- [Multikey Indexes — Covered Queries](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — conditions under which multikey indexes can cover queries.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`, `FETCH`, `COLLSCAN`, and execution metrics.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — multi-field index design.
- [Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/) — indexes and sorting.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — result completeness when using partial indexes.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — string comparison rules and index/query collations.
- [Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/) — projection syntax and default `_id` behavior.
