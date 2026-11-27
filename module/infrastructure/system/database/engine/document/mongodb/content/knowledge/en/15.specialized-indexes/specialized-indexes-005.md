# Hashed Indexes and Supported Query Scope

MongoDB provides several index types to optimize different query patterns. A **hashed index** stores a **hash value** of a field instead of storing the raw field values in natural sort order like a standard B-tree index. The primary goals of a hashed index are to support **equality queries** and to serve as the foundation for a **hashed shard key**, distributing monotonically increasing key values across multiple data ranges in sharded deployments.

However, a hashed index **is not a general-purpose index**. Because hashing destroys the natural ordering of the original values, this index is unsuitable for directly serving **range queries**, **sorting by the original field**, or optimizations such as **covered queries**.

This lesson explains the mechanics, syntax, supported query scope, key limitations, compound hashed index design, relationship with sharding, how to inspect query plans, and practical examples for choosing indexes in applications.

## 1. Start with the Question: What Does the Index Store?

Suppose the `events` collection stores user-generated events:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  userId: "user-10042",
  tenantId: "TENANT-A",
  type: "PAGE_VIEW",
  createdAt: ISODate("2026-03-01T08:15:00Z"),
  payload: {
    page: "/catalog",
    device: "mobile"
  }
}
```

With a standard B-tree index:

```javascript
db.events.createIndex({ userId: 1 });
```

MongoDB stores index keys in the comparison order of `userId` values. The index can support suitable operations such as equality lookups, certain range conditions on the same field, and sorting by that field, depending on query shape and the query planner.

With a hashed index:

```javascript
db.events.createIndex({ userId: "hashed" });
```

MongoDB computes a deterministic hash value from `userId` and uses that hash as the index key. Conceptually:

```text
Original value                 Indexed value
----------------------------------------------------
"user-10042"   ----hash--->  h_1 (hash number)
"user-10043"   ----hash--->  h_2
"user-10044"   ----hash--->  h_3

Relationship:
"user-10042" < "user-10043" < "user-10044"

Does not imply:
h_1 < h_2 < h_3
```

The symbols `h_1`, `h_2`, `h_3` are illustrative only, not MongoDB's actual hash output. What matters is that **values close together in original order do not necessarily have hash values close together**.

### 1.1. What Does a Hashed Index Optimize?

Given a specific value like `"user-10042"`, MongoDB can compute its corresponding hash and locate the index key range associated with that value. Hence, **equality lookup against a known value** is the primary use case.

Conversely, for a question like "all `userId` values from `user-10000` to `user-20000`", the original range does not correspond to a contiguous slice of hashes. MongoDB cannot use hash order the way a B-tree uses `userId` order to perform an efficient range scan.

### 1.2. Distinguishing the Index from the Shard Key

A **hashed index** is a collection index structure. A **hashed shard key** is how MongoDB uses hashes of the key field to distribute documents in a **sharded collection**.

The two concepts are related, not identical:

- Creating `db.events.createIndex({ userId: "hashed" })` on an unsharded collection **does not automatically split the collection across multiple shards**.
- Sharding requires a sharded cluster, a shard key, and explicit sharding configuration commands.
- A sharded collection with a hashed shard key uses hash values to define distribution ranges.
- The query planner can use a hashed index for equality lookups even when the collection is **not sharded**.

## 2. Creating and Inspecting a Hashed Index

### 2.1. Creating a Single-Field Hashed Index

```javascript
db.events.createIndex(
  { userId: "hashed" },
  { name: "idx_userId_hashed" }
);
```

The `"hashed"` parameter specifies the index key type, not a string compared against the `userId` field. Do not write `{ userId: 1 }` if your goal is a hashed index; that creates a regular ascending index.

View the index list:

```javascript
db.events.getIndexes();
```

In the metadata, the index has a key pattern like:

```javascript
{
  key: { userId: "hashed" },
  name: "idx_userId_hashed"
}
```

Other metadata fields vary by version and options; the snippet above highlights the core index properties.

### 2.2. A Field Is Hashed Deterministically

Identical values map to the same hash under MongoDB's hashing mechanism. This is the basis for equality lookups.

However, **a hash is not an absolute unique identifier**:

- In principle, distinct values can produce the same hash (a hash collision).
- Certain numeric types also follow normalization rules before hashing.
- Therefore, the server still ensures **exact comparison against the original value** per query semantics; it cannot treat "matching hash" as "guaranteed matching document".

This is also why you should never use a hashed index in place of a **unique index** or assume a hash alone suffices to verify a record's identity.

### 2.3. The Index Does Not Modify Document Contents

Creating a hashed index does not turn:

```javascript
{ userId: "user-10042" }
```

into a document whose `userId` field contains a hash number. The field stored in BSON retains its original value. The hash is maintained in the **index structure** to serve eligible operations.

If you want to store an actual `"hashedUserId"` field inside the document, that is an application-level decision and is **separate** from creating a hashed index. Do not add a manual business hash field merely to mimic MongoDB's internal index without a concrete reason.

## 3. Query Scope: Equality Is the Primary Case

### 3.1. Equality Operators

Equality query:

```javascript
db.events.find({
  userId: "user-10042"
});
```

Or written explicitly with `$eq`:

```javascript
db.events.find({
  userId: { $eq: "user-10042" }
});
```

Both forms express an equality condition on `userId`. With a suitable hashed index and a sufficiently large collection, the query planner **can** use the index to locate records matching the hash of that value.

Do not claim "having a hashed index guarantees the query uses it": MongoDB selects a query plan based on data distribution, selectivity, collection size, and other indexes. On a very small collection, a collection scan may be cheaper.

### 3.2. Querying Multiple Specific Values with `$in`

```javascript
db.events.find({
  userId: {
    $in: ["user-10042", "user-10043", "user-10044"]
  }
});
```

`$in` means matching any one of several values. Because each item in the list is an equality match, a hashed index can be considered to serve those values.

However:

- A very long `$in` list can trigger many lookups and significant planning/execution overhead.
- The index does not guarantee returned documents follow the order of elements in the `$in` array.
- If you need results sorted by timestamp, name, or `userId`, specify `sort()` and evaluate the corresponding index.
- If the stored field has a different BSON type than the query literal, equality will not match.

Example:

```javascript
db.events.find({
  userId: { $in: ["user-10042", "user-10043"] }
})
.sort({ createdAt: -1, _id: -1 })
.limit(50);
```

A hashed index on `userId` can assist the filter condition, yet **does not automatically support sorting by `createdAt`**. Another index or an in-memory sort stage may be needed depending on the query plan.

### 3.3. Combining with Predicates on Other Fields

```javascript
db.events.find({
  userId: "user-10042",
  type: "PURCHASE"
});
```

A single-field hashed index can locate a user's records and then filter `type` on matching documents. Yet if each user has millions of events, indexing only `userId` may still scan a large number of records before filtering `type`.

Consider a compound index when such combined queries run frequently; base the decision on workload, not merely because "a hashed index already exists".

### 3.4. Operators Not Optimized by a Hashed Index

| Query on the Hashed Field | Is a Hashed Index Suitable? | Reason |
|---|---|---|
| `{ userId: "u42" }` | **Suitable** for equality | Computes hash of one specific value |
| `{ userId: { $eq: "u42" } }` | **Suitable** | Explicit equality |
| `{ userId: { $in: ["u1", "u2"] } }` | **Can be suitable** | Multiple equality lookups |
| `{ userId: { $gt: "u100" } }` | **Unsuitable for range scan on hashed field** | Hash does not preserve string order |
| `{ userId: { $gte: "u100", $lt: "u200" } }` | **Unsuitable** | Original interval is non-contiguous in hash space |
| `{ userId: { $ne: "u42" } }` | Usually inefficient | Condition spans almost the entire value domain |
| `{ userId: { $nin: [...] } }` | Usually inefficient | Not a selective positive equality set |
| `{ userId: /^user-10/ }` | **Does not support string prefix range** | Hashing loses prefix relationships |
| `sort({ userId: 1 })` | **Cannot use hash to return original `userId` order** | Hash order differs from string order |
| Projection solely from hashed index | **Cannot cover queries with a hashed index** | Index holds hashes rather than original values |

This table addresses whether **hashed keys can optimize the predicate**. MongoDB can still **execute** range, regex, sort, or `$ne` queries via a collection scan or another index. Saying "hashed indexes do not support range queries" **does not mean MongoDB forbids writing range queries**.

## 4. Why Do Hashed Indexes Not Support Range Queries?

A standard B-tree index on numbers maintains order:

```text
Indexed original values:
10, 11, 12, 13, 14, 15, 16, 17, 18, 19

Query score >= 12 and score < 18:
              [12, 13, 14, 15, 16, 17]
```

The index can seek to `12` and scan sequentially up to just before `18`.

With a hashed index:

```text
Original: 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
Hash:     h7, h2, h9, h1, h5, h0, h8, h3, h6, h4

Hash order:
h0, h1, h2, h3, h4, h5, h6, h7, h8, h9
```

Each value in `[12, 18)` can land at an unrelated hash position. There is no contiguous index slice corresponding to that numeric interval. Therefore, a hashed index is not the structure to accelerate queries like:

```javascript
db.metrics.find({
  score: { $gte: 50, $lt: 100 }
});
```

If `score` has a hashed index while the application primarily runs range queries, create an appropriate **standard B-tree index**:

```javascript
db.metrics.createIndex({ score: 1 });
```

### 4.1. Range Combined with Equality Still Depends on Which Key Has the Range

A query:

```javascript
db.events.find({
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

Here:

- `userId` uses **equality**: suitable for hashed lookup.
- `createdAt` filters by a **Date range**: requires an ordered B-tree key on Date to optimize the range.

A **single-field** hashed index `{ userId: "hashed" }` does not assist the range scan on `createdAt`. However, that does not prevent a **compound hashed index** containing a regular Date field, covered in a later section.

### 4.2. Regex and Prefixes Do Not Translate to Hash Ranges

A string B-tree index can sometimes accelerate anchored prefix regexes, depending on collation and pattern:

```javascript
db.users.find({
  username: /^nguyen/
});
```

A hashed index on `username`, however, does not store usernames starting with `nguyen` adjacent to one another. When an application frequently runs prefix lookups, autocomplete, or alphabetical sorting, evaluate B-tree, text, or search indexes suited to those query semantics—do not choose hashing just because the field is a string.

## 5. Hashed Indexes and Sort: Original Order Is Not Preserved

The command:

```javascript
db.events.find({})
  .sort({ userId: 1 })
  .limit(20);
```

requests results in the comparison order of the **original `userId`**, not hash order. A hashed index cannot act like an ascending B-tree index on `userId`.

Similarly:

```javascript
db.events.find({ userId: "user-10042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Hashed lookup helps filter by `userId`, yet if a single user has many documents, MongoDB still has to sort or use another index supporting `createdAt` order. A standard B-tree index may fit better:

```javascript
db.events.createIndex({
  userId: 1,
  createdAt: -1,
  _id: -1
});
```

This index supports equality on `userId` and then reads events in timestamp order within that key range. It can serve both **user filtering** and **time sorting**, rather than optimizing hash equality alone.

### 5.1. Do Not Confuse Query Order with Shard Distribution

Hashed sharding can distribute monotonically increasing keys across multiple shards to avoid piling inserts onto the upper range of a single shard. **That does not make query results sorted.** Sharded queries requiring deterministic ordering still need `sort()`, the query planner, and supporting indexes.

### 5.2. Can You Have Both a Hashed Index and a B-Tree Index?

You can maintain both if distinct workloads justify the overhead:

```javascript
db.events.createIndex(
  { userId: "hashed" },
  { name: "userId_hashed" }
);

db.events.createIndex(
  { userId: 1, createdAt: -1 },
  { name: "userId_createdAt_desc" }
);
```

However, every index consumes memory/disk and adds insert/update/delete overhead. If you are not sharding and most queries are equality plus sort/range on another field, a compound B-tree index may suffice **without** needing a separate hashed index. Keep both only when measurements justify it or when the hashed index is required for sharding.

## 6. Covered Queries: A Hashed Index Cannot Return Original Values from Hashes

A **covered query** is a query satisfied entirely from the index for both filtering and projected output fields without reading documents in a `FETCH` stage (subject to specific rules and restrictions).

Example B-tree index:

```javascript
db.users.createIndex({
  tenantId: 1,
  username: 1
});
```

Query:

```javascript
db.users.find(
  { tenantId: "TENANT-A" },
  { _id: 0, username: 1 }
);
```

Under eligible conditions, the index provides the original `username` and filters by tenant, yielding a covered query.

With a hashed index:

```javascript
db.users.createIndex({
  username: "hashed"
});
```

The index stores **hash(username)**, not the raw `username`. It cannot return the original `username` by reversing the hash—hashing is not reversible encryption. MongoDB **does not use hashed indexes to cover queries**.

Example:

```javascript
db.users.find(
  { username: "nguyen.an" },
  { username: 1, _id: 0 }
);
```

Even when the query uses the hashed index to locate candidates, the engine still must inspect the document to retrieve or verify original field values per query semantics. Never infer that "returning only one field" makes a hashed index cover a query.

This also relates to hash collisions: the hash narrows down candidates, while true equality must be verified against the original value.

## 7. Data Type Rules for Hashed Fields

### 7.1. Do Not Use Array Fields

**Hashed indexes do not support multikey hashing on arrays** the way standard multikey indexes work. Do not create a hashed index on a field that can hold an array:

```javascript
{
  _id: 1,
  tags: ["mongodb", "database", "backend"]
}
```

To find documents where a tag equals `"mongodb"`, use a B-tree multikey index:

```javascript
db.articles.createIndex({ tags: 1 });

db.articles.find({ tags: "mongodb" });
```

When creating a hashed index on a field containing arrays, or inserting/updating an array into a field covered by a hashed index, MongoDB can reject the operation due to hashed multikey restrictions. For compound hashed indexes, also verify multikey limitations in your deployed version; avoid indexing fields that might become arrays without checking.

### 7.2. Hashing Rules for Numeric Types

A common surprise: when hashing **floating-point** values, MongoDB truncates or converts values to 64-bit integers before hashing under its numeric hashing rules. This can cause **distinct numeric values to share the same hash**.

Conceptual example:

```javascript
db.scores.insertMany([
  { _id: "S1", score: 2.1 },
  { _id: "S2", score: 2.8 },
  { _id: "S3", score: 3.2 }
]);

db.scores.createIndex({ score: "hashed" });
```

The values `2.1` and `2.8` can collapse to the same integer portion during hashing, so never assume distinct decimal numbers always produce distinct hash keys.

**Crucial point:** the query `{ score: 2.1 }` will not erroneously return `2.8`. MongoDB still evaluates the predicate against the original value. Hashed indexes are not used to enforce uniqueness; for numeric range comparisons, a B-tree index is far more suitable.

If numeric fields are huge, use `Decimal128`, `Double`, `Int64`, or mixed types, understand the exact hashing behavior of your MongoDB version before choosing the field as a hashed shard key. Avoid floating-point fields as shard keys if business logic expects fractional differences to distribute as completely separate keys.

### 7.3. Null, Missing Fields, and Inconsistent Schemas

A collection might contain:

```javascript
{ _id: "A", userId: "user-10042" }
{ _id: "B", userId: null }
{ _id: "C" }
```

In MongoDB, `{ userId: null }` normally matches both `null` values and missing fields. Creating and using a hashed index does not change null/missing query semantics.

If the hashed field is a shard key, missing/null rules also affect routing and shard distribution; standardize your schema and check sharding rules. For user or customer IDs, generally require **valid, consistently typed, high-cardinality values** rather than leaving many documents with null keys.

### 7.4. Hashing Does Not Replace Security Encryption

A hashed index **is not a data-masking or confidentiality tool**. Documents still store the original value, the index holds hashes for lookups, and field-level access depends on authentication, authorization, encryption, and security policies.

Never store plaintext passwords, add a hashed index, and assume the passwords are protected. Passwords must be processed using dedicated password-hashing algorithms (salted, with a work factor), never a MongoDB hashed index.

## 8. Unique Indexes: You Cannot Set `unique` on a Hashed Index

A common question: "Every `userId` must appear only once—can we use a hashed index with `unique: true`?"

**No.** Hashed indexes do not support uniqueness constraints the way unique B-tree indexes do. Do not use:

```javascript
// Not a valid design for enforcing uniqueness.
db.users.createIndex(
  { username: "hashed" },
  { unique: true }
);
```

To enforce unique usernames, use a B-tree unique index:

```javascript
db.users.createIndex(
  { username: 1 },
  { unique: true }
);
```

If the system must enforce uniqueness per tenant:

```javascript
db.users.createIndex(
  { tenantId: 1, username: 1 },
  { unique: true }
);
```

In the application, handle duplicate-key errors when two concurrent requests create the same username; "find first, then insert" does not replace a database unique constraint.

### 8.1. What If the Collection Uses a Hashed Shard Key?

In a sharded collection, MongoDB enforces constraints between unique indexes and the shard key. Adding a B-tree unique index **cannot by default be assumed to enforce cluster-wide uniqueness** if its key pattern is incompatible with the shard key under your MongoDB version's rules.

For instance, a hashed shard key on `userId` helps distribute data, yet does not mean cluster-wide uniqueness of `username` can be enforced merely by adding `{ username: 1 }`. Your architecture must define uniqueness boundaries per tenant/shard, at the application layer, or via a separate registry collection if needed.

**Choosing a hashed shard key and choosing a unique constraint are two separate decisions**; verify their compatibility before deployment.

### 8.2. Collision Is Not Duplicate Key

Even when two different values yield the same hash, a hashed index cannot be used to conclude they are the same business value. A standard unique index compares keys per index/collation semantics; a hashed index only guides candidate lookup.

## 9. Compound Hashed Indexes: Combining a Hash with Ordered Keys

MongoDB supports **compound hashed indexes** in versions offering this feature. A compound hashed index combines **one hashed field** with fields using standard B-tree ordering.

Example:

```javascript
db.events.createIndex(
  {
    tenantId: 1,
    userId: "hashed",
    createdAt: -1
  },
  {
    name: "tenant_userHash_createdAt"
  }
);
```

Interpretation:

1. `tenantId: 1` is a standard ordered key leading the index.
2. `userId: "hashed"` stores the hash of `userId`.
3. `createdAt: -1` is a descending Date field **within a matching prefix key region**.

There may be **at most one hashed field** in a compound hashed index; do not treat it as hashing the entire document or hashing every field in the key pattern.

### 9.1. Equality Query Followed by Range on a Standard Field

For the query:

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(100);
```

Structurally, the index can leverage:

- Equality on `tenantId` in the prefix.
- Equality on `userId` via hash in the next field.
- Range and sort on `createdAt` on the trailing B-tree field, once the prefix fields are bound by appropriate equality predicates.

Thus, a **compound hashed index can participate in queries containing a range**, provided the range is on **another B-tree field**, not on the hashed field itself.

Distinguish these two statements:

- "A hashed key does not provide range ordering for the original value" — true.
- "Any compound index containing a hashed field cannot be used for any range query at all" — overly broad and wrong.

### 9.2. Query with Only `tenantId`

```javascript
db.events.find({
  tenantId: "TENANT-A"
});
```

Because `tenantId` leads the index, the query can leverage the index prefix depending on the planner and selectivity. However, if Tenant A accounts for most of the collection, the planner may pick another plan.

### 9.3. Query with Only `userId`

```javascript
db.events.find({
  userId: "user-10042"
});
```

If the compound index starts with `tenantId`, a query not constraining `tenantId` may not effectively use the prefix structure. Do not assume `{ tenantId: 1, userId: "hashed" }` completely replaces `{ userId: "hashed" }` for all `userId`-only queries.

If the application always has `tenantId` from the authenticated context, including `tenantId` in the query is usually sound and prevents cross-tenant reads. If users need to look up a user across all tenants, that is a different workload and may need another index.

### 9.4. Ranges on `userId` Itself Are Still Unsupported by Hashing

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: { $gte: "user-10000", $lt: "user-20000" }
});
```

The index in Section 9 lacks original `userId` ordering; the hashed field cannot provide a contiguous lexicographical/numeric slice of `userId`. If this query runs often, use a standard B-tree compound index:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: 1
});
```

### 9.5. Position of the Hashed Field Affects Query Shapes

Compare:

```javascript
// A: usually advantageous when every query filters by tenantId.
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});

// B: hashed userId leads, targeting userId-centric workloads.
db.events.createIndex({
  userId: "hashed",
  createdAt: -1
});
```

The two indexes lead with different fields and therefore serve different scopes. Choose based on real queries and sharding rules if the index also backs a shard key. Adding more fields to a compound index does not automatically improve every query: wider indexes consume more storage and write maintenance.

## 10. Hashed Shard Keys: Distributing Monotonically Increasing Values

Hashed sharding is a flagship use case. Suppose a collection has an `_id` key with monotonically increasing values:

```text
1, 2, 3, 4, 5, 6, ...
```

With direct range-based sharding on an increasing key, new inserts can concentrate on the trailing key range and cause a **hot shard** if distribution is skewed.

A hashed shard key hashes each value before mapping it to a shard-key range:

```text
_id 1000001 -> hash H1 -> shard region A
_id 1000002 -> hash H2 -> shard region C
_id 1000003 -> hash H3 -> shard region B
...
```

Values increasing consecutively in the original domain are spread more evenly across the hash domain. This can **distribute write load** much better when there are many distinct shard key values.

### 10.1. Conceptual Configuration Example on a Sharded Cluster

Execute only inside an already configured **sharded cluster**, with admin privileges and an approved shard key plan:

```javascript
// Example namespace app.events, run through mongos.
use app;

// Create the corresponding hashed index if needed.
db.events.createIndex({ userId: "hashed" });

// Shard the collection by hashed userId.
sh.shardCollection("app.events", { userId: "hashed" });
```

Exact syntax and preconditions depend on MongoDB version and deployment setup. Sharding also requires assessing cardinality, value distribution, missing/null values, document volume, query routing, chunk migrations, and unique index constraints; never run sample commands in production merely because a hashed index exists.

### 10.2. Equality Queries on the Shard Key Gain Routing Advantages

If the shard key is `{ userId: "hashed" }`, an exact equality query:

```javascript
db.events.find({ userId: "user-10042" });
```

can generally **target** the shard holding the corresponding hash value (per current routing metadata), instead of broadcasting the query to every shard.

Conversely, a query:

```javascript
db.events.find({
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
});
```

lacks the shard key and may have to **scatter-gather** across multiple shards. A range predicate on the original shard key itself likewise does not map to a contiguous hash interval.

Shard key selection is not just about write distribution. If most queries filter by tenant, time, and status, a shard key absent from those queries can make most read load expensive.

### 10.3. Hashed Sharding Does Not Solve a Single Hot Key

Suppose one celebrity user generates thousands of events per second and every document has:

```javascript
{ userId: "celebrity-1" }
```

The hash of `"celebrity-1"` is **one fixed value**. All documents sharing that shard key value route to the exact same sharding key range. Adding more shards will not split a single `userId` value automatically.

Distinguish:

- **Monotonic hot range:** many distinct key values increasing toward the tail of the domain — hashed sharding can help distribute them.
- **Hot key:** a single key value receiving nearly all traffic — its hash is still one single value.

For a true hot key, consider extra partitioning in the data model (such as bucketing or suffixes), a suitable compound shard key, or event-stream splitting. Every workaround impacts reads and uniqueness; do not simply append random numbers to keys while ignoring how user reads work.

### 10.4. Original Range Locality Is Lost

Hashing scatters adjacent values. If a workload frequently asks:

```javascript
db.orders.find({
  orderNo: { $gte: 100000, $lt: 101000 }
});
```

a range on `orderNo` can span many shards when `orderNo` is a hashed shard key. This is the core trade-off: **more even insert distribution** in exchange for **lower range locality**.

Before selecting a hashed shard key, know whether most queries perform equality or range predicates on the shard key. If range scans dominate, range-based sharding or a different key design may fit better.

## 11. Can a Hashed Index Support Sorting on Another Field?

A subtle question: "We said hashed indexes do not support sorting—so can a compound hashed index ending in `createdAt: -1` support sorting?"

Separate two facts:

1. A hashed key **does not preserve original ordering** for the hashed field itself.
2. Within a compound index, **standard B-tree fields** still preserve order inside a matching key prefix.

Example:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});
```

When querying equality on both `tenantId` and `userId`, matching records within that prefix range can be retrieved in descending `createdAt` order via the B-tree portion of the index.

```javascript
db.events.find({
  tenantId: "TENANT-A",
  userId: "user-10042"
})
.sort({ createdAt: -1 })
.limit(20);
```

Actual index usage must still be verified with `explain()`. Never generalize this into "a hashed index can sort by the original `userId`": that remains false.

For a query binding `tenantId` without binding `userId`, overall index key order is still grouped by **hash(userId)** before `createdAt`, so the index does not yield a single tenant-wide list globally sorted descending by `createdAt`.

This is precisely why **field order in a compound index** matters.

## 12. Checking `explain()` to See Which Index Is Actually Used

Never guess index usage from index names or merely because an index was created. Use `explain("executionStats")` to inspect the query plan.

### 12.1. Equality Query

```javascript
db.events.find({
  userId: "user-10042"
}).explain("executionStats");
```

When the planner selects the hashed index, the plan includes the corresponding index access stage; exact stage shapes can vary across versions and query engines.

Useful fields:

| Field or Stage | Meaning |
|---|---|
| `winningPlan` | Chosen execution plan |
| `IXSCAN` | Index scan stage |
| `FETCH` | Needs to fetch documents or verify exact matches |
| `COLLSCAN` | Collection scan |
| `SORT` | Additional in-memory sort stage |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of returned documents |
| `executionTimeMillis` | Execution time reported by explain |

You will see `FETCH` even when the hashed index helps filtering, because the index stores hashes rather than original values and hashed indexes cannot cover queries.

### 12.2. Comparing Against a Range Query

```javascript
db.events.find({
  userId: {
    $gte: "user-10000",
    $lt: "user-20000"
  }
}).explain("executionStats");
```

Do not expect a hashed index on `userId` to provide an ordered range scan over original `userId` strings. MongoDB may choose a collection scan or another B-tree index. If this query is frequent, compare plans with a `{ userId: 1 }` index in a test environment.

### 12.3. Comparing Sort Queries

```javascript
db.events.find({
  userId: "user-10042"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

With only a single-field hashed index, the engine may need an extra sort stage for `createdAt`. With an appropriate compound B-tree or compound hashed index, the plan can change. Never benchmark once on a few dozen records; test with data volumes and distributions representative of production workloads.

### 12.4. Using `hint()` Carefully

To study index behavior in a test environment, you can use `hint()`:

```javascript
db.events.find({
  userId: "user-10042"
})
.hint("idx_userId_hashed")
.explain("executionStats");
```

`hint()` forces a specific index to be considered per API semantics; it **does not turn a hashed index into one supporting original range scans or sorts**. Do not hardcode `hint()` into production code based on a tiny test, as data distributions and query plans evolve.

## 13. Designing Indexes by Workload Rather Than Field Names

Suppose a collection has three query groups:

**Group A — find a user's events by ID:**

```javascript
db.events.find({ userId: "user-10042" });
```

**Group B — fetch a user's timeline history:**

```javascript
db.events.find({
  userId: "user-10042",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z")
  }
})
.sort({ createdAt: -1 })
.limit(100);
```

**Group C — analyze system-wide events over a time window:**

```javascript
db.events.find({
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

Candidate choices:

| Workload | Candidate Index | Explanation |
|---|---|---|
| A: equality `userId` | `{ userId: "hashed" }` or `{ userId: 1 }` | Both support equality; hashed makes more sense when paired with a sharding strategy |
| B: equality `userId` + Date range/sort | `{ userId: 1, createdAt: -1 }` | Compound B-tree directly serves equality + Date ordering |
| B on collection needing hashed field | `{ userId: "hashed", createdAt: -1 }` | Hash equality in prefix, ordered Date trailing |
| C: collection-wide Date range | `{ createdAt: 1 }` | Time-ordered range scan |
| Prefix `username` | `{ username: 1 }` or specialized search index | Hashing does not preserve string prefixes |
| Unique `username` | `{ username: 1 }` with `unique: true` | Hashed indexes cannot be unique |
| Hashed shard key distributing user events | `{ userId: "hashed" }` backing shard key | Trades off locality; watch out for hot `userId` |
| Tenant-wide sort by `createdAt` | `{ tenantId: 1, createdAt: -1, _id: -1 }` | Avoid placing an unbound hashed field in between |

Do not blindly create every candidate index: each index increases write cost, cache footprint, and storage. Index design is a trade-off among **query frequency, selectivity, data volume, shard distribution, index size, and write amplification**.

### 13.1. A Hashed Index Can Be Redundant for Equality on Small Collections

If a collection has a few thousand users and the main query is:

```javascript
db.users.findOne({ emailNormalized: "a@example.com" });
```

a B-tree index `{ emailNormalized: 1 }` likely already performs well while also enabling uniqueness and some range/sort operations. Adding a hashed index does not automatically make equality lookups faster.

Hashing is not a magic accelerator for all equality checks. It shines primarily in **key distribution architectures** or specific index designs verified by measurement.

### 13.2. Low-Cardinality Fields Do Not Distribute Well

A hashed shard key such as `status` with only three values:

```javascript
{ status: "NEW" }
{ status: "PAID" }
{ status: "CANCELLED" }
```

produces only a tiny number of distinct hash values. Millions of documents sharing a status still clump onto those few key values; hashed sharding does not magically turn three states into millions of independent partitions. Prefer shard keys with **high cardinality** and balanced write distribution.

### 13.3. Do Not Pick a Frequently Mutated Field as a Shard Key Without Understanding Consequences

Fields inside a shard key heavily impact routing and data placement. A frequently changing field can introduce complex business and operational costs when key updates happen; never pick a hashed shard key merely because an existing field sees heavy writes. Understand stability, cardinality, shard key update rules, and your deployed server version's limitations.

## 14. Java MongoDB Driver Application Example

In the Java Sync Driver, you can create a hashed index using the `Indexes.hashed()` builder.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoDatabase database = mongoClient.getDatabase("app");
MongoCollection<Document> events = database.getCollection("events");

// Hashed index on userId.
String indexName = events.createIndex(Indexes.hashed("userId"));
System.out.println(indexName);
```

Equality query:

```java
import com.mongodb.client.model.Filters;

for (Document event : events.find(
        Filters.eq("userId", "user-10042"))) {
    System.out.println(event.toJson());
}
```

Time-range query with sort:

```java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Sorts.descending;

import java.util.Date;

Date from = new Date(1772323200000L);

for (Document event : events.find(
        and(
            eq("userId", "user-10042"),
            gte("createdAt", from)
        ))
        .sort(descending("createdAt"))
        .limit(50)) {
    System.out.println(event.toJson());
}
```

This snippet illustrates driver calls; it does **not** claim a single-field hashed index automatically supports sorting by `createdAt`. To control query plans, create indexes matched to workloads and inspect them via driver monitoring or `mongosh` `explain()`.

With Spring Data MongoDB, indexes can be created via the corresponding index-operations APIs in your version. Manage indexes through controlled migrations/deployments rather than necessarily re-creating indexes on every application startup.

## 15. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "A hashed index stores sorted `userId` values." | It stores value hashes and does not preserve original order. |
| "With a hashed index, all query conditions are fast." | Primarily useful for equality; range/sort on the hashed field cannot use original ordering. |
| "No range support means `$gte` queries are forbidden." | The query is still valid, though it needs another index or scan to run efficiently. |
| "`$in` is a range query." | `$in` is a set of equality matches and can be served by a hashed index. |
| "A hashed index automatically sorts `userId` alphabetically." | No; `sort({ userId: 1 })` requires original string ordering. |
| "A hashed index covers queries returning only one field." | No; hashes do not contain the original values needed to cover queries. |
| "You can set `unique: true` on a hashed index." | Hashed indexes do not support unique constraints like B-tree unique indexes. |
| "Distinct Double numbers always produce distinct hashes." | Pre-hash numeric conversion rules can produce identical hashes. |
| "Hashed indexes support `tags` arrays as multikey." | No; hashed indexes do not support multikey hashing on arrays. |
| "Creating a hashed index means the collection is sharded." | No; sharding requires a sharded cluster and shard key configuration. |
| "A hashed shard key solves a single hot user." | One `userId` still yields one hash; a hot key does not distribute automatically. |
| "Hashing sequential `_id` keeps nearby IDs close together." | Hashing destroys original range locality. |
| "A compound hashed index cannot support any range query." | Ranges can be supported on other B-tree fields when prefix fields match; just not on the hashed field itself. |
| "Every indexed query should use `hint()`." | The planner may pick a better index; `hint()` requires benchmarking and care. |

## 16. Evaluation Workflow Before Choosing a Hashed Index

A practical design process should start from **query shapes** rather than a desired index type.

**Step 1 — Inventory queries.** Document filters, sorts, projections, limits, and frequencies for critical endpoints and batch jobs. Examples: user lookup by ID, paginated user timeline, system-wide date-range analytics.

**Step 2 — Identify operator types on the candidate hashed field.** If `$eq`/`$in` dominate, a hashed index may fit. If `$gte`, `$lt`, prefix regex, sorting, or uniqueness dominate, a B-tree or other specialized index is usually needed.

**Step 3 — Assess data characteristics.** Can the field be an array? Are there null/missing values? Are there floating-point numbers or mixed BSON numeric types? Is the field mutated after insert? For a hashed shard key, are cardinality and distribution high enough?

**Step 4 — Decide standalone vs. compound.** If queries need `tenantId`, `userId` equality, and timestamps, consider field order in a compound index. If queries filter only by `userId`, a leading prefix field can make the index unsuitable.

**Step 5 — Determine whether sharding is involved.** If you only need equality lookups, B-tree may already suffice. If the goal is spreading monotonically increasing shard key values, evaluate hashed sharding and its read-routing/uniqueness implications.

**Step 6 — Measure with representative data.** Run `explain("executionStats")`, inspect keys/docs examined, p95 latency, index size, insert/update throughput, and load distribution.

**Step 7 — Roll out safely.** Create indexes via migrations, watch index build impact, monitor post-rollout query plans, and retain a rollback plan. Never drop existing indexes solely because a new hashed index was added.

## 17. Practice Exercises

### Exercise 1 — Equality and Range on the Same Field

Create a `hashedLab` collection with 10,000 documents having string `userId` and BSON Date `createdAt`.

1. Create `db.hashedLab.createIndex({ userId: "hashed" })`.
2. Run `explain("executionStats")` for `{ userId: "user-42" }`.
3. Run explain for `{ userId: { $gte: "user-100", $lt: "user-200" } }`.
4. Create a B-tree index `{ userId: 1 }` in the test environment and compare query plans.
5. Explain why hash equality does not provide a contiguous range slice in original string order.

### Exercise 2 — Sorting After a Hashed Lookup

For a user with many events, write a query fetching the 20 most recent events.

1. Start with the single-field hashed index `{ userId: "hashed" }`.
2. Observe the sort stage when running `sort({ createdAt: -1 })`.
3. Create `{ userId: 1, createdAt: -1 }` and compare plans.
4. Also design a compound hashed version if architectural rules require a hashed field, and explain the equality prefix condition.

### Exercise 3 — Numeric Hashing

Insert records with floating-point `score` values `2.1`, `2.8`, and `3.2`. Create a hashed index on `score`, run an equality query `score: 2.1`, and verify that the result does not return every document sharing the hash. Explain why the index cannot act as a unique index for scores.

### Exercise 4 — Compound Hashed Index

Create:

```javascript
db.events.createIndex({
  tenantId: 1,
  userId: "hashed",
  createdAt: -1
});
```

Evaluate four queries:

1. Equality on both `tenantId` and `userId`.
2. Equality on both plus a range on `createdAt`.
3. Equality on `userId` only, without `tenantId`.
4. Equality on `tenantId` and a range on raw `userId`.

Which queries align with the index structure? Which require a different B-tree index? Why does key order matter?

### Exercise 5 — Hashed Sharding with Sequential IDs

Suppose one million orders are created every minute with monotonically increasing `orderNo`. Analyze the risk of a hot shard when range-sharding directly on `orderNo` and why a hashed shard key can improve write distribution.

Then evaluate the query `orderNo >= 500000 and orderNo < 600000`: what trade-off does hashed sharding introduce? If all requests update one single `orderNo`, does hashing solve that hot key?

### Exercise 6 — Uniqueness on a Sharded Collection

An application stores accounts with `tenantId` and `username`. Usernames must be unique within each tenant, while the data is sharded on a hashed key.

1. Explain why a hashed index is not a unique index.
2. Sketch the B-tree unique index required by business rules.
3. Explain why you must verify unique index constraints against the shard key/topology before deployment.
4. Describe how to handle duplicate-key errors when two requests create the same username.

### Exercise 7 — Choosing Indexes by API

An application exposes:

- API A: look up by `deviceId`.
- API B: find `deviceId` values starting with `sensor-2026`.
- API C: view a single device's telemetry over a `measuredAt` range.
- API D: view system-wide telemetry over the last 24 hours.

Select candidate indexes for each API and state when a hashed shard key on `deviceId` might make sense. Do not conclude that a single-field hashed index suffices for all four APIs.

## 18. MongoDB References

- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Compound Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/create/)
- [Create Indexes](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [Query Plans and Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Sharding](https://www.mongodb.com/docs/manual/sharding/)

## Conclusion

A **hashed index** stores the hash of a field's value, making it well suited for **equality lookups** and foundational to **hashed shard keys**. Adjacent values in original order scatter across hash space, helping distribute monotonically increasing keys across shards while giving up **range locality**.

The most important supported-scope rule to remember: **`$eq` and multiple equality values via `$in` can leverage a hashed index; range queries, prefix regexes, and sorting in original field order are not served by hash order**. Hashed indexes also cannot cover queries, do not support multikey indexing on arrays, and do not enforce uniqueness. A compound hashed index can combine equality on a hashed field with range/sort on **other B-tree fields** when prefix predicates align.

Finally, **an index is not sharding**, and **hashed sharding does not fix a single hot key**. Choose hashed indexes based on distribution goals and query shapes, use B-tree indexes when ranges, sorts, or uniqueness are needed, and verify with `explain()` against representative workloads before deploying.
