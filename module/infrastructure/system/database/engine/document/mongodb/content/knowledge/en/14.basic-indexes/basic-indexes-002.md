# Default _id Index and Managing createIndex, getIndexes, and dropIndex in MongoDB

## 1. Why Are Indexes Needed in MongoDB?

A MongoDB collection can contain millions of BSON documents. Suppose an application has a **customers** collection and needs to look up a customer by ID:

~~~javascript
db.customers.findOne({ _id: ObjectId("64b000000000000000000001") });
~~~

Without a suitable access structure, the database may have to scan many documents to find a single record. An **index** provides a data structure organized by search keys so MongoDB can locate matching documents more efficiently.

In MongoDB, standard indexes are based on a **B-tree**-like structure. Each index maintains keys derived from one or more document fields along with references to the corresponding documents. The query planner can use indexes to locate data, sort results, or serve certain queries directly from data already contained in the index.

However, indexes are not free:

- They consume **storage space** and can occupy cache memory.
- Every relevant **insert/update/delete** must maintain index data.
- Building indexes on large collections consumes time and system resources.
- An index mismatched with query shapes may go unused while still increasing write overhead.

MongoDB automatically creates a special index on the **_id** field for standard collections. Other indexes are chosen by developers or operators based on how the application accesses data.

### 1.1. Three Basic Index Management Operations

| Command | Question answered | Effect |
|---|---|---|
| **createIndex()** | Which fields and options should be indexed? | Creates an index if valid and no equivalent definition already exists. |
| **getIndexes()** | Which indexes currently exist on the collection? | Lists the created index specifications. |
| **dropIndex()** | Want to remove an index that is no longer needed? | Drops the specified index, except protected MongoDB indexes like **_id_**. |

Here is the basic lifecycle:

~~~text
               MongoDB Collection
                       |
            Default _id index
                       |
               Measure access patterns
                       |
               createIndex(...)
                       |
               getIndexes(...)
                       |
              explain(...) + load testing
                       |
          +------------+-------------+
          |                          |
      Useful index              Redundant index
          |                          |
        Keep               Consider hide/testing
                                     |
                                dropIndex(...)
~~~

## 2. Default Index on _id

### 2.1. _id Is the Document's Identity

Every document in a standard collection has an **_id** field used as its identifier. For example:

~~~javascript
{
  _id: ObjectId("64b000000000000000000001"),
  customerCode: "CUST-001",
  fullName: "Nguyen Van A",
  status: "ACTIVE"
}
~~~

MongoDB creates a **unique index** on **_id** when a standard collection is created:

~~~javascript
{
  key: { _id: 1 },
  name: "_id_",
  unique: true
}
~~~

This is an abbreviated representation of an index specification. Actual output from **getIndexes()** may also include a **v** field and other metadata depending on the MongoDB version.

Key properties:

1. **Available by default:** you do not need to call **createIndex({ _id: 1 })** to optimize queries by **_id** on standard collections.
2. **Unique:** prevents two documents within the enforced uniqueness scope from having the same **_id** value.
3. **Required:** in standard collections, the **_id_** index cannot be dropped.
4. **_id is largely immutable:** an application cannot change the **_id** value of an existing stored document using a normal update.
5. **BSON types other than ObjectId are allowed:** **_id** does not have to be an ObjectId, provided the value is valid and follows MongoDB rules.

**Point of caution:** for **sharded collections**, the **_id** index has specific limitations regarding cluster-wide uniqueness when **_id** is not the shard key. This lesson clarifies that later; never assume _id uniqueness is always enforced cluster-wide across every sharding configuration.

### 2.2. MongoDB Generates _id When the Application Does Not Supply One

In **mongosh**:

~~~javascript
use index_basics_lab

db.customers.insertOne({
  customerCode: "CUST-001",
  fullName: "Nguyen Van A",
  status: "ACTIVE"
});
~~~

If **_id** is omitted, the MongoDB driver/mongosh typically generates an **ObjectId** value for the document before sending it or during the corresponding insert processing. The result may look like:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("...")
}
~~~

**ObjectId** is a BSON type commonly used to generate identifiers with an extremely low collision probability. It is not a mathematical guarantee against collisions, nor is it a substitute for business keys across every domain. The **unique index on _id** is what enforces rejection of duplicates at the database level within its supported scope.

### 2.3. Can _id Be a String or Number?

You can define application-supplied IDs:

~~~javascript
db.customers.insertOne({
  _id: "CUS-HN-001",
  customerCode: "CUST-002",
  fullName: "Tran Thi B",
  status: "ACTIVE"
});
~~~

MongoDB stores **_id** as a BSON string in this case. Other valid choices include integers and supported BSON types, subject to `_id` field constraints. In production systems, **standardize on one _id type per collection** so Java mappers, APIs, and queries do not have to handle mixed types.

For example, the following two queries **do not mean the same thing**:

~~~javascript
db.customers.findOne({
  _id: ObjectId("64b000000000000000000001")
});

db.customers.findOne({
  _id: "64b000000000000000000001"
});
~~~

An ObjectId and a string containing the same 24 hex characters are not the same BSON type. Applications must perform explicit conversion when mapping requests to queries.

### 2.4. Do Not Modify _id with $set

~~~javascript
// Invalid if attempting to change the _id of an existing document.
db.customers.updateOne(
  { _id: "CUS-HN-001" },
  { $set: { _id: "CUS-HN-002" } }
);
~~~

MongoDB does not allow updating the **_id** of an existing document directly this way. If business logic requires changing an identifier, design an appropriate workflow (such as creating a new document, updating references, and handling the old document), taking care with consistency and unique constraints.

For business codes that may change, consider keeping **_id** stable and storing the business code in a separate field such as **customerCode**, adding a unique index if the business code must be unique.

### 2.5. Why Can't the _id_ Index Be Dropped?

The default **_id_** index is tied to the identity mechanism of a standard collection. Trying:

~~~javascript
db.customers.dropIndex("_id_");
~~~

is rejected by MongoDB. Never use undocumented methods to alter index files on disk, as doing so can corrupt data.

**Storage model exception:** certain special collection types, such as **clustered collections**, organize cluster keys and metadata differently from standard collections. When inspecting a specific system, rely on the actual collection type and catalog output rather than applying every physical index rule to all collection types.

## 3. Creating and Inspecting the Default Index in mongosh

### 3.1. Create a Test Collection

~~~javascript
use index_basics_lab

db.createCollection("products");
~~~

If the collection already exists, **createCollection** returns an error. Use a dedicated lab collection name or skip this step if it was already created.

Inspect the indexes:

~~~javascript
db.products.getIndexes();
~~~

Typical output:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
~~~

Some metadata fields may vary by version; do not hardcode checks expecting these exact keys in every environment. Even though **unique: true** is not always printed explicitly in every **_id_** specification, the default index still enforces uniqueness within MongoDB's defined scope.

### 3.2. Insert Documents and Query by _id

~~~javascript
db.products.insertMany([
  {
    _id: "SKU-KB-01",
    name: "Mechanical Keyboard",
    category: "ACCESSORIES",
    price: NumberDecimal("1250000.00"),
    status: "ACTIVE"
  },
  {
    _id: "SKU-MOUSE-01",
    name: "Wireless Mouse",
    category: "ACCESSORIES",
    price: NumberDecimal("350000.00"),
    status: "ACTIVE"
  },
  {
    _id: "SKU-MON-01",
    name: "27-inch Monitor",
    category: "DISPLAYS",
    price: NumberDecimal("4200000.00"),
    status: "ACTIVE"
  }
]);
~~~

Lookup by ID:

~~~javascript
db.products.findOne({ _id: "SKU-KB-01" });
~~~

Lookup by another field:

~~~javascript
db.products.find({ category: "ACCESSORIES" });
~~~

The first query **can leverage the _id index**. The second query **cannot efficiently use the _id index to filter by category just because _id exists**. To optimize filtering on `category`, evaluate a separate index tailored to the query shape.

### 3.3. Checking Duplicate _id

~~~javascript
db.products.insertOne({
  _id: "SKU-KB-01",
  name: "Keyboard Duplicate"
});
~~~

This command fails with a **duplicate key** error, typically containing code **E11000** in the message. MongoDB does not silently overwrite an existing document when calling **insertOne** with the same **_id**.

When building APIs that may be retried due to timeouts or network errors, design a stable **_id/business key** and distinguish "already exists with the same data" from an "identifier conflict." A unique index prevents duplicate records from being inserted, but it does not decide your idempotency policy for you.

## 4. Distinguishing the _id Index from Application-Created Indexes

Suppose you need to query:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

The default **{_id: 1}** index is built on `_id`, so it does not organize data by category/status. A new index such as:

~~~javascript
db.products.createIndex({
  category: 1,
  status: 1
});
~~~

may fit this filter condition depending on data distribution and the query plan.

### 4.1. Values 1 and -1 in Key Specifications

~~~javascript
{ category: 1, createdAt: -1 }
~~~

**1** indicates ascending order and **-1** indicates descending order in the index. For a **compound index**, field order and sort direction can affect its ability to support sorted queries, especially multi-field sorts with mixed directions.

Do not confuse:

~~~javascript
{ category: 1, createdAt: -1 }
~~~

with:

~~~javascript
{ createdAt: -1, category: 1 }
~~~

These are two different compound indexes, because field order is a critical part of the definition and determines how queries can use the index.

### 4.2. Single-Field and Compound Indexes

Single-field index:

~~~javascript
db.products.createIndex({ category: 1 });
~~~

Compound index:

~~~javascript
db.products.createIndex({ category: 1, status: 1 });
~~~

A compound index can generally support queries matching its **prefix** under suitable conditions—for example, a query on `category` using **{category:1,status:1}**. However, do not assume that same index will optimize a query filtering **only on status** as effectively as a dedicated **{status:1}** index.

Having more indexes does not automatically guarantee better speed. The MongoDB Query Planner chooses a plan based on data, metadata, and query predicates; always verify with **explain**.

## 5. createIndex(): Creating Intentional Indexes

### 5.1. General Syntax

~~~javascript
db.collection.createIndex(
  { field1: 1, field2: -1 },
  {
    name: "index_name",
    // options such as unique, partialFilterExpression...
  }
);
~~~

Arguments:

- **Key specification:** list of fields/index keys and sort directions or index types.
- **Options:** index name, unique, partial filter, collation, and other supported options.
- **Return value:** typically the name of the created index or an equivalent existing index if the command succeeds in mongosh.

Example:

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

If successful, the shell returns a name such as:

~~~text
ix_category_status
~~~

### 5.2. Why Give Indexes Clear Names?

If **name** is omitted, MongoDB auto-generates a name from the key pattern, such as **category_1_status_1**. This is valid and recognizable for simple indexes.

In large systems, intentional names help:

1. Identify an index's role in migrations and operational runbooks.
2. Drop the exact index with **dropIndex("ix_category_status")**.
3. Simplify logging and usage tracking.
4. Distinguish indexes that share similar keys but have different options, within supported MongoDB configurations.

A naming convention might look like:

~~~text
ix_<field>_<field>
uq_<field>_<field>
ttl_<field>
partial_<purpose>
~~~

This is a team naming convention, not a MongoDB syntax requirement. Keep names stable across migrations for predictable operations.

### 5.3. Creating a Unique Index

Suppose **productCode** must be unique within each **tenantId**:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    unique: true,
    name: "uq_tenant_product_code"
  }
);
~~~

When this unique compound index exists, two documents with the same **tenantId** and **productCode** cannot both be stored within MongoDB's enforced uniqueness scope. However, two different tenants can still share the same `productCode`.

**A unique index does not clean up existing duplicates automatically.** If the collection already contains duplicate key combinations, creating the unique index can fail. Identify and resolve duplicate records before creating the constraint.

Example query to find duplicate combinations during investigation:

~~~javascript
db.products.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        productCode: "$productCode"
      },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  }
]);
~~~

On large collections, pushing all IDs into an array can exceed the aggregation document size limit. When you only need to locate duplicate groups, omit **ids** and process in batches. This example is intended for test datasets, not as an optimal command for every production workload.

### 5.4. Creating a Unique Index Does Not Require Every Field to Be Populated

For a standard unique index, documents missing the field or containing **null** can generate corresponding null/missing index entries under MongoDB rules, leading to duplicate key errors in certain cases. With a single-field unique index on an optional field, only one document may be allowed to have a null/missing key value under those rules.

If uniqueness is only required for documents **that contain a specific field**, design a **partial unique index**, schema validation, or another appropriate rule. Never set **unique: true** assuming documents missing the field are automatically ignored.

### 5.5. Creating a Partial Index

Suppose queries mostly target **ACTIVE** products:

~~~javascript
db.products.createIndex(
  { category: 1 },
  {
    name: "ix_active_category",
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);
~~~

This index only includes documents matching **status: "ACTIVE"**. A matching query:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

The query planner can use a partial index only when the query predicate guarantees no results are missed relative to the defined filter expression. A query filtering by `category` without restricting `status` **cannot use this partial index** because it omits documents in non-ACTIVE states.

### 5.6. Creating a TTL Index

For collections with expiring data such as expired tokens, you can use a **TTL index**:

~~~javascript
db.temporary_sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

**expiresAt** must use an appropriate BSON Date type. MongoDB's TTL monitor purges expired documents **asynchronously**; there is no guarantee a document disappears at the exact millisecond `expiresAt` passes. Choose TTL intentionally because it deletes data, unlike indexes that only assist queries.

### 5.7. Indexes with Collation

If an application needs case-insensitive name comparisons according to an appropriate locale, consider collation:

~~~javascript
db.customers.createIndex(
  { fullName: 1 },
  {
    name: "ix_customer_name_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

To benefit from a collated index, the query must specify a compatible collation or match the collection default:

~~~javascript
db.customers.find({
  fullName: "nguyen van a"
}).collation({
  locale: "en",
  strength: 2
});
~~~

**Collation** affects string comparison semantics, index usage, and uniqueness. Do not change collation without verifying the linguistic and sorting rules of your business data.

### 5.8. createIndexes() for Declaring Multiple Indexes

MongoDB also provides **createIndexes()**, allowing multiple indexes to be declared in a single call:

~~~javascript
db.products.createIndexes([
  {
    key: { category: 1, status: 1 },
    name: "ix_category_status"
  },
  {
    key: { price: 1 },
    name: "ix_price"
  }
]);
~~~

Do not assume creating multiple indexes in one command means all index builds are transactional and rolled back together like an application transaction. Exact behavior depends on version, data volume, and operational procedures.

## 6. What Happens If createIndex() Is Called Repeatedly?

MongoDB checks existing indexes. When a **createIndex** call matches an existing index's definition under the server version's equivalence rules, MongoDB generally **does not build a duplicate copy**.

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);

db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

The second call normally does not create another index with the same name and definition.

However, distinguish these cases:

- **Same key pattern but different options:** some options cannot be modified by re-calling `createIndex`; it may conflict or require **collMod** or drop/recreate depending on the option.
- **Same name but different key pattern:** may be rejected because the name is already bound to a different definition.
- **Same key pattern, different collation/partialFilterExpression:** coexistence and equivalence rules have version-specific constraints; do not guess.
- **Adding unique: true to an existing non-unique index:** you cannot assume calling `createIndex` with the same key and the new option turns the old index into a unique one.

**Index definitions are operational schema**, so verify the actual specification before concluding an "ensure index" step succeeded as intended.

### 6.1. Protecting Migration Rollouts

When multiple application instances start simultaneously, avoid letting every instance fire a batch of large index creation/deletion commands uncoordinated. Better options include:

1. Manage indexes via versioned migration or deployment jobs.
2. Run migrations from a single coordinated owner.
3. Inspect **getIndexes** before and after changes.
4. Monitor build duration logs, CPU/I/O, and query latency impact.
5. Keep a rollback plan based on index names and observed performance.

Re-calling `createIndex` with the exact same spec is generally safer than drop/recreate, though you still must guard against concurrency, build duration, and incompatible option errors.

## 7. getIndexes(): Inspecting the Index Catalog

### 7.1. Listing a Collection's Indexes

~~~javascript
db.products.getIndexes();
~~~

Illustrative output after creating several indexes:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  },
  {
    v: 2,
    key: { category: 1, status: 1 },
    name: "ix_category_status"
  },
  {
    v: 2,
    key: { tenantId: 1, productCode: 1 },
    name: "uq_tenant_product_code",
    unique: true
  }
]
~~~

This is an abbreviated example and may not match every field or version in a real environment. Depending on the index, the catalog may contain:

| Field | Common meaning |
|---|---|
| **name** | Index identifier name, used to drop, hide, or track it. |
| **key** | Key pattern; field order and direction or index type. |
| **unique** | Uniqueness rule (for regular indexes; `_id` metadata is represented differently). |
| **partialFilterExpression** | Predicate restricting the indexed document subset. |
| **sparse** | Option to index only documents matching sparse rules. |
| **expireAfterSeconds** | TTL duration for eligible TTL indexes. |
| **collation** | String comparison rules for the index. |
| **hidden** | Indicates the index is hidden from the query planner when supported. |
| **v** | Internal index format version, not the application migration version. |

**getIndexes() lists index specifications—not usage counts, individual index sizes, or query costs.** To investigate performance, combine it with **explain**, **$indexStats**, **stats**, and appropriate monitoring tools.

### 7.2. Listing Index Names

~~~javascript
db.products.getIndexes().map(index => index.name);
~~~

Example output:

~~~javascript
[
  "_id_",
  "ix_category_status",
  "uq_tenant_product_code"
]
~~~

This snippet is handy for administration, but should never be used to automatically pick indexes to drop based only on substring name matches.

### 7.3. Checking Whether an Index Exists

~~~javascript
const indexes = db.products.getIndexes();
const index = indexes.find(
  spec => spec.name === "ix_category_status"
);

if (index) {
  printjson(index);
} else {
  print("Index does not exist yet");
}
~~~

Checking the name is only the first step. To verify the exact definition, also inspect **key**, **unique**, **partialFilterExpression**, **collation**, and other critical options; do not rely solely on a name match.

### 7.4. Listing Indexes with the listIndexes Command

Besides the mongosh helper, MongoDB provides the **listIndexes** command:

~~~javascript
db.runCommand({
  listIndexes: "products"
});
~~~

This command returns a cursor of index specifications, useful in admin tools and drivers. When running at the command level, handle the cursor per MongoDB conventions rather than assuming the response is always a complete array like **getIndexes()**.

### 7.5. getIndexes() vs. $indexStats

**getIndexes()** returns **definitions**. **$indexStats** returns index access statistics, for example:

~~~javascript
db.products.aggregate([
  { $indexStats: {} }
]);
~~~

The output may include index name, host, statistics start time, and access counters since an observation baseline. Access stats can reset after events such as restarts or index changes; they do not by themselves prove an index is unnecessary.

An index with a low access count can still be critical for:

- monthly reporting queries;
- a rare endpoint with a strict SLA;
- a **unique constraint** rule;
- transactions or special operational workflows.

Do not drop an index simply because **accesses.ops** looks low over a short observation window.

## 8. Verifying Index Usage with explain()

Create a query:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

After creating index **{category:1,status:1}**, inspect the query plan:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

An **explain** output can show stages such as:

- **IXSCAN:** reading keys from a suitable index.
- **FETCH:** retrieving documents from the collection when fields outside the index are needed or additional filtering is performed.
- **COLLSCAN:** scanning documents in the collection.
- **PROJECTION_COVERED** or equivalent engine/version-specific stages: may relate to queries covered by an index.

In newer versions, query plan representation may differ due to the **slot-based execution engine** and internal changes. Do not depend on a single hardcoded JSON path in `explain` output across all versions.

### 8.1. Key Metrics to Watch

| Metric | Meaning |
|---|---|
| **nReturned** | Number of documents returned. |
| **totalKeysExamined** | Number of index keys read/examined. |
| **totalDocsExamined** | Number of documents read/examined. |
| **winningPlan** | The plan chosen by the query planner. |
| **executionTimeMillis** | Reported time in executionStats; understand measurement limits and environmental factors. |

If **nReturned = 10** while **totalDocsExamined = 1,000,000**, the query may be scanning far too many documents. Still, do not assume an index scan always beats a collection scan: for small collections or queries returning most of the dataset, a collection scan is sometimes the sensible choice.

### 8.2. _id Index and Queries by _id

~~~javascript
db.products.find({
  _id: "SKU-KB-01"
}).explain("executionStats");
~~~

An equality query on **_id** is typically where MongoDB exploits the default index most efficiently. Depending on the planner/engine, the plan may show a specialized stage such as **IDHACK/EXPRESS_IXSCAN** in supported versions or an equivalent index stage. What matters is checking the number of documents/keys examined and actual query time.

### 8.3. Covered Queries and Default _id in Projections

Example index:

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

Query retrieving only the two fields present in the index:

~~~javascript
db.products.find(
  {
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: 0,
    category: 1,
    status: 1
  }
).explain("executionStats");
~~~

This query **can** be a **covered query** if the index and query satisfy the required conditions, because the projection asks for no fields outside the index and excludes **_id**.

If you omit **_id: 0**, MongoDB returns **_id** by default, while the **{category:1,status:1}** index does not contain `_id` as a defined key. Returning `_id` can force a **FETCH**. This is why projections should always be checked when analyzing covered queries.

### 8.4. A Single explain() Does Not Replace Benchmarking

**explain()** helps explain plans, but production environments also involve:

- network latency;
- concurrent connections;
- whether data is in cache or must be read from disk;
- replication and write load;
- tenant/shard distribution;
- peak workloads and p95/p99 latency.

Combine `explain` with metrics and benchmarks on representative data instead of tuning solely around a single warm-cache query in a small environment.

## 9. dropIndex(): Removing a Specific Index

### 9.1. Dropping by Name

~~~javascript
db.products.dropIndex("ix_category_status");
~~~

This command tells MongoDB to remove the index with the matching **name** if it exists and is permitted to be dropped. Once dropped, MongoDB no longer uses that structure to assist queries. Document data **is not deleted merely by calling dropIndex**.

**Do not confuse dropIndex with drop():**

~~~javascript
db.products.dropIndex("ix_category_status"); // Drops one index

// db.products.drop();                       // Drops the entire collection and its data
~~~

The **drop()** line is only a warning reminder, not a practice step to run.

### 9.2. Dropping by Key Pattern

MongoDB also supports specifying the key pattern to drop a matching index:

~~~javascript
db.products.dropIndex({
  category: 1,
  status: 1
});
~~~

In operations, **exact index names** are usually easier to control, especially when multiple index configurations exist with different options. Before dropping, check **getIndexes()** to confirm the name, key, and options.

### 9.3. The _id_ Index Cannot Be Dropped

~~~javascript
db.products.dropIndex("_id_");
~~~

MongoDB rejects operations attempting to drop the required index. Never try to work around this by modifying data files directly.

### 9.4. Impact of Dropping an Index on Queries

Suppose an endpoint runs:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

When **ix_category_status** is dropped, the query planner must find another plan: it may fall back to an alternative index, combine other options, or perform a collection scan. On large collections, latency can spike sharply.

**Dropping an index changes query-serving capability**, not just disk usage. Verify beforehand:

- which endpoints depend on the index;
- which queries currently use the index;
- whether another index adequately covers the filters/sorts;
- the recovery procedure if performance degrades;
- deployment timing and current database load.

### 9.5. Do Not Use dropIndexes("*") Carelessly

MongoDB provides the **dropIndexes()** helper and ways to drop multiple indexes depending on the API. For example:

~~~javascript
// Use only in a LAB collection if intentionally removing all
// droppable indexes except the protected _id_ index.
// db.products.dropIndexes();
~~~

This is a broad operation and should not be used in production migrations when only a single specific index needs removal. It can make many queries slow and stop enforcing unique constraints maintained by those indexes.

### 9.6. What Happens When a Unique Index Is Dropped?

If a unique index such as:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    name: "uq_tenant_product_code",
    unique: true
  }
);
~~~

is dropped:

~~~javascript
db.products.dropIndex("uq_tenant_product_code");
~~~

then the uniqueness constraint on **tenantId + productCode** enforced by that index disappears too. Afterward, two documents with the same key combination can be written to the collection unless another constraint prevents it.

Thus, a **unique** index is both a query optimization structure and a **data invariant**. Never evaluate dropping it solely from access metrics; confirm with domain owners and dependent systems.

## 10. Hide Index: Testing Impact Before Dropping

MongoDB supports **hidden indexes** in compatible versions. When an index is hidden:

- The query planner **does not select** that index for normal query planning.
- The index still exists and continues to be maintained when documents are written.
- It can be **unhidden** without rebuilding the entire index, making it safe to test the impact of not using it.

Example on a regular index **other than _id_**:

~~~javascript
db.products.hideIndex("ix_category_status");
~~~

Then:

~~~javascript
db.products.getIndexes();
~~~

A hidden index will show **hidden: true** in its specification. Inspect the query plan:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

If unacceptable degradation is observed:

~~~javascript
db.products.unhideIndex("ix_category_status");
~~~

Only after sufficient observation confirms the index is no longer needed and approved for removal should you run:

~~~javascript
db.products.dropIndex("ix_category_status");
~~~

**Comparing hide vs. drop:**

| | Hide index | Drop index |
|---|---|---|
| Query planner | Ignores the hidden index. | No index left to use. |
| Index structure on disk | Remains on disk. | Removed. |
| Write maintenance cost | Still incurred. | Eliminated after dropping. |
| Restoring index availability | **unhideIndex** is relatively fast. | Must run **createIndex** again, incurring full build time. |
| Use case | Testing the impact of removing an index. | Executing the actual removal decision. |

You cannot use a hidden index to "disable" a unique constraint: a **hidden unique index** continues to enforce uniqueness. The default **_id_** index also cannot be hidden like other hideable indexes.

## 11. Index Management Affects Writes and Resources

### 11.1. Indexes Speed Up Reads but Increase Write Costs

Suppose every product insert must update:

~~~text
Collection document
    |
    +-- _id_ index
    +-- ix_category_status
    +-- ix_price
    +-- uq_tenant_product_code
    +-- ...
~~~

Each additional index means write operations must maintain more index keys. Under heavy write workloads, creating too many indexes increases I/O, cache pressure, and write concern latency.

Avoid the rule "every field needs an index." Create indexes only from well-defined or measured **query patterns, sorts, joins/lookups, uniqueness, or TTL requirements**.

### 11.2. Building Indexes on Large Collections Is an Operational Task

On collections with hundreds of millions of documents, building an index can:

- require reading massive amounts of source data;
- consume CPU, RAM, I/O, and temporary disk space;
- place load on replication and replica set members;
- affect latency of running workloads;
- significantly lengthen deployment windows.

Index build mechanics, quorum behavior, and read/write availability during builds vary across MongoDB versions and topologies. Do not blindly follow legacy advice about **background: true** without checking your version: in modern MongoDB releases, index builds use optimized mechanisms and the **background** option no longer works as it once did.

Include index migrations in deployment planning, monitor progress, and provision adequate disk/CPU/network capacity. On Atlas, builds may be managed via platform-supported workflows; still account for load and cost.

### 11.3. Indexes Are Not a Substitute for Good Schema Design

If an application queries:

~~~javascript
db.products.find({
  price: "1250000.00"
});
~~~

while `price` is stored as BSON **Decimal128**, an index on **price** will not coerce a string into the right decimal type. Consistent data type mapping is essential. Likewise, an index cannot fix queries that consistently filter on the wrong tenant or non-existent fields.

### 11.4. Do Not Create an Index Just Because One Query Is Slow

A slow query can stem from:

- a missing index;
- an unsuitable index;
- returning too many documents;
- projections fetching large payloads;
- suboptimal sorting and pagination;
- saturated network, disk, cache, or connection pools;
- high update/replication frequency causing resource contention;
- skewed data distribution across shards.

Indexes are a powerful lever, but diagnose the actual root cause before adding one.

## 12. A Safe Index Management Lifecycle

Suppose the system plans to add an index supporting a category/status product listing endpoint.

### Step 1 — Describe the Actual Query

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    name: 1,
    price: 1
  }
).sort({ createdAt: -1 }).limit(50);
~~~

This query includes both filters and a sort. Do not create **{category:1}** simply because `category` appears; account for `tenantId`, `status`, `createdAt`, sort direction, projection, selectivity, and workload.

### Step 2 — Read the Index Catalog

~~~javascript
db.products.getIndexes();
~~~

Check if an existing index already covers most of the query pattern. Avoid creating overlapping roles or near-duplicate variants.

### Step 3 — Inspect the Current Query Plan

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  category: "ACCESSORIES",
  status: "ACTIVE"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

Record baseline metrics and understand how the query behaves in a test environment with representative data.

### Step 4 — Choose an Index for the Workload

A candidate:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    category: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "ix_tenant_category_status_created"
  }
);
~~~

This is a **candidate to measure**, not a guaranteed optimum. Field order may shift depending on selectivity, other queries, and pagination design. Apply the equality, sort, range principle when designing compound indexes.

### Step 5 — Verify the Index Specification

~~~javascript
db.products.getIndexes().find(
  index => index.name === "ix_tenant_category_status_created"
);
~~~

Confirm the key pattern order and defined options match expectations.

### Step 6 — Re-measure and Observe Under Load

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  category: "ACCESSORIES",
  status: "ACTIVE"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

Evaluate:

- Is the query plan appropriate?
- Did `keysExamined`/`docsExamined` decrease?
- Did application p95/p99 latency improve?
- How much did write latency and index storage size increase?
- Were there regressions on other critical endpoints?

### Step 7 — If Removing an Index, Hide It First

~~~javascript
db.products.hideIndex("ix_tenant_category_status_created");
~~~

Monitor performance and query plans over a representative window, then:

~~~javascript
// If immediate rollback is needed:
db.products.unhideIndex("ix_tenant_category_status_created");

// Drop only after gathering evidence and approval:
// db.products.dropIndex("ix_tenant_category_status_created");
~~~

Do not apply the hide/drop workflow to **_id_**.

## 13. Java Sync Driver: Creating, Listing, and Dropping Indexes

In Java applications using the **MongoDB Java Sync Driver**, you can manage indexes through the **MongoCollection** API. The advantage is using typed builders like **Indexes** and **IndexOptions** instead of concatenating raw JSON strings.

The examples below assume the MongoDB Java Sync Driver dependency and a properly configured **MongoClient**.

### 13.1. createIndex() in Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public final class IndexCreateExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI environment variable is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("index_basics_lab");

            MongoCollection<Document> collection =
                    database.getCollection("products");

            IndexOptions options = new IndexOptions()
                    .name("ix_category_status");

            String indexName = collection.createIndex(
                    Indexes.ascending("category", "status"),
                    options
            );

            System.out.println("Index name: " + indexName);
        }
    }
}
~~~

The Java driver sends the appropriate `createIndexes` command through the collection API. Running it against an existing populated collection may trigger an index build on the server; never let request handlers arbitrarily trigger large index builds per HTTP call.

### 13.2. Unique createIndex() per Tenant

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

String indexName = collection.createIndex(
        Indexes.ascending("tenantId", "productCode"),
        new IndexOptions()
                .name("uq_tenant_product_code")
                .unique(true)
);

System.out.println(indexName);
~~~

If duplicate **tenantId/productCode** pairs exist, the driver receives an error from MongoDB. Handle the specific exception properly rather than automatically deleting duplicate documents before business review.

### 13.3. listIndexes() Instead of getIndexes()

The Java Sync Driver provides **listIndexes()**:

~~~java
for (Document indexSpec : collection.listIndexes()) {
    System.out.println(indexSpec.toJson());
}
~~~

**mongosh** uses **getIndexes()**, whereas the Java driver typically uses **listIndexes()**. They are different interfaces serving the same goal of inspecting a collection's index catalog.

Filtering by index name:

~~~java
boolean exists = false;

for (Document spec : collection.listIndexes()) {
    if ("ix_category_status".equals(spec.getString("name"))) {
        exists = true;
        System.out.println(spec.toJson());
    }
}

System.out.println("Exists: " + exists);
~~~

When verifying indexes in a schema migration, compare **keys and options** as well, not just the name.

### 13.4. dropIndex() in Java

~~~java
collection.dropIndex("ix_category_status");
~~~

This command instructs MongoDB to drop the specified index. Control operational permissions and execution timing carefully. In production, use controlled migration or admin workflows rather than dropping indexes during client request handling.

### 13.5. Example of a Limited "Ensure" Helper

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public final class ProductIndexMigration {
    public static void ensureIndex(MongoCollection<Document> collection) {
        collection.createIndex(
                Indexes.ascending("tenantId", "productCode"),
                new IndexOptions()
                        .name("uq_tenant_product_code")
                        .unique(true)
        );
    }
}
~~~

This method can be called inside a coordinated migration. It is **not a complete schema management system**: it does not detect all option/collation drifts, coordinate multiple processes, resolve duplicate data, or monitor builds. Larger systems require a well-defined deployment process.

### 13.6. The Java API Does Not Replace Understanding Server Behavior

When a service calls:

~~~java
collection.dropIndex("uq_tenant_product_code");
~~~

MongoDB not only removes an acceleration structure, it also removes the unique constraint enforced by that index. Java type safety cannot prevent altering database business semantics. Treat indexes as part of your database schema and security/operational model.

## 14. Spring Data MongoDB: IndexOperations

With **Spring Data MongoDB**, indexes can be declared via annotations or managed programmatically via **MongoTemplate.indexOps()**. Annotations are convenient, yet index creation and migrations still require careful control.

### 14.1. Declaring an Entity and _id Field

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class ProductDocument {
    @Id
    private String id;

    private String tenantId;
    private String productCode;
    private String category;
    private String status;

    // constructors, getters, setters
}
~~~

The **id** field is mapped by Spring Data to MongoDB **_id** via convention/annotation. In this example **id** in Java is a **String**; how it converts to ObjectId or string upon persistence depends on Spring Data's mapping rules and the value itself. If business logic requires a specific `_id` type, declare explicit converters/annotations and a consistent contract.

### 14.2. Creating an Index with IndexOperations

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

// MongoTemplate mongoTemplate has been injected.
mongoTemplate.indexOps("products").ensureIndex(
        new Index()
                .on("category", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .named("ix_category_status")
);
~~~

**ensureIndex** ensures the corresponding index under supported conditions, but should not be assumed capable of altering arbitrary options on an existing index without a proper migration.

### 14.3. Listing Indexes with Spring Data

~~~java
mongoTemplate.indexOps("products")
        .getIndexInfo()
        .forEach(System.out::println);
~~~

Spring Data returns **IndexInfo** objects describing indexes rather than the raw **getIndexes()** format of mongosh. Information may include name, fields, uniqueness, and other options.

### 14.4. Dropping an Index with Spring Data

~~~java
mongoTemplate.indexOps("products")
        .dropIndex("ix_category_status");
~~~

Avoid placing this call in normal request paths or running it across every application instance on startup without coordination.

### 14.5. @Indexed and @CompoundIndex Annotations

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
@CompoundIndex(
        name = "uq_tenant_product_code",
        def = "{ 'tenantId': 1, 'productCode': 1 }",
        unique = true
)
public class ProductEntity {
    @Id
    private String id;

    private String tenantId;
    private String productCode;

    @Indexed(name = "ix_category")
    private String category;
}
~~~

Annotations **describe desired indexes**, while automatic creation at startup depends on **auto-index creation configuration** and the Spring Data version. Modern Spring Data MongoDB should not be assumed to auto-create all annotated indexes by default. In production, explicitly decide between controlled annotation-based creation and separate migrations.

One risk is that **changing an annotation or renaming a Java field does not automatically drop the old index**. Stale indexes can accumulate without proper lifecycle management.

## 15. _id Index and Sharding: Cluster-Wide Uniqueness Limits

In an **unsharded collection**, the unique **_id** index prevents two documents from sharing the same `_id`.

For a **sharded collection**, distinguish between these cases:

- If **_id** is chosen as the shard key, routing and ID uniqueness align directly with the sharding topology.
- If **_id is not the shard key**, MongoDB can only enforce **_id** uniqueness **per shard**, not cluster-wide across operations routed to different shards. In that case, **the application is responsible for ensuring globally unique _id values**.
- Unique indexes on sharded collections must satisfy **shard key prefix** requirements and MongoDB's supported constraints.

Suppose the shard key is **tenantId**. Two documents with identical `_id` values but different `tenantId` values could be routed to two different shards; do not rely on local `_id` indexes for cluster-wide uniqueness if `_id` is not part of the shard key as required.

**Safe design practices:**

1. Use ID generation schemes with negligible collision probability such as ObjectId/UUID properly where appropriate.
2. If business rules require cluster-wide uniqueness on a specific key, design the shard key and index strategy together from the start.
3. Never equate **an index existing on each shard** with a **global unique constraint**.
4. Verify exact guarantees against your deployed topology, MongoDB version, and collection type.

Never change a shard key solely to fix one slow query without evaluating data distribution, routing, availability, and migration costs.

## 16. Other Index Types to Put createIndex in Context

This lesson focuses on **_id**, **createIndex**, **getIndexes**, and **dropIndex**. When managing indexes, you will encounter several index types; recognize them so you do not modify or drop the wrong one.

| Index type | Example key / option | Typical use case |
|---|---|---|
| **Single-field** | **{category:1}** | Filtering or sorting on a single field. |
| **Compound** | **{tenantId:1,status:1}** | Queries across multiple fields / prefixes. |
| **Multikey** | **{tags:1}** when `tags` is an array | Matching elements within arrays. |
| **Unique** | **unique:true** | Preventing duplicate key values within scope. |
| **Partial** | **partialFilterExpression** | Indexing a subset of documents matching a predicate. |
| **TTL** | **expireAfterSeconds** | Asynchronously deleting expired documents. |
| **Text** | **{description:"text"}** | Supporting full-text search via MongoDB text indexes. |
| **Wildcard** | **{"attributes.$**":1}** | Querying dynamic fields inside documents where appropriate. |
| **Geospatial** | **{"location":"2dsphere"}** | Querying geospatial data. |
| **Hashed** | **{customerId:"hashed"}** | Hash-based lookups/distribution; limited query support. |

Options like **Atlas Search indexes** are separate search structures in the MongoDB ecosystem with different tooling and management lifecycles from standard B-tree **createIndex**. Do not attempt **dropIndex** on a search index whose management API differs.

Also, an index is not automatically "good" for every query just because it includes many fields. Overly long compound indexes consume space and fail to help queries that do not match the declared prefix.

## 17. Common Mistakes When Managing Indexes

### 17.1. Recreating the _id Index Even Though It Already Exists

~~~javascript
db.products.createIndex({ _id: 1 });
~~~

On standard collections, the **_id_** index already exists; calling this brings no meaningful optimization benefit. Check **getIndexes()** before adding indexes on other fields.

### 17.2. Confusing the _id Index with a Unique Business Key

Two products with **different _id values** but the same **productCode** can still be inserted unless a suitable unique constraint/index exists on `productCode` or the business key combination.

~~~javascript
{
  _id: "P-001",
  productCode: "KEYBOARD-01"
}

{
  _id: "P-002",
  productCode: "KEYBOARD-01"
}
~~~

If uniqueness per tenant is needed, design **{tenantId:1,productCode:1}** with **unique:true**, factoring in sharding limitations if applicable.

### 17.3. Creating a Unique Index After Duplicate Data Exists

~~~javascript
db.products.createIndex(
  { productCode: 1 },
  { unique: true }
);
~~~

This command can fail with a duplicate key error. Do not randomly delete "duplicate documents" just to get the index built; first identify the authoritative record, downstream impacts, and a migration plan.

### 17.4. Checking Only the Name While Ignoring Options

An index named **ix_active_category** with a different **partialFilterExpression** than intended represents a different contract. A migration must compare full specifications rather than just running **getIndexes().map(i => i.name)**.

### 17.5. Confusing dropIndex with Deleting Documents

**dropIndex()** removes an index, not documents. Still, dropping **unique/TTL** indexes alters data invariants or retention policies, so it remains a sensitive operation.

### 17.6. Attempting to Drop the _id_ Index

The `_id` index on a standard collection is mandatory; MongoDB prohibits dropping it. Never try to alter it using tools that touch WiredTiger files directly.

### 17.7. Creating Too Many Indexes to Make Every Query Fast

Indexes increase write overhead and disk usage. Creating many single-field indexes **{a:1}**, **{b:1}**, **{c:1}** does not automatically outperform a single compound index tailored to the access pattern. Measure the workload and maintain the minimal index set meeting SLAs.

### 17.8. Dropping an Index Simply Because $indexStats Shows Low Accesses

An index serving a monthly report may go unused all week prior. A unique index may also need to stay to enforce invariants even when few read queries use it.

### 17.9. Using Drop-Then-Create to Change Options During Peak Hours

Doing so can create a window **with no index**, slowing queries and leaving unique constraints unprotected during the gap. Index changes must be planned around option types, **collMod** availability, duplicate data, permissions, and build duration.

### 17.10. Hardcoding hint() to an Index That Becomes Obsolete

MongoDB supports **hint()** to request a specific index for certain queries. If production code forces a hint by index name and that index is dropped, queries can fail. When managing indexes, search for queries and applications referencing those hints.

~~~javascript
db.products.find({
  category: "ACCESSORIES"
}).hint("ix_category_status");
~~~

In the example above, the hint depends on the index named **ix_category_status**. If that index is removed, update the query/hint accordingly. Avoid overusing hints instead of letting the query planner choose and measuring real performance.

## 18. Hands-On Lab: Managing the Index Lifecycle in mongosh

Work inside the dedicated **index_basics_lab** database for this lab.

### Step 1 — Create the Collection and Inspect the _id Index

~~~javascript
use index_basics_lab

db.createCollection("index_practice");
db.index_practice.getIndexes();
~~~

Expect to see the index named **_id_**. If the collection already exists, skip `createCollection`.

### Step 2 — Insert Documents

~~~javascript
db.index_practice.insertMany([
  {
    _id: "P-101",
    tenantId: "SHOP-A",
    productCode: "MOUSE-01",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: "P-102",
    tenantId: "SHOP-A",
    productCode: "KEYBOARD-01",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: "P-103",
    tenantId: "SHOP-A",
    productCode: "MONITOR-01",
    category: "DISPLAYS",
    status: "DRAFT"
  }
]);
~~~

### Step 3 — Query by _id

~~~javascript
db.index_practice.find({
  _id: "P-102"
}).explain("executionStats");
~~~

Inspect the query plan and fields **nReturned**, **totalKeysExamined**, **totalDocsExamined**. With a tiny collection, the plan may differ from simple expectations depending on version, though the **_id_** index is still present.

### Step 4 — Create a Regular Index

~~~javascript
db.index_practice.createIndex(
  { category: 1, status: 1 },
  { name: "ix_practice_category_status" }
);
~~~

### Step 5 — Read the Metadata

~~~javascript
db.index_practice.getIndexes();
~~~

Look for **key: {category:1,status:1}** and **name: ix_practice_category_status**.

### Step 6 — Create a Unique Index for Product Code per Tenant

~~~javascript
db.index_practice.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    name: "uq_practice_tenant_product_code",
    unique: true
  }
);
~~~

Try inserting a new document with a **different _id** but duplicate **tenantId + productCode**:

~~~javascript
db.index_practice.insertOne({
  _id: "P-999",
  tenantId: "SHOP-A",
  productCode: "MOUSE-01",
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Expect rejection due to **duplicate key** on the new unique index, even though **_id** is not duplicated.

### Step 7 — Compare Query Plans

~~~javascript
db.index_practice.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

A tiny query may still pick **COLLSCAN** due to low cost. Note the plan and do not draw benchmark conclusions from three documents.

### Step 8 — Hide and Unhide the Index

~~~javascript
db.index_practice.hideIndex("ix_practice_category_status");
db.index_practice.getIndexes();

db.index_practice.unhideIndex("ix_practice_category_status");
db.index_practice.getIndexes();
~~~

Only test hide/unhide on **regular** indexes, not **_id_**.

### Step 9 — Drop the Test Index

~~~javascript
db.index_practice.dropIndex("ix_practice_category_status");
db.index_practice.getIndexes();
~~~

Expect **ix_practice_category_status** to no longer be listed, while **_id_** and the remaining unique index persist. Dropping a regular index does not delete documents.

### Step 10 — Verify the _id Index Cannot Be Dropped

~~~javascript
db.index_practice.dropIndex("_id_");
~~~

MongoDB rejects the operation. Do not try to modify or delete data files to experiment further.

## 19. Case-Study Exercises and Review Questions

### Scenario 1 — Is an Index on _id Needed?

An application stores 5 million customer documents. An API always retrieves a customer by **_id**. A colleague proposes:

~~~javascript
db.customers.createIndex({ _id: 1 });
~~~

Explain why this is not a necessary new index on a standard collection, and which tools should be used to confirm.

### Scenario 2 — Duplicate Business Codes

Two customers with different `_id` values but the same **customerCode** are getting saved. Propose a unique index:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, customerCode: 1 },
  { unique: true, name: "uq_tenant_customer_code" }
);
~~~

If legacy data contains duplicates, what must be done before running the migration?

### Scenario 3 — Index Reporting Few Accesses

Index **ix_monthly_report** has not been used in the past 14 days. Should it be dropped immediately? Explain why you must check reporting schedules, unique constraints, query hints, observation windows, and recovery plans.

### Scenario 4 — Slow Queries After a Drop

A team drops **ix_category_status** thinking it is "unnecessary." After deployment, the category/status filter endpoint latency jumps from tens to hundreds of milliseconds. Describe the investigation workflow using **getIndexes**, **explain**, rollback options, and the operational impacts of rebuilding the index.

### Scenario 5 — Tenant-Specific Uniqueness in a Sharded Cluster

A collection is sharded by **tenantId**, and IDs are generated independently across multiple services. Why must you consider cluster-wide uniqueness of **_id** and shard-key restrictions on unique indexes? Propose ID generation guidelines and data-model validation before sharding.

### Self-Check Questions

1. Why does MongoDB create the **_id_** index automatically?
2. Does **_id** have to be an ObjectId? Why does the BSON type of `_id` matter when querying?
3. How do **createIndex()** and **getIndexes()** serve two different goals?
4. How does **{category:1,status:1}** differ from **{status:1,category:1}**?
5. If a unique index is created on a collection that already contains duplicate keys, what can happen?
6. Can **dropIndex("_id_")** be used on a standard collection?
7. Does **dropIndex()** delete documents? Why is dropping a unique index still dangerous?
8. Does **getIndexes()** prove an index is frequently used by the query planner? What other tools are needed?
9. Why can indexes increase write latency even when read queries get faster?
10. When should you consider a **hidden index** instead of dropping immediately?
11. Why can projecting **_id: 0** matter when analyzing covered queries?
12. Does the **_id_** index always enforce cluster-wide uniqueness in a sharded cluster if `_id` is not the shard key?
13. How will an API using **hint** by index name be affected if that index is dropped?
14. Why shouldn't an index migration be treated as "completely risk-free" just because it runs as a single `createIndex` line?

## 20. Summary

A standard MongoDB collection already has an **index on _id** from the moment it is created. This index supports identifier lookups and enforces uniqueness within MongoDB's guaranteed scope. It does not replace indexes designed for business keys, filter fields, sorts, or other constraints.

Three basic index management operations:

~~~javascript
// 1. Create an index for an actual query pattern.
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);

// 2. List and verify keys and options.
db.products.getIndexes();

// 3. Drop an index that is no longer needed, after assessing impact.
db.products.dropIndex("ix_category_status");
~~~

**Key principles:**

1. **Do not recreate the _id index** just to speed up `_id` queries; it already exists on standard collections.
2. **Do not confuse _id uniqueness with business key uniqueness**; use another unique index when the domain requires it, and account for sharding.
3. **Create indexes from access patterns**, including filters, sorts, projections, and query frequency.
4. **Give indexes meaningful names** so they are easy to manage across migrations.
5. **getIndexes inspects definitions**, while **explain/$indexStats/metrics** clarify impact and usage.
6. **Dropping an index does not delete documents**, though it can remove unique/TTL constraints and slow down queries.
7. **Prefer testing with hide first** when assessing the impact of removing an index, then drop only if truly appropriate.
8. **Measure write costs and storage**, since more indexes can make every insert/update/delete more expensive.
9. **Do not rely on outdated version assumptions** regarding index builds or auto-index creation; verify against your running MongoDB and driver versions.
10. **Manage indexes as part of database schema and deployment pipelines**, not as ad-hoc commands run from arbitrary requests.

### Official Documentation for Further Reading

- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — overview of indexes and index types.
- [Default _id Index](https://www.mongodb.com/docs/manual/indexes/#default-id-index) — the default `_id` index.
- [db.collection.createIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — parameters, options, and index creation behavior.
- [db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/) — listing index specifications.
- [db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/) — dropping indexes.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hide/unhide for impact testing.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — reading query plans and executionStats.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness and limitations.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — **createIndex**, **listIndexes**, **dropIndex**.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — **IndexOperations**, **@Indexed**, **@CompoundIndex**.

In Java/Spring Data applications, distinguish **desired index definitions** from **indexes actually present in MongoDB**. Every addition, modification, or removal of an index should be treated as a change impacting both data correctness and system performance.
